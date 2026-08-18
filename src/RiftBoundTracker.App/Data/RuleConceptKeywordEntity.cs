namespace RiftBoundTracker.App.Data;

// Concept <-> official keyword many-to-many — a concept is "active" for a question either because
// one of its phrases matched, or because one of its linked keywords was independently detected.
public class RuleConceptKeywordEntity
{
    public int ConceptId { get; set; }
    public int KeywordId { get; set; }

    public RuleConceptEntity Concept { get; set; } = null!;
    public RuleKeywordEntity Keyword { get; set; } = null!;
}
