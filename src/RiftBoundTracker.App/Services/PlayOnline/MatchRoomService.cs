using RiftBoundTracker.App.Services;

namespace RiftBoundTracker.App.Services.PlayOnline;

/// <summary>
/// Owns every room this host instance is running, entirely in memory - see MatchRoom's own note
/// on why nothing here is persisted. A singleton (one instance per running app, not per request),
/// so MatchHub calls straight into it rather than each hub invocation getting its own state.
/// All room mutation and reads that need a consistent snapshot go through this one lock; for three
/// people's private games this is simplicity over throughput, which is the right trade here.
/// </summary>
public sealed class MatchRoomService(DeckLegalityService legality)
{
    private const string CodeAlphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"; // no 0/O/1/I/L - easy to read aloud
    private readonly Dictionary<string, MatchRoom> _rooms = [];
    private readonly Lock _lock = new();

    public MatchRoom CreateRoom(string hostConnectionId, string hostName)
    {
        lock (_lock)
        {
            string code;
            do { code = GenerateRoomCode(); } while (_rooms.ContainsKey(code));
            var room = new MatchRoom { RoomCode = code, HostConnectionId = hostConnectionId };
            room.Players.Add(new MatchPlayer { ConnectionId = hostConnectionId, Name = hostName, IsHost = true });
            _rooms[code] = room;
            AddLog(room, hostConnectionId, "opened the room.");
            return room;
        }
    }

    public MatchRoom? GetRoom(string code)
    {
        lock (_lock)
            return _rooms.GetValueOrDefault(code.Trim().ToUpperInvariant());
    }

    public (MatchRoom? Room, string? Error) TryJoin(string code, string connectionId, string name)
    {
        lock (_lock)
        {
            if (!_rooms.TryGetValue(code.Trim().ToUpperInvariant(), out var room))
                return (null, "Room not found.");
            if (room.Players.Count >= MatchRoom.MaxPlayers)
                return (null, "Room is full.");
            room.Players.Add(new MatchPlayer { ConnectionId = connectionId, Name = name, IsHost = false });
            AddLog(room, connectionId, "joined the room.");
            return (room, null);
        }
    }

    /// <summary>Host disconnecting ends the room outright - no reconnect/resume in Phase 1, per the
    /// plan's explicit scope cut. Returns the room's code if a room was actually removed, so the
    /// hub knows whether to notify anyone.</summary>
    public string? RemoveConnection(string connectionId)
    {
        lock (_lock)
        {
            foreach (var room in _rooms.Values)
            {
                if (room.HostConnectionId == connectionId)
                {
                    _rooms.Remove(room.RoomCode);
                    return room.RoomCode;
                }
                if (room.Players.RemoveAll(p => p.ConnectionId == connectionId) > 0)
                    return room.RoomCode;
            }
            return null;
        }
    }

    /// <summary>Takes an already-fetched deck rather than a deckId + fetching it here itself -
    /// DeckService is scoped (per-request), this service is a singleton, so the caller (MatchHub,
    /// which is safely per-invocation) resolves the deck and hands it in rather than this service
    /// holding a captive scoped dependency.</summary>
    public DeckLegalityResult SelectDeck(MatchRoom room, string connectionId, int deckId, DeckDetailDto deck)
    {
        var result = legality.Check(deck);
        if (result.Legal)
            lock (_lock)
            {
                var player = room.Players.FirstOrDefault(p => p.ConnectionId == connectionId);
                if (player is not null) player.DeckId = deckId;
                AddLog(room, connectionId, "selected a deck.");
            }
        return result;
    }

    public void SetReady(MatchRoom room, string connectionId, bool ready)
    {
        lock (_lock)
        {
            var player = room.Players.FirstOrDefault(p => p.ConnectionId == connectionId);
            if (player is not null) player.Ready = ready;
            AddLog(room, connectionId, ready ? "is ready." : "is no longer ready.");
        }
    }

    public void PassTurn(MatchRoom room, string connectionId)
    {
        lock (_lock)
        {
            if (room.Board.ActivePlayerConnectionId != connectionId) return; // only the active player can pass
            // Core Rule 143.3.b.1: damage heals off at the end of each player's own turn, wherever
            // their units are - their own Board, or any Battlefield they've got units sitting at.
            var endingZones = room.Board.GetOrAddZones(connectionId);
            foreach (var unit in endingZones.Board) unit.Damage = 0;
            foreach (var unit in ControlledBattlefieldUnits(room, connectionId)) unit.Damage = 0;
            var order = room.Players.Select(p => p.ConnectionId).ToList();
            var currentIndex = order.IndexOf(connectionId);
            room.Board.ActivePlayerConnectionId = order[(currentIndex + 1) % order.Count];
            if (currentIndex == order.Count - 1) room.Board.TurnNumber++;
            AddLog(room, connectionId, "passed the turn.");
            RunStartOfTurn(room, room.Board.ActivePlayerConnectionId!);
        }
    }

    public void UpdateCounter(MatchRoom room, string connectionId, string counterName, int delta)
    {
        lock (_lock)
        {
            var zones = room.Board.GetOrAddZones(connectionId);
            zones.Counters[counterName] = zones.Counters.GetValueOrDefault(counterName) + delta;
            AddLog(room, connectionId, $"{(delta >= 0 ? "gained" : "lost")} {Math.Abs(delta)} {counterName}.");
        }
    }

    /// <summary>
    /// Core Rule 194: how a player actually wins is Conquer/Hold at a Battlefield, which needs a
    /// Combat/control model this engine doesn't have yet - so Score here is player-adjusted by hand,
    /// same as any other counter, except it's a dedicated field (always visible, never removed by
    /// the free-form Add Counter UI) and clamped at 0 per Core Rule 194.4. Whether someone has hit
    /// the default Victory Score of 8 (Core Rule 194.3) is left for ToView's caller to notice and
    /// announce - this doesn't end the room, since ties/alternate Victory Scores aren't modeled.
    /// </summary>
    public void AdjustScore(MatchRoom room, string connectionId, int delta)
    {
        lock (_lock)
        {
            var zones = room.Board.GetOrAddZones(connectionId);
            zones.Score = Math.Max(0, zones.Score + delta);
            AddLog(room, connectionId, $"score is now {zones.Score}.");
        }
    }

    /// <summary>
    /// Deals the game in per Core Rules 111/114/116: separates each player's Legend, shuffles their
    /// Main and Rune Decks separately, and draws an opening hand of 4. Same captive-dependency shape
    /// as SelectDeck - the host (via MatchHub, which owns a scoped DeckService) resolves every
    /// ready player's deck and hands the lookup in rather than this singleton fetching it itself.
    /// Mulligans (Core Rule 117) aren't automated - players judge their own opening hand manually.
    /// </summary>
    public (bool Ok, string? Error) StartMatch(MatchRoom room, string connectionId, IReadOnlyDictionary<string, DeckDetailDto> decksByConnection)
    {
        lock (_lock)
        {
            if (room.HostConnectionId != connectionId) return (false, "Only the host can start the match.");
            if (room.Players.Count < 2) return (false, "Need at least 2 players.");
            if (room.Players.Any(p => !p.Ready || p.DeckId is null)) return (false, "Every player needs a legal deck and must be ready.");

            foreach (var player in room.Players)
            {
                if (!decksByConnection.TryGetValue(player.ConnectionId, out var deck)) continue;
                var zones = room.Board.GetOrAddZones(player.ConnectionId);
                zones.LegendCardId = deck.Cards.FirstOrDefault(c => c.Card.Type == "Legend")?.CardId;
                // Core Rule 486.4.a/486.5: each player is dealt their 3 Battlefields at Setup and
                // picks one via SelectBattlefield below - BattlefieldCards stays empty until then.
                zones.BattlefieldChoices.AddRange(Expand(deck.Cards.Where(c => c.Card.Type == "Battlefield")));

                var main = Expand(deck.Cards.Where(c => c.Section == "main" && c.Card.Type is not ("Legend" or "Rune" or "Battlefield")));
                var runes = Expand(deck.Cards.Where(c => c.Card.Type == "Rune"));
                Shuffle(main);
                Shuffle(runes);
                zones.MainDeck.AddRange(main);
                zones.RuneDeck.AddRange(runes);
                for (var i = 0; i < 4 && zones.MainDeck.Count > 0; i++) DrawTopCard(zones);
            }

            room.Board.TurnNumber = 1;
            room.Board.ActivePlayerConnectionId = room.HostConnectionId;
            AddLog(room, connectionId, "started the match.");
            RunStartOfTurn(room, room.HostConnectionId);
            return (true, null);
        }
    }

    /// <summary>
    /// Core Rule 486.5's Setup choice: picks one of the 3 dealt Battlefield candidates as the one
    /// actually used this game, discarding the other two (they're simply never added anywhere -
    /// 486.5 says they're "set aside", and this engine has no multi-game Match/Bo3 structure yet for
    /// them to be re-offered in a later game of the same match, so there's nowhere for them to go).
    /// The chosen card goes into the SHARED Battlefield Zone (BoardState.Battlefields), not anything
    /// per-player - "The selected Battlefields are placed simultaneously in the Battlefield Zone"
    /// (singular), and either player's units can be At either Battlefield once play starts.
    /// Can only be called once per game - BattlefieldChoices is empty afterward, so a second call
    /// finds nothing to pick from and fails, matching "cannot change your selected battlefield during
    /// a game."
    /// </summary>
    public bool SelectBattlefield(MatchRoom room, string connectionId, string cardId)
    {
        lock (_lock)
        {
            var zones = room.Board.GetOrAddZones(connectionId);
            if (!zones.BattlefieldChoices.Remove(cardId)) return false;
            zones.BattlefieldChoices.Clear();
            room.Board.Battlefields.Add(new BattlefieldSlot { CardId = cardId, OwnerConnectionId = connectionId });
            AddLog(room, connectionId, "chose their Battlefield.");
            return true;
        }
    }

    /// <summary>
    /// Represents a Token (Core Rule 108.2.c: Created Game Objects, not part of either deck) being
    /// put directly into play - the manual stand-in for whatever effect would have created it, since
    /// this engine has no card-effect execution. Either player can put a Token at either Battlefield
    /// (same any-unit-targetable trust model as Damage/Heal/Combat) - it's controlled by whoever
    /// created it regardless of whose Battlefield it landed on, same as any other unit there.
    /// </summary>
    public (bool Ok, string? Error) CreateToken(MatchRoom room, string connectionId, string cardId, string battlefieldOwnerConnectionId)
    {
        lock (_lock)
        {
            var slot = room.Board.Battlefields.FirstOrDefault(b => b.OwnerConnectionId == battlefieldOwnerConnectionId);
            if (slot is null) return (false, "That Battlefield isn't in play.");
            slot.Units.Add(new UnitInstance { InstanceId = Guid.NewGuid().ToString("N"), CardId = cardId, ControllerConnectionId = connectionId });
            AddLog(room, connectionId, "created a token at a Battlefield.");
            return (true, null);
        }
    }

    /// <summary>Every unit `connectionId` currently controls at any shared Battlefield - used
    /// wherever "ready/heal all my stuff" needs to reach past the caller's own Board.</summary>
    private static IEnumerable<UnitInstance> ControlledBattlefieldUnits(MatchRoom room, string connectionId) =>
        room.Board.Battlefields.SelectMany(b => b.Units).Where(u => u.ControllerConnectionId == connectionId);

    /// <summary>
    /// Core Rules 315.1/315.3/315.4 for the player whose turn is beginning: their runes AND every
    /// unit they control readies (Core Rule 415, "The Turn Player readies all Game Objects they
    /// control that are able to be readied"), they channel up to 2 runes, and they draw 1. Also
    /// empties their Rune Pool per Core Rule 167 - this engine has no separate Main Phase step, so
    /// it happens right here instead.
    /// </summary>
    private void RunStartOfTurn(MatchRoom room, string connectionId)
    {
        var zones = room.Board.GetOrAddZones(connectionId);
        zones.ExhaustedRuneCount = 0;
        foreach (var unit in zones.Board) unit.Exhausted = false;
        foreach (var unit in ControlledBattlefieldUnits(room, connectionId)) unit.Exhausted = false;
        zones.Counters.Remove("Energy");
        zones.Counters.Remove("Power");
        var channeled = 0;
        for (var i = 0; i < 2 && zones.RuneDeck.Count > 0; i++)
        {
            var top = zones.RuneDeck[^1];
            zones.RuneDeck.RemoveAt(zones.RuneDeck.Count - 1);
            zones.Base.Add(top);
            channeled++;
        }
        var drew = zones.MainDeck.Count > 0;
        if (drew) DrawTopCard(zones);
        AddLog(room, connectionId, $"started their turn - channeled {channeled} rune{(channeled == 1 ? "" : "s")}{(drew ? " and drew a card." : ".")}");
    }

    /// <summary>Player-invoked extra Draw/Channel on top of the automatic Start of Turn - for
    /// effects that grant an additional draw/channel, which aren't automated yet (Phase 1 has no
    /// card-specific ability execution), so the player applies them manually.</summary>
    public void DrawCard(MatchRoom room, string connectionId)
    {
        lock (_lock)
        {
            var zones = room.Board.GetOrAddZones(connectionId);
            if (zones.MainDeck.Count == 0) return;
            DrawTopCard(zones);
            AddLog(room, connectionId, "drew a card.");
        }
    }

    public void ChannelRune(MatchRoom room, string connectionId)
    {
        lock (_lock)
        {
            var zones = room.Board.GetOrAddZones(connectionId);
            if (zones.RuneDeck.Count == 0) return;
            var top = zones.RuneDeck[^1];
            zones.RuneDeck.RemoveAt(zones.RuneDeck.Count - 1);
            zones.Base.Add(top);
            AddLog(room, connectionId, "channeled a rune.");
        }
    }

    /// <summary>Core Rule 164.2.a, a Basic Rune's "[E]: Add [1]" ability - exhausts one of this
    /// player's ready Base runes (tracked as a count, not per-card, since they're fungible for this)
    /// to add 1 Energy to their Rune Pool (Counters["Energy"]).</summary>
    public void ExhaustRuneForEnergy(MatchRoom room, string connectionId)
    {
        lock (_lock)
        {
            var zones = room.Board.GetOrAddZones(connectionId);
            if (zones.ExhaustedRuneCount >= zones.Base.Count) return;
            zones.ExhaustedRuneCount++;
            zones.Counters["Energy"] = zones.Counters.GetValueOrDefault("Energy") + 1;
            AddLog(room, connectionId, "exhausted a rune for +1 Energy.");
        }
    }

    /// <summary>Core Rule 164.2.b, a Basic Rune's "Recycle this: Add [Domain]" ability - returns one
    /// specific Base rune to its owner's Rune Deck and adds 1 Power to their Rune Pool. Power isn't
    /// tracked per-Domain (Core Rule 163.2.a) since nothing yet spends it against a Domain cost.</summary>
    public bool RecycleRuneForPower(MatchRoom room, string connectionId, string cardId)
    {
        lock (_lock)
        {
            var zones = room.Board.GetOrAddZones(connectionId);
            if (!zones.Base.Remove(cardId)) return false;
            if (zones.ExhaustedRuneCount > zones.Base.Count) zones.ExhaustedRuneCount = zones.Base.Count;
            zones.RuneDeck.Add(cardId);
            zones.Counters["Power"] = zones.Counters.GetValueOrDefault("Power") + 1;
            AddLog(room, connectionId, "recycled a rune for +1 Power.");
            return true;
        }
    }

    /// <summary>
    /// Core Rule 349, Playing a Card - pays the card's printed Energy cost out of the caller's Rune
    /// Pool, then moves it from Hand to wherever it actually ends up: a Spell finishes executing and
    /// goes straight to the Trash (Core Rule 108.2.b), everything else (Unit, Gear, ...) is a
    /// Permanent and stays on the Board. Takes the cost/type/name as parameters rather than looking
    /// the card up itself - same captive-dependency shape as SelectDeck/StartMatch, MatchHub (with
    /// its own scoped AppDbContext) resolves the card and hands them in.
    /// </summary>
    public (bool Ok, string? Error) PlayCard(MatchRoom room, string connectionId, string cardId, int energyCost, string? cardType, string? cardName)
    {
        lock (_lock)
        {
            var zones = room.Board.GetOrAddZones(connectionId);
            if (!zones.Hand.Contains(cardId)) return (false, "That card isn't in your hand.");
            var available = zones.Counters.GetValueOrDefault("Energy");
            if (available < energyCost) return (false, $"Not enough Energy - have {available}, need {energyCost}.");
            zones.Hand.Remove(cardId);
            zones.Counters["Energy"] = available - energyCost;
            if (cardType == "Spell") zones.Trash.Add(cardId);
            else zones.Board.Add(new UnitInstance { InstanceId = Guid.NewGuid().ToString("N"), CardId = cardId, ControllerConnectionId = connectionId });
            AddLog(room, connectionId, $"played {cardName ?? "a card"}.");
            return (true, null);
        }
    }

    private static readonly Dictionary<string, Func<PlayerZones, List<string>>> MovableZones = new()
    {
        ["hand"] = z => z.Hand, ["trash"] = z => z.Trash, ["banishment"] = z => z.Banishment,
    };

    /// <summary>
    /// The one generic, manual zone-to-zone move Phase 1 offers in place of automating every
    /// specific action (Discard, Banish, Return...) - the plan's explicit "no card-specific
    /// automation yet" scope. MainDeck/RuneDeck are deliberately not reachable here; they only move
    /// via DrawCard/ChannelRune so a face-down zone's order can't be picked through by hand. Hand to
    /// Board is excluded too - that's Playing a Card (PlayCard above), which has a cost to pay, not
    /// a free move. Board itself is reachable (wraps the plain card id into a fresh ready instance,
    /// or unwraps one back down to a plain id when leaving it - the instance's own identity and
    /// Exhausted state don't survive leaving the board). A Battlefield is NOT reachable through this
    /// generic tool at all - since there can be more than one in play, "move to battlefield" needs
    /// to say WHICH one, which a same-shaped-for-every-zone tool like this can't express; that's
    /// StandardMove below (Board Battlefield) instead.
    /// </summary>
    public bool MoveCard(MatchRoom room, string connectionId, string cardId, string fromZone, string toZone)
    {
        lock (_lock)
        {
            if (fromZone == "hand" && toZone == "board") return false; // Playing a Card (PlayCard), not a free move
            var zones = room.Board.GetOrAddZones(connectionId);

            string movedCardId;
            if (fromZone == "board")
            {
                var unit = zones.Board.FirstOrDefault(u => u.CardId == cardId);
                if (unit is null) return false;
                zones.Board.Remove(unit);
                movedCardId = unit.CardId;
                DetachAllPointingTo(room, unit.InstanceId); // Core Rule 719.5
            }
            else if (MovableZones.TryGetValue(fromZone, out var from))
            {
                if (!from(zones).Remove(cardId)) return false;
                movedCardId = cardId;
            }
            else return false;

            if (toZone == "board")
                zones.Board.Add(new UnitInstance { InstanceId = Guid.NewGuid().ToString("N"), CardId = movedCardId, ControllerConnectionId = connectionId });
            else if (MovableZones.TryGetValue(toZone, out var to))
                to(zones).Add(movedCardId);
            else return false;

            AddLog(room, connectionId, $"moved a card from {fromZone} to {toZone}.");
            return true;
        }
    }

    /// <summary>
    /// Core Rule 144, the Standard Move - a Unit's own Inherent Ability to move between its
    /// controller's Base (Board) and a Battlefield (144.4.a/b), costing Exhausting itself (144.2).
    /// Unlike the free generic MoveCard, this enforces the actual cost and precondition: only a
    /// Ready unit can pay it, and it arrives at the destination already Exhausted, matching how
    /// paying a Cost works everywhere else in this engine (compare PlayCard's Energy cost).
    /// `battlefieldOwnerConnectionId` picks WHICH Battlefield (Core Rule 486.4: up to 2 in a 1v1) -
    /// required when moving there, ignored (there's only ever one destination - your own Board)
    /// when moving back.
    /// </summary>
    public bool StandardMove(MatchRoom room, string connectionId, string instanceId, string toZone, string? battlefieldOwnerConnectionId)
    {
        lock (_lock)
        {
            var zones = room.Board.GetOrAddZones(connectionId);
            if (toZone == "battlefield")
            {
                var slot = room.Board.Battlefields.FirstOrDefault(b => b.OwnerConnectionId == battlefieldOwnerConnectionId);
                var unit = zones.Board.FirstOrDefault(u => u.InstanceId == instanceId);
                if (slot is null || unit is null || unit.Exhausted) return false;
                zones.Board.Remove(unit);
                unit.Exhausted = true;
                slot.Units.Add(unit);
                AddLog(room, connectionId, "moved a unit to a Battlefield (exhausting it).");
                return true;
            }
            if (toZone == "board")
            {
                var slot = room.Board.Battlefields.FirstOrDefault(b => b.Units.Any(u => u.InstanceId == instanceId && u.ControllerConnectionId == connectionId));
                var unit = slot?.Units.FirstOrDefault(u => u.InstanceId == instanceId);
                if (unit is null || unit.Exhausted) return false;
                slot!.Units.Remove(unit);
                unit.Exhausted = true;
                zones.Board.Add(unit);
                AddLog(room, connectionId, "moved a unit to their Base (exhausting it).");
                return true;
            }
            return false;
        }
    }

    /// <summary>Core Rule 415/416's Ready/Exhausted state, toggled by hand for now - no keyword or
    /// combat automation triggers this yet, but many Keywords (Accelerate, Equip, Weaponmaster,
    /// Tank interactions...) check or change it, so it has to exist before any of those can.</summary>
    public bool ToggleUnitReady(MatchRoom room, string connectionId, string instanceId)
    {
        lock (_lock)
        {
            var zones = room.Board.GetOrAddZones(connectionId);
            var unit = zones.Board.FirstOrDefault(u => u.InstanceId == instanceId)
                ?? ControlledBattlefieldUnits(room, connectionId).FirstOrDefault(u => u.InstanceId == instanceId);
            if (unit is null) return false;
            unit.Exhausted = !unit.Exhausted;
            return true;
        }
    }

    /// <summary>Card id of any unit anywhere in play - your own Board, anyone's, or any shared
    /// Battlefield - used by the caller (MatchHub) to resolve the target's Might before calling
    /// DealDamage, since this service has no card-database access of its own.</summary>
    public string? FindUnitCardId(MatchRoom room, string instanceId)
    {
        lock (_lock)
        {
            foreach (var zones in room.Board.ZonesByPlayer.Values)
            {
                var unit = zones.Board.FirstOrDefault(u => u.InstanceId == instanceId);
                if (unit is not null) return unit.CardId;
            }
            foreach (var slot in room.Board.Battlefields)
            {
                var unit = slot.Units.FirstOrDefault(u => u.InstanceId == instanceId);
                if (unit is not null) return unit.CardId;
            }
            return null;
        }
    }

    /// <summary>
    /// Core Rule 142/465.2.d: Damage is marked on a unit (not a Might reduction), and Lethal Damage
    /// (marked Damage >= Might) Kills it (428.1.a.2, moved straight to its controller's Trash). No
    /// Combat/targeting automation exists yet, so this is a manual "assign N damage to any unit"
    /// tool standing in for real Combat Damage assignment and Kill instructions alike - the two most
    /// common ways damage actually gets applied on a real board. Any player can target any unit,
    /// same trust model as the rest of Phase 1's manual tools.
    /// </summary>
    public bool DealDamage(MatchRoom room, string connectionId, string instanceId, int amount, int? might)
    {
        lock (_lock)
            return MarkDamageAndMaybeKill(room, connectionId, instanceId, amount, might);
    }

    /// <summary>
    /// Core Rule 465.2: a simplified stand-in for the Combat Damage Step, scoped to exactly one
    /// attacker and one defender - the common case, and the one that avoids the multi-unit damage
    /// ordering rules (465.2.c.3-c.10) that the real rules explicitly leave to player choice anyway
    /// (no UI could automate that choice without asking the player, so this doesn't pretend to).
    /// Both sides' Might is summed and dealt to the other, computed before either is applied, so a
    /// mutual kill happens correctly (465.2.c.1.a: assigning damage isn't the same as dealing it -
    /// both are assigned, then both are dealt simultaneously).
    /// </summary>
    public bool ResolveCombat(MatchRoom room, string connectionId, string attackerInstanceId, int? attackerMight, string defenderInstanceId, int? defenderMight)
    {
        lock (_lock)
        {
            if (attackerInstanceId == defenderInstanceId) return false;
            var attackerDamage = defenderMight ?? 0;
            var defenderDamage = attackerMight ?? 0;
            var attackerFound = MarkDamageAndMaybeKill(room, connectionId, attackerInstanceId, attackerDamage, attackerMight);
            var defenderFound = MarkDamageAndMaybeKill(room, connectionId, defenderInstanceId, defenderDamage, defenderMight);
            if (attackerFound || defenderFound) AddLog(room, connectionId, "resolved combat between two units.");
            return attackerFound && defenderFound;
        }
    }

    private bool MarkDamageAndMaybeKill(MatchRoom room, string connectionId, string instanceId, int amount, int? might)
    {
        UnitInstance? unit = null;
        List<UnitInstance>? containingList = null;
        foreach (var zones in room.Board.ZonesByPlayer.Values)
        {
            unit = zones.Board.FirstOrDefault(u => u.InstanceId == instanceId);
            if (unit is not null) { containingList = zones.Board; break; }
        }
        if (unit is null)
            foreach (var slot in room.Board.Battlefields)
            {
                unit = slot.Units.FirstOrDefault(u => u.InstanceId == instanceId);
                if (unit is not null) { containingList = slot.Units; break; }
            }
        if (unit is null) return false;

        unit.Damage += amount;
        AddLog(room, connectionId, $"dealt {amount} damage to a unit ({unit.Damage} marked).");
        if (might is int m && unit.Damage >= m)
        {
            containingList!.Remove(unit);
            // Core Rule 428.1.a.2: a Killed unit goes to its CONTROLLER's Trash - not whoever dealt
            // the damage, and not tied to which list it was removed from once that list is shared.
            room.Board.GetOrAddZones(unit.ControllerConnectionId).Trash.Add(unit.CardId);
            DetachAllPointingTo(room, unit.InstanceId);
            AddLog(room, connectionId, "killed that unit with lethal damage.");
        }
        return true;
    }

    /// <summary>Core Rule 418, Heal - clears marked Damage from a unit (never below 0). Same manual,
    /// any-unit-targetable trust model as DealDamage.</summary>
    public bool HealUnit(MatchRoom room, string connectionId, string instanceId, int amount)
    {
        lock (_lock)
        {
            var unit = AnyUnit(room, instanceId);
            if (unit is null) return false;
            unit.Damage = Math.Max(0, unit.Damage - amount);
            AddLog(room, connectionId, $"healed {amount} damage from a unit ({unit.Damage} marked).");
            return true;
        }
    }

    /// <summary>Any unit anywhere in play, regardless of who controls it or which Battlefield (if
    /// any) it's at - the shared lookup behind Heal/Attach's "any unit" targeting.</summary>
    private static UnitInstance? AnyUnit(MatchRoom room, string instanceId) =>
        room.Board.ZonesByPlayer.Values.Select(z => z.Board.FirstOrDefault(u => u.InstanceId == instanceId)).FirstOrDefault(u => u is not null)
        ?? room.Board.Battlefields.Select(b => b.Units.FirstOrDefault(u => u.InstanceId == instanceId)).FirstOrDefault(u => u is not null);

    /// <summary>Core Rule 719.5: when a Top-Most Card leaves the board, everything Attached to it
    /// Detaches and stays where it is - always called right after removing a unit from Board or a
    /// Battlefield, from within the same lock. Attached cards can have a different Controller than
    /// their Top-Most card (718.5.e), so this has to search every player's Board AND every shared
    /// Battlefield, not just the Top-Most card's own controller.</summary>
    private static void DetachAllPointingTo(MatchRoom room, string topMostInstanceId)
    {
        foreach (var zones in room.Board.ZonesByPlayer.Values)
            foreach (var unit in zones.Board.Where(u => u.AttachedToInstanceId == topMostInstanceId)) unit.AttachedToInstanceId = null;
        foreach (var slot in room.Board.Battlefields)
            foreach (var unit in slot.Units.Where(u => u.AttachedToInstanceId == topMostInstanceId)) unit.AttachedToInstanceId = null;
    }

    /// <summary>Core Rules 717-719, Attaching - links a Gear (or any card) to a Top-Most Card
    /// anywhere in play. No Might Bonus math or ability-text appending happens here (that needs the
    /// card-effect execution this engine doesn't have) - this only tracks the structural
    /// relationship, which is itself real, checkable game state (718.5.b, 719.3). The attaching card
    /// must be yours (your Board or a Battlefield unit you control); the target can be anyone's.</summary>
    public bool AttachCard(MatchRoom room, string connectionId, string cardInstanceId, string targetInstanceId)
    {
        lock (_lock)
        {
            if (cardInstanceId == targetInstanceId) return false;
            var zones = room.Board.GetOrAddZones(connectionId);
            var card = zones.Board.FirstOrDefault(u => u.InstanceId == cardInstanceId)
                ?? ControlledBattlefieldUnits(room, connectionId).FirstOrDefault(u => u.InstanceId == cardInstanceId);
            if (card is null) return false;
            if (AnyUnit(room, targetInstanceId) is null) return false;
            card.AttachedToInstanceId = targetInstanceId;
            AddLog(room, connectionId, "attached a card to another.");
            return true;
        }
    }

    public bool DetachCard(MatchRoom room, string connectionId, string instanceId)
    {
        lock (_lock)
        {
            var zones = room.Board.GetOrAddZones(connectionId);
            var unit = zones.Board.FirstOrDefault(u => u.InstanceId == instanceId)
                ?? ControlledBattlefieldUnits(room, connectionId).FirstOrDefault(u => u.InstanceId == instanceId);
            if (unit?.AttachedToInstanceId is null) return false;
            unit.AttachedToInstanceId = null;
            AddLog(room, connectionId, "detached a card.");
            return true;
        }
    }

    private static List<string> Expand(IEnumerable<DeckCardDto> rows) =>
        rows.SelectMany(r => Enumerable.Repeat(r.CardId, r.Quantity)).ToList();

    private static void Shuffle(List<string> cards)
    {
        for (var i = cards.Count - 1; i > 0; i--)
        {
            var j = Random.Shared.Next(i + 1);
            (cards[i], cards[j]) = (cards[j], cards[i]);
        }
    }

    private static void DrawTopCard(PlayerZones zones)
    {
        var top = zones.MainDeck[^1];
        zones.MainDeck.RemoveAt(zones.MainDeck.Count - 1);
        zones.Hand.Add(top);
    }

    /// <summary>The redaction boundary: only `viewerConnectionId`'s own Hand is ever populated in
    /// the returned view. Every other player's Hand comes back null - only HandCount is visible.
    /// This is what actually enforces hidden information, not anything client-side.</summary>
    public RoomView ToView(MatchRoom room, string viewerConnectionId)
    {
        lock (_lock)
        {
            var zonesView = room.Board.ZonesByPlayer.ToDictionary(
                kv => kv.Key,
                kv => new PlayerZonesView(
                    HandCount: kv.Value.Hand.Count,
                    Hand: kv.Key == viewerConnectionId ? [..kv.Value.Hand] : null,
                    MainDeckCount: kv.Value.MainDeck.Count,
                    RuneDeckCount: kv.Value.RuneDeck.Count,
                    Base: [..kv.Value.Base],
                    ExhaustedRuneCount: kv.Value.ExhaustedRuneCount,
                    Board: kv.Value.Board.Select(ToUnitView).ToList(),
                    BattlefieldChoices: kv.Key == viewerConnectionId ? [..kv.Value.BattlefieldChoices] : null,
                    Trash: [..kv.Value.Trash],
                    Banishment: [..kv.Value.Banishment],
                    LegendCardId: kv.Value.LegendCardId,
                    ChampionCardId: kv.Value.ChampionCardId,
                    Score: kv.Value.Score,
                    Counters: new Dictionary<string, int>(kv.Value.Counters)));
            var battlefieldsView = room.Board.Battlefields
                .Select(b => new BattlefieldSlotView(b.CardId, b.OwnerConnectionId, b.Units.Select(ToUnitView).ToList()))
                .ToList();
            return new RoomView(
                room.RoomCode,
                room.Players.Select(p => new PlayerView(p.ConnectionId, p.Name, p.IsHost, p.Ready, p.DeckId)).ToList(),
                new BoardStateView(room.Board.TurnNumber, room.Board.ActivePlayerConnectionId, zonesView, battlefieldsView),
                room.Log.Select(l => new LogEntryView(l.At, l.Message)).ToList());
        }
    }

    private static UnitInstanceView ToUnitView(UnitInstance u) =>
        new(u.InstanceId, u.CardId, u.ControllerConnectionId, u.Exhausted, u.Damage, u.AttachedToInstanceId);

    private static string GenerateRoomCode() =>
        new(Enumerable.Range(0, 5).Select(_ => CodeAlphabet[Random.Shared.Next(CodeAlphabet.Length)]).ToArray());

    /// <summary>Always called from within an already-held _lock block - never locks itself.</summary>
    private static void AddLog(MatchRoom room, string connectionId, string action)
    {
        var name = room.Players.FirstOrDefault(p => p.ConnectionId == connectionId)?.Name ?? "Someone";
        room.Log.Add(new LogEntry(DateTimeOffset.UtcNow, $"{name} {action}"));
        if (room.Log.Count > MatchRoom.MaxLogEntries) room.Log.RemoveAt(0);
    }
}
