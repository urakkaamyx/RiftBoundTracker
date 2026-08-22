using System.Net;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace RiftBoundTracker.App.Services.Rules;

public sealed record EngineNamedCard(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("name")] string Name,
    [property: JsonPropertyName("effectiveText")] string? EffectiveText);

public sealed record AskResult(
    bool Ok,
    string Question,
    string Answer,
    string? DeterministicAnswer,
    List<EngineNamedCard> NamedCards,
    List<string> ClarifyingQuestions,
    JsonElement Raw);

public sealed record EngineCard(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("name")] string Name,
    [property: JsonPropertyName("setId")] string SetId,
    [property: JsonPropertyName("setLabel")] string? SetLabel,
    [property: JsonPropertyName("collectorCode")] string CollectorCode,
    [property: JsonPropertyName("type")] string Type,
    [property: JsonPropertyName("effectiveText")] string? EffectiveText,
    [property: JsonPropertyName("imageUrl")] string? ImageUrl,
    [property: JsonPropertyName("officialErrataTimeline")] List<JsonElement>? OfficialErrataTimeline,
    [property: JsonPropertyName("citationId")] string? CitationId);

public sealed record CardLookupResult(bool Ok, int MatchCount, List<EngineCard> Matches);

public sealed record EngineRule(
    [property: JsonPropertyName("ruleId")] string RuleId,
    [property: JsonPropertyName("text")] string Text,
    [property: JsonPropertyName("exampleText")] string? ExampleText,
    [property: JsonPropertyName("majorSectionTitle")] string? MajorSectionTitle,
    [property: JsonPropertyName("sourceId")] string? SourceId);

public sealed record RuleLookupResult(bool Ok, EngineRule? Rule, string? CitationId);

/// <summary>
/// Typed client for the Rules Engine's Product API v1 (http://127.0.0.1:8765) — the sole way this
/// app talks to rules/card authority, per the engine's own integration guide: no direct SQLite or
/// canonical-JSON access, no reimplemented adjudication, Product API only. Two response shapes
/// (ask, card) are fully typed since they directly drive Ask Rules routing; the rest stay as
/// JsonElement pass-throughs for now (search/evidence/sources/changes feed the "browse rules" UI,
/// which is Phase 2 — no need to lock in their shape before that work actually starts).
///
/// RulesEngineSidecarService owns the process; this owns the calls. Callers are expected to have
/// already called EnsureRunningAsync — this client doesn't start the sidecar itself.
/// </summary>
public sealed class RulesEngineClient(IHttpClientFactory httpClientFactory)
{
    private HttpClient CreateClient()
    {
        var http = httpClientFactory.CreateClient();
        http.BaseAddress = RulesEngineSidecarService.BaseAddress;
        return http;
    }

    // The engine's HTTP server (a minimal http.server-based implementation — see api_http.py's
    // manual Content-Length check) rejects any POST without an explicit Content-Length header.
    // HttpClient.PostAsJsonAsync's default JsonContent didn't send one in real testing against it
    // (confirmed directly: curl with the same payload worked, PostAsJsonAsync got a 411). Building
    // the request from a pre-materialized byte array via ByteArrayContent guarantees a real,
    // known-upfront Content-Length instead of leaving the framing to chance; pinning the request to
    // HTTP/1.1 rules out an HTTP/2 cleartext negotiation attempt against a server that only ever
    // speaks HTTP/1.1.
    private static async Task<JsonElement> PostJsonAsync(HttpClient http, string path, object body, CancellationToken ct)
    {
        var bytes = JsonSerializer.SerializeToUtf8Bytes(body);
        using var request = new HttpRequestMessage(HttpMethod.Post, path)
        {
            Version = HttpVersion.Version11,
            VersionPolicy = HttpVersionPolicy.RequestVersionExact,
            Content = new ByteArrayContent(bytes),
        };
        request.Content.Headers.ContentType = new System.Net.Http.Headers.MediaTypeHeaderValue("application/json");
        using var response = await http.SendAsync(request, ct);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<JsonElement>(cancellationToken: ct);
    }

    public async Task<AskResult> AskAsync(string question, CancellationToken ct = default)
    {
        var http = CreateClient();
        var raw = await PostJsonAsync(http, "v1/ask", new { question }, ct);

        var ok = raw.TryGetProperty("ok", out var okProp) ? okProp.ValueKind != JsonValueKind.False : true;
        var answer = raw.TryGetProperty("answer", out var answerProp) ? answerProp.GetString() ?? "" : "";
        var deterministicAnswer = raw.TryGetProperty("deterministicAnswer", out var detProp) ? detProp.GetString() : null;

        var namedCards = new List<EngineNamedCard>();
        if (raw.TryGetProperty("namedCards", out var namedCardsProp) && namedCardsProp.ValueKind == JsonValueKind.Array)
            foreach (var card in namedCardsProp.EnumerateArray())
            {
                var id = card.TryGetProperty("id", out var idP) ? idP.GetString() : null;
                var name = card.TryGetProperty("name", out var nameP) ? nameP.GetString() : null;
                var text = card.TryGetProperty("effectiveText", out var textP) ? textP.GetString() : null;
                if (id is not null && name is not null) namedCards.Add(new EngineNamedCard(id, name, text));
            }

        var clarifying = new List<string>();
        if (raw.TryGetProperty("clarifyingQuestions", out var clarifyProp) && clarifyProp.ValueKind == JsonValueKind.Array)
            foreach (var q in clarifyProp.EnumerateArray())
                if (q.ValueKind == JsonValueKind.String) clarifying.Add(q.GetString()!);

        return new AskResult(ok, question, answer, deterministicAnswer, namedCards, clarifying, raw);
    }

    public async Task<CardLookupResult> GetCardAsync(string idOrExactName, CancellationToken ct = default)
    {
        var http = CreateClient();
        using var response = await http.GetAsync($"v1/cards/{Uri.EscapeDataString(idOrExactName)}", ct);
        if (response.StatusCode == System.Net.HttpStatusCode.NotFound)
            return new CardLookupResult(false, 0, []);
        response.EnsureSuccessStatusCode();
        var body = await response.Content.ReadFromJsonAsync<CardApiBody>(cancellationToken: ct)
            ?? new CardApiBody(false, 0, []);
        return new CardLookupResult(body.Ok, body.MatchCount, body.Matches);
    }

    public async Task<RuleLookupResult> GetRuleAsync(string family, string ruleId, CancellationToken ct = default)
    {
        var http = CreateClient();
        using var response = await http.GetAsync($"v1/rules/{Uri.EscapeDataString(family)}/{Uri.EscapeDataString(ruleId)}", ct);
        if (response.StatusCode == System.Net.HttpStatusCode.NotFound)
            return new RuleLookupResult(false, null, null);
        response.EnsureSuccessStatusCode();
        var body = await response.Content.ReadFromJsonAsync<RuleApiBody>(cancellationToken: ct)
            ?? new RuleApiBody(false, null, null);
        return new RuleLookupResult(body.Ok, body.Rule, body.CitationId);
    }

    public async Task<JsonElement> SearchAsync(string query, string? kind = null, int limit = 20, int offset = 0, CancellationToken ct = default)
    {
        var http = CreateClient();
        var qs = $"v1/search?q={Uri.EscapeDataString(query)}&limit={limit}&offset={offset}";
        if (!string.IsNullOrWhiteSpace(kind)) qs += $"&kind={Uri.EscapeDataString(kind)}";
        return await http.GetFromJsonAsync<JsonElement>(qs, ct);
    }

    public async Task<JsonElement> GetEvidenceAsync(string evidenceId, CancellationToken ct = default) =>
        await CreateClient().GetFromJsonAsync<JsonElement>($"v1/evidence/{Uri.EscapeDataString(evidenceId)}", ct);

    public async Task<JsonElement> GetSourcesAsync(CancellationToken ct = default) =>
        await CreateClient().GetFromJsonAsync<JsonElement>("v1/sources", ct);

    public async Task<JsonElement> GetChangesAsync(string family, string? sourceId = null, CancellationToken ct = default)
    {
        var qs = $"v1/changes?family={Uri.EscapeDataString(family)}";
        if (!string.IsNullOrWhiteSpace(sourceId)) qs += $"&sourceId={Uri.EscapeDataString(sourceId)}";
        return await CreateClient().GetFromJsonAsync<JsonElement>(qs, ct);
    }

    private sealed record CardApiBody(
        [property: JsonPropertyName("ok")] bool Ok,
        [property: JsonPropertyName("matchCount")] int MatchCount,
        [property: JsonPropertyName("matches")] List<EngineCard> Matches);

    private sealed record RuleApiBody(
        [property: JsonPropertyName("ok")] bool Ok,
        [property: JsonPropertyName("rule")] EngineRule? Rule,
        [property: JsonPropertyName("citationId")] string? CitationId);
}
