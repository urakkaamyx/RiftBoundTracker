using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json.Serialization;

namespace RiftBoundTracker.App.Services.Rules;

public sealed record LocalAiModelStatus(
    bool Present, string? FileName, long? Bytes, string Phase, long DownloadedBytes, long TotalBytes, string? Error);

file sealed class GitHubReleaseAsset
{
    [JsonPropertyName("name")] public string Name { get; set; } = "";
    [JsonPropertyName("size")] public long Size { get; set; }
    [JsonPropertyName("browser_download_url")] public string BrowserDownloadUrl { get; set; } = "";
}

file sealed class GitHubRelease
{
    [JsonPropertyName("assets")] public List<GitHubReleaseAsset> Assets { get; set; } = [];
}

/// <summary>
/// Ask Rules' GGUF models are ~1GB+ assets that change far less often than the app itself —
/// bundling one into every app release zip meant every release (even a one-line CSS fix) re-zipped
/// and re-uploaded/re-downloaded that same blob. Each model in LocalAiModelCatalog lives entirely
/// on its own, hosted under its own release tag, and this service fetches whichever one is asked
/// for directly into App_Data — never into the install directory, since the self-update relauncher
/// wholesale-replaces everything except App_Data (see UpdateService's relaunch script), which would
/// otherwise delete a model that isn't part of the new app zip.
///
/// Each model gets its own subfolder (App_Data/Models/{modelId}/) so more than one can be
/// downloaded at once — switching which model Ask Rules uses (RulesLocalAiSettingsService's
/// SelectedModelId) shouldn't require re-downloading one you already have.
/// </summary>
public sealed class LocalAiModelService(IWebHostEnvironment env, IHttpClientFactory httpClientFactory, ILogger<LocalAiModelService> logger)
{
    private const string Owner = "urakkaamyx";
    private const string Repo = "RiftBoundTracker";

    private string ModelsRootDir => Path.Combine(env.ContentRootPath, "App_Data", "Models");
    private string ModelDir(string modelId) => Path.Combine(ModelsRootDir, modelId);

    private readonly object _progressLock = new();
    private string? _downloadingModelId;
    private LocalAiModelStatus _progress = new(false, null, null, "idle", 0, 0, null);

    public string? FindModelPath(string modelId)
    {
        MigrateLegacyModelIfPresent();
        var dir = ModelDir(modelId);
        return Directory.Exists(dir) ? Directory.EnumerateFiles(dir, "*.gguf").FirstOrDefault() : null;
    }

    public LocalAiModelStatus GetStatus(string modelId)
    {
        var path = FindModelPath(modelId);
        lock (_progressLock)
        {
            var progress = _downloadingModelId == modelId ? _progress : new LocalAiModelStatus(false, null, null, "idle", 0, 0, null);
            return progress with
            {
                Present = path is not null,
                FileName = path is null ? null : Path.GetFileName(path),
                Bytes = path is null ? null : new FileInfo(path).Length,
            };
        }
    }

    private void SetProgress(Func<LocalAiModelStatus, LocalAiModelStatus> update)
    {
        lock (_progressLock) _progress = update(_progress);
    }

    // Versions before the multi-model split shipped a single model at either Models/*.gguf (the
    // install dir, pre-App_Data-split) or App_Data/Models/*.gguf directly (the original App_Data
    // split, before per-model subfolders) — either one, if still there, is the default model and
    // gets moved into its own subfolder instead of making an existing user re-download it.
    private void MigrateLegacyModelIfPresent()
    {
        try
        {
            var defaultDir = ModelDir(LocalAiModelCatalog.DefaultModelId);
            if (Directory.Exists(defaultDir) && Directory.EnumerateFiles(defaultDir, "*.gguf").Any()) return;

            var flatAppDataFile = Directory.Exists(ModelsRootDir)
                ? Directory.EnumerateFiles(ModelsRootDir, "*.gguf", SearchOption.TopDirectoryOnly).FirstOrDefault()
                : null;
            var legacyInstallDir = Path.Combine(env.ContentRootPath, "Models");
            var legacyInstallFile = Directory.Exists(legacyInstallDir)
                ? Directory.EnumerateFiles(legacyInstallDir, "*.gguf").FirstOrDefault()
                : null;
            var source = flatAppDataFile ?? legacyInstallFile;
            if (source is null) return;

            Directory.CreateDirectory(defaultDir);
            var dest = Path.Combine(defaultDir, Path.GetFileName(source));
            logger.LogInformation("Migrating existing local AI model into its own subfolder ({ModelId}).", LocalAiModelCatalog.DefaultModelId);
            File.Move(source, dest);
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Local AI model migration failed — will download fresh instead.");
        }
    }

    public async Task DownloadAsync(string modelId, CancellationToken ct = default)
    {
        var option = LocalAiModelCatalog.Resolve(modelId);
        lock (_progressLock) _downloadingModelId = option.Id;
        try
        {
            SetProgress(p => p with { Phase = "checking", Error = null });
            var http = httpClientFactory.CreateClient("github");
            var release = await http.GetFromJsonAsync<GitHubRelease>(
                $"https://api.github.com/repos/{Owner}/{Repo}/releases/tags/{option.ReleaseTag}", ct)
                ?? throw new InvalidOperationException("Couldn't reach GitHub to fetch the model release.");

            var asset = release.Assets.FirstOrDefault(a => a.Name.EndsWith(".gguf", StringComparison.OrdinalIgnoreCase))
                ?? throw new InvalidOperationException("The model release has no .gguf asset attached.");

            var dir = ModelDir(option.Id);
            Directory.CreateDirectory(dir);
            var destPath = Path.Combine(dir, asset.Name);
            var tempPath = destPath + ".partial";

            SetProgress(p => p with { Phase = "downloading", DownloadedBytes = 0, TotalBytes = asset.Size });
            using (var response = await http.GetAsync(asset.BrowserDownloadUrl, HttpCompletionOption.ResponseHeadersRead, ct))
            {
                response.EnsureSuccessStatusCode();
                var totalBytes = response.Content.Headers.ContentLength ?? asset.Size;
                await using var httpStream = await response.Content.ReadAsStreamAsync(ct);
                await using var fileStream = File.Create(tempPath);
                var buffer = new byte[81920];
                long downloaded = 0;
                int read;
                while ((read = await httpStream.ReadAsync(buffer, ct)) > 0)
                {
                    await fileStream.WriteAsync(buffer.AsMemory(0, read), ct);
                    downloaded += read;
                    SetProgress(p => p with { Phase = "downloading", DownloadedBytes = downloaded, TotalBytes = totalBytes });
                }
            }

            // Clear out any other .gguf already in this model's own subfolder before promoting the
            // new one — there should only ever be one file per model on disk at a time. Other
            // models' subfolders are untouched.
            foreach (var existing in Directory.EnumerateFiles(dir, "*.gguf"))
                File.Delete(existing);
            File.Move(tempPath, destPath, overwrite: true);

            SetProgress(p => p with { Phase = "done", DownloadedBytes = asset.Size, TotalBytes = asset.Size });
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Local AI model download failed for {ModelId}", option.Id);
            SetProgress(p => p with { Phase = "error", Error = ex.Message });
            throw;
        }
    }
}
