using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace RiftBoundTracker.App.Services.Rules;

public sealed record RulesExplanationSettings(string ApiKey, string BaseUrl, string Model);
public sealed record RulesExplanationConfigurationStatus(bool Configured, string BaseUrl, string Model, string? KeyHint);

/// <summary>
/// Storage for the optional Ask Rules explanation provider — DPAPI-encrypted at rest, same pattern
/// as TopDeckSettingsService/PricingSettingsService. Unlike those, "configured" means a BaseUrl is
/// set, not that an API key exists: pointing at a local model server (Ollama/LM Studio's
/// OpenAI-compatible endpoint) needs no key at all. Nothing is pre-filled — the app never assumes
/// the user wants a specific paid provider; it only activates once they explicitly set one up.
/// </summary>
public sealed class RulesExplanationSettingsService(IWebHostEnvironment env, ILogger<RulesExplanationSettingsService> logger)
{
    private const string ApiKeyEnvironmentVariable = "RULES_EXPLANATION_API_KEY";
    private const string BaseUrlEnvironmentVariable = "RULES_EXPLANATION_BASE_URL";
    private const string ModelEnvironmentVariable = "RULES_EXPLANATION_MODEL";
    private string SettingsPath => Path.Combine(env.ContentRootPath, "App_Data", "rules-explanation.dat");

    public RulesExplanationConfigurationStatus GetStatus()
    {
        var settings = GetSettings();
        return settings is null
            ? new RulesExplanationConfigurationStatus(false, "", "", null)
            : new RulesExplanationConfigurationStatus(true, settings.BaseUrl, settings.Model, Hint(settings.ApiKey));
    }

    public RulesExplanationSettings? GetSettings()
    {
        var envBaseUrl = Environment.GetEnvironmentVariable(BaseUrlEnvironmentVariable);
        if (!string.IsNullOrWhiteSpace(envBaseUrl))
        {
            return new RulesExplanationSettings(
                Environment.GetEnvironmentVariable(ApiKeyEnvironmentVariable) ?? "",
                envBaseUrl.Trim(),
                Environment.GetEnvironmentVariable(ModelEnvironmentVariable)?.Trim() is { Length: > 0 } m ? m : "gpt-4o-mini");
        }

        return TryReadStored();
    }

    public void SaveSettings(string apiKey, string baseUrl, string model)
    {
        baseUrl = baseUrl.Trim().TrimEnd('/');
        if (baseUrl.Length == 0)
            throw new ArgumentException("Enter the base URL of an OpenAI-compatible chat completions API.", nameof(baseUrl));

        model = string.IsNullOrWhiteSpace(model) ? "gpt-4o-mini" : model.Trim();

        Directory.CreateDirectory(Path.GetDirectoryName(SettingsPath)!);
        var json = JsonSerializer.Serialize(new RulesExplanationSettings(apiKey.Trim(), baseUrl, model));
        var protectedBytes = ProtectedData.Protect(Encoding.UTF8.GetBytes(json), optionalEntropy: null, DataProtectionScope.CurrentUser);
        File.WriteAllBytes(SettingsPath, protectedBytes);
    }

    public void ClearStoredSettings()
    {
        if (File.Exists(SettingsPath))
            File.Delete(SettingsPath);
    }

    private RulesExplanationSettings? TryReadStored()
    {
        if (!File.Exists(SettingsPath)) return null;
        try
        {
            var protectedBytes = File.ReadAllBytes(SettingsPath);
            var bytes = ProtectedData.Unprotect(protectedBytes, optionalEntropy: null, DataProtectionScope.CurrentUser);
            return JsonSerializer.Deserialize<RulesExplanationSettings>(Encoding.UTF8.GetString(bytes));
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Could not decrypt the locally stored Ask Rules explanation settings");
            return null;
        }
    }

    private static string? Hint(string key) => string.IsNullOrEmpty(key) ? null : key.Length <= 8 ? "configured" : $"...{key[^4..]}";
}
