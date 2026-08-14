namespace RiftBoundTracker.App.Data;

public class CardTextSymbolEntity
{
    public string Token { get; set; } = "";
    public string Label { get; set; } = "";
    public string Kind { get; set; } = "";
    public string Shape { get; set; } = "";
    public string? AssetPath { get; set; }
    public string ForegroundColor { get; set; } = "";
    public string BackgroundColor { get; set; } = "";
    public string BorderColor { get; set; } = "";
    public int SortOrder { get; set; }
}
