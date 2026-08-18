using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace RiftBoundTracker.App.Migrations
{
    /// <inheritdoc />
    public partial class AddRuleConcepts : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "RuleConcepts",
                columns: table => new
                {
                    Id = table.Column<int>(type: "INTEGER", nullable: false)
                        .Annotation("Sqlite:Autoincrement", true),
                    Name = table.Column<string>(type: "TEXT", nullable: false),
                    NormalizedName = table.Column<string>(type: "TEXT", nullable: false),
                    Description = table.Column<string>(type: "TEXT", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_RuleConcepts", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "RuleConceptKeywords",
                columns: table => new
                {
                    ConceptId = table.Column<int>(type: "INTEGER", nullable: false),
                    KeywordId = table.Column<int>(type: "INTEGER", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_RuleConceptKeywords", x => new { x.ConceptId, x.KeywordId });
                    table.ForeignKey(
                        name: "FK_RuleConceptKeywords_RuleConcepts_ConceptId",
                        column: x => x.ConceptId,
                        principalTable: "RuleConcepts",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                    table.ForeignKey(
                        name: "FK_RuleConceptKeywords_RuleKeywords_KeywordId",
                        column: x => x.KeywordId,
                        principalTable: "RuleKeywords",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "RuleConceptPhrases",
                columns: table => new
                {
                    Id = table.Column<int>(type: "INTEGER", nullable: false)
                        .Annotation("Sqlite:Autoincrement", true),
                    ConceptId = table.Column<int>(type: "INTEGER", nullable: false),
                    Phrase = table.Column<string>(type: "TEXT", nullable: false),
                    NormalizedPhrase = table.Column<string>(type: "TEXT", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_RuleConceptPhrases", x => x.Id);
                    table.ForeignKey(
                        name: "FK_RuleConceptPhrases_RuleConcepts_ConceptId",
                        column: x => x.ConceptId,
                        principalTable: "RuleConcepts",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateIndex(
                name: "IX_RuleConceptKeywords_KeywordId",
                table: "RuleConceptKeywords",
                column: "KeywordId");

            migrationBuilder.CreateIndex(
                name: "IX_RuleConceptPhrases_ConceptId",
                table: "RuleConceptPhrases",
                column: "ConceptId");

            migrationBuilder.CreateIndex(
                name: "IX_RuleConceptPhrases_NormalizedPhrase",
                table: "RuleConceptPhrases",
                column: "NormalizedPhrase");

            migrationBuilder.CreateIndex(
                name: "IX_RuleConcepts_NormalizedName",
                table: "RuleConcepts",
                column: "NormalizedName",
                unique: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "RuleConceptKeywords");

            migrationBuilder.DropTable(
                name: "RuleConceptPhrases");

            migrationBuilder.DropTable(
                name: "RuleConcepts");
        }
    }
}
