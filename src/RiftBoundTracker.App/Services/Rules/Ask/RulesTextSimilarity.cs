using System.Text.RegularExpressions;

namespace RiftBoundTracker.App.Services.Rules;

/// <summary>
/// Shared word-overlap similarity used wherever two pieces of free text need to be checked for
/// "are these actually about the same thing" without real NLU — originally built for
/// RulesAdjudicationValidator's grounding check, reused by RulesCuratedRulingService's question
/// matching since both are the same underlying problem (crude but effective: strip stopwords, keep
/// nouns/verbs, count overlap).
/// </summary>
public static class RulesTextSimilarity
{
    // Short, closed-class words that carry no topical content — excluded so overlap is measured on
    // the nouns/verbs/concepts that actually identify what a question is about, not connective tissue
    // ("does", "that", "have") every question and every hallucinated tangent will share regardless.
    private static readonly HashSet<string> StopWords = new(StringComparer.OrdinalIgnoreCase)
    {
        "does", "that", "this", "with", "from", "have", "make", "makes", "when", "which", "what",
        "there", "their", "they", "them", "then", "than", "into", "onto", "will", "would", "could",
        "should", "about", "these", "those", "such", "some", "same", "only", "also", "still", "even",
        "being", "been", "were", "was", "are", "the", "and", "for", "not", "but", "you", "your",
        "can", "who", "how", "why", "did", "let",
    };

    private static readonly Regex WordPattern = new(@"[A-Za-z]{4,}", RegexOptions.Compiled);

    public static HashSet<string> SignificantWords(string text) =>
        WordPattern.Matches(text).Select(m => m.Value.ToLowerInvariant())
            .Where(w => !StopWords.Contains(w)).ToHashSet();

    /// <summary>Fraction of `a`'s significant words that also appear in `b`, 0.0-1.0.</summary>
    public static double OverlapFraction(HashSet<string> a, HashSet<string> b)
    {
        if (a.Count == 0) return 0;
        return (double)a.Count(w => b.Contains(w)) / a.Count;
    }
}
