namespace RiftBoundTracker.App.Data;

public class DeckEntity
{
    public int Id { get; set; }
    public string Name { get; set; } = "New Deck";
    public string Description { get; set; } = "";
    public string Format { get; set; } = "Standard";
    public string? CoverCardId { get; set; }
    public DateTimeOffset CreatedAt { get; set; }
    public DateTimeOffset UpdatedAt { get; set; }

    public ICollection<DeckCardEntity> Cards { get; set; } = [];
}
