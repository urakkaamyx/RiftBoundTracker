using System.Text.Json;
using System.Text.Json.Serialization;

namespace RiftBoundTracker.App.Services.Rules;

public sealed record CuratedRuling(
    string Id, string Source, List<string> Paraphrases, List<string> RuleNumbers,
    string Answer, string Explanation, List<string> Keywords);

/// <summary>
/// Why this exists (see scripts/training/generate_curated_rulings.py for the full story): four
/// rounds of fine-tuning Qwen3-1.7B on the adjudicate/explain task shape showed the model's RULING
/// quality — not just its output format — is inconsistent. The same directly-trained fact could
/// come out correct or hedge into "insufficient evidence" depending on the run, and fixing one
/// failure tended to shuffle in a different one rather than shrinking the failure count overall.
///
/// For the bounded, curatable set of questions this file covers, the model doesn't need to DECIDE
/// anything — the ruling is already known, verified either directly against the corpus this session
/// or by riftboundfaq.com's community, with real rule citations either way. RulesAnswerService
/// checks this BEFORE calling any LLM at all: a match returns an answer with zero model involvement
/// and zero hallucination risk; only a question that doesn't match anything here reaches the
/// LLM-driven adjudicate/explain pipeline (or its single-pass fallback).
///
/// Matching is deliberately conservative — plain word-overlap (RulesTextSimilarity, the same
/// mechanism RulesAdjudicationValidator uses to catch off-topic drift), required in BOTH directions
/// at a high bar. A false-positive match here would ship a confidently wrong answer with no LLM in
/// the loop to hedge or decline, so it's better to miss a real match (falling through to the normal
/// pipeline, which still might get it right) than to loosely match a superficially similar but
/// factually different question.
/// </summary>
public sealed class RulesCuratedRulingService(IWebHostEnvironment env, ILogger<RulesCuratedRulingService> logger)
{
    private const double MinOverlap = 0.65;

    private List<CuratedRuling>? _rulings;

    private List<CuratedRuling> Rulings
    {
        get
        {
            if (_rulings is not null) return _rulings;
            var path = Path.Combine(env.ContentRootPath, "RulesData", "CuratedRulings.json");
            if (!File.Exists(path))
            {
                logger.LogWarning("CuratedRulings.json not found at {Path} — curated ruling lookup disabled", path);
                _rulings = [];
                return _rulings;
            }
            try
            {
                var json = File.ReadAllText(path);
                _rulings = JsonSerializer.Deserialize<List<CuratedRulingJson>>(json, JsonOptions)
                    ?.Select(r => new CuratedRuling(r.Id, r.Source, r.Paraphrases, r.RuleNumbers, r.Answer, r.Explanation, r.Keywords ?? []))
                    .ToList() ?? [];
                logger.LogInformation("Loaded {Count} curated rulings", _rulings.Count);
            }
            catch (Exception ex)
            {
                logger.LogWarning(ex, "Failed to load CuratedRulings.json — curated ruling lookup disabled");
                _rulings = [];
            }
            return _rulings;
        }
    }

    private static readonly JsonSerializerOptions JsonOptions = new() { PropertyNameCaseInsensitive = true };

    public CuratedRuling? TryMatch(string question)
    {
        var questionWords = RulesTextSimilarity.SignificantWords(question);
        // Only reject genuinely empty word sets, not single-word ones — "What does Backline do?"
        // reduces to exactly one significant word ("backline") once "what"/"does"/"do" are
        // stripped, which used to fail this check outright and made the single most natural
        // keyword-lookup phrasing unmatchable against ANY curated entry, no matter how well it
        // otherwise fit. A single-word match still has to clear MinOverlap in both directions
        // below, which for a 1-word set means an exact match — actually stricter than the 65%
        // fuzzy bar a multi-word match gets, so this doesn't reopen the false-positive risk the
        // original 2-word floor was guarding against (a generic word incidentally overlapping a
        // longer, unrelated paraphrase) — it only stops excluding short, specific, single-term
        // questions and paraphrases from ever being compared at all.
        if (questionWords.Count < 1) return null;

        CuratedRuling? best = null;
        var bestScore = 0.0;
        foreach (var ruling in Rulings)
        {
            foreach (var paraphrase in ruling.Paraphrases)
            {
                var paraphraseWords = RulesTextSimilarity.SignificantWords(paraphrase);
                if (paraphraseWords.Count < 1) continue;
                // Both directions must clear the bar — otherwise a short, generic question would
                // "fully overlap" with one word of a much longer, more specific paraphrase (or vice
                // versa), which isn't the same question at all.
                var score = Math.Min(
                    RulesTextSimilarity.OverlapFraction(questionWords, paraphraseWords),
                    RulesTextSimilarity.OverlapFraction(paraphraseWords, questionWords));
                if (score >= MinOverlap && score > bestScore)
                {
                    bestScore = score;
                    best = ruling;
                }
            }
        }
        if (best is not null)
            logger.LogDebug("Ask Rules: curated ruling match {Id} score={Score:F2} for {Question}", best.Id, bestScore, question);
        return best;
    }

    private sealed record CuratedRulingJson(
        string Id, string Source, List<string> Paraphrases, [property: JsonPropertyName("ruleNumbers")] List<string> RuleNumbers,
        string Answer, string Explanation, List<string>? Keywords);
}
