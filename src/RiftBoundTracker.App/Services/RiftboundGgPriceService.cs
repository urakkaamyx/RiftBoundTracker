using System.Globalization;
using System.Net.Http;
using System.Text.Json;
using System.Text.RegularExpressions;
using RiftBoundTracker.App.Data;

namespace RiftBoundTracker.App.Services;

public sealed record RiftboundGgPrice(
    string CardId,
    string ProviderCardId,
    string Printing,
    double MarketPrice,
    double? Change24Hours,
    double? Change7Days,
    DateTimeOffset FetchedAt,
    string SourceUrl);

// Both prices side by side rather than collapsed to one "preferred" printing — for Mass Add's
// foil/normal toggle, where the choice belongs to whoever's adding the card, not a fixed priority.
public sealed record RiftboundGgDualPrice(
    string CardId,
    double? NormalPrice,
    double? NormalChange24Hours,
    double? FoilPrice,
    double? FoilChange24Hours,
    DateTimeOffset FetchedAt);

public sealed class RiftboundGgPriceService(
    IHttpClientFactory httpClientFactory,
    ILogger<RiftboundGgPriceService> logger)
{
    private static readonly TimeSpan CacheDuration = TimeSpan.FromMinutes(30);
    private static readonly Regex MarketIdSeparator = new("[,;|\\s]+", RegexOptions.Compiled);
    private readonly SemaphoreSlim refreshGate = new(1, 1);
    private CatalogCache? cache;

    public async Task<Dictionary<string, RiftboundGgPrice>> GetLatestAsync(
        IReadOnlyList<CardEntity> cards,
        CancellationToken ct = default)
    {
        var catalog = await GetCatalogAsync(ct);
        var result = new Dictionary<string, RiftboundGgPrice>(StringComparer.OrdinalIgnoreCase);

        foreach (var card in cards)
        {
            var printedCode = $"{card.SetId}-{card.CollectorCode}".ToUpperInvariant();
            if (!catalog.ByPrintedCode.TryGetValue(printedCode, out var price)
                && (string.IsNullOrWhiteSpace(card.TcgplayerId)
                    || !catalog.ByMarketId.TryGetValue(card.TcgplayerId, out price)))
            {
                continue;
            }

            var isNormal = price.PreferredPrinting == "Normal";
            result[card.Id] = new RiftboundGgPrice(
                card.Id,
                price.ProviderCardId,
                price.PreferredPrinting,
                (isNormal ? price.NormalPrice : price.FoilPrice) ?? 0,
                isNormal ? price.NormalChange24h : price.FoilChange24h,
                isNormal ? price.NormalChange7d : price.FoilChange7d,
                catalog.FetchedAt,
                $"https://riftbound.gg/prices/?textSearch={Uri.EscapeDataString(price.ProviderCardId)}");
        }

        return result;
    }

    public async Task<Dictionary<string, RiftboundGgDualPrice>> GetDualLatestAsync(
        IReadOnlyList<CardEntity> cards,
        CancellationToken ct = default)
    {
        var catalog = await GetCatalogAsync(ct);
        var result = new Dictionary<string, RiftboundGgDualPrice>(StringComparer.OrdinalIgnoreCase);

        foreach (var card in cards)
        {
            var printedCode = $"{card.SetId}-{card.CollectorCode}".ToUpperInvariant();
            if (!catalog.ByPrintedCode.TryGetValue(printedCode, out var price)
                && (string.IsNullOrWhiteSpace(card.TcgplayerId)
                    || !catalog.ByMarketId.TryGetValue(card.TcgplayerId, out price)))
            {
                continue;
            }

            result[card.Id] = new RiftboundGgDualPrice(
                card.Id, price.NormalPrice, price.NormalChange24h, price.FoilPrice, price.FoilChange24h,
                catalog.FetchedAt);
        }

        return result;
    }

    private async Task<CatalogCache> GetCatalogAsync(CancellationToken ct)
    {
        var current = cache;
        if (current is not null && DateTimeOffset.UtcNow - current.FetchedAt < CacheDuration)
            return current;

        await refreshGate.WaitAsync(ct);
        try
        {
            current = cache;
            if (current is not null && DateTimeOffset.UtcNow - current.FetchedAt < CacheDuration)
                return current;

            try
            {
                cache = await FetchCatalogAsync(ct);
                return cache;
            }
            catch (Exception ex) when (current is not null && !ct.IsCancellationRequested)
            {
                logger.LogWarning(ex, "Riftbound.gg price refresh failed; using the previous catalog response");
                return current;
            }
        }
        finally
        {
            refreshGate.Release();
        }
    }

    private async Task<CatalogCache> FetchCatalogAsync(CancellationToken ct)
    {
        var cacheSlot = DateTimeOffset.UtcNow.ToUnixTimeSeconds() / (long)CacheDuration.TotalSeconds;
        var client = httpClientFactory.CreateClient("riftbound-gg");
        using var response = await client.GetAsync(
            $"/cgfw/getcards?game=riftbound&mode=indexed&cache={cacheSlot}", ct);
        response.EnsureSuccessStatusCode();

        await using var stream = await response.Content.ReadAsStreamAsync(ct);
        using var document = await JsonDocument.ParseAsync(stream, cancellationToken: ct);
        var root = document.RootElement;
        if (!root.TryGetProperty("names", out var names) || names.ValueKind != JsonValueKind.Array
            || !root.TryGetProperty("data", out var rows) || rows.ValueKind != JsonValueKind.Array)
        {
            throw new InvalidDataException("Riftbound.gg returned an unexpected card catalog format.");
        }

        var fields = names.EnumerateArray()
            .Select((name, index) => new { Name = name.GetString() ?? "", Index = index })
            .Where(field => field.Name.Length > 0)
            .ToDictionary(field => field.Name, field => field.Index, StringComparer.OrdinalIgnoreCase);
        var required = new[]
        {
            "id", "marketIds", "price", "foilPrice", "deltaPrice", "deltaFoilPrice",
            "delta7dPrice", "delta7dPriceFoil", "hasNormal", "hasFoil",
        };
        if (required.Any(field => !fields.ContainsKey(field)))
            throw new InvalidDataException("Riftbound.gg omitted required price fields.");

        var byPrintedCode = new Dictionary<string, CatalogPrice>(StringComparer.OrdinalIgnoreCase);
        var byMarketId = new Dictionary<string, CatalogPrice>(StringComparer.OrdinalIgnoreCase);
        foreach (var row in rows.EnumerateArray())
        {
            if (row.ValueKind != JsonValueKind.Array) continue;
            var providerCardId = ReadString(row, fields["id"]);
            if (string.IsNullOrWhiteSpace(providerCardId)) continue;

            var normalPrice = ReadDouble(row, fields["price"]);
            var foilPrice = ReadDouble(row, fields["foilPrice"]);
            var hasNormal = ReadBoolean(row, fields["hasNormal"]);
            var hasFoil = ReadBoolean(row, fields["hasFoil"]);

            double? normal = normalPrice is > 0 ? normalPrice : null;
            double? foil = foilPrice is > 0 ? foilPrice : null;
            if (normal is null && foil is null) continue;

            // Same priority the single-price path always used (Normal wins unless only Foil is
            // actually available) — preserved here so GetLatestAsync's existing callers (Analytics,
            // Inspector, etc.) see identical output to before; GetDualLatestAsync below is the new
            // path that exposes both prices instead of collapsing to one.
            var preferNormal = normal is not null && (hasNormal || foil is null);
            var price = new CatalogPrice(
                providerCardId,
                normal, ReadDouble(row, fields["deltaPrice"]), ReadDouble(row, fields["delta7dPrice"]),
                foil, ReadDouble(row, fields["deltaFoilPrice"]), ReadDouble(row, fields["delta7dPriceFoil"]),
                preferNormal ? "Normal" : "Foil");

            byPrintedCode[providerCardId.ToUpperInvariant()] = price;

            var marketIds = ReadString(row, fields["marketIds"]);
            foreach (var marketId in MarketIdSeparator.Split(marketIds).Where(value => value.Length > 0))
                byMarketId.TryAdd(marketId, price);
        }

        var fetchedAt = DateTimeOffset.UtcNow;
        logger.LogInformation(
            "Loaded {PriceCount} Riftbound.gg prices with {MarketIdCount} market ID mappings",
            byPrintedCode.Count,
            byMarketId.Count);
        return new CatalogCache(byPrintedCode, byMarketId, fetchedAt);
    }

    private static string ReadString(JsonElement row, int index)
    {
        if (index >= row.GetArrayLength()) return "";
        var value = row[index];
        return value.ValueKind switch
        {
            JsonValueKind.String => value.GetString() ?? "",
            JsonValueKind.Number => value.GetRawText(),
            _ => "",
        };
    }

    private static double? ReadDouble(JsonElement row, int index)
    {
        if (index >= row.GetArrayLength()) return null;
        var value = row[index];
        if (value.ValueKind == JsonValueKind.Number && value.TryGetDouble(out var number)) return number;
        return value.ValueKind == JsonValueKind.String
               && double.TryParse(value.GetString(), NumberStyles.Float, CultureInfo.InvariantCulture, out number)
            ? number
            : null;
    }

    private static bool ReadBoolean(JsonElement row, int index)
    {
        if (index >= row.GetArrayLength()) return false;
        var value = row[index];
        if (value.ValueKind is JsonValueKind.True or JsonValueKind.False) return value.GetBoolean();
        return ReadString(row, index) is "1" or "true" or "True";
    }

    private sealed record CatalogPrice(
        string ProviderCardId,
        double? NormalPrice, double? NormalChange24h, double? NormalChange7d,
        double? FoilPrice, double? FoilChange24h, double? FoilChange7d,
        string PreferredPrinting);

    private sealed record CatalogCache(
        Dictionary<string, CatalogPrice> ByPrintedCode,
        Dictionary<string, CatalogPrice> ByMarketId,
        DateTimeOffset FetchedAt);
}
