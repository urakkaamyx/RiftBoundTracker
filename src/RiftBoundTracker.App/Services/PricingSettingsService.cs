using System.Security.Cryptography;
using System.Text;

namespace RiftBoundTracker.App.Services;

public record PricingConfigurationStatus(bool Configured, string Provider, string Source, string? KeyHint);

public sealed class PricingSettingsService(IWebHostEnvironment env, ILogger<PricingSettingsService> logger)
{
    private const string EnvironmentVariable = "JUSTTCG_API_KEY";
    private string SettingsPath => Path.Combine(env.ContentRootPath, "App_Data", "pricing-key.dat");

    public PricingConfigurationStatus GetStatus()
    {
        var environmentKey = Environment.GetEnvironmentVariable(EnvironmentVariable);
        if (!string.IsNullOrWhiteSpace(environmentKey))
            return new PricingConfigurationStatus(true, "JustTCG", "environment", Hint(environmentKey));

        var stored = TryReadStoredKey();
        return string.IsNullOrWhiteSpace(stored)
            ? new PricingConfigurationStatus(false, "JustTCG", "not configured", null)
            : new PricingConfigurationStatus(true, "JustTCG", "encrypted local setting", Hint(stored));
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
            throw new ArgumentException("Enter a valid JustTCG API key.", nameof(apiKey));

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
            logger.LogWarning(ex, "Could not decrypt the locally stored pricing API key");
            return null;
        }
    }

    private static string Hint(string key) => key.Length <= 8 ? "configured" : $"...{key[^4..]}";
}
