namespace RiftBoundTracker.App.Data;

// A canonical official term (Exhaust, Ready, Ganking, ...) that both the glossary and search
// treat as a first-class concept, not just a substring that happens to appear in rule text.
public class RuleKeywordEntity
{
    public int Id { get; set; }
    public string Name { get; set; } = "";
    public string NormalizedName { get; set; } = "";
    public string? Definition { get; set; }
    public string? Category { get; set; }

    // The rule that actually defines this keyword (e.g. Exhaust -> rule 414), resolved by matching
    // the keyword name against a heading-style RuleEntry's Title during sync. Left null rather than
    // guessed when no matching heading is found.
    public int? CanonicalRuleId { get; set; }
    public bool IsOfficialKeyword { get; set; } = true;

    public RuleEntryEntity? CanonicalRule { get; set; }
    public ICollection<RuleKeywordAliasEntity> Aliases { get; set; } = [];
    public ICollection<RuleEntryKeywordEntity> RuleEntries { get; set; } = [];
}
