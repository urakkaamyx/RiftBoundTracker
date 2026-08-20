using System.IO.Compression;
using System.Net.Http;
using System.Net.Http.Json;
using System.Reflection;
using System.Text.Json.Serialization;

namespace RiftBoundTracker.App.Services;

public record UpdateCheckResult(
    string CurrentVersion, string? LatestVersion, bool UpdateAvailable,
    string? ReleaseNotes, bool SelfUpdateSupported, string? UnsupportedReason);

// Phase: "idle" | "downloading" | "extracting" | "restarting" | "error".
public record UpdateProgressState(string Phase, long BytesDownloaded, long TotalBytes, string? Error);

public record PatchNoteEntry(string Version, string? Notes);

public class GitHubRelease
{
    [JsonPropertyName("tag_name")] public string TagName { get; set; } = "";
    [JsonPropertyName("body")] public string? Body { get; set; }
    [JsonPropertyName("assets")] public List<GitHubReleaseAsset> Assets { get; set; } = [];
}

public class GitHubReleaseAsset
{
    [JsonPropertyName("name")] public string Name { get; set; } = "";
    [JsonPropertyName("browser_download_url")] public string BrowserDownloadUrl { get; set; } = "";
}

/// <summary>
/// Checks GitHub Releases for a newer build and, if found, downloads it, stages it, and hands off
/// to a small detached PowerShell script that waits for this process to exit, copies the new
/// files over the install directory, and relaunches — because Windows won't let a running process
/// overwrite its own executable. App_Data (the DB, cached images, TLS cert) is never part of the
/// release payload, so it's never touched by an update.
/// </summary>
public class UpdateService(IHttpClientFactory httpClientFactory, ILogger<UpdateService> logger)
{
    private const string Owner = "urakkaamyx";
    private const string Repo = "RiftBoundTracker";
    private const string AssetNameContains = "win-x64";

    private readonly object _progressLock = new();
    private UpdateProgressState _progress = new("idle", 0, 0, null);

    // ETag cache for the "latest release" lookup — checked on every page load plus a periodic
    // background poll (see app.js's checkUpdateIndicator), so a 304 Not Modified (the overwhelming
    // common case: no new release since last check) means GitHub sends back just a status code and
    // no body at all, instead of a full JSON payload every single time. Singleton-scoped so this
    // genuinely persists across the process lifetime rather than resetting per request.
    private readonly object _releaseCacheLock = new();
    private string? _cachedReleaseETag;
    private GitHubRelease? _cachedRelease;

    public UpdateProgressState GetProgress()
    {
        lock (_progressLock) return _progress;
    }

    private void SetProgress(UpdateProgressState progress)
    {
        lock (_progressLock) _progress = progress;
    }

    public static Version CurrentVersion =>
        Assembly.GetExecutingAssembly().GetName().Version ?? new Version(0, 0, 0);

    /// <summary>
    /// Self-update only makes sense for the published self-contained deployment — under
    /// `dotnet run` (a framework-dependent dev build) there's no bundled runtime to relaunch
    /// against, and the release zip's contents wouldn't even run there. `dotnet run` actually
    /// launches the apphost exe directly, so checking the process file name doesn't distinguish
    /// dev from published. The reliable signal: a self-contained deployment always ships the
    /// .NET runtime itself (coreclr.dll etc.) next to the exe; a framework-dependent build never
    /// does, since it relies on the globally-installed shared runtime instead.
    /// </summary>
    public static (bool Supported, string? Reason) SelfUpdateSupport()
    {
        var isSelfContained = File.Exists(Path.Combine(AppContext.BaseDirectory, "coreclr.dll"));
        if (!isSelfContained)
            return (false, "Self-update only works from the published build — not 'dotnet run'.");

        if (string.IsNullOrEmpty(Environment.ProcessPath))
            return (false, "Could not determine the running executable's path.");

        return (true, null);
    }

    public async Task<UpdateCheckResult> CheckAsync(CancellationToken ct = default)
    {
        var (supported, reason) = SelfUpdateSupport();
        var current = CurrentVersion;

        var release = await GetLatestReleaseAsync(ct);
        if (release is null)
            return new UpdateCheckResult(current.ToString(), null, false, null, supported, reason);

        var latest = ParseVersion(release.TagName);
        var updateAvailable = supported && latest is not null && latest > current;

        return new UpdateCheckResult(
            current.ToString(), latest?.ToString() ?? release.TagName, updateAvailable,
            release.Body, supported, reason);
    }

    public async Task ApplyAsync(CancellationToken ct = default)
    {
        try
        {
            var (supported, reason) = SelfUpdateSupport();
            if (!supported)
                throw new InvalidOperationException(reason ?? "Self-update isn't supported in this environment.");

            var release = await GetLatestReleaseAsync(ct)
                ?? throw new InvalidOperationException("Couldn't reach GitHub to fetch the latest release.");

            var asset = release.Assets.FirstOrDefault(a => a.Name.Contains(AssetNameContains, StringComparison.OrdinalIgnoreCase))
                ?? release.Assets.FirstOrDefault(a => a.Name.EndsWith(".zip", StringComparison.OrdinalIgnoreCase))
                ?? throw new InvalidOperationException($"Latest release '{release.TagName}' has no downloadable build attached.");

            // Trim any trailing separator: a Windows command-line argument ending in `\"` (backslash
            // immediately before the closing quote) is parsed as an escaped literal quote, not
            // "backslash then end-of-argument" — it silently runs the argument into the next token.
            // AppContext.BaseDirectory always ends with a trailing backslash, so this isn't optional.
            var installDir = AppContext.BaseDirectory.TrimEnd('\\', '/');
            var exeName = Path.GetFileName(Environment.ProcessPath!);

            CleanUpOldStagingDirs();
            var stagingRoot = Path.Combine(Path.GetTempPath(), $"RiftKeep-update-{Guid.NewGuid():N}");
            Directory.CreateDirectory(stagingRoot);

            logger.LogInformation("Downloading update {Tag} from {Url}", release.TagName, asset.BrowserDownloadUrl);
            var http = httpClientFactory.CreateClient("github");
            var zipPath = Path.Combine(stagingRoot, "update.zip");
            SetProgress(new UpdateProgressState("downloading", 0, 0, null));
            using (var response = await http.GetAsync(asset.BrowserDownloadUrl, HttpCompletionOption.ResponseHeadersRead, ct))
            {
                response.EnsureSuccessStatusCode();
                var totalBytes = response.Content.Headers.ContentLength ?? 0;
                await using var httpStream = await response.Content.ReadAsStreamAsync(ct);
                await using var fileStream = File.Create(zipPath);
                var buffer = new byte[81920];
                long downloaded = 0;
                int read;
                // A plain CopyToAsync gives no visibility into how far along a ~1GB download is —
                // read in chunks and report progress after each one instead, so the UI can show a
                // real percentage rather than an indefinite spinner for however long that takes.
                while ((read = await httpStream.ReadAsync(buffer, ct)) > 0)
                {
                    await fileStream.WriteAsync(buffer.AsMemory(0, read), ct);
                    downloaded += read;
                    SetProgress(new UpdateProgressState("downloading", downloaded, totalBytes, null));
                }
            }

            SetProgress(new UpdateProgressState("extracting", 0, 0, null));
            var extractDir = Path.Combine(stagingRoot, "extracted");
            ZipFile.ExtractToDirectory(zipPath, extractDir);
            File.Delete(zipPath);

            // A zip made from a folder sometimes wraps everything in one top-level folder — if so,
            // treat that as the real root instead of the zip's literal top level.
            var entries = Directory.GetFileSystemEntries(extractDir);
            var payloadDir = entries.Length == 1 && Directory.Exists(entries[0]) ? entries[0] : extractDir;

            var scriptPath = Path.Combine(stagingRoot, "relaunch.ps1");
            await File.WriteAllTextAsync(scriptPath, BuildRelauncherScript(), ct);

            logger.LogInformation("Handing off to relauncher; this process will now exit to release its file locks.");
            SetProgress(new UpdateProgressState("restarting", 0, 0, null));

            var psi = new System.Diagnostics.ProcessStartInfo
            {
                FileName = "powershell.exe",
                Arguments = $"-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"{scriptPath}\" " +
                            $"-ProcessId {Environment.ProcessId} -StagingDir \"{payloadDir}\" " +
                            $"-InstallDir \"{installDir}\" -ExeName \"{exeName}\"",
                UseShellExecute = true,
                WindowStyle = System.Diagnostics.ProcessWindowStyle.Hidden,
            };
            System.Diagnostics.Process.Start(psi);
        }
        catch (Exception ex)
        {
            SetProgress(new UpdateProgressState("error", 0, 0, ex.Message));
            throw;
        }
    }

    // The relauncher script deliberately doesn't delete its own staging directory — a script
    // can't safely delete the folder it's still executing out of. Instead, each new update run
    // sweeps up staging directories left behind by previous runs.
    private static void CleanUpOldStagingDirs()
    {
        try
        {
            foreach (var dir in Directory.GetDirectories(Path.GetTempPath(), "RiftKeep-update-*"))
                Directory.Delete(dir, recursive: true);
        }
        catch
        {
            // Best-effort — a locked leftover file just waits for next time.
        }
    }

    private async Task<GitHubRelease?> GetLatestReleaseAsync(CancellationToken ct)
    {
        string? etag;
        lock (_releaseCacheLock) etag = _cachedReleaseETag;

        try
        {
            var http = httpClientFactory.CreateClient("github");
            using var request = new HttpRequestMessage(
                HttpMethod.Get, $"https://api.github.com/repos/{Owner}/{Repo}/releases/latest");
            if (etag is not null)
                request.Headers.TryAddWithoutValidation("If-None-Match", etag);

            using var response = await http.SendAsync(request, ct);

            if (response.StatusCode == System.Net.HttpStatusCode.NotModified)
            {
                lock (_releaseCacheLock) return _cachedRelease;
            }

            response.EnsureSuccessStatusCode();
            var release = await response.Content.ReadFromJsonAsync<GitHubRelease>(cancellationToken: ct);
            lock (_releaseCacheLock)
            {
                _cachedRelease = release;
                // The full raw header value, not EntityTagHeaderValue.Tag — GitHub's ETags here are
                // weak (W/"..."), and .Tag strips that prefix. Sending it back without the prefix
                // would likely still match under HTTP's weak-comparison rules for GET, but there's
                // no reason to depend on that when the exact original value is right here.
                _cachedReleaseETag = response.Headers.TryGetValues("ETag", out var values) ? values.FirstOrDefault() : null;
            }
            return release;
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Failed to check GitHub for the latest release");
            // A transient failure shouldn't throw away a perfectly good cached answer — fall back
            // to whatever was last confirmed rather than reporting "no update info" for what might
            // just be one dropped request.
            lock (_releaseCacheLock) return _cachedRelease;
        }
    }

    // The Patch Notes view (settings footer's "View Patch Notes") shows the whole release history,
    // not just the latest version — GitHub's list endpoint already returns releases newest-first,
    // so no re-sorting needed. Each entry's own Body is exactly one version's CHANGELOG.md section
    // (release.ps1 seeds it from there), so the client can run the same per-version markdown
    // renderer it already uses for a single release's notes.
    public async Task<List<PatchNoteEntry>> GetAllReleaseNotesAsync(CancellationToken ct = default)
    {
        try
        {
            var http = httpClientFactory.CreateClient("github");
            var releases = await http.GetFromJsonAsync<List<GitHubRelease>>(
                $"https://api.github.com/repos/{Owner}/{Repo}/releases", ct) ?? [];
            return releases.Select(r => new PatchNoteEntry(r.TagName, r.Body)).ToList();
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Failed to fetch release history from GitHub");
            return [];
        }
    }

    private static Version? ParseVersion(string tag)
    {
        var trimmed = tag.TrimStart('v', 'V');
        return Version.TryParse(trimmed, out var v) ? v : null;
    }

    private static string BuildRelauncherScript() => """
        param(
            [int]$ProcessId,
            [string]$StagingDir,
            [string]$InstallDir,
            [string]$ExeName
        )

        try { Wait-Process -Id $ProcessId -Timeout 30 -ErrorAction SilentlyContinue } catch {}
        Start-Sleep -Seconds 1

        foreach ($item in Get-ChildItem -Path $StagingDir) {
            # App_Data (DB, cached images, TLS cert) must never be part of an update payload — the
            # csproj now excludes it from publish, but this is a second guard against a release
            # ever shipping it anyway: /MIR mirrors the destination to match the source exactly,
            # which would otherwise delete or overwrite a real user's data.
            if ($item.Name -eq "App_Data") { continue }
            $dest = Join-Path $InstallDir $item.Name
            if ($item.PSIsContainer) {
                robocopy $item.FullName $dest /MIR /NFL /NDL /NJH /NJS | Out-Null
            } else {
                Copy-Item -Path $item.FullName -Destination $dest -Force
            }
        }

        Start-Process -FilePath (Join-Path $InstallDir $ExeName) -WorkingDirectory $InstallDir
        """;
}
