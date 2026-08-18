using HtmlAgilityPack;
using HtmlDocument = HtmlAgilityPack.HtmlDocument;

namespace RiftBoundTracker.App.Services.Rules;

/// <summary>
/// Parses one errata article's richText.body HTML — confirmed during planning to follow a
/// consistent pattern across all four current errata articles: an "h1" per set, an "h2" per card,
/// then a "[NEW TEXT]" paragraph block, a "▲" divider, and an "[OLD TEXT]" paragraph block, with an
/// "hr" between cards. Cards whose article deviates from this shape (an older/differently
/// templated page) simply produce no entries for that card rather than a malformed one — errata
/// entries are never fabricated or guessed from partial matches.
/// </summary>
public static class ErrataArticleParser
{
    private enum Mode { None, New, Old }

    public static List<ParsedErrataEntry> Parse(string richTextHtml)
    {
        var entries = new List<ParsedErrataEntry>();
        var doc = new HtmlDocument();
        doc.LoadHtml(richTextHtml);

        string? currentCard = null;
        var mode = Mode.None;
        var newParts = new List<string>();
        var oldParts = new List<string>();

        void Flush()
        {
            if (currentCard is not null && (newParts.Count > 0 || oldParts.Count > 0))
            {
                entries.Add(new ParsedErrataEntry
                {
                    CardNameRaw = currentCard,
                    CorrectedText = newParts.Count > 0 ? string.Join("\n", newParts) : null,
                    OriginalText = oldParts.Count > 0 ? string.Join("\n", oldParts) : null,
                });
            }
            newParts = [];
            oldParts = [];
            mode = Mode.None;
        }

        foreach (var node in doc.DocumentNode.ChildNodes)
        {
            switch (node.Name)
            {
                case "h1":
                    Flush();
                    currentCard = null; // a set-name heading, not a card
                    break;

                case "h2":
                    Flush();
                    currentCard = HtmlEntity.DeEntitize(node.InnerText).Trim();
                    break;

                case "hr":
                    Flush();
                    break;

                case "p":
                    var text = HtmlEntity.DeEntitize(node.InnerText).Trim();
                    if (text.Length == 0 || text == "▲") break;

                    if (text.StartsWith("[NEW TEXT]", StringComparison.OrdinalIgnoreCase) ||
                        text.Equals("NEW TEXT", StringComparison.OrdinalIgnoreCase))
                    {
                        mode = Mode.New;
                        break;
                    }
                    if (text.StartsWith("[OLD TEXT]", StringComparison.OrdinalIgnoreCase) ||
                        text.Equals("OLD TEXT", StringComparison.OrdinalIgnoreCase))
                    {
                        mode = Mode.Old;
                        break;
                    }

                    switch (mode)
                    {
                        case Mode.New: newParts.Add(text); break;
                        case Mode.Old: oldParts.Add(text); break;
                    }
                    break;
            }
        }

        Flush();
        return entries;
    }
}
