# Changelog

## v1.27.13 — Ask Rules' local AI now reasons over system-picked evidence, not its own guesses

- Reworked how Ask Rules' local-AI tool agent decides what rule/card data to look at. It previously let the model invent its own free-text search queries — real testing caught it improvising an unsupported wildcard search that returned the wrong rule entirely for a real question. It now always gets the same carefully-ranked evidence the rest of Ask Rules already gathers (keyword, concept, and cross-reference matching), and can only ask follow-up questions by exact rule number or exact card name — never a guessed search term. Re-verified against the same real test questions used to build this feature; the previously-wrong answer is now correct, with no regressions on the ones that already worked.
- Added a curated ruling for "how many Legends can a deck have" (exactly one, per rule 103/103.1) — found missing while testing the above.

## v1.27.12 — Deck-code premade packs, Mass Add deck codes, fullscreen close-button fix

- Added three more premade Champion Deck packs — Shen (Vendetta), Zed (Vendetta), and Vex (Unleashed) — decoded from official RiftAtlas deck codes and cross-checked against the card catalog.
- Mass Add now recognizes a pasted RiftAtlas deck code (the same compact format Import Deck already accepts) and adds every card in it straight to your owned collection in one action, instead of only building a Deck.
- Fixed a real bug on mobile: the fullscreen card image viewer's close button could land underneath the browser's own URL bar and be unclickable. It was positioned `fixed` to the raw layout viewport, which is taller than the visible area whenever the browser's toolbar is showing; it's now positioned relative to the already viewport-corrected modal instead.

## v1.27.11 — Ask Rules: instant, verified answers for known rulings

- Ask Rules now checks a 154-entry table of hand-verified and community-reviewed rulings (real card interactions, keyword mechanics, and common misconceptions) before asking the local AI anything — a match answers instantly and correctly with no AI involved at all. Covers a wide range of real rules questions, including several that the AI had been getting inconsistently right or wrong. Anything not in that table still goes through the AI as before.

## v1.27.10 — Ask Rules: fixed a repetition bug in local AI answers

- Found and fixed a real bug where Ask Rules' local AI could occasionally get stuck repeating the same sentence or listing rule numbers over and over until it ran out of room to answer, instead of giving a normal response — caused by a repetition-penalty setting that was never actually being applied. Local AI answers should no longer do this.

## v1.27.9 — Trade All, Runes/Battlefields tradeable again, Test Draw modal sizing

- Mark for Trade no longer excludes Runes and Battlefields — that exclusion from a couple updates ago turned out to be unwanted; they're tradeable alongside the rest of the deck again.
- Trade Binder: added a Trade All button that confirms every card currently offered for trade in one action, instead of one card at a time.
- Test Draw's popup was still sized for the old 7-card draw, leaving a wide, mostly-empty box since it's only drawn 4 cards for a while now — it's properly sized to its content now.

## v1.27.8 — Fix the real cause of Acquired clicks not counting

- Found the actual bug behind last update's Acquired-button fix not being enough: the Deck Builder's Discover panel caches its card list to avoid re-fetching on every render, and every deck re-render was re-registering that stale cached list, silently reverting the ownership count an Acquired click had just correctly updated. A second (or third) click would then recompute the same target as before and do nothing. Collection changes now drop that cache so it always refetches fresh.

## v1.27.7 — Fix Acquired button not registering a second click

- The Deck Builder's new Acquired button (added last update) could silently do nothing on a second click for a card needing 2+ more copies — a click landing before the previous one's response came back read stale data and computed the same target quantity. The button now disables itself the instant it's clicked so every click is counted.

## v1.27.6 — Mass Add accepts deck exports; Acquired button in Deck Builder

- Mass Add now accepts a pasted RiftKeep deck export directly, not just a bare list of card codes — also fixed a real bug this surfaced where a comma in a card's own name (e.g. "Kennen, Keeper of Balance") split the line in half and caused a spurious parse error.
- Deck Builder: each card in the current deck now has an "Acquired" button next to its ownership badge when you don't own enough copies — one click adds 1 to your Vault.

## v1.27.5 — Cheaper update checks

- Update checks (on load and the periodic background poll) now use conditional requests against GitHub — when nothing's changed since the last check, GitHub sends back an empty "not modified" response instead of the full release payload every time.

## v1.27.4 — Mark for Trade: honest messaging for unowned cards

- Fixed a follow-up to last update's Mark for Trade fix: a deck with cards you don't own at all got "0 updated" back from the server, which the toast then reported as "every card was already marked for trade" — false. It now correctly says how many cards aren't owned and can't be marked, instead of implying they were already handled.

## v1.27.3 — Update footer, refresh fixes, Mark for Trade fix, RiftKeep rename cleanup

- Fixed a real race condition affecting every collection-changing action (owned counts, favorites, decks, pack import/remove/undo, catalog refresh): the set-hero banner (Owned/Missing/Completion%) and the sidebar's per-set counts could render with pre-change numbers because the refresh ran before the new totals had finished loading. Reproduced directly with a pack import — now fixed everywhere the same pattern was used.
- Mark for Trade no longer flags Runes or Battlefields — they're separate resource pools, not part of the deck itself, same reasoning Test Draw already excludes them for.
- Trade Binder's Remove/Confirm Trade are now icon buttons (trash / repeat) instead of text.
- Removed the "Refresh Sets" sidebar icon — a heavy full catalog re-sync too easy to misclick from the front page. Settings → Catalog still has it.
- Replaced the old expanding "Updates" card in Settings with a footer that pops up on any page once an update is available, and stays permanently visible on Settings. "View Changelog" is now "View Patch Notes" and shows the full version history instead of just the latest release.
- Settings polish: API key inputs stretch full width instead of stopping at 360px, the top-row status cards share equal height, and Catalog shows per-set owned/total chips like the other cards already do.
- Finished a rename that was only partially done a while back — a handful of stray "Riftbound Vault" references (browser tab title, patch notes header, debug console, dev HTTPS cert, User-Agent strings) are now "RiftKeep" like everywhere else.

## v1.27.2 — Test Draw fix, mobile modal close button fix

- Test Draw no longer includes Battlefields (a separate pool, never drawn from the Main Deck — same reasoning Runes were already excluded for) and now draws 4 cards instead of 7.
- Fixed modal close buttons getting hidden behind the mobile browser's URL bar and becoming unreachable — every full-height modal now sizes against the real visible viewport instead of the browser's largest-possible one.

## v1.27.1 — Fix mobile Vault layout: no more horizontal scrolling

- Mass Add/Scan Card/Check Price/Import Pack and the All/Owned/Missing/Favorites tabs used to share one row you had to swipe sideways through on a phone. Split into a labelled Tools row above the tabs, and every row in the Vault toolbar now wraps instead of scrolling on narrow screens — tools, tabs, and rarity/type/domain filters all go multi-line, and the grid/list view toggle moved down to sit with Sort below the set banner. Desktop is unchanged.

## v1.27.0 — Reset Data: choose exactly what to wipe, catalog untouched

- New "Reset Data" card in Settings opens a checklist: Owned Collection, Trade Binder, Favorites, Card Notes, Decks, Price History, and Price Checker Queue. Check exactly what you want gone and type RESET to confirm — the card catalog itself is never touched, only the data you own.
- A full backup is taken automatically before anything is deleted, so a mistake has a real way back.

## v1.26.5 — Ask Rules: fix a ranking regression, help the model with negations

- Last update's multi-hop trace had a bug: a rule's score could grow unbounded from every cross-reference path that converged on it, so a heavily-cited "hub" rule with no real bearing on a question could outrank the rule that actually answers it. Caught on a real question about playing units to a battlefield you control — the deciding rule ranked 14th of 16 sources behind six unrelated hub rules. Capped how much score convergence alone can contribute, so citation-hub status can't beat a rule the question's own keywords or text matched directly.
- Even with the right evidence reaching the model intact, a rule built on a negated condition ("applies if the battlefield is NOT already Contested and you do NOT already control it") got read backwards, producing a confidently wrong answer. Added an explicit instruction for the model to work out which side of each "not" applies before answering — retested and the same question now answers correctly.

## v1.26.4 — Ask Rules: trace further, stop dropping found evidence

- The Tank question from the last update now retrieved the right rules but still gave a garbled, self-contradictory answer — because real evidence was being found and then silently thrown away before it ever reached the model. Two fixes: the cross-reference trace only followed one hop and discarded any reference back to a rule it already had instead of scoring it, and the evidence budget fed to the model (900 characters per rule, 5500 total) was too small for questions needing many rules. Cross-references now trace up to 3 hops with revisits boosting a rule's score instead of being ignored, the budget is roughly 60% bigger, and the model's context window was widened to match. The Tank question now answers cleanly with all 11 relevant rules cited.

## v1.26.3 — Restore the ability to re-download the Ask Rules model

- The button to re-download the Ask Rules model (e.g. to pick up an improved version) was lost when Ask Rules became multi-model-capable — once a model showed "In use" there was no action left on its row at all. Added the refresh icon back to any downloaded model, not just the selected one. Also fixed a bug this exposed: re-downloading a model while Local AI was already enabled silently kept using the old weights until an app restart, since the reload check only looked at the file path — it now also checks the file's write time, so a fresh download actually takes effect on your next question.

## v1.26.2 — Ask Rules: seed the rest of the official Keyword Glossary

- A real question about Tank ("do enemy spells have to target it first?") came back with no evidence found at all, even though the rules that answer it are indexed and searchable directly. The hand-curated list Ask Rules uses to recognize keywords in a question only had 6 of the game's 25 official Keyword Glossary keywords in it — added the other 19 (Tank, Shield, Assault, Backline, Equip, Level, Flow, and more). Takes effect the next time you run a Rules sync from Settings.

## v1.26.1 — Fix Check Price missing on mobile

- Check Price lived in the top bar next to Connect, which is fully hidden (not just its label) below 720px since Connect is a desktop-only "scan this QR from your phone" feature — Check Price got hidden along with it. Moved it into the Vault tab's action row next to Scan Card, where it stays reachable at every screen width, same as Scan Card and Import Pack already are.

## v1.26.0 — Check Price, trade workflow, and Test Draw fix

- New "Check Price" button next to Connect: scan a card (live camera, photo, or manual lookup) to look up its market price without adding it to your collection. Opens the card's detail panel with a price history graph (low/average/high and period change over the last 90 days) alongside the existing current-price and 24hr/7-day change figures.
- Test Draw no longer pulls Runes into the hand — they're a separate resource played from their own Rune Deck and are never drawn alongside Main Deck cards in real play.
- Vault: Import Pack's preview panel now has a Remove button alongside Import, subtracting that pack's card list from your collection (safely clamped to 0) — unlike Undo, this works from Vault at any time, not just right after importing.
- Deck view: new "Mark for Trade" button flags every card the deck uses as available in the Trade Binder in one click.
- Trade Binder: a new Confirm Trade action removes a card from your collection entirely once a trade actually completes, distinct from the existing Remove (which only un-flags it as tradeable but keeps it owned).

## v1.25.0 — Remote access over the internet (ngrok)

- The Connect popup now has a LAN | WAN toggle. LAN is the existing same-Wi-Fi QR/URL, unchanged. WAN creates a temporary public link to the app using ngrok, reachable from anywhere — not just your home network — with the same QR/URL to scan or copy.
- This is opt-in and never starts on its own: press Start each time you want it, and a clear warning stays on screen the whole time a tunnel is active, since anyone with the link can open your vault (there's no login on this app yet).
- If ngrok isn't installed, the popup walks through the setup instead of just failing — download, sign up, one command to add your auth token, then come back and press Start.

## v1.24.2 — Pulled the Qwen3 model option

- Removed Qwen3 1.7B from Ask Rules' model list. A real question ("does damage reduce my unit's Might, or get tracked separately?") reproducibly got an incoherent, self-contradictory answer from it even when the right rules were already found — the earlier testing that called it stable didn't cover this. Anyone who had it selected reverts to the default Qwen2.5 model automatically. Qwen2.5 remains the only option for now.

## v1.24.1 — Ask Rules: card evidence priority, better name matching, retrained Qwen3

- A question naming a specific card could lose that card's own evidence entirely if enough other rule evidence also matched — the shared evidence budget was filled by general rules first, sometimes before ever reaching the card's own text. Card evidence is now assembled first, every time.
- Free-text card questions now match names without punctuation too ("Darius Trifarian" now finds the card "Darius - Trifarian"), not just the exact or comma/dash-swapped spelling.
- Retrained the Qwen3 1.7B option: fixed a leaked `<think>` tag showing up at the start of answers, and fixed a card with more than one type of evidence (its own text plus a ban or errata) getting its raw evidence dumped back almost verbatim instead of a real answer.

## v1.24.0 — Retrained Ask Rules model + a second model option

- Fully retrained the Ask Rules local model from scratch on a corrected training set — the old training data didn't include a card's own printed text as evidence at all, which was the root cause of cards with no ban/errata history (e.g. Arena Kingpin, Blazing Scorcher) getting a non-answer instead of a real description of what they do. Verified against a wide battery of real cards and rules questions with no regressions.
- Settings → Ask Rules now shows a list of local models instead of one fixed one — Qwen2.5 1.5B (the original, still the default) and a new Qwen3 1.7B option, a newer-generation model that benchmarks ahead of it. Each downloads independently, and switching between ones you've already downloaded is instant.

## v1.23.1 — Ask Rules: card evidence + a context-overflow bug from v1.23.0

- Asking Ask Rules about a specific card by name (e.g. "the rules of Arena Kingpin") could come back with "I didn't find any official rule..." even for a real card, if that card had no ban/errata history — its own printed text was never used as evidence. It is now, run through the same symbol translator the rest of the app uses so the local model sees "Exhaust" instead of a raw `:rb_exhaust:` token.
- Fixed a bug from v1.23.0: broad questions (e.g. "How does Exhaust work?") could silently return no answer at all. A Patch Notes article is indexed as one whole-section block and one such entry was 27,000+ characters as a single piece of evidence — enough on its own to overflow the local model's context window. Evidence sent to the model is now bounded per-item and in total.

## v1.23.0 — Layout cleanup, Ask Rules evidence fixes

- Quick Add, Mass Add, Scan Card, and Import Pack moved off the top bar and onto the Vault tab, next to All Cards/Owned/Missing/Favorites; Quick Add itself was removed (Mass Add covers the same thing). The top bar now only holds the theme toggle and Connect, and the search box only shows on the Vault page.
- Settings: dropped the card backgrounds, removed the now-redundant Appearance and Phone Connection cards, gave Pricing and Community Data their own full-width rows, and pinned the Updates card to the bottom-left of the page so it stays in place while you scroll. Added a small dot next to the sidebar version number that lights up when an update is available (checked on load and every 5 minutes).
- Ask Rules' local AI explanations now get the full text of every cited rule instead of a 220-character preview, get the actual printed text of a card when you ask about it specifically (previously just its name), and pull in one hop of explicitly cross-referenced rules ("See rule 197...") that keyword/text matching alone would have missed.
- Rewrote the README to match the app as it exists today.

## v1.22.0 — Faster releases and updates

- The Ask Rules local AI model no longer ships inside the app itself — releases and self-updates used to bundle the same ~940MB model file every time, even for a one-line fix. It's now fetched separately (once, from Settings → Ask Rules, or automatically carried over from your existing install) and stored where app updates never touch it, so future releases and updates are dramatically smaller and faster.
- A "Download Model" step with live progress replaces "Enable" if the model isn't downloaded yet; a small refresh button lets you pick up a newer model later without waiting on an app update.

## v1.21.1 — Settings layout follow-up

- Settings now groups cards into three deliberate rows (system/device status, sync/version, then a dedicated full-width band for Pricing and Community Data) instead of an open masonry pack — same compact idea, more predictable grouping.

## v1.21.0 — Import Pack confirmation step, Settings masonry, real update progress

- Import Pack is now a proper preview-then-confirm flow: clicking a pack no longer adds it immediately — it opens a preview panel with a fixed header showing the pack name, a per-type card count (Legend/Champion/Unit/Spell/Gear/Battlefield/Rune) using Riftbound's own symbols, and an **Import** button that's the actual confirmation step.
- Settings is now a compact multi-column card layout instead of one long scrolling list — short sections pack several per row automatically, collapsing back to one column on narrow windows.
- **Update and Restart** now shows real progress — a live percentage and progress bar through downloading, extracting, and restarting — instead of going silent for however long the ~1GB download takes.

## v1.20.0 — Import Pack undo + preview, Settings cleanup

- Import Pack now shows a right-side preview panel with every card from the pack — art thumbnail, fullscreen button, name/type/set-code/quantity — and an **Undo** button next to the result to reverse the import in one click.
- Moved the **Ask Rules (Local AI)** toggle from Settings to the Rules page itself (right above the question input), since it's only ever relevant there.
- Settings: added an "APIs" group label above Pricing and Community Data to visually separate the two sections that need an API key from the sync/system sections around them.

## v1.19.0 — Import Pack, RiftAtlas deck codes, rule detail popups

- New **Import Pack** button (next to Quick Add/Mass Add/Scan Card) adds every card from an official preconstructed Champion Deck to your tracked collection in one click, on top of whatever you already own. Ships with all 5 Champion Decks (Viktor, Jinx, Lee Sin, Vi, Fiora) and all 4 Origins: Proving Grounds starter decks (Annie, Garen, Lux, Master Yi).
- Import Deck now accepts a RiftAtlas/Piltover Archive **deck code** (the compact string those tools generate for sharing a deck) — pasted in directly, auto-detected, no format picker needed.
- Clicking a cited rule in Ask Rules' "Why?" evidence list now opens its full text and keywords in a popup instead of requiring a trip to the Rules tab and a manual re-search.
- Fixed a gap where "my unit died" questions in Ask Rules couldn't find the rule that actually covers it (a unit dying and going to the trash).
- Deck import name-matching is a bit more forgiving: added a fallback for decklists that write a card as "Name, Cardname" where only the part after the comma is the card's real name.

## v1.18.1 — Deck import shows exactly which lines failed

- Import Deck's "X lines did not match" message now lists each unmatched line so you can see exactly what to fix, instead of just a count.

## v1.18.0 — Fine-tuned Ask Rules model + card legality/errata questions

- The local Ask Rules model is now fine-tuned on Riftbound's own rules, keywords, and card data (not the generic base model) — trained on real examples generated from the synced rules library, including how to answer a specific format when a card has more than one legality ruling (e.g. banned in both Constructed and 2v2 Constructed).
- Ask Rules can now answer questions about a specific card's ban status or errata history (e.g. "Is Called Shot banned in Constructed?", "Has Draven, Vanquisher received any errata?") — previously that data existed in the app but Ask Rules had no way to find it for a free-text question.
- Training scripts are included (`scripts/training/`) so the model can be retrained later as the rules library grows.

## v1.17.0 — Fully local Ask Rules AI

- Replaced the third-party AI option with a small language model that ships with the app and runs entirely on your machine — no account, no API key, no data ever leaves your PC. Settings → Ask Rules (Local AI) is now a single on/off toggle instead of endpoint/key configuration.
- Off by default (loading the model uses about 1GB of memory and takes a few seconds per question) — turn it on any time from Settings.

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
