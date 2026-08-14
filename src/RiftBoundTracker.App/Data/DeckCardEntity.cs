namespace RiftBoundTracker.App.Data;

public class DeckCardEntity
{
    public int DeckId { get; set; }
    public string CardId { get; set; } = "";
    public string Section { get; set; } = "main";
    public int Quantity { get; set; }

    public DeckEntity Deck { get; set; } = null!;
    public CardEntity Card { get; set; } = null!;
}
