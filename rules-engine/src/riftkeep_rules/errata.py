from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import fitz

WS_RE = re.compile(r"\s+")
VARIANT_SUFFIX_RE = re.compile(
    r"\s*\((?:alternate art|overnumbered|signature|metal|promo|showcase|launch exclusive|ultimate)\)\s*$",
    re.I,
)
SEP_RE = re.compile(r"\s*(?:[-–—]|,)\s*")


def _norm_text(value: str | None) -> str:
    s = unicodedata.normalize("NFKC", value or "")
    s = s.replace("’", "'").replace("‘", "'")
    return WS_RE.sub(" ", s).strip()


def canonical_card_identity(name: str | None) -> str:
    """Conservative gameplay-identity key used only to link errata to printings.

    Riot's card data mixes separators ("Janna - Savior") while official errata uses
    comma forms ("Janna, Savior"). Alternate/promo suffixes are printing metadata, not
    gameplay identity. We normalize only those known presentation differences.
    """
    s = _norm_text(name)
    s = VARIANT_SUFFIX_RE.sub("", s)
    s = SEP_RE.sub(" ", s)
    s = re.sub(r"[^\w'!]+", " ", s, flags=re.UNICODE)
    return WS_RE.sub(" ", s).strip().casefold()


def card_identity_aliases(name: str | None) -> set[str]:
    """Known alternate title forms used between the official card DB and errata docs.

    Older data often stores champion cards as ``Character - Subtitle`` while errata
    may identify the card only by ``Subtitle``. We expose the subtitle as an alias but
    use it only as a fallback when the alias resolves to one gameplay identity.
    """
    raw = _norm_text(name)
    aliases = {canonical_card_identity(raw)}
    stripped = VARIANT_SUFFIX_RE.sub("", raw)
    if " - " in stripped:
        _prefix, subtitle = stripped.split(" - ", 1)
        aliases.add(canonical_card_identity(subtitle))
    return {a for a in aliases if a}


def _page_lines(page: fitz.Page) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    data = page.get_text("dict")
    for block in data.get("blocks", []):
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            text = _norm_text("".join(str(s.get("text") or "") for s in spans))
            if not text:
                continue
            rows.append({
                "text": text,
                "size": max(float(s.get("size") or 0) for s in spans),
                "fonts": sorted({str(s.get("font") or "") for s in spans}),
                "bbox": list(line.get("bbox") or []),
            })
    rows.sort(key=lambda r: ((r.get("bbox") or [0, 0])[1], (r.get("bbox") or [0, 0])[0]))
    return rows


def parse_errata_pdf(
    path: Path,
    *,
    source_id: str,
    source_url: str,
    published: str,
    release_name: str,
) -> dict[str, Any]:
    """Parse Riot's official card-errata PDF layout without OCR.

    The current official errata PDFs use 20pt card headings and explicit [NEW TEXT] /
    [OLD TEXT] markers. The parser treats typography as structure and preserves the
    line ordering inside each text block. If that contract changes, validation fails
    rather than guessing.
    """
    raw = path.read_bytes()
    doc = fitz.open(path)
    entries: list[dict[str, Any]] = []
    section = None
    current: dict[str, Any] | None = None
    mode: str | None = None

    def finish() -> None:
        nonlocal current, mode
        if not current:
            return
        current["newText"] = "\n".join(current.pop("_new", [])).strip()
        current["oldText"] = "\n".join(current.pop("_old", [])).strip()
        current["identityKey"] = canonical_card_identity(current["cardName"])
        if current["newText"] or current["oldText"]:
            entries.append(current)
        current = None
        mode = None

    for page_no, page in enumerate(doc, start=1):
        for row in _page_lines(page):
            text = row["text"]
            size = row["size"]
            low = text.casefold()

            # Ignore document title/date and visual delimiter.
            if text == "Riftbound Card Errata" or low.startswith("last updated:") or text == "▲":
                continue

            if 19.0 <= size <= 21.5:
                if low.endswith(" cards"):
                    finish()
                    section = text[:-6].strip()
                    continue
                finish()
                current = {
                    "entryId": f"{source_id}:{len(entries)+1:03d}",
                    "sourceId": source_id,
                    "sourceUrl": source_url,
                    "sourceType": "card_errata",
                    "release": release_name,
                    "published": published,
                    "sectionSet": section,
                    "cardName": text,
                    "page": page_no,
                    "_new": [],
                    "_old": [],
                }
                continue

            if text == "[NEW TEXT]":
                mode = "new"
                continue
            if text == "[OLD TEXT]":
                mode = "old"
                continue
            if current and mode == "new":
                current["_new"].append(text)
            elif current and mode == "old":
                current["_old"].append(text)

    finish()
    return {
        "schemaVersion": 1,
        "sourceId": source_id,
        "sourceType": "card_errata",
        "sourceUrl": source_url,
        "release": release_name,
        "published": published,
        "localFile": str(path.name),
        "sourceSha256": hashlib.sha256(raw).hexdigest(),
        "entryCount": len(entries),
        "entries": entries,
    }


def load_structured_errata(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    for i, e in enumerate(obj.get("entries", []), start=1):
        e.setdefault("entryId", f"{obj.get('sourceId')}:{i:03d}")
        e.setdefault("sourceId", obj.get("sourceId"))
        e.setdefault("sourceUrl", obj.get("sourceUrl"))
        e.setdefault("sourceType", "card_errata")
        e.setdefault("published", obj.get("published"))
        e.setdefault("release", obj.get("release"))
        e["cardName"] = _norm_text(e.get("cardName"))
        e["newText"] = _norm_multiline(e.get("newText"))
        e["oldText"] = _norm_multiline(e.get("oldText"))
        e["identityKey"] = canonical_card_identity(e.get("cardName"))
    obj["entryCount"] = len(obj.get("entries", []))
    return obj


def _norm_multiline(value: str | None) -> str:
    if not value:
        return ""
    return "\n".join(_norm_text(line) for line in str(value).splitlines() if _norm_text(line))


def _date_key(value: str | None) -> tuple[int, int, int]:
    try:
        d = date.fromisoformat((value or "")[:10])
        return d.year, d.month, d.day
    except Exception:
        return (0, 0, 0)


def build_errata_history(
    cards: dict[str, Any],
    source_documents: list[dict[str, Any]],
) -> dict[str, Any]:
    """Link official errata events to card identities and apply the latest official text.

    No claim is made that OLD TEXT was physically printed on every matched promo/variant.
    The old/new pair is stored as rules-text history for the gameplay identity. Current
    effective text is sourced from the latest official errata event.
    """
    all_entries: list[dict[str, Any]] = []
    for doc in source_documents:
        all_entries.extend(doc.get("entries", []))
    all_entries.sort(key=lambda e: (_date_key(e.get("published")), str(e.get("entryId") or "")))

    cards_by_identity: dict[str, list[dict[str, Any]]] = defaultdict(list)
    cards_by_alias: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for card in cards.get("cards", []):
        full_key = canonical_card_identity(card.get("name"))
        cards_by_identity[full_key].append(card)
        for alias in card_identity_aliases(card.get("name")):
            cards_by_alias[alias].append(card)

    # An alias is safe only if every matching printing points at the same full gameplay
    # identity. This prevents subtitle-only matching from silently crossing cards.
    safe_aliases: dict[str, list[dict[str, Any]]] = {}
    for alias, rows in cards_by_alias.items():
        fulls = {canonical_card_identity(c.get("name")) for c in rows}
        if len(fulls) == 1:
            safe_aliases[alias] = rows

    identity_events: dict[str, list[dict[str, Any]]] = defaultdict(list)
    resolved_key_map: dict[str, str] = {}
    unresolved: list[dict[str, Any]] = []
    for e in all_entries:
        source_key = str(e.get("identityKey") or canonical_card_identity(e.get("cardName")))
        key = source_key
        matches = cards_by_identity.get(key, [])
        match_method = "full_identity"
        if not matches and source_key in safe_aliases:
            matches = safe_aliases[source_key]
            key = canonical_card_identity(matches[0].get("name"))
            match_method = "unique_subtitle_alias"
        resolved_key_map[source_key] = key
        link = dict(e)
        link["matchedCardIds"] = sorted(str(c.get("id")) for c in matches if c.get("id"))
        link["matchedCardNames"] = sorted({str(c.get("name")) for c in matches if c.get("name")})
        link["matchCount"] = len(matches)
        link["matchMethod"] = match_method if matches else "unresolved"
        link["resolvedIdentityKey"] = key
        if not matches:
            unresolved.append(link)
        identity_events[str(key)].append(link)

    applied_cards = 0
    for key, matching_cards in cards_by_identity.items():
        timeline = identity_events.get(key, [])
        if not timeline:
            for c in matching_cards:
                c["officialErrataTimeline"] = []
            continue
        latest = sorted(timeline, key=lambda e: (_date_key(e.get("published")), str(e.get("entryId") or "")))[-1]
        for card in matching_cards:
            card["officialErrataTimeline"] = [
                {
                    "entryId": e.get("entryId"),
                    "sourceId": e.get("sourceId"),
                    "published": e.get("published"),
                    "release": e.get("release"),
                    "oldText": e.get("oldText"),
                    "newText": e.get("newText"),
                    "sourceUrl": e.get("sourceUrl"),
                    "page": e.get("page"),
                    "sectionSet": e.get("sectionSet"),
                }
                for e in timeline
            ]
            if latest.get("newText"):
                card["effectiveText"] = _norm_text(latest["newText"])
                card["textSource"] = f"official_errata:{latest.get('sourceId')}"
                card["effectiveTextProvenance"] = {
                    "sourceId": latest.get("sourceId"),
                    "entryId": latest.get("entryId"),
                    "published": latest.get("published"),
                    "sourceUrl": latest.get("sourceUrl"),
                }
                applied_cards += 1

    identities = []
    for key, timeline in sorted(identity_events.items()):
        matches = cards_by_identity.get(key, [])
        latest = sorted(timeline, key=lambda e: (_date_key(e.get("published")), str(e.get("entryId") or "")))[-1]
        identities.append({
            "identityKey": key,
            "canonicalErrataName": latest.get("cardName"),
            "matchedCardIds": sorted(str(c.get("id")) for c in matches if c.get("id")),
            "eventCount": len(timeline),
            "events": timeline,
            "currentOfficialText": latest.get("newText"),
            "currentTextSourceId": latest.get("sourceId"),
            "currentTextPublished": latest.get("published"),
        })

    return {
        "schemaVersion": 1,
        "sourceDocumentCount": len(source_documents),
        "errataEventCount": len(all_entries),
        "errataIdentityCount": len(identity_events),
        "matchedIdentityCount": sum(1 for key in identity_events if cards_by_identity.get(key)),
        "unresolvedIdentityCount": len(unresolved),
        "effectiveCardPrintingCount": applied_cards,
        "unresolved": unresolved,
        "sourceDocuments": [
            {
                "sourceId": d.get("sourceId"),
                "sourceUrl": d.get("sourceUrl"),
                "published": d.get("published"),
                "release": d.get("release"),
                "entryCount": d.get("entryCount", len(d.get("entries", []))),
                "sourceSha256": d.get("sourceSha256"),
                "localFile": d.get("localFile"),
                "ingestionMethod": d.get("ingestionMethod", "official_pdf_typography" if str(d.get("localFile") or "").endswith(".pdf") else "structured_official_web_snapshot"),
            }
            for d in source_documents
        ],
        "identities": identities,
    }


def load_official_errata_documents(root: Path) -> list[dict[str, Any]]:
    """Load every locally mirrored official errata source declared in the manifest.

    PDFs are parsed from their typography; structured snapshots are already-normalized
    source transcriptions. Missing files are simply not loaded here and are reported by
    authority coverage rather than silently invented.
    """
    manifest_path = root / "data/source/official_source_manifest.json"
    if not manifest_path.exists():
        return []
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    docs: list[dict[str, Any]] = []
    for src in manifest.get("sources", []):
        if src.get("type") != "card_errata":
            continue
        release = src.get("release") or str(src.get("id") or "").split("-errata", 1)[0].replace("-", " ").title()
        local_pdf = src.get("localSnapshot")
        local_struct = src.get("localStructuredSnapshot")
        if local_pdf:
            path = root / "data/source" / str(local_pdf)
            if path.exists() and path.suffix.lower() == ".pdf":
                docs.append(parse_errata_pdf(
                    path, source_id=str(src["id"]), source_url=str(src.get("url") or ""),
                    published=str(src.get("published") or ""), release_name=str(release),
                ))
        elif local_struct:
            path = root / "data/source" / str(local_struct)
            if path.exists():
                doc = load_structured_errata(path)
                doc.setdefault("release", release)
                docs.append(doc)
    docs.sort(key=lambda d: (_date_key(d.get("published")), str(d.get("sourceId") or "")))
    return docs


def validate_errata_history(history: dict[str, Any], expected_source_ids: set[str] | None = None) -> dict[str, Any]:
    failures: list[str] = []
    source_ids = {str(x.get("sourceId")) for x in history.get("sourceDocuments", []) if x.get("sourceId")}
    if expected_source_ids is not None:
        missing = sorted(expected_source_ids - source_ids)
        if missing:
            failures.append(f"missing declared errata sources: {missing}")
    if not history.get("sourceDocumentCount"):
        failures.append("no official errata source documents loaded")
    if history.get("unresolvedIdentityCount"):
        failures.append(f"unresolved errata identities: {history.get('unresolvedIdentityCount')}")
    entry_ids: list[str] = []
    for identity in history.get("identities", []):
        if not identity.get("currentOfficialText"):
            failures.append(f"missing current official text for {identity.get('canonicalErrataName')}")
        for event in identity.get("events", []):
            if event.get("entryId"):
                entry_ids.append(str(event["entryId"]))
    if len(entry_ids) != len(set(entry_ids)):
        failures.append("duplicate errata entry IDs detected")
    return {
        "passed": not failures,
        "failureCount": len(failures),
        "failures": failures,
        "sourceDocumentCount": history.get("sourceDocumentCount"),
        "errataEventCount": history.get("errataEventCount"),
        "errataIdentityCount": history.get("errataIdentityCount"),
        "matchedIdentityCount": history.get("matchedIdentityCount"),
        "effectiveCardPrintingCount": history.get("effectiveCardPrintingCount"),
        "sourceIds": sorted(source_ids),
    }

# ---------------------------------------------------------------------------
# Public compatibility/runtime API
# ---------------------------------------------------------------------------

def normalize_card_identity(name: str | None) -> str:
    return canonical_card_identity(name)


def _snapshot_to_errata_doc(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Parse a validated official HTML snapshot into old/new card-text records."""
    blocks = list(snapshot.get("blocks") or [])
    entries: list[dict[str, Any]] = []
    section_set: str | None = None
    current_name: str | None = None
    new_parts: list[str] = []
    old_parts: list[str] = []
    mode: str | None = None

    def finish() -> None:
        nonlocal current_name, new_parts, old_parts, mode
        if current_name and (new_parts or old_parts):
            entries.append({
                "sourceId": snapshot.get("sourceId"),
                "sourceUrl": snapshot.get("sourceUrl"),
                "sourceType": "card_errata",
                "published": snapshot.get("published") or snapshot.get("effectiveFrom"),
                "release": snapshot.get("title"),
                "sectionSet": section_set,
                "cardName": current_name,
                "newText": _norm_multiline("\n".join(new_parts)),
                "oldText": _norm_multiline("\n".join(old_parts)),
                "identityKey": canonical_card_identity(current_name),
            })
        current_name = None
        new_parts = []
        old_parts = []
        mode = None

    for b in blocks:
        kind = str(b.get("kind") or "")
        text = _norm_text(str(b.get("text") or ""))
        if not text:
            continue
        low = text.casefold().strip("# ")
        if kind == "heading":
            if low in {"[new text]", "new text"}:
                mode = "new"; continue
            if low in {"[old text]", "old text"}:
                mode = "old"; continue
            if text == "▲" or low in {"related articles"}:
                continue
            if low.endswith(" cards"):
                finish()
                section_set = text[:-6].strip()
                continue
            # Ignore page/article title; card headings are followed by NEW TEXT.
            # We can safely stage any non-title heading and only emit once markers appear.
            if text != snapshot.get("title"):
                finish()
                current_name = text
            continue
        if current_name and mode == "new":
            new_parts.append(text)
        elif current_name and mode == "old":
            old_parts.append(text)
    finish()

    for i, e in enumerate(entries, start=1):
        e["entryId"] = f"{snapshot.get('sourceId')}:{i:03d}"
    return {
        "schemaVersion": 1,
        "sourceId": snapshot.get("sourceId"),
        "sourceType": "card_errata",
        "sourceUrl": snapshot.get("sourceUrl"),
        "release": snapshot.get("title"),
        "published": snapshot.get("published") or snapshot.get("effectiveFrom"),
        "sourceSha256": snapshot.get("sha256"),
        "entryCount": len(entries),
        "ingestionMethod": "versioned_official_web_snapshot",
        "entries": entries,
    }


def _builtin_errata_documents(root: Path) -> list[dict[str, Any]]:
    source = root / "data/source"
    docs: list[dict[str, Any]] = []
    origins = source / "official_pdfs/origins_errata_2025-10-28.pdf"
    if origins.exists():
        docs.append(parse_errata_pdf(
            origins,
            source_id="origins-errata",
            source_url="https://playriftbound.com/en-us/news/rules-and-releases/riftbound-origins-card-errata/",
            published="2025-10-28",
            release_name="Origins",
        ))
    spirit = source / "official_pdfs/spiritforged_errata_2026-01-14.pdf"
    if spirit.exists():
        docs.append(parse_errata_pdf(
            spirit,
            source_id="spiritforged-errata",
            source_url="https://playriftbound.com/en-us/news/rules-and-releases/riftbound-spiritforged-errata/",
            published="2026-01-14",
            release_name="Spiritforged",
        ))
    for rel in [
        "official_structured/unleashed_errata_2026-04-03.json",
        "official_structured/vendetta_errata_2026-07-23.json",
    ]:
        p = source / rel
        if p.exists():
            docs.append(load_structured_errata(p))
    return docs


def compile_official_errata(root: Path) -> dict[str, Any]:
    """Compile current official errata history from local PDFs/structured snapshots.

    If a fully synced official web snapshot exists for a source, it supersedes the
    bootstrap/local representation for that same source ID. Historical events remain
    separate by release/source ID and are sorted chronologically.
    """
    by_source = {d["sourceId"]: d for d in _builtin_errata_documents(root)}
    try:
        from .official_sources import load_latest_snapshots
        for snap in load_latest_snapshots(root):
            if snap.get("sourceType") == "card_errata" and snap.get("validation", {}).get("passed", True):
                parsed = _snapshot_to_errata_doc(snap)
                if parsed.get("entryCount"):
                    by_source[str(parsed["sourceId"])] = parsed
    except Exception:
        # Static sources remain a valid offline baseline. Sync failures are reported by
        # authority status rather than making card-text compilation non-deterministic.
        pass

    docs = sorted(by_source.values(), key=lambda d: (_date_key(d.get("published")), str(d.get("sourceId") or "")))
    records = [dict(e) for d in docs for e in d.get("entries", []) if e.get("newText") and e.get("oldText")]
    invalid = [dict(e) for d in docs for e in d.get("entries", []) if not e.get("newText") or not e.get("oldText")]
    return {
        "schemaVersion": 1,
        "sourceDocumentCount": len(docs),
        "sourceDocuments": [{
            "sourceId": d.get("sourceId"), "sourceUrl": d.get("sourceUrl"),
            "published": d.get("published"), "release": d.get("release"),
            "entryCount": d.get("entryCount", len(d.get("entries", []))),
            "sourceSha256": d.get("sourceSha256"), "localFile": d.get("localFile"),
            "ingestionMethod": d.get("ingestionMethod", "official_pdf_typography" if str(d.get("localFile") or "").endswith(".pdf") else "structured_official_web_snapshot"),
        } for d in docs],
        "recordCount": len(records) + len(invalid),
        "validRecordCount": len(records),
        "invalidRecordCount": len(invalid),
        "records": records,
        "invalidRecords": invalid,
    }


def compiled_errata_documents(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """Rehydrate the source-document shape from a compiled errata bundle."""
    docs_by_id: dict[str, dict[str, Any]] = {
        str(d.get("sourceId")): dict(d) for d in bundle.get("sourceDocuments", [])
    }
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in bundle.get("records", []):
        grouped[str(r.get("sourceId"))].append(dict(r))
    docs: list[dict[str, Any]] = []
    for sid, rows in grouped.items():
        meta = docs_by_id.get(sid, {})
        docs.append({**meta, "sourceId": sid, "entries": rows, "entryCount": len(rows)})
    docs.sort(key=lambda d: (_date_key(d.get("published")), str(d.get("sourceId") or "")))
    return docs


def build_compiled_errata_history(cards: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    return build_errata_history(cards, compiled_errata_documents(bundle))


def apply_official_errata(cards: dict[str, Any], bundle: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    history = build_compiled_errata_history(cards, bundle)

    # Compatibility field plus conservative proven-old-text attachment. OLD TEXT is
    # official historical rules text; this does not imply databaseText was the print.
    history_by_key = {i["identityKey"]: i for i in history.get("identities", [])}
    for card in cards.get("cards", []):
        key = canonical_card_identity(card.get("name"))
        identity = history_by_key.get(key)
        if identity is None:
            # Try safe subtitle alias through the already linked event IDs.
            linked = card.get("officialErrataTimeline") or []
        else:
            linked = card.get("officialErrataTimeline") or []
        card["officialErrataHistory"] = linked
        if linked and not card.get("knownPrintedText"):
            first_old = next((x.get("oldText") for x in linked if x.get("oldText")), None)
            if first_old:
                card["knownPrintedText"] = _norm_text(first_old)

    report = {
        "passed": history.get("unresolvedIdentityCount", 0) == 0 and bundle.get("invalidRecordCount", 0) == 0,
        "records": bundle.get("recordCount", 0),
        "validRecords": bundle.get("validRecordCount", 0),
        "cardsAffected": history.get("effectiveCardPrintingCount", 0),
        "identitiesAffected": history.get("errataIdentityCount", 0),
        "unresolvedIdentityCount": history.get("unresolvedIdentityCount", 0),
        "unresolved": history.get("unresolved", []),
        "sourceDocumentCount": history.get("sourceDocumentCount", 0),
    }
    cards.setdefault("metadata", {})["officialErrata"] = report
    return cards, report
