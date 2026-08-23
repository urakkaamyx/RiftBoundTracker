using System.Net.Http;
using RiftBoundTracker.App.Data;

namespace RiftBoundTracker.App.Services;

/// <summary>
/// Same gap as the orphan token cards (TokenCardCatalogService): riftcodex.com's API has no data
/// at all for Spiritforged's or Unleashed's own Rune reprints, confirmed by querying it directly —
/// only Origins, Vendetta, and the Organized Play promo set's runes came through the normal sync.
/// Unlike orphan tokens, though, these ARE real cards with real set data (a genuine SFD/UNL
/// printing, not a gameplay-only marker) — seeded as ordinary cards (IsSyntheticToken stays
/// false), so they count toward their set's totals and completion % like any other card.
///
/// Images come from static.dotgg.gg the same way the token images do — a plain HttpClient reaches
/// it directly, no bot-detection wall.
/// </summary>
public class RuneCardCatalogService(AppDbContext db, IHttpClientFactory httpClientFactory, IWebHostEnvironment env, ILogger<RuneCardCatalogService> logger)
{
    private sealed record RuneDef(string Id, string Name, string SetId, string SetLabel, string CollectorCode, string Domain);

    // R01-R06 = Fury/Calm/Mind/Body/Chaos/Order, matching Vendetta's own already-synced rune
    // numbering (VEN-R01..R06) — the same six domains reprinted the same way in every set that
    // includes its own rune reprints.
    private static readonly (string Code, string Domain)[] Domains =
    [
        ("R01", "Fury"), ("R02", "Calm"), ("R03", "Mind"), ("R04", "Body"), ("R05", "Chaos"), ("R06", "Order"),
    ];

    // Confirmed directly with the user: "a" = Alternate Art (matches the existing suffix Origins'
    // own rune reprints already use), "b" = Promo.
    private static readonly (string Suffix, string? NameSuffix)[] Variants = [("", null), ("a", "Alternate Art"), ("b", "Promo")];

    private static readonly (string SetId, string SetLabel)[] Sets = [("SFD", "Spiritforged"), ("UNL", "Unleashed")];

    private static readonly RuneDef[] Runes = BuildRunes();

    private static RuneDef[] BuildRunes()
    {
        var list = new List<RuneDef>();
        foreach (var (setId, setLabel) in Sets)
            foreach (var (code, domain) in Domains)
                foreach (var (suffix, nameSuffix) in Variants)
                {
                    var collectorCode = code + suffix;
                    var name = nameSuffix is null ? $"{domain} Rune" : $"{domain} Rune ({nameSuffix})";
                    list.Add(new RuneDef($"{setId.ToLowerInvariant()}-{collectorCode.ToLowerInvariant()}", name, setId, setLabel, collectorCode, domain));
                }
        return list.ToArray();
    }

    public async Task EnsureSeededAsync(CancellationToken ct = default)
    {
        foreach (var def in Runes)
        {
            var existing = await db.Cards.FindAsync([def.Id], ct);
            if (existing is not null)
            {
                var refreshed = await TryFetchImageAsync(def, ct);
                if (refreshed is not null && refreshed != existing.LocalImagePath)
                {
                    existing.LocalImagePath = refreshed;
                    existing.ImageUrl = DotggImageUrl(def);
                    existing.UpdatedAt = DateTimeOffset.UtcNow;
                    logger.LogInformation("Refreshed image for rune card {Id}", def.Id);
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
                Type = "Rune",
                Supertype = "Basic",
                IsSyntheticToken = false,
                Rarity = "Common",
                DomainsCsv = def.Domain,
                TextRich = "<p>[NO TEXT]</p>",
                TextPlain = "[NO TEXT]",
                ImageUrl = DotggImageUrl(def),
                LocalImagePath = localImagePath,
                Orientation = "portrait",
                OwnedCount = 0,
                CachedAt = now,
                UpdatedAt = now,
            });
            logger.LogInformation("Seeded rune card {Id} ({Name})", def.Id, def.Name);
        }
        await db.SaveChangesAsync(ct);
    }

    private static string DotggImageUrl(RuneDef def) =>
        $"https://static.dotgg.gg/riftbound/cards/{def.SetId}-{def.CollectorCode}.webp";

    private static int ExtractNumber(string code)
    {
        var digits = new string(code.Where(char.IsDigit).ToArray());
        return int.TryParse(digits, out var n) ? n : 0;
    }

    private async Task<string?> TryFetchImageAsync(RuneDef def, CancellationToken ct)
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
            logger.LogWarning(ex, "Could not fetch rune image for {Id}", def.Id);
            return null;
        }
    }
}
