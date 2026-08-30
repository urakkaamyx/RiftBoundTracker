namespace RiftBoundTracker.App.Services.PlayOnline;

// The wire shape sent to clients - never MatchRoom/BoardState/PlayerZones directly, so hand
// redaction (see MatchRoomService.ToView) can never accidentally be bypassed by serializing the
// real model. Hand is null for every player except the viewer themselves; HandCount is always
// present so a viewer can see how many cards an opponent is holding without seeing what they are.
public sealed record PlayerZonesView(
    int HandCount, List<string>? Hand,
    int MainDeckCount, int RuneDeckCount, List<string> Base, int ExhaustedRuneCount,
    List<string> Board, List<string> Battlefield, List<string> Trash, List<string> Banishment,
    string? LegendCardId, string? ChampionCardId, int Score, Dictionary<string, int> Counters);

public sealed record BoardStateView(
    int TurnNumber, string? ActivePlayerConnectionId, Dictionary<string, PlayerZonesView> ZonesByPlayer);

public sealed record PlayerView(string ConnectionId, string Name, bool IsHost, bool Ready, int? DeckId);

public sealed record RoomView(string RoomCode, List<PlayerView> Players, BoardStateView Board);
