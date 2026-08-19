using Microsoft.EntityFrameworkCore;
using RiftBoundTracker.App.Data;
using RiftBoundTracker.App.Services;

namespace RiftBoundTracker.App.Services.Rules;

public sealed record RuleEvidence(RuleSearchHit Hit, List<string> MatchedVia, double Score);

// A card's current legality/errata status, surfaced when its exact name appears in the question.
// Not a RuleEntry, so it can't flow through RuleSearchHit — kept as a small parallel evidence
// type instead of forcing an unrelated shape onto it. One fact per entry (never merged into a
// single multi-fact block) so LocalLlmExplanationProvider can format each as its own bracketed
// evidence item — the same shape as every other evidence source it's ever seen.
public sealed record CardEvidence(string CardId, string CardName, string Authority, string Note);

public sealed record RulesEvidenceResult(List<RuleEvidence> Rules, List<CardEvidence> Cards);

/// <summary>
/// Multi-strategy retrieval for a free-text question (architecture doc section 11): exact rule
/// numbers, every rule tied to a detected or concept-linked keyword, and a full-text fallback on
/// the raw question — merged and deduplicated, each rule keeping every reason it matched. Built
/// entirely on RulesSearchService (never re-implements FTS or keyword lookup), per the doc's
/// explicit instruction to consume the deterministic search system rather than duplicate it.
///
/// Also checks the question for an exact local card name (a bounded, deliberately narrow check —
/// not general card-name detection; see RulesQuestionService's own note on why fuzzy card-name
/// scanning in free text is avoided) and pulls that card's legality/errata as extra evidence, so
/// "Is Called Shot banned?" actually has something to answer from instead of silently finding
/// nothing — legality/errata rows live outside the FTS-indexed RuleEntries table entirely, so the
/// text-fallback search above can never see them on its own.
/// </summary>
public sealed class RulesEvidenceService(RulesSearchService search, AppDbContext db, CardTextSymbolCatalogService symbols)
{
    private const double RuleNumberWeight = 1000;
    private const double TextFallbackDamping = 0.4;
    // Between mentioned-keyword (80) and text-fallback tiers — a rule the evidence set explicitly
    // points to ("See rule 197...") is a stronger signal than an incidental text match, but
    // shouldn't outrank anything the question's own keywords/concepts pulled in directly.
    private const double CrossReferenceWeight = 60;

    public async Task<RulesEvidenceResult> GatherAsync(
        RulesQuestionAnalysis analysis, bool currentOnly = true, int limit = 16, CancellationToken ct = default)
    {
        var byId = new Dictionary<int, (RuleSearchHit Hit, List<string> Via, double Score)>();

        // Weighted the same way RulesSearchService's own final ranking weights authority — without
        // this, a Patch Notes article that happens to mention several keywords in passing (it's
        // indexed as one whole-section blob, see ArticleSectionParser) can rack up a higher raw
        // score than a single precise Core Rules definition just by accumulating more "mentioned
        // in" hits, which is exactly backwards per the doc's "current authoritative material always
        // outranks" rule (section 10).
        void Add(RuleSearchHit hit, string via, double weight)
        {
            var weighted = weight * AuthorityWeight(hit.Document.Authority);
            if (byId.TryGetValue(hit.RuleId, out var existing))
            {
                if (!existing.Via.Contains(via)) existing.Via.Add(via);
                byId[hit.RuleId] = (existing.Hit, existing.Via, existing.Score + weighted);
            }
            else
            {
                byId[hit.RuleId] = (hit, [via], weighted);
            }
        }

        foreach (var number in analysis.DetectedRuleNumbers)
        {
            var response = await search.SearchAsync(number, currentOnly, 1, ct);
            foreach (var hit in response.Results.Where(h => h.MatchType == "RuleNumber"))
                Add(hit, $"rule number {number}", RuleNumberWeight);
        }

        var keywordNames = analysis.DetectedKeywords.ToDictionary(k => k.Id, k => k.Name);
        var conceptKeywordIds = await db.RuleConceptKeywords
            .Where(ck => analysis.DetectedConcepts.Select(c => c.Id).Contains(ck.ConceptId))
            .Include(ck => ck.Keyword)
            .ToListAsync(ct);
        foreach (var link in conceptKeywordIds)
            keywordNames.TryAdd(link.KeywordId, link.Keyword.Name);

        foreach (var (keywordId, name) in keywordNames)
        {
            var hits = await search.SearchByKeywordIdAsync(keywordId, currentOnly, ct);
            foreach (var hit in hits)
                Add(hit, $"keyword \"{name}\"", hit.Score);
        }

        var textResponse = await search.SearchAsync(analysis.OriginalQuestion, currentOnly, limit, ct);
        foreach (var hit in textResponse.Results.Where(h => h.MatchType is "FullText" or "Title"))
            Add(hit, "matching text", hit.Score * TextFallbackDamping);

        // Multi-hop trace across the RuleCrossReferences graph, not one hop only — a rule that says
        // "See rule 197" can itself point somewhere the question actually needs, and a real
        // multi-part interaction can be more than one reference away from anything the question's
        // own keywords/text matched directly. Each hop's weight decays (60, 30, 20...) so distance
        // from the seed evidence still matters — a rule several hops out shouldn't outrank one
        // found directly — and the walk is bounded to maxHops so a densely cross-referenced corpus
        // can't turn into an unbounded graph traversal.
        //
        // A trace landing back on a rule already in the evidence set is never re-added or
        // re-expanded — Add() folds it into that rule's existing score instead, since a rule
        // multiple paths converge on genuinely is more load-bearing than one only reached once.
        // Each rule is only expanded (its own outgoing references followed) the first time it's
        // reached, regardless of how many times it's re-scored after that.
        if (byId.Count > 0)
        {
            const int maxHops = 3;
            var frontier = byId.Keys.ToList();
            var expanded = new HashSet<int>();
            for (var hop = 0; hop < maxHops && frontier.Count > 0; hop++)
            {
                var toExpand = frontier.Where(expanded.Add).ToList();
                if (toExpand.Count == 0) break;
                var hopWeight = CrossReferenceWeight / (hop + 1);
                var crossRefs = await db.RuleCrossReferences
                    .Where(x => toExpand.Contains(x.FromRuleId))
                    .Include(x => x.ToRule).ThenInclude(r => r.Document)
                    .ToListAsync(ct);
                var nextFrontier = new List<int>();
                foreach (var xref in crossRefs)
                {
                    if (currentOnly && !xref.ToRule.IsCurrent) continue;
                    var fromLabel = byId.TryGetValue(xref.FromRuleId, out var fromEntry)
                        ? fromEntry.Hit.RuleNumber ?? fromEntry.Hit.Title
                        : xref.FromRuleId.ToString();
                    var hit = await search.ToHitAsync(xref.ToRule, "CrossReference", hopWeight, ct);
                    Add(hit, $"cross-reference from Rule {fromLabel}", hopWeight);
                    nextFrontier.Add(xref.ToRuleId);
                }
                frontier = nextFrontier;
            }
        }

        var ruleEvidence = byId.Values
            .OrderByDescending(x => x.Score)
            .ThenByDescending(x => x.Hit.Document.Current)
            .Take(limit)
            .Select(x => new RuleEvidence(x.Hit, x.Via, x.Score))
            .ToList();

        var cardEvidence = await FindCardEvidenceAsync(analysis.OriginalQuestion, ct);
        return new RulesEvidenceResult(ruleEvidence, cardEvidence);
    }

    private async Task<List<CardEvidence>> FindCardEvidenceAsync(string question, CancellationToken ct)
    {
        var cards = await db.Cards.Select(c => new { c.Id, c.Name, c.TextPlain }).ToListAsync(ct);
        // Checks the card's own separator style, the swapped style ("Champion, Title" vs
        // "Champion - Title" — the catalog isn't internally consistent about comma vs dash,
        // confirmed directly: "Draven - Vanquisher" but errata/legality text and natural questions
        // both say "Draven, Vanquisher"), and no separator at all ("Darius Trifarian" for the card
        // "Darius - Trifarian" — a real question phrased exactly that way found no card evidence at
        // all until this was added, since a casual question is at least as likely to drop the
        // punctuation entirely as to use the "other" punctuated style).
        var matched = cards
            .Where(c => ContainsWholeWord(question, c.Name)
                || ContainsWholeWord(question, CardCacheService.SwapNameSeparator(c.Name))
                || ContainsWholeWord(question, CardCacheService.StripNameSeparator(c.Name)))
            .Take(3).ToList();
        if (matched.Count == 0) return [];

        var result = new List<CardEvidence>();
        foreach (var card in matched)
        {
            // A card's own printed text is evidence in its own right — "what does Arena Kingpin
            // do?" has a real answer even though the card has no ban/errata history, but before
            // this only legality/errata rows ever became CardEvidence, so a clean card with a
            // literal name match still fell through to "insufficient evidence".
            if (!string.IsNullOrWhiteSpace(card.TextPlain))
                result.Add(new CardEvidence(card.Id, card.Name, "CardText", (await symbols.HumanizeAsync(card.TextPlain, ct))!));

            var legalities = await db.CardLegalities.Where(l => l.CardId == card.Id && l.IsCurrent).ToListAsync(ct);
            foreach (var l in legalities)
                result.Add(new CardEvidence(card.Id, card.Name, "CoreRules", $"{card.Name} is {l.Status} in {l.Format}."));

            var errata = await db.CardErrata.Where(e => e.CardId == card.Id && e.IsCurrent).ToListAsync(ct);
            foreach (var e in errata)
                result.Add(new CardEvidence(card.Id, card.Name, "OfficialErrata",
                    $"Original: {e.OriginalText}\nUpdated: {e.CorrectedText}"));
        }
        return result;
    }

    private static bool ContainsWholeWord(string haystack, string needle) =>
        needle.Length > 0 && System.Text.RegularExpressions.Regex.IsMatch(
            haystack, @"\b" + System.Text.RegularExpressions.Regex.Escape(needle) + @"\b",
            System.Text.RegularExpressions.RegexOptions.IgnoreCase);

    private static double AuthorityWeight(string authority) =>
        Enum.TryParse<RuleAuthority>(authority, out var value) ? (int)value + 1 : 1;
}
