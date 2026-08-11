using System.Net;
using System.Net.Http;
using System.Net.Http.Json;

namespace RiftBoundTracker.App.Services;

/// <summary>
/// Thin wrapper around the Riftcodex API. Retries transient failures (403/429/5xx) with backoff —
/// a 403 with no other explanation is almost always a WAF/bot-detection response rather than a
/// real permissions error, and it can be inconsistent across networks/IPs even for identical
/// requests, so a bare failure on the first attempt shouldn't be treated as final.
/// </summary>
public class RiftcodexClient(HttpClient http)
{
    private const int MaxAttempts = 4;

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
                throw new RiftcodexApiException(
                    $"Riftcodex API returned {(int)response.StatusCode} {response.StatusCode} for {url} " +
                    $"after {attempt} attempt(s). This is usually the API's bot/rate protection, not a real " +
                    "permissions error — it can come and go. Try again in a minute.",
                    response.StatusCode);
            }

            var delay = TimeSpan.FromSeconds(Math.Pow(2, attempt)); // 2s, 4s, 8s
            await Task.Delay(delay, ct);
        }

        return default;
    }
}

public class RiftcodexApiException(string message, HttpStatusCode statusCode) : Exception(message)
{
    public HttpStatusCode StatusCode { get; } = statusCode;
}
