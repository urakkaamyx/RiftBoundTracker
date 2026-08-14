# RiftBound Vault

A local-first collection and deck manager for the *Riftbound* TCG. The Windows desktop app also
serves the same responsive interface to a phone on your LAN. It includes the full Vault, deck
builder, favorites, trade binder, collection analytics, photo/live-camera scanning, and optional
market pricing.

Card data and art are pulled from the [Riftcodex](https://riftcodex.com) API once per set (via
the Sync button) and cached locally in SQLite — everyday use never re-hits the live API.

## Running it

Download the latest release from the [Releases](../../releases) page, unzip it, and run
`RiftBoundTracker.App.exe`. No .NET install required — it's self-contained.

The app prints a couple of URLs on startup:

- `http://localhost:5080` — open this on the same PC
- `http://<your-LAN-IP>:5080` — open this from your phone (same Wi-Fi)
- `https://<your-LAN-IP>:5443` — needed specifically for the live-camera scanner (browsers only
  allow camera access over HTTPS from a non-localhost address). Your browser will warn about the
  self-signed certificate the first time — tap **Advanced → Proceed**; it remembers after that.

Your collection data lives in `App_Data/` next to the exe and is never included in an update.
Before a schema upgrade, the app creates a SQLite-consistent timestamped backup in
`App_Data/backups/`, verifies it, runs the migration, and confirms that card and ownership totals
did not change. If verification fails, the backup is restored and startup stops with an error.

## Pricing

Pricing is optional. Add a JustTCG API key on the Settings page or set the
`JUSTTCG_API_KEY` environment variable. A key entered in the app is encrypted for the current
Windows user and stored under `App_Data`; it is never placed in source or sent to the browser.
Price refreshes are cached as local snapshots. The app shows an explicit unconfigured state when
no provider is available and never generates placeholder prices.

The normal refresh covers cards that are owned, favorited, in the trade binder, or used in a
deck. The full-catalog refresh is available separately and observes the provider's documented
free-tier batch and request limits.

## Updating

Click **Check for updates** in the app. If a newer release is available, **Update & Restart**
downloads it, replaces the app files, and relaunches automatically — your collection data and
settings are untouched. Any database schema changes ship as migrations, so upgrading never wipes
your data.

## Development

Requires the .NET 10 SDK.

```bash
cd src/RiftBoundTracker.App
dotnet run
```

Schema changes go through EF Core migrations — never edit the database by hand:

```bash
dotnet ef migrations add SomeDescriptiveName
```
