using Microsoft.EntityFrameworkCore;
using RiftBoundTracker.App.Data;

namespace RiftBoundTracker.App.Services;

public class CardTextSymbolCatalogService(AppDbContext db)
{
    private static readonly (string Name, string Color)[] RuneSymbols =
    [
        ("body", "#E87600"),
        ("calm", "#488C38"),
        ("chaos", "#6A4094"),
        ("fury", "#DF1620"),
        ("mind", "#0F6FA6"),
        ("order", "#D2B400"),
        ("rainbow", "multicolor")
    ];

    private static readonly (string Name, string Family)[] KeywordBadges =
    [
        ("accelerate", "teal"), ("action", "teal"), ("ambush", "teal"),
        ("flow", "teal"), ("hidden", "teal"), ("legion", "teal"),
        ("quick-draw", "teal"), ("reaction", "teal"), ("repeat", "teal"),

        ("add", "gray"), ("buff", "gray"),
        ("burn", "gray"), ("empower", "gray"), ("equip", "gray"),
        ("mighty", "gray"), ("predict", "gray"), ("stun", "gray"),
        ("temporary", "gray"), ("unique", "gray"), ("weaponmaster", "gray"),
        ("vision", "gray"),

        ("assault", "magenta"), ("backline", "magenta"), ("shield", "magenta"),
        ("tank", "magenta"),

        ("deathknell", "lime"), ("deflect", "lime"), ("empowered", "lime"),
        ("ganking", "lime"), ("hunt", "lime"), ("level", "lime")
    ];

    public async Task EnsureSeededAsync(CancellationToken ct = default)
    {
        var existing = await db.CardTextSymbols.ToDictionaryAsync(s => s.Token, ct);
        foreach (var definition in BuildDefinitions())
        {
            if (!existing.TryGetValue(definition.Token, out var entity))
            {
                db.CardTextSymbols.Add(definition);
                continue;
            }

            entity.Label = definition.Label;
            entity.Kind = definition.Kind;
            entity.Shape = definition.Shape;
            entity.AssetPath = definition.AssetPath;
            entity.ForegroundColor = definition.ForegroundColor;
            entity.BackgroundColor = definition.BackgroundColor;
            entity.BorderColor = definition.BorderColor;
            entity.SortOrder = definition.SortOrder;
        }

        await db.SaveChangesAsync(ct);
    }

    public Task<List<CardTextSymbolEntity>> GetAllAsync(CancellationToken ct = default) =>
        db.CardTextSymbols
            .AsNoTracking()
            .OrderBy(s => s.SortOrder)
            .ThenBy(s => s.Token)
            .ToListAsync(ct);

    private static IEnumerable<CardTextSymbolEntity> BuildDefinitions()
    {
        for (var value = 0; value <= 12; value++)
        {
            yield return Symbol(
                $":rb_energy_{value}:", $"{value} Energy", "energy", "circle",
                $"/assets/riftbound-symbols/energy_{value}.svg", "#013951", "#FFFFFF", "#FFFFFF", value);
        }

        yield return Symbol(":rb_exhaust:", "Exhaust", "action", "official-glyph",
            "/assets/riftbound-symbols/exhaust.svg", "#FFFFFF", "transparent", "transparent", 20);
        yield return Symbol(":rb_might:", "Might", "stat", "official-glyph",
            "/assets/riftbound-symbols/might.svg", "#FFFFFF", "transparent", "transparent", 21);

        var runeOrder = 30;
        foreach (var (name, color) in RuneSymbols)
        {
            yield return Symbol(
                $":rb_rune_{name}:", $"{TitleCase(name)} Rune", "rune", name == "rainbow" ? "rainbow" : "circle",
                $"/assets/riftbound-symbols/rune_{name}.svg", "#FFFFFF", color, color, runeOrder++);
        }

        var keywordOrder = 100;
        foreach (var (name, family) in KeywordBadges)
        {
            var (foreground, background, border) = family switch
            {
                "teal" => ("#FFFFFF", "#0B8775", "#0B8775"),
                "magenta" => ("#FFFFFF", "#D63F78", "#D63F78"),
                "lime" => ("#142019", "#A7C92A", "#A7C92A"),
                _ => ("#FFFFFF", "#777A78", "#777A78")
            };
            yield return Symbol(
                $"keyword:{name}", TitleCase(name), "keyword", $"slanted-{family}",
                null, foreground, background, border, keywordOrder++);
        }

        yield return Symbol("keyword:>", "Ability separator", "separator", "divider",
            null, "#6D6A61", "transparent", "transparent", 200);
        yield return Symbol("keyword:>>", "Ability separator", "separator", "double-divider",
            null, "#6D6A61", "transparent", "transparent", 201);
    }

    private static CardTextSymbolEntity Symbol(
        string token, string label, string kind, string shape, string? assetPath,
        string foreground, string background, string border, int order) => new()
        {
            Token = token,
            Label = label,
            Kind = kind,
            Shape = shape,
            AssetPath = assetPath,
            ForegroundColor = foreground,
            BackgroundColor = background,
            BorderColor = border,
            SortOrder = order
        };

    private static string TitleCase(string value) =>
        string.Join('-', value.Split('-').Select(part =>
            part.Length == 0 ? part : char.ToUpperInvariant(part[0]) + part[1..]));
}
