using System.Text.RegularExpressions;

namespace RiftBoundTracker.App.Services;

// Code preserves the printed collector code, including leading zeroes and any letter prefix/suffix
// (e.g. "002", "R01", "007A"). That distinction is required for sets where 002, R02, and SP2 all
// share the same numeric CollectorNumber.
public record ParsedCardId(int Number, int? Total, string? SetCode, string? Code);

public static partial class CardIdParser
{
    // Each digit slot also accepts common OCR misreads of a digit (O/o/Q for 0, I/l/i/| for 1, S/s
    // for 5, B for 8) — normalized back to the real digit before parsing. The separator accepts an
    // actual slash-like glyph, or falls back to bare whitespace for photos where OCR drops the
    // slash entirely (e.g. "123 252" instead of "123/252"). An optional single letter directly
    // adjacent to the digits (no space) captures a printed prefix/suffix like "R01" or "007A" —
    // restricted to no-space adjacency so it doesn't grab onto stray letters from nearby rules text.
    [GeneratedRegex(@"(?<prefix>[A-Za-z])?(?<num>[0-9OoQIl|iSsB]{1,3})(?<suffix>[A-Za-z])?(?:\s*[/\\|]\s*|\s+)(?<total>[0-9OoQIl|iSsB]{1,3})")]
    private static partial Regex NumberSlashTotal();

    [GeneratedRegex(@"\b(?<code>[A-Z]{2,4})\b")]
    private static partial Regex SetCodeWord();

    private static readonly Dictionary<char, char> DigitConfusions = new()
    {
        ['O'] = '0', ['o'] = '0', ['Q'] = '0',
        ['I'] = '1', ['l'] = '1', ['i'] = '1', ['|'] = '1',
        ['S'] = '5', ['s'] = '5',
        ['B'] = '8',
    };

    // How much surrounding text (in characters) to search for a set-code token near a number
    // match, instead of taking the first 2-4 letter uppercase word anywhere in the whole OCR blob.
    private const int SetCodeWindowChars = 14;

    /// <summary>
    /// Pulls candidate "collector-number/set-total" pairs (and a nearby set code, if legible) out
    /// of raw OCR text from the card's bottom band. Candidates are NOT validated here — the caller
    /// checks them against the actual local card cache, since a fuzzy digit/separator match can
    /// occasionally fire on text that isn't a collector number at all.
    /// </summary>
    public static List<ParsedCardId> Parse(string ocrText)
    {
        var results = new List<ParsedCardId>();

        foreach (Match m in NumberSlashTotal().Matches(ocrText))
        {
            if (!TryNormalizeNumber(m.Groups["num"].Value, out var num) || num <= 0 || num > 999)
                continue;

            int? total = TryNormalizeNumber(m.Groups["total"].Value, out var t) ? t : null;

            var windowStart = Math.Max(0, m.Index - SetCodeWindowChars);
            var windowEnd = Math.Min(ocrText.Length, m.Index + m.Length + SetCodeWindowChars);
            var window = ocrText[windowStart..windowEnd];
            var setCode = SetCodeWord().Match(window) is { Success: true } sm ? sm.Groups["code"].Value : null;

            var prefix = m.Groups["prefix"].Success ? m.Groups["prefix"].Value : null;
            var suffix = m.Groups["suffix"].Success ? m.Groups["suffix"].Value : null;
            var normalizedDigits = NormalizeDigits(m.Groups["num"].Value);
            var code = $"{prefix}{normalizedDigits}{suffix}".ToUpperInvariant();

            results.Add(new ParsedCardId(num, total, setCode, code));
        }

        return results
            .DistinctBy(r => (r.Number, r.Total))
            .ToList();
    }

    private static bool TryNormalizeNumber(string raw, out int value)
    {
        return int.TryParse(NormalizeDigits(raw), out value);
    }

    private static string NormalizeDigits(string raw) =>
        new(raw.Select(c => DigitConfusions.GetValueOrDefault(c, c)).ToArray());
}
