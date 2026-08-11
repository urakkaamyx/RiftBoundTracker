using System.Net.Http;
using System.Net.Http.Json;

namespace RiftBoundTracker.App.Services;

public class RiftcodexClient(HttpClient http)
{
    public async Task<List<RiftcodexCard>> GetByRiftboundIdAsync(string riftboundId, CancellationToken ct = default)
    {
        var result = await http.GetFromJsonAsync<List<RiftcodexCard>>(
            $"/cards/riftbound/{Uri.EscapeDataString(riftboundId)}", ct);
        return result ?? [];
    }

    public async Task<RiftcodexCardPage> GetSetPageAsync(string setId, int page, int size, CancellationToken ct = default)
    {
        var url = $"/cards?set_id={Uri.EscapeDataString(setId)}&sort=collector_number&dir=1&page={page}&size={size}";
        var result = await http.GetFromJsonAsync<RiftcodexCardPage>(url, ct);
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
}
