using System.Text.RegularExpressions;
using HtmlAgilityPack;
using HtmlDocument = HtmlAgilityPack.HtmlDocument;
using RiftBoundTracker.App.Data;

namespace RiftBoundTracker.App.Services.Rules;

public sealed record RulesHubParseResult(
    List<DiscoveredRuleDocument> Documents, List<ParsedLegalityEntry> Legalities, DateTimeOffset? LegalityUpdatedAt);

/// <summary>
/// Parses the Rules Hub's richText.body HTML fragment — confirmed during planning to be a flat
/// run of &lt;h3&gt; section headings (Core Rules, Tournament Rules, Patch Notes, Errata, two
/// Legality sections) each followed by siblings up to the next heading. This is the app's
/// RulesSourceDiscoveryService: it doesn't recursively crawl anything, it just reads the one page
/// Riot themselves curate as the entry point for every other rules document.
/// </summary>
public static partial class RulesHubParser
{
    public static RulesHubParseResult Parse(string richTextHtml)
    {
        var documents = new List<DiscoveredRuleDocument>();
        var legalities = new List<ParsedLegalityEntry>();
        DateTimeOffset? legalityUpdatedAt = null;

        var doc = new HtmlDocument();
        doc.LoadHtml(richTextHtml);

        var headings = doc.DocumentNode.SelectNodes("//h3");
        if (headings is null) return new RulesHubParseResult(documents, legalities, legalityUpdatedAt);

        foreach (var heading in headings)
        {
            var headingText = HtmlEntity.DeEntitize(heading.InnerText).Trim();
            var section = CollectUntilNextHeading(heading);

            if (headingText.Equals("Core Rules", StringComparison.OrdinalIgnoreCase))
            {
                var found = FindPdfDocument(section, RuleSourceType.CoreRules, headingText);
                if (found is not null) documents.Add(found);
            }
            else if (headingText.Equals("Tournament Rules", StringComparison.OrdinalIgnoreCase))
            {
                var found = FindPdfDocument(section, RuleSourceType.TournamentRules, headingText);
                if (found is not null) documents.Add(found);
            }
            else if (headingText.Equals("Patch Notes", StringComparison.OrdinalIgnoreCase))
            {
                documents.AddRange(FindLinkedArticles(section, RuleSourceType.PatchNotes));
            }
            else if (headingText.Equals("Errata", StringComparison.OrdinalIgnoreCase))
            {
                documents.AddRange(FindLinkedArticles(section, RuleSourceType.Errata));
            }
            else if (headingText.Contains("Legality", StringComparison.OrdinalIgnoreCase))
            {
                var format = DeriveFormat(headingText);
                var updated = ExtractUpdatedDate(section);
                if (updated is not null) legalityUpdatedAt = updated;
                legalities.AddRange(ParseLegalityTable(section, format));
            }
        }

        return new RulesHubParseResult(documents, legalities, legalityUpdatedAt);
    }

    private static List<HtmlNode> CollectUntilNextHeading(HtmlNode heading)
    {
        var nodes = new List<HtmlNode>();
        var node = heading.NextSibling;
        while (node is not null && node.Name != "h3")
        {
            nodes.Add(node);
            node = node.NextSibling;
        }
        return nodes;
    }

    private static DiscoveredRuleDocument? FindPdfDocument(List<HtmlNode> section, RuleSourceType type, string title)
    {
        foreach (var node in section)
        {
            var anchor = node.Name == "a" ? node : node.SelectSingleNode(".//a[contains(@href, '.pdf')]");
            if (anchor?.GetAttributeValue("href", null) is not { } href || !href.Contains(".pdf")) continue;

            var context = HtmlEntity.DeEntitize(node.InnerText);
            var versionText = ExtractUpdatedDate(context, out var versionRaw) is { } parsed
                ? (DateTimeOffset?)parsed
                : null;

            return new DiscoveredRuleDocument
            {
                SourceType = type,
                Title = title,
                SourceUrl = href,
                DownloadUrl = href,
                DocumentVersionText = versionRaw,
                PublishedAt = versionText,
            };
        }
        return null;
    }

    private static IEnumerable<DiscoveredRuleDocument> FindLinkedArticles(List<HtmlNode> section, RuleSourceType type)
    {
        var anchors = section
            .SelectMany(n => (IEnumerable<HtmlNode>?)n.SelectNodes(".//li//a") ?? [])
            .Where(a => !string.IsNullOrWhiteSpace(a.GetAttributeValue("href", null)));

        foreach (var anchor in anchors)
        {
            yield return new DiscoveredRuleDocument
            {
                SourceType = type,
                Title = HtmlEntity.DeEntitize(anchor.InnerText).Trim(),
                SourceUrl = anchor.GetAttributeValue("href", ""),
            };
        }
    }

    private static List<ParsedLegalityEntry> ParseLegalityTable(List<HtmlNode> section, string format)
    {
        var entries = new List<ParsedLegalityEntry>();
        foreach (var table in section.SelectMany(n => (IEnumerable<HtmlNode>?)n.SelectNodes(".//table") ?? []))
        {
            foreach (var cell in table.SelectNodes(".//td") ?? Enumerable.Empty<HtmlNode>())
            {
                // Each <td> is one category ("Cards" / "Battlefields" / "Legends") — the heading
                // text isn't used for anything except confirming this cell is a real category,
                // since every name in every cell of a legality table means the same thing: banned.
                var items = cell.SelectNodes(".//li");
                if (items is null) continue;
                foreach (var item in items)
                {
                    var name = HtmlEntity.DeEntitize(item.InnerText).Trim();
                    if (name.Length == 0) continue;
                    entries.Add(new ParsedLegalityEntry { CardNameRaw = name, Format = format, Status = CardLegalityStatus.Banned });
                }
            }
        }
        return entries;
    }

    private static string DeriveFormat(string headingText)
    {
        var text = LegalitySuffix().Replace(headingText, "").Trim();
        text = FormatSuffix().Replace(text, "").Trim();
        return text;
    }

    private static DateTimeOffset? ExtractUpdatedDate(List<HtmlNode> section)
    {
        var text = string.Join(" ", section.Select(n => HtmlEntity.DeEntitize(n.InnerText)));
        return ExtractUpdatedDate(text, out _);
    }

    private static DateTimeOffset? ExtractUpdatedDate(string text, out string? raw)
    {
        var match = LastUpdatedPattern().Match(text);
        if (!match.Success)
        {
            raw = null;
            return null;
        }
        raw = match.Groups[1].Value.Trim();
        return DateTimeOffset.TryParse(raw, out var parsed) ? parsed : null;
    }

    [GeneratedRegex(@"Legality\s*$", RegexOptions.IgnoreCase)]
    private static partial Regex LegalitySuffix();

    [GeneratedRegex(@"\bFormat\s*$", RegexOptions.IgnoreCase)]
    private static partial Regex FormatSuffix();

    [GeneratedRegex(@"Last updated:?\s*([A-Za-z]+ \d{1,2},? \d{4})", RegexOptions.IgnoreCase)]
    private static partial Regex LastUpdatedPattern();
}
