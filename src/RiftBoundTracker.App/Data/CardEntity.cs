namespace RiftBoundTracker.App.Data;

public class CardEntity
{
    public string Id { get; set; } = ""; // riftbound_id, e.g. "ven-147-166"
    public string Name { get; set; } = "";
    public int CollectorNumber { get; set; }
    public string SetId { get; set; } = "";
    public string SetLabel { get; set; } = "";
    public string Type { get; set; } = "";
    public string? Supertype { get; set; }
    public string Rarity { get; set; } = "";
    public string DomainsCsv { get; set; } = "";
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

    public int OwnedCount { get; set; }
    public string? Notes { get; set; }
    public DateTimeOffset CachedAt { get; set; }
    public DateTimeOffset UpdatedAt { get; set; }

    public string[] Domains => string.IsNullOrEmpty(DomainsCsv)
        ? Array.Empty<string>()
        : DomainsCsv.Split(',', StringSplitOptions.RemoveEmptyEntries);
}
