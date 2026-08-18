# Changelog

## v1.13.3 — Recommended tab now matches Legend variants

- Fixed the Recommended tab only matching community data logged under the exact Legend print in your deck. Choosing VEN-193/166 now also pulls recommendations recorded under its sibling print VEN-147/166 (and any other print of the same Legend) instead of showing "no community data yet".

## v1.13.2 — Vault performance + upgrade prices

- Fixed Vault lag on every Add/Remove click — it was re-fetching the entire card catalog twice per click (once just for filter dropdowns, which never change from an ownership edit). Now only re-fetches when you switch sets.
- Top Recommended Upgrades now shows the market price for missing cards instead of just "Missing".

## v1.13.1 — Deck Builder fixes

- Fixed a crash opening Recommended/Analysis for a deck that has the same card in both Main Deck and Sideboard.
- Fixed the deck's cover art getting stuck on a removed Legend after swapping to a new one outside the "Change Legend" flow.
- Fixed Import not setting the Legend as the deck's cover art.
- Fixed the deck art being cropped instead of showing the whole card.
- Fixed the deck description box visually bleeding into the stats row below it.
- Removed the redundant duplicate card-art block in the deck summary column.
- Added search to the Recommended tab, and hover popouts on Discover panel cards (a stats card for Recommended — inclusion rate, average copies, and which tournaments it appeared in — a normal image preview elsewhere).
- Recommended-tab ownership/"already in deck" checks now count any print of a card, not just the exact print a tournament decklist happened to use.
- Hid the Price Checker tab for now.

## v1.13.0 — Community Recommendations

- New Settings section: **Community Data** — add your own TopDeck.gg API key and pull recent tournament decklists with a manual "Sync Now" button (shows last sync time, tournament/deck counts, unresolved-card count).
- Deck Builder's **Recommended** tab now shows real cards the community plays alongside your Legend — inclusion rate, average copies, and how many you own — with the same add/stepper controls as the other tabs.
- Deck Analysis' **Community Comparison** and **Top Recommended Upgrades** panels now show real data instead of "not synced yet" placeholders.
- Nothing syncs automatically — TopDeck.gg is only ever called when you press Sync Now, to respect its rate limits.

## v1.12.1 — View Changelog

- Added a "View Changelog" button next to "Update and Restart" in Settings, so you can see what's new in an available update before installing it.

## v1.12.0 — Deck Builder Redesign

### Legend Picker
- Variation selector redesigned into a strip of card thumbnails: dark-gold thick outer border, thin bright-gold inner border, tiny gap between segments, and a clearly dimmed/brightened hover state.
- "Not Owned" variants now show a diagonal caution banner instead of a straight ribbon.
- Fixed duplicate "Base" labels on Legends that share a name across two prints (falls back to set code when needed).
- Print variants are now abbreviated on their selector buttons: `ALT`, `EXL`, `SIG`, `MTL`, `OVN`, `STR`, `ULT`.
- Removed the Format dropdown from deck creation (new decks default to Standard).
- Removed the card's full rules-text block from this screen only — still shown everywhere else in the app.
- Added a fullscreen popout button on the selected card's art, and fixed the fullscreen viewer not closing when clicking near (but not directly on) the card image.

### Deck Builder Layout
- Left column redesigned: **Change Legend** button (swap a deck's Legend without rebuilding it), a color-coded ownership breakdown (Fully Owned / Partially Owned / Missing), and a **View Analysis** button.
- Center deck list rows redesigned: circular ownership badges (red/orange/green), full-row background art, a hover preview popup near the cursor, and click-to-fullscreen.
- Deck list now has separate **Main Deck** / **Sideboard** tabs instead of one combined list with a side toggle.

### Discover / Add Cards Panel
- Cards with multiple print variants now show one row with a text-only variant strip beneath it (green = owned, red/orange caution icon = missing or short) instead of duplicate rows per print.
- Added pagination (10–100 per page) under the search bar.
- Refreshing the page now returns you to where you were instead of resetting to Vault.

### Export / Import
- Export now opens a preview window: switch between **RiftKeep** and **RiftAtlas** format on the left to preview the exact file contents, then **Export** (far right) to download.
- Added RiftAtlas as a second export/import format (`Legend:` / `Champion:` / `MainDeck:` / `Battlefields:` / `Runes:` / `Sideboard:` sections).
- Import now auto-detects RiftKeep- or RiftAtlas-formatted text per line (a paste can even mix both) and correctly sorts cards into Main Deck vs. Sideboard based on the section header, instead of dropping everything into Main Deck.

### Performance
- Adding/removing deck cards no longer redundantly re-fetches the full card catalog or deck detail — roughly halved the API calls per interaction, fixing the lag during rapid add/remove.
