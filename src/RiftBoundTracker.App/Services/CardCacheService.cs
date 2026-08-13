using System.Net.Http;
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

public class CardCacheService(
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
            entity.SetId = card.Set?.SetId ?? setId;
            entity.SetLabel = card.Set?.Label ?? "";
            entity.Type = card.Classification?.Type ?? "";
            entity.Supertype = card.Classification?.Supertype;
            entity.Rarity = card.Classification?.Rarity ?? "";
            entity.DomainsCsv = string.Join(',', card.Classification?.Domain ?? []);
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
            var search = q.Search.Trim();
            query = query.Where(c => c.Name.Contains(search) || c.Id.Contains(search)
                || c.CollectorNumber.ToString().Contains(search));
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

    public Task<CardEntity?> FindByNumberAsync(string? setId, int number, CancellationToken ct = default)
    {
        var query = db.Cards.Where(c => c.CollectorNumber == number);
        if (!string.IsNullOrWhiteSpace(setId))
            query = query.Where(c => c.SetId == setId.ToUpper());
        return query.FirstOrDefaultAsync(ct);
    }

    public Task<List<CardEntity>> FindAllByNumberAsync(int number, CancellationToken ct = default)
        => db.Cards.Where(c => c.CollectorNumber == number).ToListAsync(ct);

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
