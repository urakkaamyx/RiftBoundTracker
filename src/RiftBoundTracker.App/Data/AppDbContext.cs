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
    }
}
