namespace RiftBoundTracker.App.Services.Rules;

public sealed record RulesExplanationContext(string Question, List<RuleEvidence> Evidence, List<CardSummaryDto> CardContext);
public sealed record RulesGeneratedAnswer(string? Answer, bool Success, string? Error);

/// <summary>
/// The plain-language explanation layer sits behind this interface (architecture doc section 26)
/// so the deterministic evidence/ranking pipeline never depends on any specific AI provider — or
/// on AI being configured at all. Implementations only ever see the evidence this app already
/// retrieved; the final architectural rule (doc section 33) is that the AI explains evidence, it
/// never decides the rule on its own.
/// </summary>
public interface IRulesExplanationProvider
{
    bool IsConfigured { get; }
    Task<RulesGeneratedAnswer> ExplainAsync(RulesExplanationContext context, CancellationToken ct = default);
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
}
