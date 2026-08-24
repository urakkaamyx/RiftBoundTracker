using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace RiftBoundTracker.App.Services;

public record RiftKeepServerSettings(string ServerUrl, string Token, string Tier, DateTimeOffset ExpiresAt, string? DiscordUsername);

/// <summary>
/// Local, per-install storage for this client's connection to a RiftKeep server — the base URL to
/// call, and the bearer token issued by that server's Discord sign-in flow (see
/// DiscordSignInService). Same DPAPI-protected-file pattern as PricingSettingsService's JustTCG
/// key: this token is exactly the kind of secret that must never leave this machine except as an
/// Authorization header on a request to the configured server itself.
/// </summary>
public sealed class RiftKeepServerSettingsService(IWebHostEnvironment env, ILogger<RiftKeepServerSettingsService> logger)
{
    private string SettingsPath => Path.Combine(env.ContentRootPath, "App_Data", "riftkeep-server.dat");

    public RiftKeepServerSettings? GetSettings()
    {
        if (!File.Exists(SettingsPath)) return null;
        try
        {
            var protectedBytes = File.ReadAllBytes(SettingsPath);
            var bytes = ProtectedData.Unprotect(protectedBytes, optionalEntropy: null, DataProtectionScope.CurrentUser);
            return JsonSerializer.Deserialize<RiftKeepServerSettings>(bytes, new JsonSerializerOptions(JsonSerializerDefaults.Web));
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Could not decrypt the locally stored RiftKeep server settings");
            return null;
        }
    }

    /// <summary>
    /// True only once a server is configured AND the stored token hasn't expired — the two ways a
    /// client can end up back in "not connected" state (never signed in, or a Restricted member's
    /// grace period ran out and no fresh token could be issued).
    /// </summary>
    public bool IsConnected()
    {
        var settings = GetSettings();
        return settings is not null && settings.ExpiresAt > DateTimeOffset.UtcNow;
    }

    public void Save(RiftKeepServerSettings settings)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(SettingsPath)!);
        var bytes = JsonSerializer.SerializeToUtf8Bytes(settings, new JsonSerializerOptions(JsonSerializerDefaults.Web));
        var protectedBytes = ProtectedData.Protect(bytes, optionalEntropy: null, DataProtectionScope.CurrentUser);
        File.WriteAllBytes(SettingsPath, protectedBytes);
    }

    public void Clear()
    {
        if (File.Exists(SettingsPath))
            File.Delete(SettingsPath);
    }
}
