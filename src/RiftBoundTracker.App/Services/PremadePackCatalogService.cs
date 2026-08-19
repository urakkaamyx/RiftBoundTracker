namespace RiftBoundTracker.App.Services;

public sealed record PremadePackCardEntry(string CardName, int Quantity);
public sealed record PremadePackDefinition(string Key, string Name, string Wave, List<PremadePackCardEntry> Cards);

/// <summary>
/// Hand-curated contents of official preconstructed "Champion Deck" products, so someone who buys
/// one physically can add its exact contents to their tracked collection in one action instead of
/// looking up and incrementing every card by hand.
///
/// Sourced from the Origins Champion Decks Reddit thread (user-supplied product photos, since the
/// original playriftbound.com announcement for these three has since been retired from the site
/// and isn't reachable through any source this app is willing to fetch — several third-party sites
/// that mirror it explicitly block AI/Claude access via robots.txt). Deliberately NOT scraped —
/// every card name here was manually transcribed from a screenshot.
///
/// Card names are transcribed as printed on the product; PremadePackImportService resolves them
/// against the catalog the same way deck import does (including the comma/dash and comma-suffix
/// name fallbacks in CardCacheService.FindByNameAsync), so a transcription mismatch surfaces as an
/// unmatched card in the import result rather than silently applying to the wrong one.
/// </summary>
public static class PremadePackCatalogService
{
    public static readonly List<PremadePackDefinition> Packs =
    [
        new("origins-viktor", "Viktor Champion Deck", "Origins", [
            new("Viktor - Herald of the Arcane", 1),
            new("Viktor, Innovator", 1),
            new("Trifarian War Camp", 1),
            new("The Grand Plaza", 1),
            new("Altar to Unity", 1),
            new("Mind Rune", 6),
            new("Order Rune", 6),
            new("Orb of Regret", 2),
            new("Cull the Weak", 3),
            new("Hidden Blade", 2),
            new("Consult the Past", 2),
            new("Smoke Screen", 2),
            new("Back to Back", 2),
            new("Sprite Call", 2),
            new("Soaring Scout", 3),
            new("Stupefy", 2),
            new("Eager Apprentice", 3),
            new("Cruel Patron", 3),
            new("Jeweled Colossus", 2),
            new("Mushroom Pouch", 2),
            new("Ravenbloom Student", 3),
            new("Noxian Drummer", 3),
            new("Wraith of Echoes", 1),
            new("Grand Strategem", 1),
            new("Heimerdinger, Inventor", 1),
        ]),
        new("origins-jinx", "Jinx Champion Deck", "Origins", [
            new("Jinx - Loose Cannon", 1),
            new("Jinx, Demolitionist", 1),
            new("Targon's Peak", 1),
            new("Zaun Warrens", 1),
            new("Reaver's Row", 1),
            new("Fury Rune", 6),
            new("Chaos Rune", 6),
            new("Flame Chompers", 3),
            new("Blazing Scorcher", 2),
            new("Fight or Flight", 3),
            new("Get Excited!", 2),
            new("Gust", 3),
            new("Cemetery Attendant", 2),
            new("Undercover Agent", 2),
            new("Chemtech Enforcer", 3),
            new("Brazen Buccaneer", 3),
            new("Magma Wurm", 1),
            new("Void Seeker", 2),
            new("Fading Memories", 2),
            new("Traveling Merchant", 3),
            new("Scrapheap", 3),
            new("Raging Soul", 3),
            new("Vi, Destructive", 1),
            new("Rhasa the Sunderer", 1),
        ]),
        new("origins-lee-sin", "Lee Sin Champion Deck", "Origins", [
            new("Lee Sin - Blind Monk", 1),
            new("Lee Sin, Centered", 1),
            new("Monastery of Hirana", 1),
            new("Targon's Peak", 1),
            new("Grove of the God-Willow", 1),
            new("Calm Rune", 6),
            new("Body Rune", 6),
            new("Stalwart Poro", 3),
            new("Pit Rookie", 3),
            new("Wielder of Water", 3),
            new("First Mate", 3),
            new("Charm", 2),
            new("Challenge", 3),
            new("Stand United", 3),
            new("Pakaa Cub", 2),
            new("Bilgewater Bully", 2),
            new("Stormclaw Ursine", 2),
            new("Discipline", 3),
            new("Wildclaw Shaman", 3),
            new("Mask of Foresight", 1),
            new("Mountain Drake", 2),
            new("Wizened Elder", 3),
            new("Mistfall", 1),
            new("Udyr, Wildman", 1),
        ]),
    ];
}
