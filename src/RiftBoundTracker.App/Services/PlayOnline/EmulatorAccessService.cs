using Microsoft.EntityFrameworkCore;
using RiftBoundTracker.App.Data;

namespace RiftBoundTracker.App.Services.PlayOnline;

/// <summary>
/// Whether this install has proven it knows today's RiftCode. Persisted (not just held in the
/// browser) so it survives a page reload or app restart within the same day, but GrantedOn is
/// checked against today's date on every read - the grant itself expires at midnight, it isn't a
/// one-time unlock. This is also the server-side check MatchHub relies on before hosting/joining a
/// room, since that's the real security boundary once the room is exposed to the internet.
/// </summary>
public sealed class EmulatorAccessService(AppDbContext db)
{
    public async Task<bool> HasAccessTodayAsync(CancellationToken ct = default)
    {
        var row = await db.EmulatorAccess.FindAsync([1], ct);
        return row is { HasAccess: true } && row.GrantedOn == DateOnly.FromDateTime(DateTimeOffset.Now.Date);
    }

    public async Task<bool> TryVerifyAsync(string? attempt, CancellationToken ct = default)
    {
        if (!RuneDailyPasscode.Verify(attempt)) return false;
        var row = await db.EmulatorAccess.FindAsync([1], ct);
        if (row is null)
        {
            row = new EmulatorAccessEntity();
            db.EmulatorAccess.Add(row);
        }
        row.HasAccess = true;
        row.GrantedOn = DateOnly.FromDateTime(DateTimeOffset.Now.Date);
        await db.SaveChangesAsync(ct);
        return true;
    }
}
