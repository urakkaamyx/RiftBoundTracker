using System.Net;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;

namespace RiftBoundTracker.App.Services;

/// <summary>
/// Thin wrapper around the Riftcodex API. Retries transient failures (403/429/5xx) with backoff —
/// a 403 with no other explanation is almost always a WAF/bot-detection response rather than a
/// real permissions error, and it can be inconsistent across networks/IPs even for identical
/// requests, so a bare failure on the first attempt shouldn't be treated as final. If every direct
/// attempt still fails, falls back to <see cref="BrowserRelayClient"/> — some bot detection
/// fingerprints the TLS handshake itself, which no header on a plain HttpClient can spoof, but a
/// real embedded browser naturally passes.
/// </summary>
public class RiftcodexClient(HttpClient http, BrowserRelayClient relay, ILogger<RiftcodexClient> logger)
{
    private const int MaxAttempts = 4;

    // Matches what System.Net.Http.Json's ReadFromJsonAsync uses internally by default (the
    // primary path) — the relay fallback deserializes raw bytes itself, so it needs the same
    // case-insensitive/camelCase behavior or fields on properties without an explicit
    // [JsonPropertyName] would silently come back unset.
    private static readonly JsonSerializerOptions RelayJsonOptions = new(JsonSerializerDefaults.Web);

    public async Task<List<RiftcodexCard>> GetByRiftboundIdAsync(string riftboundId, CancellationToken ct = default)
    {
        var result = await GetWithRetryAsync<List<RiftcodexCard>>(
            $"/cards/riftbound/{Uri.EscapeDataString(riftboundId)}", ct);
        return result ?? [];
    }

    public async Task<RiftcodexCardPage> GetSetPageAsync(string setId, int page, int size, CancellationToken ct = default)
    {
        var url = $"/cards?set_id={Uri.EscapeDataString(setId)}&sort=collector_number&dir=1&page={page}&size={size}";
        var result = await GetWithRetryAsync<RiftcodexCardPage>(url, ct);
        return result ?? new RiftcodexCardPage();
    }

    public async IAsyncEnumerable<RiftcodexCard> GetAllForSetAsync(
        string setId, int pageSize = 100,
        [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken ct = default)
    {
        var page = 1;
        while (true)
        {
            var result = await GetSetPageAsync(setId, page, pageSize, ct);
            foreach (var card in result.Items)
                yield return card;

            if (result.Items.Count == 0 || page >= result.Pages)
                yield break;
            page++;
        }
    }

    private async Task<T?> GetWithRetryAsync<T>(string url, CancellationToken ct)
    {
        for (var attempt = 1; attempt <= MaxAttempts; attempt++)
        {
            using var response = await http.GetAsync(url, ct);

            if (response.IsSuccessStatusCode)
                return await response.Content.ReadFromJsonAsync<T>(ct);

            var transient = response.StatusCode is HttpStatusCode.Forbidden or HttpStatusCode.TooManyRequests
                             || (int)response.StatusCode >= 500;
            if (!transient || attempt == MaxAttempts)
            {
                var viaRelay = await TryBrowserRelayAsync<T>(url, ct);
                if (viaRelay is not null)
                    return viaRelay;

                throw new RiftcodexApiException(
                    $"Riftcodex API returned {(int)response.StatusCode} {response.StatusCode} for {url} " +
                    $"after {attempt} attempt(s) (the embedded-browser fallback also couldn't get through). " +
                    "This is usually the API's bot/rate protection, not a real permissions error — it can " +
                    "come and go. Try again in a minute.",
                    response.StatusCode);
            }

            var delay = TimeSpan.FromSeconds(Math.Pow(2, attempt)); // 2s, 4s, 8s
            await Task.Delay(delay, ct);
        }

        return default;
    }

    private async Task<T?> TryBrowserRelayAsync<T>(string url, CancellationToken ct)
    {
        try
        {
            var fullUrl = http.BaseAddress is null ? url : new Uri(http.BaseAddress, url).ToString();
            logger.LogWarning("Direct requests to {Url} keep failing; trying the embedded-browser fallback", fullUrl);

            var bytes = await relay.FetchBytesAsync(fullUrl, ct);
            return bytes is null ? default : JsonSerializer.Deserialize<T>(bytes, RelayJsonOptions);
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Browser-relay fallback failed for {Url}", url);
            return default;
        }
    }
}

public class RiftcodexApiException(string message, HttpStatusCode statusCode) : Exception(message)
{
    public HttpStatusCode StatusCode { get; } = statusCode;
}
