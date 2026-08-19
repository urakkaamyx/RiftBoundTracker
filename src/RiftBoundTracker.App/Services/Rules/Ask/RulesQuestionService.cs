using System.Text.RegularExpressions;
using Microsoft.EntityFrameworkCore;
using RiftBoundTracker.App.Data;
using RiftBoundTracker.App.Services;

namespace RiftBoundTracker.App.Services.Rules;

/// <summary>
/// Parses a free-text question into the structured signals the rest of the Ask Rules pipeline
/// needs (architecture doc section 5): rule numbers, official keywords, player-slang aliases
/// (resolved back to their canonical keyword), and broader concepts. Card-name detection is
/// deliberately NOT done by scanning arbitrary free text against the ~1300-card catalog — too many
/// card names collide with common English words (a card literally named "Control") to do that
/// without constant false positives, so card context only comes from an explicit cardId the caller
/// supplies (the "Ask About This Card" flow the doc describes in section 23), never guessed.
/// </summary>
public sealed partial class RulesQuestionService(AppDbContext db, CardTextSymbolCatalogService symbols)
{
    public async Task<RulesQuestionAnalysis> AnalyzeAsync(string question, string? cardId = null, CancellationToken ct = default)
    {
        var normalized = NormalizeQuestion(question);

        var ruleNumbers = RuleNumberMention().Matches(normalized)
            .Select(m => m.Value.TrimEnd('.'))
            .Distinct()
            .ToList();

        var keywords = await db.RuleKeywords.Include(k => k.Aliases).ToListAsync(ct);
        var detectedKeywords = new List<DetectedKeywordDto>();
        foreach (var keyword in keywords)
        {
            if (ContainsWholeWord(normalized, keyword.NormalizedName))
            {
                detectedKeywords.Add(new DetectedKeywordDto(keyword.Id, keyword.Name, null));
                continue;
            }
            var alias = keyword.Aliases.FirstOrDefault(a => ContainsWholeWord(normalized, a.NormalizedAlias));
            if (alias is not null)
                detectedKeywords.Add(new DetectedKeywordDto(keyword.Id, keyword.Name, alias.Alias));
        }

        var concepts = await db.RuleConcepts.Include(c => c.Phrases).Include(c => c.Keywords).ToListAsync(ct);
        var detectedKeywordIds = detectedKeywords.Select(k => k.Id).ToHashSet();
        var detectedConcepts = new List<DetectedConceptDto>();
        foreach (var concept in concepts)
        {
            var phrase = concept.Phrases.FirstOrDefault(p => ContainsWholeWord(normalized, p.NormalizedPhrase));
            var viaKeyword = concept.Keywords.Any(k => detectedKeywordIds.Contains(k.KeywordId));
            if (phrase is not null || viaKeyword)
                detectedConcepts.Add(new DetectedConceptDto(concept.Id, concept.Name, phrase?.Phrase));
        }

        // Concept-linked keywords that weren't independently detected in the question text still
        // count as retrieval evidence (that's the whole point of a concept), just not as a
        // "detected keyword" the UI would highlight as literally present in the question.
        var conceptKeywordIds = concepts
            .Where(c => detectedConcepts.Any(dc => dc.Id == c.Id))
            .SelectMany(c => c.Keywords.Select(k => k.KeywordId))
            .Distinct();
        var expandedTerms = detectedKeywords.Select(k => k.Name)
            .Concat(keywords.Where(k => conceptKeywordIds.Contains(k.Id)).Select(k => k.Name))
            .Distinct()
            .ToList();

        var cardContext = new List<CardSummaryDto>();
        if (!string.IsNullOrWhiteSpace(cardId))
        {
            var card = await db.Cards.Where(c => c.Id == cardId)
                .Select(c => new CardSummaryDto(c.Id, c.Name, c.LocalImagePath ?? c.ImageUrl, c.TextPlain))
                .FirstOrDefaultAsync(ct);
            if (card is not null) cardContext.Add(card with { Text = await symbols.HumanizeAsync(card.Text, ct) });
        }

        return new RulesQuestionAnalysis(question, normalized, ruleNumbers, detectedKeywords, detectedConcepts, cardContext, expandedTerms);
    }

    private static string NormalizeQuestion(string question) =>
        WhitespaceRun().Replace(question.Trim().ToLowerInvariant(), " ");

    private static bool ContainsWholeWord(string haystack, string needle) =>
        needle.Length > 0 && WordBoundaryPattern(needle).IsMatch(haystack);

    private static readonly Dictionary<string, Regex> WordBoundaryCache = new();
    private static Regex WordBoundaryPattern(string needle)
    {
        if (WordBoundaryCache.TryGetValue(needle, out var cached)) return cached;
        var regex = new Regex(@"\b" + Regex.Escape(needle) + @"\b", RegexOptions.IgnoreCase);
        WordBoundaryCache[needle] = regex;
        return regex;
    }

    [GeneratedRegex(@"\b\d{3,}(?:\.[0-9a-zA-Z]+)*\b")]
    private static partial Regex RuleNumberMention();

    [GeneratedRegex(@"\s+")]
    private static partial Regex WhitespaceRun();
}
