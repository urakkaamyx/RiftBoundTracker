namespace RiftBoundTracker.App.Data;

// Player/other-TCG terminology mapped to the official term ("tap" -> Exhaust) so a search for the
// familiar word still lands on the right rule, while the UI can still say what the official name is.
public class RuleKeywordAliasEntity
{
    public int Id { get; set; }
    public int KeywordId { get; set; }
    public string Alias { get; set; } = "";
    public string NormalizedAlias { get; set; } = "";

    public RuleKeywordEntity Keyword { get; set; } = null!;
}
