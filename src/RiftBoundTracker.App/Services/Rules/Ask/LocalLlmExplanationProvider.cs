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
    IWebHostEnvironment env, RulesLocalAiSettingsService settings, ILogger<LocalLlmExplanationProvider> logger)
    : IRulesExplanationProvider, IDisposable
{
    private const string SystemPrompt = """
        You are a rules-reference assistant for the Riftbound trading card game. Answer only from
        the official rules evidence supplied below. If the evidence does not clearly establish the
        answer, say so plainly instead of guessing. Never invent a ruling that isn't supported by
        the evidence. Prefer current Core Rules over Tournament Rules, errata, or historical
        material when they overlap. Clearly distinguish what a rule directly says from any
        interpretation you're making. Keep the answer concise — a few sentences, not an essay.
        """;

    private readonly SemaphoreSlim _gate = new(1, 1);
    private ModelParams? _modelParams;
    private LLamaWeights? _weights;
    private bool _loadFailed;

    public bool IsConfigured => settings.IsEnabled() && !_loadFailed && FindModelPath() is not null;

    public async Task<RulesGeneratedAnswer> ExplainAsync(RulesExplanationContext context, CancellationToken ct = default)
    {
        if (!settings.IsEnabled())
            return new RulesGeneratedAnswer(null, false, "Local AI explanations are turned off.");

        var modelPath = FindModelPath();
        if (modelPath is null)
            return new RulesGeneratedAnswer(null, false, "No local model file found under Models/.");

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
            };

            var output = new StringBuilder();
            await foreach (var token in session.ChatAsync(new ChatHistory.Message(AuthorRole.User, BuildUserMessage(context)), inferenceParams)
                .WithCancellation(ct))
                output.Append(token);

            var answer = StripTrailingAntiPrompt(output.ToString(), inferenceParams.AntiPrompts);
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
        if (_weights is not null) return true;
        try
        {
            _modelParams = new ModelParams(modelPath) { ContextSize = 2048, GpuLayerCount = 0 };
            _weights = LLamaWeights.LoadFromFile(_modelParams);
            return true;
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Failed to load local AI model from {Path}", modelPath);
            _loadFailed = true;
            return false;
        }
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

    private static string BuildUserMessage(RulesExplanationContext context)
    {
        var evidenceText = string.Join("\n\n", context.Evidence.Select(e =>
            $"[{(e.Hit.RuleNumber is not null ? $"Rule {e.Hit.RuleNumber}" : e.Hit.Title)}] " +
            $"({e.Hit.Document.Authority}{(e.Hit.Document.Current ? "" : ", historical")}) {e.Hit.Title}\n{e.Hit.Snippet}"));

        var cardText = context.CardContext.Count > 0
            ? "\n\nThe question is specifically about this card: " + string.Join(", ", context.CardContext.Select(c => c.Name))
            : "";

        return $"Question: {context.Question}{cardText}\n\nRules evidence:\n{evidenceText}";
    }

    public string? FindModelPath()
    {
        var dir = Path.Combine(env.ContentRootPath, "Models");
        return Directory.Exists(dir) ? Directory.EnumerateFiles(dir, "*.gguf").FirstOrDefault() : null;
    }

    public void Dispose()
    {
        _weights?.Dispose();
        _gate.Dispose();
    }
}
