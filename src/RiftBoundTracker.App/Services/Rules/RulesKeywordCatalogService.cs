using Microsoft.EntityFrameworkCore;
using RiftBoundTracker.App.Data;

namespace RiftBoundTracker.App.Services.Rules;

/// <summary>
/// Seeds the official keyword glossary and player-terminology aliases. Hand-curated (mirroring
/// CardTextSymbolCatalogService's seed pattern) from terms the architecture docs explicitly name
/// and from real keyword badges this app already renders on card text — never auto-derived from
/// scanning rule text, since the docs are explicit that alias lists must stay curated, not
/// speculative. CanonicalRuleId and the "mentioned in" links (RuleEntryKeyword/CardRuleReference)
/// ARE derived automatically from real parsed content, by RulesKeywordLinkerService after sync.
/// </summary>
public class RulesKeywordCatalogService(AppDbContext db)
{
    private static readonly (string Name, string? Category, string[] Aliases)[] Keywords =
    [
        ("Exhaust", "Action", ["tap"]),
        ("Ready", "Action", ["untap"]),
        ("Chain", "Timing", []),
        ("Reaction", "Timing", []),
        ("Showdown", "Timing", []),
        ("Deflect", "Combat", []),
        ("Banish", "Zone", []),
        ("Recycle", "Zone", []),
        ("Trash", "Zone", ["graveyard"]),
        ("Hidden", "Card State", []),
        ("Ganking", "Movement", ["gank"]),
        ("Domain", "Deckbuilding", ["color", "colors"]),
        ("Domain Identity", "Deckbuilding", ["color identity"]),
        ("Chosen Champion", "Deckbuilding", []),
        ("Champion Legend", "Deckbuilding", ["leader"]),
        ("Damage", "Combat", []),
        ("Heal", "Combat", []),
        ("Trigger", "Ability", []),
        ("Ambush", "Action", []),
        ("Empower", "Action", []),
        ("Predict", "Action", []),
        ("Stun", "Card State", []),
        ("Destroy", "Combat", ["kill"]),
        ("Might", "Stat", []),
        ("Control", "Board State", []),
        ("Location", "Board State", []),
        ("Battlefield", "Board State", []),
        ("Conquer", "Board State", []),
    ];

    public async Task EnsureSeededAsync(CancellationToken ct = default)
    {
        var existing = await db.RuleKeywords
            .Include(k => k.Aliases)
            .ToDictionaryAsync(k => k.NormalizedName, ct);

        foreach (var (name, category, aliases) in Keywords)
        {
            var normalized = Normalize(name);
            if (!existing.TryGetValue(normalized, out var keyword))
            {
                keyword = new RuleKeywordEntity { Name = name, NormalizedName = normalized };
                db.RuleKeywords.Add(keyword);
            }
            keyword.Name = name;
            keyword.Category = category;
            keyword.IsOfficialKeyword = true;

            var existingAliases = keyword.Aliases.Select(a => a.NormalizedAlias).ToHashSet();
            foreach (var alias in aliases)
            {
                var normalizedAlias = Normalize(alias);
                if (existingAliases.Contains(normalizedAlias)) continue;
                keyword.Aliases.Add(new RuleKeywordAliasEntity { Alias = alias, NormalizedAlias = normalizedAlias });
            }
        }

        await db.SaveChangesAsync(ct);
    }

    internal static string Normalize(string value) => value.Trim().ToLowerInvariant();
}
