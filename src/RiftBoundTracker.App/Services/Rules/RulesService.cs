namespace RiftBoundTracker.App.Services.Rules;

public sealed record CardErrataDto(string? OriginalText, string? CorrectedText);
public sealed record CardRulesDto(List<CardErrataDto> Errata);

/// <summary>
/// Card-side "browse rules" lookups, backed by the Rules Engine sidecar's card API — card IDs
/// already match between this app's catalog and the engine's (e.g. "ogn-134-298"), so this maps
/// cleanly with no identity-scheme change needed.
///
/// The rule/keyword-side browsing this class used to serve (rule detail pages, the keyword
/// glossary list, document list — see git history) is NOT migrated here. Those pages are built
/// around internal integer RuleEntry/Keyword IDs with parent/child/previous/next navigation baked
/// into the frontend; the engine's rule IDs are strings that are the actual rule numbers ("815",
/// "815.1"), a different identity scheme entirely. Re-pointing them at the sidecar needs frontend
/// routing changes, not just a backend swap — real, separate follow-up work, deliberately not
/// rushed through as a side effect of the Ask Rules integration.
/// </summary>
public sealed class RulesService(RulesEngineClient engine)
{
    public async Task<CardRulesDto> GetCardRulesAsync(string cardId, CancellationToken ct = default)
    {
        var lookup = await engine.GetCardAsync(cardId, ct);
        if (lookup.MatchCount == 0) return new CardRulesDto([]);

        var card = lookup.Matches[0];
        var errata = (card.OfficialErrataTimeline ?? [])
            .Select(e => new CardErrataDto(
                e.TryGetProperty("originalText", out var o) ? o.GetString() : null,
                e.TryGetProperty("correctedText", out var c) ? c.GetString() : null))
            .ToList();

        return new CardRulesDto(errata);
    }
}
