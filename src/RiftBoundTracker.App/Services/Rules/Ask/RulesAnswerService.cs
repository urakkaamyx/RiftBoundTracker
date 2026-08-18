namespace RiftBoundTracker.App.Services.Rules;

public sealed record RulesAskResponse(
    string Question, string? Answer, bool AnswerGenerated, string Confidence,
    List<DetectedKeywordDto> Keywords, List<DetectedConceptDto> Concepts, List<RuleCitationDto> Sources);

/// <summary>
/// Orchestrates one question end to end (architecture doc section 4): analyze -> gather evidence
/// -> decide confidence -> optionally explain. The confidence levels (doc section 18) are derived
/// from real, measured retrieval signals — never estimated by an LLM — because the whole point of
/// this architecture is that evidence quality, not AI confidence, drives the answer.
/// </summary>
public sealed class RulesAnswerService(
    RulesQuestionService questions, RulesEvidenceService evidenceService, IRulesExplanationProvider explanationProvider)
{
    public async Task<RulesAskResponse> AskAsync(string question, string? cardId, CancellationToken ct = default)
    {
        var analysis = await questions.AnalyzeAsync(question, cardId, ct);
        var evidence = await evidenceService.GatherAsync(analysis, currentOnly: true, limit: 12, ct);
        var confidence = DetermineConfidence(evidence, analysis);

        string? answer = null;
        var answerGenerated = false;
        if (evidence.Count > 0 && explanationProvider.IsConfigured)
        {
            var context = new RulesExplanationContext(question, evidence, analysis.CardContext);
            var generated = await explanationProvider.ExplainAsync(context, ct);
            if (generated.Success)
            {
                answer = generated.Answer;
                answerGenerated = true;
            }
        }

        return new RulesAskResponse(
            question, answer, answerGenerated, confidence,
            analysis.DetectedKeywords, analysis.DetectedConcepts, RulesCitationService.Format(evidence));
    }

    // High: an exact rule number resolved, or the question named exactly one official
    // keyword/concept and evidence answers it directly. Medium: the question named two or more
    // distinct official keywords/concepts — genuinely needed combining multiple rules. Low: only a
    // full-text fallback match, nothing the question explicitly named. InsufficientEvidence:
    // nothing came back at all. Deliberately counts what the QUESTION directly named
    // (analysis.DetectedKeywords / phrase-matched concepts), not every keyword evidence-gathering
    // pulled in — a concept like "Card State" pulls in sibling keywords (Exhaust's evidence also
    // surfaces Ready/Stun) as useful related context, but that shouldn't by itself downgrade "How
    // does Exhaust work?" from a clean single-concept question to a multi-concept one.
    private static string DetermineConfidence(List<RuleEvidence> evidence, RulesQuestionAnalysis analysis)
    {
        if (evidence.Count == 0) return "InsufficientEvidence";
        if (evidence.Any(e => e.MatchedVia.Any(v => v.StartsWith("rule number", StringComparison.Ordinal))))
            return "High";

        var directSignals = analysis.DetectedKeywords.Count
            + analysis.DetectedConcepts.Count(c => c.MatchedPhrase is not null);
        if (directSignals >= 2) return "Medium";
        if (directSignals == 1) return "High";

        return "Low";
    }
}
