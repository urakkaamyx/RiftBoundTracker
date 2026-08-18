using System.Net.Http;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace RiftBoundTracker.App.Services.Rules;

public sealed record NextJsArticlePage(string Title, string RichTextHtml, DateTimeOffset? PublishedAt);

/// <summary>
/// playriftbound.com / riftbound.leagueoflegends.com are Next.js sites that embed their entire
/// page payload as server-rendered JSON in a &lt;script id="__NEXT_DATA__"&gt; tag — confirmed
/// during planning by fetching the real Rules Hub and an errata article directly. Reading that
/// JSON is far more reliable than scraping rendered DOM: every article-style page (Rules Hub,
/// Patch Notes, Errata) shares the same "masthead + articleRichText + related carousel" blade
/// shape, so this one fetcher covers all of them — only the richText.body HTML differs per page,
/// and that's handed off to a page-specific parser (RulesHubParser, ErrataArticleParser).
/// </summary>
public sealed partial class NextJsArticlePageFetcher(IHttpClientFactory httpClientFactory)
{
    public async Task<NextJsArticlePage?> FetchAsync(string url, CancellationToken ct)
    {
        var client = httpClientFactory.CreateClient("rules-source");
        var html = await client.GetStringAsync(url, ct);

        var match = NextDataRegex().Match(html);
        if (!match.Success) return null;

        using var doc = JsonDocument.Parse(match.Groups[1].Value);
        if (!doc.RootElement.TryGetProperty("props", out var props) ||
            !props.TryGetProperty("pageProps", out var pageProps) ||
            !pageProps.TryGetProperty("page", out var page))
            return null;

        var title = page.TryGetProperty("title", out var titleEl) ? titleEl.GetString() ?? "" : "";

        DateTimeOffset? publishedAt = null;
        if (page.TryGetProperty("analytics", out var analytics) &&
            analytics.TryGetProperty("publishDate", out var publishDateEl) &&
            DateTimeOffset.TryParse(publishDateEl.GetString(), out var parsedDate))
            publishedAt = parsedDate;

        if (!page.TryGetProperty("blades", out var blades)) return null;

        foreach (var blade in blades.EnumerateArray())
        {
            if (blade.TryGetProperty("type", out var bladeType) && bladeType.GetString() == "articleRichText" &&
                blade.TryGetProperty("richText", out var richText) &&
                richText.TryGetProperty("body", out var body))
            {
                return new NextJsArticlePage(title, body.GetString() ?? "", publishedAt);
            }
        }

        return null;
    }

    [GeneratedRegex("""<script id="__NEXT_DATA__"[^>]*>(.*?)</script>""", RegexOptions.Singleline)]
    private static partial Regex NextDataRegex();
}
