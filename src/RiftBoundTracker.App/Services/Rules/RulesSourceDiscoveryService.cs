using RiftBoundTracker.App.Data;

namespace RiftBoundTracker.App.Services.Rules;

public sealed record RulesDiscoveryResult(
    List<DiscoveredRuleDocument> Documents, List<ParsedLegalityEntry> Legalities, DateTimeOffset? LegalityUpdatedAt);

/// <summary>
/// The single entry point into official Riftbound rules content: the Rules Hub page
/// (playriftbound.com/en-us/rules-hub/) that Riot themselves curate as the index of every current
/// rules document. This deliberately does not crawl anything beyond that one page — every document
/// it discovers (Core/Tournament Rules PDFs, Patch Notes articles, Errata articles, the two
/// Legality tables) is reachable directly from links on that page, so there's no need for (and
/// this app never builds) a generic recursive crawler that could wander into store pages, esports
/// content, or anything else non-rules.
/// </summary>
public sealed class RulesSourceDiscoveryService(NextJsArticlePageFetcher fetcher)
{
    private const string RulesHubUrl = "https://playriftbound.com/en-us/rules-hub/";

    public async Task<RulesDiscoveryResult> DiscoverAsync(CancellationToken ct = default)
    {
        var hub = await fetcher.FetchAsync(RulesHubUrl, ct)
            ?? throw new InvalidOperationException("Could not read the Riftbound Rules Hub page — its layout may have changed.");

        var parsed = RulesHubParser.Parse(hub.RichTextHtml);
        return new RulesDiscoveryResult(parsed.Documents, parsed.Legalities, parsed.LegalityUpdatedAt);
    }
}
