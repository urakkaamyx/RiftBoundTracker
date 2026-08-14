using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json.Serialization;
using RiftBoundTracker.App.Data;

namespace RiftBoundTracker.App.Services;

public record PriceQuote(
    string CardId, string Provider, string VariantId, string Condition, string Printing,
    string Currency, double MarketPrice, double? Change24Hours, DateTimeOffset? SourceUpdatedAt);

public interface IPriceProvider
{
    string Name { get; }
    bool IsConfigured { get; }
    Task<List<PriceQuote>> GetPricesAsync(IReadOnlyList<CardEntity> cards, CancellationToken ct = default);
}

public sealed class JustTcgPriceProvider(
    IHttpClientFactory httpClientFactory,
    PricingSettingsService settings,
    ILogger<JustTcgPriceProvider> logger) : IPriceProvider
{
    public const int FreeTierBatchSize = 20;
    public string Name => "JustTCG";
    public bool IsConfigured => !string.IsNullOrWhiteSpace(settings.GetApiKey());

    public async Task<List<PriceQuote>> GetPricesAsync(IReadOnlyList<CardEntity> cards, CancellationToken ct = default)
    {
        var apiKey = settings.GetApiKey();
        if (string.IsNullOrWhiteSpace(apiKey))
            throw new InvalidOperationException("Pricing is not configured. Add a JustTCG API key in Settings.");
        if (cards.Count > FreeTierBatchSize)
            throw new ArgumentOutOfRangeException(nameof(cards), $"JustTCG's free tier accepts up to {FreeTierBatchSize} cards per batch.");

        var requested = cards
            .Where(c => !string.IsNullOrWhiteSpace(c.TcgplayerId))
            .ToDictionary(c => c.TcgplayerId!, StringComparer.OrdinalIgnoreCase);
        if (requested.Count == 0) return [];

        using var request = new HttpRequestMessage(HttpMethod.Post, "/v1/cards");
        request.Headers.Add("x-api-key", apiKey);
        request.Content = JsonContent.Create(requested.Keys.Select(id => new
        {
            tcgplayerId = id,
            condition = "Near Mint",
            printing = "Normal",
        }));

        var client = httpClientFactory.CreateClient("justtcg");
        using var response = await client.SendAsync(request, ct);
        if (!response.IsSuccessStatusCode)
        {
            var body = await response.Content.ReadAsStringAsync(ct);
            logger.LogWarning("JustTCG request failed with {Status}: {Body}", (int)response.StatusCode, body);
            throw new InvalidOperationException($"JustTCG returned {(int)response.StatusCode}. Check the API key and rate limits.");
        }

        var payload = await response.Content.ReadFromJsonAsync<JustTcgResponse>(cancellationToken: ct);
        var quotes = new List<PriceQuote>();
        foreach (var item in payload?.Data ?? [])
        {
            if (string.IsNullOrWhiteSpace(item.TcgplayerId)
                || !requested.TryGetValue(item.TcgplayerId, out var localCard))
                continue;

            var variant = item.Variants
                .Where(v => v.Price is >= 0)
                .OrderByDescending(v => string.Equals(v.Language, "English", StringComparison.OrdinalIgnoreCase))
                .ThenByDescending(v => string.Equals(v.Condition, "Near Mint", StringComparison.OrdinalIgnoreCase))
                .ThenByDescending(v => string.Equals(v.Printing, "Normal", StringComparison.OrdinalIgnoreCase))
                .FirstOrDefault();
            if (variant?.Price is null) continue;

            quotes.Add(new PriceQuote(
                localCard.Id, Name, variant.Uuid ?? variant.Id ?? "default",
                variant.Condition ?? "Near Mint", variant.Printing ?? "Normal", "USD",
                variant.Price.Value, variant.PriceChange24Hours,
                variant.LastUpdated is > 0
                    ? DateTimeOffset.FromUnixTimeSeconds(variant.LastUpdated.Value)
                    : null));
        }
        return quotes;
    }

    private sealed class JustTcgResponse
    {
        public List<JustTcgCard> Data { get; set; } = [];
    }

    private sealed class JustTcgCard
    {
        [JsonPropertyName("tcgplayerId")]
        public string? TcgplayerId { get; set; }
        public List<JustTcgVariant> Variants { get; set; } = [];
    }

    private sealed class JustTcgVariant
    {
        public string? Id { get; set; }
        public string? Uuid { get; set; }
        public string? Condition { get; set; }
        public string? Printing { get; set; }
        public string? Language { get; set; }
        public double? Price { get; set; }
        [JsonPropertyName("priceChange24hr")]
        public double? PriceChange24Hours { get; set; }
        public long? LastUpdated { get; set; }
    }
}
