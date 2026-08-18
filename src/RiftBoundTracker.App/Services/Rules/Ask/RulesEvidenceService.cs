using Microsoft.EntityFrameworkCore;
using RiftBoundTracker.App.Data;

namespace RiftBoundTracker.App.Services.Rules;

public sealed record RuleEvidence(RuleSearchHit Hit, List<string> MatchedVia, double Score);

/// <summary>
/// Multi-strategy retrieval for a free-text question (architecture doc section 11): exact rule
/// numbers, every rule tied to a detected or concept-linked keyword, and a full-text fallback on
/// the raw question — merged and deduplicated, each rule keeping every reason it matched. Built
/// entirely on RulesSearchService (never re-implements FTS or keyword lookup), per the doc's
/// explicit instruction to consume the deterministic search system rather than duplicate it.
/// </summary>
public sealed class RulesEvidenceService(RulesSearchService search, AppDbContext db)
{
    private const double RuleNumberWeight = 1000;
    private const double TextFallbackDamping = 0.4;

    public async Task<List<RuleEvidence>> GatherAsync(
        RulesQuestionAnalysis analysis, bool currentOnly = true, int limit = 12, CancellationToken ct = default)
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

        return byId.Values
            .OrderByDescending(x => x.Score)
            .ThenByDescending(x => x.Hit.Document.Current)
            .Take(limit)
            .Select(x => new RuleEvidence(x.Hit, x.Via, x.Score))
            .ToList();
    }

    private static double AuthorityWeight(string authority) =>
        Enum.TryParse<RuleAuthority>(authority, out var value) ? (int)value + 1 : 1;
}
