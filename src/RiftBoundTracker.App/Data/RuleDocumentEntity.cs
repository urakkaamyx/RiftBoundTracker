namespace RiftBoundTracker.App.Data;

// The distinct classes of official document this app actually discovers from playriftbound.com's
// Rules Hub today. Not the full list the architecture doc sketches (FAQ, generic RulesArticle,
// HistoricalRules) — those aren't published as separate documents on the real site, so no
// placeholder document types are created for them; add one if/when the site actually publishes it.
public enum RuleSourceType { CoreRules, TournamentRules, PatchNotes, Errata, Legality }

// Higher value always outranks lower in search — current Core Rules must beat an old FAQ even if
// the FAQ is a better text match. Mirrors the architecture doc's suggested enum exactly.
public enum RuleAuthority
{
    Historical = 0,
    Supplemental = 1,
    OfficialClarification = 2,
    OfficialErrata = 3,
    TournamentRules = 4,
    CoreRules = 5,
}

public class RuleDocumentEntity
{
    public int Id { get; set; }
    public RuleSourceType SourceType { get; set; }
    public string Title { get; set; } = "";

    // The page a human would open (an article URL, or the Rules Hub itself for Legality).
    public string SourceUrl { get; set; } = "";
    // The actual file fetched for parsing (PDF url for Core/Tournament Rules); null for
    // HTML-sourced documents, where SourceUrl doubles as what was parsed.
    public string? DownloadUrl { get; set; }

    // The "Last updated" date as published on the site (free text — the sites are inconsistent
    // about exact format), kept alongside the parsed PublishedAt for display/debugging.
    public string? DocumentVersion { get; set; }
    public DateTimeOffset? PublishedAt { get; set; }
    public DateTimeOffset DiscoveredAt { get; set; }
    public DateTimeOffset? DownloadedAt { get; set; }

    // SHA-256 of the downloaded bytes (PDF) or the extracted richText HTML (articles) — a source
    // can keep the same URL while replacing the underlying document, so content identity (not URL)
    // decides whether a re-sync actually needs to reparse anything.
    public string? ContentHash { get; set; }

    public RuleAuthority Authority { get; set; }
    public bool IsCurrent { get; set; } = true;

    public string? ParseStatus { get; set; } // "Ok" | "Failed" | null (not yet parsed)
    public string? LastError { get; set; }

    public ICollection<RuleEntryEntity> Entries { get; set; } = [];
}
