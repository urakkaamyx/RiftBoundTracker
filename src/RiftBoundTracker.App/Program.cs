using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using Microsoft.EntityFrameworkCore;
using RiftBoundTracker.App.Data;
using RiftBoundTracker.App.Desktop;
using RiftBoundTracker.App.Services;
using RiftBoundTracker.App.Services.Rules;

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

            // Belt-and-suspenders for shutdown (see StopAsync note below): if graceful shutdown
            // ever hangs for any reason, force the process to exit anyway after a bounded wait so
            // an update can never leave someone stuck with two copies of the app running.
            lifetime.ApplicationStopping.Register(() => Task.Run(async () =>
            {
                await Task.Delay(TimeSpan.FromSeconds(8));
                Environment.Exit(0);
            }));

            new DesktopShell(port, app.Environment.WebRootPath, lifetime).Run();

            // Must not run on this STA thread: WPF's Application.Run() (inside DesktopShell.Run())
            // installs a DispatcherSynchronizationContext that stays set on the thread even after
            // the message loop returns. If StopAsync's internals ever await a continuation that
            // captures SynchronizationContext.Current, it would try to post back to a Dispatcher
            // that's no longer pumping messages — a deadlock the 5s ShutdownTimeout can't break,
            // since that only cancels a token, it can't force-unblock a stuck continuation. Running
            // it on a thread-pool thread (no captured context) sidesteps that entirely.
            Task.Run(() => app.StopAsync()).GetAwaiter().GetResult();
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
        builder.Services.AddHttpClient("justtcg", c =>
        {
            c.BaseAddress = new Uri("https://api.justtcg.com");
            c.Timeout = TimeSpan.FromSeconds(45);
            c.DefaultRequestHeaders.UserAgent.ParseAdd("RiftBoundVault-PriceTracker/2.0");
        });
        builder.Services.AddHttpClient("riftbound-gg", c =>
        {
            c.BaseAddress = new Uri("https://api.dotgg.gg");
            c.Timeout = TimeSpan.FromSeconds(45);
            c.DefaultRequestHeaders.UserAgent.ParseAdd("RiftBoundVault-PriceTracker/1.6");
            c.DefaultRequestHeaders.Accept.ParseAdd("application/json");
            c.DefaultRequestHeaders.AcceptLanguage.ParseAdd("en-US,en;q=0.9");
            c.DefaultRequestHeaders.Referrer = new Uri("https://riftbound.gg/prices/");
            c.DefaultRequestHeaders.Add("Origin", "https://riftbound.gg");
        });
        builder.Services.AddHttpClient("topdeck", c =>
        {
            c.BaseAddress = new Uri("https://topdeck.gg");
            c.Timeout = TimeSpan.FromSeconds(45);
            c.DefaultRequestHeaders.UserAgent.ParseAdd("RiftBoundVault-CommunitySync/1.0");
            c.DefaultRequestHeaders.Accept.ParseAdd("application/json");
        });
        builder.Services.AddHttpClient("rules-source", c =>
        {
            c.Timeout = TimeSpan.FromSeconds(60);
            c.DefaultRequestHeaders.UserAgent.ParseAdd(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36");
            c.DefaultRequestHeaders.Accept.ParseAdd("text/html,application/pdf,*/*");
            c.DefaultRequestHeaders.AcceptLanguage.ParseAdd("en-US,en;q=0.9");
        });

        builder.Services.AddSingleton<ImageHashService>();
        builder.Services.AddSingleton<OcrService>();
        builder.Services.AddSingleton<UpdateService>();
        builder.Services.AddSingleton<BrowserRelayClient>();
        builder.Services.AddScoped<CardCacheService>();
        builder.Services.AddScoped<ScanService>();
        builder.Services.AddScoped<CatalogSyncService>();
        builder.Services.AddScoped<DatabaseSafetyService>();
        builder.Services.AddScoped<DeckService>();
        builder.Services.AddScoped<VaultService>();
        builder.Services.AddScoped<PremadePackImportService>();
        builder.Services.AddScoped<PriceSyncService>();
        builder.Services.AddScoped<CardTextSymbolCatalogService>();
        builder.Services.AddScoped<IPriceProvider, JustTcgPriceProvider>();
        builder.Services.AddSingleton<RiftboundGgPriceService>();
        builder.Services.AddSingleton<PricingSettingsService>();
        builder.Services.AddSingleton<TopDeckSettingsService>();
        builder.Services.AddScoped<TopDeckClient>();
        builder.Services.AddScoped<CommunityCardResolver>();
        builder.Services.AddScoped<CommunityDeckSyncService>();
        builder.Services.AddScoped<CommunityRecommendationService>();
        builder.Services.AddScoped<NextJsArticlePageFetcher>();
        builder.Services.AddScoped<RulesSourceDiscoveryService>();
        builder.Services.AddScoped<RulesImportService>();
        builder.Services.AddScoped<RulesKeywordCatalogService>();
        builder.Services.AddScoped<RulesConceptCatalogService>();
        builder.Services.AddScoped<RulesKeywordLinkerService>();
        builder.Services.AddScoped<RulesSyncService>();
        builder.Services.AddScoped<RulesSearchService>();
        builder.Services.AddScoped<RulesService>();
        builder.Services.AddSingleton<RulesLocalAiSettingsService>();
        // Singleton: tracks download progress across requests the same way UpdateService does for
        // app updates, and the model file itself needs to be found consistently by both the
        // question-answering path and the status/progress endpoints.
        builder.Services.AddSingleton<LocalAiModelService>();
        // Singleton (not Scoped): holds the loaded model + context so it's loaded once and kept
        // resident across requests instead of reloading a ~1GB model on every question.
        builder.Services.AddSingleton<LocalLlmExplanationProvider>();
        builder.Services.AddSingleton<IRulesExplanationProvider>(sp => sp.GetRequiredService<LocalLlmExplanationProvider>());
        builder.Services.AddScoped<RulesQuestionService>();
        builder.Services.AddScoped<RulesEvidenceService>();
        builder.Services.AddScoped<RulesAnswerService>();

        var app = builder.Build();

        using (var scope = app.Services.CreateScope())
        {
            var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();

            // Back up through SQLite's own online-backup API so WAL pages are included, verify the
            // backup, run migrations, then prove that card and ownership totals are unchanged.
            var databaseSafety = scope.ServiceProvider.GetRequiredService<DatabaseSafetyService>();
            await databaseSafety.MigrateSafelyAsync(dbPath);

            var symbolCatalog = scope.ServiceProvider.GetRequiredService<CardTextSymbolCatalogService>();
            await symbolCatalog.EnsureSeededAsync();

            // First launch (or a DB that's never finished a full sync) — populate the whole
            // catalog automatically instead of requiring the old manual per-set sync. Runs in its
            // own background scope so it doesn't block app startup / the desktop window showing up.
            var catalogSync = scope.ServiceProvider.GetRequiredService<CatalogSyncService>();
            var needsInitialSync = !await catalogSync.HasEverSyncedAsync();
            var needsContentRefresh = await catalogSync.NeedsContentRefreshAsync();
            if (!args.Contains("--no-catalog-sync") && (needsInitialSync || needsContentRefresh))
            {
                var scopeFactory = app.Services.GetRequiredService<IServiceScopeFactory>();
                _ = Task.Run(async () =>
                {
                    using var bgScope = scopeFactory.CreateScope();
                    var bgSync = bgScope.ServiceProvider.GetRequiredService<CatalogSyncService>();
                    await bgSync.TrySyncAllAsync();
                });
            }
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
        app.UseStaticFiles(new StaticFileOptions
        {
            // The desktop shell's WebView2 window keeps the same on-disk HTTP cache across app
            // restarts — after a self-update swaps in new files, a plain cache hit could go on
            // serving pre-update JS/CSS/HTML with no way for the user to tell anything changed.
            // Forcing revalidation means real content changes (new ETag/Last-Modified) always win,
            // while an unchanged file still gets a cheap 304 instead of a full re-download.
            OnPrepareResponse = ctx => ctx.Context.Response.Headers.CacheControl = "no-cache"
        });
        app.UseStaticFiles(new StaticFileOptions
        {
            FileProvider = new Microsoft.Extensions.FileProviders.PhysicalFileProvider(Path.Combine(dataDir, "images")),
            RequestPath = "/card-images"
        });

        app.MapGet("/api/server-info", () =>
            Results.Ok(new { httpPort = port, httpsPort, version = UpdateService.CurrentVersion.ToString() }));

        app.MapGet("/api/health", async (AppDbContext db, DatabaseSafetyService safety, CancellationToken ct) =>
            Results.Ok(new
            {
                status = "ok",
                database = safety.LastStatus,
                cards = await db.Cards.CountAsync(ct),
                ownedCards = await db.Cards.CountAsync(c => c.OwnedCount > 0, ct),
                ownedCopies = await db.Cards.SumAsync(c => c.OwnedCount, ct),
                migrations = await db.Database.GetAppliedMigrationsAsync(ct),
            }));

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

        app.MapPost("/api/update/apply", (UpdateService updater, IHostApplicationLifetime lifetime, ILogger<UpdateService> logger) =>
        {
            // Fail fast, synchronously, for the case that's already known before any download
            // starts — nothing to poll progress for if self-update isn't even supported here.
            var (supported, reason) = UpdateService.SelfUpdateSupport();
            if (!supported)
                return Results.BadRequest(new { error = reason ?? "Self-update isn't supported in this environment." });

            // The download+extract can take a while for a ~1GB build — run it detached so this
            // request returns immediately and the client polls /api/update/progress instead of
            // holding one connection open (and showing nothing) for the entire duration.
            _ = Task.Run(async () =>
            {
                try
                {
                    await updater.ApplyAsync(CancellationToken.None);
                    // Give the client's next progress poll a chance to see the "restarting" phase
                    // before the connection actually drops.
                    await Task.Delay(800);
                    lifetime.StopApplication();
                }
                catch (Exception ex)
                {
                    logger.LogError(ex, "Self-update failed");
                }
            });
            return Results.Ok(new { started = true });
        });

        app.MapGet("/api/update/progress", (UpdateService updater) => Results.Ok(updater.GetProgress()));

        app.MapGet("/api/sets", async (CardCacheService cache, CancellationToken ct)
            => Results.Ok(await cache.GetSetsAsync(ct)));

        app.MapGet("/api/card-text-symbols", async (CardTextSymbolCatalogService symbols, CancellationToken ct) =>
            Results.Ok(await symbols.GetAllAsync(ct)));

        app.MapPost("/api/sync/{setId}", async (string setId, CardCacheService cache, CancellationToken ct) =>
        {
            var count = await cache.SyncSetAsync(setId, progress: null, ct);
            return Results.Ok(new { setId = setId.ToUpperInvariant(), synced = count });
        });

        app.MapPost("/api/sync/refresh", (IServiceScopeFactory scopeFactory) =>
        {
            _ = Task.Run(async () =>
            {
                using var scope = scopeFactory.CreateScope();
                var sync = scope.ServiceProvider.GetRequiredService<CatalogSyncService>();
                await sync.TrySyncAllAsync();
            });
            return Results.Ok(new { started = true });
        });

        app.MapGet("/api/sync/status", async (CatalogSyncService sync, CancellationToken ct) =>
            Results.Ok(await sync.GetStatusAsync(ct)));

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

        app.MapPost("/api/favorites/{cardId}", async (string cardId, FavoriteRequest body, VaultService vault, CancellationToken ct) =>
        {
            var updated = await vault.SetFavoriteAsync(cardId, body.Favorite, ct);
            return updated is null ? Results.NotFound() : Results.Ok(updated);
        });

        app.MapGet("/api/favorites", async (VaultService vault, CancellationToken ct) =>
            Results.Ok(await vault.GetFavoritesAsync(ct)));

        app.MapPost("/api/binder/{cardId}", async (string cardId, BinderRequest body, VaultService vault, CancellationToken ct) =>
        {
            var updated = await vault.SetBinderCountAsync(cardId, body.Count, ct);
            return updated is null ? Results.NotFound() : Results.Ok(updated);
        });

        app.MapGet("/api/binder", async (VaultService vault, CancellationToken ct) =>
            Results.Ok(await vault.GetBinderAsync(ct)));

        app.MapGet("/api/analytics", async (VaultService vault, CancellationToken ct) =>
            Results.Ok(await vault.GetOverviewAsync(ct)));

        app.MapGet("/api/decks", async (DeckService decks, CancellationToken ct) =>
            Results.Ok(await decks.GetAllAsync(ct)));

        app.MapGet("/api/decks/{id:int}", async (int id, DeckService decks, CancellationToken ct) =>
        {
            var deck = await decks.GetAsync(id, ct);
            return deck is null ? Results.NotFound() : Results.Ok(deck);
        });

        app.MapPost("/api/decks", async (CreateDeckRequest body, DeckService decks, CancellationToken ct) =>
            Results.Created("/api/decks", await decks.CreateAsync(body, ct)));

        app.MapPut("/api/decks/{id:int}", async (int id, UpdateDeckRequest body, DeckService decks, CancellationToken ct) =>
        {
            var deck = await decks.UpdateAsync(id, body, ct);
            return deck is null ? Results.NotFound() : Results.Ok(deck);
        });

        app.MapDelete("/api/decks/{id:int}", async (int id, DeckService decks, CancellationToken ct) =>
            await decks.DeleteAsync(id, ct) ? Results.NoContent() : Results.NotFound());

        app.MapPost("/api/decks/{id:int}/cards", async (int id, SetDeckCardRequest body, DeckService decks, CancellationToken ct) =>
        {
            var deck = await decks.SetCardAsync(id, body, ct);
            return deck is null ? Results.NotFound() : Results.Ok(deck);
        });

        app.MapPost("/api/decks/import", async (ImportDeckRequest body, DeckService decks, CancellationToken ct) =>
            Results.Ok(await decks.ImportAsync(body, ct)));

        app.MapGet("/api/premade-packs", () => Results.Ok(PremadePackCatalogService.Packs
            .Select(p => new { p.Key, p.Name, p.Wave, CardCount = p.Cards.Sum(c => c.Quantity) })));

        app.MapGet("/api/premade-packs/{key}/preview", async (string key, PremadePackImportService importer, CancellationToken ct) =>
        {
            var result = await importer.PreviewAsync(key, ct);
            return result is null ? Results.NotFound() : Results.Ok(result);
        });

        app.MapPost("/api/premade-packs/{key}/import", async (string key, PremadePackImportService importer, CancellationToken ct) =>
        {
            var result = await importer.ImportAsync(key, ct);
            return result is null ? Results.NotFound() : Results.Ok(result);
        });

        app.MapPost("/api/premade-packs/undo", async (PremadePackUndoRequest body, PremadePackImportService importer, CancellationToken ct) =>
        {
            await importer.UndoAsync(body.AppliedCards, ct);
            return Results.Ok(new { ok = true });
        });

        app.MapGet("/api/decks/{id:int}/export", async (int id, string? format, DeckService decks, CancellationToken ct) =>
        {
            var contents = await decks.ExportAsync(id, format, ct);
            return contents is null
                ? Results.NotFound()
                : Results.Text(contents, "text/plain", System.Text.Encoding.UTF8);
        });

        app.MapGet("/api/decks/{id:int}/recommendations", async (
            int id, string legendCardId, CommunityRecommendationService recommendations, CancellationToken ct) =>
            Results.Ok(await recommendations.GetRecommendationsAsync(id, legendCardId, ct)));

        app.MapGet("/api/community-decks/status", async (CommunityDeckSyncService sync, CancellationToken ct) =>
            Results.Ok(await sync.GetStatusAsync(ct)));

        app.MapPost("/api/community-decks/sync", async (
            CommunitySyncRequest? body, CommunityDeckSyncService sync, CancellationToken ct) =>
        {
            try
            {
                return Results.Ok(await sync.SyncAsync(body?.Days ?? 30, ct));
            }
            catch (Exception ex)
            {
                return Results.Problem(ex.Message, statusCode: 502);
            }
        });

        app.MapGet("/api/rules/search", async (
            string q, bool? currentOnly, int? limit, RulesService rules, CancellationToken ct) =>
            Results.Ok(await rules.SearchAsync(q, currentOnly ?? true, limit ?? 30, ct)));

        app.MapGet("/api/rules/status", async (RulesSyncService sync, CancellationToken ct) =>
            Results.Ok(await sync.GetStatusAsync(ct)));

        app.MapPost("/api/rules/sync", async (RulesSyncService sync, CancellationToken ct) =>
        {
            try
            {
                return Results.Ok(await sync.SyncAsync(ct));
            }
            catch (Exception ex)
            {
                return Results.Problem(ex.Message, statusCode: 502);
            }
        });

        app.MapGet("/api/rules/keywords", async (RulesService rules, CancellationToken ct) =>
            Results.Ok(await rules.GetKeywordsAsync(ct)));

        app.MapGet("/api/rules/keywords/{id:int}", async (int id, RulesService rules, CancellationToken ct) =>
        {
            var detail = await rules.GetKeywordDetailAsync(id, ct);
            return detail is null ? Results.NotFound() : Results.Ok(detail);
        });

        app.MapGet("/api/rules/documents", async (RulesService rules, CancellationToken ct) =>
            Results.Ok(await rules.GetDocumentsAsync(ct)));

        app.MapGet("/api/rules/documents/{id:int}", async (int id, RulesService rules, CancellationToken ct) =>
        {
            var detail = await rules.GetDocumentDetailAsync(id, ct);
            return detail is null ? Results.NotFound() : Results.Ok(detail);
        });

        app.MapGet("/api/rules/errata", async (RulesService rules, CancellationToken ct) =>
            Results.Ok(await rules.GetErrataAsync(ct)));

        app.MapGet("/api/rules/errata/cards/{cardId}", async (string cardId, RulesService rules, CancellationToken ct) =>
            Results.Ok(await rules.GetErrataForCardAsync(cardId, ct)));

        app.MapGet("/api/rules/legality", async (RulesService rules, CancellationToken ct) =>
            Results.Ok(await rules.GetLegalityAsync(ct)));

        app.MapGet("/api/rules/legality/cards/{cardId}", async (string cardId, RulesService rules, CancellationToken ct) =>
            Results.Ok(await rules.GetLegalityForCardAsync(cardId, ct)));

        app.MapGet("/api/rules/cards/{cardId}", async (string cardId, RulesService rules, CancellationToken ct) =>
            Results.Ok(await rules.GetCardRulesAsync(cardId, ct)));

        app.MapPost("/api/rules/ask", async (AskRuleQuestionRequest body, RulesAnswerService answers, CancellationToken ct) =>
        {
            if (string.IsNullOrWhiteSpace(body.Question))
                return Results.BadRequest(new { error = "Ask a question." });
            return Results.Ok(await answers.AskAsync(body.Question, body.CardId, ct));
        });

        app.MapPost("/api/rules/analyze-question", async (AskRuleQuestionRequest body, RulesQuestionService questions, CancellationToken ct) =>
        {
            if (string.IsNullOrWhiteSpace(body.Question))
                return Results.BadRequest(new { error = "Ask a question." });
            return Results.Ok(await questions.AnalyzeAsync(body.Question, body.CardId, ct));
        });

        app.MapGet("/api/rules/local-ai/status", (RulesLocalAiSettingsService settings, LocalAiModelService modelService) =>
        {
            var status = modelService.GetStatus();
            return Results.Ok(new RulesLocalAiStatusDto(settings.IsEnabled(), status.Present, status.FileName, status.Bytes));
        });

        app.MapGet("/api/rules/local-ai/model-progress", (LocalAiModelService modelService) =>
            Results.Ok(modelService.GetStatus()));

        app.MapPost("/api/rules/local-ai/download-model", (LocalAiModelService modelService, ILogger<LocalAiModelService> logger) =>
        {
            // Detached, same reasoning as the app self-update: the download can take a while, so
            // this request returns immediately and the client polls model-progress instead of
            // holding one connection open for the whole ~940MB transfer.
            _ = Task.Run(async () =>
            {
                try { await modelService.DownloadAsync(CancellationToken.None); }
                catch (Exception ex) { logger.LogError(ex, "Local AI model download failed"); }
            });
            return Results.Ok(new { started = true });
        });

        app.MapPost("/api/rules/local-ai/configure", (RulesLocalAiToggleRequest body, RulesLocalAiSettingsService settings) =>
        {
            settings.SetEnabled(body.Enabled);
            return Results.Ok(new { enabled = settings.IsEnabled() });
        });

        // Registered after the more specific /api/rules/* routes above — ASP.NET Core's endpoint
        // routing prefers literal segment matches ("search", "keywords", ...) over this
        // parameterized one regardless of registration order, but keeping it last mirrors that.
        app.MapGet("/api/rules/{id:int}", async (int id, RulesService rules, CancellationToken ct) =>
        {
            var detail = await rules.GetRuleDetailAsync(id, ct);
            return detail is null ? Results.NotFound() : Results.Ok(detail);
        });

        app.MapGet("/api/pricing/status", (PricingSettingsService settings) => Results.Ok(settings.GetStatus()));

        app.MapPost("/api/pricing/configure", (PricingKeyRequest body, PricingSettingsService settings) =>
        {
            settings.SaveApiKey(body.ApiKey);
            return Results.Ok(settings.GetStatus());
        });

        app.MapDelete("/api/pricing/configure", (PricingSettingsService settings) =>
        {
            settings.ClearStoredApiKey();
            return Results.Ok(settings.GetStatus());
        });

        app.MapGet("/api/topdeck/status", (TopDeckSettingsService settings) => Results.Ok(settings.GetStatus()));

        app.MapPost("/api/topdeck/configure", (TopDeckKeyRequest body, TopDeckSettingsService settings) =>
        {
            settings.SaveApiKey(body.ApiKey);
            return Results.Ok(settings.GetStatus());
        });

        app.MapDelete("/api/topdeck/configure", (TopDeckSettingsService settings) =>
        {
            settings.ClearStoredApiKey();
            return Results.Ok(settings.GetStatus());
        });

        app.MapGet("/api/pricing/latest", async (PriceSyncService prices, CancellationToken ct) =>
            Results.Ok(await prices.GetLatestAsync(ct)));

        app.MapGet("/api/pricing/history/{cardId}", async (string cardId, int? days, PriceSyncService prices, CancellationToken ct) =>
            Results.Ok(await prices.GetHistoryAsync(cardId, days ?? 30, ct)));

        app.MapGet("/api/pricing/queue", async (PriceSyncService prices, CancellationToken ct) =>
            Results.Ok(await prices.GetQueueAsync(ct)));

        app.MapPost("/api/pricing/queue/{cardId}", async (
            string cardId, PriceQueueRequest body, PriceSyncService prices, CancellationToken ct) =>
        {
            try
            {
                var updated = await prices.SetQueuedAsync(cardId, body.Queued, ct);
                return updated is null ? Results.NotFound() : Results.Ok(updated);
            }
            catch (InvalidOperationException ex)
            {
                return Results.BadRequest(new { error = ex.Message });
            }
        });

        app.MapDelete("/api/pricing/queue", async (PriceSyncService prices, CancellationToken ct) =>
            Results.Ok(new { removed = await prices.ClearQueueAsync(ct) }));

        app.MapPost("/api/pricing/queue/check", async (PriceSyncService prices, CancellationToken ct) =>
        {
            try
            {
                return Results.Ok(await prices.SyncNextQueueBatchAsync(ct));
            }
            catch (InvalidOperationException ex)
            {
                return Results.BadRequest(new { error = ex.Message });
            }
        });

        app.MapPost("/api/pricing/refresh", async (PriceRefreshRequest body, PriceSyncService prices, CancellationToken ct) =>
            Results.Ok(await prices.SyncTrackedAsync(body.IncludeAllCards, ct)));

        app.MapGet("/api/cards/lookup", async (string? setId, int? number, string? code, CardCacheService cache, CancellationToken ct) =>
        {
            // "code" (e.g. "R01", "007A") is the printed collector code — the only way to tell
            // apart cards that share a bare CollectorNumber (see CardEntity.CollectorCode). Falls
            // back to the plain numeric lookup when the caller doesn't have a code to give.
            var matches = !string.IsNullOrWhiteSpace(code)
                ? await cache.FindByCodeAsync(setId, code, ct)
                : await cache.FindAllByNumberAsync(setId, number ?? 0, ct);
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
            var cardIdOnly = form["cardIdOnly"].ToString() == "true";
            await using var stream = file.OpenReadStream();
            var result = await scanner.ScanAsync(
                stream,
                string.IsNullOrWhiteSpace(setHint) ? null : setHint,
                fast,
                cardIdOnly,
                ct);
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
public record PricingKeyRequest(string ApiKey);
public record TopDeckKeyRequest(string ApiKey);
public record CommunitySyncRequest(int? Days);
public record AskRuleQuestionRequest(string Question, string? CardId);
public record RulesLocalAiToggleRequest(bool Enabled);
public record PriceRefreshRequest(bool IncludeAllCards);
public record PriceQueueRequest(bool Queued);
