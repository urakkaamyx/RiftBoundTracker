namespace RiftBoundTracker.App.Services.PlayOnline;

/// <summary>
/// The Emulator passcode isn't a stored secret - it's a scheme the three players already share:
/// one of the 6 rune types plus Colorless, cycling Sunday through Saturday in the same order the
/// rest of the app already lists domains in (see DOMAIN_COLOR in app.js). Knowing today's word is
/// what proves you're one of the three, not a password anyone had to configure.
/// </summary>
public static class RuneDailyPasscode
{
    private static readonly string[] WeeklySequence = ["Fury", "Calm", "Order", "Mind", "Body", "Chaos", "Colorless"];

    public static string TodayName(DateTimeOffset? now = null) => WeeklySequence[(int)(now ?? DateTimeOffset.Now).DayOfWeek];

    public static bool Verify(string? attempt, DateTimeOffset? now = null) =>
        !string.IsNullOrWhiteSpace(attempt) && string.Equals(attempt.Trim(), TodayName(now), StringComparison.OrdinalIgnoreCase);
}
