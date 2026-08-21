using System.Text.RegularExpressions;
using Microsoft.EntityFrameworkCore;
using RiftBoundTracker.App.Data;

namespace RiftBoundTracker.App.Services.Rules;

/// <summary>
/// Runs after every sync to (1) point each seeded keyword at the rule that actually defines it —
/// a current RuleEntry whose own Title matches the keyword name exactly, never guessed — and
/// (2) link every rule/card whose real text mentions a keyword, so "Cards Using Exhaust" and a
/// card's own "Rules References" are both derived from real parsed/catalog content rather than a
/// hand-maintained list. Metadata only: never touches CardEntity or RuleEntry text itself.
/// </summary>
public sealed class RulesKeywordLinkerService(AppDbContext db)
{
    public async Task LinkAsync(CancellationToken ct = default)
    {
        var keywords = await db.RuleKeywords.ToListAsync(ct);
        if (keywords.Count == 0) return;

        var headings = await db.RuleEntries
            .Where(r => r.IsCurrent && r.Title != null)
            .Select(r => new { r.Id, r.Title, r.Authority })
            .ToListAsync(ct);

        foreach (var keyword in keywords)
        {
            var canonical = headings
                .Where(h => string.Equals(h.Title, keyword.Name, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(h => h.Authority)
                .FirstOrDefault();
            keyword.CanonicalRuleId = canonical?.Id;
        }
        await db.SaveChangesAsync(ct);

        db.RuleEntryKeywords.RemoveRange(db.RuleEntryKeywords);
        var currentEntries = await db.RuleEntries
            .Where(r => r.IsCurrent)
            .Select(r => new { r.Id, r.Text })
            .ToListAsync(ct);
        foreach (var keyword in keywords)
        {
            var pattern = WholeWord(keyword.Name);
            foreach (var entry in currentEntries)
            {
                if (pattern.Matches(entry.Text).Any(IsRealMatch))
                    db.RuleEntryKeywords.Add(new RuleEntryKeywordEntity { RuleEntryId = entry.Id, KeywordId = keyword.Id });
            }
        }

        db.CardRuleReferences.RemoveRange(db.CardRuleReferences);
        var cardText = await db.Cards
            .Where(c => c.TextPlain != null && c.TextPlain != "")
            .Select(c => new { c.Id, c.TextPlain })
            .ToListAsync(ct);
        foreach (var keyword in keywords)
        {
            var pattern = WholeWord(keyword.Name);
            foreach (var card in cardText)
            {
                if (pattern.Matches(card.TextPlain!).Any(IsRealMatch))
                    db.CardRuleReferences.Add(new CardRuleReferenceEntity { CardId = card.Id, KeywordId = keyword.Id });
            }
        }

        await db.SaveChangesAsync(ct);
    }

    // Matches the keyword plus up to 4 trailing letters, not just the bare word — real rule text
    // almost always uses an inflected form ("controls", "controller", "controlled") rather than the
    // bare keyword itself. Confirmed directly against the corpus: an exact-word match tagged only 90
    // of the 239 rules substantively about Control, missing the other 149 (including rule 355.2.a,
    // "a Battlefield the controller controls" — the actual answer to a real "can I play directly to
    // a battlefield I control" question that a from-evidence model got wrong because this rule never
    // made it into its evidence at all). The {1,4} window is wide enough to catch irregular doubled-
    // consonant forms a simple suffix list would miss (controller, controlling), verified against
    // every keyword in the live corpus before shipping — the denylist below is the small number of
    // real false hits that check turned up (unrelated words that happen to start with a keyword,
    // all from Code of Conduct / tournament-administration text, never gameplay rules).
    private static readonly HashSet<string> InflectionDenylist = new(StringComparer.OrdinalIgnoreCase)
    {
        "healthy", "stunt", "exhaustive", "exhaustively",
    };

    private static Regex WholeWord(string term) =>
        new(@"\b" + Regex.Escape(term) + @"[a-z]{0,4}\b", RegexOptions.IgnoreCase | RegexOptions.Compiled);

    private static bool IsRealMatch(Match match) => !InflectionDenylist.Contains(match.Value);
}
