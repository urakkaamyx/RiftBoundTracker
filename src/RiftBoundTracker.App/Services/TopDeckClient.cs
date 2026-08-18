using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace RiftBoundTracker.App.Services;

public sealed class TopDeckTournament
{
    [JsonPropertyName("TID")] public string Tid { get; set; } = "";
    [JsonPropertyName("tournamentName")] public string TournamentName { get; set; } = "";
    public string Game { get; set; } = "";
    public string Format { get; set; } = "";
    public long StartDate { get; set; }
    public List<TopDeckStanding> Standings { get; set; } = [];
}

public sealed class TopDeckStanding
{
    public string? Name { get; set; }
    public int? Standing { get; set; }
    public string? Decklist { get; set; }

    // Kept as raw JsonElement per section rather than a strongly-typed dictionary: deckObj
    // includes a non-card "metadata" section ({game, format, importedFrom} — plain strings, not
    // {id, count} card entries) alongside the real Legend/Champion/Runes/Battlefields/Mainboard/
    // Sideboard sections. Deserializing everything as {id,count} up front would throw on that
    // section; callers must skip "metadata" by key before parsing a section's contents.
    public Dictionary<string, JsonElement>? DeckObj { get; set; }
}

public sealed class TopDeckCardRef
{
    public string Id { get; set; } = "";
    public int Count { get; set; }
}

/// <summary>
/// Thin wrapper around TopDeck.gg's tournament API — confirmed during planning: POST
/// /api/v2/tournaments with {game, format, start (unix seconds)}, an "Authorization: {key}"
/// header (no "Bearer " prefix — that returns 401). A missing "start" field 500s instead of
/// 400ing, so it's always sent even for "give me everything" queries.
/// </summary>
public sealed class TopDeckClient(IHttpClientFactory httpClientFactory, TopDeckSettingsService settings, ILogger<TopDeckClient> logger)
{
    public bool IsConfigured => !string.IsNullOrWhiteSpace(settings.GetApiKey());

    public async Task<List<TopDeckTournament>> GetTournamentsAsync(
        DateTimeOffset start, string format = "Constructed", CancellationToken ct = default)
    {
        var apiKey = settings.GetApiKey();
        if (string.IsNullOrWhiteSpace(apiKey))
            throw new InvalidOperationException("TopDeck.gg is not configured. Add an API key in Settings.");

        using var request = new HttpRequestMessage(HttpMethod.Post, "/api/v2/tournaments");
        request.Headers.Add("Authorization", apiKey);
        request.Content = JsonContent.Create(new
        {
            game = "Riftbound",
            format,
            start = start.ToUnixTimeSeconds(),
        });

        var client = httpClientFactory.CreateClient("topdeck");
        using var response = await client.SendAsync(request, ct);
        if (!response.IsSuccessStatusCode)
        {
            var body = await response.Content.ReadAsStringAsync(ct);
            logger.LogWarning("TopDeck.gg request failed with {Status}: {Body}", (int)response.StatusCode, body);
            throw new InvalidOperationException($"TopDeck.gg returned {(int)response.StatusCode}. Check the API key and rate limits.");
        }

        return await response.Content.ReadFromJsonAsync<List<TopDeckTournament>>(cancellationToken: ct) ?? [];
    }
}
