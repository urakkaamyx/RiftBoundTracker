namespace RiftBoundTracker.App.Data;

public class PriceSnapshotEntity
{
    public long Id { get; set; }
    public string CardId { get; set; } = "";
    public string Provider { get; set; } = "";
    public string VariantId { get; set; } = "";
    public string Condition { get; set; } = "";
    public string Printing { get; set; } = "";
    public string Currency { get; set; } = "USD";
    public double MarketPrice { get; set; }
    public double? Change24Hours { get; set; }
    public DateTimeOffset CapturedAt { get; set; }
    public DateTimeOffset? SourceUpdatedAt { get; set; }

    public CardEntity Card { get; set; } = null!;
}
