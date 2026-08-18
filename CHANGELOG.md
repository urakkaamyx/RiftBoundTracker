# Changelog

## v1.16.0 — Ask Rules

- The Rules tab now has an **Ask Rules** mode alongside search: ask a rules question in plain English and get back the real official rules that answer it, ranked with a confidence level (High/Medium/Low/Insufficient Evidence) based on how directly the evidence covers your question.
- Understands official keywords, player slang ("tap" → Exhaust), and broader concepts your question implies even without the exact term ("my unit dies" → Unit Death, Leaving Battlefield) — every answer shows exactly which rules it drew from and why.
- Never invents a ruling: with no AI configured, it shows the most relevant official rule text directly; nothing is fabricated either way.
- New optional Settings section, **Ask Rules (AI Explanations)** — off by default. Point it at any OpenAI-compatible endpoint (OpenAI itself, or a local model server like Ollama/LM Studio) with your own key to get a written-out plain-language summary on top of the same rules evidence. Nothing is sent anywhere unless you configure this yourself.

## v1.15.0 — Rules library

- New **Rules** tab: a searchable, locally-indexed copy of Riftbound's official Core Rules, Tournament Rules, card errata, and format legality/banned list — pulled from playriftbound.com and kept entirely offline afterward.
- Search by rule number ("103.2.b"), official keyword ("exhaust"), player slang ("tap" finds Exhaust), or free text — results rank current Core Rules above historical material, never the reverse.
- Rule detail view shows the rule's own text, its place in the rule hierarchy (parent/children, previous/next), explicit cross-references ("See rule 197..."), and which official keywords it touches.
- Keyword glossary: every official keyword's canonical rule, aliases, every rule that mentions it, and every local card whose text uses it.
- Errata and Banned Cards browsers show real official corrections and ban lists, cross-linked to local card names where they resolve.
- New Settings section: **Rules Library** — manual "Sync Now" button (nothing syncs automatically), with last-synced time and rule/keyword/errata/legality counts.

## v1.14.2 — RiftDecks import support

- Import now handles RiftDecks-style decklists (plain "{qty} {name}" lines with no set/collector code), resolving cards by exact name and always preferring the base print over a variant when a name is ambiguous.
- Fixed a name-resolution gap where "Champion, Title" cards fail to match when the decklist and our catalog disagree on comma vs. dash as the separator (e.g. "Nocturne, Horrifying" vs. "Nocturne - Horrifying") — now retried automatically with the separator swapped.
- Simplified the Import modal: removed the RiftKeep/RiftAtlas format buttons since import already auto-detects the format per line.

## v1.14.1 — Sidebar cleanup

- Removed the redundant RIFTKEEP logo/text block from the top of the sidebar (the launch screen already carries the branding) — the nav list now starts right at the top.
- Renamed the title bar, taskbar tooltip, and tray menu from "RiftBound Vault" to "RiftKeep".

## v1.14.0 — RiftKeep branding, custom app chrome, launch screen

- New logo and "RIFTKEEP" branding in the sidebar, browser tab icon, and taskbar/window icon.
- Replaced the native Windows title bar with a custom dark/gold one (minimize, maximize/restore, close) — the app now opens maximized by default.
- Added a launch screen: the full RiftKeep emblem on its own transparent, borderless window with an "Enter Vault" button. Clicking it plays a zoom-through-the-gate transition into the main window (drop a `wwwroot/sounds/door-open.mp3` or `.wav` in to add a sound — none is bundled yet).

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
