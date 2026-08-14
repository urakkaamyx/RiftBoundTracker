namespace RiftBoundTracker.App.Data;

public class PriceQueueEntity
{
    public string CardId { get; set; } = "";
    public DateTimeOffset QueuedAt { get; set; }

    public CardEntity Card { get; set; } = null!;
}
