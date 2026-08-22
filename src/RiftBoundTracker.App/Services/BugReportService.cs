using System.Net.Http;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json.Serialization;

namespace RiftBoundTracker.App.Services;

/// <summary>
/// Files a bug report directly as a GitHub Issue using a fine-grained token scoped to ONLY
/// "Issues: write" on this one repo — never committed to source, baked into release builds by
/// scripts/release.ps1 from an environment variable. Worst case if a build is ever decompiled and
/// the token extracted: someone can spam issues on this one public repo, nothing else.
///
/// GitHub's Issues REST API has no way to attach a binary image to an issue or comment — that
/// upload path only exists behind the website's own session-authenticated flow, not the public
/// API, regardless of token scope. So the screenshot never goes through this service at all: the
/// frontend copies it straight to the OS clipboard and the app opens the newly-created issue in
/// the user's browser, so a single Ctrl+V drops it in as a comment.
/// </summary>
public class BugReportService(
    IHttpClientFactory httpClientFactory,
    IConfiguration config,
    IWebHostEnvironment env,
    ILogger<BugReportService> logger)
{
    private const string Owner = "urakkaamyx";
    private const string Repo = "RiftBoundTracker";

    private string LogPath => Path.Combine(env.ContentRootPath, "App_Data", "logs", "riftkeep.log");

    public string GetRecentLogTail(int maxChars = 8000)
    {
        try
        {
            if (!File.Exists(LogPath)) return "(no log file yet)";
            using var stream = new FileStream(LogPath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
            using var reader = new StreamReader(stream);
            var text = reader.ReadToEnd();
            return text.Length <= maxChars ? text : text[^maxChars..];
        }
        catch (Exception ex)
        {
            return $"(could not read log: {ex.Message})";
        }
    }

    // Finds the app's own window by title (DesktopShell titles both the launcher and main window
    // This process's own main window (not FindWindow-by-title — a dev instance and the live app
    // both title their window "RiftKeep", and FindWindow searches every top-level window on the
    // desktop regardless of which process owns it, so a title match alone can grab the wrong
    // process's window entirely). Works regardless of which page/modal is showing, since this is a
    // real screen capture, not a DOM render. Returns null (rather than throwing) when there's no
    // window at all — e.g. running --headless and only ever reached via a browser.
    public byte[]? CaptureAppWindow()
    {
        try
        {
            var hwnd = System.Diagnostics.Process.GetCurrentProcess().MainWindowHandle;
            if (hwnd == IntPtr.Zero || !NativeMethods.GetWindowRect(hwnd, out var rect)) return null;
            var width = rect.Right - rect.Left;
            var height = rect.Bottom - rect.Top;
            if (width <= 0 || height <= 0) return null;

            using var bitmap = new System.Drawing.Bitmap(width, height);
            using var g = System.Drawing.Graphics.FromImage(bitmap);
            g.CopyFromScreen(rect.Left, rect.Top, 0, 0, new System.Drawing.Size(width, height));
            using var ms = new MemoryStream();
            bitmap.Save(ms, System.Drawing.Imaging.ImageFormat.Png);
            return ms.ToArray();
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Bug report window capture failed");
            return null;
        }
    }

    public async Task<BugReportResult> SubmitIssueAsync(string title, string description, CancellationToken ct)
    {
        var token = config["BugReport:GitHubToken"];
        if (string.IsNullOrWhiteSpace(token))
            return new BugReportResult(false, "Bug reporting isn't set up in this build (no token configured).", null);

        var body = new StringBuilder();
        body.AppendLine(description);
        body.AppendLine();
        body.AppendLine("---");
        body.AppendLine($"**App version:** {UpdateService.CurrentVersion}");
        body.AppendLine($"**OS:** {RuntimeInformation.OSDescription}");
        body.AppendLine($"**Reported:** {DateTime.UtcNow:u}");
        body.AppendLine();
        body.AppendLine("<details><summary>Recent log</summary>");
        body.AppendLine();
        body.AppendLine("```");
        body.AppendLine(GetRecentLogTail());
        body.AppendLine("```");
        body.AppendLine("</details>");
        body.AppendLine();
        body.AppendLine("_Screenshot: reporter was prompted to paste one into a comment below._");

        var http = httpClientFactory.CreateClient("github");
        using var request = new HttpRequestMessage(HttpMethod.Post, $"https://api.github.com/repos/{Owner}/{Repo}/issues");
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
        request.Headers.Accept.ParseAdd("application/vnd.github+json");
        request.Content = JsonContent.Create(new { title, body = body.ToString(), labels = new[] { "bug", "user-report" } });

        try
        {
            using var response = await http.SendAsync(request, ct);
            if (!response.IsSuccessStatusCode)
            {
                var errText = await response.Content.ReadAsStringAsync(ct);
                logger.LogWarning("Bug report submission failed: {Status} {Body}", response.StatusCode, errText);
                return new BugReportResult(false, $"GitHub rejected the report ({(int)response.StatusCode}).", null);
            }
            var payload = await response.Content.ReadFromJsonAsync<GitHubIssueResponse>(cancellationToken: ct);
            return new BugReportResult(true, "Issue created.", payload?.HtmlUrl);
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Bug report submission failed");
            return new BugReportResult(false, $"Couldn't reach GitHub: {ex.Message}", null);
        }
    }

    private sealed record GitHubIssueResponse([property: JsonPropertyName("html_url")] string HtmlUrl);
}

public sealed record BugReportResult(bool Ok, string Message, string? IssueUrl);

internal static class NativeMethods
{
    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool GetWindowRect(IntPtr hWnd, out Rect rect);

    public struct Rect { public int Left, Top, Right, Bottom; }
}
