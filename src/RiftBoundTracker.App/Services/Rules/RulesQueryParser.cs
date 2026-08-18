using System.Text.RegularExpressions;

namespace RiftBoundTracker.App.Services.Rules;

/// <summary>
/// Recognizes query intent so a search for "103.2.b" opens that exact rule instead of running a
/// full-text search for it, matching every other numbered rule mention in the corpus (architecture
/// doc section 13/40). Keyword/alias/full-text intent is resolved by RulesSearchService itself,
/// since that needs a DB lookup this parser deliberately stays free of.
/// </summary>
public static partial class RulesQueryParser
{
    public static bool TryParseRuleNumber(string query, out string ruleNumber)
    {
        var trimmed = query.Trim().TrimEnd('.');
        var match = RuleNumberPattern().Match(trimmed);
        ruleNumber = match.Success ? match.Value : "";
        return match.Success;
    }

    // Same shape RulesPdfParser recognizes when parsing rule markers — a dot-separated chain
    // starting with a 3+ digit top-level number.
    [GeneratedRegex(@"^\d{3,}(?:\.[0-9a-zA-Z]+)*$")]
    private static partial Regex RuleNumberPattern();
}
