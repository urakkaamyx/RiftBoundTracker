using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace RiftBoundTracker.App.Migrations
{
    /// <inheritdoc />
    public partial class AddCardDescriptionSymbols : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<int>(
                name: "CatalogContentRevision",
                table: "SyncState",
                type: "INTEGER",
                nullable: false,
                defaultValue: 0);

            migrationBuilder.AddColumn<string>(
                name: "TextRich",
                table: "Cards",
                type: "TEXT",
                nullable: true);

            migrationBuilder.CreateTable(
                name: "CardTextSymbols",
                columns: table => new
                {
                    Token = table.Column<string>(type: "TEXT", nullable: false),
                    Label = table.Column<string>(type: "TEXT", nullable: false),
                    Kind = table.Column<string>(type: "TEXT", nullable: false),
                    Shape = table.Column<string>(type: "TEXT", nullable: false),
                    AssetPath = table.Column<string>(type: "TEXT", nullable: true),
                    ForegroundColor = table.Column<string>(type: "TEXT", nullable: false),
                    BackgroundColor = table.Column<string>(type: "TEXT", nullable: false),
                    BorderColor = table.Column<string>(type: "TEXT", nullable: false),
                    SortOrder = table.Column<int>(type: "INTEGER", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_CardTextSymbols", x => x.Token);
                });

            migrationBuilder.CreateIndex(
                name: "IX_CardTextSymbols_Kind_SortOrder",
                table: "CardTextSymbols",
                columns: new[] { "Kind", "SortOrder" });
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "CardTextSymbols");

            migrationBuilder.DropColumn(
                name: "CatalogContentRevision",
                table: "SyncState");

            migrationBuilder.DropColumn(
                name: "TextRich",
                table: "Cards");
        }
    }
}
