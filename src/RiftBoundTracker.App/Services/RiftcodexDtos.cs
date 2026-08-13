using System.Text.Json.Serialization;

namespace RiftBoundTracker.App.Services;

public class RiftcodexCard
{
    public string? Id { get; set; }
    public string Name { get; set; } = "";

    [JsonPropertyName("riftbound_id")]
    public string RiftboundId { get; set; } = "";

    [JsonPropertyName("tcgplayer_id")]
    public string? TcgplayerId { get; set; }

    [JsonPropertyName("collector_number")]
    public int CollectorNumber { get; set; }

    public RiftcodexAttributes? Attributes { get; set; }
    public RiftcodexClassification? Classification { get; set; }
    public RiftcodexText? Text { get; set; }
    public RiftcodexSet? Set { get; set; }
    public RiftcodexMedia? Media { get; set; }
    public string? Orientation { get; set; }
}

public class RiftcodexAttributes
{
    public int? Energy { get; set; }
    public int? Might { get; set; }
    public int? Power { get; set; }
}

public class RiftcodexClassification
{
    public string Type { get; set; } = "";
    public string? Supertype { get; set; }
    public string Rarity { get; set; } = "";
    public List<string> Domain { get; set; } = [];
}

public class RiftcodexText
{
    public string? Rich { get; set; }
    public string? Plain { get; set; }
    public string? Flavour { get; set; }
}

public class RiftcodexSet
{
    [JsonPropertyName("set_id")]
    public string SetId { get; set; } = "";
    public string Label { get; set; } = "";
}

public class RiftcodexMedia
{
    [JsonPropertyName("image_url")]
    public string ImageUrl { get; set; } = "";
    public string? Artist { get; set; }
}

public class RiftcodexCardPage
{
    public List<RiftcodexCard> Items { get; set; } = [];
    public int Total { get; set; }
    public int Page { get; set; }
    public int Size { get; set; }
    public int Pages { get; set; }
}

public class RiftcodexSetListItem
{
    public string? Id { get; set; }
    public string Name { get; set; } = "";

    [JsonPropertyName("set_id")]
    public string SetId { get; set; } = "";

    [JsonPropertyName("card_count")]
    public int CardCount { get; set; }

    [JsonPropertyName("published_on")]
    public DateTimeOffset? PublishedOn { get; set; }
}

public class RiftcodexSetPage
{
    public List<RiftcodexSetListItem> Items { get; set; } = [];
    public int Total { get; set; }
    public int Page { get; set; }
    public int Size { get; set; }
    public int Pages { get; set; }
}
