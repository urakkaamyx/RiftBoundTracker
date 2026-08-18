using Microsoft.EntityFrameworkCore;

namespace RiftBoundTracker.App.Data;

public class AppDbContext(DbContextOptions<AppDbContext> options) : DbContext(options)
{
    public DbSet<CardEntity> Cards => Set<CardEntity>();
    public DbSet<SyncStateEntity> SyncState => Set<SyncStateEntity>();
    public DbSet<DeckEntity> Decks => Set<DeckEntity>();
    public DbSet<DeckCardEntity> DeckCards => Set<DeckCardEntity>();
    public DbSet<PriceSnapshotEntity> PriceSnapshots => Set<PriceSnapshotEntity>();
    public DbSet<PriceQueueEntity> PriceQueue => Set<PriceQueueEntity>();
    public DbSet<CardTextSymbolEntity> CardTextSymbols => Set<CardTextSymbolEntity>();
    public DbSet<CommunityTournamentEntity> CommunityTournaments => Set<CommunityTournamentEntity>();
    public DbSet<CommunityDeckEntity> CommunityDecks => Set<CommunityDeckEntity>();
    public DbSet<CommunityDeckCardEntity> CommunityDeckCards => Set<CommunityDeckCardEntity>();
    public DbSet<CommunitySyncStateEntity> CommunitySyncState => Set<CommunitySyncStateEntity>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        var card = modelBuilder.Entity<CardEntity>();
        card.HasKey(c => c.Id);
        card.HasIndex(c => c.SetId);
        card.HasIndex(c => c.CollectorNumber);
        card.HasIndex(c => new { c.SetId, c.CollectorNumber });
        card.HasIndex(c => c.IsFavorite);
        card.HasIndex(c => c.BinderCount);

        modelBuilder.Entity<SyncStateEntity>().HasKey(s => s.Id);

        var deck = modelBuilder.Entity<DeckEntity>();
        deck.HasKey(d => d.Id);
        deck.HasIndex(d => d.UpdatedAt);

        var deckCard = modelBuilder.Entity<DeckCardEntity>();
        deckCard.HasKey(dc => new { dc.DeckId, dc.CardId, dc.Section });
        deckCard.HasOne(dc => dc.Deck)
            .WithMany(d => d.Cards)
            .HasForeignKey(dc => dc.DeckId)
            .OnDelete(DeleteBehavior.Cascade);
        deckCard.HasOne(dc => dc.Card)
            .WithMany(c => c.DeckCards)
            .HasForeignKey(dc => dc.CardId)
            .OnDelete(DeleteBehavior.Restrict);

        var price = modelBuilder.Entity<PriceSnapshotEntity>();
        price.HasKey(p => p.Id);
        price.HasIndex(p => new { p.CardId, p.CapturedAt });
        price.HasIndex(p => new { p.CardId, p.Provider, p.VariantId, p.CapturedAt });
        price.HasOne(p => p.Card)
            .WithMany(c => c.PriceSnapshots)
            .HasForeignKey(p => p.CardId)
            .OnDelete(DeleteBehavior.Cascade);

        var priceQueue = modelBuilder.Entity<PriceQueueEntity>();
        priceQueue.HasKey(q => q.CardId);
        priceQueue.HasIndex(q => q.QueuedAt);
        priceQueue.HasOne(q => q.Card)
            .WithOne(c => c.PriceQueueItem)
            .HasForeignKey<PriceQueueEntity>(q => q.CardId)
            .OnDelete(DeleteBehavior.Cascade);

        var symbol = modelBuilder.Entity<CardTextSymbolEntity>();
        symbol.HasKey(s => s.Token);
        symbol.HasIndex(s => new { s.Kind, s.SortOrder });

        var tournament = modelBuilder.Entity<CommunityTournamentEntity>();
        tournament.HasKey(t => t.Id);
        tournament.HasIndex(t => t.ExternalTournamentId).IsUnique();
        tournament.HasIndex(t => t.StartDate);

        var communityDeck = modelBuilder.Entity<CommunityDeckEntity>();
        communityDeck.HasKey(d => d.Id);
        communityDeck.HasIndex(d => d.LegendCardId);
        communityDeck.HasOne(d => d.Tournament)
            .WithMany(t => t.Decks)
            .HasForeignKey(d => d.TournamentId)
            .OnDelete(DeleteBehavior.Cascade);
        communityDeck.HasOne(d => d.LegendCard)
            .WithMany()
            .HasForeignKey(d => d.LegendCardId)
            .OnDelete(DeleteBehavior.Restrict);

        var communityDeckCard = modelBuilder.Entity<CommunityDeckCardEntity>();
        communityDeckCard.HasKey(c => c.Id);
        communityDeckCard.HasIndex(c => new { c.CommunityDeckId, c.CardId });
        communityDeckCard.HasIndex(c => c.CardId);
        communityDeckCard.HasOne(c => c.CommunityDeck)
            .WithMany(d => d.Cards)
            .HasForeignKey(c => c.CommunityDeckId)
            .OnDelete(DeleteBehavior.Cascade);
        communityDeckCard.HasOne(c => c.Card)
            .WithMany()
            .HasForeignKey(c => c.CardId)
            .OnDelete(DeleteBehavior.Restrict);

        modelBuilder.Entity<CommunitySyncStateEntity>().HasKey(s => s.Id);
    }
}
