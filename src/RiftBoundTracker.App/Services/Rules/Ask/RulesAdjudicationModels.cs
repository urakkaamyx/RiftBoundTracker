namespace RiftBoundTracker.App.Services.Rules;

// Assigns stable "E1, E2, ..." identifiers to evidence the retrieval step already found, so the
// adjudicator can cite evidence without ever typing a rule number itself — the model references
// "E3", the backend resolves E3 back to the real rule/card. This is the hard boundary against
// hallucinated citations: an EvidenceId that isn't in this map is rejected by
// RulesAdjudicationValidator, never silently rendered as if it were real.
public sealed record EvidenceRef(string Id, string Label, string Authority, bool Current, string FullText);

public sealed record RulesAdjudicatedIssue(
    string Question, string Answer, string Reason, IReadOnlyList<string> EvidenceIds);

// Internal-only — never returned to the frontend as-is. The player-facing text is what
// LocalLlmExplanationProvider.ExplainAsync produces from this once it's been validated.
public sealed record RulesAdjudication(
    string OverallVerdict, IReadOnlyList<RulesAdjudicatedIssue> Issues, IReadOnlyList<string> MissingInformation);

/// <summary>
/// Builds the stable evidence-ID list once per question, shared by the adjudication prompt (which
/// cites only E&lt;n&gt; tokens), the validator (which checks every cited id actually exists here),
/// and the explanation prompt (which quotes FullText for only the ids the adjudicator actually used).
/// </summary>
public static class EvidenceIdMapper
{
    public static IReadOnlyList<EvidenceRef> Build(List<RuleEvidence> rules, List<CardEvidence> cards)
    {
        var refs = new List<EvidenceRef>();
        var n = 1;
        // Card evidence first, matching BuildUserMessage's own ordering rationale (LocalLlm-
        // ExplanationProvider.cs) — a question about a specific card must never lose the budget/
        // attention race to general rule evidence just because there's more of it.
        foreach (var c in cards)
            refs.Add(new EvidenceRef($"E{n++}", $"{c.CardName} ({c.Authority})", c.Authority, true, c.Note));
        foreach (var r in rules)
        {
            var label = r.Hit.RuleNumber is not null ? $"Rule {r.Hit.RuleNumber}" : r.Hit.Title;
            refs.Add(new EvidenceRef($"E{n++}", label, r.Hit.Document.Authority, r.Hit.Document.Current, r.Hit.FullText));
        }
        return refs;
    }
}
