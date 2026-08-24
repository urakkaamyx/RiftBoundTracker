using System.Text.Json;
using System.Windows;
using System.Windows.Threading;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.Wpf;

namespace RiftBoundTracker.App.Services;

public sealed record RiftKeepSignInResult(string Token, string Tier, DateTimeOffset ExpiresAt, string? DiscordUsername);

/// <summary>
/// Opens a real, visible window running a configured RiftKeep server's Discord sign-in flow, and
/// waits for the server's TokenIssued page to hand the issued token back via
/// window.chrome.webview.postMessage (see RiftKeepServer's Views/Account/TokenIssued.cshtml —
/// it feature-detects window.chrome.webview so the same page still works fine in a normal browser).
///
/// Runs on its own dedicated STA thread with a private Dispatcher/message loop — same pattern as
/// BrowserRelayClient — rather than depending on the main WPF Application's UI thread, so this
/// works the same whether the app currently has a visible main window or not (including
/// --headless mode, where Application.Current is null but a one-off sign-in window still works).
/// </summary>
public sealed class DiscordSignInService(IWebHostEnvironment env, ILogger<DiscordSignInService> logger)
{
    public Task<RiftKeepSignInResult?> SignInAsync(string serverBaseUrl, CancellationToken ct = default)
    {
        var tcs = new TaskCompletionSource<RiftKeepSignInResult?>(TaskCreationOptions.RunContinuationsAsynchronously);
        var thread = new Thread(() => RunSignInWindow(serverBaseUrl, tcs))
        {
            IsBackground = true,
            Name = "DiscordSignIn",
        };
        thread.SetApartmentState(ApartmentState.STA);
        thread.Start();

        if (ct.CanBeCanceled)
            ct.Register(() => tcs.TrySetCanceled(ct));

        return tcs.Task;
    }

    private void RunSignInWindow(string serverBaseUrl, TaskCompletionSource<RiftKeepSignInResult?> tcs)
    {
        try
        {
            var dispatcher = Dispatcher.CurrentDispatcher;
            var webView = new WebView2();
            var window = new Window
            {
                Title = "Sign in with Discord — RiftKeep",
                Width = 480,
                Height = 720,
                WindowStartupLocation = WindowStartupLocation.CenterScreen,
                Content = webView,
            };

            // Fires whether the user closes the window manually (cancelled — TrySetResult(null) is
            // then the "real" outcome) or this service closes it itself after a successful sign-in
            // (TrySetResult already ran with the real payload, so this second call is just a no-op)
            // — either way the dispatcher needs to stop pumping so this thread can exit.
            window.Closed += (_, _) =>
            {
                tcs.TrySetResult(null);
                dispatcher.InvokeShutdown();
            };

            _ = InitializeAndNavigateAsync(webView, window, serverBaseUrl, tcs);

            window.Show();
            window.Activate();
            Dispatcher.Run();
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Discord sign-in window failed");
            tcs.TrySetException(ex);
        }
    }

    private async Task InitializeAndNavigateAsync(WebView2 webView, Window window, string serverBaseUrl, TaskCompletionSource<RiftKeepSignInResult?> tcs)
    {
        try
        {
            var userDataFolder = Path.Combine(env.ContentRootPath, "App_Data", "webview2-signin");
            Directory.CreateDirectory(userDataFolder);
            var environment = await CoreWebView2Environment.CreateAsync(userDataFolder: userDataFolder);
            await webView.EnsureCoreWebView2Async(environment);

            webView.CoreWebView2.WebMessageReceived += (_, args) =>
            {
                try
                {
                    var json = args.WebMessageAsJson;
                    var payload = JsonSerializer.Deserialize<RiftKeepSignInResult>(json, new JsonSerializerOptions(JsonSerializerDefaults.Web));
                    if (payload is null) return;
                    tcs.TrySetResult(payload);
                    window.Close();
                }
                catch (Exception ex)
                {
                    logger.LogWarning(ex, "Could not parse the sign-in message from the RiftKeep server");
                }
            };

            webView.Source = new Uri($"{serverBaseUrl.TrimEnd('/')}/account/login");
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Discord sign-in WebView2 initialization failed");
            tcs.TrySetException(ex);
            window.Close();
        }
    }
}
