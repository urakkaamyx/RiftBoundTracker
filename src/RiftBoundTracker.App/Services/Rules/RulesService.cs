using Microsoft.EntityFrameworkCore;
using RiftBoundTracker.App.Data;

namespace RiftBoundTracker.App.Services.Rules;

public sealed record RuleEntryDto(
    int Id, string? RuleNumber, string? Title, string Text, string Authority, bool IsCurrent, RuleDocumentSummaryDto Document);

public sealed record RuleKeywordSummaryDto(int Id, string Name, string? Definition, string? Category, int? CanonicalRuleId);

public sealed record RuleDetailDto(
    RuleEntryDto Rule, RuleEntryDto? Parent, List<RuleEntryDto> Children,
    RuleEntryDto? Previous, RuleEntryDto? Next, List<RuleKeywordSummaryDto> Keywords,
    List<RuleEntryDto> References, List<RuleEntryDto> ReferencedBy);

// Text is populated only for the Ask Rules "about this card" flow (RulesQuestionService.AnalyzeAsync)
// so the LLM prompt has the card's actual printed text to reason from, not just its name — every
// other caller of this DTO leaves it at the default and it's simply not serialized into those
// responses in any meaningful way.
public sealed record CardSummaryDto(string Id, string Name, string ImageUrl, string? Text = null);

public sealed record RuleKeywordDetailDto(
    int Id, string Name, string? Definition, string? Category, List<string> Aliases,
    RuleEntryDto? CanonicalRule, List<RuleEntryDto> MentionedIn, List<CardSummaryDto> Cards);

public sealed record RuleDocumentDto(
    int Id, string SourceType, string Title, string SourceUrl, string? DocumentVersion,
    DateTimeOffset? PublishedAt, string Authority, bool IsCurrent, int RuleCount);

public sealed record CardErrataDto(int Id, string? OriginalText, string? CorrectedText, DateTimeOffset? EffectiveAt, string DocumentTitle);
public sealed record CardLegalityDto(string Format, string Status, DateTimeOffset? EffectiveAt);
public sealed record CardRulesDto(List<RuleKeywordSummaryDto> Keywords, List<CardErrataDto> Errata, List<CardLegalityDto> Legalities);
public sealed record CardErrataListItemDto(int Id, string? CardId, string CardName, string? OriginalText, string? CorrectedText, DateTimeOffset? EffectiveAt);
public sealed record CardLegalityListItemDto(int Id, string? CardId, string CardName, string Format, string Status);

/// <summary>
/// The high-level facade the API layer talks to — keeps Program.cs's rules endpoints thin, per the
/// architecture doc's explicit instruction not to put rules business logic directly in Program.cs.
/// Search itself lives in RulesSearchService (enough logic on its own to earn a separate file);
/// everything else here is straightforward reads over the Rules tables.
/// </summary>
public sealed class RulesService(AppDbContext db, RulesSearchService search)
{
    public Task<RuleSearchResponse> SearchAsync(string query, bool currentOnly, int limit, CancellationToken ct = default) =>
        search.SearchAsync(query, currentOnly, limit, ct);

    public async Task<RuleDetailDto?> GetRuleDetailAsync(int id, CancellationToken ct = default)
    {
        var rule = await db.RuleEntries.Include(r => r.Document).FirstOrDefaultAsync(r => r.Id == id, ct);
        if (rule is null) return null;

        var parent = rule.ParentRuleId is null ? null
            : await db.RuleEntries.Include(r => r.Document).FirstOrDefaultAsync(r => r.Id == rule.ParentRuleId, ct);

        var children = await db.RuleEntries.Include(r => r.Document)
            .Where(r => r.ParentRuleId == id).OrderBy(r => r.SortOrder).ToListAsync(ct);

        var previous = await db.RuleEntries.Include(r => r.Document)
            .Where(r => r.DocumentId == rule.DocumentId && r.SortOrder < rule.SortOrder)
            .OrderByDescending(r => r.SortOrder).FirstOrDefaultAsync(ct);
        var next = await db.RuleEntries.Include(r => r.Document)
            .Where(r => r.DocumentId == rule.DocumentId && r.SortOrder > rule.SortOrder)
            .OrderBy(r => r.SortOrder).FirstOrDefaultAsync(ct);

        var keywords = await db.RuleEntryKeywords
            .Where(rk => rk.RuleEntryId == id)
            .Select(rk => rk.Keyword)
            .Select(k => new RuleKeywordSummaryDto(k.Id, k.Name, k.Definition, k.Category, k.CanonicalRuleId))
            .ToListAsync(ct);

        var references = await db.RuleCrossReferences.Where(x => x.FromRuleId == id)
            .Include(x => x.ToRule).ThenInclude(r => r.Document)
            .Select(x => x.ToRule).ToListAsync(ct);
        var referencedBy = await db.RuleCrossReferences.Where(x => x.ToRuleId == id)
            .Include(x => x.FromRule).ThenInclude(r => r.Document)
            .Select(x => x.FromRule).ToListAsync(ct);

        return new RuleDetailDto(
            ToDto(rule), parent is null ? null : ToDto(parent), children.Select(ToDto).ToList(),
            previous is null ? null : ToDto(previous), next is null ? null : ToDto(next),
            keywords, references.Select(ToDto).ToList(), referencedBy.Select(ToDto).ToList());
    }

    public async Task<List<RuleKeywordSummaryDto>> GetKeywordsAsync(CancellationToken ct = default) =>
        await db.RuleKeywords.OrderBy(k => k.Name)
            .Select(k => new RuleKeywordSummaryDto(k.Id, k.Name, k.Definition, k.Category, k.CanonicalRuleId))
            .ToListAsync(ct);

    public async Task<RuleKeywordDetailDto?> GetKeywordDetailAsync(int id, CancellationToken ct = default)
    {
        var keyword = await db.RuleKeywords
            .Include(k => k.CanonicalRule).ThenInclude(r => r!.Document)
            .Include(k => k.Aliases)
            .FirstOrDefaultAsync(k => k.Id == id, ct);
        if (keyword is null) return null;

        var mentioned = await db.RuleEntryKeywords
            .Where(rk => rk.KeywordId == id)
            .Include(rk => rk.RuleEntry).ThenInclude(r => r.Document)
            .Select(rk => rk.RuleEntry)
            .Where(r => r.Id != keyword.CanonicalRuleId)
            .OrderBy(r => r.SortOrder)
            .ToListAsync(ct);

        var cards = await db.CardRuleReferences.Where(x => x.KeywordId == id)
            .Include(x => x.Card)
            .Select(x => x.Card)
            .ToListAsync(ct);

        return new RuleKeywordDetailDto(
            keyword.Id, keyword.Name, keyword.Definition, keyword.Category,
            keyword.Aliases.Select(a => a.Alias).ToList(),
            keyword.CanonicalRule is null ? null : ToDto(keyword.CanonicalRule),
            mentioned.Select(ToDto).ToList(),
            cards.Select(c => new CardSummaryDto(c.Id, c.Name, c.LocalImagePath ?? c.ImageUrl)).ToList());
    }

    public async Task<List<RuleDocumentDto>> GetDocumentsAsync(CancellationToken ct = default)
    {
        var documents = await db.RuleDocuments.Where(d => d.IsCurrent).ToListAsync(ct);
        var counts = await db.RuleEntries.Where(r => r.IsCurrent)
            .GroupBy(r => r.DocumentId)
            .Select(g => new { DocumentId = g.Key, Count = g.Count() })
            .ToDictionaryAsync(x => x.DocumentId, x => x.Count, ct);

        return documents.Select(d => new RuleDocumentDto(
            d.Id, d.SourceType.ToString(), d.Title, d.SourceUrl, d.DocumentVersion,
            d.PublishedAt, d.Authority.ToString(), d.IsCurrent, counts.GetValueOrDefault(d.Id))).ToList();
    }

    public async Task<RuleDocumentDto?> GetDocumentDetailAsync(int id, CancellationToken ct = default)
    {
        var document = await db.RuleDocuments.FirstOrDefaultAsync(d => d.Id == id, ct);
        if (document is null) return null;
        var count = await db.RuleEntries.CountAsync(r => r.DocumentId == id && r.IsCurrent, ct);
        return new RuleDocumentDto(
            document.Id, document.SourceType.ToString(), document.Title, document.SourceUrl, document.DocumentVersion,
            document.PublishedAt, document.Authority.ToString(), document.IsCurrent, count);
    }

    public async Task<CardRulesDto> GetCardRulesAsync(string cardId, CancellationToken ct = default)
    {
        var keywords = await db.CardRuleReferences.Where(x => x.CardId == cardId)
            .Include(x => x.Keyword)
            .Select(x => x.Keyword)
            .Select(k => new RuleKeywordSummaryDto(k.Id, k.Name, k.Definition, k.Category, k.CanonicalRuleId))
            .ToListAsync(ct);

        var errata = await db.CardErrata.Where(x => x.CardId == cardId && x.IsCurrent)
            .Include(x => x.Document)
            .Select(x => new CardErrataDto(x.Id, x.OriginalText, x.CorrectedText, x.EffectiveAt, x.Document.Title))
            .ToListAsync(ct);

        var legalities = await db.CardLegalities.Where(x => x.CardId == cardId && x.IsCurrent)
            .Select(x => new CardLegalityDto(x.Format, x.Status.ToString(), x.EffectiveAt))
            .ToListAsync(ct);

        return new CardRulesDto(keywords, errata, legalities);
    }

    public async Task<List<CardErrataListItemDto>> GetErrataAsync(CancellationToken ct = default) =>
        await db.CardErrata.Where(x => x.IsCurrent)
            .OrderBy(x => x.CardNameRaw)
            .Select(x => new CardErrataListItemDto(x.Id, x.CardId, x.CardNameRaw, x.OriginalText, x.CorrectedText, x.EffectiveAt))
            .ToListAsync(ct);

    public async Task<List<CardErrataDto>> GetErrataForCardAsync(string cardId, CancellationToken ct = default) =>
        await db.CardErrata.Where(x => x.CardId == cardId && x.IsCurrent)
            .Include(x => x.Document)
            .Select(x => new CardErrataDto(x.Id, x.OriginalText, x.CorrectedText, x.EffectiveAt, x.Document.Title))
            .ToListAsync(ct);

    public async Task<List<CardLegalityListItemDto>> GetLegalityAsync(CancellationToken ct = default) =>
        await db.CardLegalities.Where(x => x.IsCurrent)
            .OrderBy(x => x.Format).ThenBy(x => x.CardNameRaw)
            .Select(x => new CardLegalityListItemDto(x.Id, x.CardId, x.CardNameRaw, x.Format, x.Status.ToString()))
            .ToListAsync(ct);

    public async Task<List<CardLegalityDto>> GetLegalityForCardAsync(string cardId, CancellationToken ct = default) =>
        await db.CardLegalities.Where(x => x.CardId == cardId && x.IsCurrent)
            .Select(x => new CardLegalityDto(x.Format, x.Status.ToString(), x.EffectiveAt))
            .ToListAsync(ct);

    private static RuleEntryDto ToDto(RuleEntryEntity r) => new(
        r.Id, r.RuleNumber, r.Title, r.Text, r.Authority.ToString(), r.IsCurrent,
        new RuleDocumentSummaryDto(r.Document.Id, r.Document.Title, r.Document.Authority.ToString(), r.Document.IsCurrent));
}
