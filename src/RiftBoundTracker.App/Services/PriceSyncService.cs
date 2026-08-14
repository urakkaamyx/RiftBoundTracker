using Microsoft.EntityFrameworkCore;
using RiftBoundTracker.App.Data;

namespace RiftBoundTracker.App.Services;

public record PriceSyncResult(int RequestedCards, int PricedCards, int SnapshotsSaved, DateTimeOffset CompletedAt);
public record PriceQueueItemDto(CardEntity Card, DateTimeOffset QueuedAt);
public record PriceQueueDto(
    List<PriceQueueItemDto> Items, int BatchSize, bool Configured, string Provider);
public record PriceQueueUpdateDto(CardEntity Card, bool Queued, int QueueCount);
public record PriceQueueSyncResult(
    int RequestedCards, int PricedCards, int SnapshotsSaved, int RemainingQueued,
    DateTimeOffset CompletedAt);
public record LatestPriceDto(
    string CardId, string Provider, string VariantId, string Condition, string Printing,
    string Currency, double MarketPrice, double? Change24Hours, DateTimeOffset CapturedAt,
    DateTimeOffset? SourceUpdatedAt, double? Change7Days = null, string? SourceUrl = null);

public sealed class PriceSyncService(
    AppDbContext db,
    IEnumerable<IPriceProvider> providers,
    RiftboundGgPriceService riftboundGg,
    ILogger<PriceSyncService> logger)
{
    public async Task<PriceQueueDto> GetQueueAsync(CancellationToken ct = default)
    {
        var provider = providers.FirstOrDefault(p => p.IsConfigured);
        var rows = await db.PriceQueue
            .AsNoTracking()
            .Include(q => q.Card)
            .ToListAsync(ct);
        var items = rows
            .OrderBy(q => q.QueuedAt)
            .Select(q => new PriceQueueItemDto(q.Card, q.QueuedAt))
            .ToList();

        return new PriceQueueDto(
            items,
            JustTcgPriceProvider.FreeTierBatchSize,
            provider is not null,
            provider?.Name ?? "JustTCG");
    }

    public async Task<PriceQueueUpdateDto?> SetQueuedAsync(
        string cardId,
        bool queued,
        CancellationToken ct = default)
    {
        var card = await db.Cards.FindAsync([cardId], ct);
        if (card is null) return null;

        var existing = await db.PriceQueue.FindAsync([cardId], ct);
        if (queued && existing is null)
        {
            if (string.IsNullOrWhiteSpace(card.TcgplayerId))
                throw new InvalidOperationException("This card does not have a pricing ID and cannot be checked yet.");

            db.PriceQueue.Add(new PriceQueueEntity
            {
                CardId = cardId,
                QueuedAt = DateTimeOffset.UtcNow,
            });
        }
        else if (!queued && existing is not null)
        {
            db.PriceQueue.Remove(existing);
        }

        await db.SaveChangesAsync(ct);
        return new PriceQueueUpdateDto(card, queued, await db.PriceQueue.CountAsync(ct));
    }

    public async Task<int> ClearQueueAsync(CancellationToken ct = default)
    {
        var removed = await db.PriceQueue.ExecuteDeleteAsync(ct);
        return removed;
    }

    public async Task<PriceQueueSyncResult> SyncNextQueueBatchAsync(CancellationToken ct = default)
    {
        var provider = providers.FirstOrDefault(p => p.IsConfigured)
            ?? throw new InvalidOperationException("Pricing is not configured. Add a JustTCG API key in Settings.");

        var queueRows = await db.PriceQueue
            .Include(q => q.Card)
            .ToListAsync(ct);
        var queued = queueRows
            .OrderBy(q => q.QueuedAt)
            .Take(JustTcgPriceProvider.FreeTierBatchSize)
            .ToList();
        if (queued.Count == 0)
        {
            return new PriceQueueSyncResult(
                0, 0, 0, 0, DateTimeOffset.UtcNow);
        }

        var quotes = await provider.GetPricesAsync(queued.Select(q => q.Card).ToList(), ct);
        var now = DateTimeOffset.UtcNow;
        foreach (var quote in quotes)
        {
            db.PriceSnapshots.Add(ToSnapshot(quote, now));
        }

        db.PriceQueue.RemoveRange(queued);
        await db.SaveChangesAsync(ct);

        return new PriceQueueSyncResult(
            queued.Count,
            quotes.Count,
            quotes.Count,
            await db.PriceQueue.CountAsync(ct),
            now);
    }

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
                db.PriceSnapshots.Add(ToSnapshot(quote, now));
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
        var latest = rows.OrderByDescending(p => p.CapturedAt).DistinctBy(p => p.CardId).ToDictionary(
            p => p.CardId,
            p => new LatestPriceDto(
                p.CardId, p.Provider, p.VariantId, p.Condition, p.Printing, p.Currency,
                p.MarketPrice, p.Change24Hours, p.CapturedAt, p.SourceUpdatedAt));

        try
        {
            var cards = await db.Cards.AsNoTracking().ToListAsync(ct);
            var livePrices = await riftboundGg.GetLatestAsync(cards, ct);
            foreach (var price in livePrices.Values)
            {
                latest[price.CardId] = new LatestPriceDto(
                    price.CardId,
                    "riftbound.gg",
                    price.ProviderCardId,
                    "Market",
                    price.Printing,
                    "USD",
                    price.MarketPrice,
                    price.Change24Hours,
                    price.FetchedAt,
                    null,
                    price.Change7Days,
                    price.SourceUrl);
            }
        }
        catch (Exception ex) when (!ct.IsCancellationRequested)
        {
            logger.LogWarning(ex, "Could not load live Riftbound.gg prices; using stored snapshots");
        }

        return latest;
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

    private static PriceSnapshotEntity ToSnapshot(PriceQuote quote, DateTimeOffset capturedAt) => new()
    {
        CardId = quote.CardId,
        Provider = quote.Provider,
        VariantId = quote.VariantId,
        Condition = quote.Condition,
        Printing = quote.Printing,
        Currency = quote.Currency,
        MarketPrice = quote.MarketPrice,
        Change24Hours = quote.Change24Hours,
        CapturedAt = capturedAt,
        SourceUpdatedAt = quote.SourceUpdatedAt,
    };
}
