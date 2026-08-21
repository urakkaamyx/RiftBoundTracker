using Microsoft.EntityFrameworkCore;
using RiftBoundTracker.App.Data;

namespace RiftBoundTracker.App.Services.Rules;

/// <summary>
/// Seeds broader rule concepts (mirrors RulesKeywordCatalogService's hand-curated pattern) so a
/// question phrased in plain English — "my unit dies", "leave the fight" — still reaches the right
/// keywords/rules even when it never uses the exact official term. Curated from the Ask Rules
/// architecture doc's own worked examples plus this app's real seeded keyword list; never
/// auto-generated, since a wrong concept link would silently mislead a rules question.
/// </summary>
public class RulesConceptCatalogService(AppDbContext db)
{
    private static readonly (string Name, string[] Phrases, string[] Keywords)[] Concepts =
    [
        // "Kill" isn't itself a glossary keyword (it's a plain rule action, not a card-facing
        // keyword ability like "Destroy" is) — the rule that actually governs it (428.2: a killed
        // permanent goes to the trash) is only reachable via the "Trash" keyword, which it's tagged
        // under. Without it, a "my unit died" question never surfaces the one rule that explains
        // what happens to it.
        ("Unit Death", ["dies", "died", "destroyed", "killed", "defeated", "kill a unit"], ["Destroy", "Trash"]),
        ("Leaving Battlefield", ["leaves play", "leave the battlefield", "removed from the battle", "remove from combat", "leave the fight"], ["Banish", "Recycle", "Trash"]),
        ("Battlefield Control", ["control", "controls", "controlled", "occupied", "uncontrolled"], ["Control", "Conquer", "Battlefield"]),
        ("Hidden Cards", ["hidden", "facedown", "face down", "face-down"], ["Hidden"]),
        ("Combat Resolution", ["combat", "fight", "attack", "attacks", "defend", "defends", "showdown"], ["Damage", "Deflect", "Showdown"]),
        ("Triggered Abilities", ["trigger", "triggers", "triggered ability", "when i", "whenever"], ["Trigger", "Reaction"]),
        ("Effect Resolution", ["resolve", "resolves", "resolution", "stack", "chain"], ["Chain"]),
        ("Movement", ["move", "moves", "moving", "move to another battlefield"], ["Ganking"]),
        ("Card State", ["tap", "untap", "tapped", "untapped", "exhausted", "ready", "stunned"], ["Exhaust", "Ready", "Stun"]),
        ("Deck Construction", ["deckbuilding", "deck construction", "build a deck", "domain identity", "color identity"], ["Domain Identity", "Chosen Champion", "Champion Legend", "Domain"]),
        ("Healing", ["heal", "healing", "heals", "restore"], ["Heal"]),
        // Real bug this fixes: a question about playing a unit directly to a battlefield you
        // control (rule 355.2.a) never surfaced that rule as evidence, even after the "Control"
        // keyword's under-tagging was fixed separately — with "Control" now correctly tagging 239
        // rules instead of 90, dozens of them tie for score on any question mentioning control and
        // battlefield together (this game is fundamentally about battlefield control), and 355.2.a
        // has nothing to distinguish it from the crowd. It's also tagged "Location" — a keyword the
        // question's own wording never triggers on its own, since nobody phrases it as "what's a
        // valid location." This concept bridges that gap: it gives 355.2.a a third keyword hit
        // (Location, on top of Control and Battlefield) specifically when the question is actually
        // about where a unit can be played, which outranks every rule that only shares the generic
        // Control+Battlefield pair.
        ("Valid Play Locations", ["play directly to a battlefield", "play to a battlefield", "play units to a battlefield", "bypass base", "bypass my base", "bypass playing to base", "instead of my base", "instead of playing to base", "without playing to base", "skip playing to base", "playing to base"], ["Location"]),
    ];

    public async Task EnsureSeededAsync(CancellationToken ct = default)
    {
        var keywordsByName = await db.RuleKeywords.ToDictionaryAsync(k => k.NormalizedName, ct);
        var existing = await db.RuleConcepts
            .Include(c => c.Phrases)
            .Include(c => c.Keywords)
            .ToDictionaryAsync(c => c.NormalizedName, ct);

        foreach (var (name, phrases, keywordNames) in Concepts)
        {
            var normalized = RulesKeywordCatalogService.Normalize(name);
            if (!existing.TryGetValue(normalized, out var concept))
            {
                concept = new RuleConceptEntity { Name = name, NormalizedName = normalized };
                db.RuleConcepts.Add(concept);
            }
            concept.Name = name;

            var existingPhrases = concept.Phrases.Select(p => p.NormalizedPhrase).ToHashSet();
            foreach (var phrase in phrases)
            {
                var normalizedPhrase = RulesKeywordCatalogService.Normalize(phrase);
                if (existingPhrases.Contains(normalizedPhrase)) continue;
                concept.Phrases.Add(new RuleConceptPhraseEntity { Phrase = phrase, NormalizedPhrase = normalizedPhrase });
            }

            var existingKeywordIds = concept.Keywords.Select(k => k.KeywordId).ToHashSet();
            foreach (var keywordName in keywordNames)
            {
                if (!keywordsByName.TryGetValue(RulesKeywordCatalogService.Normalize(keywordName), out var keyword)) continue;
                if (existingKeywordIds.Contains(keyword.Id)) continue;
                concept.Keywords.Add(new RuleConceptKeywordEntity { KeywordId = keyword.Id });
            }
        }

        await db.SaveChangesAsync(ct);
    }
}
