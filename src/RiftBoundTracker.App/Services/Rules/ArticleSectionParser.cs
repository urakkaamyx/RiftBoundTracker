using HtmlAgilityPack;
using HtmlDocument = HtmlAgilityPack.HtmlDocument;

namespace RiftBoundTracker.App.Services.Rules;

/// <summary>
/// Generic heading-delimited article parser for content that has no official rule numbering
/// (Patch Notes) — each h1-h4 heading becomes one searchable ParsedRule (Title = heading, Text =
/// the following paragraphs up to the next heading), so a Patch Notes article still shows up in
/// search results scoped to the specific topic instead of one giant undifferentiated blob.
/// </summary>
public static class ArticleSectionParser
{
    public static List<ParsedRule> Parse(string richTextHtml, string fallbackTitle)
    {
        var sections = new List<ParsedRule>();
        var doc = new HtmlDocument();
        doc.LoadHtml(richTextHtml);

        string? currentTitle = null;
        var parts = new List<string>();
        var sortOrder = 0;

        void Flush()
        {
            var text = string.Join("\n\n", parts.Where(p => p.Length > 0)).Trim();
            if (text.Length > 0)
            {
                sections.Add(new ParsedRule
                {
                    RuleNumber = null,
                    Title = currentTitle ?? fallbackTitle,
                    Text = text,
                    SortOrder = sortOrder++,
                });
            }
            parts = [];
        }

        foreach (var node in doc.DocumentNode.ChildNodes)
        {
            if (node.Name is "h1" or "h2" or "h3" or "h4")
            {
                Flush();
                currentTitle = HtmlEntity.DeEntitize(node.InnerText).Trim();
                continue;
            }

            var text = HtmlEntity.DeEntitize(node.InnerText).Trim();
            if (text.Length > 0) parts.Add(text);
        }

        Flush();
        return sections;
    }
}
