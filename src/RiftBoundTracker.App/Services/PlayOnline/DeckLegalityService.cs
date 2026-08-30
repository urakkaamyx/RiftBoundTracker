using RiftBoundTracker.App.Services;

namespace RiftBoundTracker.App.Services.PlayOnline;

public sealed record DeckLegalityViolation(string Constraint, string Message);
public sealed record DeckLegalityResult(bool Legal, List<DeckLegalityViolation> Violations);

/// <summary>
/// Structured pass/fail deck-construction check for Play Online room setup - the C# counterpart
/// to rules-engine's deck_construction.py, which only answers natural-language QUESTIONS about
/// these same constraints. Nothing in this app validated an actual decklist object before this;
/// see the "Private online play" plan for the research that confirmed the gap. Thresholds mirror
/// Core Rule 103 and its children exactly as rules-engine already established them - this
/// deliberately doesn't re-derive them, just applies the same known numbers structurally.
/// </summary>
public sealed class DeckLegalityService
{
    private const int RequiredLegendCount = 1; // Rule 103.1
    private const int MinimumMainDeckCount = 40; // Rule 103.2
    private const int MaximumCopiesOfSameName = 3; // Rule 103.2.b
    private const int RequiredRuneCount = 12; // Rule 103.3
    private const int MaximumSignatureCards = 3; // Rule 103.2.d

    public DeckLegalityResult Check(DeckDetailDto deck)
    {
        var violations = new List<DeckLegalityViolation>();
        var cards = deck.Cards;

        var legendCount = cards.Where(c => c.Card.Type == "Legend").Sum(c => c.Quantity);
        if (legendCount != RequiredLegendCount)
            violations.Add(new DeckLegalityViolation("champion_legend_count",
                $"A deck needs exactly {RequiredLegendCount} Champion Legend (has {legendCount})."));

        var runeCount = cards.Where(c => c.Card.Type == "Rune").Sum(c => c.Quantity);
        if (runeCount != RequiredRuneCount)
            violations.Add(new DeckLegalityViolation("rune_deck_count",
                $"A Rune Deck needs exactly {RequiredRuneCount} Rune Cards (has {runeCount})."));

        // Main Deck = everything that isn't a Legend, Rune, or Battlefield - the same three-way
        // split the desktop's own deck-summary counters use (see deckSummaryMarkup's mainCount).
        var mainDeckCount = cards
            .Where(c => c.Section == "main" && c.Card.Type is not ("Legend" or "Rune" or "Battlefield"))
            .Sum(c => c.Quantity);
        if (mainDeckCount < MinimumMainDeckCount)
            violations.Add(new DeckLegalityViolation("main_deck_minimum",
                $"A Main Deck needs at least {MinimumMainDeckCount} cards (has {mainDeckCount})."));

        var signatureCount = cards.Where(c => c.Card.Name.Contains("Signature", StringComparison.OrdinalIgnoreCase)
                || (c.Card.Supertype?.Contains("Signature", StringComparison.OrdinalIgnoreCase) ?? false))
            .Sum(c => c.Quantity);
        if (signatureCount > MaximumSignatureCards)
            violations.Add(new DeckLegalityViolation("signature_limit",
                $"A deck can have at most {MaximumSignatureCards} Signature cards (has {signatureCount})."));

        // Same-named copy limit - group by card Name (not printing id), since different printings
        // of the same named card share the limit (confirmed by rules-engine's own same_name_copy_limit
        // obligation, which keys off "same named card" not "same exact card id").
        var byName = cards
            .Where(c => c.Card.Type is not ("Legend" or "Rune" or "Battlefield"))
            .GroupBy(c => c.Card.Name)
            .Select(g => new { Name = g.Key, Count = g.Sum(c => c.Quantity) });
        foreach (var group in byName.Where(g => g.Count > MaximumCopiesOfSameName))
            violations.Add(new DeckLegalityViolation("same_name_copy_limit",
                $"At most {MaximumCopiesOfSameName} copies of the same named card are allowed - {group.Name} has {group.Count}."));

        return new DeckLegalityResult(violations.Count == 0, violations);
    }
}
