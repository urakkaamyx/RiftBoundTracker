using System.Security.Cryptography;
using System.Text;

namespace RiftBoundTracker.App.Services;

public record TopDeckConfigurationStatus(bool Configured, string Source, string? KeyHint);

public sealed class TopDeckSettingsService(IWebHostEnvironment env, ILogger<TopDeckSettingsService> logger)
{
    private const string EnvironmentVariable = "TOPDECK_API_KEY";
    private string SettingsPath => Path.Combine(env.ContentRootPath, "App_Data", "topdeck-key.dat");

    public TopDeckConfigurationStatus GetStatus()
    {
        var environmentKey = Environment.GetEnvironmentVariable(EnvironmentVariable);
        if (!string.IsNullOrWhiteSpace(environmentKey))
            return new TopDeckConfigurationStatus(true, "environment", Hint(environmentKey));

        var stored = TryReadStoredKey();
        return string.IsNullOrWhiteSpace(stored)
            ? new TopDeckConfigurationStatus(false, "not configured", null)
            : new TopDeckConfigurationStatus(true, "encrypted local setting", Hint(stored));
    }

    public string? GetApiKey()
    {
        var environmentKey = Environment.GetEnvironmentVariable(EnvironmentVariable);
        return string.IsNullOrWhiteSpace(environmentKey) ? TryReadStoredKey() : environmentKey.Trim();
    }

    public void SaveApiKey(string apiKey)
    {
        apiKey = apiKey.Trim();
        if (apiKey.Length < 8)
            throw new ArgumentException("Enter a valid TopDeck.gg API key.", nameof(apiKey));

        Directory.CreateDirectory(Path.GetDirectoryName(SettingsPath)!);
        var protectedBytes = ProtectedData.Protect(
            Encoding.UTF8.GetBytes(apiKey), optionalEntropy: null, DataProtectionScope.CurrentUser);
        File.WriteAllBytes(SettingsPath, protectedBytes);
    }

    public void ClearStoredApiKey()
    {
        if (File.Exists(SettingsPath))
            File.Delete(SettingsPath);
    }

    private string? TryReadStoredKey()
    {
        if (!File.Exists(SettingsPath)) return null;
        try
        {
            var protectedBytes = File.ReadAllBytes(SettingsPath);
            var bytes = ProtectedData.Unprotect(protectedBytes, optionalEntropy: null, DataProtectionScope.CurrentUser);
            return Encoding.UTF8.GetString(bytes);
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Could not decrypt the locally stored TopDeck API key");
            return null;
        }
    }

    private static string Hint(string key) => key.Length <= 8 ? "configured" : $"...{key[^4..]}";
}
