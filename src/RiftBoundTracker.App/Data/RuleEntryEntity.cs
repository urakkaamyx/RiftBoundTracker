namespace RiftBoundTracker.App.Data;

// One individual rule (e.g. "103.2.b") or, for whole-article documents like Patch Notes, one
// section of that article — never a whole 120-page PDF crammed into a single row, so a search hit
// can jump straight to the paragraph that matters instead of a giant text blob.
public class RuleEntryEntity
{
    public int Id { get; set; }
    public int DocumentId { get; set; }

    // Null for entries carved out of prose articles (Patch Notes) that have no official numbering.
    public string? RuleNumber { get; set; }
    public int? ParentRuleId { get; set; }

    // Set when this entry is itself a heading (e.g. "173. Legends") rather than rule text — lets
    // the UI show a breadcrumb by walking up the parent chain to the nearest entry with a Title.
    public string? Title { get; set; }
    public string Text { get; set; } = "";

    // Position within the source document — preserves reading order for Previous/Next navigation
    // even though RuleNumber sorts correctly on its own in the common case.
    public int SortOrder { get; set; }

    // Denormalized from the owning document so ranking/filtering doesn't need a join for the
    // hottest query path (search).
    public RuleAuthority Authority { get; set; }
    public bool IsCurrent { get; set; } = true;

    public RuleDocumentEntity Document { get; set; } = null!;
    public RuleEntryEntity? Parent { get; set; }
    public ICollection<RuleEntryKeywordEntity> Keywords { get; set; } = [];
}
