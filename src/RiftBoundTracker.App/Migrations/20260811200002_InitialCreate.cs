using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace RiftBoundTracker.App.Migrations
{
    /// <inheritdoc />
    public partial class InitialCreate : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "Cards",
                columns: table => new
                {
                    Id = table.Column<string>(type: "TEXT", nullable: false),
                    Name = table.Column<string>(type: "TEXT", nullable: false),
                    CollectorNumber = table.Column<int>(type: "INTEGER", nullable: false),
                    SetId = table.Column<string>(type: "TEXT", nullable: false),
                    SetLabel = table.Column<string>(type: "TEXT", nullable: false),
                    Type = table.Column<string>(type: "TEXT", nullable: false),
                    Supertype = table.Column<string>(type: "TEXT", nullable: true),
                    Rarity = table.Column<string>(type: "TEXT", nullable: false),
                    DomainsCsv = table.Column<string>(type: "TEXT", nullable: false),
                    TextPlain = table.Column<string>(type: "TEXT", nullable: true),
                    Flavour = table.Column<string>(type: "TEXT", nullable: true),
                    ImageUrl = table.Column<string>(type: "TEXT", nullable: false),
                    LocalImagePath = table.Column<string>(type: "TEXT", nullable: true),
                    ImageHash = table.Column<byte[]>(type: "BLOB", nullable: true),
                    Artist = table.Column<string>(type: "TEXT", nullable: true),
                    Orientation = table.Column<string>(type: "TEXT", nullable: true),
                    TcgplayerId = table.Column<string>(type: "TEXT", nullable: true),
                    Energy = table.Column<int>(type: "INTEGER", nullable: true),
                    Might = table.Column<int>(type: "INTEGER", nullable: true),
                    Power = table.Column<int>(type: "INTEGER", nullable: true),
                    OwnedCount = table.Column<int>(type: "INTEGER", nullable: false),
                    CachedAt = table.Column<DateTimeOffset>(type: "TEXT", nullable: false),
                    UpdatedAt = table.Column<DateTimeOffset>(type: "TEXT", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Cards", x => x.Id);
                });

            migrationBuilder.CreateIndex(
                name: "IX_Cards_CollectorNumber",
                table: "Cards",
                column: "CollectorNumber");

            migrationBuilder.CreateIndex(
                name: "IX_Cards_SetId",
                table: "Cards",
                column: "SetId");

            migrationBuilder.CreateIndex(
                name: "IX_Cards_SetId_CollectorNumber",
                table: "Cards",
                columns: new[] { "SetId", "CollectorNumber" });
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "Cards");
        }
    }
}
