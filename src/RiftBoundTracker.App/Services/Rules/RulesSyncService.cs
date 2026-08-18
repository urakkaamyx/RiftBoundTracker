using System.Net.Http;
using Microsoft.EntityFrameworkCore;
using RiftBoundTracker.App.Data;

namespace RiftBoundTracker.App.Services.Rules;

public sealed record RulesSyncResult(
    bool Ok, int DocumentsUpdated, int RulesIndexed, int ErrataIndexed, int LegalityEntriesIndexed, string? Error);

public sealed record RulesSyncStatusDto(
    bool Configured, DateTimeOffset? LastCheckAt, DateTimeOffset? LastSuccessfulSyncAt, bool LastSyncOk,
    int DocumentsIndexed, int RulesIndexed, int KeywordsIndexed, int ErrataIndexed, int LegalityEntriesIndexed, string? LastError);

/// <summary>
/// Orchestrates a full Rules Hub sync: discover -> download/fetch each document -> parse -> import
/// (each import is its own transaction, see RulesImportService) -> link keywords -> rebuild the
/// FTS index. Manual-trigger only, same as the TopDeck.gg community sync — never runs on a normal
/// page load or app startup, so the official site is only ever hit when the user asks for it.
/// </summary>
public sealed class RulesSyncService(
    AppDbContext db,
    RulesSourceDiscoveryService discovery,
    NextJsArticlePageFetcher articleFetcher,
    RulesImportService import,
    RulesKeywordCatalogService keywordCatalog,
    RulesKeywordLinkerService keywordLinker,
    IHttpClientFactory httpClientFactory,
    ILogger<RulesSyncService> logger)
{
    private const string RulesHubUrl = "https://playriftbound.com/en-us/rules-hub/";

    public async Task<RulesSyncStatusDto> GetStatusAsync(CancellationToken ct = default)
    {
        var state = await db.RulesSyncState.FirstOrDefaultAsync(ct);
        return new RulesSyncStatusDto(
            true, state?.LastCheckAt, state?.LastSuccessfulSyncAt, state?.LastSyncOk ?? false,
            state?.DocumentsIndexed ?? 0, state?.RulesIndexed ?? 0, state?.KeywordsIndexed ?? 0,
            state?.ErrataIndexed ?? 0, state?.LegalityEntriesIndexed ?? 0, state?.LastError);
    }

    public async Task<RulesSyncResult> SyncAsync(CancellationToken ct = default)
    {
        try
        {
            await keywordCatalog.EnsureSeededAsync(ct);

            var discovered = await discovery.DiscoverAsync(ct);
            var documentsUpdated = 0;
            var rulesIndexed = 0;
            var errataIndexed = 0;

            foreach (var doc in discovered.Documents)
            {
                ct.ThrowIfCancellationRequested();
                try
                {
                    switch (doc.SourceType)
                    {
                        case RuleSourceType.CoreRules or RuleSourceType.TournamentRules:
                        {
                            var bytes = await DownloadAsync(doc.DownloadUrl!, ct);
                            var authority = doc.SourceType == RuleSourceType.CoreRules
                                ? RuleAuthority.CoreRules : RuleAuthority.TournamentRules;
                            var outcome = await import.ImportPdfAsync(doc, bytes, authority, ct);
                            if (!outcome.Unchanged) { documentsUpdated++; rulesIndexed += outcome.RuleCount; }
                            break;
                        }
                        case RuleSourceType.PatchNotes:
                        {
                            var article = await articleFetcher.FetchAsync(doc.SourceUrl, ct);
                            if (article is null) { logger.LogWarning("Could not read patch notes article {Url}", doc.SourceUrl); break; }
                            var outcome = await import.ImportArticleAsync(doc, article, RuleAuthority.OfficialClarification, ct);
                            if (!outcome.Unchanged) { documentsUpdated++; rulesIndexed += outcome.RuleCount; }
                            break;
                        }
                        case RuleSourceType.Errata:
                        {
                            var article = await articleFetcher.FetchAsync(doc.SourceUrl, ct);
                            if (article is null) { logger.LogWarning("Could not read errata article {Url}", doc.SourceUrl); break; }
                            var outcome = await import.ImportErrataAsync(doc, article, ct);
                            if (!outcome.Unchanged) { documentsUpdated++; errataIndexed += outcome.ErrataCount; }
                            break;
                        }
                    }
                }
                catch (Exception ex)
                {
                    // One bad document (a changed page template, a transient fetch failure)
                    // must not abort the whole sync — the rest of the hub's documents still
                    // deserve a chance to update, and whatever was already current stays current.
                    logger.LogWarning(ex, "Failed to sync {SourceType} document {Title}", doc.SourceType, doc.Title);
                }
            }

            var legalityCount = await import.ImportLegalityAsync(discovered.Legalities, RulesHubUrl, discovered.LegalityUpdatedAt, ct);

            await keywordLinker.LinkAsync(ct);
            await RebuildFtsIndexAsync(ct);

            var totalDocs = await db.RuleDocuments.CountAsync(d => d.IsCurrent, ct);
            var totalRules = await db.RuleEntries.CountAsync(r => r.IsCurrent, ct);
            var totalKeywords = await db.RuleKeywords.CountAsync(ct);
            var totalErrata = await db.CardErrata.CountAsync(e => e.IsCurrent, ct);
            var totalLegality = await db.CardLegalities.CountAsync(l => l.IsCurrent, ct);

            await SaveStateAsync(ok: true, totalDocs, totalRules, totalKeywords, totalErrata, totalLegality, null, ct);
            return new RulesSyncResult(true, documentsUpdated, rulesIndexed, errataIndexed, legalityCount, null);
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Rules sync failed");
            await SaveStateAsync(ok: false, null, null, null, null, null, ex.Message, ct);
            return new RulesSyncResult(false, 0, 0, 0, 0, ex.Message);
        }
    }

    private async Task<byte[]> DownloadAsync(string url, CancellationToken ct)
    {
        var client = httpClientFactory.CreateClient("rules-source");
        return await client.GetByteArrayAsync(url, ct);
    }

    private async Task RebuildFtsIndexAsync(CancellationToken ct)
    {
        var keywordNamesByRule = (await db.RuleEntryKeywords
                .Select(k => new { k.RuleEntryId, k.Keyword.Name })
                .ToListAsync(ct))
            .GroupBy(x => x.RuleEntryId)
            .ToDictionary(g => g.Key, g => string.Join(" ", g.Select(x => x.Name)));

        var entries = await db.RuleEntries
            .Where(r => r.IsCurrent)
            .Select(r => new { r.Id, r.RuleNumber, r.Title, r.Text })
            .ToListAsync(ct);

        await using var transaction = await db.Database.BeginTransactionAsync(ct);
        await db.Database.ExecuteSqlRawAsync("DELETE FROM RuleSearchFts;", ct);
        foreach (var entry in entries)
        {
            var keywordText = keywordNamesByRule.GetValueOrDefault(entry.Id, "");
            await db.Database.ExecuteSqlInterpolatedAsync(
                $"""
                 INSERT INTO RuleSearchFts(rowid, RuleNumber, Title, Text, Keywords)
                 VALUES ({entry.Id}, {entry.RuleNumber}, {entry.Title}, {entry.Text}, {keywordText})
                 """, ct);
        }
        await transaction.CommitAsync(ct);
    }

    private async Task SaveStateAsync(
        bool ok, int? documents, int? rules, int? keywords, int? errata, int? legality, string? error, CancellationToken ct)
    {
        var state = await db.RulesSyncState.FirstOrDefaultAsync(ct) ?? Add(new RulesSyncStateEntity());
        state.LastCheckAt = DateTimeOffset.UtcNow;
        state.LastSyncOk = ok;
        state.LastError = error;
        if (ok)
        {
            state.LastSuccessfulSyncAt = DateTimeOffset.UtcNow;
            state.DocumentsIndexed = documents ?? state.DocumentsIndexed;
            state.RulesIndexed = rules ?? state.RulesIndexed;
            state.KeywordsIndexed = keywords ?? state.KeywordsIndexed;
            state.ErrataIndexed = errata ?? state.ErrataIndexed;
            state.LegalityEntriesIndexed = legality ?? state.LegalityEntriesIndexed;
        }
        await db.SaveChangesAsync(ct);
    }

    private RulesSyncStateEntity Add(RulesSyncStateEntity entity)
    {
        db.RulesSyncState.Add(entity);
        return entity;
    }
}
