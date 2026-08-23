using System.Net.Http;
using RiftBoundTracker.App.Data;

namespace RiftBoundTracker.App.Services;

/// <summary>
/// Riftbound's token cards (Recruit, Brush, Mech, etc.) are real printed cards, but riftcodex.com
/// — the only data source CardCacheService syncs from — only carries the handful that happen to
/// share their base set's normal numeric collector numbering (the three Recruits and Sprite in
/// Origins, Gold in Spiritforged). The rest use special "T01"-style collector codes riftcodex's
/// API doesn't expose at all (confirmed by querying it directly), so they're seeded here instead.
///
/// Images come from static.dotgg.gg (riftbound.gg's own card image CDN) — unlike riftbound.gg's
/// own pages or the League wiki, this asset host has no bot-detection wall, so a plain HttpClient
/// reaches it directly with no browser-relay workaround needed.
///
/// Safe to run on every startup: CardCacheService's own sync only ever upserts by Id and never
/// deletes rows missing from a fresh API response, so these entries are never at risk from a
/// regular set sync. Re-running this is a no-op for a card that already has an image; a card
/// that's missing one (or was seeded before dotgg was known to be reachable) gets retried, so a
/// transient fetch failure self-heals on the next launch instead of leaving a blank image forever.
/// </summary>
public class TokenCardCatalogService(AppDbContext db, IHttpClientFactory httpClientFactory, IWebHostEnvironment env, ILogger<TokenCardCatalogService> logger)
{
    private sealed record TokenDef(
        string Id, string Name, string SetId, string SetLabel, string CollectorCode,
        string Type, int? Might, string Text);

    // Rules text is verbatim from Rule 187 (the compiled rules-engine's own canonical core_rules
    // data) — not paraphrased, so it matches the actual printed card text. Domain "Colorless"
    // matches the convention the four already-synced tokens (Recruit x3, Sprite) already use for
    // "domainless" rather than introducing a second value the UI's domain filter doesn't know.
    //
    // "ven-t06" was seeded in an earlier release as a guess at Tentacle's code, sourced from the
    // League wiki — dotgg.gg (confirmed directly reachable and far more likely to be accurate)
    // 404s on VEN-T06, while VEN-T03 is a real, fetchable card. Corrected here.
    private static readonly TokenDef[] Tokens =
    [
        new("sfd-t01", "Mech", "SFD", "Spiritforged", "T01", "Unit", 3,
            "A 3 Might Mech token is a domainless unit token with 3 Might and the Mech tag."),
        new("sfd-t02", "Sand Soldier", "SFD", "Spiritforged", "T02", "Unit", 2,
            "A 2 Might Sand Soldier token is a domainless unit token with 2 Might and the Shurima tag."),
        new("unl-t01", "Baron Pit", "UNL", "Unleashed", "T01", "Battlefield", null,
            "The Baron Pit battlefield token is a domainless battlefield token with \"Units can move here from anywhere.\""),
        new("unl-t02", "Bird", "UNL", "Unleashed", "T02", "Unit", 1,
            "A 1 Might Bird token is a domainless unit token with 1 Might, the Bird tag, and the Deflect keyword."),
        new("unl-t03", "Brush", "UNL", "Unleashed", "T03", "Battlefield", null,
            "A Brush battlefield token is a domainless battlefield token with \"Bird, Cat, Dog, Poro, and Ivern units here have +1 Might\" and \"When you score here, you may replace this with the battlefield it replaced.\""),
        new("unl-t04", "Buff", "UNL", "Unleashed", "T04", "Marker", null,
            "A reference card used alongside a token to track additional Might it has been granted."),
        new("unl-t05", "Gold", "UNL", "Unleashed", "T05", "Gear", null,
            "A Gold gear token is a domainless gear token with \"[Reaction][Kill this], [Energy]: Add [1].\""),
        new("unl-t06", "Reflection", "UNL", "Unleashed", "T06", "Unit", 0,
            "A 0 Might Reflection token is a domainless unit token with 0 Might."),
        new("unl-t08", "XP Tracker", "UNL", "Unleashed", "T08", "Marker", null,
            "A reference card used to track a Legend's experience toward leveling up."),
        new("ven-t01", "Empowered", "VEN", "Vendetta", "T01", "Marker", null,
            "A reference card used to mark a Game Object as Empowered."),
        new("ven-t03", "Tentacle", "VEN", "Vendetta", "T03", "Unit", 1,
            "A 1 Might Tentacle token is a domainless unit token with 1 Might and the Bilgewater tag."),
        new("ven-t05", "Shadow Clone", "VEN", "Vendetta", "T05", "Unit", 0,
            "A 0 Might Shadow Clone token is a domainless unit token with 0 Might and \"[Reaction] When I attack, you may banish a unit from your trash. If you do, give me [Assault 4] this turn.\""),
    ];

    public async Task EnsureSeededAsync(CancellationToken ct = default)
    {
        var stale = await db.Cards.FindAsync(["ven-t06"], ct);
        if (stale is not null) db.Cards.Remove(stale);

        foreach (var def in Tokens)
        {
            var existing = await db.Cards.FindAsync([def.Id], ct);
            if (existing is not null)
            {
                // Always re-attempt rather than only filling a blank: an earlier release seeded
                // these from the League wiki (lower quality, 3 of 12 had no image at all) — this
                // upgrades every existing row to the better dotgg source too, not just the gaps.
                var refreshed = await TryFetchImageAsync(def, ct);
                if (refreshed is not null && refreshed != existing.LocalImagePath)
                {
                    existing.LocalImagePath = refreshed;
                    existing.ImageUrl = DotggImageUrl(def);
                    existing.UpdatedAt = DateTimeOffset.UtcNow;
                    logger.LogInformation("Refreshed image for token card {Id}", def.Id);
                }
                continue;
            }

            var localImagePath = await TryFetchImageAsync(def, ct);
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
                ImageUrl = DotggImageUrl(def),
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

    private static string DotggImageUrl(TokenDef def) =>
        $"https://static.dotgg.gg/riftbound/cards/{def.SetId}-{def.CollectorCode}.webp";

    private static int ExtractNumber(string code)
    {
        var digits = new string(code.Where(char.IsDigit).ToArray());
        return int.TryParse(digits, out var n) ? n : 0;
    }

    private async Task<string?> TryFetchImageAsync(TokenDef def, CancellationToken ct)
    {
        try
        {
            var http = httpClientFactory.CreateClient("card-images");
            var bytes = await http.GetByteArrayAsync(DotggImageUrl(def), ct);
            if (bytes.Length < 512) return null;

            var imagesDir = Path.Combine(env.ContentRootPath, "App_Data", "images");
            Directory.CreateDirectory(imagesDir);
            var fileName = $"{def.Id}.webp";
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
