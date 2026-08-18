using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using RiftBoundTracker.App.Data;

namespace RiftBoundTracker.App.Services;

public record CommunitySyncResult(bool Ok, int TournamentCount, int DeckCount, int UnresolvedCardCount, string? Error);
public record CommunitySyncStatusDto(
    bool Configured, DateTimeOffset? LastSyncAt, bool LastSyncOk,
    int TournamentCount, int DeckCount, int UnresolvedCardCount, string? LastError);

/// <summary>
/// Pulls recent tournament decklists from TopDeck.gg and mirrors them into the local
/// Community* tables so CommunityRecommendationService can compute usage percentages entirely
/// from local data (no live TopDeck call on the recommendation read path). Manual-trigger only
/// for v1 — never runs on a normal page load, respecting TopDeck's tight rate limit.
/// </summary>
public sealed class CommunityDeckSyncService(
    AppDbContext db, TopDeckClient client, CommunityCardResolver resolver, ILogger<CommunityDeckSyncService> logger)
{
    // JsonElement.Deserialize<T>() defaults to case-SENSITIVE matching (unlike
    // HttpContent.ReadFromJsonAsync, which uses web/case-insensitive defaults) — TopDeck's
    // section entries use lowercase "id"/"count" against this app's PascalCase TopDeckCardRef,
    // so this must be passed explicitly or every card silently fails to bind and gets skipped.
    private static readonly JsonSerializerOptions CardRefOptions = new() { PropertyNameCaseInsensitive = true };

    // TopDeck's deckObj sections that map to this app's binary main/sideboard model. Any section
    // key not listed here (chiefly the non-card "metadata" section — {game, format, importedFrom}
    // — confirmed present alongside the real sections during planning) is skipped entirely rather
    // than guessed at.
    private static readonly Dictionary<string, string> SectionMap = new(StringComparer.OrdinalIgnoreCase)
    {
        ["Legend"] = "main",
        ["Champion"] = "main",
        ["Runes"] = "main",
        ["Battlefields"] = "main",
        ["Mainboard"] = "main",
        ["Sideboard"] = "sideboard",
    };

    public async Task<CommunitySyncStatusDto> GetStatusAsync(CancellationToken ct = default)
    {
        var state = await db.CommunitySyncState.FirstOrDefaultAsync(ct);
        return new CommunitySyncStatusDto(
            client.IsConfigured, state?.LastSyncAt, state?.LastSyncOk ?? false,
            state?.TournamentCount ?? 0, state?.DeckCount ?? 0, state?.UnresolvedCardCount ?? 0, state?.LastError);
    }

    public async Task<CommunitySyncResult> SyncAsync(int days = 30, CancellationToken ct = default)
    {
        if (!client.IsConfigured)
            return await FailAsync("TopDeck.gg is not configured. Add an API key in Settings.", ct);

        List<TopDeckTournament> tournaments;
        try
        {
            tournaments = await client.GetTournamentsAsync(DateTimeOffset.UtcNow.AddDays(-days), ct: ct);
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "TopDeck.gg sync failed while fetching tournaments");
            return await FailAsync(ex.Message, ct);
        }

        var deckCount = 0;
        var unresolvedCount = 0;

        foreach (var t in tournaments)
        {
            if (string.IsNullOrWhiteSpace(t.Tid)) continue;

            var tournament = await db.CommunityTournaments
                .FirstOrDefaultAsync(x => x.ExternalTournamentId == t.Tid, ct);
            if (tournament is null)
            {
                tournament = new CommunityTournamentEntity { ExternalTournamentId = t.Tid, ImportedAt = DateTimeOffset.UtcNow };
                db.CommunityTournaments.Add(tournament);
            }
            tournament.Name = t.TournamentName;
            tournament.Format = t.Format;
            tournament.StartDate = DateTimeOffset.FromUnixTimeSeconds(t.StartDate);
            tournament.ParticipantCount = t.Standings.Count;
            tournament.ImportedAt = DateTimeOffset.UtcNow;

            // Save now so a brand-new tournament has an Id before its decks reference it, and so
            // re-syncing an already-known tournament can look up its existing deck rows to replace.
            await db.SaveChangesAsync(ct);

            var existingDecks = await db.CommunityDecks
                .Where(d => d.TournamentId == tournament.Id)
                .ToListAsync(ct);
            if (existingDecks.Count > 0)
            {
                db.CommunityDecks.RemoveRange(existingDecks);
                await db.SaveChangesAsync(ct);
            }

            foreach (var standing in t.Standings)
            {
                if (string.IsNullOrWhiteSpace(standing.Decklist) || standing.DeckObj is null || standing.DeckObj.Count == 0)
                    continue;

                var deck = new CommunityDeckEntity
                {
                    TournamentId = tournament.Id,
                    PlayerName = standing.Name ?? "",
                    Standing = standing.Standing ?? 0,
                    ImportedAt = DateTimeOffset.UtcNow,
                };

                foreach (var (sectionName, sectionJson) in standing.DeckObj)
                {
                    if (!SectionMap.TryGetValue(sectionName, out var mappedSection)) continue;

                    Dictionary<string, TopDeckCardRef>? cardRefs;
                    try
                    {
                        cardRefs = sectionJson.Deserialize<Dictionary<string, TopDeckCardRef>>(CardRefOptions);
                    }
                    catch (JsonException)
                    {
                        continue;
                    }
                    if (cardRefs is null) continue;

                    foreach (var (cardName, cardRef) in cardRefs)
                    {
                        if (string.IsNullOrWhiteSpace(cardRef.Id) || cardRef.Count <= 0) continue;

                        var resolution = await resolver.ResolveAsync(cardRef.Id, ct);
                        if (resolution.Status == CardResolution.Unresolved)
                        {
                            unresolvedCount++;
                            continue;
                        }

                        if (string.Equals(sectionName, "Legend", StringComparison.OrdinalIgnoreCase))
                        {
                            deck.LegendCardId = resolution.CardId;
                            deck.LegendRawName = cardName;
                        }

                        deck.Cards.Add(new CommunityDeckCardEntity
                        {
                            CardId = resolution.CardId!,
                            Quantity = cardRef.Count,
                            Section = mappedSection,
                        });
                    }
                }

                db.CommunityDecks.Add(deck);
                deckCount++;
            }

            await db.SaveChangesAsync(ct);
        }

        var state = await db.CommunitySyncState.FirstOrDefaultAsync(ct) ?? Add(new CommunitySyncStateEntity());
        state.LastSyncAt = DateTimeOffset.UtcNow;
        state.LastSyncOk = true;
        state.TournamentCount = tournaments.Count;
        state.DeckCount = deckCount;
        state.UnresolvedCardCount = unresolvedCount;
        state.LastError = null;
        await db.SaveChangesAsync(ct);

        return new CommunitySyncResult(true, tournaments.Count, deckCount, unresolvedCount, null);
    }

    private async Task<CommunitySyncResult> FailAsync(string error, CancellationToken ct)
    {
        var state = await db.CommunitySyncState.FirstOrDefaultAsync(ct) ?? Add(new CommunitySyncStateEntity());
        state.LastSyncAt = DateTimeOffset.UtcNow;
        state.LastSyncOk = false;
        state.LastError = error;
        await db.SaveChangesAsync(ct);
        return new CommunitySyncResult(false, 0, 0, 0, error);
    }

    private CommunitySyncStateEntity Add(CommunitySyncStateEntity entity)
    {
        db.CommunitySyncState.Add(entity);
        return entity;
    }
}
