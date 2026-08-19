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
/// The Ask Rules GGUF model is a ~940MB asset that changes far less often than the app itself —
/// bundling it into every app release zip meant every release (even a one-line CSS fix) re-zipped
/// and re-uploaded/re-downloaded that same ~1GB blob. It now lives entirely on its own, hosted as
/// the "ask-rules-model-v1" release tag (see scripts/training/README.md), and this service fetches
/// it directly into App_Data — never into the install directory, since the self-update relauncher
/// wholesale-replaces everything except App_Data (see UpdateService's relaunch script), which would
/// otherwise delete a model that isn't part of the new app zip.
/// </summary>
public sealed class LocalAiModelService(IWebHostEnvironment env, IHttpClientFactory httpClientFactory, ILogger<LocalAiModelService> logger)
{
    private const string Owner = "urakkaamyx";
    private const string Repo = "RiftBoundTracker";
    private const string ModelReleaseTag = "ask-rules-model-v1";

    private string ModelDir => Path.Combine(env.ContentRootPath, "App_Data", "Models");

    private readonly object _progressLock = new();
    private LocalAiModelStatus _progress = new(false, null, null, "idle", 0, 0, null);

    public string? FindModelPath()
    {
        MigrateLegacyModelIfPresent();
        return Directory.Exists(ModelDir) ? Directory.EnumerateFiles(ModelDir, "*.gguf").FirstOrDefault() : null;
    }

    public LocalAiModelStatus GetStatus()
    {
        var path = FindModelPath();
        lock (_progressLock)
        {
            return _progress with
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

    // Versions before this split shipped the model at Models/*.gguf under the install directory —
    // if that's still there (a self-update from an older version) and App_Data has nothing yet,
    // reuse it instead of making an existing user re-download ~940MB they already have.
    private void MigrateLegacyModelIfPresent()
    {
        try
        {
            if (Directory.Exists(ModelDir) && Directory.EnumerateFiles(ModelDir, "*.gguf").Any()) return;
            var legacyDir = Path.Combine(env.ContentRootPath, "Models");
            if (!Directory.Exists(legacyDir)) return;
            var legacyFile = Directory.EnumerateFiles(legacyDir, "*.gguf").FirstOrDefault();
            if (legacyFile is null) return;

            Directory.CreateDirectory(ModelDir);
            var dest = Path.Combine(ModelDir, Path.GetFileName(legacyFile));
            logger.LogInformation("Migrating existing local AI model from install directory into App_Data.");
            File.Move(legacyFile, dest);
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Local AI model migration from the install directory failed — will download fresh instead.");
        }
    }

    public async Task DownloadAsync(CancellationToken ct = default)
    {
        try
        {
            SetProgress(p => p with { Phase = "checking", Error = null });
            var http = httpClientFactory.CreateClient("github");
            var release = await http.GetFromJsonAsync<GitHubRelease>(
                $"https://api.github.com/repos/{Owner}/{Repo}/releases/tags/{ModelReleaseTag}", ct)
                ?? throw new InvalidOperationException("Couldn't reach GitHub to fetch the model release.");

            var asset = release.Assets.FirstOrDefault(a => a.Name.EndsWith(".gguf", StringComparison.OrdinalIgnoreCase))
                ?? throw new InvalidOperationException("The model release has no .gguf asset attached.");

            Directory.CreateDirectory(ModelDir);
            var destPath = Path.Combine(ModelDir, asset.Name);
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

            // Clear out any other .gguf already in App_Data/Models before promoting the new one —
            // there should only ever be one model on disk at a time.
            foreach (var existing in Directory.EnumerateFiles(ModelDir, "*.gguf"))
                File.Delete(existing);
            File.Move(tempPath, destPath, overwrite: true);

            SetProgress(p => p with { Phase = "done", DownloadedBytes = asset.Size, TotalBytes = asset.Size });
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Local AI model download failed");
            SetProgress(p => p with { Phase = "error", Error = ex.Message });
            throw;
        }
    }
}
