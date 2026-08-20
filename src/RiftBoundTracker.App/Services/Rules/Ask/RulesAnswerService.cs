namespace RiftBoundTracker.App.Services.Rules;

public sealed record RulesAskResponse(
    string Question, string? Answer, bool AnswerGenerated, string Confidence,
    List<DetectedKeywordDto> Keywords, List<DetectedConceptDto> Concepts, List<RuleCitationDto> Sources,
    List<CardEvidence> CardNotes);

/// <summary>
/// Orchestrates one question end to end (architecture doc section 4): analyze -> gather evidence
/// -> decide confidence -> optionally explain. The confidence levels (doc section 18) are derived
/// from real, measured retrieval signals — never estimated by an LLM — because the whole point of
/// this architecture is that evidence quality, not AI confidence, drives the answer.
/// </summary>
public sealed class RulesAnswerService(
    RulesQuestionService questions, RulesEvidenceService evidenceService, IRulesExplanationProvider explanationProvider,
    ILogger<RulesAnswerService> logger)
{
    // The adjudicate -> validate -> explain pipeline is built, wired, and hardened (repeat-penalty
    // fix, anti-example-copying instructions, semantic grounding check) but is being kept OFF the hot
    // path for now based on real measurement, not guesswork: run against the actual resident model
    // (Qwen2.5-1.5B, fine-tuned only on the single-pass ExplainAsync shape), it validated on 1 of 14
    // real attempts across 7 test questions — and that one success turned out to be a hallucinated
    // question the grounding check now correctly rejects, so its real success rate on this model is
    // effectively zero. Every attempt still costs two full inference calls (~30-60s each) before
    // falling back, which would roughly double-to-triple every Ask Rules question's latency for no
    // realized benefit. Flip this to true once a model actually fine-tuned on the adjudication output
    // shape is trained and shipped (scripts/training/generate_dataset.py would need a new category
    // for it first — out of scope for this pass, which only fixed that script's existing drift).
    // static readonly, not const — a const bool makes the compiler treat the disabled branch below
    // as statically unreachable (CS0162), which it isn't: this is a runtime-flippable switch.
    private static readonly bool AdjudicationPipelineEnabled = false;

    public async Task<RulesAskResponse> AskAsync(string question, string? cardId, CancellationToken ct = default)
    {
        var analysis = await questions.AnalyzeAsync(question, cardId, ct);
        var result = await evidenceService.GatherAsync(analysis, currentOnly: true, limit: 16, ct);
        var confidence = DetermineConfidence(result, analysis);

        string? answer = null;
        var answerGenerated = false;
        if ((result.Rules.Count > 0 || result.Cards.Count > 0) && explanationProvider.IsConfigured)
        {
            if (AdjudicationPipelineEnabled)
            {
                var evidenceRefs = EvidenceIdMapper.Build(result.Rules, result.Cards);
                logger.LogDebug("Ask Rules: assigned {Count} evidence ids for {Question}", evidenceRefs.Count, question);

                var adjudication = await TryAdjudicateAsync(question, analysis.CardContext, evidenceRefs, ct);
                if (adjudication is not null)
                {
                    var explainContext = new RulesAdjudicatedExplanationContext(question, adjudication, evidenceRefs, analysis.CardContext);
                    var generated = await explanationProvider.ExplainAdjudicationAsync(explainContext, ct);
                    logger.LogDebug("Ask Rules: adjudicated explanation success={Success} error={Error} raw={Raw}",
                        generated.Success, generated.Error, generated.Answer);
                    if (generated.Success)
                    {
                        answer = generated.Answer;
                        answerGenerated = true;
                    }
                }
            }

            // Fallback to the original single-pass path whenever adjudication is disabled, never
            // validated (even after a retry), or the adjudicated-explanation call itself failed — Ask
            // Rules must never regress to no answer at all because the newer pipeline had a bad run.
            if (!answerGenerated)
            {
                var context = new RulesExplanationContext(question, result.Rules, analysis.CardContext, result.Cards);
                var generated = await explanationProvider.ExplainAsync(context, ct);
                logger.LogDebug("Ask Rules: fallback single-pass explanation success={Success} error={Error}",
                    generated.Success, generated.Error);
                if (generated.Success)
                {
                    answer = generated.Answer;
                    answerGenerated = true;
                }
            }
        }

        return new RulesAskResponse(
            question, answer, answerGenerated, confidence,
            analysis.DetectedKeywords, analysis.DetectedConcepts, RulesCitationService.Format(result.Rules), result.Cards);
    }

    // Up to one retry: the first attempt gets the plain evidence packet, a failed attempt's specific
    // validation error is fed back as CorrectionNote so the retry can actually fix it rather than
    // blindly repeating the same prompt. Two failures in a row means AskAsync falls back to ExplainAsync.
    private async Task<RulesAdjudication?> TryAdjudicateAsync(
        string question, List<CardSummaryDto> cardContext, IReadOnlyList<EvidenceRef> evidenceRefs, CancellationToken ct)
    {
        string? correctionNote = null;
        for (var attempt = 1; attempt <= 2; attempt++)
        {
            var context = new RulesAdjudicationContext(question, cardContext, evidenceRefs, correctionNote);
            var output = await explanationProvider.AdjudicateAsync(context, ct);
            logger.LogDebug("Ask Rules: adjudication attempt {Attempt} success={Success} error={Error} raw={Raw}",
                attempt, output.Success, output.Error, output.RawText);
            if (!output.Success || output.RawText is null)
            {
                correctionNote = "Your previous attempt returned no usable output.";
                continue;
            }

            var validated = RulesAdjudicationValidator.ParseAndValidate(output.RawText, evidenceRefs, question);
            logger.LogDebug("Ask Rules: adjudication validation attempt {Attempt} success={Success} error={Error}",
                attempt, validated.Success, validated.Error);
            if (validated.Success) return validated.Adjudication;
            correctionNote = validated.Error;
        }
        return null;
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
    private static string DetermineConfidence(RulesEvidenceResult result, RulesQuestionAnalysis analysis)
    {
        if (result.Rules.Count == 0 && result.Cards.Count == 0) return "InsufficientEvidence";
        if (result.Rules.Any(e => e.MatchedVia.Any(v => v.StartsWith("rule number", StringComparison.Ordinal))))
            return "High";
        // An exact card-name match (legality/errata) is as direct a hit as a rule number — the
        // question named a specific card and evidence answers it about that exact card.
        if (result.Cards.Count > 0) return "High";

        var directSignals = analysis.DetectedKeywords.Count
            + analysis.DetectedConcepts.Count(c => c.MatchedPhrase is not null);
        if (directSignals >= 2) return "Medium";
        if (directSignals == 1) return "High";

        return "Low";
    }
}
