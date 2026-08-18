using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;
using RiftBoundTracker.App.Data;

namespace RiftBoundTracker.App.Services.Rules;

public sealed record RuleDocumentSummaryDto(int Id, string Title, string Authority, bool Current);
public sealed record RuleSearchHit(
    int RuleId, string? RuleNumber, string Title, string? Section, string Snippet,
    RuleDocumentSummaryDto Document, string MatchType, double Score);
public sealed record RuleSearchResponse(string Query, string NormalizedQuery, int Total, List<RuleSearchHit> Results);

/// <summary>
/// One search bar, several strategies merged behind it (architecture doc section 40): an exact
/// rule number opens directly; an exact keyword or alias pulls its canonical rule plus everything
/// that mentions it; everything else falls through to the FTS5 index. Current authoritative
/// material always outranks historical/lower-authority material at the same text-match strength —
/// never the other way around, per doc section 10's explicit ranking rule.
/// </summary>
public sealed class RulesSearchService(AppDbContext db)
{
    private const int RuleNumberWeight = 1000;
    private const int CanonicalKeywordWeight = 200;
    private const int TitleMatchWeight = 120;
    private const int MentionedKeywordWeight = 80;
    private const int FullTextWeight = 40;

    public async Task<RuleSearchResponse> SearchAsync(
        string query, bool currentOnly = true, int limit = 30, CancellationToken ct = default)
    {
        var trimmed = query.Trim();
        if (trimmed.Length == 0) return new RuleSearchResponse(query, "", 0, []);

        if (RulesQueryParser.TryParseRuleNumber(trimmed, out var ruleNumber))
        {
            var exact = await db.RuleEntries
                .Include(r => r.Document)
                .Where(r => r.RuleNumber == ruleNumber && (!currentOnly || r.IsCurrent))
                .OrderByDescending(r => r.Authority)
                .FirstOrDefaultAsync(ct);
            if (exact is not null)
            {
                var hit = await ToHitAsync(exact, "RuleNumber", RuleNumberWeight, ct);
                return new RuleSearchResponse(query, trimmed, 1, [hit]);
            }
            // No exact rule at that number — fall through to a normal text search instead of a dead end.
        }

        var normalized = RulesKeywordCatalogService.Normalize(trimmed);
        var keyword = await db.RuleKeywords
            .Include(k => k.Aliases)
            .FirstOrDefaultAsync(k => k.NormalizedName == normalized || k.Aliases.Any(a => a.NormalizedAlias == normalized), ct);

        var scored = new Dictionary<int, (RuleEntryEntity Entry, string MatchType, double Score)>();

        if (keyword is not null)
            foreach (var (entry, matchType, score) in await KeywordEvidenceAsync(keyword.Id, currentOnly, ct))
                Consider(scored, entry, matchType, score);

        var titleMatches = await db.RuleEntries
            .Include(r => r.Document)
            .Where(r => r.Title != null && r.Title.Contains(trimmed) && (!currentOnly || r.IsCurrent))
            .Take(limit)
            .ToListAsync(ct);
        foreach (var entry in titleMatches)
            Consider(scored, entry, "Title", TitleMatchWeight);

        var ftsIds = await SearchFtsAsync(trimmed, limit * 2, ct);
        if (ftsIds.Count > 0)
        {
            var ftsEntries = await db.RuleEntries
                .Include(r => r.Document)
                .Where(r => ftsIds.Contains(r.Id) && (!currentOnly || r.IsCurrent))
                .ToListAsync(ct);
            foreach (var entry in ftsEntries)
                Consider(scored, entry, "FullText", FullTextWeight);
        }

        var ranked = scored.Values
            .OrderByDescending(x => x.Score * AuthorityWeight(x.Entry.Authority))
            .ThenByDescending(x => x.Entry.IsCurrent)
            .ThenBy(x => x.Entry.SortOrder)
            .Take(limit)
            .ToList();

        var results = new List<RuleSearchHit>();
        foreach (var (entry, matchType, score) in ranked)
            results.Add(await ToHitAsync(entry, matchType, score, ct));

        return new RuleSearchResponse(query, trimmed, results.Count, results);
    }

    /// <summary>
    /// Every rule tied to one keyword — its own canonical definition plus every rule whose text
    /// mentions it. Shared by SearchAsync's exact-keyword branch and RulesEvidenceService (which
    /// needs the same lookup per detected/concept-linked keyword when answering a free-text
    /// question) so the two never diverge on what "evidence for this keyword" means.
    /// </summary>
    public async Task<List<RuleSearchHit>> SearchByKeywordIdAsync(int keywordId, bool currentOnly, CancellationToken ct = default)
    {
        var hits = new List<RuleSearchHit>();
        foreach (var (entry, matchType, score) in await KeywordEvidenceAsync(keywordId, currentOnly, ct))
            hits.Add(await ToHitAsync(entry, matchType, score, ct));
        return hits;
    }

    private async Task<List<(RuleEntryEntity Entry, string MatchType, double Score)>> KeywordEvidenceAsync(
        int keywordId, bool currentOnly, CancellationToken ct)
    {
        var results = new List<(RuleEntryEntity, string, double)>();
        var keyword = await db.RuleKeywords
            .Include(k => k.CanonicalRule).ThenInclude(r => r!.Document)
            .FirstOrDefaultAsync(k => k.Id == keywordId, ct);
        if (keyword?.CanonicalRule is { } canonicalRule && (!currentOnly || canonicalRule.IsCurrent))
            results.Add((canonicalRule, "Keyword", CanonicalKeywordWeight));

        var mentioned = await db.RuleEntryKeywords
            .Where(rk => rk.KeywordId == keywordId)
            .Include(rk => rk.RuleEntry).ThenInclude(r => r.Document)
            .Select(rk => rk.RuleEntry)
            .Where(r => !currentOnly || r.IsCurrent)
            .ToListAsync(ct);
        foreach (var entry in mentioned)
            results.Add((entry, "Keyword", MentionedKeywordWeight));

        return results;
    }

    private static void Consider(
        Dictionary<int, (RuleEntryEntity Entry, string MatchType, double Score)> scored, RuleEntryEntity entry, string matchType, double score)
    {
        if (scored.TryGetValue(entry.Id, out var existing) && existing.Score >= score) return;
        scored[entry.Id] = (entry, matchType, score);
    }

    private static double AuthorityWeight(RuleAuthority authority) => (int)authority + 1;

    private async Task<List<int>> SearchFtsAsync(string query, int limit, CancellationToken ct)
    {
        var ftsQuery = BuildFtsQuery(query);
        if (ftsQuery.Length == 0) return [];

        var ids = new List<int>();
        var connection = db.Database.GetDbConnection();
        var shouldClose = connection.State != System.Data.ConnectionState.Open;
        if (shouldClose) await connection.OpenAsync(ct);
        try
        {
            await using var command = connection.CreateCommand();
            command.CommandText = "SELECT rowid FROM RuleSearchFts WHERE RuleSearchFts MATCH $q ORDER BY rank LIMIT $limit;";
            var qParam = command.CreateParameter();
            qParam.ParameterName = "$q";
            qParam.Value = ftsQuery;
            command.Parameters.Add(qParam);
            var limitParam = command.CreateParameter();
            limitParam.ParameterName = "$limit";
            limitParam.Value = limit;
            command.Parameters.Add(limitParam);

            await using var reader = await command.ExecuteReaderAsync(ct);
            while (await reader.ReadAsync(ct))
                ids.Add(reader.GetInt32(0));
        }
        catch (SqliteException)
        {
            // A malformed FTS5 query string (stray quote, bare operator) shouldn't 500 the whole
            // search — just contribute no full-text results for this query.
            return [];
        }
        finally
        {
            if (shouldClose) await connection.CloseAsync();
        }
        return ids;
    }

    // FTS5's default query syntax treats bare punctuation and lone operators (AND/OR/NOT/-) as
    // syntax errors — wrap each token as a quoted phrase so arbitrary user text (including
    // apostrophes, "can't", punctuation) always parses as a plain implicit-AND term search.
    private static string BuildFtsQuery(string query)
    {
        var tokens = query.Split(' ', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Select(t => "\"" + t.Replace("\"", "\"\"") + "\"*")
            .ToList();
        return string.Join(" ", tokens);
    }

    private async Task<RuleSearchHit> ToHitAsync(RuleEntryEntity entry, string matchType, double score, CancellationToken ct)
    {
        var section = await ComputeSectionAsync(entry.ParentRuleId, ct);
        var snippet = entry.Text.Length > 220 ? entry.Text[..220] + "…" : entry.Text;
        var displayTitle = entry.Title
            ?? (entry.RuleNumber is not null ? $"Rule {entry.RuleNumber}" : entry.Document.Title);
        return new RuleSearchHit(
            entry.Id, entry.RuleNumber, displayTitle, section, snippet,
            new RuleDocumentSummaryDto(entry.Document.Id, entry.Document.Title, entry.Document.Authority.ToString(), entry.Document.IsCurrent),
            matchType, score);
    }

    private async Task<string?> ComputeSectionAsync(int? parentId, CancellationToken ct)
    {
        var current = parentId;
        var guard = 0;
        while (current is not null && guard++ < 20)
        {
            var node = await db.RuleEntries
                .Where(r => r.Id == current)
                .Select(r => new { r.Title, r.ParentRuleId })
                .FirstOrDefaultAsync(ct);
            if (node is null) return null;
            if (node.Title is not null) return node.Title;
            current = node.ParentRuleId;
        }
        return null;
    }
}
