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
    RulesCuratedRulingService curatedRulings, RulesToolAgentProvider toolAgent, ILogger<RulesAnswerService> logger)
{
    // The adjudicate -> validate -> explain pipeline is built, wired, and hardened (repeat-penalty
    // fix, anti-example-copying instructions, semantic grounding check, explanation-fidelity check)
    // but is kept OFF the hot path based on real measurement across four separate fine-tuning rounds
    // on a Qwen3-1.7B model dedicated to this exact task shape (scripts/training/generate_adjudication
    // _dataset.py) — each round fixed some real-question failures and introduced different ones
    // without the overall pass rate ever climbing, the signature of a real capability ceiling for a
    // model this size on genuine multi-step rules reasoning, not something one more round fixes.
    // RulesCuratedRulingService (checked below, before this) is the actual fix: for the class of
    // question that has a knowable answer, C# now determines that answer directly from a verified
    // lookup table, and the model's only remaining job is questions that table doesn't cover — which
    // this flag still routes to the single-pass ExplainAsync fallback rather than the LLM-driven
    // adjudicator, since that fallback has no exposure to this task's specific failure modes.
    // static readonly, not const — a const bool makes the compiler treat the disabled branch below
    // as statically unreachable (CS0162), which it isn't: this is a runtime-flippable switch, worth
    // revisiting if a future model is actually reliable at this specific task.
    private static readonly bool AdjudicationPipelineEnabled = false;

    public async Task<RulesAskResponse> AskAsync(string question, string? cardId, CancellationToken ct = default)
    {
        var analysis = await questions.AnalyzeAsync(question, cardId, ct);
        var result = await evidenceService.GatherAsync(analysis, currentOnly: true, limit: 16, ct);
        var confidence = DetermineConfidence(result, analysis);

        string? answer = null;
        var answerGenerated = false;

        // Checked before any LLM call, not as a fallback after one fails — see
        // RulesCuratedRulingService's own doc comment for why. A match here means the ruling is
        // already known and verified; the model doesn't get a turn to second-guess it.
        var curated = curatedRulings.TryMatch(question);
        if (curated is not null)
        {
            logger.LogDebug("Ask Rules: curated ruling {Id} matched — skipping the LLM pipeline entirely", curated.Id);
            answer = curated.Explanation;
            answerGenerated = true;
            confidence = "High";
        }
        else if (toolAgent.IsConfigured)
        {
            // No curated match — hand the model the same deterministic evidence RulesEvidenceService
            // already gathered above (also used for Sources/Confidence display below regardless of
            // which path answers the question). The model reasons over this; it doesn't get to
            // invent its own search terms — see RulesToolAgentProvider's own doc comment for why.
            var evidenceRefs = EvidenceIdMapper.Build(result.Rules, result.Cards);
            var toolAnswer = await toolAgent.AnswerAsync(question, evidenceRefs, ct);
            logger.LogDebug("Ask Rules (tools): success={Success} error={Error}", toolAnswer.Success, toolAnswer.Error);
            if (toolAnswer.Success)
            {
                answer = toolAnswer.Answer;
                answerGenerated = true;
            }
        }

        if (!answerGenerated && (result.Rules.Count > 0 || result.Cards.Count > 0) && explanationProvider.IsConfigured)
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
                    var faithful = !generated.Success || generated.Answer is null
                        || IsExplanationFaithfulToVerdict(adjudication.OverallVerdict, generated.Answer);
                    logger.LogDebug("Ask Rules: adjudicated explanation success={Success} faithfulToVerdict={Faithful} error={Error} raw={Raw}",
                        generated.Success, faithful, generated.Error, generated.Answer);
                    if (generated.Success && faithful)
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

    // Caught directly in testing: ExplainAdjudicationAsync is explicitly told "THE RULING BELOW HAS
    // ALREADY BEEN DETERMINED — do not re-adjudicate it, do not change any Yes/No/Insufficient
    // answer given" — and did exactly that anyway on a real question. Adjudication correctly ruled
    // "No" with correct reasoning and passed validation cleanly; the explanation stage then quietly
    // re-decided the question and shipped "we don't know" instead. RulesAdjudicationValidator only
    // checks the adjudication output — nothing previously checked that the explanation it produces
    // still agrees with the verdict it was handed. This is a blunt, string-based check, not a
    // semantic one: if the verdict was a real ruling (not already "Insufficient evidence") but the
    // explanation reads like a refusal, treat the explanation as failed so AskAsync falls through to
    // the existing single-pass fallback rather than shipping a self-contradicting answer.
    private static readonly string[] HedgePhrases =
    [
        "doesn't establish", "does not establish", "don't have rules evidence", "don't have evidence",
        "no rules evidence", "can't say for sure", "cannot say for sure", "can't guess", "cannot guess",
        "no idea", "unknown issue", "is unknown", "not covered by the supplied evidence",
        "isn't covered by", "is not covered by", "we don't know", "we do not know", "i don't know",
        "i do not know", "that's also unknown", "is also unknown",
    ];

    private static bool IsExplanationFaithfulToVerdict(string verdict, string explanation)
    {
        if (verdict.Contains("Insufficient", StringComparison.OrdinalIgnoreCase)) return true;
        return !HedgePhrases.Any(phrase => explanation.Contains(phrase, StringComparison.OrdinalIgnoreCase));
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
