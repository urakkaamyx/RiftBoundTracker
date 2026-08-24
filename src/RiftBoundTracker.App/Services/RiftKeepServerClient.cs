using System.Net.Http;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace RiftBoundTracker.App.Services;

/// <summary>
/// The one card shape the client's local catalog cares about from a RiftKeep server — a subset of
/// the server's own CardEntity JSON. Only catalog fields (never ownership — the server's version
/// of CardEntity doesn't have those fields at all; see RiftKeepServer's Data/CardEntity.cs).
/// </summary>
public sealed class RiftKeepServerCard
{
    public string Id { get; set; } = "";
    public string Name { get; set; } = "";
    public int CollectorNumber { get; set; }
    public string CollectorCode { get; set; } = "";
    public string SetId { get; set; } = "";
    public string SetLabel { get; set; } = "";
    public string Type { get; set; } = "";
    public string? Supertype { get; set; }
    public string Rarity { get; set; } = "";
    public string DomainsCsv { get; set; } = "";
    public string? TextRich { get; set; }
    public string? TextPlain { get; set; }
    public string? Flavour { get; set; }
    public string ImageUrl { get; set; } = "";
    public string? LocalImagePath { get; set; }
    public string? Artist { get; set; }
    public string? Orientation { get; set; }
    public string? TcgplayerId { get; set; }
    public int? Energy { get; set; }
    public int? Might { get; set; }
    public int? Power { get; set; }
    public bool IsSyntheticToken { get; set; }
}

public sealed record RiftKeepJustTcgQuote(
    string CardId, string Provider, string VariantId, string Condition, string Printing,
    string Currency, double MarketPrice, double? Change24Hours, DateTimeOffset? SourceUpdatedAt);

/// <summary>
/// The only place this client talks to a configured RiftKeep server — everything a client needs
/// from "the outside world" (card catalog, pricing) is meant to route through here once a server
/// is configured, rather than each service reaching riftcodex.com/dotgg.gg/justtcg.com directly.
/// See RiftKeepServerCardSyncService and JustTcgPriceProvider for the call sites.
/// </summary>
public sealed class RiftKeepServerClient(IHttpClientFactory httpClientFactory, RiftKeepServerSettingsService settings)
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

    public bool IsConfigured => settings.IsConnected();

    private HttpClient CreateClient(RiftKeepServerSettings connection)
    {
        var http = httpClientFactory.CreateClient("riftkeep-server");
        http.BaseAddress = new Uri(connection.ServerUrl.TrimEnd('/') + "/");
        http.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", connection.Token);
        return http;
    }

    public async Task<List<RiftKeepServerCard>> GetAllCardsAsync(CancellationToken ct = default)
    {
        var connection = settings.GetSettings() ?? throw new InvalidOperationException("No RiftKeep server is configured.");
        var http = CreateClient(connection);
        return await http.GetFromJsonAsync<List<RiftKeepServerCard>>("api/cards", JsonOptions, ct) ?? [];
    }

    public async Task<byte[]> DownloadImageAsync(string localImagePath, CancellationToken ct = default)
    {
        var connection = settings.GetSettings() ?? throw new InvalidOperationException("No RiftKeep server is configured.");
        var http = CreateClient(connection);
        return await http.GetByteArrayAsync(localImagePath.TrimStart('/'), ct);
    }

    /// <summary>
    /// Passes the client's own locally-stored JustTCG key through to the server for this one call
    /// — the server relays it to JustTCG and forgets it (see RiftKeep.Server's JustTcgPriceProvider),
    /// so this client never calls api.justtcg.com directly once a server is configured.
    /// </summary>
    public async Task<List<RiftKeepJustTcgQuote>> GetJustTcgPricesAsync(string apiKey, List<string> cardIds, CancellationToken ct = default)
    {
        var connection = settings.GetSettings() ?? throw new InvalidOperationException("No RiftKeep server is configured.");
        var http = CreateClient(connection);
        using var response = await http.PostAsJsonAsync("api/pricing/justtcg", new { apiKey, cardIds }, JsonOptions, ct);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<List<RiftKeepJustTcgQuote>>(JsonOptions, ct) ?? [];
    }
}
