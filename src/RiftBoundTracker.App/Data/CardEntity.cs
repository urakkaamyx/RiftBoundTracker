using System.Text.Json.Serialization;

namespace RiftBoundTracker.App.Data;

public class CardEntity
{
    public string Id { get; set; } = ""; // riftbound_id, e.g. "ven-147-166"
    public string Name { get; set; } = "";
    public int CollectorNumber { get; set; }
    // The number as actually printed on the card, e.g. "001", "R01" (rune), "007A" (alt art) —
    // Riftcodex's own collector_number field is purely numeric and drops any letter prefix/suffix,
    // so two different cards (e.g. VEN "001" and VEN "R01") can share the same CollectorNumber.
    // Derived from RiftboundId at sync time; see CardCacheService.ExtractCollectorCode.
    public string CollectorCode { get; set; } = "";
    public string SetId { get; set; } = "";
    public string SetLabel { get; set; } = "";
    public string Type { get; set; } = "";
    public string? Supertype { get; set; }
    public string Rarity { get; set; } = "";
    public string DomainsCsv { get; set; } = "";
    public string? TextRich { get; set; }
    public string? TextPlain { get; set; }
    public string? Flavour { get; set; }
    public string ImageUrl { get; set; } = "";
    public string? LocalImagePath { get; set; } // relative path under wwwroot
    public byte[]? ImageHash { get; set; } // 256-bit dHash fingerprint, for photo-match fallback
    public string? Artist { get; set; }
    public string? Orientation { get; set; }
    public string? TcgplayerId { get; set; }
    public int? Energy { get; set; }
    public int? Might { get; set; }
    public int? Power { get; set; }

    // True only for the token cards TokenCardCatalogService hand-seeds (Brush, Baron Pit, etc.) —
    // riftcodex.com has no data for them at all, unlike the handful of tokens (Recruit x3, Sprite,
    // Gold // Buff) that came through the normal set sync with real set data and stay part of
    // their set's own collection/completion stats like any other card. This flag is what lets the
    // Vault separate "orphan" tokens with no real set home from those that still have one.
    public bool IsSyntheticToken { get; set; }

    public int OwnedCount { get; set; }
    public bool IsFavorite { get; set; }
    public int BinderCount { get; set; }
    // How many of OwnedCount are the Hologram foil finish — a sub-count of ownership, not a
    // separate printing (unlike Alternate Art etc., Hologram isn't its own collector-numbered
    // card), so it's tracked here rather than as a distinct CardEntity row. Always clamped to
    // [0, OwnedCount], same as BinderCount.
    public int HologramCount { get; set; }
    public string? Notes { get; set; }
    public DateTimeOffset CachedAt { get; set; }
    public DateTimeOffset UpdatedAt { get; set; }

    public string[] Domains => string.IsNullOrEmpty(DomainsCsv)
        ? Array.Empty<string>()
        : DomainsCsv.Split(',', StringSplitOptions.RemoveEmptyEntries);

    [JsonIgnore]
    public ICollection<DeckCardEntity> DeckCards { get; set; } = [];
    [JsonIgnore]
    public ICollection<PriceSnapshotEntity> PriceSnapshots { get; set; } = [];
    [JsonIgnore]
    public PriceQueueEntity? PriceQueueItem { get; set; }
}
