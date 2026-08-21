using System.Text;
using System.Text.Json;
using LLama;
using LLama.Common;
using LLama.Sampling;
using LLama.Transformers;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using RiftBoundTracker.App.Data;

namespace RiftBoundTracker.App.Services.Rules;

/// <summary>
/// The model reasons over evidence a deterministic system already gathered for it — it never
/// invents its own search text. Relevance judgment (which rules, which cards) belongs entirely to
/// RulesQuestionService/RulesEvidenceService, the same retrieval this app's other explanation paths
/// already build on and that's been through multiple real bug-fix rounds this session. An earlier
/// version of this provider let the model call a free-text search_rules(query)/search_cards(name)
/// tool instead — real testing caught it improvising SQL-style wildcards the tool never documented
/// ("*Hunt*"), which slipped past the exact-keyword fast path and returned the wrong rule entirely.
/// The model was doing a worse job of relevance judgment than the system already does elsewhere.
///
/// So: the caller (RulesAnswerService) runs the normal evidence pipeline first and hands the result
/// in as `evidence` — that's simply given to the model on turn one, no tool call involved, since
/// it isn't optional or discretionary. The only tools left are narrow, exact-identifier lookups —
/// get_rule(rule_number), get_card(name), and get_keyword(name) — for the rare case that bundle
/// didn't already cover something the question or the evidence itself named, or a term the model
/// needs defined to actually reason about it. All three are deterministic: they either resolve to
/// one real rule/card/keyword or they don't, with no free text and no ranking involved, so there's
/// no room for the model to "arbitrarily" look anything up.
///
/// Why a raw base model at all: four rounds of fine-tuning a model specifically on the
/// adjudicate/explain task shape never got reliability past a real ceiling (see
/// RulesAnswerService's own comment on AdjudicationPipelineEnabled) — and directly probing the
/// RESIDENT fine-tuned model against a simple tool-call prompt showed it doesn't attempt one at
/// all; it just answers as if the tool didn't exist, ignoring the instruction outright. Probing the
/// RAW, un-fine-tuned base model with the identical prompt got a correctly-formed tool call on the
/// first try. The narrow single-pass fine-tuning didn't fail to teach tool use — it measurably
/// destroyed general instruction-following the base model already had. This provider is built
/// against that raw base model specifically, not the fine-tuned "ask-rules-model-v1"
/// LocalLlmExplanationProvider uses — RulesCuratedRulingService already covers the highest-value
/// known questions with zero model involvement; this is for whatever that lookup table doesn't
/// cover, and the model's job here is reasoning over data it was given, not memorizing rules
/// content into its own weights or deciding what's relevant.
/// </summary>
public sealed class RulesToolAgentProvider(
    RulesLocalAiSettingsService settings, LocalAiModelService modelService,
    IServiceScopeFactory scopeFactory, ILogger<RulesToolAgentProvider> logger) : IDisposable
{
    private const string SystemPrompt = """
        You are a rules assistant for the Riftbound trading card game. You do not know Riftbound's
        rules or cards from memory — answer only from the evidence you're given.

        Below the question, you'll see a list of evidence items (labeled E1, E2, ...) that a
        separate lookup system already gathered for this exact question — real rule text and card
        data pulled from the actual rulebook and card catalog, not something you found yourself.
        Read all of it before answering. Base your answer on it and cite the E-ids you used.

        If that evidence is missing something specific, you may call one of these tools to fetch
        it. They do not search: they only return something if you give an exact rule number, exact
        card name, or a real Riftbound keyword/term, so there's no point guessing or trying
        variations.

        - get_rule(rule_number): returns that rule's full text, only if the number matches a real
          rule exactly.
        - get_card(name): returns that card's printed text, current format legality, and any
          official errata, only if the name matches a real card exactly.
        - get_keyword(name): returns the official definition of a Riftbound keyword or rules term
          (e.g. "Tank", "Contested", "Hunt") — use this when you understand the question but need
          to actually learn what a term means, not just look up a number you already have.

        To call a tool, output ONLY this, nothing else:
        <tool_call>{"name": "get_rule", "arguments": {"rule_number": "..."}}</tool_call>

        Call at most one tool at a time — you'll see its result before deciding whether to call
        another. Once you have enough to answer, respond in plain language with no tool_call tag.
        If the evidence you were given, plus anything you looked up, still doesn't cover the
        question, say so plainly instead of guessing.

        Your final answer must be a faithful summary of the evidence you were given and anything
        you looked up — reread it before you answer. Do not bring in details, examples, or other
        card/rule names from outside that text, even ones that sound related or that you recall
        from elsewhere. If it doesn't fully answer the question, say what it does say and note the
        gap — never fill it from memory.
        """;

    private readonly SemaphoreSlim _gate = new(1, 1);
    private ModelParams? _modelParams;
    private LLamaWeights? _weights;
    private string? _loadedModelPath;
    private string? _failedModelPath;

    public bool IsConfigured => settings.IsEnabled() && FindModelPath() is { } path && path != _failedModelPath;

    // Separate from LocalLlmExplanationProvider's FindModelPath — this provider is built against
    // the raw base model, not whatever fine-tune LocalAiModelCatalog's selected option points to.
    // TODO(temporary): hardcoded to the local test conversion while validating the tool loop itself
    // — swap to modelService.FindModelPath("qwen2.5-1.5b-base") once that catalog entry is hosted.
    public string? FindModelPath() =>
        File.Exists(TempTestModelPath) ? TempTestModelPath : modelService.FindModelPath("qwen2.5-1.5b-base");

    private const string TempTestModelPath = "G:/Users/Urakka/AppData/Local/Temp/qwen25-base-Q4_K_M.gguf";

    public async Task<RulesGeneratedAnswer> AnswerAsync(
        string question, IReadOnlyList<EvidenceRef> evidence, CancellationToken ct = default)
    {
        if (!settings.IsEnabled())
            return new RulesGeneratedAnswer(null, false, "Local AI explanations are turned off.");
        var modelPath = FindModelPath();
        if (modelPath is null)
            return new RulesGeneratedAnswer(null, false, "The tool-agent base model hasn't been downloaded yet.");

        await _gate.WaitAsync(ct);
        try
        {
            if (!EnsureWeightsLoaded(modelPath))
                return new RulesGeneratedAnswer(null, false, "Could not load the tool-agent base model.");

            using var requestContext = _weights!.CreateContext(_modelParams!);
            var executor = new InteractiveExecutor(requestContext);
            var chatHistory = new ChatHistory();
            chatHistory.AddMessage(AuthorRole.System, SystemPrompt);
            var session = new ChatSession(executor, chatHistory)
                .WithHistoryTransform(new PromptTemplateTransformer(_weights!, withAssistant: true));

            // The evidence a deterministic system already gathered is simply part of the first
            // turn — not something the model has to call a tool to receive, since there's no real
            // choice involved (it always gets the same system-computed bundle for this question).
            var nextMessage = $"Question: {question}\n\nEvidence:\n{FormatEvidence(evidence)}";
            const int maxToolRounds = 4;
            for (var round = 0; round <= maxToolRounds; round++)
            {
                var inferenceParams = new InferenceParams
                {
                    MaxTokens = 400,
                    AntiPrompts = ["User:", "<|im_end|>"],
                    SamplingPipeline = new DefaultSamplingPipeline
                    {
                        Temperature = 0.15f,
                        RepeatPenalty = 1.1f,
                    },
                    OverflowStrategy = LLama.Common.ContextOverflowStrategy.TruncateAndReprefill,
                };

                var output = new StringBuilder();
                await foreach (var token in session.ChatAsync(new ChatHistory.Message(AuthorRole.User, nextMessage), inferenceParams)
                    .WithCancellation(ct))
                    output.Append(token);

                var raw = StripLeadingThinkBlock(output.ToString());
                var toolCall = ExtractToolCall(raw);
                logger.LogDebug("Ask Rules (tools): round {Round} calledTool={CalledTool} raw={Raw}", round, toolCall is not null, raw);

                if (toolCall is null)
                {
                    var final = StripTrailingAntiPrompt(raw, inferenceParams.AntiPrompts);
                    return final.Length == 0
                        ? new RulesGeneratedAnswer(null, false, "The tool-agent model returned an empty response.")
                        : new RulesGeneratedAnswer(final, true, null);
                }

                if (round == maxToolRounds)
                {
                    logger.LogDebug("Ask Rules (tools): hit max tool-call rounds without a final answer");
                    return new RulesGeneratedAnswer(null, false, "The tool-agent model didn't reach a final answer in time.");
                }

                var (name, arguments) = toolCall.Value;
                var result = await RunToolAsync(name, arguments, ct);
                logger.LogDebug("Ask Rules (tools): {Name}({Arguments}) -> {Result}", name, arguments, Cap(result, 300));
                // No native "tool" role in LLamaSharp's AuthorRole (only System/User/Assistant) even
                // though the underlying chat template has one — approximated as a clearly-delimited
                // User turn instead. The system prompt primes the model for this shape specifically.
                nextMessage = $"<tool_response>\n{result}\n</tool_response>";
            }

            return new RulesGeneratedAnswer(null, false, "The tool-agent model didn't reach a final answer in time.");
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Tool-agent explanation failed");
            return new RulesGeneratedAnswer(null, false, ex.Message);
        }
        finally
        {
            _gate.Release();
        }
    }

    // Creates a DI scope per tool call rather than injecting AppDbContext/CardCacheService/
    // RulesSearchService/CardTextSymbolCatalogService directly — those are all Scoped (EF Core's own
    // default, matched by the services built on it), and this provider is a Singleton so its model
    // weights stay resident across requests. A Singleton can't hold a Scoped dependency directly
    // (DI throws at startup); creating a fresh scope per call is the standard fix, and also means
    // each tool call sees a clean, uncached DbContext rather than one accumulating state across an
    // entire process lifetime.
    private async Task<string> RunToolAsync(string name, Dictionary<string, string> arguments, CancellationToken ct)
    {
        using var scope = scopeFactory.CreateScope();
        switch (name)
        {
            case "get_rule":
                if (!arguments.TryGetValue("rule_number", out var ruleNumber) || string.IsNullOrWhiteSpace(ruleNumber))
                    return "Error: get_rule requires a non-empty \"rule_number\" argument.";
                return await GetRuleToolAsync(scope.ServiceProvider, ruleNumber, ct);
            case "get_card":
                if (!arguments.TryGetValue("name", out var cardName) || string.IsNullOrWhiteSpace(cardName))
                    return "Error: get_card requires a non-empty \"name\" argument.";
                return await GetCardToolAsync(scope.ServiceProvider, cardName, ct);
            case "get_keyword":
                if (!arguments.TryGetValue("name", out var keywordName) || string.IsNullOrWhiteSpace(keywordName))
                    return "Error: get_keyword requires a non-empty \"name\" argument.";
                return await GetKeywordToolAsync(scope.ServiceProvider, keywordName, ct);
            default:
                return $"Error: unknown tool \"{name}\". Available tools: get_rule, get_card, get_keyword.";
        }
    }

    // Exact-identifier only, never a search: validates the argument matches a real rule-number
    // shape before touching the database at all, then accepts only a MatchType == "RuleNumber"
    // hit — never falls through to RulesSearchService's fuzzy full-text path the way the old
    // free-text search_rules tool could (that's what let the model's own invented "*Hunt*" wildcard
    // slip past the exact-keyword fast path and return the wrong rule entirely).
    private static async Task<string> GetRuleToolAsync(IServiceProvider sp, string ruleNumber, CancellationToken ct)
    {
        var trimmed = ruleNumber.Trim();
        if (!RulesQueryParser.TryParseRuleNumber(trimmed, out var parsed))
            return $"Error: \"{trimmed}\" isn't a valid rule number.";
        var search = sp.GetRequiredService<RulesSearchService>();
        var response = await search.SearchAsync(parsed, currentOnly: true, limit: 1, ct);
        var hit = response.Results.FirstOrDefault(h => h.MatchType == "RuleNumber");
        if (hit is null) return $"No rule numbered {parsed} exists.";
        return $"[Rule {hit.RuleNumber}] ({hit.Document.Authority})\n{Cap(hit.FullText, 1200)}";
    }

    // Conceptual "help me understand this term" lookup — distinct from get_rule (which needs a
    // number the model already has) and search_rules-style free text (which this design deliberately
    // has none of). Still fully deterministic: the name must resolve to a real RuleKeywords entry
    // or one of its known player-slang aliases (the exact same normalize-and-match RulesSearchService
    // itself uses for its own keyword fast path), never a fuzzy/ranked guess. Returns the keyword's
    // canonical definition plus every other rule that references it, same shape RulesEvidenceService
    // already builds for keyword evidence elsewhere in this app.
    private static async Task<string> GetKeywordToolAsync(IServiceProvider sp, string name, CancellationToken ct)
    {
        var db = sp.GetRequiredService<AppDbContext>();
        var normalized = RulesKeywordCatalogService.Normalize(name.Trim());
        var keyword = await db.RuleKeywords
            .Include(k => k.Aliases)
            .FirstOrDefaultAsync(k => k.NormalizedName == normalized || k.Aliases.Any(a => a.NormalizedAlias == normalized), ct);
        if (keyword is null) return $"\"{name.Trim()}\" isn't a known Riftbound keyword or term.";

        var search = sp.GetRequiredService<RulesSearchService>();
        var hits = (await search.SearchByKeywordIdAsync(keyword.Id, currentOnly: true, ct))
            .OrderByDescending(h => h.Score)
            .Take(8);
        var parts = hits.Select(hit =>
        {
            var label = hit.RuleNumber is not null ? $"Rule {hit.RuleNumber}" : hit.Title;
            return $"[{label}] ({hit.Document.Authority})\n{Cap(hit.FullText, 1200)}";
        }).ToList();
        return parts.Count > 0
            ? string.Join("\n\n", parts)
            : $"\"{keyword.Name}\" is a known keyword but has no rules text on file.";
    }

    private static async Task<string> GetCardToolAsync(IServiceProvider sp, string name, CancellationToken ct)
    {
        var cards = sp.GetRequiredService<CardCacheService>();
        var symbols = sp.GetRequiredService<CardTextSymbolCatalogService>();
        var db = sp.GetRequiredService<AppDbContext>();
        var matches = await cards.FindByNameAsync(name, ct);
        if (matches.Count == 0) return $"No card found named \"{name}\".";
        var card = matches[0];
        var parts = new List<string>();
        if (!string.IsNullOrWhiteSpace(card.TextPlain))
            parts.Add($"{card.Name}'s printed text: \"{await symbols.HumanizeAsync(card.TextPlain, ct)}\"");
        var legalities = await db.CardLegalities.Where(l => l.CardId == card.Id && l.IsCurrent).ToListAsync(ct);
        parts.AddRange(legalities.Select(l => $"{card.Name} is {l.Status} in {l.Format}."));
        var errata = await db.CardErrata.Where(e => e.CardId == card.Id && e.IsCurrent).ToListAsync(ct);
        parts.AddRange(errata.Select(e => $"{card.Name} errata — original: \"{e.OriginalText}\", updated: \"{e.CorrectedText}\""));
        return parts.Count > 0 ? string.Join("\n", parts) : $"{card.Name} has no printed text, legality, or errata on file.";
    }

    // Scans for a balanced JSON object after "<tool_call>" rather than regex-matching up to
    // "</tool_call>" — real generation observed during probing cut off (hit MaxTokens/an anti-prompt)
    // before ever emitting the closing tag, even though the JSON payload itself was already complete
    // and well-formed. A brace-balance scan finds the real end of the object regardless of whether
    // the closing tag ever arrives.
    private static (string Name, Dictionary<string, string> Arguments)? ExtractToolCall(string text)
    {
        var start = text.IndexOf("<tool_call>", StringComparison.Ordinal);
        if (start < 0) return null;
        var jsonStart = start + "<tool_call>".Length;
        var depth = 0;
        var end = -1;
        for (var i = jsonStart; i < text.Length; i++)
        {
            if (text[i] == '{') depth++;
            else if (text[i] == '}')
            {
                depth--;
                if (depth == 0) { end = i; break; }
            }
        }
        if (end < 0) return null;
        var jsonText = text[jsonStart..(end + 1)].Trim();
        try
        {
            using var doc = JsonDocument.Parse(jsonText);
            var root = doc.RootElement;
            if (!root.TryGetProperty("name", out var nameProp) || nameProp.ValueKind != JsonValueKind.String)
                return null;
            var args = new Dictionary<string, string>();
            if (root.TryGetProperty("arguments", out var argsProp) && argsProp.ValueKind == JsonValueKind.Object)
                foreach (var prop in argsProp.EnumerateObject())
                    args[prop.Name] = prop.Value.ValueKind == JsonValueKind.String ? prop.Value.GetString()! : prop.Value.GetRawText();
            return (nameProp.GetString()!, args);
        }
        catch (JsonException)
        {
            return null;
        }
    }

    private bool EnsureWeightsLoaded(string modelPath)
    {
        if (_weights is not null && _loadedModelPath == modelPath) return true;
        if (_weights is not null) { _weights.Dispose(); _weights = null; }
        try
        {
            _modelParams = new ModelParams(modelPath) { ContextSize = 6144, GpuLayerCount = 0 };
            _weights = LLamaWeights.LoadFromFile(_modelParams);
            _loadedModelPath = modelPath;
            _failedModelPath = null;
            return true;
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Failed to load tool-agent base model from {Path}", modelPath);
            _failedModelPath = modelPath;
            return false;
        }
    }

    private static string StripLeadingThinkBlock(string text)
    {
        var trimmed = text.TrimStart();
        if (!trimmed.StartsWith("<think>", StringComparison.Ordinal)) return text;
        var closeIndex = trimmed.IndexOf("</think>", StringComparison.Ordinal);
        if (closeIndex >= 0) return trimmed[(closeIndex + "</think>".Length)..].TrimStart();
        return trimmed["<think>".Length..].TrimStart();
    }

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

    // Same bracketed-block shape the (disabled) adjudication pipeline already renders evidence in
    // — reusing a familiar shape rather than inventing a new one for this provider specifically.
    private static string FormatEvidence(IReadOnlyList<EvidenceRef> evidence)
    {
        if (evidence.Count == 0) return "No evidence was found for this question.";
        return string.Join("\n\n", evidence.Select(e =>
            $"[{e.Id}] {e.Label} ({e.Authority}){(e.Current ? "" : " [historical]")}\n{Cap(e.FullText, 1200)}"));
    }

    public void Dispose()
    {
        _weights?.Dispose();
        _gate.Dispose();
    }
}
