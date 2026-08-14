using Microsoft.EntityFrameworkCore;
using RiftBoundTracker.App.Data;

namespace RiftBoundTracker.App.Services;

public record CatalogSyncStatus(
    bool Running, string? CurrentSet, int SetsDone, int SetsTotal, int CardsDone,
    DateTimeOffset? LastSyncedAt, int TotalCards, int TotalSets);

/// <summary>
/// Orchestrates fetching every known set (via <see cref="RiftcodexClient.GetAllSetsAsync"/>) and
/// caching it locally, replacing the old "type a set code and sync it yourself" flow. Progress is
/// tracked in a static in-memory snapshot rather than the database — a restart mid-sync just starts
/// a fresh run, which is cheap and safe since <see cref="CardCacheService.SyncSetAsync"/> upserts by
/// card ID rather than replacing anything.
/// </summary>
public class CatalogSyncService(
    RiftcodexClient riftcodex,
    CardCacheService cache,
    AppDbContext db,
    ILogger<CatalogSyncService> logger)
{
    public const int CurrentContentRevision = 1;
    // Shared across scoped instances (one per request) since sync runs as a single background task
    // outliving any individual request scope.
    private static volatile bool _running;
    private static string? _currentSet;
    private static int _setsDone;
    private static int _setsTotal;
    private static int _cardsDone;
    private static readonly SemaphoreSlim RunGate = new(1, 1);

    public async Task<bool> TrySyncAllAsync(CancellationToken ct = default)
    {
        if (!await RunGate.WaitAsync(0, ct))
            return false; // already running

        _running = true;
        _currentSet = null;
        _setsDone = 0;
        _cardsDone = 0;
        try
        {
            var sets = new List<RiftcodexSetListItem>();
            await foreach (var set in riftcodex.GetAllSetsAsync(ct: ct))
                sets.Add(set);
            _setsTotal = sets.Count;

            foreach (var set in sets)
            {
                ct.ThrowIfCancellationRequested();
                _currentSet = set.Name;
                var synced = await cache.SyncSetAsync(set.SetId, progress: null, ct);
                _cardsDone += synced;
                _setsDone++;

                // Stay gentle on the bot-protected upstream API between sets — RiftcodexClient
                // already retries/backs off within a single set's pagination.
                await Task.Delay(TimeSpan.FromMilliseconds(500), ct);
            }

            await SaveSyncStateAsync(ok: true, sets.Count, _cardsDone, ct);
            return true;
        }
        catch (OperationCanceledException)
        {
            throw;
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Full-catalog sync failed");
            await SaveSyncStateAsync(ok: false, _setsTotal, _cardsDone, ct);
            return false;
        }
        finally
        {
            _running = false;
            _currentSet = null;
            RunGate.Release();
        }
    }

    private async Task SaveSyncStateAsync(bool ok, int setsKnown, int cardsSynced, CancellationToken ct)
    {
        var state = await db.SyncState.FindAsync([1], ct) ?? new SyncStateEntity { Id = 1 };
        state.LastFullSyncAt = DateTimeOffset.UtcNow;
        state.LastFullSyncOk = ok;
        state.TotalSetsKnown = setsKnown;
        state.TotalCardsSynced = cardsSynced;
        if (ok)
            state.CatalogContentRevision = CurrentContentRevision;
        if (db.Entry(state).State == EntityState.Detached)
            db.SyncState.Add(state);
        await db.SaveChangesAsync(ct);
    }

    public async Task<CatalogSyncStatus> GetStatusAsync(CancellationToken ct = default)
    {
        var state = await db.SyncState.FindAsync([1], ct);
        var totalCards = await db.Cards.CountAsync(ct);
        var totalSets = state?.TotalSetsKnown ?? 0;

        return new CatalogSyncStatus(
            _running, _currentSet, _setsDone, _setsTotal, _cardsDone,
            state?.LastFullSyncAt, totalCards, totalSets);
    }

    public async Task<bool> HasEverSyncedAsync(CancellationToken ct = default)
    {
        var state = await db.SyncState.FindAsync([1], ct);
        return state is { LastFullSyncOk: true };
    }

    public async Task<bool> NeedsContentRefreshAsync(CancellationToken ct = default)
    {
        var state = await db.SyncState.FindAsync([1], ct);
        return state is { LastFullSyncOk: true } && state.CatalogContentRevision < CurrentContentRevision;
    }
}
