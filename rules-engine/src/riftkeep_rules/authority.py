from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _has_ingested_snapshot(root: Path, source_id: str) -> bool:
    latest = root / "data/source/snapshots" / source_id / "latest.json"
    if not latest.exists():
        return False
    try:
        ptr = json.loads(latest.read_text(encoding="utf-8"))
        record = root / ptr.get("snapshotRecord", "")
        if not record.exists():
            return False
        snap = json.loads(record.read_text(encoding="utf-8"))
        return bool(snap.get("sections")) and snap.get("sourceId") == source_id and bool((snap.get("validation") or {}).get("passed", True))
    except Exception:
        return False



def _source_locally_ingested(root: Path, source: dict[str, Any]) -> bool:
    if _has_ingested_snapshot(root, str(source.get("id") or "")):
        return True
    for key in ("localSnapshot", "localStructuredSnapshot"):
        rel = source.get(key)
        if rel and (root / "data/source" / str(rel)).exists():
            return True
    return False

def _local_exists(root: Path, rel: str | None) -> bool:
    return bool(rel) and (root / "data/source" / str(rel)).exists()


def _source_material_available(root: Path, source: dict[str, Any]) -> bool:
    """A source family can be complete from a versioned web snapshot or an audited
    local PDF/structured extraction. Metadata-only registrations never count.
    """
    sid = str(source.get("id") or "")
    if sid and _has_ingested_snapshot(root, sid):
        return True
    return _local_exists(root, source.get("localSnapshot")) or _local_exists(root, source.get("localStructuredSnapshot"))


def _coverage(status: str, complete: bool, missing: list[dict[str, Any]], note: str) -> dict[str, Any]:
    return {"status": status if complete else "partial", "complete": complete, "missing": missing, "note": note}


def load_authority_status(root: Path) -> dict[str, Any]:
    manifest_path = root / "data/source/official_source_manifest.json"
    if not manifest_path.exists():
        return {"status": "missing_manifest", "currentRulesComplete": False, "missing": [str(manifest_path)], "coverage": {}}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sources = list(manifest.get("sources", []))

    active_overlays = [s for s in sources if s.get("status") == "current_overlay"]
    ingested_overlays = [s["id"] for s in active_overlays if _has_ingested_snapshot(root, s["id"])]

    current_core = next((s for s in sources if s.get("type") == "core_rules_pdf" and s.get("status") == "current"), None)
    current_tr = next((s for s in sources if s.get("type") == "tournament_rules_pdf" and s.get("status") == "current"), None)
    hub = next((s for s in sources if s.get("type") == "rules_hub" and s.get("status") == "current_index"), None)

    game_missing: list[dict[str, Any]] = []
    if current_core is None or not _local_exists(root, current_core.get("localSnapshot") if current_core else None):
        game_missing.append({"sourceId": current_core.get("id") if current_core else None, "reason": "current Core Rules PDF snapshot missing"})
    for s in active_overlays:
        if not _has_ingested_snapshot(root, s["id"]):
            game_missing.append({"sourceId": s["id"], "reason": "active authority overlay body is not locally ingested"})

    tr_missing: list[dict[str, Any]] = []
    if current_tr is None or not _local_exists(root, current_tr.get("localSnapshot") if current_tr else None):
        tr_missing.append({"sourceId": current_tr.get("id") if current_tr else None, "reason": "current Tournament Rules PDF snapshot missing"})

    legality_missing: list[dict[str, Any]] = []
    if hub is None or not _local_exists(root, hub.get("localStructuredSnapshot") if hub else None):
        legality_missing.append({"sourceId": hub.get("id") if hub else None, "reason": "current Rules Hub legality snapshot missing"})

    cards_missing = [] if (root / "data/source/riftbound_cards.json").exists() else [{"sourceId": "cards-database-snapshot", "reason": "card database snapshot missing"}]

    errata_sources = [s for s in sources if s.get("type") == "card_errata" and s.get("status") in {"active_history", "current"}]
    errata_missing = [{"sourceId": s["id"], "reason": "official errata body not locally ingested"} for s in errata_sources if not _source_locally_ingested(root, s)]

    patch_sources = [s for s in sources if s.get("type") == "patch_notes"]
    patch_missing = [{"sourceId": s["id"], "reason": "patch-note body not locally ingested"} for s in patch_sources if not _has_ingested_snapshot(root, s["id"])]

    historical_faqs = [s for s in sources if s.get("type") == "official_faq" and s.get("status") == "superseded_history"]
    faq_hist_missing = [{"sourceId": s["id"], "reason": "historical FAQ body not locally ingested"} for s in historical_faqs if not _has_ingested_snapshot(root, s["id"])]

    coverage = {
        "gameplayRulesCurrent": _coverage("complete", not game_missing, game_missing, "Current Core Rules plus every active official FAQ/rulings overlay."),
        "tournamentProcedureCurrent": _coverage("complete", not tr_missing, tr_missing, "Current Tournament Rules PDF."),
        "sanctionedFormatLegalityCurrent": _coverage("complete", not legality_missing, legality_missing, "Current structured snapshot from the official Rules Hub."),
        "cardDatabaseCurrentSnapshot": _coverage("available", not cards_missing, cards_missing, "User-supplied card database snapshot; current card text is kept separate from proven printed-history text."),
        "officialCardErrataHistory": _coverage("complete", not errata_missing, errata_missing, "All registered official errata pages mirrored and versioned."),
        "officialPatchNoteHistory": _coverage("complete", not patch_missing, patch_missing, "Patch notes are non-exhaustive change context; PDF-to-PDF diff remains authoritative for actual Core Rules changes."),
        "historicalFaqArchive": _coverage("complete", not faq_hist_missing, faq_hist_missing, "Superseded FAQs are historical evidence only and must not override current rules."),
    }

    missing = game_missing
    return {
        "status": "complete" if not missing else "partial",
        "currentRulesComplete": not missing,
        "activeOverlays": [s["id"] for s in active_overlays],
        "ingestedOverlays": ingested_overlays,
        "missing": missing,
        "coverage": coverage,
        "policy": "Current gameplay adjudication requires the current Core Rules and every active official overlay. Other source families report coverage independently rather than being collapsed into one boolean.",
    }
