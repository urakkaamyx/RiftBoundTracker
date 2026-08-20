namespace RiftBoundTracker.App.Services.Rules;

public sealed record LocalAiModelOption(string Id, string DisplayName, string Description, string ReleaseTag, long ApproxBytes);

/// <summary>
/// Every local model Ask Rules can offer, each fine-tuned on the same Riftbound rules corpus (see
/// scripts/training/) and hosted as its own GitHub release tag so a new option ships independently
/// of app releases — same pattern LocalAiModelService already used for a single model, just keyed
/// by Id now instead of assuming there's only ever one. Qwen2.5 1.5B is the default and, for now,
/// the only option.
///
/// A Qwen3 1.7B option was added, trained, and shipped here briefly (v1.24.0-v1.24.1) — pulled
/// after a real user question ("If my card has 8 might and someone does 2 damage, does that make
/// my might 6...") reproducibly (3/3 attempts) got an incoherent, self-contradictory non-answer
/// from it despite RulesEvidenceService retrieving exactly the right rules (143.2.a, 142.4.b — both
/// state plainly that damage is marked separately from Might). Qwen2.5 answered the same question
/// correctly on the first try.
///
/// A second Qwen3 1.7B was later fine-tuned specifically on the adjudicate/explain task shape
/// (scripts/training/generate_adjudication_dataset.py) across four training rounds — each round
/// fixed some failures and introduced different ones without the overall reliability ever climbing,
/// the signature of a real capability ceiling for a 1.7B model on this task, not something one more
/// round fixes. The actual fix that worked: RulesCuratedRulingService checks a hand-verified +
/// riftboundfaq.com-sourced lookup table BEFORE any model call for the class of questions that has a
/// knowable answer at all — the model's job shrank to "phrase a question the curated table doesn't
/// cover," not "decide any ruling." See RulesCuratedRulingService's own doc comment.
/// </summary>
public static class LocalAiModelCatalog
{
    public const string DefaultModelId = "qwen2.5-1.5b";

    public static readonly IReadOnlyList<LocalAiModelOption> Options =
    [
        new(DefaultModelId, "Qwen2.5 1.5B", "The Ask Rules model — runs entirely on this machine.",
            "ask-rules-model-v1", 940_000_000),
    ];

    public static LocalAiModelOption Resolve(string? modelId) =>
        Options.FirstOrDefault(o => o.Id == modelId) ?? Options.First(o => o.Id == DefaultModelId);
}
