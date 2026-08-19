using System.Text.Json;

namespace RiftBoundTracker.App.Services.Rules;

/// <summary>
/// Whether to attempt AI explanations at all, and which of LocalAiModelCatalog's models to use.
/// There's no key or URL to configure — models ship with the app (see LocalLlmExplanationProvider)
/// — enabling this is purely a resource-cost opt-in/out, since loading a ~1GB model into memory and
/// running CPU inference has a real cost on a low-end machine that a user might reasonably want to
/// avoid. Off by default for that reason; Ask Rules works fully either way (see
/// NullRulesExplanationProvider fallback behavior).
/// </summary>
public sealed class RulesLocalAiSettingsService(IWebHostEnvironment env)
{
    private string SettingsPath => Path.Combine(env.ContentRootPath, "App_Data", "local-ai-settings.json");

    private JsonElement? ReadSettings()
    {
        if (!File.Exists(SettingsPath)) return null;
        try
        {
            return JsonSerializer.Deserialize<JsonElement>(File.ReadAllText(SettingsPath));
        }
        catch
        {
            return null;
        }
    }

    public bool IsEnabled()
    {
        var settings = ReadSettings();
        return settings is { } s && s.TryGetProperty("enabled", out var enabled) && enabled.GetBoolean();
    }

    public void SetEnabled(bool enabled) => Write(enabled, GetSelectedModelId());

    // Older settings files (before multi-model support) have no "selectedModelId" property at
    // all — falls back to the catalog default, which is exactly the one model that existed back
    // then, so nothing changes behaviorally for an existing install.
    public string GetSelectedModelId()
    {
        var settings = ReadSettings();
        if (settings is { } s && s.TryGetProperty("selectedModelId", out var id) && id.GetString() is { } value)
            return LocalAiModelCatalog.Resolve(value).Id;
        return LocalAiModelCatalog.DefaultModelId;
    }

    public void SetSelectedModelId(string modelId) => Write(IsEnabled(), LocalAiModelCatalog.Resolve(modelId).Id);

    private void Write(bool enabled, string selectedModelId)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(SettingsPath)!);
        File.WriteAllText(SettingsPath, JsonSerializer.Serialize(new { enabled, selectedModelId }));
    }
}
