# Changelog

## v1.30.0 — Emulator: real Damage and Kill

- Added a Deal Damage tool that can target any unit on the board, yours or an opponent's. Damage is marked on the unit (shown as a red badge, e.g. "3/4") rather than reducing its stats directly, and the moment marked damage reaches its Might, it's Killed — moved straight to its controller's Trash, automatically. Damage heals off a unit at the end of its controller's turn, so it doesn't carry over.
- This is a real combat primitive (Core Rules 142/428), not yet full Combat - there's still no Attacker/Defender designation, Battlefield-location control, or automatic damage from units fighting each other. For now, damage is something a player assigns by hand, same as everything else Phase 2 hasn't automated yet.

## v1.29.9 — Emulator: Ready/Exhausted units, layout fix

- Units on the Board and at Battlefields now have real Ready/Exhausted state, matching how the physical game actually works: a unit you play enters ready, click it to exhaust or ready it by hand, and every unit you control readies automatically at the start of your turn. An exhausted unit tilts and dims so it reads at a glance. This is genuine foundational groundwork - several keywords (Accelerate, Equip, Weaponmaster, and others) key off Ready/Exhausted, and none of those are wired up yet.
- Your own player card now stretches the full width of the board instead of being capped and centered, matching your opponent's.

## v1.29.8 — Fix: ornate frame ballooning on tall cards

- The gold frame around each player card was stretching to the card's exact size, which blew the corner scrollwork up to a huge size on a tall card (a full hand plus the move tool and counters) and covered the controls underneath. The corners now stay a fixed size no matter how tall the card gets — only the thin connecting edge lines stretch.

## v1.29.7 — Emulator: real illustrated art

- Replaced the plain CSS gradients and placeholder circles with actual illustrated art: a moody mountain-vista backdrop behind each side of the battlefield (your side and your opponent's are tinted differently so they read apart at a glance), an ornate gold filigree frame around every player card, a real engraved rune card-back on every deck pile, a gold ring frame around each Legend portrait, and real glowing glyph icons for the six Domain pips instead of plain colored dots.

## v1.29.6 — Emulator: never on mobile, launches in its own window, real stat block

- The Emulator is now completely inaccessible on a phone-sized screen — the nav item, the RiftCode gate, all of it. This also applies live if you shrink a desktop window narrow enough, not just an actual phone.
- Hosting or joining now opens the board in its own window instead of taking over the one you were browsing the vault in, so the vault stays where you left it.
- Redesigned the player card: a circular Legend portrait with a Might badge, a real Energy/Runes stat readout, and a live Domain-colored pip row for the runes currently in your Base. The Victory Score track moved out of the header into its own strip down the edge of the card — on the opponent's side it's upside down along with the rest of their card, same as everything else about them.

## v1.29.5 — Emulator: match log

- Added a live match log next to the board — every draw, channel, exhaust, recycle, play, move, score change, ready-up, and turn pass shows up there with a timestamp as it happens, newest on top. Never reveals what's actually in anyone's hand, only that something moved.

## v1.29.4 — Emulator: across-the-table layout, Spells go to the Trash

- The board is no longer a side-by-side split — your opponent's side sits upside down at the top of the table, and your own side is right-way up at the bottom, same as sitting across a real table from them.
- Playing a Spell now sends it to the Trash once it resolves instead of leaving it on the Board — Units and Gear still stay in play.

## v1.29.3 — Emulator: Playing a card actually costs Energy, plus Score

- Hand cards now have a real Play button showing their Energy cost — playing one pays that cost out of your current Energy and moves it to Board, and it's disabled (with a reason) when you can't afford it yet. The old free drag-to-Board move no longer works for Hand specifically, since that's Playing a Card, not a shuffle between zones.
- Added a Score counter next to your name (★ x/8, matching the default Victory Score) with its own +/- buttons — can't go below 0. Reaching 8 doesn't end the room (Conquer/Hold and combat still aren't modeled), but everyone gets a toast the moment someone crosses it.

## v1.29.2 — Emulator: real Energy/Power, automatic turn start

- Start of turn is now automatic, matching the real Setup/Turn sequence: your runes ready, you channel 2 from your Rune Deck, and you draw 1 — the moment your turn begins, not on manual clicks. Draw/Channel Rune are still there on their piles for an extra draw or rune beyond the automatic ones.
- Replaced the old "Rune Pool" card zone with what it's actually meant to be: channeled runes sit in your **Base** (still real, still visible to everyone), and Energy/Power are the numeric resource generated by *activating* one — exhaust a rune for +1 Energy, or recycle one back to your Rune Deck for +1 Power. Both show up as counters next to your name, same as Life. Everyone's unspent Energy/Power (and every rune's exhausted status) resets at the start of your turn, matching how it actually works — it doesn't bank between turns.

## v1.29.1 — Emulator: real battlefield layout

- The Emulator board now renders actual card art instead of plain text tiles — Battlefield, Board, Rune Pool, Trash, Banishment, and your own Hand all show real card images where the printing is known locally.
- Main Deck and Rune Deck are now stacked card-pile buttons (click to Draw/Channel) instead of a separate row of buttons, and each player's Champion Legend art shows next to their name.
- Life/score-style counters now show as pills next to the player's name instead of a separate list.
- The sidebar collapses to icons-only while a room's board is on screen, so the battlefield gets the width instead of sharing it with the vault navigation — restores automatically the moment you leave the room.

## v1.29.0 — Emulator: private online play with friends

- New "Emulator" feature: host or join a private room with your two friends over a live connection, reusing the existing Remote Access (ngrok) flow to expose a hosted room to the internet — whoever hosts runs it from their own copy of the app, no separate server involved.
- Locked behind a RiftCode: type the rune type for today (Fury, Calm, Order, Mind, Body, Chaos, or Colorless, cycling Sunday through Saturday) into the field next to Connect — only the three of you know the scheme. Checked server-side on every room action, not just in the browser, and only holds for the day it was entered — it resets at midnight, it isn't a permanent unlock.
- Deck legality is checked server-side before a deck can be selected for a room: exactly 1 Champion Legend, a 40+ card Main Deck, exactly 12 Rune Cards, at most 3 copies of any named card, at most 3 Signature cards.
- Starting a match shuffles each player's Main Deck and Rune Deck separately and deals an opening hand of 4, matching the real Setup Process. Draw and Channel Rune pull one card at a time from your own deck; a Move tool moves any of your own cards between Hand, Board, Battlefield, Trash, Banishment, and your Rune Pool. Hidden information is enforced on the server — your hand is never sent to anyone else's browser, only how many cards are in it.
- Not in this release: automatic cost/legality checking for individual plays, combat, the Chain/priority system, or any card-specific ability text. That's real rules automation and a much larger project on its own — this release is the shared board and hosting foundation it would sit on top of.

## v1.28.30 — Rules tab hidden again

Not quite right yet — back to hidden while it gets more work.

## v1.28.29 — Rules tab is back

Unhidden now that Ask Rules quality has caught up (see v1.28.28). Opens on Ask Rules by default — Search Rules is still on the old catalog and not yet wired to the new engine, so it's there if you want it but isn't the first thing you see.

## v1.28.28 — Ask Rules quality: points at rules-engine v1.0.6

The app now downloads rules-engine v1.0.6 (previously v1.0.5) the first time Ask Rules is used, or the next time the engine auto-updates for an existing install. That release fixes a family of bugs found by running a large external QA corpus against the engine: verbatim rule/card quotes were falling through to the wrong adjudicator instead of a direct lookup, two silent verification checks were downgrading correct answers back to "insufficient," and the deck-construction obligation detector was misfiring on incidental word co-occurrence (e.g. a question just listing "Rune Deck" as a zone name, with an unrelated "require" elsewhere in the sentence, used to get answered as if it were a rune-count question). Measured on QA-corpus samples: the two largest failure categories went from resolving correctly ~10-30% of the time to ~85-92%.

## v1.28.27 — Deck Builder: prices on Missing, cost breakdown, cheapest-printing swap

- The Missing tab now shows each card's market price alongside owned count, sourced from the same price cache the Estimated Missing Cost figure already used.
- Hovering Estimated Missing Cost shows every missing card and its cost, priciest first, in a compact one-line-per-card popup sized to fit without scrolling.
- Added "Replace All With Cheapest" next to Estimated Missing Cost (both the deck summary and Analysis tab) — for every missing line, swaps to whichever printing of that card would cost the least to finish the deck's required quantity (copies still needed after that printing's own owned count, times its price), not just the cheapest printing by sticker price alone. Reuses the same swap path the printing-picker popup uses, so nothing about deck legality changes.
- Also fixed the yellow alt-printing badge (v1.28.26) actually rendering grey — a more specific existing selector was winning the color; and the printing-swap popup's variant segments now show how many of each you own.

## v1.28.26 — Deck Builder flags cards where you own a different printing

- Each deck row now shows a small badge when you own a different printing of that card than the one in the deck — built from a base-name index over your owned cards, so you don't have to click into every line's Change Printing popup just to find out. Click the row same as before to switch.

## v1.28.25 — Deck Builder: deck-scoped Missing tab, click a card to change its printing

- The deck workspace's Missing discover tab now shows only the open deck's own unfulfilled lines instead of every not-owned card in the whole catalog — the catalog-wide "not owned anywhere" view is still there on the Vault page's own Missing filter, this was specifically about the deck you're actively building.
- Clicking a card in the deck's own card list now opens a popup to swap it for a different printing (same base-name variant grouping the Legend picker already used, generalized to any card) instead of opening a full-screen image — reuses SetCardAsync's existing Legend cover-art reassignment, so swapping a Legend's own printing this way correctly updates the deck's cover art too, same as Change Legend already did.

## v1.28.24 — Foil pricing and selection across Mass Add and Scanner

- Mass Add now shows a live price per line, Foil by default, with a shiny toggle to switch to Normal — sourced from riftbound.gg, which already returns both prices per card; the pipeline just used to collapse them to one and discard the other, now it doesn't for this new bulk lookup path.
- Pasted decklists set the foil flag from the text itself instead of defaulting: a trailing "f" or "foil" on a line (after the quantity, if any — e.g. "Blazing Scorcher x3 foil") marks it Foil, its absence means Normal. The printing picker (for ambiguous same-name cards) carries the flag through even when it has to wait on your choice.
- Scanning a card to add it now opens a confirmation popup with the card's art/name and a Hologram checkbox, default off — since a physical scan is a genuine claim about the real card in hand, checking it actually marks the new copy as a Hologram (the counter added in v1.28.23), not just a price preference like Mass Add's toggle.

## v1.28.23 — Track how many of a card's copies are Hologram

- Added a Hologram counter to the card inspector, right next to Owned/Trade — since Hologram is a foil finish rather than its own separately-numbered printing, it's tracked as a sub-count of how many copies you own (not a separate card entry, unlike Alternate Art). Always clamped to your owned count in both directions: setting Hologram above what you own is capped, and lowering your owned count below your recorded Hologram count brings it down with it.

## v1.28.22 — Rules hidden for now

- Hid the Rules nav item while Keywords/Legality are still unimplemented and Ask Rules' answer quality gets more work — nothing removed, just tucked away until it's ready for regular use.

## v1.28.21 — Added the missing Spiritforged and Unleashed Runes

- Same underlying gap as the orphan token cards: riftcodex.com has no data at all for Spiritforged's or Unleashed's own Rune reprints (confirmed by querying it directly), even though they're real printed cards with real artwork. Added all 36 (6 domains × base/Alternate Art/Promo, across both sets) — real art fetched from the same source the token images use.
- Unlike orphan tokens, these are stored as ordinary cards, not set apart in the Tokens tab — they have real set data, so they count toward Spiritforged's and Unleashed's own totals and completion % like any other card (SFD 288→306, UNL 280→298).

## v1.28.20 — Collection export line format: qty, name, (id)

- `{qty} {Name} {SetId}-{Code}` → `{qty} {Name} ({SetId}-{Code})` for the RiftKeep collection export — matches riftbound.gg's expected format.

## v1.28.19 — Collection export (RiftKeep) line order changed to qty/name/id

- `{qty} {SetId}-{Code} {Name}` → `{qty} {Name} {SetId}-{Code}` for the RiftKeep collection export specifically — decks keep the old order since their import parser depends on the code coming right after the quantity.

## v1.28.18 — Export your entire collection (RiftKeep or RiftAtlas format)

- Added "Export Collection" to Settings — every card you own as a plain text file, in either RiftKeep's own format (grouped by set) or RiftAtlas's flat decklist format, reusing the same export UI and formats decks already export in. Orphan token cards are excluded, same as every other collection stat.

## v1.28.17 — Import Pack notification now shows real copy counts

- "Import Pack" only ever reported the number of *unique* cards added (e.g. "24 cards added"), never how many physical copies that actually meant — a 25-card deck with several 3-ofs was really adding 56 copies to your collection, silently. The notification (and Remove Pack's) now shows both: "25 unique cards (56 copies)."

## v1.28.16 — Fixed Mass Add: couldn't add a second, different printing of the same card

- First real bug caught by the new "Report a Bug" pipeline (issue #2): once you picked a printing for an ambiguous card name (e.g. two different arts of Dockside Butcher) from the live search dropdown, picking that same name again silently reused the first choice instead of showing the printing picker again — so a second, different variant of the same card could never be added. The "remember the answer" shortcut was meant for a bulk paste with the same card repeated on several lines, not for a deliberate second pick from the dropdown; it now only applies to the paste path.

## v1.28.15 — Fixed Errata (and any string-ID) result rows never being clickable

- Found the real cause behind Errata entries not responding to clicks: the shared result-list click handler ran every result ID through `Number(...)` before looking it up — correct for the legacy numeric rule/keyword IDs, but errata uses string IDs like "origins-errata:006", which `Number()` turns into `NaN`. Every click matched nothing and silently did nothing. Fixed to only coerce IDs for the kinds that actually use numeric ones.

## v1.28.14 — Rules Browser's Errata list is back

- Fixed a real gap left over since the rules-engine swap in v1.28.0: `/api/rules/keywords`, `/api/rules/errata`, and `/api/rules/legality` were never re-implemented on the new engine at all (documented at the time as "temporarily degraded," which never got a follow-up) — so the Rules Browser's Errata, Keywords, and Legality tabs were 404ing on every load.
- Errata is properly fixed: 63 real official errata entries, read from the rules engine's own canonical data (same file it already ships with — no new download), with 44 automatically matched to a real card in your catalog for a working detail link.
- Keywords and Legality don't have an equivalent bulk-list source in the engine yet (only single-item and search lookups exist there) — those two still show a clear "Could not load" message rather than a broken page, and are real follow-up work rather than something rushed through tonight.

## v1.28.13 — Only "orphan" tokens get their own tab — the rest still belong to their set

- The tokens that came through the normal riftcodex sync with real official set data (the three Recruits, Sprite, and Gold // Buff) were wrongly swept into the same "keep out of All Cards" treatment as the 12 hand-added orphan tokens (Brush, Baron Pit, etc., which have no real set data anywhere). Split the two apart with a new flag: only the 12 true orphans stay in their own Tokens tab and out of set/collection stats — the 5 with real set data are back to behaving like any other card in their set, contributing to All Cards, that set's completion %, and everything else, the same as before tokens existed as a separate concept in this app at all.

## v1.28.12 — Owned token copies now count toward "Total copies"

- v1.28.9 excluded token cards from every collection stat, which also silently dropped owned token copies out of "Total copies" (Analytics/Settings) — if you actually own some tokens, that's a real part of your collection size. Fixed by counting them there specifically, while leaving the sidebar's "X owned / Y cards" ratio and set completion % untouched, since tokens still aren't in that denominator — adding them to the numerator there would let "owned" exceed "total."

## v1.28.11 — Fixed Battlefield token orientation (Baron Pit, Brush)

- Baron Pit and Brush are Battlefield cards, which print landscape — but their seeded data never set that, so both were rendered as if portrait everywhere. Now correctly flip to fit the grid's portrait tile slots (matching how every other landscape card in the app already behaves) and show in their natural horizontal orientation on the card detail view.

## v1.28.10 — Token card artwork upgraded, and a wrong card code fixed

- Switched token card images from the League wiki (bot-walled, needed a browser-relay workaround, only had art for 9 of 12) to static.dotgg.gg — riftbound.gg's own card image CDN, directly reachable with a plain request. All 12 token cards now have real artwork, up from 9.
- Fixed a wrong collector code: Tentacle was seeded as VEN-T06 based on the wiki, which doesn't actually exist (confirmed — that code 404s). The real card is VEN-T03. The bad row is removed and replaced automatically on next launch, no action needed.

## v1.28.9 — Token cards moved to their own Vault tab

- Token cards no longer clutter the main All Cards / Owned / Missing grid — added a 5th Vault tab ("Tokens") so they're still fully searchable, ownable, and trackable, just kept separate from normal browsing. An explicit search (Mass Add, the Vault's own search box, etc.) still finds a token by name even from the regular tabs — only plain, unsearched browsing excludes them.
- Fixed token cards silently distorting collection stats: each set's completion %, the rarity/domain distribution charts, and total collection value were quietly counting tokens as if they were normal owned/missing prints. They're now excluded from every one of those calculations, with their own dedicated count instead.

## v1.28.8 — Added the missing token cards (Brush, Baron Pit, Mech, and 9 others)

- Riftbound's token cards are real printed cards, but riftcodex.com (the only data source cards are synced from) only carries the ones that happen to share their base set's normal numeric collector numbering — 4 tokens (3 Recruits + Sprite in Origins) were already tracked correctly; everything else uses special "T01"-style collector codes riftcodex's own API doesn't expose at all, confirmed by querying it directly. Added the 12 missing ones by hand: Mech, Sand Soldier (Spiritforged), Baron Pit, Bird, Brush, Buff, Gold, Reflection, XP Tracker (Unleashed), Empowered, Shadow Clone, Tentacle (Vendetta) — real card text pulled verbatim from the compiled rules engine's own Rule 187, not paraphrased.
- Found and fixed a real bug in the browser-relay fetch path while sourcing these cards' artwork: the existing binary-fetch helper read image responses as text and re-encoded them as UTF-8, which silently corrupts arbitrary binary data — every fetched image was coming back empty. Added a proper base64-safe binary fetch path; 9 of the 12 tokens now have their real card art (the remaining 3 have no image on record anywhere, so they're left honestly blank rather than faked).
- Verified end-to-end rather than just inserted: Mass Add's search, Single Add's exact set+code lookup, and owning a copy all round-trip correctly against the new cards. The Scanner's OCR code parser and deck export already handled letter-prefixed collector codes like "T03" by design — no changes needed there. The regular card sync only ever adds/updates by Id and never deletes what it doesn't recognize, so these entries are safe from being wiped by a future sync.

## v1.28.7 — Report a Bug: files a real GitHub Issue, plus a real logging system

- Added a "Report a Bug" button (bottom of the sidebar) that opens a form and files a real GitHub Issue directly — title, description, app version, OS, and a recent trace of what the app was doing, all attached automatically.
- Added a persisted rolling log file (`App_Data/logs/riftkeep.log`) covering both the backend and frontend (JS errors and unhandled promise rejections now get logged too) — previously the only way to see backend logs at all was `--debug-console`, which only showed anything if you remembered to launch with that flag *before* reproducing the problem. Every bug report now automatically includes a recent excerpt.
- The screenshot never travels through GitHub's issue-creation API — there's no way to attach a binary image to an issue through it regardless of token scope, that only exists behind GitHub's own website upload flow. Instead, submitting copies the screenshot to your clipboard and opens the new issue in your browser so a single paste drops it in as a comment. If you don't attach your own screenshot, one is captured automatically from the app's own window at submit time.
- The GitHub token used to file issues is scoped to Issues-write-only on this one repo and is never committed to source — it's stamped into the build at publish time from an environment variable, so the public repo's history never contains it.

## v1.28.6 — Mass Add rebuilt, plus a new "Add to Collection+" tabbed entry point

- Rebuilt Mass Add end-to-end: live per-line search with a grid-style dropdown (`[CardID] Card Name`), hover-to-preview big on the right with click-to-lock, inline and big-preview quantity steppers, and a scrollable error log for anything that failed to resolve instead of it silently vanishing into a stack of toasts.
- Fixed the real gap that prompted the rebuild: every network call in Mass Add — both the bulk-paste path and the final "Add to Collection" submit — is now its own try/catch, so one bad line or one failed card can no longer halt the rest of a batch.
- Added a printing picker: pasting or searching a card name that matches more than one real printing (e.g. two "Riptide Rex" reprints) now offers a picker instead of just erroring out, and repeat occurrences of the same card later in a paste reuse the earlier choice automatically. The big preview panel also gained a printing-switch strip and a "Not Owned" ribbon matching the existing Legend picker's look.
- Fixed duplicate entries silently failing to combine: adding a card already on the list now merges into that line's quantity instead of creating a second row, and reopening Mass Add after an accidental backdrop click or Escape no longer wipes an in-progress list.
- Replaced the separate Mass Add / Scan Card / Import Pack toolbar buttons with a single "Add to Collection+" button that opens one tabbed modal for all three (Check Price stays separate, since it never touches your collection).
- Fixed a real mobile layout bug: on narrow windows the new modal was capped at its desktop height and pinned to the bottom of the screen by the existing mobile bottom-sheet styling, leaving a large empty gap above it — it now fills the sheet the same way every other tall modal already does.

## v1.28.5 — Ask Rules: fixed the Brush/token fix actually applying to how you'd ask it

- Fixed a real gap in the previous token-catalog fix (v1.28.3): it only worked when phrased as a question ("what is X", "how do I play X"). A bare mention with no question phrase at all — "Brush", "Token Brush Card", just typing the name — never triggered the lookup at all despite the answer existing. Ask Rules now recognizes a question that's nothing but a known card/token/keyword name (after stripping words like "token"/"card"/"the") as a definition lookup on its own.

## v1.28.4 — Ask Rules: real local-AI wiring (experimental, off by default)

- Wired a real local LLM provider into Ask Rules' existing AI interpretation/explanation design, which had never actually been connected to a model since the engine swap earlier this release line — it's off by default, and enabling it requires an advanced manual setup (running a local OpenAI-compatible model server yourself). When enabled, the model can only emit output matching the exact expected shape (schema-constrained generation), and every verdict and citation is still checked exactly against the real deterministic answer no matter what the model produces — a bad response is discarded, never shown.
- Direct testing against a small local model caught it explaining Riftbound's own "Ganking" keyword using outside knowledge of an unrelated game's same-spelled slang term instead of the real supplied rule text — fluent, confidently wrong, and something no structural check can catch since it's about truth, not shape. Documented as an experimental limitation; this is why the feature ships off by default rather than on.

- Added definition-lookup coverage for every token type in Rule 187's catalog — Brush battlefield, Baron Pit battlefield, Recruit, Sprite, Sand Soldier, Mech, Gold gear, Reflection, Bird, Tentacle, and Shadow Clone. These are created by other cards' effects rather than played from your deck, and Ask Rules previously had no way to answer questions about any of them (e.g. "How do I play the Brush Battlefield card?" just declined, or a looser phrasing accidentally matched the generic Battlefield rules instead). Now correctly answers with the actual rule text for whichever token was asked about.
- "How do I play X?" / "How to play X?" is now recognized as a definition-lookup question when X is exactly one of these token names — since most things asked about this way aren't cards you play at all. Ordinary gameplay questions like "How do I play a unit to a battlefield I control?" are unaffected.

## v1.28.2 — Ask Rules engine now actually updates itself

- Fixed the real cause behind "I have no way to update the Rules Engine": once an engine version was installed, nothing ever checked whether it was still the version the app expected, so it kept running forever even after a newer one shipped — the update mechanism silently never fired. Ask Rules now checks the installed engine's version against what this app build expects, and automatically fetches and swaps in the right one (cleanly stopping the old one first) the next time you use Ask Rules — no manual reinstall needed. Verified end-to-end: an old install with no version marker was correctly detected as stale, swapped for the current engine, and answered correctly right after.

## v1.28.1 — Ask Rules: Attach/Exhausted question, and a real update-failure fix

- Fixed a real "Access to the path 'mupdfcpp64.dll' is denied" failure: updating the rules engine could fail if a sidecar process from a previous run of the app was still holding its files open, since nothing stopped that leftover process before overwriting its files. The updater now stops any running copy of the engine — including one left over from before the app was last restarted — before replacing its files.
- Added a compiled answer for Attach + Exhausted questions (e.g. "Can I attach gear to an exhausted unit?") — previously declined with no answer at all. Exhausted/Ready state doesn't prevent a card from being Attached or receiving an Attach action; cited to Rule 719.4 and 434.2.

## v1.28.0 — Ask Rules now runs on a real deterministic rules engine

- Replaced Ask Rules' entire retrieval+local-AI pipeline with the RiftKeep Rules Engine — a separately-developed, proof-verified deterministic rules compiler with a sealed LLM boundary (the model never sees authoritative rule/card text and never decides a verdict; any malformed output falls back to the deterministic answer). It runs locally as a sidecar process the app talks to over its own HTTP API, fetched on first use the same way the old local-AI model was — nothing changes in the base install size.
- Fixes the real failure this replacement was built to solve: a compound question about playing a unit directly to a battlefield you control, and whether that applies Contested status, now answers completely and correctly with cited rule text — this never answered right under the old system despite several rounds of targeted fixes.
- Every answer is now backed by 2,381 structurally-compiled Core Rules, 935 Tournament Rules, 1,304 cards, the current official FAQ, and all official errata — with proof-verified citations, and an honest "I can't determine this" instead of a guess whenever a topic isn't yet covered by a compiled rule.
- Plain "what does this card do" questions now resolve directly against the card's own official text, separately labeled from an adjudicated ruling so the two are never confused.
- The "browse rules" library pages (keyword glossary, document/errata/legality lists) are temporarily running in a reduced, degraded mode while they're migrated onto the new engine in a follow-up update — Ask Rules itself is fully switched over in this release.
- Fixed a real routing bug in the new engine: plain deck-building questions like "Can I play more than one Legend in my deck?" were getting misrouted into tournament/format-legality checking (because they contained "deck") and coming back with a blank or nonsensical answer. Tournament/format handling now only activates on explicit signals — "tournament," "Constructed," "sanctioned," "banned," and similar — never inferred from ordinary words like "deck," "legal," or "can I play."
- Ask Rules can now actually answer deck-construction questions instead of just declining them: Champion Legend count (exactly 1), Main Deck size (at least 40), same-named card copy limit (up to 3, including your Chosen Champion), Signature card limit (up to 3, matching Champion tag), and Rune Deck size (exactly 12) all resolve to a real, cited answer now. A "how many Battlefields do I need" question correctly asks which Mode of Play you're using instead of guessing.
- Added a **Tournament Rules** checkbox next to the Ask Rules question box. Checking it explicitly flags the question as tournament context (so "Is this legal?" gets checked against the ban list) instead of relying on guessing intent from wording.

## v1.27.16 — Ask Rules: fixed a real retrieval bug affecting the whole rules corpus

- Found and fixed the actual cause of a wrong Ask Rules answer (playing a unit directly to a battlefield you control was being misjudged as Contesting it): the system that tags each rule with the keywords it discusses only matched the exact bare word "Control" — missing "controls", "controller", "controlled" entirely. That's how real rule text almost always phrases it, so 149 of 239 rules substantively about Control (62%) were invisible to keyword-based search. Fixed for every keyword, not just Control, and re-verified against the full rules corpus with no new false matches.
- Added a "Valid Play Locations" concept so a question about playing directly to a battlefield (bypassing base) reliably surfaces the rule that actually answers it, the same mechanism already used for phrases like "my unit dies" reaching the right rule text.
- Raised Ask Rules' evidence limit (16 → 24) after finding that a heavily-tied, common-keyword topic could push a directly relevant rule out of consideration entirely, even after the fixes above.
- Added the exact combined ruling this bug was traced from — "can I play directly to a battlefield I control, bypassing base, and does that Contest it" (no, and no) — as a curated instant answer, since the underlying scoring tie-break for extremely common keyword pairs like Control+Battlefield is a deeper problem than today's fixes fully resolve on their own.

## v1.27.15 — Ask Rules: instant answers for deck construction

- Added curated, instant answers for deck construction — Domain Identity, Main Deck minimum size, Chosen Champion requirements, the 3-copy card limit, the 3-Signature-card limit, Rune Deck size, and Battlefield rules — each verified against the live rule text.

## v1.27.14 — Ask Rules: instant answers for the full keyword glossary, plus a new lookup tool

- Ask Rules' local AI can now ask what a Riftbound keyword or rules term means (e.g. "Tank", "Hunt") as a bounded lookup, on top of the exact rule-number and card-name lookups it already had — still no free-text search, just one more precise way to fill a real gap in what it was given.
- Added curated, instant answers for 23 of the 25 official keywords (Tank and Vision were already covered) — what each one is, how it works, when it applies, and why. Verified against the live rules text.
- Fixed a real gap in curated-answer matching: the single most natural way to ask about a keyword — "What does Tank do?" — was being rejected before it ever got compared to anything, because it reduces to one meaningful word after stripping filler like "what"/"does". This affected every existing single-keyword entry too (Exhaust, Ready, Counter, etc.), not just the new ones — all now match correctly.

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
