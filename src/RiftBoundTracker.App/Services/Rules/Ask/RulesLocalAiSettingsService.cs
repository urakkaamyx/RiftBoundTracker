using System.Text.Json;

namespace RiftBoundTracker.App.Services.Rules;

public sealed record RulesLocalAiStatusDto(bool Enabled, bool ModelAvailable, string? ModelFile, long? ModelBytes);

/// <summary>
/// Whether to attempt AI explanations at all. There's no key, URL, or model choice to configure —
/// the model ships with the app (see LocalLlmExplanationProvider) — this is purely a resource-cost
/// opt-in/out, since loading a ~1GB model into memory and running CPU inference has a real cost on
/// a low-end machine that a user might reasonably want to avoid. Off by default for that reason;
/// Ask Rules works fully either way (see NullRulesExplanationProvider fallback behavior).
/// </summary>
public sealed class RulesLocalAiSettingsService(IWebHostEnvironment env)
{
    private string SettingsPath => Path.Combine(env.ContentRootPath, "App_Data", "local-ai-settings.json");

    public bool IsEnabled()
    {
        if (!File.Exists(SettingsPath)) return false;
        try
        {
            var json = File.ReadAllText(SettingsPath);
            return JsonSerializer.Deserialize<JsonElement>(json).GetProperty("enabled").GetBoolean();
        }
        catch
        {
            return false;
        }
    }

    public void SetEnabled(bool enabled)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(SettingsPath)!);
        File.WriteAllText(SettingsPath, JsonSerializer.Serialize(new { enabled }));
    }
}
