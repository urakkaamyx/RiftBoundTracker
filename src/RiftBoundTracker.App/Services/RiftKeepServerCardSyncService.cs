using Microsoft.EntityFrameworkCore;
using RiftBoundTracker.App.Data;

namespace RiftBoundTracker.App.Services;

/// <summary>
/// The server-backed replacement for CardCacheService's direct riftcodex.com sync: once a RiftKeep
/// server is configured (RiftKeepServerSettingsService.IsConnected()), this is what actually
/// populates the local catalog — CatalogSyncService prefers this over the direct path whenever a
/// server is connected (see CatalogSyncService.TrySyncAllAsync).
///
/// Only ever touches catalog fields on the local CardEntity (Name, SetId, Rarity, text, image,
/// etc.) — OwnedCount, HologramCount, BinderCount, IsFavorite, and Notes are this client's own
/// personal collection data and are never overwritten by a catalog sync, from either source.
///
/// This keeps the client fully usable offline after the first successful sync: the local SQLite
/// cache this writes into is exactly the same table CardCacheService.QueryAsync and everything
/// else in the app already reads from — nothing downstream needs to know or care whether a given
/// row came from riftcodex.com directly or by way of a RiftKeep server.
/// </summary>
public sealed class RiftKeepServerCardSyncService(
    AppDbContext db,
    RiftKeepServerClient serverClient,
    ImageHashService hasher,
    IWebHostEnvironment env,
    ILogger<RiftKeepServerCardSyncService> logger)
{
    private string ImagesRoot => Path.Combine(env.ContentRootPath, "App_Data", "images");

    public async Task<int> SyncAsync(CancellationToken ct = default)
    {
        var remoteCards = await serverClient.GetAllCardsAsync(ct);
        Directory.CreateDirectory(ImagesRoot);

        var synced = 0;
        foreach (var remote in remoteCards)
        {
            ct.ThrowIfCancellationRequested();
            var existing = await db.Cards.FindAsync([remote.Id], ct);
            var entity = existing ?? new CardEntity { Id = remote.Id };

            entity.Name = remote.Name;
            entity.CollectorNumber = remote.CollectorNumber;
            entity.CollectorCode = remote.CollectorCode;
            entity.SetId = remote.SetId;
            entity.SetLabel = remote.SetLabel;
            entity.Type = remote.Type;
            entity.Supertype = remote.Supertype;
            entity.Rarity = remote.Rarity;
            entity.DomainsCsv = remote.DomainsCsv;
            entity.TextRich = remote.TextRich;
            entity.TextPlain = remote.TextPlain;
            entity.Flavour = remote.Flavour;
            entity.ImageUrl = remote.ImageUrl;
            entity.Artist = remote.Artist;
            entity.Orientation = remote.Orientation;
            entity.TcgplayerId = remote.TcgplayerId;
            entity.Energy = remote.Energy;
            entity.Might = remote.Might;
            entity.Power = remote.Power;
            entity.IsSyntheticToken = remote.IsSyntheticToken;
            entity.CachedAt = DateTimeOffset.UtcNow;
            if (existing is null)
            {
                entity.OwnedCount = 0;
                entity.UpdatedAt = DateTimeOffset.UtcNow;
                db.Cards.Add(entity);
            }

            await DownloadImageAsync(entity, remote.LocalImagePath, ct);
            synced++;
        }

        await db.SaveChangesAsync(ct);
        logger.LogInformation("Synced {Count} cards from RiftKeep server", synced);
        return synced;
    }

    // Images are fetched from the RiftKeep server's own /card-images path — never from the
    // original external CDN URL (ImageUrl) — so this client makes no direct calls to any image
    // host once a server is configured, same rule as the card data itself.
    private async Task DownloadImageAsync(CardEntity entity, string? remoteLocalImagePath, CancellationToken ct)
    {
        if (string.IsNullOrEmpty(remoteLocalImagePath))
            return;

        var previousLocalPath = entity.LocalImagePath;
        var fileName = Path.GetFileName(remoteLocalImagePath);
        var localPath = Path.Combine(ImagesRoot, fileName);

        if (!File.Exists(localPath))
        {
            try
            {
                var bytes = await serverClient.DownloadImageAsync(remoteLocalImagePath, ct);
                await File.WriteAllBytesAsync(localPath, bytes, ct);
            }
            catch (Exception ex)
            {
                logger.LogWarning(ex, "Failed to download image for {CardId} from RiftKeep server", entity.Id);
                entity.LocalImagePath = previousLocalPath;
                return;
            }
        }

        entity.LocalImagePath = $"/card-images/{fileName}";

        if (entity.ImageHash is null)
        {
            await using var fs = File.OpenRead(localPath);
            entity.ImageHash = await hasher.ComputeDHashAsync(fs, ct);
        }
    }
}
