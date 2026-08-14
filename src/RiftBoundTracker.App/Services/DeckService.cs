using System.Text;
using System.Text.RegularExpressions;
using Microsoft.EntityFrameworkCore;
using RiftBoundTracker.App.Data;

namespace RiftBoundTracker.App.Services;

public record DeckSummaryDto(
    int Id, string Name, string Description, string Format, string? CoverCardId,
    string? CoverImagePath, int MainCount, int SideboardCount, int UniqueCards,
    int OwnedCount, int MissingCount, DateTimeOffset UpdatedAt);

public record DeckCardDto(
    string CardId, string Section, int Quantity, int Owned, int Missing, CardEntity Card);

public record DeckDetailDto(DeckSummaryDto Summary, List<DeckCardDto> Cards);

public record CreateDeckRequest(string? Name, string? Description, string? Format, string? CoverCardId);
public record UpdateDeckRequest(string? Name, string? Description, string? Format, string? CoverCardId);
public record SetDeckCardRequest(string CardId, int Quantity, string? Section);
public record ImportDeckRequest(string? Name, string? Description, string? Format, string Contents);
public record DeckImportResult(int DeckId, int AddedLines, List<string> UnmatchedLines);

public partial class DeckService(AppDbContext db, CardCacheService cache)
{
    public async Task<List<DeckSummaryDto>> GetAllAsync(CancellationToken ct = default)
    {
        var decks = await db.Decks
            .AsNoTracking()
            .Include(d => d.Cards)
            .ThenInclude(dc => dc.Card)
            .ToListAsync(ct);

        return decks.OrderByDescending(d => d.UpdatedAt).Select(ToSummary).ToList();
    }

    public async Task<DeckDetailDto?> GetAsync(int id, CancellationToken ct = default)
    {
        var deck = await db.Decks
            .AsNoTracking()
            .Include(d => d.Cards)
            .ThenInclude(dc => dc.Card)
            .SingleOrDefaultAsync(d => d.Id == id, ct);
        return deck is null ? null : ToDetail(deck);
    }

    public async Task<DeckDetailDto> CreateAsync(CreateDeckRequest request, CancellationToken ct = default)
    {
        var now = DateTimeOffset.UtcNow;
        var deck = new DeckEntity
        {
            Name = Clean(request.Name, "New Deck", 80),
            Description = Clean(request.Description, "", 500),
            Format = Clean(request.Format, "Standard", 40),
            CoverCardId = await ValidCardIdAsync(request.CoverCardId, ct),
            CreatedAt = now,
            UpdatedAt = now,
        };
        db.Decks.Add(deck);
        await db.SaveChangesAsync(ct);
        return ToDetail(deck);
    }

    public async Task<DeckDetailDto?> UpdateAsync(int id, UpdateDeckRequest request, CancellationToken ct = default)
    {
        var deck = await db.Decks
            .Include(d => d.Cards)
            .ThenInclude(dc => dc.Card)
            .SingleOrDefaultAsync(d => d.Id == id, ct);
        if (deck is null) return null;

        deck.Name = Clean(request.Name, deck.Name, 80);
        deck.Description = Clean(request.Description, deck.Description, 500);
        deck.Format = Clean(request.Format, deck.Format, 40);
        deck.CoverCardId = string.IsNullOrWhiteSpace(request.CoverCardId)
            ? deck.CoverCardId
            : await ValidCardIdAsync(request.CoverCardId, ct);
        deck.UpdatedAt = DateTimeOffset.UtcNow;
        await db.SaveChangesAsync(ct);
        return ToDetail(deck);
    }

    public async Task<bool> DeleteAsync(int id, CancellationToken ct = default)
    {
        var deck = await db.Decks.FindAsync([id], ct);
        if (deck is null) return false;
        db.Decks.Remove(deck);
        await db.SaveChangesAsync(ct);
        return true;
    }

    public async Task<DeckDetailDto?> SetCardAsync(int id, SetDeckCardRequest request, CancellationToken ct = default)
    {
        var deck = await db.Decks.FindAsync([id], ct);
        var card = await db.Cards.FindAsync([request.CardId], ct);
        if (deck is null || card is null) return null;

        var section = NormalizeSection(request.Section);
        var row = await db.DeckCards.FindAsync([id, request.CardId, section], ct);
        var quantity = Math.Clamp(request.Quantity, 0, 99);

        if (quantity == 0)
        {
            if (row is not null) db.DeckCards.Remove(row);
        }
        else if (row is null)
        {
            db.DeckCards.Add(new DeckCardEntity
            {
                DeckId = id,
                CardId = request.CardId,
                Section = section,
                Quantity = quantity,
            });
        }
        else
        {
            row.Quantity = quantity;
        }

        deck.CoverCardId ??= request.CardId;
        deck.UpdatedAt = DateTimeOffset.UtcNow;
        await db.SaveChangesAsync(ct);
        return await GetAsync(id, ct);
    }

    public async Task<DeckImportResult> ImportAsync(ImportDeckRequest request, CancellationToken ct = default)
    {
        var created = await CreateAsync(new CreateDeckRequest(
            request.Name ?? "Imported Deck", request.Description, request.Format, null), ct);
        var unmatched = new List<string>();
        var added = 0;

        foreach (var rawLine in request.Contents.Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries))
        {
            var line = rawLine.Trim();
            if (line.Length == 0 || line.StartsWith('#')) continue;

            var match = ImportLinePattern().Match(line);
            if (!match.Success)
            {
                unmatched.Add(line);
                continue;
            }

            var quantity = match.Groups["qty"].Success ? int.Parse(match.Groups["qty"].Value) : 1;
            var setId = match.Groups["set"].Value;
            var code = match.Groups["code"].Value;
            var cards = await cache.FindByCodeAsync(setId, code, ct);
            if (cards.Count != 1)
            {
                unmatched.Add(line);
                continue;
            }

            var existing = await db.DeckCards.FindAsync([created.Summary.Id, cards[0].Id, "main"], ct);
            if (existing is null)
            {
                db.DeckCards.Add(new DeckCardEntity
                {
                    DeckId = created.Summary.Id,
                    CardId = cards[0].Id,
                    Section = "main",
                    Quantity = Math.Clamp(quantity, 1, 99),
                });
            }
            else
            {
                existing.Quantity = Math.Clamp(existing.Quantity + quantity, 1, 99);
            }
            added++;
        }

        var deck = await db.Decks.FindAsync([created.Summary.Id], ct);
        if (deck is not null)
        {
            deck.UpdatedAt = DateTimeOffset.UtcNow;
            await db.SaveChangesAsync(ct);
        }

        return new DeckImportResult(created.Summary.Id, added, unmatched);
    }

    public async Task<string?> ExportAsync(int id, CancellationToken ct = default)
    {
        var detail = await GetAsync(id, ct);
        if (detail is null) return null;

        var text = new StringBuilder();
        text.AppendLine($"# {detail.Summary.Name}");
        text.AppendLine($"# Format: {detail.Summary.Format}");
        if (!string.IsNullOrWhiteSpace(detail.Summary.Description))
            text.AppendLine($"# {detail.Summary.Description}");

        foreach (var section in detail.Cards.GroupBy(c => c.Section).OrderBy(g => g.Key))
        {
            text.AppendLine();
            text.AppendLine($"# {section.Key}");
            foreach (var row in section.OrderBy(c => c.Card.Type).ThenBy(c => c.Card.Energy).ThenBy(c => c.Card.Name))
                text.AppendLine($"{row.Quantity} {row.Card.SetId}-{CardCode(row.Card)} {row.Card.Name}");
        }
        return text.ToString();
    }

    private async Task<string?> ValidCardIdAsync(string? cardId, CancellationToken ct)
    {
        if (string.IsNullOrWhiteSpace(cardId)) return null;
        return await db.Cards.AnyAsync(c => c.Id == cardId, ct) ? cardId : null;
    }

    private static DeckDetailDto ToDetail(DeckEntity deck)
    {
        var cards = deck.Cards
            .OrderBy(dc => dc.Section)
            .ThenBy(dc => dc.Card.Type)
            .ThenBy(dc => dc.Card.Energy)
            .ThenBy(dc => dc.Card.Name)
            .Select(dc => new DeckCardDto(
                dc.CardId, dc.Section, dc.Quantity,
                Math.Min(dc.Quantity, dc.Card.OwnedCount),
                Math.Max(0, dc.Quantity - dc.Card.OwnedCount),
                dc.Card))
            .ToList();
        return new DeckDetailDto(ToSummary(deck), cards);
    }

    private static DeckSummaryDto ToSummary(DeckEntity deck)
    {
        var main = deck.Cards.Where(c => c.Section == "main").Sum(c => c.Quantity);
        var side = deck.Cards.Where(c => c.Section == "sideboard").Sum(c => c.Quantity);
        var owned = deck.Cards.Sum(c => Math.Min(c.Quantity, c.Card.OwnedCount));
        var required = deck.Cards.Sum(c => c.Quantity);
        var cover = deck.Cards.FirstOrDefault(c => c.CardId == deck.CoverCardId)?.Card.LocalImagePath
                    ?? deck.Cards.FirstOrDefault()?.Card.LocalImagePath;
        return new DeckSummaryDto(
            deck.Id, deck.Name, deck.Description, deck.Format, deck.CoverCardId, cover,
            main, side, deck.Cards.Count, owned, Math.Max(0, required - owned), deck.UpdatedAt);
    }

    private static string NormalizeSection(string? section) =>
        string.Equals(section, "sideboard", StringComparison.OrdinalIgnoreCase) ? "sideboard" : "main";

    private static string Clean(string? value, string fallback, int maxLength)
    {
        var clean = string.IsNullOrWhiteSpace(value) ? fallback : value.Trim();
        return clean.Length <= maxLength ? clean : clean[..maxLength];
    }

    private static string CardCode(CardEntity card) =>
        string.IsNullOrWhiteSpace(card.CollectorCode)
            ? card.CollectorNumber.ToString("000")
            : card.CollectorCode;

    [GeneratedRegex(@"^(?:(?<qty>\d{1,2})\s*[xX]?\s+)?(?<set>[A-Za-z]{2,4})[-\s]+(?<code>[A-Za-z]{0,2}\d{1,3}[A-Za-z]?)\b")]
    private static partial Regex ImportLinePattern();
}
