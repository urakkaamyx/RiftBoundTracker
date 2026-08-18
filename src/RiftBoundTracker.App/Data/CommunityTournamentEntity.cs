namespace RiftBoundTracker.App.Data;

public class CommunityTournamentEntity
{
    public int Id { get; set; }
    public string ExternalTournamentId { get; set; } = "";
    public string Name { get; set; } = "";
    public string Format { get; set; } = "";
    public DateTimeOffset StartDate { get; set; }
    public int ParticipantCount { get; set; }
    public DateTimeOffset ImportedAt { get; set; }

    public ICollection<CommunityDeckEntity> Decks { get; set; } = [];
}
