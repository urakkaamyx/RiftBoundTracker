namespace RiftBoundTracker.App.Data;

// A broader rule idea spanning multiple official terms (e.g. "Unit Death" covers Destroy, dying,
// leaving play) so a question phrased in plain English ("my unit dies") can still reach the right
// keywords/rules even when it never uses the exact official term.
public class RuleConceptEntity
{
    public int Id { get; set; }
    public string Name { get; set; } = "";
    public string NormalizedName { get; set; } = "";
    public string? Description { get; set; }

    public ICollection<RuleConceptKeywordEntity> Keywords { get; set; } = [];
    public ICollection<RuleConceptPhraseEntity> Phrases { get; set; } = [];
}
