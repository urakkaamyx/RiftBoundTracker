namespace RiftBoundTracker.App.Data;

// Links a local card to an official keyword its own rules text mentions (e.g. a card printed with
// "Exhaust this unit..." links to the Exhaust keyword) so a card detail screen can show "Rules
// References" without touching the card's own text. Metadata only — never alters CardEntity.
public class CardRuleReferenceEntity
{
    public int Id { get; set; }
    public string CardId { get; set; } = "";
    public int KeywordId { get; set; }

    public CardEntity Card { get; set; } = null!;
    public RuleKeywordEntity Keyword { get; set; } = null!;
}
