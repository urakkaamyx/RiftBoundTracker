using System.Net.Http;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace RiftBoundTracker.App.Services.Rules;

/// <summary>
/// Calls a standard OpenAI-compatible "/chat/completions" endpoint — covers real OpenAI, and also
/// a locally-hosted model via Ollama/LM Studio's OpenAI-compatible server (both the "OpenAI" and
/// "Local Model" options the architecture doc names, doc section 26, from one implementation).
/// Only ever sends the question plus the evidence this app already retrieved locally — never a
/// live web search, never anything beyond what RulesEvidenceService found (doc section 25).
/// </summary>
public sealed class OpenAiCompatibleExplanationProvider(
    IHttpClientFactory httpClientFactory, RulesExplanationSettingsService settings, ILogger<OpenAiCompatibleExplanationProvider> logger)
    : IRulesExplanationProvider
{
    private const string SystemPrompt = """
        You are a rules-reference assistant for the Riftbound trading card game. Answer only from
        the official rules evidence supplied below. If the evidence does not clearly establish the
        answer, say so plainly instead of guessing. Never invent a ruling that isn't supported by
        the evidence. Prefer current Core Rules over Tournament Rules, errata, or historical
        material when they overlap. Clearly distinguish what a rule directly says from any
        interpretation you're making. Keep the answer concise — a few sentences, not an essay.
        """;

    public bool IsConfigured => settings.GetSettings() is not null;

    public async Task<RulesGeneratedAnswer> ExplainAsync(RulesExplanationContext context, CancellationToken ct = default)
    {
        var config = settings.GetSettings();
        if (config is null) return new RulesGeneratedAnswer(null, false, "Not configured.");

        var evidenceText = string.Join("\n\n", context.Evidence.Select(e =>
            $"[{(e.Hit.RuleNumber is not null ? $"Rule {e.Hit.RuleNumber}" : e.Hit.Title)}] " +
            $"({e.Hit.Document.Authority}{(e.Hit.Document.Current ? "" : ", historical")}) {e.Hit.Title}\n{e.Hit.Snippet}"));

        var cardText = context.CardContext.Count > 0
            ? "\n\nThe question is specifically about this card: " + string.Join(", ", context.CardContext.Select(c => c.Name))
            : "";

        var userMessage = $"Question: {context.Question}{cardText}\n\nRules evidence:\n{evidenceText}";

        try
        {
            var client = httpClientFactory.CreateClient("rules-explanation");
            using var request = new HttpRequestMessage(HttpMethod.Post, $"{config.BaseUrl}/chat/completions");
            if (!string.IsNullOrWhiteSpace(config.ApiKey))
                request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", config.ApiKey);
            request.Content = JsonContent.Create(new ChatCompletionRequest(
                config.Model,
                [new ChatMessage("system", SystemPrompt), new ChatMessage("user", userMessage)],
                0.2));

            using var response = await client.SendAsync(request, ct);
            if (!response.IsSuccessStatusCode)
            {
                var body = await response.Content.ReadAsStringAsync(ct);
                logger.LogWarning("Ask Rules explanation provider returned {Status}: {Body}", (int)response.StatusCode, body);
                return new RulesGeneratedAnswer(null, false, $"Explanation provider returned {(int)response.StatusCode}.");
            }

            var payload = await response.Content.ReadFromJsonAsync<ChatCompletionResponse>(cancellationToken: ct);
            var text = payload?.Choices?.FirstOrDefault()?.Message?.Content?.Trim();
            return string.IsNullOrWhiteSpace(text)
                ? new RulesGeneratedAnswer(null, false, "Explanation provider returned an empty response.")
                : new RulesGeneratedAnswer(text, true, null);
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Ask Rules explanation provider call failed");
            return new RulesGeneratedAnswer(null, false, ex.Message);
        }
    }

    private sealed record ChatMessage(string Role, string Content);
    private sealed record ChatCompletionRequest(
        string Model, List<ChatMessage> Messages, double Temperature);

    private sealed class ChatCompletionResponse
    {
        [JsonPropertyName("choices")] public List<ChatChoice>? Choices { get; set; }
    }
    private sealed class ChatChoice
    {
        [JsonPropertyName("message")] public ChatChoiceMessage? Message { get; set; }
    }
    private sealed class ChatChoiceMessage
    {
        [JsonPropertyName("content")] public string? Content { get; set; }
    }
}
