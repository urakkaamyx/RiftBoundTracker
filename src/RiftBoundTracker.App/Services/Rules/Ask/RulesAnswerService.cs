namespace RiftBoundTracker.App.Services.Rules;

public sealed record RulesAskCitationDto(string RuleId, string? Family, string Text, string? SectionTitle);
public sealed record RulesAskCardDto(string Id, string Name, string? Text);

public sealed record RulesAskResponse(
    string Question, string? Answer, bool AnswerGenerated, string Confidence,
    List<string> ClarifyingQuestions, List<RulesAskCitationDto> Sources, List<RulesAskCardDto> CardNotes);

/// <summary>
/// Orchestrates one question end to end against the Rules Engine sidecar's Product API — no rules
/// logic lives here. Per the engine's own integration guide, this app "does not know how Riftbound
/// rules work"; it only calls /v1/ask, and separately calls /v1/cards/{id} for the one gap proven
/// directly against the real engine this session: a plain "what does this card do" question isn't
/// an adjudication template, so /v1/ask alone declines it even though the card's exact text is
/// sitting right there in its own namedCards evidence. RulesEvidenceService/RulesQuestionService/
/// RulesCuratedRulingService/RulesToolAgentProvider (the retrieval+LLM pipeline built earlier this
/// session) are retired entirely in favor of this — the fixes for that pipeline's real failures
/// (wrong retrieval, negation errors, hallucinated backwards reasoning) belong in the engine, not
/// worked around in C#.
/// </summary>
public sealed class RulesAnswerService(
    RulesEngineSidecarService sidecar, RulesEngineClient engine,
    RulesLocalAiSettingsService settings, ILogger<RulesAnswerService> logger)
{
    // The engine's own stable prefix for "no compiled adjudication template can prove this" —
    // confirmed directly this session across multiple uncompiled-family questions (Mobilize,
    // generic card lookups). Matching on this substring (not full equality) is deliberately the
    // same pragmatic pattern this app already used for detecting hedge/refusal language elsewhere
    // — robust to the engine wording shifting slightly across future releases.
    private const string DeterministicDeclinePrefix = "I can't determine this from the currently compiled deterministic rules";

    public async Task<RulesAskResponse> AskAsync(string question, string? cardId, CancellationToken ct = default)
    {
        if (!settings.IsEnabled())
            return new RulesAskResponse(question, null, false, "InsufficientEvidence", [], [], []);

        if (!await sidecar.EnsureRunningAsync(ct))
        {
            logger.LogWarning("Ask Rules: rules engine sidecar is not available");
            return new RulesAskResponse(question, null, false, "InsufficientEvidence", [], [], []);
        }

        // An explicit "Ask About This Card" flow already knows the card — skip straight to the
        // card API rather than round-tripping through /v1/ask for something already resolved.
        if (!string.IsNullOrWhiteSpace(cardId))
        {
            var direct = await engine.GetCardAsync(cardId, ct);
            return BuildCardResponse(question, direct);
        }

        var ask = await engine.AskAsync(question, ct);
        // Real testing caught a second decline shape beyond the documented prefix: for a topic
        // with no recognized keyword/rule lookup target at all ("Legend" isn't a rules-keyword the
        // engine indexes), it returns "ok": true with a genuinely empty answer string rather than
        // the "I can't determine..." text — a blank answer is just as much a non-answer as that
        // prefix is, and treating only the prefix as "declined" let this slip through as a
        // reported "High confidence" empty response.
        var declined = string.IsNullOrWhiteSpace(ask.Answer) || ask.Answer.StartsWith(DeterministicDeclinePrefix, StringComparison.Ordinal);
        logger.LogDebug("Ask Rules: /v1/ask ok={Ok} declined={Declined} namedCards={NamedCards} clarifying={Clarifying}",
            ask.Ok, declined, ask.NamedCards.Count, ask.ClarifyingQuestions.Count);
        if (declined && ask.NamedCards.Count == 1)
        {
            var cardLookup = await engine.GetCardAsync(ask.NamedCards[0].Id, ct);
            if (cardLookup.MatchCount >= 1)
                return BuildCardResponse(question, cardLookup);
        }

        if (declined)
        {
            // Only the prefixed decline text is worth showing as "the answer" — a genuinely blank
            // answer has nothing to display, so AnswerGenerated is false and the frontend shows
            // its own "no answer" note instead of an empty paragraph.
            var hasDeclineText = !string.IsNullOrWhiteSpace(ask.Answer);
            return new RulesAskResponse(
                question, hasDeclineText ? ask.Answer : null, hasDeclineText, "InsufficientEvidence",
                ask.ClarifyingQuestions, [], NamedCardsToNotes(ask.NamedCards));
        }

        return new RulesAskResponse(
            question, ask.Answer, true, "High", ask.ClarifyingQuestions, [], NamedCardsToNotes(ask.NamedCards));
    }

    private static RulesAskResponse BuildCardResponse(string question, CardLookupResult lookup)
    {
        if (lookup.MatchCount == 0)
            return new RulesAskResponse(question, null, false, "InsufficientEvidence", [], [], []);

        var card = lookup.Matches[0];
        var answer = $"{card.Name} ({card.SetId}-{card.CollectorCode}, {card.Type}): {card.EffectiveText}";
        var note = new RulesAskCardDto(card.Id, card.Name, card.EffectiveText);
        // A card's own printed text, not a proof-verified ruling about an interaction — "Medium"
        // reflects that distinction honestly rather than claiming the same certainty as a fully
        // adjudicated verdict.
        return new RulesAskResponse(question, answer, true, "Medium", [], [], [note]);
    }

    private static List<RulesAskCardDto> NamedCardsToNotes(List<EngineNamedCard> namedCards) =>
        namedCards.Select(c => new RulesAskCardDto(c.Id, c.Name, c.EffectiveText)).ToList();
}
