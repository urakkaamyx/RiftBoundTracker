using System.Text;
using LLama;
using LLama.Common;
using LLama.Sampling;
using LLama.Transformers;

namespace RiftBoundTracker.App.Services.Rules;

/// <summary>
/// Fully local plain-language explanation layer for Ask Rules — a small instruct model (GGUF,
/// bundled with the app; see Models/ and scripts/release.ps1) run entirely in-process via
/// llama.cpp bindings. No network call, no API key, no third party: the question and the rules
/// evidence this app already retrieved locally never leave the machine. Registered as a singleton
/// so the model loads once (a couple of seconds) and stays resident for the process lifetime
/// rather than reloading per question.
///
/// A missing chat template was the actual cause of a hallucinated/rambling first attempt during
/// development (verified against the real model directly) — PromptTemplateTransformer applies the
/// GGUF's own embedded template (ChatML for Qwen), which is what actually makes the model follow
/// "answer only from the supplied evidence" instead of free-associating from the prompt text.
/// </summary>
public sealed class LocalLlmExplanationProvider(
    RulesLocalAiSettingsService settings, LocalAiModelService modelService, ILogger<LocalLlmExplanationProvider> logger)
    : IRulesExplanationProvider, IDisposable
{
    private const string SystemPrompt = """
        You are a rules-reference assistant for the Riftbound trading card game. Answer only from
        the official rules evidence supplied below. If the evidence does not clearly establish the
        answer, say so plainly instead of guessing. Never invent a ruling that isn't supported by
        the evidence. Prefer current Core Rules over Tournament Rules, errata, or historical
        material when they overlap. Clearly distinguish what a rule directly says from any
        interpretation you're making. Keep the answer concise — a few sentences, not an essay.
        A card's own printed text is valid evidence of what that card does — if it's supplied below,
        describe the card's effect directly instead of calling the evidence insufficient.
        Rules text is often a conditional built on negations ("applies if X is not Y and Z does not
        W") — before answering, work out literally which side of each "not" the actual situation in
        the question falls on. Getting a negation backwards produces the opposite of the correct
        ruling, which is worse than not answering at all.
        """;

    private readonly SemaphoreSlim _gate = new(1, 1);
    private ModelParams? _modelParams;
    private LLamaWeights? _weights;
    private string? _loadedModelPath;
    private DateTime _loadedModelWriteTimeUtc;
    // Keyed to the path that failed, not a bare bool — switching to a DIFFERENT catalog model
    // after one failed to load must not keep reporting unconfigured for a model that was never
    // actually tried.
    private string? _failedModelPath;

    public bool IsConfigured => settings.IsEnabled() && FindModelPath() is { } path && path != _failedModelPath;

    public async Task<RulesGeneratedAnswer> ExplainAsync(RulesExplanationContext context, CancellationToken ct = default)
    {
        if (!settings.IsEnabled())
            return new RulesGeneratedAnswer(null, false, "Local AI explanations are turned off.");

        var modelPath = FindModelPath();
        if (modelPath is null)
            return new RulesGeneratedAnswer(null, false, "The selected local model hasn't been downloaded yet.");

        await _gate.WaitAsync(ct);
        try
        {
            if (!EnsureWeightsLoaded(modelPath))
                return new RulesGeneratedAnswer(null, false, "Could not load the local model.");

            // A fresh context per question — only the model weights (the big, slow-to-load part)
            // stay resident. Reusing one context's KV cache across questions caused a real
            // 'llama_decode failed: InvalidInputBatch' error once the cache from an earlier
            // question left it without room for the next one; a new context has no such history.
            using var requestContext = _weights!.CreateContext(_modelParams!);
            var executor = new InteractiveExecutor(requestContext);
            var chatHistory = new ChatHistory();
            chatHistory.AddMessage(AuthorRole.System, SystemPrompt);
            var session = new ChatSession(executor, chatHistory)
                .WithHistoryTransform(new PromptTemplateTransformer(_weights!, withAssistant: true));

            var inferenceParams = new InferenceParams
            {
                MaxTokens = 350,
                AntiPrompts = ["User:", "Question:", "<|im_end|>"],
                SamplingPipeline = new DefaultSamplingPipeline { Temperature = 0.2f },
                // A defensive backstop, not the primary defense — BuildUserMessage's own evidence
                // budget is what's supposed to keep prompts under the context size. This just
                // means a case that budget didn't anticipate degrades to a truncated answer
                // instead of a hard ContextOverflowException and no answer at all (a real failure
                // mode hit directly during testing: a single Patch Notes article indexed as one
                // whole-section blob ran to 27,000+ characters as one piece of "evidence").
                OverflowStrategy = LLama.Common.ContextOverflowStrategy.TruncateAndReprefill,
            };

            var output = new StringBuilder();
            await foreach (var token in session.ChatAsync(new ChatHistory.Message(AuthorRole.User, BuildUserMessage(context)), inferenceParams)
                .WithCancellation(ct))
                output.Append(token);

            var answer = StripTrailingAntiPrompt(StripLeadingThinkBlock(output.ToString()), inferenceParams.AntiPrompts);
            return answer.Length == 0
                ? new RulesGeneratedAnswer(null, false, "The local model returned an empty response.")
                : new RulesGeneratedAnswer(answer, true, null);
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Local AI explanation failed");
            return new RulesGeneratedAnswer(null, false, ex.Message);
        }
        finally
        {
            _gate.Release();
        }
    }

    private bool EnsureWeightsLoaded(string modelPath)
    {
        var writeTimeUtc = File.GetLastWriteTimeUtc(modelPath);
        if (_weights is not null && _loadedModelPath == modelPath && _loadedModelWriteTimeUtc == writeTimeUtc) return true;
        // Either nothing loaded yet, the user switched which catalog model is selected
        // (RulesLocalAiSettingsService.SelectedModelId), or re-downloaded the same model to pick up
        // an improved version — the write-time check catches that last case even though the path on
        // disk is unchanged. Swap the resident weights instead of requiring an app restart.
        if (_weights is not null)
        {
            _weights.Dispose();
            _weights = null;
        }
        try
        {
            // 6144, not 4096 — raised again alongside BuildUserMessage's evidence budget (900/5500
            // -> 1400/9000 chars): a real question (Tank's interaction with spell targeting) needed
            // 11 rules to answer properly, and 5500 chars wasn't enough room to fit them all even
            // though retrieval had already found the right ones — evidence was silently dropped by
            // the budget loop, not by retrieval. The bigger context window is what makes the bigger
            // budget actually usable instead of just hitting a llama_decode overflow instead.
            _modelParams = new ModelParams(modelPath) { ContextSize = 6144, GpuLayerCount = 0 };
            _weights = LLamaWeights.LoadFromFile(_modelParams);
            _loadedModelPath = modelPath;
            _loadedModelWriteTimeUtc = writeTimeUtc;
            _failedModelPath = null;
            return true;
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Failed to load local AI model from {Path}", modelPath);
            _failedModelPath = modelPath;
            return false;
        }
    }

    // Qwen3's chat template pre-fills the assistant turn with a "<think>\n\n</think>\n\n" block
    // whenever thinking mode isn't explicitly enabled (confirmed directly in the GGUF's own
    // embedded template) — the model then continues generating its real answer after that, but
    // the literal tag text lands in the output stream same as any other token, so it leaked
    // straight into every answer during testing until this was added. Qwen2.5 has no such
    // template branch, so this is a no-op for it.
    private static string StripLeadingThinkBlock(string text)
    {
        var trimmed = text.TrimStart();
        if (!trimmed.StartsWith("<think>", StringComparison.Ordinal)) return text;
        var closeIndex = trimmed.IndexOf("</think>", StringComparison.Ordinal);
        if (closeIndex >= 0) return trimmed[(closeIndex + "</think>".Length)..].TrimStart();
        // Observed directly: the template's usual "<think>\n\n</think>\n\n" pre-fill sometimes
        // comes back with no closing tag at all before the real answer starts — generation just
        // continues past the empty think block without ever emitting "</think>". Rather than guess
        // where real content begins (there's nothing to reliably anchor on), just drop the literal
        // opening tag itself and keep everything after it.
        return trimmed["<think>".Length..].TrimStart();
    }

    // Anti-prompts stop generation once matched, but the matched text itself can still land in
    // the output stream before the stop takes effect (observed directly: "User:" trailing a real
    // answer during testing) — strip any of them (and anything after) off the end.
    private static string StripTrailingAntiPrompt(string text, IEnumerable<string> antiPrompts)
    {
        var trimmed = text;
        foreach (var antiPrompt in antiPrompts)
        {
            var index = trimmed.IndexOf(antiPrompt, StringComparison.Ordinal);
            if (index >= 0) trimmed = trimmed[..index];
        }
        return trimmed.Trim();
    }

    private static string Cap(string text, int maxChars) =>
        text.Length > maxChars ? text[..maxChars] + "…" : text;

    private static string BuildUserMessage(RulesExplanationContext context)
    {
        // Card evidence is deliberately formatted with the exact same "[Title] (Authority) Title\nText"
        // shape as regular rule evidence below (matching what the training data used, see
        // generate_dataset.py's errata/legality categories) — a differently-shaped evidence block
        // the model never saw during fine-tuning caused it to contradict its own supplied evidence
        // in testing, even though the underlying fact was correct.
        //
        // FullText, not Snippet — Snippet is a 220-char UI preview (RulesSearchService.ToHitAsync),
        // truncated for ~11.5% of rules in the corpus. A rule cut off mid-sentence there was
        // starving the model of evidence it needed to answer correctly even though the retrieval
        // step had found the right rule.
        //
        // That said, FullText is unbounded, and at least one real entry blows past it dramatically:
        // a Patch Notes article is indexed as one whole-section blob (ArticleSectionParser) and can
        // run to tens of thousands of characters — one such entry alone overflowed the model's
        // context window outright during testing, silently losing the answer entirely. PerItemCap
        // keeps any single item from doing that; TotalBudget keeps several merely-long items from
        // adding up to the same problem. Both are generous relative to the old 220-char snippet —
        // this only ever bites entries that were already far outside the normal range for one rule.
        const int perItemCap = 1400;
        const int totalBudget = 9000;
        var used = 0;
        var evidenceParts = new List<string>();
        // CardNotes FIRST, not last — a question about a specific card (its own text, legality, or
        // errata) is directly on-topic for that card no matter how much general rule evidence also
        // matched, so it must never lose the budget race to it. Before this fix, rule evidence (up
        // to 12 items, each up to perItemCap) filled the shared totalBudget first and the loop's
        // own "if (used >= totalBudget) break" could exhaust the budget before ever reaching a
        // card's own evidence, silently dropping it from the prompt entirely — the model would
        // then have no idea the card evidence even existed, however much noise it were.
        foreach (var part in context.CardNotes.Select(c => $"[{c.CardName}] ({c.Authority}) {c.CardName}\n{Cap(c.Note, perItemCap)}")
            .Concat(context.Evidence.Select(e =>
                $"[{(e.Hit.RuleNumber is not null ? $"Rule {e.Hit.RuleNumber}" : e.Hit.Title)}] " +
                $"({e.Hit.Document.Authority}{(e.Hit.Document.Current ? "" : ", historical")}) {e.Hit.Title}\n{Cap(e.Hit.FullText, perItemCap)}")))
        {
            if (used >= totalBudget) break;
            var remaining = totalBudget - used;
            var trimmed = part.Length > remaining ? Cap(part, remaining) : part;
            evidenceParts.Add(trimmed);
            used += trimmed.Length;
        }
        var evidenceText = string.Join("\n\n", evidenceParts);

        // Previously only the card's name reached the model, never its printed text — it could
        // name the card but had nothing to reason from when the question was actually about what
        // the card itself does (e.g. "does this trigger Fury?" needs the card's own text, not just
        // which rules mention Fury generically).
        var cardText = context.CardContext.Count > 0
            ? "\n\nThe question is specifically about this card:\n" + string.Join("\n\n", context.CardContext.Select(c =>
                $"[{c.Name}]" + (string.IsNullOrWhiteSpace(c.Text) ? "" : $"\n{c.Text}")))
            : "";

        return $"Question: {context.Question}{cardText}\n\nRules evidence:\n{evidenceText}";
    }

    public string? FindModelPath() => modelService.FindModelPath(settings.GetSelectedModelId());

    public void Dispose()
    {
        _weights?.Dispose();
        _gate.Dispose();
    }
}
