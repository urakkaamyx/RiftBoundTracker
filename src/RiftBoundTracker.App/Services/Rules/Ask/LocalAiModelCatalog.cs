namespace RiftBoundTracker.App.Services.Rules;

public sealed record LocalAiModelOption(string Id, string DisplayName, string Description, string ReleaseTag, long ApproxBytes);

/// <summary>
/// Every local model Ask Rules can offer, each fine-tuned on the same Riftbound rules corpus (see
/// scripts/training/) and hosted as its own GitHub release tag so a new option ships independently
/// of app releases — same pattern LocalAiModelService already used for a single model, just keyed
/// by Id now instead of assuming there's only ever one. Qwen2.5 1.5B stays the default: smallest
/// footprint, and what most existing installs already have downloaded. Qwen3 1.7B is offered
/// alongside it, not in place of it — a newer generation, benchmarked to outperform Qwen2.5 1.5B
/// (and even Qwen2.5 3B on some evals) despite the small size difference.
///
/// Deliberately Qwen3, not Qwen3.5 — Qwen3.5's small checkpoints turned out to be multimodal
/// vision-language models under the hood (a real `vision_config` block, plus experimental hybrid
/// linear-attention/Mamba layers — confirmed by loading the actual HF config, not assumed from
/// marketing copy), neither of which this text-only use case needs, and the hybrid architecture is
/// new enough that llama.cpp/GGUF support for it can't be assumed reliable yet. Qwen3 is a plain
/// `Qwen3ForCausalLM` text model with the same standard attention every other supported model here
/// uses, and has had mature llama.cpp support for a long time.
/// </summary>
public static class LocalAiModelCatalog
{
    public const string DefaultModelId = "qwen2.5-1.5b";

    public static readonly IReadOnlyList<LocalAiModelOption> Options =
    [
        new(DefaultModelId, "Qwen2.5 1.5B", "The original Ask Rules model — smallest download and fastest per-question.",
            "ask-rules-model-v1", 940_000_000),
        new("qwen3-1.7b", "Qwen3 1.7B", "A newer-generation model — a somewhat larger download, generally more reliable answers.",
            "ask-rules-model-qwen3-1.7b-v1", 1_100_000_000),
    ];

    public static LocalAiModelOption Resolve(string? modelId) =>
        Options.FirstOrDefault(o => o.Id == modelId) ?? Options.First(o => o.Id == DefaultModelId);
}
