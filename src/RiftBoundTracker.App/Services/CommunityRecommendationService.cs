using Microsoft.EntityFrameworkCore;
using RiftBoundTracker.App.Data;

namespace RiftBoundTracker.App.Services;

public record CardRecommendationDto(
    int DeckCount, int TotalDecks, double InclusionRate,
    double AverageCopies, int CurrentDeckQuantity, int OwnedCount, string Section, CardEntity Card,
    List<string> Tournaments);

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
        var decks = await db.CommunityDecks
            .Where(d => d.LegendCardId == legendCardId)
            .Select(d => new { d.Id, d.TournamentId })
            .ToListAsync(ct);
        var totalDecks = decks.Count;
        if (totalDecks == 0) return [];

        var deckIds = decks.Select(d => d.Id).ToList();
        var tournamentIds = decks.Select(d => d.TournamentId).Distinct().ToList();
        var tournaments = await db.CommunityTournaments
            .Where(t => tournamentIds.Contains(t.Id))
            .ToDictionaryAsync(t => t.Id, t => new { t.Name, t.StartDate }, ct);
        var deckToTournament = decks.ToDictionary(d => d.Id, d => d.TournamentId);

        var communityCards = await db.CommunityDeckCards
            .Where(c => deckIds.Contains(c.CommunityDeckId) && c.CardId != legendCardId)
            .Include(c => c.Card)
            .ToListAsync(ct);

        // TopDeck logs decklists under whatever specific print a player happened to submit —
        // that has nothing to do with deckbuilding strategy, so "do I already own/have this
        // card" must be checked across every print sharing the same base name, not just the
        // exact print id the community data references. Otherwise a card the user owns under a
        // different print (e.g. a Rune reprint) shows as "own 0" and gets recommended as an
        // upgrade they already effectively have.
        var allCards = await db.Cards.AsNoTracking().Select(c => new { c.Id, c.Name, c.OwnedCount }).ToListAsync(ct);
        var ownedByBase = allCards
            .GroupBy(c => BaseName(c.Name))
            .ToDictionary(g => g.Key, g => g.Sum(c => c.OwnedCount));
        var cardNameById = allCards.ToDictionary(c => c.Id, c => c.Name);

        var currentDeckRows = await db.DeckCards
            .Where(dc => dc.DeckId == deckId)
            .Select(dc => new { dc.CardId, dc.Quantity })
            .ToListAsync(ct);
        var currentDeckByBase = currentDeckRows
            .GroupBy(dc => BaseName(cardNameById.GetValueOrDefault(dc.CardId, "")))
            .ToDictionary(g => g.Key, g => g.Sum(dc => dc.Quantity));

        return communityCards
            .GroupBy(c => c.CardId)
            .Select(g =>
            {
                var card = g.First().Card;
                var baseName = BaseName(card.Name);
                var deckCount = g.Select(c => c.CommunityDeckId).Distinct().Count();
                var mainCount = g.Count(c => c.Section == "main");
                var sideCount = g.Count(c => c.Section == "sideboard");
                var tournamentNames = g.Select(c => deckToTournament[c.CommunityDeckId])
                    .Distinct()
                    .Select(tid => tournaments[tid])
                    .OrderByDescending(t => t.StartDate)
                    .Select(t => t.Name)
                    .Take(5)
                    .ToList();
                return new CardRecommendationDto(
                    deckCount, totalDecks,
                    Math.Round(deckCount * 100.0 / totalDecks, 1),
                    Math.Round(g.Average(c => c.Quantity), 2),
                    currentDeckByBase.GetValueOrDefault(baseName),
                    ownedByBase.GetValueOrDefault(baseName),
                    mainCount >= sideCount ? "main" : "sideboard", card, tournamentNames);
            })
            .OrderByDescending(r => r.InclusionRate)
            .ThenByDescending(r => r.AverageCopies)
            .ToList();
    }

    // Different prints of the same card share a base name with the variant called out in a
    // trailing "(...)" — mirrors the client-side legendBaseName()/groupLegendVariants() split.
    private static string BaseName(string name)
    {
        var idx = name.IndexOf(" (", StringComparison.Ordinal);
        return idx == -1 ? name : name[..idx];
    }
}
