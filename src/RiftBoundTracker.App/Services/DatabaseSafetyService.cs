using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;
using RiftBoundTracker.App.Data;

namespace RiftBoundTracker.App.Services;

public record DatabaseSafetyStatus(
    bool DatabaseExists,
    string DatabasePath,
    string? LastBackupPath,
    DateTimeOffset? LastMigrationAt,
    int CardCount,
    int OwnedCards,
    int OwnedCopies,
    string Integrity);

public sealed class DatabaseSafetyService(
    AppDbContext db,
    ILogger<DatabaseSafetyService> logger)
{
    private static DatabaseSafetyStatus? _lastStatus;

    public DatabaseSafetyStatus? LastStatus => _lastStatus;

    public async Task MigrateSafelyAsync(string dbPath, CancellationToken ct = default)
    {
        var existed = File.Exists(dbPath);
        var before = existed ? await ReadFingerprintAsync(dbPath, ct) : DatabaseFingerprint.Empty;
        var pending = (await db.Database.GetPendingMigrationsAsync(ct)).ToList();
        string? backupPath = null;

        if (pending.Count > 0 && existed)
        {
            backupPath = await CreateVerifiedBackupAsync(dbPath, before, ct);
            logger.LogInformation(
                "Database backup verified before {Count} migration(s): {Source} -> {Backup}",
                pending.Count, dbPath, backupPath);
        }

        try
        {
            await db.Database.MigrateAsync(ct);
            var after = await ReadFingerprintAsync(dbPath, ct);

            if (!string.Equals(after.Integrity, "ok", StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException($"Migrated database failed integrity check: {after.Integrity}");

            if (existed && (after.CardCount != before.CardCount
                            || after.OwnedCards != before.OwnedCards
                            || after.OwnedCopies != before.OwnedCopies))
            {
                throw new InvalidDataException(
                    "Migration changed protected collection totals " +
                    $"(cards {before.CardCount}->{after.CardCount}, " +
                    $"owned cards {before.OwnedCards}->{after.OwnedCards}, " +
                    $"owned copies {before.OwnedCopies}->{after.OwnedCopies}).");
            }

            _lastStatus = new DatabaseSafetyStatus(
                true, dbPath, backupPath, pending.Count > 0 ? DateTimeOffset.UtcNow : null,
                after.CardCount, after.OwnedCards, after.OwnedCopies, after.Integrity);

            logger.LogInformation(
                "Database ready and verified at {Path}: {Cards} cards, {OwnedCards} owned entries, {OwnedCopies} copies",
                dbPath, after.CardCount, after.OwnedCards, after.OwnedCopies);
        }
        catch (Exception migrationError) when (backupPath is not null)
        {
            logger.LogCritical(migrationError, "Database migration verification failed; restoring verified backup {Backup}", backupPath);
            await db.Database.CloseConnectionAsync();
            SqliteConnection.ClearAllPools();
            await RestoreVerifiedBackupAsync(backupPath, dbPath, ct);

            var restored = await ReadFingerprintAsync(dbPath, ct);
            if (restored != before)
            {
                throw new InvalidDataException(
                    $"Migration failed and the automatic restore could not be verified. " +
                    $"The verified backup remains at {backupPath}.", migrationError);
            }

            throw new InvalidOperationException(
                $"The database migration failed. Your original database was restored and a verified backup is at {backupPath}.",
                migrationError);
        }
    }

    private static async Task RestoreVerifiedBackupAsync(string backupPath, string destinationPath, CancellationToken ct)
    {
        await using var backup = new SqliteConnection($"Data Source={backupPath};Mode=ReadOnly");
        await using var destination = new SqliteConnection($"Data Source={destinationPath};Mode=ReadWrite");
        await backup.OpenAsync(ct);
        await destination.OpenAsync(ct);
        backup.BackupDatabase(destination);
        await destination.CloseAsync();
        await backup.CloseAsync();
    }

    private async Task<string> CreateVerifiedBackupAsync(
        string sourcePath,
        DatabaseFingerprint expected,
        CancellationToken ct)
    {
        var backupDir = Path.Combine(Path.GetDirectoryName(sourcePath)!, "backups");
        Directory.CreateDirectory(backupDir);

        var stamp = DateTime.UtcNow.ToString("yyyyMMdd-HHmmss-fff");
        var backupPath = Path.Combine(backupDir, $"riftbound-{stamp}.db");

        await using var source = new SqliteConnection($"Data Source={sourcePath};Mode=ReadOnly");
        await using var destination = new SqliteConnection($"Data Source={backupPath};Mode=ReadWriteCreate");
        await source.OpenAsync(ct);
        await destination.OpenAsync(ct);
        source.BackupDatabase(destination);
        await destination.CloseAsync();
        await source.CloseAsync();

        var actual = await ReadFingerprintAsync(backupPath, ct);
        if (actual != expected)
        {
            throw new InvalidDataException(
                $"Database backup verification failed. Source fingerprint {expected}; backup fingerprint {actual}.");
        }

        return backupPath;
    }

    private static async Task<DatabaseFingerprint> ReadFingerprintAsync(string path, CancellationToken ct)
    {
        await using var connection = new SqliteConnection($"Data Source={path};Mode=ReadOnly");
        await connection.OpenAsync(ct);

        var integrity = await ScalarStringAsync(connection, "PRAGMA integrity_check;", ct) ?? "unknown";
        var cardsTable = await ScalarLongAsync(connection,
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='Cards';", ct) > 0;

        if (!cardsTable)
            return new DatabaseFingerprint(0, 0, 0, integrity);

        var cardCount = await ScalarLongAsync(connection, "SELECT COUNT(*) FROM Cards;", ct);
        var ownedCards = await ScalarLongAsync(connection, "SELECT COUNT(*) FROM Cards WHERE OwnedCount > 0;", ct);
        var ownedCopies = await ScalarLongAsync(connection, "SELECT COALESCE(SUM(OwnedCount), 0) FROM Cards;", ct);
        return new DatabaseFingerprint((int)cardCount, (int)ownedCards, (int)ownedCopies, integrity);
    }

    private static async Task<long> ScalarLongAsync(SqliteConnection connection, string sql, CancellationToken ct)
    {
        await using var command = connection.CreateCommand();
        command.CommandText = sql;
        return Convert.ToInt64(await command.ExecuteScalarAsync(ct));
    }

    private static async Task<string?> ScalarStringAsync(SqliteConnection connection, string sql, CancellationToken ct)
    {
        await using var command = connection.CreateCommand();
        command.CommandText = sql;
        return Convert.ToString(await command.ExecuteScalarAsync(ct));
    }

    private record DatabaseFingerprint(int CardCount, int OwnedCards, int OwnedCopies, string Integrity)
    {
        public static DatabaseFingerprint Empty { get; } = new(0, 0, 0, "ok");
    }
}
