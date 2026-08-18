using Microsoft.EntityFrameworkCore;
using RiftBoundTracker.App.Data;

namespace RiftBoundTracker.App.Services;

public record CardRecommendationDto(
    int DeckCount, int TotalDecks, double InclusionRate,
    double AverageCopies, int CurrentDeckQuantity, string Section, CardEntity Card);

/// <summary>
/// Computes "how often does the community play this card alongside this Legend" purely from
/// locally-synced data (CommunityDeckSyncService populates it separately, on a manual trigger) —
/// never a live TopDeck call on this read path, matching the tight rate limit.
/// </summary>
public sealed class CommunityRecommendationService(AppDbContext db)
{
    public async Task<List<CardRecommendationDto>> GetRecommendationsAsync(
        int deckId, string legendCardId, CancellationToken ct = default)
    {
        var deckIds = await db.CommunityDecks
            .Where(d => d.LegendCardId == legendCardId)
            .Select(d => d.Id)
            .ToListAsync(ct);
        var totalDecks = deckIds.Count;
        if (totalDecks == 0) return [];

        var communityCards = await db.CommunityDeckCards
            .Where(c => deckIds.Contains(c.CommunityDeckId) && c.CardId != legendCardId)
            .Include(c => c.Card)
            .ToListAsync(ct);

        var currentDeck = await db.DeckCards
            .Where(dc => dc.DeckId == deckId)
            .ToDictionaryAsync(dc => dc.CardId, dc => dc.Quantity, ct);

        return communityCards
            .GroupBy(c => c.CardId)
            .Select(g =>
            {
                var card = g.First().Card;
                var deckCount = g.Select(c => c.CommunityDeckId).Distinct().Count();
                var mainCount = g.Count(c => c.Section == "main");
                var sideCount = g.Count(c => c.Section == "sideboard");
                return new CardRecommendationDto(
                    deckCount, totalDecks,
                    Math.Round(deckCount * 100.0 / totalDecks, 1),
                    Math.Round(g.Average(c => c.Quantity), 2),
                    currentDeck.GetValueOrDefault(card.Id),
                    mainCount >= sideCount ? "main" : "sideboard", card);
            })
            .OrderByDescending(r => r.InclusionRate)
            .ThenByDescending(r => r.AverageCopies)
            .ToList();
    }
}
