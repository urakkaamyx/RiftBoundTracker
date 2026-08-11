using System.Text.RegularExpressions;

namespace RiftBoundTracker.App.Services;

public record ParsedCardId(int Number, int? Total, string? SetCode);

public static partial class CardIdParser
{
    [GeneratedRegex(@"(?<num>\d{1,3})\s*/\s*(?<total>\d{1,3})")]
    private static partial Regex NumberSlashTotal();

    [GeneratedRegex(@"\b(?<code>[A-Z]{2,4})\b")]
    private static partial Regex SetCodeWord();

    /// <summary>
    /// Pulls candidate "collector-number/set-total" pairs (and a nearby set code, if legible)
    /// out of raw OCR text from the card's bottom band. Returns candidates in the order found;
    /// the caller decides how to disambiguate against the cache.
    /// </summary>
    public static List<ParsedCardId> Parse(string ocrText)
    {
        var results = new List<ParsedCardId>();
        var setCode = SetCodeWord().Matches(ocrText)
            .Select(m => m.Groups["code"].Value)
            .FirstOrDefault(c => c is { Length: >= 2 and <= 4 });

        foreach (Match m in NumberSlashTotal().Matches(ocrText))
        {
            if (!int.TryParse(m.Groups["num"].Value, out var num)) continue;
            int? total = int.TryParse(m.Groups["total"].Value, out var t) ? t : null;
            if (num <= 0 || num > 999) continue;
            results.Add(new ParsedCardId(num, total, setCode));
        }

        return results
            .DistinctBy(r => (r.Number, r.Total))
            .ToList();
    }
}
