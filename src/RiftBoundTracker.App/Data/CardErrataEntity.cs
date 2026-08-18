namespace RiftBoundTracker.App.Data;

// One card's old-text -> new-text correction from an official errata article. CardId is resolved
// via CardCacheService.FindByNameAsync (the same base-print-preferring lookup the RiftDecks import
// uses) and left null — never guessed — when the raw printed name doesn't resolve, so the entry is
// still tracked and visible rather than silently dropped.
public class CardErrataEntity
{
    public int Id { get; set; }
    public string? CardId { get; set; }
    public string CardNameRaw { get; set; } = "";
    public int DocumentId { get; set; }

    public string? OriginalText { get; set; }
    public string? CorrectedText { get; set; }
    public DateTimeOffset? EffectiveAt { get; set; }
    public bool IsCurrent { get; set; } = true;

    public RuleDocumentEntity Document { get; set; } = null!;
    public CardEntity? Card { get; set; }
}
