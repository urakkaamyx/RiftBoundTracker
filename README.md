# RiftBound Vault

A self-hosted collection tracker for the *Riftbound* TCG. Runs a local web app you open from
your phone or PC — browse your cache of every card in a set, mark what you own, and scan cards
(by photo, live camera, or typing the number) to add them.

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

Your collection data lives in `App_Data/` next to the exe and is never touched by updates.

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
