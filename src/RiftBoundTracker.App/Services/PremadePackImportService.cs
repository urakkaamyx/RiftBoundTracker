namespace RiftBoundTracker.App.Services;

public sealed record PremadePackImportResult(int AddedCards, List<string> UnmatchedCards);

/// <summary>
/// Applies a PremadePackCatalogService pack's contents to the tracked collection — adds each
/// card's pack quantity on top of whatever's already owned (buying the box gives you those cards
/// in addition to any you already had, not a floor/ceiling on the total).
/// </summary>
public sealed class PremadePackImportService(CardCacheService cache)
{
    public async Task<PremadePackImportResult?> ImportAsync(string packKey, CancellationToken ct = default)
    {
        var pack = PremadePackCatalogService.Packs.FirstOrDefault(p => p.Key == packKey);
        if (pack is null) return null;

        var unmatched = new List<string>();
        var added = 0;
        foreach (var entry in pack.Cards)
        {
            var cards = await cache.FindByCodeAsync(entry.SetId, entry.Code, ct);
            if (cards.Count != 1)
            {
                unmatched.Add($"{entry.SetId}-{entry.Code}");
                continue;
            }
            var card = cards[0];
            await cache.SetOwnedAsync(card.Id, card.OwnedCount + entry.Quantity, ct);
            added++;
        }
        return new PremadePackImportResult(added, unmatched);
    }
}
