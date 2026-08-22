using System.Diagnostics;
using System.IO.Compression;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace RiftBoundTracker.App.Services.Rules;

public sealed record RulesEngineStatus(bool Installed, bool Running, string Phase, long DownloadedBytes, long TotalBytes, string? Error);

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
/// Manages the RiftKeep Rules Engine (Python, Milestone 19 "Stable 1.0") as a local sidecar
/// process — download it into App_Data on first use (same fetch-on-first-use pattern
/// LocalAiModelService already used for the GGUF model: never bundled in the base install, never
/// touched by the self-update relauncher since App_Data survives updates), launch it, and manage
/// its lifetime. RiftKeep talks to it exclusively over its Product API v1
/// (http://127.0.0.1:8765) — this service owns the process, RulesEngineClient owns the HTTP calls.
///
/// Per the engine's own integration guide: never silently launch a second copy (always probe
/// /v1/status first), and readiness is more than a 200 response — the guide's health-check flow is
/// reachable -> Stable 1.0 -> authority complete -> runtime snapshot healthy, in that order. A
/// degraded/fail-closed status must not be treated as ready to serve Ask Rules.
/// </summary>
public sealed class RulesEngineSidecarService(
    IWebHostEnvironment env, IHttpClientFactory httpClientFactory,
    IHostApplicationLifetime lifetime, ILogger<RulesEngineSidecarService> logger) : IDisposable
{
    private const string Owner = "urakkaamyx";
    private const string Repo = "RiftBoundTracker";
    private const string ReleaseTag = "rules-engine-v1.0.1";
    private const int Port = 8765;

    public static readonly Uri BaseAddress = new($"http://127.0.0.1:{Port}/");

    private string EngineRootDir => Path.Combine(env.ContentRootPath, "App_Data", "RulesEngine");
    private string PythonExePath => Path.Combine(EngineRootDir, "python", "python.exe");
    private string EntryScriptPath => Path.Combine(EngineRootDir, "riftkeep.py");

    private readonly SemaphoreSlim _gate = new(1, 1);
    private readonly object _progressLock = new();
    private RulesEngineStatus _progress = new(false, false, "idle", 0, 0, null);
    private Process? _process;
    private bool _shutdownRegistered;

    public bool IsInstalled => File.Exists(PythonExePath) && File.Exists(EntryScriptPath);

    public RulesEngineStatus GetStatus()
    {
        lock (_progressLock)
            return _progress with { Installed = IsInstalled, Running = _process is { HasExited: false } };
    }

    private void SetProgress(Func<RulesEngineStatus, RulesEngineStatus> update)
    {
        lock (_progressLock) _progress = update(_progress);
    }

    /// <summary>
    /// Downloads and extracts the packaged sidecar bundle (portable Python + engine, built by
    /// scripts/package-rules-engine.ps1) from its GitHub release into App_Data. Same shape as
    /// LocalAiModelService.DownloadAsync — resolve the release by tag, stream to a .partial file,
    /// extract, clean up — but a zip needing extraction instead of a single .gguf file.
    /// </summary>
    public async Task DownloadAsync(CancellationToken ct = default)
    {
        try
        {
            SetProgress(p => p with { Phase = "checking", Error = null });
            var http = httpClientFactory.CreateClient("github");
            var release = await http.GetFromJsonAsync<GitHubRelease>(
                $"https://api.github.com/repos/{Owner}/{Repo}/releases/tags/{ReleaseTag}", ct)
                ?? throw new InvalidOperationException("Couldn't reach GitHub to fetch the rules engine release.");

            var asset = release.Assets.FirstOrDefault(a => a.Name.EndsWith(".zip", StringComparison.OrdinalIgnoreCase))
                ?? throw new InvalidOperationException("The rules engine release has no .zip asset attached.");

            Directory.CreateDirectory(Path.GetDirectoryName(EngineRootDir)!);
            var tempZipPath = EngineRootDir + ".partial.zip";

            SetProgress(p => p with { Phase = "downloading", DownloadedBytes = 0, TotalBytes = asset.Size });
            using (var response = await http.GetAsync(asset.BrowserDownloadUrl, HttpCompletionOption.ResponseHeadersRead, ct))
            {
                response.EnsureSuccessStatusCode();
                var totalBytes = response.Content.Headers.ContentLength ?? asset.Size;
                await using var httpStream = await response.Content.ReadAsStreamAsync(ct);
                await using var fileStream = File.Create(tempZipPath);
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

            SetProgress(p => p with { Phase = "extracting" });
            if (Directory.Exists(EngineRootDir)) Directory.Delete(EngineRootDir, recursive: true);
            var extractTempDir = EngineRootDir + ".extracting";
            if (Directory.Exists(extractTempDir)) Directory.Delete(extractTempDir, recursive: true);
            ZipFile.ExtractToDirectory(tempZipPath, extractTempDir);
            File.Delete(tempZipPath);

            // scripts/package-rules-engine.ps1 zips the "RulesEngine" folder itself (not just its
            // contents), so the archive has one extra nesting level to flatten.
            var nested = Path.Combine(extractTempDir, "RulesEngine");
            Directory.Move(Directory.Exists(nested) ? nested : extractTempDir, EngineRootDir);
            if (Directory.Exists(extractTempDir)) Directory.Delete(extractTempDir, recursive: true);

            SetProgress(p => p with { Phase = "done", DownloadedBytes = asset.Size, TotalBytes = asset.Size });
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Rules engine download failed");
            SetProgress(p => p with { Phase = "error", Error = ex.Message });
            throw;
        }
    }

    /// <summary>
    /// Ensures the sidecar is installed, running, and healthy. Safe to call repeatedly — probes
    /// /v1/status first (possibly reaching an instance this process didn't start) before ever
    /// spawning a child process, per the integration guide's explicit "never silently launch a
    /// second copy."
    /// </summary>
    public async Task<bool> EnsureRunningAsync(CancellationToken ct = default)
    {
        await _gate.WaitAsync(ct);
        try
        {
            if (await IsHealthyAsync(ct)) return true;

            if (!IsInstalled)
            {
                await DownloadAsync(ct);
                if (!IsInstalled) return false;
            }

            StartProcess();

            var deadline = DateTime.UtcNow.AddSeconds(30);
            while (DateTime.UtcNow < deadline)
            {
                if (await IsHealthyAsync(ct)) return true;
                await Task.Delay(500, ct);
            }
            logger.LogWarning("Rules engine did not become healthy within the startup timeout.");
            return false;
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task RestartAsync(CancellationToken ct = default)
    {
        StopProcess();
        await EnsureRunningAsync(ct);
    }

    private void StartProcess()
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = PythonExePath,
            ArgumentList = { EntryScriptPath, "serve" },
            WorkingDirectory = EngineRootDir,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        _process = new Process { StartInfo = startInfo, EnableRaisingEvents = true };
        _process.OutputDataReceived += (_, e) => { if (e.Data is not null) logger.LogDebug("[rules-engine] {Line}", e.Data); };
        _process.ErrorDataReceived += (_, e) => { if (e.Data is not null) logger.LogDebug("[rules-engine] {Line}", e.Data); };
        _process.Start();
        _process.BeginOutputReadLine();
        _process.BeginErrorReadLine();
        logger.LogInformation("Started rules engine sidecar (PID {Pid})", _process.Id);

        if (!_shutdownRegistered)
        {
            _shutdownRegistered = true;
            lifetime.ApplicationStopping.Register(StopProcess);
        }
    }

    private void StopProcess()
    {
        var process = _process;
        _process = null;
        if (process is null) return;
        try
        {
            if (!process.HasExited) process.Kill(entireProcessTree: true);
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Failed to stop the rules engine sidecar cleanly");
        }
        finally
        {
            process.Dispose();
        }
    }

    /// <summary>
    /// The multi-condition readiness check from the integration guide: reachable, "ok", and not
    /// degraded/fail-closed. Deliberately does not require authority.status == "complete" here —
    /// that's a real, possible, non-degraded state (a future overlay not yet mirrored) that the
    /// engine itself surfaces per-question rather than refusing to serve at all; the sidecar only
    /// needs to know the *process* is healthy, not that today's authority happens to be complete.
    /// </summary>
    private async Task<bool> IsHealthyAsync(CancellationToken ct)
    {
        try
        {
            var http = httpClientFactory.CreateClient();
            http.BaseAddress = BaseAddress;
            http.Timeout = TimeSpan.FromSeconds(3);
            using var response = await http.GetAsync("v1/status", ct);
            if (!response.IsSuccessStatusCode) return false;
            var status = await response.Content.ReadFromJsonAsync<JsonElement>(cancellationToken: ct);
            if (!status.TryGetProperty("ok", out var okProp) || okProp.ValueKind != JsonValueKind.True) return false;
            if (status.TryGetProperty("runtime", out var runtime)
                && runtime.TryGetProperty("degraded", out var degraded)
                && degraded.ValueKind == JsonValueKind.True)
                return false;
            return true;
        }
        catch
        {
            return false;
        }
    }

    public void Dispose() => StopProcess();
}
