using RiftBoundTracker.App.Data;

namespace RiftBoundTracker.App.Services;

/// <summary>
/// Riftbound's token cards (Recruit, Brush, Mech, etc.) are real printed cards, but riftcodex.com
/// — the only data source CardCacheService syncs from — only carries the handful that happen to
/// share their base set's normal numeric collector numbering (the three Recruits and Sprite in
/// Origins, Gold in Spiritforged). The rest use special "T01"-style collector codes riftcodex's
/// API doesn't expose at all (confirmed by querying it directly), so they're seeded here instead.
///
/// Safe to run on every startup: CardCacheService's own sync only ever upserts by Id and never
/// deletes rows missing from a fresh API response, so these entries are never at risk from a
/// regular set sync, and re-running this seed is a no-op once every Id already exists.
/// </summary>
public class TokenCardCatalogService(AppDbContext db, BrowserRelayClient relay, IWebHostEnvironment env, ILogger<TokenCardCatalogService> logger)
{
    private sealed record TokenDef(
        string Id, string Name, string SetId, string SetLabel, string CollectorCode,
        string Type, int? Might, string Text, string? WikiImageFile);

    // Rules text is verbatim from Rule 187 (the compiled rules-engine's own canonical core_rules
    // data) — not paraphrased, so it matches the actual printed card text. Domain "Colorless"
    // matches the convention the four already-synced tokens (Recruit x3, Sprite) already use for
    // "domainless" rather than introducing a second value the UI's domain filter doesn't know.
    private static readonly TokenDef[] Tokens =
    [
        new("sfd-t01", "Mech", "SFD", "Spiritforged", "T01", "Unit", 3,
            "A 3 Might Mech token is a domainless unit token with 3 Might and the Mech tag.", "RB_card_SFD-T01.png"),
        new("sfd-t02", "Sand Soldier", "SFD", "Spiritforged", "T02", "Unit", 2,
            "A 2 Might Sand Soldier token is a domainless unit token with 2 Might and the Shurima tag.", "RB_card_SFD-T02.png"),
        new("unl-t01", "Baron Pit", "UNL", "Unleashed", "T01", "Battlefield", null,
            "The Baron Pit battlefield token is a domainless battlefield token with \"Units can move here from anywhere.\"", "RB_card_UNL-T01.png"),
        new("unl-t02", "Bird", "UNL", "Unleashed", "T02", "Unit", 1,
            "A 1 Might Bird token is a domainless unit token with 1 Might, the Bird tag, and the Deflect keyword.", "RB_card_UNL-T02.png"),
        new("unl-t03", "Brush", "UNL", "Unleashed", "T03", "Battlefield", null,
            "A Brush battlefield token is a domainless battlefield token with \"Bird, Cat, Dog, Poro, and Ivern units here have +1 Might\" and \"When you score here, you may replace this with the battlefield it replaced.\"", "RB_card_UNL-T03.png"),
        new("unl-t04", "Buff", "UNL", "Unleashed", "T04", "Marker", null,
            "A reference card used alongside a token to track additional Might it has been granted.", "RB_card_UNL-T04.png"),
        new("unl-t05", "Gold", "UNL", "Unleashed", "T05", "Gear", null,
            "A Gold gear token is a domainless gear token with \"[Reaction][Kill this], [Energy]: Add [1].\"", "RB_card_UNL-T05.png"),
        new("unl-t06", "Reflection", "UNL", "Unleashed", "T06", "Unit", 0,
            "A 0 Might Reflection token is a domainless unit token with 0 Might.", "RB_card_UNL-T06.png"),
        new("unl-t08", "XP Tracker", "UNL", "Unleashed", "T08", "Marker", null,
            "A reference card used to track a Legend's experience toward leveling up.", "RB_card_UNL-T08.png"),
        new("ven-t01", "Empowered", "VEN", "Vendetta", "T01", "Marker", null,
            "A reference card used to mark a Game Object as Empowered.", null),
        new("ven-t05", "Shadow Clone", "VEN", "Vendetta", "T05", "Unit", 0,
            "A 0 Might Shadow Clone token is a domainless unit token with 0 Might and \"[Reaction] When I attack, you may banish a unit from your trash. If you do, give me [Assault 4] this turn.\"", null),
        new("ven-t06", "Tentacle", "VEN", "Vendetta", "T06", "Unit", 1,
            "A 1 Might Tentacle token is a domainless unit token with 1 Might and the Bilgewater tag.", null),
    ];

    public async Task EnsureSeededAsync(CancellationToken ct = default)
    {
        foreach (var def in Tokens)
        {
            if (await db.Cards.FindAsync([def.Id], ct) is not null) continue;

            var localImagePath = def.WikiImageFile is null ? null : await TryFetchImageAsync(def, ct);
            var now = DateTimeOffset.UtcNow;
            db.Cards.Add(new CardEntity
            {
                Id = def.Id,
                Name = def.Name,
                CollectorNumber = ExtractNumber(def.CollectorCode),
                CollectorCode = def.CollectorCode,
                SetId = def.SetId,
                SetLabel = def.SetLabel,
                Type = def.Type,
                Supertype = "Token",
                Rarity = "Common",
                DomainsCsv = "Colorless",
                TextRich = $"<p>{def.Text}</p>",
                TextPlain = def.Text,
                ImageUrl = def.WikiImageFile is null ? "" : $"https://wiki.leagueoflegends.com/en-us/images/{def.WikiImageFile}",
                LocalImagePath = localImagePath,
                Might = def.Might,
                OwnedCount = 0,
                CachedAt = now,
                UpdatedAt = now,
            });
            logger.LogInformation("Seeded token card {Id} ({Name})", def.Id, def.Name);
        }
        await db.SaveChangesAsync(ct);
    }

    private static int ExtractNumber(string code)
    {
        var digits = new string(code.Where(char.IsDigit).ToArray());
        return int.TryParse(digits, out var n) ? n : 0;
    }

    // Best-effort: the wiki's own page is behind bot detection a plain HttpClient can't pass, but
    // its image files aren't protected the same way once fetched through a real browser engine —
    // BrowserRelayClient is the same off-screen WebView2 fallback CardCacheService already uses for
    // riftcodex.com. A failed fetch just leaves the card without a cached local image (it still
    // falls back to the direct wiki ImageUrl in the browser) rather than blocking the seed.
    private async Task<string?> TryFetchImageAsync(TokenDef def, CancellationToken ct)
    {
        try
        {
            var bytes = await relay.FetchImageBytesAsync($"https://wiki.leagueoflegends.com/en-us/images/{def.WikiImageFile}", ct);
            if (bytes is null || bytes.Length < 512) return null;

            var imagesDir = Path.Combine(env.ContentRootPath, "App_Data", "images");
            Directory.CreateDirectory(imagesDir);
            var fileName = $"{def.Id}.png";
            await File.WriteAllBytesAsync(Path.Combine(imagesDir, fileName), bytes, ct);
            return $"/card-images/{fileName}";
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Could not fetch token image for {Id}", def.Id);
            return null;
        }
    }
}
