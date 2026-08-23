using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using RiftBoundTracker.App.Data;

namespace RiftBoundTracker.App.Services.Rules;

public sealed record CardErrataDto(string? OriginalText, string? CorrectedText);
public sealed record CardRulesDto(List<CardErrataDto> Errata);
public sealed record ErrataListEntryDto(string Id, string CardName, string? CardId, string? OriginalText, string? CorrectedText);

/// <summary>
/// Card-side "browse rules" lookups, backed by the Rules Engine sidecar's card API — card IDs
/// already match between this app's catalog and the engine's (e.g. "ogn-134-298"), so this maps
/// cleanly with no identity-scheme change needed.
///
/// The rule/keyword-side browsing this class used to serve (rule detail pages, the keyword
/// glossary list, document list — see git history) is NOT migrated here. Those pages are built
/// around internal integer RuleEntry/Keyword IDs with parent/child/previous/next navigation baked
/// into the frontend; the engine's rule IDs are strings that are the actual rule numbers ("815",
/// "815.1"), a different identity scheme entirely. Re-pointing them at the sidecar needs frontend
/// routing changes, not just a backend swap — real, separate follow-up work, deliberately not
/// rushed through as a side effect of the Ask Rules integration.
/// </summary>
public sealed class RulesService(RulesEngineClient engine, AppDbContext db, IWebHostEnvironment env)
{
    public async Task<CardRulesDto> GetCardRulesAsync(string cardId, CancellationToken ct = default)
    {
        var lookup = await engine.GetCardAsync(cardId, ct);
        if (lookup.MatchCount == 0) return new CardRulesDto([]);

        var card = lookup.Matches[0];
        var errata = (card.OfficialErrataTimeline ?? [])
            .Select(e => new CardErrataDto(
                e.TryGetProperty("originalText", out var o) ? o.GetString() : null,
                e.TryGetProperty("correctedText", out var c) ? c.GetString() : null))
            .ToList();

        return new CardRulesDto(errata);
    }

    // The sidecar's public API only ever supports single-card errata lookups (above) or a
    // keyword-search over individual entries, never "list everything" — this bulk browse page
    // reads the same canonical data file the sidecar itself was built from directly instead, since
    // it's part of the same installed release (same path every version, no separate download).
    public async Task<List<ErrataListEntryDto>> GetErrataListAsync(CancellationToken ct = default)
    {
        var path = Path.Combine(env.ContentRootPath, "App_Data", "RulesEngine", "data", "canonical", "official_errata.json");
        if (!File.Exists(path)) return [];

        await using var stream = File.OpenRead(path);
        using var doc = await JsonDocument.ParseAsync(stream, cancellationToken: ct);
        if (!doc.RootElement.TryGetProperty("records", out var records)) return [];

        var namesById = await db.Cards.AsNoTracking()
            .Select(c => new { c.Id, c.Name })
            .ToListAsync(ct);
        var idsByLowerName = namesById
            .GroupBy(c => c.Name.ToLowerInvariant())
            .ToDictionary(g => g.Key, g => g.First().Id);

        var results = new List<ErrataListEntryDto>();
        foreach (var record in records.EnumerateArray())
        {
            var id = record.GetProperty("entryId").GetString() ?? "";
            var cardName = record.TryGetProperty("cardName", out var n) ? n.GetString() ?? "" : "";
            var identityKey = record.TryGetProperty("identityKey", out var k) ? k.GetString() : null;
            var cardId = identityKey is not null && idsByLowerName.TryGetValue(identityKey, out var matchedId) ? matchedId : null;
            var oldText = record.TryGetProperty("oldText", out var o) ? o.GetString() : null;
            var newText = record.TryGetProperty("newText", out var nt) ? nt.GetString() : null;
            results.Add(new ErrataListEntryDto(id, cardName, cardId, oldText, newText));
        }
        return results.OrderBy(e => e.CardName).ToList();
    }
}
