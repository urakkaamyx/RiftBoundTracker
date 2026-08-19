namespace RiftBoundTracker.App.Services.Rules;

public sealed record LocalAiModelOption(string Id, string DisplayName, string Description, string ReleaseTag, long ApproxBytes);

/// <summary>
/// Every local model Ask Rules can offer, each fine-tuned on the same Riftbound rules corpus (see
/// scripts/training/) and hosted as its own GitHub release tag so a new option ships independently
/// of app releases — same pattern LocalAiModelService already used for a single model, just keyed
/// by Id now instead of assuming there's only ever one. Qwen2.5 1.5B stays the default: smallest
/// footprint, and what most existing installs already have downloaded. Qwen3.5 2B is offered
/// alongside it, not in place of it — same LLamaSharp/llama.cpp runtime already pinned in this
/// project supports it (confirmed: LLamaSharp 0.27.0's own release notes list Qwen3.5 support), so
/// no dependency change was needed to add it.
/// </summary>
public static class LocalAiModelCatalog
{
    public const string DefaultModelId = "qwen2.5-1.5b";

    public static readonly IReadOnlyList<LocalAiModelOption> Options =
    [
        new(DefaultModelId, "Qwen2.5 1.5B", "The original Ask Rules model — smallest download and fastest per-question.",
            "ask-rules-model-v1", 940_000_000),
        new("qwen3.5-2b", "Qwen3.5 2B", "A newer-generation model — a somewhat larger download, generally more reliable answers.",
            "ask-rules-model-qwen3.5-2b-v1", 1_300_000_000),
    ];

    public static LocalAiModelOption Resolve(string? modelId) =>
        Options.FirstOrDefault(o => o.Id == modelId) ?? Options.First(o => o.Id == DefaultModelId);
}
