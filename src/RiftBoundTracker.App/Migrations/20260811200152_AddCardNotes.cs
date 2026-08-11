using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace RiftBoundTracker.App.Migrations
{
    /// <inheritdoc />
    public partial class AddCardNotes : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "Notes",
                table: "Cards",
                type: "TEXT",
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "Notes",
                table: "Cards");
        }
    }
}
