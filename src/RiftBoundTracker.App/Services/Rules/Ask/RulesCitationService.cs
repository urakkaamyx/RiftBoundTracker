namespace RiftBoundTracker.App.Services.Rules;

public sealed record RuleCitationDto(int RuleId, string? RuleNumber, string Title, string Snippet, string Document, string Authority, bool Current, List<string> MatchedVia);

/// <summary>
/// Formats retrieved evidence into the response shape a client renders as "Why?" / sources
/// (architecture doc section 16/20) — a pure formatter, no retrieval logic of its own.
/// </summary>
public static class RulesCitationService
{
    public static List<RuleCitationDto> Format(List<RuleEvidence> evidence) => evidence
        .Select(e => new RuleCitationDto(
            e.Hit.RuleId, e.Hit.RuleNumber, e.Hit.Title, e.Hit.Snippet, e.Hit.Document.Title, e.Hit.Document.Authority, e.Hit.Document.Current, e.MatchedVia))
        .ToList();
}
