using System.Net.Http;
using System.Text.RegularExpressions;
using Microsoft.EntityFrameworkCore;
using RiftBoundTracker.App.Data;

namespace RiftBoundTracker.App.Services;

public record CardQuery(
    string? Search = null,
    string? SetId = null,
    string? Type = null,
    string? Rarity = null,
    string? Domain = null,
    string? Owned = null, // "all" | "owned" | "missing"
    string Sort = "num-asc"
);

public record SyncProgress(string SetId, int Synced, int Total);

public partial class CardCacheService(
    AppDbContext db,
    RiftcodexClient riftcodex,
    ImageHashService hasher,
    IHttpClientFactory httpClientFactory,
    IWebHostEnvironment env,
    ILogger<CardCacheService> logger)
{
    private string ImagesRoot => Path.Combine(env.ContentRootPath, "App_Data", "images");

    public async Task<int> SyncSetAsync(string setId, IProgress<SyncProgress>? progress, CancellationToken ct = default)
    {
        setId = setId.Trim().ToUpperInvariant();
        Directory.CreateDirectory(ImagesRoot);
        var imgClient = httpClientFactory.CreateClient("card-images");

        var seen = new HashSet<string>();
        var synced = 0;
        var total = 0;

        await foreach (var card in riftcodex.GetAllForSetAsync(setId, ct: ct))
        {
            total++;
            if (string.IsNullOrEmpty(card.RiftboundId) || !seen.Add(card.RiftboundId))
                continue; // API returns duplicate variant rows per riftbound_id; keep the first (most complete comes first in practice)

            var existing = await db.Cards.FindAsync([card.RiftboundId], ct);
            var entity = existing ?? new CardEntity { Id = card.RiftboundId };

            entity.Name = card.Name;
            entity.CollectorNumber = card.CollectorNumber;
            entity.CollectorCode = ExtractCollectorCode(card.RiftboundId);
            entity.SetId = card.Set?.SetId ?? setId;
            entity.SetLabel = card.Set?.Label ?? "";
            entity.Type = card.Classification?.Type ?? "";
            entity.Supertype = card.Classification?.Supertype;
            entity.Rarity = card.Classification?.Rarity ?? "";
            entity.DomainsCsv = string.Join(',', card.Classification?.Domain ?? []);
            entity.TextRich = card.Text?.Rich;
            entity.TextPlain = card.Text?.Plain;
            entity.Flavour = card.Text?.Flavour;
            entity.ImageUrl = card.Media?.ImageUrl ?? "";
            entity.Artist = card.Media?.Artist;
            entity.Orientation = card.Orientation;
            entity.TcgplayerId = card.TcgplayerId;
            entity.Energy = card.Attributes?.Energy;
            entity.Might = card.Attributes?.Might;
            entity.Power = card.Attributes?.Power;
            entity.CachedAt = DateTimeOffset.UtcNow;
            if (existing is null)
            {
                entity.OwnedCount = 0;
                entity.UpdatedAt = DateTimeOffset.UtcNow;
                db.Cards.Add(entity);
            }

            await DownloadAndHashImageAsync(entity, imgClient, ct);

            synced++;
            progress?.Report(new SyncProgress(setId, synced, total));
        }

        await db.SaveChangesAsync(ct);
        return synced;
    }

    private async Task DownloadAndHashImageAsync(CardEntity entity, HttpClient imgClient, CancellationToken ct)
    {
        if (string.IsNullOrEmpty(entity.ImageUrl))
            return;

        // Some riftbound_ids contain characters that aren't valid in a Windows filename (e.g. a
        // trailing "*" marking a foil/variant print) — sanitize before using the id as a filename.
        var fileName = $"{SanitizeFileName(entity.Id)}.png";
        var localPath = Path.Combine(ImagesRoot, fileName);

        if (!File.Exists(localPath))
        {
            try
            {
                var bytes = await imgClient.GetByteArrayAsync(entity.ImageUrl, ct);
                await File.WriteAllBytesAsync(localPath, bytes, ct);
            }
            catch (Exception ex)
            {
                logger.LogWarning(ex, "Failed to download image for {CardId}", entity.Id);
                return;
            }
        }

        entity.LocalImagePath = $"/card-images/{fileName}";

        if (entity.ImageHash is null)
        {
            await using var fs = File.OpenRead(localPath);
            entity.ImageHash = await hasher.ComputeDHashAsync(fs, ct);
        }
    }

    private static string SanitizeFileName(string id)
    {
        var invalid = Path.GetInvalidFileNameChars();
        return string.Concat(id.Select(c => invalid.Contains(c) ? '_' : c));
    }

    // riftbound_id is "{setId}-{code}" or "{setId}-{code}-{something}" (e.g. "ven-001-166",
    // "ven-r01", "sfd-223*-221", "opp-007b-298") — the second hyphen-separated segment is
    // consistently the printed collector code across every id shape observed from the API.
    private static string ExtractCollectorCode(string riftboundId)
    {
        var parts = riftboundId.Split('-');
        return (parts.Length >= 2 ? parts[1] : riftboundId).ToUpperInvariant();
    }

    public Task<List<CardEntity>> QueryAsync(CardQuery q, CancellationToken ct = default)
    {
        var query = db.Cards.AsQueryable();

        if (!string.IsNullOrWhiteSpace(q.SetId))
            query = query.Where(c => c.SetId == q.SetId.ToUpper());
        if (!string.IsNullOrWhiteSpace(q.Type))
            query = query.Where(c => c.Type == q.Type);
        if (!string.IsNullOrWhiteSpace(q.Rarity))
            query = query.Where(c => c.Rarity == q.Rarity);
        if (!string.IsNullOrWhiteSpace(q.Domain))
            query = query.Where(c => c.DomainsCsv.Contains(q.Domain));
        if (!string.IsNullOrWhiteSpace(q.Search))
        {
            // SQLite translates string.Contains to instr(), which is case-sensitive. Normalize
            // both sides so searches such as "blade" still match a name beginning with "Blade".
            var search = q.Search.Trim().ToLowerInvariant();
            query = query.Where(c => c.Name.ToLower().Contains(search) || c.Id.ToLower().Contains(search)
                || c.CollectorNumber.ToString().Contains(search) || c.CollectorCode.ToLower().Contains(search));
        }
        if (q.Owned == "owned")
            query = query.Where(c => c.OwnedCount > 0);
        else if (q.Owned == "missing")
            query = query.Where(c => c.OwnedCount == 0);

        query = q.Sort switch
        {
            "num-desc" => query.OrderByDescending(c => c.CollectorNumber),
            "name-asc" => query.OrderBy(c => c.Name),
            "rarity" => query.OrderBy(c => c.Rarity).ThenBy(c => c.CollectorNumber),
            "domain" => query.OrderBy(c => c.DomainsCsv).ThenBy(c => c.CollectorNumber),
            "owned" => query.OrderByDescending(c => c.OwnedCount > 0).ThenBy(c => c.CollectorNumber),
            _ => query.OrderBy(c => c.CollectorNumber),
        };

        return query.ToListAsync(ct);
    }

    public async Task<CardEntity?> SetOwnedAsync(string cardId, int ownedCount, CancellationToken ct = default)
    {
        var card = await db.Cards.FindAsync([cardId], ct);
        if (card is null) return null;
        card.OwnedCount = Math.Max(0, ownedCount);
        card.BinderCount = Math.Min(card.BinderCount, card.OwnedCount);
        card.UpdatedAt = DateTimeOffset.UtcNow;
        await db.SaveChangesAsync(ct);
        return card;
    }

    public Task<List<CardEntity>> GetCardsWithHashesAsync(string? setId, CancellationToken ct = default)
    {
        var query = db.Cards.Where(c => c.ImageHash != null);
        if (!string.IsNullOrWhiteSpace(setId))
            query = query.Where(c => c.SetId == setId.ToUpper());
        return query.ToListAsync(ct);
    }

    public Task<List<CardEntity>> FindAllByNumberAsync(string? setId, int number, CancellationToken ct = default)
    {
        var query = db.Cards.Where(c => c.CollectorNumber == number);
        if (!string.IsNullOrWhiteSpace(setId))
            query = query.Where(c => c.SetId == setId.ToUpper());
        return query.ToListAsync(ct);
    }

    // Prefix allows up to 2 letters — most lettered codes are single-letter ("R01"), but some are
    // two ("SP1" for signature/promo cards).
    [GeneratedRegex(@"^(?<prefix>[A-Za-z]{0,2})(?<num>\d{1,3})(?<suffix>[A-Za-z])?$")]
    private static partial Regex CollectorCodePattern();

    // Decomposes a collector code into (letter prefix, numeric value, letter suffix) so codes can
    // be compared regardless of zero-padding — Riftcodex's own padding isn't even consistent across
    // numbering schemes ("R01" is 2 digits, "007A" is 3), so exact string equality isn't reliable.
    private static (string? Prefix, int? Number, string? Suffix) DecomposeCode(string code)
    {
        var m = CollectorCodePattern().Match(code.Trim());
        if (!m.Success) return (null, null, null);
        return (
            m.Groups["prefix"].Value.Length > 0 ? m.Groups["prefix"].Value.ToUpperInvariant() : null,
            int.Parse(m.Groups["num"].Value),
            m.Groups["suffix"].Success ? m.Groups["suffix"].Value.ToUpperInvariant() : null
        );
    }

    /// <summary>
    /// Looks up by the actual printed code (e.g. "R01", "007A", or a plain "45") rather than just
    /// the bare number — the only way to tell apart cards like VEN "001" and VEN "R01", which share
    /// CollectorNumber but are different physical cards. Falls back to <see cref="FindAllByNumberAsync"/>
    /// for the numeric part, then filters in memory since the prefix/suffix decomposition can't be
    /// translated into SQL.
    /// </summary>
    public async Task<List<CardEntity>> FindByCodeAsync(string? setId, string code, CancellationToken ct = default)
    {
        var (prefix, number, suffix) = DecomposeCode(code);
        if (number is null) return [];

        var candidates = await FindAllByNumberAsync(setId, number.Value, ct);
        return candidates.Where(c =>
        {
            var (cPrefix, cNumber, cSuffix) = DecomposeCode(c.CollectorCode);
            // A candidate whose own code doesn't decompose (unrecognized shape) must never be
            // treated as "no prefix/suffix" by default — that would make it match ANY plain query.
            return cNumber is not null && cPrefix == prefix && cSuffix == suffix;
        }).ToList();
    }

    /// <summary>
    /// Exact name match for decklist formats that give no set/collector code at all (e.g. a
    /// "RiftDecks" export — just "{qty} {name}" per line). An exact match against the full Name
    /// field naturally prefers the base print over a variant: a plain query like "Stacked Deck"
    /// only matches a card whose Name is literally that, never "Stacked Deck (Metal)". The rare
    /// case of two prints sharing an identical unsuffixed name (a handful of Legends do — an OPP
    /// promo and the OGN rare) falls back to the lowest set/collector number for a deterministic,
    /// reasonable pick — still a base print either way, just not a unique one.
    /// </summary>
    public async Task<List<CardEntity>> FindByNameAsync(string name, CancellationToken ct = default)
    {
        var trimmed = name.Trim();
        if (trimmed.Length == 0) return [];

        var direct = await QueryExactNameAsync(trimmed, ct);
        if (direct.Count > 0) return direct;

        // "Champion, Title" style names are inconsistent about whether the separator is a comma
        // or a dash — even our own catalog isn't consistent with itself card-to-card (confirmed:
        // "Kennen, Storm of Shuriken" but "Nocturne - Horrifying"), so a decklist export using
        // the other style than whatever this specific card happens to use would otherwise fail
        // to resolve. Retry once with the separator swapped before giving up.
        var swapped = SwapNameSeparator(trimmed);
        return swapped == trimmed ? [] : await QueryExactNameAsync(swapped, ct);
    }

    private async Task<List<CardEntity>> QueryExactNameAsync(string name, CancellationToken ct) =>
        await db.Cards
            .Where(c => c.Name.ToLower() == name.ToLower())
            .OrderBy(c => c.SetId).ThenBy(c => c.CollectorNumber)
            .ToListAsync(ct);

    private static string SwapNameSeparator(string name)
    {
        var commaIdx = name.IndexOf(", ", StringComparison.Ordinal);
        if (commaIdx > 0) return string.Concat(name.AsSpan(0, commaIdx), " - ", name.AsSpan(commaIdx + 2));
        var dashIdx = name.IndexOf(" - ", StringComparison.Ordinal);
        return dashIdx > 0 ? string.Concat(name.AsSpan(0, dashIdx), ", ", name.AsSpan(dashIdx + 3)) : name;
    }

    public record SetSummary(string SetId, string SetLabel, int Total, int Owned);

    public async Task<List<SetSummary>> GetSetsAsync(CancellationToken ct = default)
    {
        var rows = await db.Cards
            .Select(c => new { c.SetId, c.SetLabel, c.OwnedCount })
            .ToListAsync(ct);

        return rows
            .GroupBy(c => (c.SetId, c.SetLabel))
            .Select(g => new SetSummary(g.Key.SetId, g.Key.SetLabel, g.Count(), g.Count(c => c.OwnedCount > 0)))
            .OrderBy(s => s.SetId)
            .ToList();
    }

    public record Stats(int Total, int Owned, int TotalCopies);

    public async Task<Stats> GetStatsAsync(string? setId, CancellationToken ct = default)
    {
        var query = db.Cards.AsQueryable();
        if (!string.IsNullOrWhiteSpace(setId))
            query = query.Where(c => c.SetId == setId.ToUpper());
        var total = await query.CountAsync(ct);
        var owned = await query.CountAsync(c => c.OwnedCount > 0, ct);
        var copies = await query.SumAsync(c => c.OwnedCount, ct);
        return new Stats(total, owned, copies);
    }
}
