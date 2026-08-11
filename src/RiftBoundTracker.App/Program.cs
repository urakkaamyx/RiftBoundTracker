using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using Microsoft.EntityFrameworkCore;
using RiftBoundTracker.App.Data;
using RiftBoundTracker.App.Desktop;
using RiftBoundTracker.App.Services;

namespace RiftBoundTracker.App;

internal static class Program
{
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool AllocConsole();

    // WPF needs the UI thread to be STA. Top-level statements can't be decorated with
    // [STAThread] (there's no method signature to attach it to), so this app uses a normal
    // explicit Main instead.
    [STAThread]
    private static void Main(string[] args)
    {
        // The app normally runs with no console at all (see the WinExe change) so a friend
        // troubleshooting an issue has nowhere to see what's happening. --debug-console opens one
        // on demand without needing a whole separate build — AllocConsole works even though the
        // exe itself is the GUI (WinExe) subsystem; Console.Out/Error just need re-pointing at it
        // since the runtime already decided at startup that there was no console to write to.
        if (args.Contains("--debug-console"))
        {
            AllocConsole();
            var stdout = new StreamWriter(Console.OpenStandardOutput()) { AutoFlush = true };
            Console.SetOut(stdout);
            var stderr = new StreamWriter(Console.OpenStandardError()) { AutoFlush = true };
            Console.SetError(stderr);
            Console.Title = "RiftBound Vault - Debug Console";
            Console.WriteLine("=== RiftBound Vault debug console ===");
            Console.WriteLine("Diagnostic output shows up here. Leave this window open while you reproduce the issue, then copy/paste what it shows.");
            Console.WriteLine();
        }

        var (app, port, httpsPort) = BuildApp(args).GetAwaiter().GetResult();
        app.StartAsync().GetAwaiter().GetResult();
        PrintStartupBanner(port, httpsPort);

        // --headless (or no interactive desktop session, e.g. a scheduled task) skips the window
        // and just runs as a background server, same as before this app had a UI at all.
        var headless = args.Contains("--headless") || !Environment.UserInteractive;
        if (headless)
        {
            app.WaitForShutdownAsync().GetAwaiter().GetResult();
        }
        else
        {
            // "localhost" counts as a secure context even over plain HTTP (the spec carves out
            // loopback addresses), so the desktop window skips the self-signed-cert warning the
            // phone has to click through — it navigates to the plain HTTP port instead of TLS.
            // The lifetime is passed through so IHostApplicationLifetime.StopApplication() (the
            // self-update flow calls this) actually closes the WPF window instead of leaving the
            // process running with the message loop blocked forever.
            var lifetime = app.Services.GetRequiredService<IHostApplicationLifetime>();
            new DesktopShell(port, lifetime).Run();
            app.StopAsync().GetAwaiter().GetResult();
        }
    }

    private static async Task<(WebApplication App, int Port, int HttpsPort)> BuildApp(string[] args)
    {
        var builder = WebApplication.CreateBuilder(args);

        // Bound how long shutdown can take — the default host shutdown timeout waits longer than
        // makes sense for a small local app, and if anything ever did hang draining a connection,
        // this keeps it from looking permanently "stuck" instead of just closing.
        builder.Host.ConfigureHostOptions(o => o.ShutdownTimeout = TimeSpan.FromSeconds(5));

        var port = builder.Configuration.GetValue<int?>("Port") ?? 5080;
        var httpsPort = builder.Configuration.GetValue<int?>("HttpsPort") ?? 5443;

        var dataDir = Path.Combine(builder.Environment.ContentRootPath, "App_Data");
        Directory.CreateDirectory(dataDir);
        Directory.CreateDirectory(Path.Combine(dataDir, "images"));

        // Live camera access (getUserMedia) only works in a "secure context" — HTTPS, or localhost.
        // The phone hits this over a LAN IP, so it needs a real (if self-signed) TLS endpoint too.
        var devCert = DevCertificateProvider.GetOrCreate(
            Path.Combine(dataDir, "certs", "devcert.pfx"), GetLanAddresses());

        builder.WebHost.ConfigureKestrel(options =>
        {
            options.ListenAnyIP(port);
            options.ListenAnyIP(httpsPort, listenOptions => listenOptions.UseHttps(devCert));
        });

        var dbPath = Path.Combine(dataDir, "riftbound.db");
        builder.Services.AddDbContext<AppDbContext>(opt => opt.UseSqlite($"Data Source={dbPath}"));

        builder.Services.AddHttpClient<RiftcodexClient>(c =>
        {
            c.BaseAddress = new Uri("https://api.riftcodex.com");
            c.Timeout = TimeSpan.FromSeconds(30);
            // The default HttpClient sends no User-Agent at all, which bot/WAF protection
            // (Cloudflare etc.) treats as an obvious non-browser signal. A bare UA header alone
            // isn't always enough against stricter bot-scoring — filling in the rest of what a
            // real browser sends when it loads riftcodex.com (Referer/Origin so it looks like a
            // same-site API call the page itself made, Accept-Language, and the Sec-Fetch-* hints
            // Chromium adds) gives it more to match against than a UA string in isolation.
            c.DefaultRequestHeaders.UserAgent.ParseAdd(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36");
            c.DefaultRequestHeaders.Accept.ParseAdd("application/json, text/plain, */*");
            c.DefaultRequestHeaders.AcceptLanguage.ParseAdd("en-US,en;q=0.9");
            c.DefaultRequestHeaders.Referrer = new Uri("https://riftcodex.com/");
            c.DefaultRequestHeaders.Add("Origin", "https://riftcodex.com");
            c.DefaultRequestHeaders.Add("Sec-Fetch-Site", "same-site");
            c.DefaultRequestHeaders.Add("Sec-Fetch-Mode", "cors");
            c.DefaultRequestHeaders.Add("Sec-Fetch-Dest", "empty");
        });
        builder.Services.AddHttpClient("card-images", c => c.Timeout = TimeSpan.FromSeconds(30));
        builder.Services.AddHttpClient("github", c =>
        {
            c.DefaultRequestHeaders.UserAgent.ParseAdd("RiftBoundVault-UpdateChecker");
            c.Timeout = TimeSpan.FromSeconds(60);
        });

        builder.Services.AddSingleton<ImageHashService>();
        builder.Services.AddSingleton<OcrService>();
        builder.Services.AddSingleton<UpdateService>();
        builder.Services.AddSingleton<BrowserRelayClient>();
        builder.Services.AddScoped<CardCacheService>();
        builder.Services.AddScoped<ScanService>();

        var app = builder.Build();

        using (var scope = app.Services.CreateScope())
        {
            var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();

            // An update should never cost the user their collection. If there's a real schema
            // change (a migration to apply) rather than a first-ever launch, snapshot the DB
            // first so a bad migration is recoverable instead of silently destructive.
            var pending = (await db.Database.GetPendingMigrationsAsync()).ToList();
            if (pending.Count > 0 && File.Exists(dbPath))
            {
                var backupPath = $"{dbPath}.bak-{DateTime.UtcNow:yyyyMMddHHmmss}";
                File.Copy(dbPath, backupPath, overwrite: false);
                app.Logger.LogInformation("Applying {Count} pending migration(s); backed up DB to {Backup}", pending.Count, backupPath);
            }

            await db.Database.MigrateAsync();
        }

        // A safety net for anything that slips past a route's own error handling: without this,
        // an unhandled exception anywhere (a flaky external API, a bad file, whatever) surfaces
        // to the client as a bare connection failure and dumps a raw stack trace to the console
        // instead of a message someone can actually act on.
        app.UseExceptionHandler(handler =>
        {
            handler.Run(async ctx =>
            {
                var error = ctx.Features.Get<Microsoft.AspNetCore.Diagnostics.IExceptionHandlerFeature>()?.Error;
                app.Logger.LogError(error, "Unhandled exception on {Path}", ctx.Request.Path);

                ctx.Response.StatusCode = error is RiftcodexApiException ? 502 : 500;
                ctx.Response.ContentType = "application/json";
                await ctx.Response.WriteAsJsonAsync(new { error = error?.Message ?? "Something went wrong." });
            });
        });

        app.UseDefaultFiles();
        app.UseStaticFiles();
        app.UseStaticFiles(new StaticFileOptions
        {
            FileProvider = new Microsoft.Extensions.FileProviders.PhysicalFileProvider(Path.Combine(dataDir, "images")),
            RequestPath = "/card-images"
        });

        app.MapGet("/api/server-info", () =>
            Results.Ok(new { httpPort = port, httpsPort, version = UpdateService.CurrentVersion.ToString() }));

        app.MapGet("/api/connection-info", () =>
        {
            var lanIp = GetLanAddresses().FirstOrDefault();
            return lanIp is null
                ? Results.Ok(new { available = false })
                : Results.Ok(new { available = true, url = $"https://{lanIp}:{httpsPort}", lanIp, httpsPort });
        });

        app.MapGet("/api/connection-qr.png", () =>
        {
            var lanIp = GetLanAddresses().FirstOrDefault();
            if (lanIp is null) return Results.NotFound();

            var url = $"https://{lanIp}:{httpsPort}";
            using var qrGenerator = new QRCoder.QRCodeGenerator();
            using var qrData = qrGenerator.CreateQrCode(url, QRCoder.QRCodeGenerator.ECCLevel.Q);
            var png = new QRCoder.PngByteQRCode(qrData).GetGraphic(12);
            return Results.File(png, "image/png");
        });

        app.MapGet("/api/update/check", async (UpdateService updater, CancellationToken ct) =>
            Results.Ok(await updater.CheckAsync(ct)));

        app.MapPost("/api/update/apply", async (UpdateService updater, IHostApplicationLifetime lifetime, CancellationToken ct) =>
        {
            try
            {
                await updater.ApplyAsync(ct);
            }
            catch (InvalidOperationException ex)
            {
                return Results.BadRequest(new { error = ex.Message });
            }

            // Respond before the process exits so the client actually gets this confirmation.
            _ = Task.Run(async () =>
            {
                await Task.Delay(500);
                lifetime.StopApplication();
            });
            return Results.Ok(new { started = true });
        });

        app.MapGet("/api/sets", async (CardCacheService cache, CancellationToken ct)
            => Results.Ok(await cache.GetSetsAsync(ct)));

        app.MapPost("/api/sync/{setId}", async (string setId, CardCacheService cache, CancellationToken ct) =>
        {
            var count = await cache.SyncSetAsync(setId, progress: null, ct);
            return Results.Ok(new { setId = setId.ToUpperInvariant(), synced = count });
        });

        app.MapGet("/api/cards", async (
            string? search, string? setId, string? type, string? rarity, string? domain, string? owned, string? sort,
            CardCacheService cache, CancellationToken ct) =>
        {
            var q = new CardQuery(search, setId, type, rarity, domain, owned, sort ?? "num-asc");
            return Results.Ok(await cache.QueryAsync(q, ct));
        });

        app.MapGet("/api/stats", async (string? setId, CardCacheService cache, CancellationToken ct)
            => Results.Ok(await cache.GetStatsAsync(setId, ct)));

        app.MapPost("/api/collection/{cardId}", async (string cardId, OwnedRequest body, CardCacheService cache, CancellationToken ct) =>
        {
            var updated = await cache.SetOwnedAsync(cardId, body.Owned, ct);
            return updated is null ? Results.NotFound() : Results.Ok(updated);
        });

        app.MapGet("/api/cards/lookup", async (string? setId, int number, CardCacheService cache, CancellationToken ct) =>
        {
            var matches = string.IsNullOrWhiteSpace(setId)
                ? await cache.FindAllByNumberAsync(number, ct)
                : (await cache.FindByNumberAsync(setId, number, ct) is { } single ? [single] : new List<CardEntity>());
            return Results.Ok(matches);
        });

        app.MapPost("/api/scan", async (HttpRequest request, ScanService scanner, CancellationToken ct) =>
        {
            if (!request.HasFormContentType)
                return Results.BadRequest(new { error = "Expected multipart/form-data with a 'photo' file." });

            var form = await request.ReadFormAsync(ct);
            var file = form.Files["photo"];
            if (file is null || file.Length == 0)
                return Results.BadRequest(new { error = "Missing 'photo' file." });

            var setHint = form["setId"].ToString();
            var fast = form["fast"].ToString() == "true";
            await using var stream = file.OpenReadStream();
            var result = await scanner.ScanAsync(stream, string.IsNullOrWhiteSpace(setHint) ? null : setHint, fast, ct);
            return Results.Ok(result);
        });

        return (app, port, httpsPort);
    }

    private static void PrintStartupBanner(int port, int httpsPort)
    {
        var addresses = GetLanAddresses();
        Console.WriteLine();
        Console.WriteLine("  RiftBound Vault is running:");
        Console.WriteLine($"    Local:        http://localhost:{port}");
        Console.WriteLine($"    Local (TLS):  https://localhost:{httpsPort}");
        for (var i = 0; i < addresses.Count; i++)
        {
            var note = i == 0 ? "  (most likely)" : "";
            Console.WriteLine($"    Phone:        http://{addresses[i]}:{port}{note}");
            Console.WriteLine($"    Phone (TLS):  https://{addresses[i]}:{httpsPort}{note}  <- use this for live camera scan");
        }
        if (addresses.Count == 0)
            Console.WriteLine("    Phone:   no LAN address detected — check your network connection.");
        Console.WriteLine("    (The TLS link uses a self-signed cert — your browser will warn once; tap Advanced -> Proceed.)");
        Console.WriteLine();
    }

    private static List<string> GetLanAddresses()
    {
        // Real tunnel/VPN adapters (not reachable from a phone on the same Wi-Fi) get excluded by name;
        // everything else is kept and ranked by how likely it is to be the actual home-LAN address,
        // since Hyper-V/WSL virtual switches can legitimately carry the real bridged Wi-Fi IP.
        string[] excludeHints = ["vpn", "tailscale", "radmin", "hamachi"];

        var candidates = NetworkInterface.GetAllNetworkInterfaces()
            .Where(nic => nic.OperationalStatus == OperationalStatus.Up)
            .Where(nic => nic.NetworkInterfaceType != NetworkInterfaceType.Loopback)
            .Where(nic => !excludeHints.Any(h => nic.Description.Contains(h, StringComparison.OrdinalIgnoreCase)
                                                || nic.Name.Contains(h, StringComparison.OrdinalIgnoreCase)))
            .SelectMany(nic => nic.GetIPProperties().UnicastAddresses)
            .Where(addr => addr.Address.AddressFamily == AddressFamily.InterNetwork)
            .Where(addr => !IPAddress.IsLoopback(addr.Address))
            .Where(addr => !addr.Address.ToString().StartsWith("169.254."))
            .Select(addr => addr.Address.ToString())
            .Distinct()
            .OrderBy(RankLanAddress)
            .ToList();

        return candidates;
    }

    private static int RankLanAddress(string ip)
    {
        if (ip.StartsWith("192.168.")) return 0;
        if (ip.StartsWith("10.")) return 1;
        for (var block = 16; block <= 31; block++)
            if (ip.StartsWith($"172.{block}.")) return 2;
        return 3;
    }
}

public record OwnedRequest(int Owned);
