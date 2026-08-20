using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;
using RiftBoundTracker.App.Data;

namespace RiftBoundTracker.App.Services;

public record PurgeOptions(
    bool OwnedCollection, bool TradeBinder, bool Favorites, bool CardNotes,
    bool Decks, bool PriceHistory, bool PriceQueue);

public record PurgeResult(
    string? BackupPath, int OwnedCardsReset, int BinderCardsReset, int FavoritesCleared,
    int NotesCleared, int DecksDeleted, int PriceSnapshotsDeleted, int PriceQueueCleared);

/// <summary>
/// Resets user-owned data (owned counts, trade binder, favorites, notes, decks, price history/
/// queue) without touching the card catalog itself — the Cards table's rows always stay exactly as
/// synced; only the per-card OwnedCount/BinderCount/IsFavorite/Notes columns on it are ever reset,
/// never a row deleted. Every other table this touches (Decks, PriceSnapshots, PriceQueue) is
/// exclusively the user's own data, never catalog/reference data (Rules, CardErrata, community
/// sync, etc. are all untouched, on purpose — those come back from a normal sync, this isn't what
/// "reset my collection" means).
///
/// Takes a full verified-by-copy backup before making any change, same mechanism
/// DatabaseSafetyService uses before a migration — this is a genuinely destructive, one-way action
/// from the app's own perspective (no in-app undo), so a file-level escape hatch always exists.
/// </summary>
public sealed class PurgeService(AppDbContext db, IWebHostEnvironment env, ILogger<PurgeService> logger)
{
    public async Task<PurgeResult> PurgeAsync(PurgeOptions options, CancellationToken ct = default)
    {
        if (!options.OwnedCollection && !options.TradeBinder && !options.Favorites && !options.CardNotes
            && !options.Decks && !options.PriceHistory && !options.PriceQueue)
            throw new InvalidOperationException("Select at least one category to reset.");

        var backupPath = await CreateBackupAsync(ct);

        var ownedReset = 0;
        var binderReset = 0;
        var favoritesCleared = 0;
        var notesCleared = 0;
        var decksDeleted = 0;
        var snapshotsDeleted = 0;
        var queueCleared = 0;

        // OwnedCollection implies clearing BinderCount too — a trade-binder entry with zero owned
        // copies is a contradiction the rest of the app never allows (BinderCount is always clamped
        // to OwnedCount on every other write path), so this reset can't leave that state behind.
        if (options.OwnedCollection)
        {
            ownedReset = await db.Cards.CountAsync(c => c.OwnedCount != 0, ct);
            binderReset = await db.Cards.CountAsync(c => c.BinderCount != 0, ct);
            await db.Cards.ExecuteUpdateAsync(s => s
                .SetProperty(c => c.OwnedCount, 0)
                .SetProperty(c => c.BinderCount, 0), ct);
        }
        else if (options.TradeBinder)
        {
            binderReset = await db.Cards.Where(c => c.BinderCount != 0)
                .ExecuteUpdateAsync(s => s.SetProperty(c => c.BinderCount, 0), ct);
        }

        if (options.Favorites)
            favoritesCleared = await db.Cards.Where(c => c.IsFavorite)
                .ExecuteUpdateAsync(s => s.SetProperty(c => c.IsFavorite, false), ct);

        if (options.CardNotes)
            notesCleared = await db.Cards.Where(c => c.Notes != null)
                .ExecuteUpdateAsync(s => s.SetProperty(c => c.Notes, (string?)null), ct);

        if (options.Decks)
            decksDeleted = await db.Decks.ExecuteDeleteAsync(ct); // cascades to DeckCards

        if (options.PriceHistory)
            snapshotsDeleted = await db.PriceSnapshots.ExecuteDeleteAsync(ct);

        if (options.PriceQueue)
            queueCleared = await db.PriceQueue.ExecuteDeleteAsync(ct);

        logger.LogWarning(
            "Data reset performed — owned:{Owned} binder:{Binder} favorites:{Fav} notes:{Notes} " +
            "decks:{Decks} priceHistory:{Price} priceQueue:{Queue}. Backup at {Backup}",
            ownedReset, binderReset, favoritesCleared, notesCleared, decksDeleted, snapshotsDeleted, queueCleared, backupPath);

        return new PurgeResult(
            backupPath, ownedReset, binderReset, favoritesCleared, notesCleared,
            decksDeleted, snapshotsDeleted, queueCleared);
    }

    private async Task<string?> CreateBackupAsync(CancellationToken ct)
    {
        var dbPath = Path.Combine(env.ContentRootPath, "App_Data", "riftbound.db");
        if (!File.Exists(dbPath)) return null;

        var backupDir = Path.Combine(env.ContentRootPath, "App_Data", "backups");
        Directory.CreateDirectory(backupDir);
        var stamp = DateTime.UtcNow.ToString("yyyyMMdd-HHmmss-fff");
        var backupPath = Path.Combine(backupDir, $"riftbound-{stamp}-pre-reset.db");

        await using var source = new SqliteConnection($"Data Source={dbPath};Mode=ReadOnly");
        await using var destination = new SqliteConnection($"Data Source={backupPath};Mode=ReadWriteCreate");
        await source.OpenAsync(ct);
        await destination.OpenAsync(ct);
        source.BackupDatabase(destination);
        await destination.CloseAsync();
        await source.CloseAsync();

        return backupPath;
    }
}
