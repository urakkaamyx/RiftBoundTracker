namespace RiftBoundTracker.App.Data;

// Singleton row (Id is always 1) tracking the last Rules Hub sync — separate from SyncStateEntity
// (card catalog) and CommunitySyncStateEntity (TopDeck.gg), same one-row-per-subsystem pattern.
public class RulesSyncStateEntity
{
    public int Id { get; set; } = 1;
    public DateTimeOffset? LastCheckAt { get; set; }
    public DateTimeOffset? LastSuccessfulSyncAt { get; set; }
    public bool LastSyncOk { get; set; }

    public int DocumentsIndexed { get; set; }
    public int RulesIndexed { get; set; }
    public int KeywordsIndexed { get; set; }
    public int ErrataIndexed { get; set; }
    public int LegalityEntriesIndexed { get; set; }

    public string? LastError { get; set; }
}
