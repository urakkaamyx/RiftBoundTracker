using System.Net.Http;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json.Serialization;

namespace RiftBoundTracker.App.Services;

public sealed record RemoteAccessStatus(bool Active, string? Url, string? Error, bool Installed);

file sealed class NgrokTunnelsResponse
{
    [JsonPropertyName("tunnels")] public List<NgrokTunnel> Tunnels { get; set; } = [];
}

file sealed class NgrokTunnel
{
    [JsonPropertyName("public_url")] public string PublicUrl { get; set; } = "";
    [JsonPropertyName("proto")] public string Proto { get; set; } = "";
}

/// <summary>
/// Opt-in WAN access via an ngrok tunnel to the app's plain HTTP port — ngrok terminates its own
/// TLS on the public side, so unlike the LAN QR flow there's no self-signed-certificate warning
/// for whoever opens the link. Deliberately never auto-started: this is a real widening of who can
/// reach the app (from "same Wi-Fi" to "anyone with the URL"), on an app that currently has no
/// authentication at all, so it only ever runs when a user explicitly asks for it in this session
/// — never persisted as "always on" across restarts.
///
/// Talks to ngrok two ways: spawns the `ngrok` CLI as a child process, then polls ngrok's own
/// local API (127.0.0.1:4040, ngrok's own convention, nothing this app defines) for the assigned
/// public URL rather than screen-scraping process output for it. Stdout/stderr are still captured,
/// though — this is written assuming most installs of RiftKeep will NOT already have ngrok set up
/// (unlike the dev machine this was built on), so a failure needs to surface ngrok's own real
/// error text (not authenticated, not installed at all, etc.) rather than a generic timeout, since
/// that's the difference between a user knowing what to do next and not.
/// </summary>
public sealed class NgrokService(int httpPort, IHttpClientFactory httpClientFactory, ILogger<NgrokService> logger) : IDisposable
{
    private const string LocalApiBase = "http://127.0.0.1:4040/api/tunnels";

    private readonly object _lock = new();
    private System.Diagnostics.Process? _process;
    private string? _url;
    private string? _error;
    private bool? _installed;

    public async Task<RemoteAccessStatus> GetStatusAsync(CancellationToken ct = default)
    {
        var installed = await IsInstalledAsync(ct);
        lock (_lock) return new RemoteAccessStatus(_url is not null, _url, _error, installed);
    }

    public async Task<RemoteAccessStatus> StartAsync(CancellationToken ct = default)
    {
        lock (_lock)
        {
            if (_url is not null) return new RemoteAccessStatus(true, _url, null, true);
            _error = null;
        }

        if (!await IsInstalledAsync(ct))
        {
            const string message = "ngrok isn't installed on this machine. Download it from ngrok.com/download, " +
                "sign up for a free account, run the \"ngrok config add-authtoken <token>\" command it gives you " +
                "once in a terminal, then try again.";
            lock (_lock) _error = message;
            return new RemoteAccessStatus(false, null, message, false);
        }

        var output = new StringBuilder();
        try
        {
            var process = new System.Diagnostics.Process
            {
                StartInfo = new System.Diagnostics.ProcessStartInfo
                {
                    FileName = "ngrok",
                    Arguments = $"http {httpPort} --log=stdout",
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                },
            };
            process.OutputDataReceived += (_, e) => { if (e.Data is not null) lock (output) output.AppendLine(e.Data); };
            process.ErrorDataReceived += (_, e) => { if (e.Data is not null) lock (output) output.AppendLine(e.Data); };
            process.Start();
            process.BeginOutputReadLine();
            process.BeginErrorReadLine();
            lock (_lock) _process = process;

            var http = httpClientFactory.CreateClient();
            var url = await PollForUrlAsync(http, process, ct);
            if (url is null)
            {
                // The process exiting on its own (bad/missing authtoken, free-tier limit already in
                // use elsewhere, etc.) is the common failure case for a fresh install — its own
                // stdout/stderr says exactly why far better than anything this app could guess.
                string capturedOutput;
                lock (output) capturedOutput = output.ToString().Trim();
                Stop();
                var message = capturedOutput.Length > 0
                    ? $"ngrok didn't start a tunnel:\n{Cap(capturedOutput, 500)}"
                    : "ngrok started but never reported a tunnel URL. Run \"ngrok config check\" in a terminal to confirm it's set up correctly.";
                lock (_lock) _error = message;
                return new RemoteAccessStatus(false, null, message, true);
            }

            lock (_lock) _url = url;
            return new RemoteAccessStatus(true, url, null, true);
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Failed to start ngrok tunnel");
            Stop();
            lock (_lock) _error = ex.Message;
            return new RemoteAccessStatus(false, null, ex.Message, true);
        }
    }

    private async Task<bool> IsInstalledAsync(CancellationToken ct)
    {
        lock (_lock)
        {
            if (_installed is { } cached) return cached;
        }
        bool installed;
        try
        {
            using var probe = System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo
            {
                FileName = "ngrok",
                Arguments = "version",
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            });
            if (probe is null) { installed = false; }
            else
            {
                await probe.WaitForExitAsync(ct);
                installed = probe.ExitCode == 0;
            }
        }
        catch (System.ComponentModel.Win32Exception)
        {
            installed = false;
        }
        lock (_lock) _installed = installed;
        return installed;
    }

    private static async Task<string?> PollForUrlAsync(HttpClient http, System.Diagnostics.Process process, CancellationToken ct)
    {
        // ngrok needs a moment to establish the tunnel after the process starts — poll its local
        // API rather than guessing a fixed delay. Also bail out early if the process has already
        // exited (a bad authtoken fails fast; no point waiting out the full timeout for that).
        for (var attempt = 0; attempt < 30; attempt++)
        {
            if (process.HasExited) return null;
            await Task.Delay(500, ct);
            try
            {
                var response = await http.GetFromJsonAsync<NgrokTunnelsResponse>(LocalApiBase, ct);
                var httpsTunnel = response?.Tunnels.FirstOrDefault(t => t.Proto == "https");
                if (httpsTunnel is not null) return httpsTunnel.PublicUrl;
            }
            catch
            {
                // Local API not up yet — keep polling until the attempt budget runs out.
            }
        }
        return null;
    }

    private static string Cap(string text, int maxChars) =>
        text.Length > maxChars ? text[..maxChars] + "…" : text;

    public void Stop()
    {
        System.Diagnostics.Process? process;
        lock (_lock)
        {
            process = _process;
            _process = null;
            _url = null;
            _error = null;
        }
        if (process is null) return;
        try
        {
            if (!process.HasExited) process.Kill(entireProcessTree: true);
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Failed to stop ngrok process");
        }
        finally
        {
            process.Dispose();
        }
    }

    public void Dispose() => Stop();
}
