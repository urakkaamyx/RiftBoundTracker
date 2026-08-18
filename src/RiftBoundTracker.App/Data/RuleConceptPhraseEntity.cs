namespace RiftBoundTracker.App.Data;

// A curated player phrase that signals a concept even when no official keyword is present in the
// question at all (e.g. "dies" / "destroyed" / "leaves play" all signal the Unit Death concept).
// Hand-curated only — never speculatively generated, same discipline as RuleKeywordAliasEntity.
public class RuleConceptPhraseEntity
{
    public int Id { get; set; }
    public int ConceptId { get; set; }
    public string Phrase { get; set; } = "";
    public string NormalizedPhrase { get; set; } = "";

    public RuleConceptEntity Concept { get; set; } = null!;
}
