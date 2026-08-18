namespace RiftBoundTracker.App.Data;

public class CommunityDeckEntity
{
    public int Id { get; set; }
    public int TournamentId { get; set; }
    public string PlayerName { get; set; } = "";

    // Nullable: set only when the Legend's provider card id resolved to a real local card.
    // LegendRawName is kept regardless, so an unresolved Legend can still be shown/debugged.
    public string? LegendCardId { get; set; }
    public string LegendRawName { get; set; } = "";
    public int Standing { get; set; }
    public DateTimeOffset ImportedAt { get; set; }

    public CommunityTournamentEntity Tournament { get; set; } = null!;
    public CardEntity? LegendCard { get; set; }
    public ICollection<CommunityDeckCardEntity> Cards { get; set; } = [];
}
