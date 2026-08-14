using Microsoft.EntityFrameworkCore;
using RiftBoundTracker.App.Data;

namespace RiftBoundTracker.App.Services;

public record PriceSyncResult(int RequestedCards, int PricedCards, int SnapshotsSaved, DateTimeOffset CompletedAt);
public record LatestPriceDto(
    string CardId, string Provider, string VariantId, string Condition, string Printing,
    string Currency, double MarketPrice, double? Change24Hours, DateTimeOffset CapturedAt,
    DateTimeOffset? SourceUpdatedAt);

public sealed class PriceSyncService(AppDbContext db, IEnumerable<IPriceProvider> providers)
{
    public async Task<PriceSyncResult> SyncTrackedAsync(bool includeAllCards, CancellationToken ct = default)
    {
        var provider = providers.FirstOrDefault(p => p.IsConfigured)
            ?? throw new InvalidOperationException("Pricing is not configured. Add a JustTCG API key in Settings.");

        var trackedDeckCardIds = db.DeckCards.Select(dc => dc.CardId);
        var query = db.Cards.Where(c => c.TcgplayerId != null && c.TcgplayerId != "");
        if (!includeAllCards)
        {
            query = query.Where(c => c.OwnedCount > 0 || c.IsFavorite || c.BinderCount > 0
                                     || trackedDeckCardIds.Contains(c.Id));
        }

        var cards = await query.OrderBy(c => c.SetId).ThenBy(c => c.CollectorNumber).ToListAsync(ct);
        var saved = 0;
        var priced = 0;

        var batches = cards.Chunk(JustTcgPriceProvider.FreeTierBatchSize).ToList();
        for (var batchIndex = 0; batchIndex < batches.Count; batchIndex++)
        {
            var batch = batches[batchIndex];
            var quotes = await provider.GetPricesAsync(batch, ct);
            priced += quotes.Count;
            var now = DateTimeOffset.UtcNow;
            foreach (var quote in quotes)
            {
                db.PriceSnapshots.Add(new PriceSnapshotEntity
                {
                    CardId = quote.CardId,
                    Provider = quote.Provider,
                    VariantId = quote.VariantId,
                    Condition = quote.Condition,
                    Printing = quote.Printing,
                    Currency = quote.Currency,
                    MarketPrice = quote.MarketPrice,
                    Change24Hours = quote.Change24Hours,
                    CapturedAt = now,
                    SourceUpdatedAt = quote.SourceUpdatedAt,
                });
                saved++;
            }
            await db.SaveChangesAsync(ct);

            // The documented free tier allows 10 requests/minute. Keep every multi-batch refresh
            // inside that boundary, including an unusually large tracked-card collection.
            if (batchIndex < batches.Count - 1)
                await Task.Delay(TimeSpan.FromSeconds(6.25), ct);
        }

        return new PriceSyncResult(cards.Count, priced, saved, DateTimeOffset.UtcNow);
    }

    public async Task<Dictionary<string, LatestPriceDto>> GetLatestAsync(CancellationToken ct = default)
    {
        var rows = await db.PriceSnapshots
            .AsNoTracking()
            .ToListAsync(ct);
        return rows.OrderByDescending(p => p.CapturedAt).DistinctBy(p => p.CardId).ToDictionary(
            p => p.CardId,
            p => new LatestPriceDto(
                p.CardId, p.Provider, p.VariantId, p.Condition, p.Printing, p.Currency,
                p.MarketPrice, p.Change24Hours, p.CapturedAt, p.SourceUpdatedAt));
    }

    public async Task<List<LatestPriceDto>> GetHistoryAsync(string cardId, int days, CancellationToken ct = default)
    {
        var since = DateTimeOffset.UtcNow.AddDays(-Math.Clamp(days, 1, 365));
        var rows = await db.PriceSnapshots
            .AsNoTracking()
            .Where(p => p.CardId == cardId)
            .ToListAsync(ct);
        return rows
            .Where(p => p.CapturedAt >= since)
            .OrderBy(p => p.CapturedAt)
            .Select(p => new LatestPriceDto(
                p.CardId, p.Provider, p.VariantId, p.Condition, p.Printing, p.Currency,
                p.MarketPrice, p.Change24Hours, p.CapturedAt, p.SourceUpdatedAt))
            .ToList();
    }
}
