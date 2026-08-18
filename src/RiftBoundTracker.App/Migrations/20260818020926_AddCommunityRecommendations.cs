using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace RiftBoundTracker.App.Migrations
{
    /// <inheritdoc />
    public partial class AddCommunityRecommendations : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "CommunitySyncState",
                columns: table => new
                {
                    Id = table.Column<int>(type: "INTEGER", nullable: false)
                        .Annotation("Sqlite:Autoincrement", true),
                    LastSyncAt = table.Column<DateTimeOffset>(type: "TEXT", nullable: true),
                    LastSyncOk = table.Column<bool>(type: "INTEGER", nullable: false),
                    TournamentCount = table.Column<int>(type: "INTEGER", nullable: false),
                    DeckCount = table.Column<int>(type: "INTEGER", nullable: false),
                    UnresolvedCardCount = table.Column<int>(type: "INTEGER", nullable: false),
                    LastError = table.Column<string>(type: "TEXT", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_CommunitySyncState", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "CommunityTournaments",
                columns: table => new
                {
                    Id = table.Column<int>(type: "INTEGER", nullable: false)
                        .Annotation("Sqlite:Autoincrement", true),
                    ExternalTournamentId = table.Column<string>(type: "TEXT", nullable: false),
                    Name = table.Column<string>(type: "TEXT", nullable: false),
                    Format = table.Column<string>(type: "TEXT", nullable: false),
                    StartDate = table.Column<DateTimeOffset>(type: "TEXT", nullable: false),
                    ParticipantCount = table.Column<int>(type: "INTEGER", nullable: false),
                    ImportedAt = table.Column<DateTimeOffset>(type: "TEXT", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_CommunityTournaments", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "CommunityDecks",
                columns: table => new
                {
                    Id = table.Column<int>(type: "INTEGER", nullable: false)
                        .Annotation("Sqlite:Autoincrement", true),
                    TournamentId = table.Column<int>(type: "INTEGER", nullable: false),
                    PlayerName = table.Column<string>(type: "TEXT", nullable: false),
                    LegendCardId = table.Column<string>(type: "TEXT", nullable: true),
                    LegendRawName = table.Column<string>(type: "TEXT", nullable: false),
                    Standing = table.Column<int>(type: "INTEGER", nullable: false),
                    ImportedAt = table.Column<DateTimeOffset>(type: "TEXT", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_CommunityDecks", x => x.Id);
                    table.ForeignKey(
                        name: "FK_CommunityDecks_Cards_LegendCardId",
                        column: x => x.LegendCardId,
                        principalTable: "Cards",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                    table.ForeignKey(
                        name: "FK_CommunityDecks_CommunityTournaments_TournamentId",
                        column: x => x.TournamentId,
                        principalTable: "CommunityTournaments",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "CommunityDeckCards",
                columns: table => new
                {
                    Id = table.Column<int>(type: "INTEGER", nullable: false)
                        .Annotation("Sqlite:Autoincrement", true),
                    CommunityDeckId = table.Column<int>(type: "INTEGER", nullable: false),
                    CardId = table.Column<string>(type: "TEXT", nullable: false),
                    Quantity = table.Column<int>(type: "INTEGER", nullable: false),
                    Section = table.Column<string>(type: "TEXT", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_CommunityDeckCards", x => x.Id);
                    table.ForeignKey(
                        name: "FK_CommunityDeckCards_Cards_CardId",
                        column: x => x.CardId,
                        principalTable: "Cards",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                    table.ForeignKey(
                        name: "FK_CommunityDeckCards_CommunityDecks_CommunityDeckId",
                        column: x => x.CommunityDeckId,
                        principalTable: "CommunityDecks",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateIndex(
                name: "IX_CommunityDeckCards_CardId",
                table: "CommunityDeckCards",
                column: "CardId");

            migrationBuilder.CreateIndex(
                name: "IX_CommunityDeckCards_CommunityDeckId_CardId",
                table: "CommunityDeckCards",
                columns: new[] { "CommunityDeckId", "CardId" });

            migrationBuilder.CreateIndex(
                name: "IX_CommunityDecks_LegendCardId",
                table: "CommunityDecks",
                column: "LegendCardId");

            migrationBuilder.CreateIndex(
                name: "IX_CommunityDecks_TournamentId",
                table: "CommunityDecks",
                column: "TournamentId");

            migrationBuilder.CreateIndex(
                name: "IX_CommunityTournaments_ExternalTournamentId",
                table: "CommunityTournaments",
                column: "ExternalTournamentId",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_CommunityTournaments_StartDate",
                table: "CommunityTournaments",
                column: "StartDate");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "CommunityDeckCards");

            migrationBuilder.DropTable(
                name: "CommunitySyncState");

            migrationBuilder.DropTable(
                name: "CommunityDecks");

            migrationBuilder.DropTable(
                name: "CommunityTournaments");
        }
    }
}
