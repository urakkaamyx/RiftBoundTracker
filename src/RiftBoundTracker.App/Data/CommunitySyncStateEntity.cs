namespace RiftBoundTracker.App.Data;

// Singleton row (Id is always 1) tracking the last TopDeck.gg community sync — separate from
// SyncStateEntity, which tracks the card catalog sync and has nothing to do with this.
public class CommunitySyncStateEntity
{
    public int Id { get; set; } = 1;
    public DateTimeOffset? LastSyncAt { get; set; }
    public bool LastSyncOk { get; set; }
    public int TournamentCount { get; set; }
    public int DeckCount { get; set; }
    public int UnresolvedCardCount { get; set; }
    public string? LastError { get; set; }
}
