using System.Text.Json;

namespace RiftBoundTracker.App.Services.Rules;

/// <summary>
/// Whether Ask Rules is turned on at all. There's no key, URL, or model choice to configure —
/// enabling this just starts the Rules Engine sidecar (RulesEngineSidecarService) on first use.
/// Off by default since the sidecar is a real resident process a user might reasonably want to
/// avoid running until they actually want Ask Rules.
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

    public void SetEnabled(bool enabled)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(SettingsPath)!);
        File.WriteAllText(SettingsPath, JsonSerializer.Serialize(new { enabled }));
    }
}
