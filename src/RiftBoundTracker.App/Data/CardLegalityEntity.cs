namespace RiftBoundTracker.App.Data;

public enum CardLegalityStatus { Legal, Banned, Restricted, NotLegal }

// One card/battlefield/legend's status in one format, parsed straight out of the Rules Hub's
// legality tables. CardId resolves the same way as CardErrataEntity — battlefields and legends are
// ordinary CardEntity rows in this app's catalog (Type = Battlefield / Legend), so the same
// name-based lookup covers all three without special-casing.
public class CardLegalityEntity
{
    public int Id { get; set; }
    public string? CardId { get; set; }
    public string CardNameRaw { get; set; } = "";
    public string Format { get; set; } = "";
    public CardLegalityStatus Status { get; set; }
    public DateTimeOffset? EffectiveAt { get; set; }
    public int DocumentId { get; set; }
    public bool IsCurrent { get; set; } = true;

    public RuleDocumentEntity Document { get; set; } = null!;
    public CardEntity? Card { get; set; }
}
