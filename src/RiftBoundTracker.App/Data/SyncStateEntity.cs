namespace RiftBoundTracker.App.Data;

// Singleton row (Id is always 1) tracking whether/when a full-catalog sync last completed
// successfully, so the app knows not to re-walk every set on every startup.
public class SyncStateEntity
{
    public int Id { get; set; } = 1;
    public DateTimeOffset? LastFullSyncAt { get; set; }
    public bool LastFullSyncOk { get; set; }
    public int TotalSetsKnown { get; set; }
    public int TotalCardsSynced { get; set; }
    public int CatalogContentRevision { get; set; }
}
