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
    public DbSet<RuleDocumentEntity> RuleDocuments => Set<RuleDocumentEntity>();
    public DbSet<RuleEntryEntity> RuleEntries => Set<RuleEntryEntity>();
    public DbSet<RuleKeywordEntity> RuleKeywords => Set<RuleKeywordEntity>();
    public DbSet<RuleKeywordAliasEntity> RuleKeywordAliases => Set<RuleKeywordAliasEntity>();
    public DbSet<RuleEntryKeywordEntity> RuleEntryKeywords => Set<RuleEntryKeywordEntity>();
    public DbSet<RuleCrossReferenceEntity> RuleCrossReferences => Set<RuleCrossReferenceEntity>();
    public DbSet<CardRuleReferenceEntity> CardRuleReferences => Set<CardRuleReferenceEntity>();
    public DbSet<CardErrataEntity> CardErrata => Set<CardErrataEntity>();
    public DbSet<CardLegalityEntity> CardLegalities => Set<CardLegalityEntity>();
    public DbSet<RulesSyncStateEntity> RulesSyncState => Set<RulesSyncStateEntity>();
    public DbSet<RuleConceptEntity> RuleConcepts => Set<RuleConceptEntity>();
    public DbSet<RuleConceptKeywordEntity> RuleConceptKeywords => Set<RuleConceptKeywordEntity>();
    public DbSet<RuleConceptPhraseEntity> RuleConceptPhrases => Set<RuleConceptPhraseEntity>();
    public DbSet<EmulatorAccessEntity> EmulatorAccess => Set<EmulatorAccessEntity>();

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

        var ruleDocument = modelBuilder.Entity<RuleDocumentEntity>();
        ruleDocument.HasKey(d => d.Id);
        ruleDocument.HasIndex(d => new { d.SourceType, d.IsCurrent });

        var ruleEntry = modelBuilder.Entity<RuleEntryEntity>();
        ruleEntry.HasKey(r => r.Id);
        ruleEntry.HasIndex(r => r.RuleNumber);
        ruleEntry.HasIndex(r => new { r.DocumentId, r.SortOrder });
        ruleEntry.HasOne(r => r.Document)
            .WithMany(d => d.Entries)
            .HasForeignKey(r => r.DocumentId)
            .OnDelete(DeleteBehavior.Cascade);
        ruleEntry.HasOne(r => r.Parent)
            .WithMany()
            .HasForeignKey(r => r.ParentRuleId)
            .OnDelete(DeleteBehavior.Restrict);

        var ruleKeyword = modelBuilder.Entity<RuleKeywordEntity>();
        ruleKeyword.HasKey(k => k.Id);
        ruleKeyword.HasIndex(k => k.NormalizedName).IsUnique();
        ruleKeyword.HasOne(k => k.CanonicalRule)
            .WithMany()
            .HasForeignKey(k => k.CanonicalRuleId)
            .OnDelete(DeleteBehavior.SetNull);

        var ruleKeywordAlias = modelBuilder.Entity<RuleKeywordAliasEntity>();
        ruleKeywordAlias.HasKey(a => a.Id);
        ruleKeywordAlias.HasIndex(a => a.NormalizedAlias);
        ruleKeywordAlias.HasOne(a => a.Keyword)
            .WithMany(k => k.Aliases)
            .HasForeignKey(a => a.KeywordId)
            .OnDelete(DeleteBehavior.Cascade);

        var ruleEntryKeyword = modelBuilder.Entity<RuleEntryKeywordEntity>();
        ruleEntryKeyword.HasKey(rk => new { rk.RuleEntryId, rk.KeywordId });
        ruleEntryKeyword.HasOne(rk => rk.RuleEntry)
            .WithMany(r => r.Keywords)
            .HasForeignKey(rk => rk.RuleEntryId)
            .OnDelete(DeleteBehavior.Cascade);
        ruleEntryKeyword.HasOne(rk => rk.Keyword)
            .WithMany(k => k.RuleEntries)
            .HasForeignKey(rk => rk.KeywordId)
            .OnDelete(DeleteBehavior.Cascade);

        var ruleCrossReference = modelBuilder.Entity<RuleCrossReferenceEntity>();
        ruleCrossReference.HasKey(x => x.Id);
        ruleCrossReference.HasIndex(x => new { x.FromRuleId, x.ToRuleId }).IsUnique();
        ruleCrossReference.HasOne(x => x.FromRule)
            .WithMany()
            .HasForeignKey(x => x.FromRuleId)
            .OnDelete(DeleteBehavior.Cascade);
        ruleCrossReference.HasOne(x => x.ToRule)
            .WithMany()
            .HasForeignKey(x => x.ToRuleId)
            .OnDelete(DeleteBehavior.Restrict);

        var cardRuleReference = modelBuilder.Entity<CardRuleReferenceEntity>();
        cardRuleReference.HasKey(x => x.Id);
        cardRuleReference.HasIndex(x => new { x.CardId, x.KeywordId }).IsUnique();
        cardRuleReference.HasOne(x => x.Card)
            .WithMany()
            .HasForeignKey(x => x.CardId)
            .OnDelete(DeleteBehavior.Cascade);
        cardRuleReference.HasOne(x => x.Keyword)
            .WithMany()
            .HasForeignKey(x => x.KeywordId)
            .OnDelete(DeleteBehavior.Cascade);

        var cardErrata = modelBuilder.Entity<CardErrataEntity>();
        cardErrata.HasKey(x => x.Id);
        cardErrata.HasIndex(x => x.CardId);
        cardErrata.HasOne(x => x.Document)
            .WithMany()
            .HasForeignKey(x => x.DocumentId)
            .OnDelete(DeleteBehavior.Cascade);
        cardErrata.HasOne(x => x.Card)
            .WithMany()
            .HasForeignKey(x => x.CardId)
            .OnDelete(DeleteBehavior.SetNull);

        var cardLegality = modelBuilder.Entity<CardLegalityEntity>();
        cardLegality.HasKey(x => x.Id);
        cardLegality.HasIndex(x => new { x.CardId, x.Format });
        cardLegality.HasOne(x => x.Document)
            .WithMany()
            .HasForeignKey(x => x.DocumentId)
            .OnDelete(DeleteBehavior.Cascade);
        cardLegality.HasOne(x => x.Card)
            .WithMany()
            .HasForeignKey(x => x.CardId)
            .OnDelete(DeleteBehavior.SetNull);

        modelBuilder.Entity<RulesSyncStateEntity>().HasKey(s => s.Id);

        var ruleConcept = modelBuilder.Entity<RuleConceptEntity>();
        ruleConcept.HasKey(c => c.Id);
        ruleConcept.HasIndex(c => c.NormalizedName).IsUnique();

        var ruleConceptKeyword = modelBuilder.Entity<RuleConceptKeywordEntity>();
        ruleConceptKeyword.HasKey(x => new { x.ConceptId, x.KeywordId });
        ruleConceptKeyword.HasOne(x => x.Concept)
            .WithMany(c => c.Keywords)
            .HasForeignKey(x => x.ConceptId)
            .OnDelete(DeleteBehavior.Cascade);
        ruleConceptKeyword.HasOne(x => x.Keyword)
            .WithMany()
            .HasForeignKey(x => x.KeywordId)
            .OnDelete(DeleteBehavior.Cascade);

        modelBuilder.Entity<EmulatorAccessEntity>().HasKey(s => s.Id);

        var ruleConceptPhrase = modelBuilder.Entity<RuleConceptPhraseEntity>();
        ruleConceptPhrase.HasKey(x => x.Id);
        ruleConceptPhrase.HasIndex(x => x.NormalizedPhrase);
        ruleConceptPhrase.HasOne(x => x.Concept)
            .WithMany(c => c.Phrases)
            .HasForeignKey(x => x.ConceptId)
            .OnDelete(DeleteBehavior.Cascade);
    }
}
