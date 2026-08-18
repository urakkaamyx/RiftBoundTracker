using System.Text.RegularExpressions;
using UglyToad.PdfPig;
using UglyToad.PdfPig.DocumentLayoutAnalysis.TextExtractor;

namespace RiftBoundTracker.App.Services.Rules;

/// <summary>
/// Parses the Core Rules / Tournament Rules PDFs — both use the identical numbering scheme
/// (confirmed during planning against the real documents: "103.", "103.2.", "103.2.b.",
/// "103.2.b.1." etc., each alone on its own line with its rule text on the following line(s),
/// occasionally with the first line of text on the same line as the number itself). One shared
/// parser covers both; only the resulting RuleAuthority differs, which the caller sets based on
/// which document this came from.
///
/// PdfPig's raw Page.Text joins every word on a page with plain spaces and drops line breaks
/// entirely, which is useless for a parser that depends on rule numbers starting their own line —
/// ContentOrderTextExtractor reconstructs real reading-order lines instead (verified directly
/// against the actual PDF during planning: its output matches a reference Python/PyMuPDF
/// extraction of the same document line-for-line).
/// </summary>
public static partial class RulesPdfParser
{
    public static List<ParsedRule> Parse(byte[] pdfBytes)
    {
        using var document = PdfDocument.Open(pdfBytes);
        var lines = new List<string>();
        foreach (var page in document.GetPages())
            lines.AddRange(ContentOrderTextExtractor.GetText(page).Split('\n'));

        return ParseLines(lines);
    }

    internal static List<ParsedRule> ParseLines(List<string> rawLines)
    {
        var lines = rawLines.Select(NormalizeLine).ToList();
        var rules = new List<ParsedRule>();
        // A cross-reference like "...listed in 704. Engaging in unsporting conduct may..." can
        // wrap so the referenced number lands alone at the start of a line — indistinguishable
        // from a genuine new rule marker by shape alone (confirmed against the real Tournament
        // Rules PDF). Rather than trying to enumerate every English phrasing that can precede a
        // reference ("see", "listed in", "described in", ...), this corpus has zero legitimate
        // duplicate rule numbers (verified against the full real document), so once a number has
        // been used by a genuine rule, any later line that merely looks like that same marker is
        // necessarily a citation, not a new definition — its line folds into whatever rule is
        // currently accumulating instead of starting a new one.
        var seenNumbers = new HashSet<string>();
        var sortOrder = 0;
        var i = 0;

        while (i < lines.Count)
        {
            var line = lines[i].Trim();
            var marker = RuleNumberLine().Match(line);
            if (!marker.Success || seenNumbers.Contains(marker.Groups[1].Value)) { i++; continue; }

            var number = marker.Groups[1].Value;
            seenNumbers.Add(number);
            var inlineText = marker.Groups[2].Value.Trim();
            i++;

            var contentParts = new List<string>();
            if (inlineText.Length > 0) contentParts.Add(inlineText);

            var pendingParagraphBreak = false;
            while (i < lines.Count)
            {
                var next = lines[i].Trim();
                if (next.Length == 0) { pendingParagraphBreak = true; i++; continue; }
                var nextMarker = RuleNumberLine().Match(next);
                if (nextMarker.Success && !seenNumbers.Contains(nextMarker.Groups[1].Value)) break;

                contentParts.Add(pendingParagraphBreak && contentParts.Count > 0 ? "\n\n" + next : next);
                pendingParagraphBreak = false;
                i++;
            }

            var text = string.Join(" ", contentParts).Replace(" \n\n", "\n\n").Trim();
            if (text.Length == 0) continue; // a bare number with no content anywhere (shouldn't happen, but never emit an empty rule)

            var isHeading = text.Length <= 60 && !text.Contains('\n') && !EndsSentence(text);

            var rule = new ParsedRule
            {
                RuleNumber = number,
                Title = isHeading ? text.TrimEnd(':').Trim() : null,
                Text = text,
                SortOrder = sortOrder++,
            };
            foreach (Match refMatch in CrossReferencePattern().Matches(text))
                rule.ExplicitReferenceNumbers.Add(refMatch.Groups[1].Value);

            rules.Add(rule);
        }

        return rules;
    }

    private static bool EndsSentence(string text) =>
        text.EndsWith('.') || text.EndsWith('?') || text.EndsWith('!');

    // PdfPig's word extraction preserves ligature glyphs ("battleﬁelds", "ﬁrst") as single
    // characters instead of decomposing them — fine visually, but breaks plain-text FTS matching
    // against a search for "field" or "first", so they're expanded back out here.
    private static string NormalizeLine(string line) => line
        .Replace("ﬀ", "ff")
        .Replace("ﬁ", "fi")
        .Replace("ﬂ", "fl")
        .Replace("ﬃ", "ffi")
        .Replace("ﬄ", "ffl")
        .TrimEnd('\r');

    // A rule-number marker: digit/letter components separated by dots, terminated by a literal
    // dot, alone at the start of a line — optionally with the rule's own first line of text
    // immediately following on the same line (e.g. "000. Golden and Silver Rules"). The top-level
    // component must be 3+ digits (every real top-level number in both documents is, e.g. "000",
    // "173", "829") specifically to reject the rare false positive where a sentence wraps with a
    // small in-text number like "...draw 2." landing alone at the start of a line, which would
    // otherwise look identical to a genuine new rule marker.
    [GeneratedRegex(@"^(\d{3,}(?:\.[0-9a-z]+)*)\.(?:\s+(.*))?$")]
    private static partial Regex RuleNumberLine();

    // Explicit cross-references: "See rule 197. Locations for more information." (Core Rules),
    // "See 205 for more information." (Tournament Rules, no "rule" word), and "See CR 128. ..."
    // (Tournament Rules referencing the Core Rules) all match.
    [GeneratedRegex(@"See\s+(?:rule\s+|CR\s+)?(\d+(?:\.[0-9A-Za-z]+)*)\.?", RegexOptions.IgnoreCase)]
    private static partial Regex CrossReferencePattern();
}
