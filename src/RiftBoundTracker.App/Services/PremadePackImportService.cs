using RiftBoundTracker.App.Data;

namespace RiftBoundTracker.App.Services;

// Carries the full CardEntity (not just the id) so the UI can render a preview of exactly what
// would be added -- image, name, type, rarity -- without a second round-trip to look each one up.
public sealed record PremadePackAppliedCard(CardEntity Card, int Quantity);
public sealed record PremadePackPreviewResult(List<string> UnmatchedCards, List<PremadePackAppliedCard> Cards);
public sealed record PremadePackImportResult(int AddedCards, int AddedCopies, List<string> UnmatchedCards, List<PremadePackAppliedCard> AppliedCards);

// Lean id+quantity pairs for the reverse direction -- undo only needs enough to find and adjust
// each card, not the full entity the import response carried for display purposes.
public sealed record PremadePackUndoEntry(string CardId, int Quantity);
public sealed record PremadePackUndoRequest(List<PremadePackUndoEntry> AppliedCards);

/// <summary>
/// Resolves and applies a PremadePackCatalogService pack's contents to the tracked collection.
/// Resolution (matching each pack entry's SetId/Code to a real card) is shared between preview and
/// import so they can never disagree about which cards a pack resolves to — only ImportAsync
/// actually touches ownership. Import adds each card's pack quantity on top of whatever's already
/// owned (buying the box gives you those cards in addition to any you already had, not a
/// floor/ceiling on the total), and reports exactly which cards were touched and by how much so
/// the UI can offer an immediate Undo without needing a general-purpose action-history system.
/// </summary>
public sealed class PremadePackImportService(CardCacheService cache)
{
    public async Task<PremadePackPreviewResult?> PreviewAsync(string packKey, CancellationToken ct = default)
    {
        var pack = PremadePackCatalogService.Packs.FirstOrDefault(p => p.Key == packKey);
        if (pack is null) return null;

        var (resolved, unmatched) = await ResolveAsync(pack, ct);
        return new PremadePackPreviewResult(unmatched, resolved);
    }

    public async Task<PremadePackImportResult?> ImportAsync(string packKey, CancellationToken ct = default)
    {
        var pack = PremadePackCatalogService.Packs.FirstOrDefault(p => p.Key == packKey);
        if (pack is null) return null;

        var (resolved, unmatched) = await ResolveAsync(pack, ct);
        foreach (var entry in resolved)
            await cache.AdjustOwnedAsync(entry.Card.Id, entry.Quantity, ct);

        return new PremadePackImportResult(resolved.Count, resolved.Sum(r => r.Quantity), unmatched, resolved);
    }

    private async Task<(List<PremadePackAppliedCard> Resolved, List<string> Unmatched)> ResolveAsync(
        PremadePackDefinition pack, CancellationToken ct)
    {
        var unmatched = new List<string>();
        var resolved = new List<PremadePackAppliedCard>();
        foreach (var entry in pack.Cards)
        {
            var cards = await cache.FindByCodeAsync(entry.SetId, entry.Code, ct);
            if (cards.Count != 1)
            {
                unmatched.Add($"{entry.SetId}-{entry.Code}");
                continue;
            }
            resolved.Add(new PremadePackAppliedCard(cards[0], entry.Quantity));
        }
        return (resolved, unmatched);
    }

    // Reverses exactly the deltas a prior ImportAsync call reported applying. Not a snapshot
    // restore — if ownership changed some other way in between (manual edit, a second import),
    // this only subtracts the recorded quantities, same as the import only ever added them.
    public async Task UndoAsync(List<PremadePackUndoEntry> appliedCards, CancellationToken ct = default)
    {
        foreach (var entry in appliedCards)
            await cache.AdjustOwnedAsync(entry.CardId, -entry.Quantity, ct);
    }

    // Same subtraction as UndoAsync, but for the Vault page's "Remove Pack" action — available any
    // time, not just right after an import (Undo needs the frontend to still be holding the exact
    // entries ImportAsync returned, which is gone once that session's result is out of scope).
    // Re-resolves the pack fresh instead, since resolution is deterministic and doesn't depend on
    // import history. AdjustOwnedAsync clamps to 0, so this is safe even if some copies were
    // already traded away or never actually came from this pack.
    public async Task<PremadePackImportResult?> RemoveAsync(string packKey, CancellationToken ct = default)
    {
        var pack = PremadePackCatalogService.Packs.FirstOrDefault(p => p.Key == packKey);
        if (pack is null) return null;

        var (resolved, unmatched) = await ResolveAsync(pack, ct);
        foreach (var entry in resolved)
            await cache.AdjustOwnedAsync(entry.Card.Id, -entry.Quantity, ct);

        return new PremadePackImportResult(resolved.Count, resolved.Sum(r => r.Quantity), unmatched, resolved);
    }
}
