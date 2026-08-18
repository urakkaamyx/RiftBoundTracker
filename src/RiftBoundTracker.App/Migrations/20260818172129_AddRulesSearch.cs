using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace RiftBoundTracker.App.Migrations
{
    /// <inheritdoc />
    public partial class AddRulesSearch : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "RuleDocuments",
                columns: table => new
                {
                    Id = table.Column<int>(type: "INTEGER", nullable: false)
                        .Annotation("Sqlite:Autoincrement", true),
                    SourceType = table.Column<int>(type: "INTEGER", nullable: false),
                    Title = table.Column<string>(type: "TEXT", nullable: false),
                    SourceUrl = table.Column<string>(type: "TEXT", nullable: false),
                    DownloadUrl = table.Column<string>(type: "TEXT", nullable: true),
                    DocumentVersion = table.Column<string>(type: "TEXT", nullable: true),
                    PublishedAt = table.Column<DateTimeOffset>(type: "TEXT", nullable: true),
                    DiscoveredAt = table.Column<DateTimeOffset>(type: "TEXT", nullable: false),
                    DownloadedAt = table.Column<DateTimeOffset>(type: "TEXT", nullable: true),
                    ContentHash = table.Column<string>(type: "TEXT", nullable: true),
                    Authority = table.Column<int>(type: "INTEGER", nullable: false),
                    IsCurrent = table.Column<bool>(type: "INTEGER", nullable: false),
                    ParseStatus = table.Column<string>(type: "TEXT", nullable: true),
                    LastError = table.Column<string>(type: "TEXT", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_RuleDocuments", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "RulesSyncState",
                columns: table => new
                {
                    Id = table.Column<int>(type: "INTEGER", nullable: false)
                        .Annotation("Sqlite:Autoincrement", true),
                    LastCheckAt = table.Column<DateTimeOffset>(type: "TEXT", nullable: true),
                    LastSuccessfulSyncAt = table.Column<DateTimeOffset>(type: "TEXT", nullable: true),
                    LastSyncOk = table.Column<bool>(type: "INTEGER", nullable: false),
                    DocumentsIndexed = table.Column<int>(type: "INTEGER", nullable: false),
                    RulesIndexed = table.Column<int>(type: "INTEGER", nullable: false),
                    KeywordsIndexed = table.Column<int>(type: "INTEGER", nullable: false),
                    ErrataIndexed = table.Column<int>(type: "INTEGER", nullable: false),
                    LegalityEntriesIndexed = table.Column<int>(type: "INTEGER", nullable: false),
                    LastError = table.Column<string>(type: "TEXT", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_RulesSyncState", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "CardErrata",
                columns: table => new
                {
                    Id = table.Column<int>(type: "INTEGER", nullable: false)
                        .Annotation("Sqlite:Autoincrement", true),
                    CardId = table.Column<string>(type: "TEXT", nullable: true),
                    CardNameRaw = table.Column<string>(type: "TEXT", nullable: false),
                    DocumentId = table.Column<int>(type: "INTEGER", nullable: false),
                    OriginalText = table.Column<string>(type: "TEXT", nullable: true),
                    CorrectedText = table.Column<string>(type: "TEXT", nullable: true),
                    EffectiveAt = table.Column<DateTimeOffset>(type: "TEXT", nullable: true),
                    IsCurrent = table.Column<bool>(type: "INTEGER", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_CardErrata", x => x.Id);
                    table.ForeignKey(
                        name: "FK_CardErrata_Cards_CardId",
                        column: x => x.CardId,
                        principalTable: "Cards",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.SetNull);
                    table.ForeignKey(
                        name: "FK_CardErrata_RuleDocuments_DocumentId",
                        column: x => x.DocumentId,
                        principalTable: "RuleDocuments",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "CardLegalities",
                columns: table => new
                {
                    Id = table.Column<int>(type: "INTEGER", nullable: false)
                        .Annotation("Sqlite:Autoincrement", true),
                    CardId = table.Column<string>(type: "TEXT", nullable: true),
                    CardNameRaw = table.Column<string>(type: "TEXT", nullable: false),
                    Format = table.Column<string>(type: "TEXT", nullable: false),
                    Status = table.Column<int>(type: "INTEGER", nullable: false),
                    EffectiveAt = table.Column<DateTimeOffset>(type: "TEXT", nullable: true),
                    DocumentId = table.Column<int>(type: "INTEGER", nullable: false),
                    IsCurrent = table.Column<bool>(type: "INTEGER", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_CardLegalities", x => x.Id);
                    table.ForeignKey(
                        name: "FK_CardLegalities_Cards_CardId",
                        column: x => x.CardId,
                        principalTable: "Cards",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.SetNull);
                    table.ForeignKey(
                        name: "FK_CardLegalities_RuleDocuments_DocumentId",
                        column: x => x.DocumentId,
                        principalTable: "RuleDocuments",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "RuleEntries",
                columns: table => new
                {
                    Id = table.Column<int>(type: "INTEGER", nullable: false)
                        .Annotation("Sqlite:Autoincrement", true),
                    DocumentId = table.Column<int>(type: "INTEGER", nullable: false),
                    RuleNumber = table.Column<string>(type: "TEXT", nullable: true),
                    ParentRuleId = table.Column<int>(type: "INTEGER", nullable: true),
                    Title = table.Column<string>(type: "TEXT", nullable: true),
                    Text = table.Column<string>(type: "TEXT", nullable: false),
                    SortOrder = table.Column<int>(type: "INTEGER", nullable: false),
                    Authority = table.Column<int>(type: "INTEGER", nullable: false),
                    IsCurrent = table.Column<bool>(type: "INTEGER", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_RuleEntries", x => x.Id);
                    table.ForeignKey(
                        name: "FK_RuleEntries_RuleDocuments_DocumentId",
                        column: x => x.DocumentId,
                        principalTable: "RuleDocuments",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                    table.ForeignKey(
                        name: "FK_RuleEntries_RuleEntries_ParentRuleId",
                        column: x => x.ParentRuleId,
                        principalTable: "RuleEntries",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "RuleCrossReferences",
                columns: table => new
                {
                    Id = table.Column<int>(type: "INTEGER", nullable: false)
                        .Annotation("Sqlite:Autoincrement", true),
                    FromRuleId = table.Column<int>(type: "INTEGER", nullable: false),
                    ToRuleId = table.Column<int>(type: "INTEGER", nullable: false),
                    ReferenceText = table.Column<string>(type: "TEXT", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_RuleCrossReferences", x => x.Id);
                    table.ForeignKey(
                        name: "FK_RuleCrossReferences_RuleEntries_FromRuleId",
                        column: x => x.FromRuleId,
                        principalTable: "RuleEntries",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                    table.ForeignKey(
                        name: "FK_RuleCrossReferences_RuleEntries_ToRuleId",
                        column: x => x.ToRuleId,
                        principalTable: "RuleEntries",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "RuleKeywords",
                columns: table => new
                {
                    Id = table.Column<int>(type: "INTEGER", nullable: false)
                        .Annotation("Sqlite:Autoincrement", true),
                    Name = table.Column<string>(type: "TEXT", nullable: false),
                    NormalizedName = table.Column<string>(type: "TEXT", nullable: false),
                    Definition = table.Column<string>(type: "TEXT", nullable: true),
                    Category = table.Column<string>(type: "TEXT", nullable: true),
                    CanonicalRuleId = table.Column<int>(type: "INTEGER", nullable: true),
                    IsOfficialKeyword = table.Column<bool>(type: "INTEGER", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_RuleKeywords", x => x.Id);
                    table.ForeignKey(
                        name: "FK_RuleKeywords_RuleEntries_CanonicalRuleId",
                        column: x => x.CanonicalRuleId,
                        principalTable: "RuleEntries",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.SetNull);
                });

            migrationBuilder.CreateTable(
                name: "CardRuleReferences",
                columns: table => new
                {
                    Id = table.Column<int>(type: "INTEGER", nullable: false)
                        .Annotation("Sqlite:Autoincrement", true),
                    CardId = table.Column<string>(type: "TEXT", nullable: false),
                    KeywordId = table.Column<int>(type: "INTEGER", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_CardRuleReferences", x => x.Id);
                    table.ForeignKey(
                        name: "FK_CardRuleReferences_Cards_CardId",
                        column: x => x.CardId,
                        principalTable: "Cards",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                    table.ForeignKey(
                        name: "FK_CardRuleReferences_RuleKeywords_KeywordId",
                        column: x => x.KeywordId,
                        principalTable: "RuleKeywords",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "RuleEntryKeywords",
                columns: table => new
                {
                    RuleEntryId = table.Column<int>(type: "INTEGER", nullable: false),
                    KeywordId = table.Column<int>(type: "INTEGER", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_RuleEntryKeywords", x => new { x.RuleEntryId, x.KeywordId });
                    table.ForeignKey(
                        name: "FK_RuleEntryKeywords_RuleEntries_RuleEntryId",
                        column: x => x.RuleEntryId,
                        principalTable: "RuleEntries",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                    table.ForeignKey(
                        name: "FK_RuleEntryKeywords_RuleKeywords_KeywordId",
                        column: x => x.KeywordId,
                        principalTable: "RuleKeywords",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "RuleKeywordAliases",
                columns: table => new
                {
                    Id = table.Column<int>(type: "INTEGER", nullable: false)
                        .Annotation("Sqlite:Autoincrement", true),
                    KeywordId = table.Column<int>(type: "INTEGER", nullable: false),
                    Alias = table.Column<string>(type: "TEXT", nullable: false),
                    NormalizedAlias = table.Column<string>(type: "TEXT", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_RuleKeywordAliases", x => x.Id);
                    table.ForeignKey(
                        name: "FK_RuleKeywordAliases_RuleKeywords_KeywordId",
                        column: x => x.KeywordId,
                        principalTable: "RuleKeywords",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateIndex(
                name: "IX_CardErrata_CardId",
                table: "CardErrata",
                column: "CardId");

            migrationBuilder.CreateIndex(
                name: "IX_CardErrata_DocumentId",
                table: "CardErrata",
                column: "DocumentId");

            migrationBuilder.CreateIndex(
                name: "IX_CardLegalities_CardId_Format",
                table: "CardLegalities",
                columns: new[] { "CardId", "Format" });

            migrationBuilder.CreateIndex(
                name: "IX_CardLegalities_DocumentId",
                table: "CardLegalities",
                column: "DocumentId");

            migrationBuilder.CreateIndex(
                name: "IX_CardRuleReferences_CardId_KeywordId",
                table: "CardRuleReferences",
                columns: new[] { "CardId", "KeywordId" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_CardRuleReferences_KeywordId",
                table: "CardRuleReferences",
                column: "KeywordId");

            migrationBuilder.CreateIndex(
                name: "IX_RuleCrossReferences_FromRuleId_ToRuleId",
                table: "RuleCrossReferences",
                columns: new[] { "FromRuleId", "ToRuleId" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_RuleCrossReferences_ToRuleId",
                table: "RuleCrossReferences",
                column: "ToRuleId");

            migrationBuilder.CreateIndex(
                name: "IX_RuleDocuments_SourceType_IsCurrent",
                table: "RuleDocuments",
                columns: new[] { "SourceType", "IsCurrent" });

            migrationBuilder.CreateIndex(
                name: "IX_RuleEntries_DocumentId_SortOrder",
                table: "RuleEntries",
                columns: new[] { "DocumentId", "SortOrder" });

            migrationBuilder.CreateIndex(
                name: "IX_RuleEntries_ParentRuleId",
                table: "RuleEntries",
                column: "ParentRuleId");

            migrationBuilder.CreateIndex(
                name: "IX_RuleEntries_RuleNumber",
                table: "RuleEntries",
                column: "RuleNumber");

            migrationBuilder.CreateIndex(
                name: "IX_RuleEntryKeywords_KeywordId",
                table: "RuleEntryKeywords",
                column: "KeywordId");

            migrationBuilder.CreateIndex(
                name: "IX_RuleKeywordAliases_KeywordId",
                table: "RuleKeywordAliases",
                column: "KeywordId");

            migrationBuilder.CreateIndex(
                name: "IX_RuleKeywordAliases_NormalizedAlias",
                table: "RuleKeywordAliases",
                column: "NormalizedAlias");

            migrationBuilder.CreateIndex(
                name: "IX_RuleKeywords_CanonicalRuleId",
                table: "RuleKeywords",
                column: "CanonicalRuleId");

            migrationBuilder.CreateIndex(
                name: "IX_RuleKeywords_NormalizedName",
                table: "RuleKeywords",
                column: "NormalizedName",
                unique: true);

            // Standalone FTS5 index (not an EF-modeled entity — EF Core doesn't support virtual
            // tables). Explicit rowid keeps it aligned 1:1 with RuleEntries.Id so a search hit maps
            // straight back to the owning row; RulesImportService fully repopulates it after every
            // sync rather than wiring content='' triggers, since syncs are infrequent (manual
            // trigger) and a full rebuild keeps the read/write code trivially correct.
            migrationBuilder.Sql(
                """
                CREATE VIRTUAL TABLE RuleSearchFts USING fts5(
                    RuleNumber,
                    Title,
                    Text,
                    Keywords,
                    tokenize = 'porter unicode61'
                );
                """);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.Sql("DROP TABLE IF EXISTS RuleSearchFts;");

            migrationBuilder.DropTable(
                name: "CardErrata");

            migrationBuilder.DropTable(
                name: "CardLegalities");

            migrationBuilder.DropTable(
                name: "CardRuleReferences");

            migrationBuilder.DropTable(
                name: "RuleCrossReferences");

            migrationBuilder.DropTable(
                name: "RuleEntryKeywords");

            migrationBuilder.DropTable(
                name: "RuleKeywordAliases");

            migrationBuilder.DropTable(
                name: "RulesSyncState");

            migrationBuilder.DropTable(
                name: "RuleKeywords");

            migrationBuilder.DropTable(
                name: "RuleEntries");

            migrationBuilder.DropTable(
                name: "RuleDocuments");
        }
    }
}
