using System.Security.Cryptography;
using System.Text;
using Microsoft.EntityFrameworkCore;
using RiftBoundTracker.App.Data;

namespace RiftBoundTracker.App.Services.Rules;

public sealed record RuleImportOutcome(RuleDocumentEntity Document, int RuleCount, int ErrataCount, int LegalityCount, bool Unchanged);

/// <summary>
/// The only place that actually writes to the Rules tables. Every import follows the same shape:
/// parse into a staging model first (already done by the caller via a parser), then write
/// everything for one document inside a single transaction — a parse or write failure never
/// leaves the previously-active rules library half-replaced, since the old "current" document
/// isn't marked historical until the new one has fully committed alongside it.
/// </summary>
public sealed class RulesImportService(AppDbContext db, CardCacheService cards, ILogger<RulesImportService> logger)
{
    public async Task<RuleImportOutcome> ImportPdfAsync(
        DiscoveredRuleDocument discovered, byte[] pdfBytes, RuleAuthority authority, CancellationToken ct)
    {
        var contentHash = ComputeHash(pdfBytes);
        var existingCurrent = await db.RuleDocuments
            .FirstOrDefaultAsync(d => d.SourceType == discovered.SourceType && d.IsCurrent, ct);
        if (existingCurrent is not null && existingCurrent.ContentHash == contentHash)
            return new RuleImportOutcome(existingCurrent, 0, 0, 0, Unchanged: true);

        List<ParsedRule> parsedRules;
        try
        {
            parsedRules = RulesPdfParser.Parse(pdfBytes);
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Failed to parse {Title} as a rules PDF", discovered.Title);
            throw new InvalidOperationException($"Could not parse {discovered.Title} — the source document may have changed format.", ex);
        }

        if (parsedRules.Count == 0)
            throw new InvalidOperationException($"Parsing {discovered.Title} produced zero rules — refusing to activate a possibly-broken parse.");

        var document = await WriteDocumentAsync(discovered, authority, contentHash, parsedRules, ct);
        return new RuleImportOutcome(document, parsedRules.Count, 0, 0, Unchanged: false);
    }

    public async Task<RuleImportOutcome> ImportArticleAsync(
        DiscoveredRuleDocument discovered, NextJsArticlePage article, RuleAuthority authority, CancellationToken ct)
    {
        var contentHash = ComputeHash(Encoding.UTF8.GetBytes(article.RichTextHtml));
        var existingCurrent = await db.RuleDocuments
            .FirstOrDefaultAsync(d => d.SourceType == discovered.SourceType && d.SourceUrl == discovered.SourceUrl && d.IsCurrent, ct);
        if (existingCurrent is not null && existingCurrent.ContentHash == contentHash)
            return new RuleImportOutcome(existingCurrent, 0, 0, 0, Unchanged: true);

        var sections = ArticleSectionParser.Parse(article.RichTextHtml, discovered.Title);
        discovered.PublishedAt ??= article.PublishedAt;
        var document = await WriteDocumentAsync(discovered, authority, contentHash, sections, ct, existingBySourceUrl: true);
        return new RuleImportOutcome(document, sections.Count, 0, 0, Unchanged: false);
    }

    public async Task<RuleImportOutcome> ImportErrataAsync(
        DiscoveredRuleDocument discovered, NextJsArticlePage article, CancellationToken ct)
    {
        var contentHash = ComputeHash(Encoding.UTF8.GetBytes(article.RichTextHtml));
        var existingCurrent = await db.RuleDocuments
            .FirstOrDefaultAsync(d => d.SourceType == RuleSourceType.Errata && d.SourceUrl == discovered.SourceUrl && d.IsCurrent, ct);
        if (existingCurrent is not null && existingCurrent.ContentHash == contentHash)
            return new RuleImportOutcome(existingCurrent, 0, 0, 0, Unchanged: true);

        var entries = ErrataArticleParser.Parse(article.RichTextHtml);

        await using var transaction = await db.Database.BeginTransactionAsync(ct);
        if (existingCurrent is not null) existingCurrent.IsCurrent = false;

        var document = new RuleDocumentEntity
        {
            SourceType = RuleSourceType.Errata,
            Title = discovered.Title,
            SourceUrl = discovered.SourceUrl,
            PublishedAt = discovered.PublishedAt ?? article.PublishedAt,
            DiscoveredAt = DateTimeOffset.UtcNow,
            DownloadedAt = DateTimeOffset.UtcNow,
            ContentHash = contentHash,
            Authority = RuleAuthority.OfficialErrata,
            IsCurrent = true,
            ParseStatus = "Ok",
        };
        db.RuleDocuments.Add(document);
        await db.SaveChangesAsync(ct);

        var resolved = 0;
        foreach (var entry in entries)
        {
            var cardId = await ResolveCardIdAsync(entry.CardNameRaw, ct);
            if (cardId is not null) resolved++;

            db.CardErrata.Add(new CardErrataEntity
            {
                CardId = cardId,
                CardNameRaw = entry.CardNameRaw,
                DocumentId = document.Id,
                OriginalText = entry.OriginalText,
                CorrectedText = entry.CorrectedText,
                EffectiveAt = document.PublishedAt,
                IsCurrent = true,
            });
        }
        await db.SaveChangesAsync(ct);
        await transaction.CommitAsync(ct);

        logger.LogInformation(
            "Imported errata article '{Title}': {Total} cards, {Resolved} resolved to a local card",
            discovered.Title, entries.Count, resolved);

        return new RuleImportOutcome(document, 0, entries.Count, 0, Unchanged: false);
    }

    public async Task<int> ImportLegalityAsync(
        List<ParsedLegalityEntry> entries, string hubUrl, DateTimeOffset? updatedAt, CancellationToken ct)
    {
        var existingCurrent = await db.RuleDocuments
            .FirstOrDefaultAsync(d => d.SourceType == RuleSourceType.Legality && d.IsCurrent, ct);

        var contentHash = ComputeHash(Encoding.UTF8.GetBytes(
            string.Join("|", entries.Select(e => $"{e.Format}:{e.CardNameRaw}:{e.Status}").OrderBy(s => s))));
        if (existingCurrent is not null && existingCurrent.ContentHash == contentHash)
            return 0;

        await using var transaction = await db.Database.BeginTransactionAsync(ct);
        if (existingCurrent is not null) existingCurrent.IsCurrent = false;

        var document = new RuleDocumentEntity
        {
            SourceType = RuleSourceType.Legality,
            Title = "Format Legality",
            SourceUrl = hubUrl,
            PublishedAt = updatedAt,
            DiscoveredAt = DateTimeOffset.UtcNow,
            DownloadedAt = DateTimeOffset.UtcNow,
            ContentHash = contentHash,
            Authority = RuleAuthority.CoreRules,
            IsCurrent = true,
            ParseStatus = "Ok",
        };
        db.RuleDocuments.Add(document);
        await db.SaveChangesAsync(ct);

        foreach (var entry in entries)
        {
            var cardId = await ResolveCardIdAsync(entry.CardNameRaw, ct);
            db.CardLegalities.Add(new CardLegalityEntity
            {
                CardId = cardId,
                CardNameRaw = entry.CardNameRaw,
                Format = entry.Format,
                Status = entry.Status,
                EffectiveAt = updatedAt,
                DocumentId = document.Id,
                IsCurrent = true,
            });
        }
        await db.SaveChangesAsync(ct);
        await transaction.CommitAsync(ct);
        return entries.Count;
    }

    private async Task<RuleDocumentEntity> WriteDocumentAsync(
        DiscoveredRuleDocument discovered, RuleAuthority authority, string contentHash,
        List<ParsedRule> parsedRules, CancellationToken ct, bool existingBySourceUrl = false)
    {
        // A failure partway through (parent-linking, cross-reference resolution) must never leave
        // the previously-active document marked historical while its replacement sits half-written
        // — everything for one document commits together or not at all.
        await using var transaction = await db.Database.BeginTransactionAsync(ct);

        var existingCurrent = existingBySourceUrl
            ? await db.RuleDocuments.FirstOrDefaultAsync(
                d => d.SourceType == discovered.SourceType && d.SourceUrl == discovered.SourceUrl && d.IsCurrent, ct)
            : await db.RuleDocuments.FirstOrDefaultAsync(d => d.SourceType == discovered.SourceType && d.IsCurrent, ct);
        if (existingCurrent is not null) existingCurrent.IsCurrent = false;

        var document = new RuleDocumentEntity
        {
            SourceType = discovered.SourceType,
            Title = discovered.Title,
            SourceUrl = discovered.SourceUrl,
            DownloadUrl = discovered.DownloadUrl,
            DocumentVersion = discovered.DocumentVersionText,
            PublishedAt = discovered.PublishedAt,
            DiscoveredAt = DateTimeOffset.UtcNow,
            DownloadedAt = DateTimeOffset.UtcNow,
            ContentHash = contentHash,
            Authority = authority,
            IsCurrent = true,
            ParseStatus = "Ok",
        };
        db.RuleDocuments.Add(document);
        await db.SaveChangesAsync(ct);

        var entities = new List<RuleEntryEntity>(parsedRules.Count);
        foreach (var parsed in parsedRules)
        {
            var entity = new RuleEntryEntity
            {
                DocumentId = document.Id,
                RuleNumber = parsed.RuleNumber,
                Title = parsed.Title,
                Text = parsed.Text,
                SortOrder = parsed.SortOrder,
                Authority = authority,
                IsCurrent = true,
            };
            entities.Add(entity);
            db.RuleEntries.Add(entity);
        }
        await db.SaveChangesAsync(ct); // assigns Ids

        var byNumber = entities
            .Where(e => e.RuleNumber is not null)
            .ToDictionary(e => e.RuleNumber!);

        foreach (var entity in entities)
        {
            if (entity.RuleNumber is null) continue;
            var parentNumber = ParentOf(entity.RuleNumber);
            if (parentNumber is not null && byNumber.TryGetValue(parentNumber, out var parent))
                entity.ParentRuleId = parent.Id;
        }

        for (var i = 0; i < parsedRules.Count; i++)
        {
            var parsed = parsedRules[i];
            if (parsed.RuleNumber is null || parsed.ExplicitReferenceNumbers.Count == 0) continue;
            var fromEntry = entities[i];
            foreach (var refNumber in parsed.ExplicitReferenceNumbers.Distinct())
            {
                if (refNumber == parsed.RuleNumber) continue;
                if (byNumber.TryGetValue(refNumber, out var toEntry))
                    db.RuleCrossReferences.Add(new RuleCrossReferenceEntity { FromRuleId = fromEntry.Id, ToRuleId = toEntry.Id });
            }
        }

        await db.SaveChangesAsync(ct);
        await transaction.CommitAsync(ct);
        logger.LogInformation("Imported {Title}: {Count} rules ({Authority})", discovered.Title, entities.Count, authority);
        return document;
    }

    // "Always choose the base card" when a name is ambiguous — same rule this app already applies
    // to RiftDecks import (CardCacheService.FindByNameAsync orders base-print-first). Battlefields
    // and Legends resolve the same way since they're ordinary CardEntity rows in this catalog.
    private async Task<string?> ResolveCardIdAsync(string rawName, CancellationToken ct)
    {
        var matches = await cards.FindByNameAsync(rawName, ct);
        return matches.Count > 0 ? matches[0].Id : null;
    }

    private static string? ParentOf(string ruleNumber)
    {
        var idx = ruleNumber.LastIndexOf('.');
        return idx < 0 ? null : ruleNumber[..idx];
    }

    private static string ComputeHash(byte[] bytes) => Convert.ToHexStringLower(SHA256.HashData(bytes));
}
