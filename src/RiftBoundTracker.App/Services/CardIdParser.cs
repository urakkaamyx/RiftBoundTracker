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
    [GeneratedRegex(@"(?<![A-Za-z0-9])(?<prefix>SP|[A-Za-z])?(?<num>[0-9OoQIl|iSsB]{1,3})(?<suffix>[A-Za-z])?(?:\s*[/\\|]\s*|\s+)(?<total>[0-9OoQIl|iSsB]{1,3})(?![A-Za-z0-9])", RegexOptions.IgnoreCase)]
    private static partial Regex NumberSlashTotal();

    // Rune cards use a code-only footer such as "VEN • R01 • EN". OCR commonly returns ROI or
    // RO1, so the number portion accepts the same digit confusions as the slash/total pattern.
    // SP is the only multi-letter prefix in the current catalog; the single-letter fallback also
    // covers R and T without starting a match in the middle of a larger word.
    [GeneratedRegex(@"(?<![A-Za-z0-9])(?<prefix>SP|[A-Za-z])(?<num>[0-9OoQIl|iSsB]{1,3})(?<suffix>[A-Za-z])?(?![A-Za-z0-9])", RegexOptions.IgnoreCase)]
    private static partial Regex CodeOnly();

    // At camera resolution Windows OCR can merge the two leading zeroes in a code such as 001
    // into a single m-shaped glyph. Restrict this correction to a standalone two-character token
    // so ordinary words containing m are never rewritten.
    [GeneratedRegex(@"(?<![A-Za-z0-9])[mM](?=[0-9OoQIl|iSsB](?![A-Za-z0-9]))")]
    private static partial Regex CollapsedDoubleZero();

    [GeneratedRegex(@"(?<![A-Za-z0-9])(?<num>[0-9OoQIl|iSsB]{3})(?![A-Za-z0-9])")]
    private static partial Regex BareCodeOnly();

    [GeneratedRegex(@"\b(?<code>[A-Z]{2,4})\b")]
    private static partial Regex SetCodeWord();

    private static readonly Dictionary<char, char> DigitConfusions = new()
    {
        ['O'] = '0', ['o'] = '0', ['Q'] = '0',
        ['I'] = '1', ['l'] = '1', ['i'] = '1', ['|'] = '1',
        ['S'] = '5', ['s'] = '5',
        ['B'] = '8',
    };

    private static readonly HashSet<string> LanguageMarkers = new(StringComparer.OrdinalIgnoreCase)
    {
        "EN", "DE", "ES", "FR", "IT", "JA", "JP", "KO", "KR", "PT", "ZH"
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
        var normalizedText = CollapsedDoubleZero().Replace(ocrText, "00");

        foreach (Match m in NumberSlashTotal().Matches(normalizedText))
        {
            if (!TryNormalizeNumber(m.Groups["num"].Value, out var num) || num <= 0 || num > 999)
                continue;

            int? total = TryNormalizeNumber(m.Groups["total"].Value, out var t) ? t : null;

            var prefix = m.Groups["prefix"].Success ? m.Groups["prefix"].Value : null;
            var suffix = m.Groups["suffix"].Success ? m.Groups["suffix"].Value : null;
            var normalizedDigits = NormalizeDigits(m.Groups["num"].Value);
            var code = $"{prefix}{normalizedDigits}{suffix}".ToUpperInvariant();

            results.Add(new ParsedCardId(num, total, FindNearbySetCode(normalizedText, m), code));
        }

        foreach (Match m in CodeOnly().Matches(normalizedText))
        {
            if (!TryNormalizeNumber(m.Groups["num"].Value, out var num) || num <= 0 || num > 999)
                continue;

            var normalizedDigits = NormalizeDigits(m.Groups["num"].Value);
            var code = $"{m.Groups["prefix"].Value}{normalizedDigits}{m.Groups["suffix"].Value}".ToUpperInvariant();
            results.Add(new ParsedCardId(num, null, FindNearbySetCode(normalizedText, m), code));
        }

        foreach (Match m in BareCodeOnly().Matches(normalizedText))
        {
            var setCode = FindNearbySetCode(normalizedText, m);
            if (setCode is null || IsAfterTotalSeparator(normalizedText, m.Index)
                || !TryNormalizeNumber(m.Groups["num"].Value, out var num) || num <= 0 || num > 999)
                continue;

            results.Add(new ParsedCardId(
                num,
                null,
                setCode,
                NormalizeDigits(m.Groups["num"].Value).ToUpperInvariant()));
        }

        return results
            .DistinctBy(r => (r.Code, r.Total, r.SetCode))
            .ToList();
    }

    private static string? FindNearbySetCode(string ocrText, Match match)
    {
        var windowStart = Math.Max(0, match.Index - SetCodeWindowChars);
        var windowEnd = Math.Min(ocrText.Length, match.Index + match.Length + SetCodeWindowChars);
        var window = ocrText[windowStart..windowEnd];
        return SetCodeWord().Matches(window)
            .Select(m => m.Groups["code"].Value)
            .FirstOrDefault(code => !LanguageMarkers.Contains(code));
    }

    private static bool IsAfterTotalSeparator(string text, int index)
    {
        for (var i = index - 1; i >= 0; i--)
        {
            if (char.IsWhiteSpace(text[i])) continue;
            return text[i] is '/' or '\\' or '|';
        }
        return false;
    }

    private static bool TryNormalizeNumber(string raw, out int value)
    {
        return int.TryParse(NormalizeDigits(raw), out value);
    }

    private static string NormalizeDigits(string raw) =>
        new(raw.Select(c => DigitConfusions.GetValueOrDefault(c, c)).ToArray());
}
