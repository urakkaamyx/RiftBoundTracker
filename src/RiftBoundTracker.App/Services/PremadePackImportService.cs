using RiftBoundTracker.App.Data;

namespace RiftBoundTracker.App.Services;

// Carries the full CardEntity (not just the id) so the UI can render a preview of exactly what
// was just added — image, name, type, rarity — without a second round-trip to look each one up.
public sealed record PremadePackAppliedCard(CardEntity Card, int Quantity);
public sealed record PremadePackImportResult(int AddedCards, List<string> UnmatchedCards, List<PremadePackAppliedCard> AppliedCards);

// Lean id+quantity pairs for the reverse direction — undo only needs enough to find and adjust
// each card, not the full entity the import response carried for display purposes.
public sealed record PremadePackUndoEntry(string CardId, int Quantity);
public sealed record PremadePackUndoRequest(List<PremadePackUndoEntry> AppliedCards);

/// <summary>
/// Applies a PremadePackCatalogService pack's contents to the tracked collection — adds each
/// card's pack quantity on top of whatever's already owned (buying the box gives you those cards
/// in addition to any you already had, not a floor/ceiling on the total). Returns exactly which
/// cards were touched and by how much, so the UI can offer an immediate Undo without needing a
/// general-purpose action-history system — undo just replays the same deltas negated.
/// </summary>
public sealed class PremadePackImportService(CardCacheService cache)
{
    public async Task<PremadePackImportResult?> ImportAsync(string packKey, CancellationToken ct = default)
    {
        var pack = PremadePackCatalogService.Packs.FirstOrDefault(p => p.Key == packKey);
        if (pack is null) return null;

        var unmatched = new List<string>();
        var applied = new List<PremadePackAppliedCard>();
        foreach (var entry in pack.Cards)
        {
            var cards = await cache.FindByCodeAsync(entry.SetId, entry.Code, ct);
            if (cards.Count != 1)
            {
                unmatched.Add($"{entry.SetId}-{entry.Code}");
                continue;
            }
            var updated = await cache.AdjustOwnedAsync(cards[0].Id, entry.Quantity, ct);
            if (updated is not null) applied.Add(new PremadePackAppliedCard(updated, entry.Quantity));
        }
        return new PremadePackImportResult(applied.Count, unmatched, applied);
    }

    // Reverses exactly the deltas a prior ImportAsync call reported applying. Not a snapshot
    // restore — if ownership changed some other way in between (manual edit, a second import),
    // this only subtracts the recorded quantities, same as the import only ever added them.
    public async Task UndoAsync(List<PremadePackUndoEntry> appliedCards, CancellationToken ct = default)
    {
        foreach (var entry in appliedCards)
            await cache.AdjustOwnedAsync(entry.CardId, -entry.Quantity, ct);
    }
}
