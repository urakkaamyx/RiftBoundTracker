namespace RiftBoundTracker.App.Data;

// An explicit "See rule 197. Locations for more information." reference parsed straight out of the
// rule text. V1 only stores references that actually resolved to a real local RuleEntry — a
// "See rule X" pointing at a number that doesn't exist in the current corpus is dropped rather than
// stored dangling, per the architecture doc's "never fabricate cross-references" instruction.
public class RuleCrossReferenceEntity
{
    public int Id { get; set; }
    public int FromRuleId { get; set; }
    public int ToRuleId { get; set; }
    public string? ReferenceText { get; set; }

    public RuleEntryEntity FromRule { get; set; } = null!;
    public RuleEntryEntity ToRule { get; set; } = null!;
}
