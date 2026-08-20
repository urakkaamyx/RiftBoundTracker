using System.Text.RegularExpressions;

namespace RiftBoundTracker.App.Services.Rules;

public sealed record RulesAdjudicationValidationResult(bool Success, RulesAdjudication? Adjudication, string? Error);

/// <summary>
/// Parses the adjudicator's raw line-based output (see LocalLlmExplanationProvider's adjudication
/// system prompt for the exact expected shape — deliberately not JSON, since the fine-tuned model
/// has never seen JSON output and small models are unreliable at it via prompting alone) and
/// validates every cited EvidenceId actually exists in the evidence packet the question was given.
/// This is the hard boundary against a hallucinated citation ever reaching the player: a malformed
/// block or an unknown EvidenceId is a validation failure, never silently repaired or dropped.
/// RulesAnswerService retries once with a corrective prompt on failure, then falls back to the
/// pre-adjudication single-pass explanation if the retry also fails, so Ask Rules never regresses to
/// "no answer" because this stage had a bad run.
///
/// Expected shape, one block per issue:
///   ISSUE: &lt;restated sub-question&gt;
///   ANSWER: Yes|No|Insufficient
///   REASON: &lt;one sentence&gt;
///   EVIDENCE: E1, E3
///   MISSING: &lt;optional — only when ANSWER is Insufficient&gt;
///   ---
///   VERDICT: &lt;one line, after the last issue&gt;
///
/// Structural validity (well-formed blocks, only real E-ids cited) is not sufficient on its own —
/// this 1.5B model has no fine-tuning exposure to this new adjudication task shape yet (unlike the
/// single-pass ExplainAsync format it WAS fine-tuned on), and real testing caught it producing
/// perfectly well-formed output that answered a completely different, self-invented question instead
/// of the one actually asked (e.g. asked "do enemy spells have to target a Tank unit first?", it
/// adjudicated "does Tank let me play cards from the trash?" — sharing only the word "Tank" with the
/// real question). A validator that only checks structure would let that reach the player as if it
/// were the real answer. IsGroundedInQuestion is the check against exactly that: it requires the
/// issues to actually share meaningful content with the question asked, not just look well-formed.
/// </summary>
public static class RulesAdjudicationValidator
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

    private static HashSet<string> SignificantWords(string text) =>
        WordPattern.Matches(text).Select(m => m.Value.ToLowerInvariant())
            .Where(w => !StopWords.Contains(w)).ToHashSet();

    // Requires at least a third of the real question's significant words to reappear across the
    // adjudicated issues. Deliberately lenient (ISSUE is a free paraphrase, not a quote) — this is
    // aimed at catching wholesale topic drift, not penalizing normal rewording. Trivial questions
    // with fewer than 2 significant words skip the check entirely (nothing meaningful to compare).
    private static bool IsGroundedInQuestion(string originalQuestion, List<RulesAdjudicatedIssue> issues)
    {
        var questionWords = SignificantWords(originalQuestion);
        if (questionWords.Count < 2) return true;
        var issueWords = SignificantWords(string.Join(" ", issues.Select(i => i.Question)));
        var overlap = questionWords.Count(w => issueWords.Contains(w));
        return overlap >= Math.Max(1, questionWords.Count / 3);
    }

    public static RulesAdjudicationValidationResult ParseAndValidate(
        string rawOutput, IReadOnlyList<EvidenceRef> evidence, string originalQuestion)
    {
        var validIds = evidence.Select(e => e.Id).ToHashSet();
        var issues = new List<RulesAdjudicatedIssue>();
        var missing = new List<string>();
        string? verdict = null;

        string? question = null, answer = null, reason = null;
        List<string> evidenceIds = [];

        void FlushIssue()
        {
            if (question is not null && answer is not null)
                issues.Add(new RulesAdjudicatedIssue(question, answer, reason ?? "", evidenceIds));
            question = null; answer = null; reason = null; evidenceIds = [];
        }

        foreach (var rawLine in rawOutput.Split('\n'))
        {
            var line = rawLine.Trim();
            if (line.Length == 0) continue;
            if (line == "---") { FlushIssue(); continue; }

            if (TryExtract(line, "ISSUE:", out var v)) { FlushIssue(); question = v; }
            else if (TryExtract(line, "ANSWER:", out v)) answer = v;
            else if (TryExtract(line, "REASON:", out v)) reason = v;
            else if (TryExtract(line, "EVIDENCE:", out v))
                evidenceIds = [.. v.Split(',', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries)];
            else if (TryExtract(line, "MISSING:", out v)) missing.Add(v);
            else if (TryExtract(line, "VERDICT:", out v)) verdict = v;
        }
        FlushIssue();

        if (issues.Count == 0 || verdict is null)
            return new RulesAdjudicationValidationResult(
                false, null, "Adjudication output was malformed or empty — no parseable ISSUE/VERDICT lines found.");

        var unknownIds = issues.SelectMany(i => i.EvidenceIds).Where(id => !validIds.Contains(id)).Distinct().ToList();
        if (unknownIds.Count > 0)
            return new RulesAdjudicationValidationResult(false, null,
                $"Adjudication cited unknown evidence id(s): {string.Join(", ", unknownIds)}. " +
                $"Valid ids were: {string.Join(", ", validIds)}.");

        if (!IsGroundedInQuestion(originalQuestion, issues))
            return new RulesAdjudicationValidationResult(false, null,
                $"The ISSUE line(s) don't address the actual question asked (\"{originalQuestion}\"). " +
                "Restate and answer THIS exact question — do not substitute a different one.");

        return new RulesAdjudicationValidationResult(true, new RulesAdjudication(verdict, issues, missing), null);
    }

    private static bool TryExtract(string line, string prefix, out string value)
    {
        if (line.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
        {
            value = line[prefix.Length..].Trim();
            return true;
        }
        value = "";
        return false;
    }
}
