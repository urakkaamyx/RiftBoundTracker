using RiftBoundTracker.App.Data;

namespace RiftBoundTracker.App.Services.Rules;

// Staging model a parser fills in before anything touches the real database — RulesImportService
// only writes to RuleDocuments/RuleEntries/etc. after this has been fully built, so a parser bug
// can never leave the active rules library half-written (architecture doc section 25/28).
public sealed class ParsedRuleDocument
{
    public string Title { get; set; } = "";
    public string? DocumentVersionText { get; set; }
    public DateTimeOffset? PublishedAt { get; set; }
    public List<ParsedRule> Rules { get; } = [];
    public List<ParsedErrataEntry> Errata { get; } = [];
    public List<ParsedLegalityEntry> Legalities { get; } = [];
}

public sealed class ParsedRule
{
    // Null for entries carved out of prose articles that have no official rule numbering
    // (Patch Notes) — those still get a SortOrder-based position but no hierarchy.
    public string? RuleNumber { get; set; }
    public string? Title { get; set; }
    public string Text { get; set; } = "";
    public int SortOrder { get; set; }

    // Raw "See rule 197." style matches found in this rule's own text, resolved to real
    // RuleEntryEntity ids by RulesImportService once the whole document's numbers are known.
    public List<string> ExplicitReferenceNumbers { get; } = [];
}

public sealed class ParsedErrataEntry
{
    public string CardNameRaw { get; set; } = "";
    public string? OriginalText { get; set; }
    public string? CorrectedText { get; set; }
}

public sealed class ParsedLegalityEntry
{
    public string CardNameRaw { get; set; } = "";
    public string Format { get; set; } = "";
    public CardLegalityStatus Status { get; set; }
}

// What RulesSourceDiscoveryService finds before anything is downloaded — enough to decide whether
// a re-fetch is even needed (content-hash comparison happens after download, in RulesSyncService).
public sealed class DiscoveredRuleDocument
{
    public RuleSourceType SourceType { get; set; }
    public string Title { get; set; } = "";
    public string SourceUrl { get; set; } = "";
    public string? DownloadUrl { get; set; }
    public string? DocumentVersionText { get; set; }
    public DateTimeOffset? PublishedAt { get; set; }
}
