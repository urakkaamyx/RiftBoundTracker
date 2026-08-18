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
            // Clear a stale cover pointing at the card that was just removed — otherwise ??=
            // below never fires again (it's not null, just pointing at a card no longer in the
            // deck) and the deck keeps showing art for a Legend it doesn't have anymore.
            if (deck.CoverCardId == request.CardId) deck.CoverCardId = null;
        }
        else
        {
            if (row is null)
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

            // A newly-added Legend always takes over as the deck's cover — a deck should show
            // its current Legend, not whichever card happened to be added first.
            if (card.Type == "Legend") deck.CoverCardId = request.CardId;
            else deck.CoverCardId ??= request.CardId;
        }

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
        string? legendCardId = null;

        // Tracks which section subsequent card lines belong to as we scan — both export formats
        // mark section boundaries with header lines rather than repeating "main"/"sideboard" per
        // card, so the current section has to carry forward until the next header changes it.
        // RiftKeep marks section boundaries as "# main" / "# sideboard" comment lines; RiftAtlas
        // uses "Sideboard:" (and other non-sideboard headers like "Legend:"/"MainDeck:", which all
        // map to "main" since this app only tracks two sections).
        var currentSection = "main";
        foreach (var rawLine in request.Contents.Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries))
        {
            var line = rawLine.Trim();
            if (line.Length == 0) continue;

            if (line.StartsWith('#'))
            {
                var comment = line.TrimStart('#').Trim();
                if (string.Equals(comment, "sideboard", StringComparison.OrdinalIgnoreCase)) currentSection = "sideboard";
                else if (string.Equals(comment, "main", StringComparison.OrdinalIgnoreCase)) currentSection = "main";
                continue;
            }

            var headerMatch = SectionHeaderPattern().Match(line);
            if (headerMatch.Success)
            {
                currentSection = string.Equals(headerMatch.Groups["name"].Value, "Sideboard", StringComparison.OrdinalIgnoreCase)
                    ? "sideboard" : "main";
                continue;
            }

            // Accept RiftKeep's "{qty} {set}-{code} {name}" lines, RiftAtlas' "{qty} {name}
            // [{set}-{code}]" lines, or a bare "{qty} {name}" line with no set/code at all (e.g.
            // a RiftDecks export) — auto-detected per line, tried in that order, so a paste can
            // even mix formats without the user picking one.
            int quantity;
            List<CardEntity> cards;
            var match = ImportLinePattern().Match(line);
            if (match.Success)
            {
                quantity = match.Groups["qty"].Success ? int.Parse(match.Groups["qty"].Value) : 1;
                cards = await cache.FindByCodeAsync(match.Groups["set"].Value, match.Groups["code"].Value, ct);
                if (cards.Count != 1) cards = [];
            }
            else if ((match = RiftAtlasImportLinePattern().Match(line)).Success)
            {
                quantity = int.Parse(match.Groups["qty"].Value);
                cards = await cache.FindByCodeAsync(match.Groups["set"].Value, match.Groups["code"].Value, ct);
                if (cards.Count != 1) cards = [];
            }
            else if ((match = NameOnlyImportLinePattern().Match(line)).Success)
            {
                quantity = int.Parse(match.Groups["qty"].Value);
                // Multiple matches (the rare pair of prints sharing an identical unsuffixed name)
                // resolve to the first result — FindByNameAsync already orders those toward a
                // deterministic base-print pick rather than rejecting the line outright.
                cards = await cache.FindByNameAsync(match.Groups["name"].Value, ct);
            }
            else
            {
                unmatched.Add(line);
                continue;
            }

            if (cards.Count == 0)
            {
                unmatched.Add(line);
                continue;
            }

            if (cards[0].Type == "Legend") legendCardId ??= cards[0].Id;

            var existing = await db.DeckCards.FindAsync([created.Summary.Id, cards[0].Id, currentSection], ct);
            if (existing is null)
            {
                db.DeckCards.Add(new DeckCardEntity
                {
                    DeckId = created.Summary.Id,
                    CardId = cards[0].Id,
                    Section = currentSection,
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
            deck.CoverCardId ??= legendCardId;
            deck.UpdatedAt = DateTimeOffset.UtcNow;
            await db.SaveChangesAsync(ct);
        }

        return new DeckImportResult(created.Summary.Id, added, unmatched);
    }

    public async Task<string?> ExportAsync(int id, string? format, CancellationToken ct = default)
    {
        var detail = await GetAsync(id, ct);
        if (detail is null) return null;

        return string.Equals(format, "riftatlas", StringComparison.OrdinalIgnoreCase)
            ? ExportRiftAtlas(detail)
            : ExportRiftKeep(detail);
    }

    private static string ExportRiftKeep(DeckDetailDto detail)
    {
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

    // RiftAtlas' community decklist format: sections split out by role rather than by main/sideboard
    // alone (Legend and Champion get their own headers even though both live in the "main" section),
    // each line reading "{qty} {name} [{set}-{code}]". Sideboard stays a single flat list regardless
    // of card type, matching how RiftAtlas exports it.
    private static string ExportRiftAtlas(DeckDetailDto detail)
    {
        var main = detail.Cards.Where(c => c.Section == "main").ToLookup(AtlasCategory);
        var side = detail.Cards.Where(c => c.Section == "sideboard").ToList();

        var text = new StringBuilder();
        AppendAtlasSection(text, "Legend", main["Legend"]);
        AppendAtlasSection(text, "Champion", main["Champion"]);
        AppendAtlasSection(text, "MainDeck", main["MainDeck"]);
        AppendAtlasSection(text, "Battlefields", main["Battlefield"]);
        AppendAtlasSection(text, "Runes", main["Rune"]);
        AppendAtlasSection(text, "Sideboard", side);
        return text.ToString();
    }

    private static string AtlasCategory(DeckCardDto row)
    {
        if (row.Card.Type == "Legend") return "Legend";
        if (string.Equals(row.Card.Supertype, "Champion", StringComparison.OrdinalIgnoreCase)) return "Champion";
        if (row.Card.Type == "Battlefield") return "Battlefield";
        if (row.Card.Type == "Rune") return "Rune";
        return "MainDeck";
    }

    private static void AppendAtlasSection(StringBuilder text, string title, IEnumerable<DeckCardDto> rows)
    {
        var ordered = rows
            .OrderByDescending(r => r.Quantity)
            .ThenBy(r => r.Card.SetId)
            .ThenBy(r => r.Card.CollectorNumber)
            .ThenBy(r => r.Card.CollectorCode)
            .ThenBy(r => r.Card.Name)
            .ToList();
        if (ordered.Count == 0) return;
        if (text.Length > 0) text.AppendLine();
        text.AppendLine($"{title}:");
        foreach (var row in ordered)
            text.AppendLine($"{row.Quantity} {row.Card.Name} [{row.Card.SetId}-{CardCode(row.Card)}]");
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

    [GeneratedRegex(@"^(?<qty>\d{1,2})\s+.+?\[(?<set>[A-Za-z]{2,4})-(?<code>[A-Za-z]{0,2}\d{1,3}[A-Za-z]?)\]\s*$")]
    private static partial Regex RiftAtlasImportLinePattern();

    // Last-resort fallback for exports with no set/collector code at all (e.g. a RiftDecks
    // export) — just "{qty} {name}". Tried only after both code-based patterns fail.
    [GeneratedRegex(@"^(?<qty>\d{1,2})\s+(?<name>.+?)\s*$")]
    private static partial Regex NameOnlyImportLinePattern();

    [GeneratedRegex(@"^(?<name>[A-Za-z][A-Za-z ]*):$")]
    private static partial Regex SectionHeaderPattern();
}
