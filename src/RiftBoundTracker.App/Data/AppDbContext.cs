using Microsoft.EntityFrameworkCore;

namespace RiftBoundTracker.App.Data;

public class AppDbContext(DbContextOptions<AppDbContext> options) : DbContext(options)
{
    public DbSet<CardEntity> Cards => Set<CardEntity>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        var card = modelBuilder.Entity<CardEntity>();
        card.HasKey(c => c.Id);
        card.HasIndex(c => c.SetId);
        card.HasIndex(c => c.CollectorNumber);
        card.HasIndex(c => new { c.SetId, c.CollectorNumber });
    }
}
