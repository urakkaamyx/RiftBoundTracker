namespace RiftBoundTracker.App.Services.Rules;

public sealed record RulesExplanationContext(
    string Question, List<RuleEvidence> Evidence, List<CardSummaryDto> CardContext, List<CardEvidence> CardNotes);
public sealed record RulesGeneratedAnswer(string? Answer, bool Success, string? Error);

// Adjudication stage — decides the ruling from evidence, produces no player-facing prose at all.
// CorrectionNote is set only on a retry (RulesAnswerService gives up after one), naming exactly
// what RulesAdjudicationValidator rejected about the previous attempt so the model can fix it
// instead of blindly retrying the same prompt.
public sealed record RulesAdjudicationContext(
    string Question, IReadOnlyList<CardSummaryDto> CardContext, IReadOnlyList<EvidenceRef> Evidence,
    string? CorrectionNote = null);
public sealed record RulesAdjudicationOutput(string? RawText, bool Success, string? Error);

// Explanation-of-an-already-decided-ruling stage — the counterpart to ExplainAsync above, but fed a
// validated RulesAdjudication instead of raw evidence, and explicitly told not to re-adjudicate it.
public sealed record RulesAdjudicatedExplanationContext(
    string Question, RulesAdjudication Adjudication, IReadOnlyList<EvidenceRef> Evidence, IReadOnlyList<CardSummaryDto> CardContext);

/// <summary>
/// The plain-language explanation layer sits behind this interface (architecture doc section 26)
/// so the deterministic evidence/ranking pipeline never depends on any specific AI provider — or
/// on AI being configured at all. Implementations only ever see the evidence this app already
/// retrieved; the final architectural rule (doc section 33) is that the AI explains evidence, it
/// never decides the rule on its own.
///
/// ExplainAsync (the original single-pass path: raw evidence in, prose out) is kept exactly as it
/// was, unmodified — it's the deliberate fallback RulesAnswerService uses whenever the newer
/// Adjudicate -> validate -> ExplainAdjudicationAsync sequence fails validation (even after one
/// retry), so a bad adjudication run degrades to today's known-working behavior instead of Ask
/// Rules producing no answer at all.
/// </summary>
public interface IRulesExplanationProvider
{
    bool IsConfigured { get; }
    Task<RulesGeneratedAnswer> ExplainAsync(RulesExplanationContext context, CancellationToken ct = default);
    Task<RulesAdjudicationOutput> AdjudicateAsync(RulesAdjudicationContext context, CancellationToken ct = default);
    Task<RulesGeneratedAnswer> ExplainAdjudicationAsync(RulesAdjudicatedExplanationContext context, CancellationToken ct = default);
}

/// <summary>
/// Default no-op implementation — Ask Rules must work fully without any AI configured (doc section
/// 27): "the deterministic rules library remains useful even without an API key." Registered as the
/// default so callers never need to null-check the provider itself.
/// </summary>
public sealed class NullRulesExplanationProvider : IRulesExplanationProvider
{
    public bool IsConfigured => false;
    public Task<RulesGeneratedAnswer> ExplainAsync(RulesExplanationContext context, CancellationToken ct = default) =>
        Task.FromResult(new RulesGeneratedAnswer(null, false, "No explanation provider configured."));
    public Task<RulesAdjudicationOutput> AdjudicateAsync(RulesAdjudicationContext context, CancellationToken ct = default) =>
        Task.FromResult(new RulesAdjudicationOutput(null, false, "No explanation provider configured."));
    public Task<RulesGeneratedAnswer> ExplainAdjudicationAsync(RulesAdjudicatedExplanationContext context, CancellationToken ct = default) =>
        Task.FromResult(new RulesGeneratedAnswer(null, false, "No explanation provider configured."));
}
