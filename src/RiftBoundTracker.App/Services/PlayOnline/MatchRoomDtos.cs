namespace RiftBoundTracker.App.Services.PlayOnline;

// The wire shape sent to clients - never MatchRoom/BoardState/PlayerZones directly, so hand
// redaction (see MatchRoomService.ToView) can never accidentally be bypassed by serializing the
// real model. Hand is null for every player except the viewer themselves; HandCount is always
// present so a viewer can see how many cards an opponent is holding without seeing what they are.
public sealed record UnitInstanceView(string InstanceId, string CardId, string ControllerConnectionId, bool Exhausted, int Damage, string? AttachedToInstanceId);

public sealed record PlayerZonesView(
    int HandCount, List<string>? Hand,
    int MainDeckCount, int RuneDeckCount, List<string> Base, int ExhaustedRuneCount,
    List<UnitInstanceView> Board,
    List<string>? BattlefieldChoices, List<string> Trash, List<string> Banishment,
    string? LegendCardId, string? ChampionCardId, int Score, Dictionary<string, int> Counters);

// The shared Battlefield Zone (Core Rule 486.5) - both players' chosen Battlefields and whoever's
// Units are sitting at each, addressed by OwnerConnectionId (see BattlefieldSlot).
public sealed record BattlefieldSlotView(string CardId, string OwnerConnectionId, List<UnitInstanceView> Units);

public sealed record BoardStateView(
    int TurnNumber, string? ActivePlayerConnectionId, Dictionary<string, PlayerZonesView> ZonesByPlayer, List<BattlefieldSlotView> Battlefields);

public sealed record PlayerView(string ConnectionId, string Name, bool IsHost, bool Ready, int? DeckId);

public sealed record LogEntryView(DateTimeOffset At, string Message);

public sealed record RoomView(string RoomCode, List<PlayerView> Players, BoardStateView Board, List<LogEntryView> Log);
