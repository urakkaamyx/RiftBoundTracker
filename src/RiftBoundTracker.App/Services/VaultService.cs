using Microsoft.EntityFrameworkCore;
using RiftBoundTracker.App.Data;

namespace RiftBoundTracker.App.Services;

public record FavoriteRequest(bool Favorite);
public record BinderRequest(int Count);
public record SetProgressDto(string SetId, string SetLabel, int Total, int Owned, int Copies, double Completion);
public record DistributionDto(string Label, int Cards, int Owned, int Copies);
public record ValuableCardDto(CardEntity Card, double UnitPrice, double CollectionValue, double? Change24Hours);
public record VaultOverviewDto(
    int TotalCards, int OwnedCards, int OwnedCopies, int MissingCards, int FavoriteCards,
    int BinderCards, int BinderCopies, int Decks, int ReadyDecks, bool HasPricing,
    double CollectionValue, double BinderValue, List<SetProgressDto> Sets,
    List<DistributionDto> Rarities, List<DistributionDto> Domains,
    List<ValuableCardDto> MostValuable, List<DeckSummaryDto> DeckReadiness);

public sealed class VaultService(
    AppDbContext db,
    PriceSyncService prices,
    DeckService decks)
{
    public async Task<CardEntity?> SetFavoriteAsync(string cardId, bool favorite, CancellationToken ct = default)
    {
        var card = await db.Cards.FindAsync([cardId], ct);
        if (card is null) return null;
        card.IsFavorite = favorite;
        card.UpdatedAt = DateTimeOffset.UtcNow;
        await db.SaveChangesAsync(ct);
        return card;
    }

    public async Task<CardEntity?> SetBinderCountAsync(string cardId, int count, CancellationToken ct = default)
    {
        var card = await db.Cards.FindAsync([cardId], ct);
        if (card is null) return null;
        card.BinderCount = Math.Clamp(count, 0, card.OwnedCount);
        card.UpdatedAt = DateTimeOffset.UtcNow;
        await db.SaveChangesAsync(ct);
        return card;
    }

    // Distinct from SetBinderCountAsync(0), which only un-flags a card as tradeable and leaves it
    // in the collection — this is for when a trade actually happened: the copies are gone, not
    // just no longer offered. Removes from both OwnedCount and BinderCount together.
    public async Task<CardEntity?> ConfirmTradeAsync(string cardId, int count, CancellationToken ct = default)
    {
        var card = await db.Cards.FindAsync([cardId], ct);
        if (card is null) return null;
        card.OwnedCount = Math.Max(0, card.OwnedCount - count);
        card.BinderCount = Math.Min(card.BinderCount, card.OwnedCount);
        card.UpdatedAt = DateTimeOffset.UtcNow;
        await db.SaveChangesAsync(ct);
        return card;
    }

    public Task<List<CardEntity>> GetFavoritesAsync(CancellationToken ct = default) =>
        db.Cards.AsNoTracking()
            .Where(c => c.IsFavorite)
            .OrderBy(c => c.Name)
            .ToListAsync(ct);

    public Task<List<CardEntity>> GetBinderAsync(CancellationToken ct = default) =>
        db.Cards.AsNoTracking()
            .Where(c => c.BinderCount > 0)
            .OrderBy(c => c.SetId)
            .ThenBy(c => c.CollectorNumber)
            .ToListAsync(ct);

    public async Task<VaultOverviewDto> GetOverviewAsync(CancellationToken ct = default)
    {
        var cards = await db.Cards.AsNoTracking().ToListAsync(ct);
        var latestPrices = await prices.GetLatestAsync(ct);
        var deckSummaries = await decks.GetAllAsync(ct);

        var sets = cards
            .GroupBy(c => new { c.SetId, c.SetLabel })
            .Select(g => new SetProgressDto(
                g.Key.SetId, g.Key.SetLabel, g.Count(), g.Count(c => c.OwnedCount > 0),
                g.Sum(c => c.OwnedCount), g.Any() ? g.Count(c => c.OwnedCount > 0) * 100d / g.Count() : 0))
            .OrderBy(s => s.SetId)
            .ToList();

        var rarities = cards
            .GroupBy(c => string.IsNullOrWhiteSpace(c.Rarity) ? "Unknown" : c.Rarity)
            .Select(ToDistribution)
            .OrderByDescending(d => d.Cards)
            .ToList();

        var domains = cards
            .SelectMany(c => (c.Domains.Length == 0 ? ["Colorless"] : c.Domains)
                .Select(domain => new { Domain = domain, Card = c }))
            .GroupBy(x => x.Domain)
            .Select(g => new DistributionDto(
                g.Key, g.Count(), g.Count(x => x.Card.OwnedCount > 0), g.Sum(x => x.Card.OwnedCount)))
            .OrderByDescending(d => d.Cards)
            .ToList();

        var valuable = cards
            .Where(c => c.OwnedCount > 0 && latestPrices.ContainsKey(c.Id))
            .Select(c => new ValuableCardDto(
                c, latestPrices[c.Id].MarketPrice,
                latestPrices[c.Id].MarketPrice * c.OwnedCount,
                latestPrices[c.Id].Change24Hours))
            .OrderByDescending(v => v.CollectionValue)
            .Take(12)
            .ToList();

        var collectionValue = cards.Sum(c =>
            latestPrices.TryGetValue(c.Id, out var price) ? price.MarketPrice * c.OwnedCount : 0);
        var binderValue = cards.Sum(c =>
            latestPrices.TryGetValue(c.Id, out var price) ? price.MarketPrice * c.BinderCount : 0);

        return new VaultOverviewDto(
            cards.Count,
            cards.Count(c => c.OwnedCount > 0),
            cards.Sum(c => c.OwnedCount),
            cards.Count(c => c.OwnedCount == 0),
            cards.Count(c => c.IsFavorite),
            cards.Count(c => c.BinderCount > 0),
            cards.Sum(c => c.BinderCount),
            deckSummaries.Count,
            deckSummaries.Count(d => d.MissingCount == 0 && d.MainCount > 0),
            latestPrices.Count > 0,
            collectionValue,
            binderValue,
            sets,
            rarities,
            domains,
            valuable,
            deckSummaries);
    }

    private static DistributionDto ToDistribution(IGrouping<string, CardEntity> group) =>
        new(group.Key, group.Count(), group.Count(c => c.OwnedCount > 0), group.Sum(c => c.OwnedCount));
}
