from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .parser import parse_numbered_pdf, validate_pdf_parse
from .versioning import compare_rule_versions
from .version_integrity import FAMILIES, current_manifest_source, ensure_version_ledgers, history_path, load_history, sha256_file, validate_rule_version_integrity
from .runtime_hardening import atomic_write_json


def _dump(path: Path, data: Any) -> None:
    atomic_write_json(path, data)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def stage_rules_update(root: Path, family: str, pdf: Path, source_id: str, effective_from: str | None = None) -> dict[str, Any]:
    if family not in FAMILIES:
        raise ValueError(f"unknown family: {family}")
    if not pdf.exists():
        raise FileNotFoundError(pdf)
    ensure_version_ledgers(root)
    integrity = validate_rule_version_integrity(root)
    if not integrity.get("passed"):
        raise RuntimeError("cannot stage update while current rule-version integrity is broken")
    cfg = FAMILIES[family]
    current = current_manifest_source(root, family)
    if source_id == current.get("id"):
        raise ValueError("new source-id must differ from the current source-id")
    old_doc = _read(root / "data/canonical" / cfg["canonicalFile"])
    new_doc = parse_numbered_pdf(pdf, source_id, cfg["stablePrefix"], cfg["title"])
    validation = validate_pdf_parse(pdf, new_doc)
    stage_dir = root / "data/source/rule_versions" / family / "staged" / source_id
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)
    staged_pdf = stage_dir / "source.pdf"
    shutil.copy2(pdf, staged_pdf)
    _dump(stage_dir / "parsed_rules.raw.json", new_doc)
    diff: dict[str, Any] | None = None
    status = "parse_validation_failed"
    if validation.get("passed"):
        diff = compare_rule_versions(old_doc, new_doc, stable_prefix=cfg["stablePrefix"])
        # The comparison is the only place allowed to inherit stable identities.
        promoted = dict(new_doc)
        promoted["rules"] = diff["promotedNewRules"]
        _dump(stage_dir / "parsed_rules.json", promoted)
        _dump(stage_dir / "diff.json", {k: v for k, v in diff.items() if k != "promotedNewRules"})
        status = "ready_for_promotion" if diff.get("safeToAutoPromote") else "review_required"
    stage = {
        "schemaVersion": 1,
        "family": family,
        "sourceId": source_id,
        "status": status,
        "stagedAt": _now(),
        "effectiveFrom": effective_from,
        "previousSourceId": current.get("id"),
        "sourceSha256": sha256_file(staged_pdf),
        "sourcePdf": str(staged_pdf.relative_to(root)),
        "validation": validation,
        "diff": {
            "changeCounts": (diff or {}).get("changeCounts", {}),
            "reviewRequiredCount": (diff or {}).get("reviewRequiredCount"),
            "unmatchedOldCount": (diff or {}).get("unmatchedOldCount"),
            "unmatchedNewCount": (diff or {}).get("unmatchedNewCount"),
            "safeToAutoPromote": (diff or {}).get("safeToAutoPromote", False),
        },
    }
    _dump(stage_dir / "stage.json", stage)
    return stage


def _expire_next_core_overlays(manifest: dict[str, Any], new_source_id: str, effective_from: str | None) -> list[str]:
    expired: list[str] = []
    for src in manifest.get("sources", []):
        if src.get("status") != "current_overlay":
            continue
        precedence = src.get("precedence") or {}
        if precedence.get("expiresWhen") != "next_core_rules_document_released":
            continue
        src["status"] = "superseded_history"
        src["effectiveUntil"] = effective_from
        src["supersededBy"] = new_source_id
        src["supersededReason"] = "Overlay metadata declared expiration when the next Core Rules document was released."
        expired.append(str(src.get("id")))
    return expired


def promote_staged_update(root: Path, family: str, source_id: str, approve_review: bool = False) -> dict[str, Any]:
    if family not in FAMILIES:
        raise ValueError(f"unknown family: {family}")
    cfg = FAMILIES[family]
    ensure_version_ledgers(root)
    integrity = validate_rule_version_integrity(root)
    if not integrity.get("passed"):
        raise RuntimeError("cannot promote while current rule-version integrity is broken")
    stage_dir = root / "data/source/rule_versions" / family / "staged" / source_id
    stage_path = stage_dir / "stage.json"
    parsed_path = stage_dir / "parsed_rules.json"
    diff_path = stage_dir / "diff.json"
    if not stage_path.exists() or not parsed_path.exists() or not diff_path.exists():
        raise FileNotFoundError("staged update is incomplete")
    stage = _read(stage_path)
    if not (stage.get("validation") or {}).get("passed"):
        raise RuntimeError("staged PDF did not pass independent parser validation")
    diff = _read(diff_path)
    unsafe = not bool(stage.get("diff", {}).get("safeToAutoPromote"))
    if unsafe and not approve_review:
        raise RuntimeError("staged update requires explicit review approval before promotion")

    manifest_path = root / "data/source/official_source_manifest.json"
    manifest = _read(manifest_path)
    old_src = current_manifest_source(root, family)
    old_id = str(old_src["id"])
    old_live = root / "data/source" / str(old_src.get("localSnapshot") or cfg["liveFile"])
    history = load_history(root, family)
    current_versions = [v for v in history.get("versions", []) if v.get("status") == "current"]
    if len(current_versions) != 1 or current_versions[0].get("sourceId") != old_id:
        raise RuntimeError("version ledger current source does not match manifest")

    old_dir = history_path(root, family).parent / old_id
    old_dir.mkdir(parents=True, exist_ok=True)
    archived_old_pdf = old_dir / "source.pdf"
    if not archived_old_pdf.exists():
        shutil.copy2(old_live, archived_old_pdf)
    if sha256_file(archived_old_pdf) != current_versions[0].get("sourceSha256"):
        raise RuntimeError("archived old PDF hash mismatch; refusing promotion")

    parsed = _read(parsed_path)
    new_dir = history_path(root, family).parent / source_id
    if new_dir.exists():
        raise RuntimeError(f"immutable version directory already exists: {new_dir}")
    new_dir.mkdir(parents=True)
    new_pdf = new_dir / "source.pdf"
    shutil.copy2(stage_dir / "source.pdf", new_pdf)
    new_parsed = new_dir / "parsed_rules.json"
    _dump(new_parsed, parsed)

    # Mutate manifest only after immutable new artifacts have been written.
    for src in manifest.get("sources", []):
        if src.get("type") == cfg["manifestType"] and src.get("status") == "current":
            src["status"] = "superseded_history"
            src["supersededBy"] = source_id
            src["effectiveUntil"] = stage.get("effectiveFrom")
    new_manifest_src = {
        "id": source_id,
        "type": cfg["manifestType"],
        "status": "current",
        "localSnapshot": cfg["liveFile"],
        "effectiveFrom": stage.get("effectiveFrom"),
        "authorityScope": list(old_src.get("authorityScope") or []),
        "previousSourceId": old_id,
        "sourceSha256": stage.get("sourceSha256"),
    }
    manifest.setdefault("sources", []).append(new_manifest_src)
    expired_overlays: list[str] = []
    if family == "core":
        expired_overlays = _expire_next_core_overlays(manifest, source_id, stage.get("effectiveFrom"))

    # Replace the live convenience PDF only through this promotion gate.
    staged_sha = str(stage["sourceSha256"])
    shutil.copy2(stage_dir / "source.pdf", old_live)
    if sha256_file(old_live) != staged_sha:
        raise RuntimeError("live PDF copy verification failed")

    # Update version history and version metadata.
    for v in history["versions"]:
        if v.get("status") == "current":
            v["status"] = "superseded"
            v["nextSourceId"] = source_id
            v["archivedSourcePdf"] = str(archived_old_pdf.relative_to(root))
    new_version = {
        "sourceId": source_id,
        "status": "current",
        "sourceSha256": staged_sha,
        "sourceFile": str(old_live.relative_to(root)),
        "archivedSourcePdf": str(new_pdf.relative_to(root)),
        "parsedRules": str(new_parsed.relative_to(root)),
        "ruleCount": len(parsed.get("rules", [])),
        "previousSourceId": old_id,
        "nextSourceId": None,
        "effectiveFrom": stage.get("effectiveFrom"),
        "promotedAt": _now(),
        "reviewApprovalRequired": unsafe,
        "reviewApproved": bool(approve_review),
        "changeCounts": diff.get("changeCounts", {}),
    }
    history["versions"].append(new_version)
    history["currentSourceId"] = source_id
    _dump(history_path(root, family), history)
    _dump(new_dir / "version.json", new_version)
    _dump(manifest_path, manifest)

    # The canonical artifact is updated immediately to the identity-preserving staged
    # parse. A normal build will independently parse the new live PDF again and verify
    # it against the ledger before rebuilding all downstream artifacts.
    _dump(root / "data/canonical" / cfg["canonicalFile"], parsed)
    stage["status"] = "promoted"
    stage["promotedAt"] = new_version["promotedAt"]
    stage["reviewApproved"] = bool(approve_review)
    _dump(stage_path, stage)
    return {
        "status": "promoted",
        "family": family,
        "sourceId": source_id,
        "previousSourceId": old_id,
        "expiredOverlays": expired_overlays,
        "reviewApproved": bool(approve_review),
        "changeCounts": diff.get("changeCounts", {}),
    }
