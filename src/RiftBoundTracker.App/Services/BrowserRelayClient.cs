using System.Windows;
using System.Windows.Threading;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.Wpf;

namespace RiftBoundTracker.App.Services;

/// <summary>
/// A hidden, off-screen WebView2 instance used as a last-resort fallback when the plain
/// HttpClient path to an external API gets blocked by bot/TLS-fingerprint detection that no
/// amount of header spoofing can get past. A plain .NET HttpClient has a fundamentally different
/// TLS handshake signature than a real browser — some WAFs (Cloudflare's bot management included)
/// fingerprint that at the TLS layer before HTTP headers are even read, which no User-Agent or
/// Referer trick can spoof. WebView2 is a genuine Chromium engine, so requests it makes carry the
/// same fingerprint a normal browser visiting the site would.
///
/// Runs on its own dedicated STA thread with a private message loop, so it works the same whether
/// or not the app currently has a visible desktop window (including --headless mode).
/// </summary>
public sealed class BrowserRelayClient(IWebHostEnvironment env, ILogger<BrowserRelayClient> logger) : IAsyncDisposable
{
    private readonly string _userDataFolder = Path.Combine(env.ContentRootPath, "App_Data", "webview2-relay");
    private readonly TaskCompletionSource _ready = new();
    private Thread? _thread;
    private Dispatcher? _dispatcher;
    private WebView2? _webView;
    private volatile bool _failed;

    private Task EnsureStartedAsync()
    {
        if (_thread is not null) return _ready.Task;

        lock (_ready)
        {
            if (_thread is not null) return _ready.Task;
            _thread = new Thread(RunMessageLoop) { IsBackground = true, Name = "BrowserRelay" };
            _thread.SetApartmentState(ApartmentState.STA);
            _thread.Start();
        }
        return _ready.Task;
    }

    private void RunMessageLoop()
    {
        try
        {
            _dispatcher = Dispatcher.CurrentDispatcher;

            var hiddenWindow = new Window
            {
                Width = 4,
                Height = 4,
                WindowStyle = WindowStyle.None,
                ShowInTaskbar = false,
                ShowActivated = false,
                Left = -32000,
                Top = -32000,
            };
            _webView = new WebView2();
            hiddenWindow.Content = _webView;
            hiddenWindow.Show();

            // EnsureCoreWebView2Async requires the dispatcher's message loop to already be pumping
            // — BeginInvoke queues this to run once Dispatcher.Run() below has actually started,
            // rather than running it synchronously here before the loop exists.
            _dispatcher.BeginInvoke(() => _ = InitializeWebViewAsync());

            Dispatcher.Run();
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Browser relay failed to start");
            _failed = true;
            _ready.TrySetResult();
        }
    }

    private async Task InitializeWebViewAsync()
    {
        try
        {
            Directory.CreateDirectory(_userDataFolder);
            var environment = await CoreWebView2Environment.CreateAsync(userDataFolder: _userDataFolder);
            await _webView!.EnsureCoreWebView2Async(environment);
            _ready.TrySetResult();
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Browser relay WebView2 initialization failed");
            _failed = true;
            _ready.TrySetResult();
        }
    }

    private const string BaseSiteUrl = "https://riftcodex.com/";
    private bool _baseSiteLoaded;

    /// <summary>
    /// Loads the real riftcodex.com site once (a normal page, not a raw API response — Chromium's
    /// built-in viewer for a direct JSON navigation turns out to run fetch() in a restricted
    /// context that doesn't behave like a normal page), then runs <c>fetch()</c> against the given
    /// API URL from within that already-loaded page and returns the raw response text. Subsequent
    /// calls reuse the same loaded page instead of re-navigating each time — exactly like a normal
    /// browser tab making several API calls without reloading.
    /// </summary>
    public async Task<byte[]?> FetchBytesAsync(string url, CancellationToken ct = default)
    {
        await EnsureStartedAsync();
        await _ready.Task;
        if (_failed || _dispatcher is null || _webView is null) return null;

        return await _dispatcher.InvokeAsync(async () =>
        {
            var core = _webView!.CoreWebView2;

            if (!_baseSiteLoaded)
            {
                var navTcs = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
                void NavHandler(object? s, CoreWebView2NavigationCompletedEventArgs e) => navTcs.TrySetResult(e.IsSuccess);
                core.NavigationCompleted += NavHandler;
                try
                {
                    using var reg = ct.Register(() => navTcs.TrySetCanceled(ct));
                    core.Navigate(BaseSiteUrl);
                    _baseSiteLoaded = await navTcs.Task.WaitAsync(TimeSpan.FromSeconds(20), ct);
                }
                catch (TimeoutException)
                {
                    logger.LogWarning("Browser relay timed out loading {Url}", BaseSiteUrl);
                    return null;
                }
                finally
                {
                    core.NavigationCompleted -= NavHandler;
                }

                if (!_baseSiteLoaded)
                {
                    logger.LogWarning("Browser relay couldn't load {Url}", BaseSiteUrl);
                    return null;
                }
            }

            // ExecuteScriptAsync's return value only reflects the script's synchronous completion
            // value — a bare Promise serializes to "{}" (promises have no own enumerable
            // properties), it is not awaited for you. The documented way to get an async result
            // back out is postMessage() from the page + WebMessageReceived on this side.
            var msgTcs = new TaskCompletionSource<string?>(TaskCreationOptions.RunContinuationsAsynchronously);
            void MessageHandler(object? s, CoreWebView2WebMessageReceivedEventArgs e)
                => msgTcs.TrySetResult(e.TryGetWebMessageAsString());
            core.WebMessageReceived += MessageHandler;

            try
            {
                var jsUrl = System.Text.Json.JsonSerializer.Serialize(url);
                var script = $$"""
                    fetch({{jsUrl}})
                        .then(r => r.text())
                        .then(t => window.chrome.webview.postMessage(t))
                        .catch(e => window.chrome.webview.postMessage('FETCH_ERROR: ' + String(e)));
                    """;
                await core.ExecuteScriptAsync(script);

                using var reg = ct.Register(() => msgTcs.TrySetCanceled(ct));
                var text = await msgTcs.Task.WaitAsync(TimeSpan.FromSeconds(20), ct);

                if (text is null || text.StartsWith("FETCH_ERROR:"))
                {
                    logger.LogWarning("Browser relay fetch of {Url} failed: {Text}", url, text);
                    return null;
                }
                return System.Text.Encoding.UTF8.GetBytes(text);
            }
            catch (TimeoutException)
            {
                logger.LogWarning("Browser relay timed out fetching {Url}", url);
                return null;
            }
            finally
            {
                core.WebMessageReceived -= MessageHandler;
            }
        }).Task.Unwrap();
    }

    /// <summary>
    /// Fetches a binary payload (an image) from an arbitrary origin — deliberately separate from
    /// <see cref="FetchBytesAsync"/> in two ways. First, that method reads the response as text and
    /// UTF-8 re-encodes it, which is lossy for arbitrary bytes and silently corrupts anything
    /// binary; this reads the response as a blob and base64-encodes it in JS instead, which
    /// round-trips through the string-only WebMessage bridge intact. Second, that method reuses a
    /// page already loaded on <see cref="BaseSiteUrl"/> (riftcodex.com) so its fetches are
    /// same-origin API calls; a `fetch()` to a *different* origin's images from that page would be
    /// cross-origin and get CORS-blocked regardless of engine, so this always navigates to the
    /// target image's own origin first (no `_baseSiteLoaded` caching — this is a rare, one-time
    /// seeding path, not a hot one).
    /// </summary>
    public async Task<byte[]?> FetchImageBytesAsync(string url, CancellationToken ct = default)
    {
        await EnsureStartedAsync();
        await _ready.Task;
        if (_failed || _dispatcher is null || _webView is null) return null;

        var origin = new Uri(url).GetLeftPart(UriPartial.Authority) + "/";

        return await _dispatcher.InvokeAsync(async () =>
        {
            var core = _webView!.CoreWebView2;

            var navTcs = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            void NavHandler(object? s, CoreWebView2NavigationCompletedEventArgs e) => navTcs.TrySetResult(e.IsSuccess);
            core.NavigationCompleted += NavHandler;
            bool loaded;
            try
            {
                using var reg = ct.Register(() => navTcs.TrySetCanceled(ct));
                core.Navigate(origin);
                loaded = await navTcs.Task.WaitAsync(TimeSpan.FromSeconds(20), ct);
            }
            catch (TimeoutException)
            {
                logger.LogWarning("Browser relay timed out loading {Url}", origin);
                return null;
            }
            finally
            {
                core.NavigationCompleted -= NavHandler;
            }
            if (!loaded)
            {
                logger.LogWarning("Browser relay couldn't load {Url}", origin);
                return null;
            }
            _baseSiteLoaded = false; // this instance now sits on a foreign origin — force FetchBytesAsync to renavigate to riftcodex.com next time

            var msgTcs = new TaskCompletionSource<string?>(TaskCreationOptions.RunContinuationsAsynchronously);
            void MessageHandler(object? s, CoreWebView2WebMessageReceivedEventArgs e)
                => msgTcs.TrySetResult(e.TryGetWebMessageAsString());
            core.WebMessageReceived += MessageHandler;

            try
            {
                var jsUrl = System.Text.Json.JsonSerializer.Serialize(url);
                var script = $$"""
                    fetch({{jsUrl}})
                        .then(r => r.blob())
                        .then(b => new Promise((resolve, reject) => {
                            const reader = new FileReader();
                            reader.onload = () => resolve(reader.result.split(',')[1]);
                            reader.onerror = reject;
                            reader.readAsDataURL(b);
                        }))
                        .then(b64 => window.chrome.webview.postMessage(b64))
                        .catch(e => window.chrome.webview.postMessage('FETCH_ERROR: ' + String(e)));
                    """;
                await core.ExecuteScriptAsync(script);

                using var reg = ct.Register(() => msgTcs.TrySetCanceled(ct));
                var base64 = await msgTcs.Task.WaitAsync(TimeSpan.FromSeconds(20), ct);

                if (base64 is null || base64.StartsWith("FETCH_ERROR:"))
                {
                    logger.LogWarning("Browser relay image fetch of {Url} failed: {Text}", url, base64);
                    return null;
                }
                return Convert.FromBase64String(base64);
            }
            catch (TimeoutException)
            {
                logger.LogWarning("Browser relay timed out fetching image {Url}", url);
                return null;
            }
            finally
            {
                core.WebMessageReceived -= MessageHandler;
            }
        }).Task.Unwrap();
    }

    public async ValueTask DisposeAsync()
    {
        if (_dispatcher is null) return;
        await _dispatcher.InvokeAsync(() => _dispatcher.InvokeShutdown());
    }
}
