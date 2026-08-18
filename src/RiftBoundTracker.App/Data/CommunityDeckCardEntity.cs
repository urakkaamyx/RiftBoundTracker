namespace RiftBoundTracker.App.Data;

public class CommunityDeckCardEntity
{
    public int Id { get; set; }
    public int CommunityDeckId { get; set; }
    public string CardId { get; set; } = "";
    public int Quantity { get; set; }
    public string Section { get; set; } = "main";

    public CommunityDeckEntity CommunityDeck { get; set; } = null!;
    public CardEntity Card { get; set; } = null!;
}
