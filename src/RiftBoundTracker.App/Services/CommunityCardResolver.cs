namespace RiftBoundTracker.App.Services;

public enum CardResolution { Resolved, Unresolved }

public record CardResolutionResult(CardResolution Status, string? CardId);

/// <summary>
/// TopDeck.gg card ids are already in this app's "{SetId}-{CollectorCode}" format — confirmed
/// during planning against a real 180-day pull (100% resolution across 83,000+ card references),
/// so resolution is a direct split on the first hyphen into a CardCacheService lookup rather than
/// fuzzy/name-based matching. Falls back to Unresolved (never a guess) when the id doesn't
/// decompose or the local lookup doesn't return exactly one match.
/// </summary>
public sealed class CommunityCardResolver(CardCacheService cache)
{
    public async Task<CardResolutionResult> ResolveAsync(string providerId, CancellationToken ct = default)
    {
        var dash = providerId.IndexOf('-');
        if (dash <= 0 || dash == providerId.Length - 1)
            return new CardResolutionResult(CardResolution.Unresolved, null);

        var setId = providerId[..dash];
        var code = providerId[(dash + 1)..];
        var cards = await cache.FindByCodeAsync(setId, code, ct);
        return cards.Count == 1
            ? new CardResolutionResult(CardResolution.Resolved, cards[0].Id)
            : new CardResolutionResult(CardResolution.Unresolved, null);
    }
}
