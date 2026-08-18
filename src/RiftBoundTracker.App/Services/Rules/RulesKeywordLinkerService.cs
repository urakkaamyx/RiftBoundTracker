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
                if (pattern.IsMatch(entry.Text))
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
                if (pattern.IsMatch(card.TextPlain!))
                    db.CardRuleReferences.Add(new CardRuleReferenceEntity { CardId = card.Id, KeywordId = keyword.Id });
            }
        }

        await db.SaveChangesAsync(ct);
    }

    private static Regex WholeWord(string term) =>
        new(@"\b" + Regex.Escape(term) + @"\b", RegexOptions.IgnoreCase | RegexOptions.Compiled);
}
