using Microsoft.AspNetCore.SignalR;
using RiftBoundTracker.App.Data;

namespace RiftBoundTracker.App.Services.PlayOnline;

public sealed record HubResult(bool Ok, string? Error, object? View = null, List<DeckLegalityViolation>? Violations = null);

/// <summary>
/// The real-time transport for the Emulator. Emulator access is verified here, server-side, on
/// every HostRoom/JoinRoom call - never trust the client's nav-item visibility alone, since once a
/// room is hosted this server is reachable from the public internet via the existing ngrok WAN flow
/// (see NgrokService). A rejection here never hands out any room state.
/// </summary>
public sealed class MatchHub(MatchRoomService rooms, EmulatorAccessService access, DeckService decks, AppDbContext db) : Hub
{
    public async Task<HubResult> PlayCard(string roomCode, string cardId)
    {
        var room = rooms.GetRoom(roomCode);
        if (room is null) return new HubResult(false, "Room not found.");
        var card = await db.Cards.FindAsync(cardId);
        var (ok, error) = rooms.PlayCard(room, Context.ConnectionId, cardId, card?.Energy ?? 0, card?.Type);
        if (!ok) return new HubResult(false, error);
        await BroadcastAsync(room);
        return new HubResult(true, null);
    }

    public async Task<HubResult> HostRoom(string hostName)
    {
        if (!await access.HasAccessTodayAsync()) return new HubResult(false, "Enter today's RiftCode first.");
        var room = rooms.CreateRoom(Context.ConnectionId, hostName);
        await Groups.AddToGroupAsync(Context.ConnectionId, room.RoomCode);
        return new HubResult(true, null, rooms.ToView(room, Context.ConnectionId));
    }

    public async Task<HubResult> JoinRoom(string roomCode, string playerName)
    {
        if (!await access.HasAccessTodayAsync()) return new HubResult(false, "Enter today's RiftCode first.");
        var (room, error) = rooms.TryJoin(roomCode, Context.ConnectionId, playerName);
        if (room is null) return new HubResult(false, error);
        await Groups.AddToGroupAsync(Context.ConnectionId, room.RoomCode);
        await BroadcastAsync(room);
        return new HubResult(true, null, rooms.ToView(room, Context.ConnectionId));
    }

    public async Task<HubResult> SelectDeck(string roomCode, int deckId)
    {
        var room = rooms.GetRoom(roomCode);
        if (room is null) return new HubResult(false, "Room not found.");
        var deck = await decks.GetAsync(deckId);
        if (deck is null) return new HubResult(false, "Deck not found.");
        var result = rooms.SelectDeck(room, Context.ConnectionId, deckId, deck);
        if (result.Legal) await BroadcastAsync(room);
        return new HubResult(result.Legal, null, Violations: result.Violations);
    }

    public async Task<HubResult> StartMatch(string roomCode)
    {
        var room = rooms.GetRoom(roomCode);
        if (room is null) return new HubResult(false, "Room not found.");
        var decksByConnection = new Dictionary<string, DeckDetailDto>();
        foreach (var player in room.Players)
        {
            if (player.DeckId is not int deckId) continue;
            var deck = await decks.GetAsync(deckId);
            if (deck is not null) decksByConnection[player.ConnectionId] = deck;
        }
        var (ok, error) = rooms.StartMatch(room, Context.ConnectionId, decksByConnection);
        if (!ok) return new HubResult(false, error);
        await BroadcastAsync(room);
        return new HubResult(true, null);
    }

    public async Task DrawCard(string roomCode)
    {
        var room = rooms.GetRoom(roomCode);
        if (room is null) return;
        rooms.DrawCard(room, Context.ConnectionId);
        await BroadcastAsync(room);
    }

    public async Task ChannelRune(string roomCode)
    {
        var room = rooms.GetRoom(roomCode);
        if (room is null) return;
        rooms.ChannelRune(room, Context.ConnectionId);
        await BroadcastAsync(room);
    }

    public async Task ExhaustRune(string roomCode)
    {
        var room = rooms.GetRoom(roomCode);
        if (room is null) return;
        rooms.ExhaustRuneForEnergy(room, Context.ConnectionId);
        await BroadcastAsync(room);
    }

    public async Task<HubResult> RecycleRune(string roomCode, string cardId)
    {
        var room = rooms.GetRoom(roomCode);
        if (room is null) return new HubResult(false, "Room not found.");
        if (!rooms.RecycleRuneForPower(room, Context.ConnectionId, cardId)) return new HubResult(false, "Could not recycle that rune.");
        await BroadcastAsync(room);
        return new HubResult(true, null);
    }

    public async Task<HubResult> MoveCard(string roomCode, string cardId, string fromZone, string toZone)
    {
        var room = rooms.GetRoom(roomCode);
        if (room is null) return new HubResult(false, "Room not found.");
        if (!rooms.MoveCard(room, Context.ConnectionId, cardId, fromZone, toZone))
            return new HubResult(false, fromZone == "hand" && toZone == "board"
                ? "That's Playing a Card - use the Play button on the card instead, so its cost gets paid."
                : "Could not move that card.");
        await BroadcastAsync(room);
        return new HubResult(true, null);
    }

    public async Task ReadyUp(string roomCode, bool ready)
    {
        var room = rooms.GetRoom(roomCode);
        if (room is null) return;
        rooms.SetReady(room, Context.ConnectionId, ready);
        await BroadcastAsync(room);
    }

    public async Task PassTurn(string roomCode)
    {
        var room = rooms.GetRoom(roomCode);
        if (room is null) return;
        rooms.PassTurn(room, Context.ConnectionId);
        await BroadcastAsync(room);
    }

    public async Task UpdateCounter(string roomCode, string counterName, int delta)
    {
        var room = rooms.GetRoom(roomCode);
        if (room is null) return;
        rooms.UpdateCounter(room, Context.ConnectionId, counterName, delta);
        await BroadcastAsync(room);
    }

    public async Task AdjustScore(string roomCode, int delta)
    {
        var room = rooms.GetRoom(roomCode);
        if (room is null) return;
        rooms.AdjustScore(room, Context.ConnectionId, delta);
        await BroadcastAsync(room);
    }

    public override async Task OnDisconnectedAsync(Exception? exception)
    {
        var closedRoomCode = rooms.RemoveConnection(Context.ConnectionId);
        if (closedRoomCode is not null)
            await Clients.Group(closedRoomCode).SendAsync("RoomClosed");
        await base.OnDisconnectedAsync(exception);
    }

    /// <summary>
    /// Sends every connected player THEIR OWN redacted view individually - Clients.Group would
    /// send one identical payload to the whole room, which would leak every player's hand
    /// contents to everyone else. Hidden information has to be enforced per-recipient.
    /// </summary>
    private async Task BroadcastAsync(MatchRoom room)
    {
        foreach (var player in room.Players.ToList())
            await Clients.Client(player.ConnectionId).SendAsync("BoardStateUpdated", rooms.ToView(room, player.ConnectionId));
    }
}
