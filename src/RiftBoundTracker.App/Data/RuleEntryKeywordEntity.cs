namespace RiftBoundTracker.App.Data;

// Rule <-> Keyword many-to-many (a rule can mention several keywords; a keyword is referenced by
// several rules beyond just its own canonical definition).
public class RuleEntryKeywordEntity
{
    public int RuleEntryId { get; set; }
    public int KeywordId { get; set; }

    public RuleEntryEntity RuleEntry { get; set; } = null!;
    public RuleKeywordEntity Keyword { get; set; } = null!;
}
