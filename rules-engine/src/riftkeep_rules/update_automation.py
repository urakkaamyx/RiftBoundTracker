from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .official_sources import (
    MAX_SOURCE_BYTES,
    import_official_snapshot,
    validate_official_url,
)
from .release_gate import run_release_gate, summarize_release_gate
from .rule_updates import promote_staged_update, stage_rules_update
from .runtime_hardening import atomic_write_json, atomic_write_text

SCHEMA_VERSION = 1
TX_BASE = Path("data/update_transactions")
SUPPORTED_KINDS = {"core_rules_pdf", "tournament_rules_pdf", "official_snapshot", "reviewed_file"}
RULE_FAMILY = {"core_rules_pdf": "core", "tournament_rules_pdf": "tournament"}
SOURCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
TX_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
MAX_PDF_BYTES = 64 * 1024 * 1024
MAX_REVIEWED_FILE_BYTES = 4 * 1024 * 1024
REVIEWED_FILE_TARGETS = {
    "data/source/official_ruling_catalog.json",
    "data/source/current_authority_overlay.json",
    "data/source/history_sync_plan.json",
}
ALLOWED_REGISTERED_TYPES = {"rules_hub", "official_faq", "patch_notes", "card_errata", "official_article"}
ALLOWED_REGISTERED_STATUSES = {"current_index", "current_overlay", "current_change_record", "active_history", "history", "superseded_history"}

GateRunner = Callable[[Path], dict[str, Any]]
Fetcher = Callable[[str, int], tuple[bytes, str]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dump(path: Path, data: Any) -> None:
    atomic_write_json(path, data)


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _seal_sidecar(path: Path) -> Path:
    sidecar = path.with_name(path.name + ".sha256")
    atomic_write_text(sidecar, f"{sha256_file(path)}  {path.name}\n")
    return sidecar


def _dump_sealed(path: Path, data: Any) -> None:
    _dump(path, data)
    _seal_sidecar(path)


def _read_sealed(path: Path) -> dict[str, Any]:
    sidecar = path.with_name(path.name + ".sha256")
    if not path.exists() or not sidecar.exists():
        raise RuntimeError(f"sealed transaction document missing: {path.name}")
    parts = sidecar.read_text(encoding="utf-8").strip().split()
    expected = parts[0] if parts else ""
    if not expected or expected != sha256_file(path):
        raise RuntimeError(f"sealed transaction document hash mismatch: {path.name}")
    return _read(path)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _manifest(root: Path) -> dict[str, Any]:
    return _read(root / "data/source/official_source_manifest.json")


def _manifest_source(root: Path, source_id: str) -> dict[str, Any] | None:
    return next((x for x in _manifest(root).get("sources", []) if str(x.get("id")) == source_id), None)


def _ignored_for_fingerprint(rel: str) -> bool:
    rel = rel.replace("\\", "/")
    if rel.startswith("data/update_transactions/"):
        return True
    if rel.startswith("data/validation/") or rel.startswith("data/index/") or rel.startswith("data/canonical/"):
        return True
    if "/__pycache__/" in f"/{rel}/" or rel.endswith((".pyc", ".pyo")):
        return True
    if rel.startswith(".git/"):
        return True
    return False


def project_fingerprint(root: Path) -> dict[str, Any]:
    """Fingerprint source/code inputs that define an update rehearsal baseline.

    Generated canonical/index/validation files and the transaction ledger itself are
    excluded so running tests or recording an approval cannot make its own transaction
    stale. Source history, snapshots, contracts, code, tests, gold fixtures and UI/API
    files are included.
    """
    root = Path(root).resolve()
    rows: list[dict[str, Any]] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = str(path.relative_to(root)).replace("\\", "/")
        if _ignored_for_fingerprint(rel):
            continue
        rows.append({"path": rel, "sha256": sha256_file(path), "bytes": path.stat().st_size})
    digest = hashlib.sha256()
    for row in rows:
        digest.update(row["path"].encode("utf-8")); digest.update(b"\0")
        digest.update(row["sha256"].encode("ascii")); digest.update(b"\0")
    return {"sha256": digest.hexdigest(), "fileCount": len(rows)}


def _validate_id(value: str, *, transaction: bool = False) -> str:
    pat = TX_ID_RE if transaction else SOURCE_ID_RE
    if not pat.fullmatch(value or ""):
        raise ValueError(f"invalid {'transaction' if transaction else 'source'} id: {value!r}")
    return value


def _tx_dir(root: Path, tx_id: str) -> Path:
    _validate_id(tx_id, transaction=True)
    return root / TX_BASE / tx_id


def _candidate_limit(kind: str) -> int:
    if kind in RULE_FAMILY:
        return MAX_PDF_BYTES
    if kind == "reviewed_file":
        return MAX_REVIEWED_FILE_BYTES
    return MAX_SOURCE_BYTES


def _validate_reviewed_target(value: Any) -> str:
    target = str(value or "").replace("\\", "/")
    if target not in REVIEWED_FILE_TARGETS:
        raise ValueError(f"reviewed file target is not allowlisted: {target}")
    return target


def _default_tx_id(spec: dict[str, Any]) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw = json.dumps(spec, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"upd-{stamp}-{hashlib.sha256(raw).hexdigest()[:10]}"




def _normalize_registration(raw: Any, source_id: str) -> dict[str, Any] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("registration must be an object")
    stype = str(raw.get("type") or "")
    status = str(raw.get("status") or "")
    if stype not in ALLOWED_REGISTERED_TYPES:
        raise ValueError(f"unsupported registered source type: {stype}")
    if status not in ALLOWED_REGISTERED_STATUSES:
        raise ValueError(f"unsupported registered source status: {status}")
    url = str(raw.get("url") or "")
    if stype in {"rules_hub", "official_faq", "patch_notes", "card_errata", "official_article"}:
        if not url:
            raise ValueError("registered official web source requires url")
        validate_official_url(url)
    authority_scope = list(raw.get("authorityScope") or [])
    precedence = raw.get("precedence")
    if status == "current_overlay":
        if not authority_scope:
            raise ValueError("current_overlay registration requires authorityScope")
        if not isinstance(precedence, dict) or not precedence:
            raise ValueError("current_overlay registration requires explicit precedence metadata")
        if not raw.get("supersedesSourceId"):
            raise ValueError("current_overlay registration requires supersedesSourceId")
    out = {
        "id": source_id,
        "type": stype,
        "status": status,
        "url": url,
        "published": raw.get("published"),
        "effectiveFrom": raw.get("effectiveFrom"),
        "authorityScope": authority_scope,
        "precedence": precedence,
        "validationProfile": raw.get("validationProfile") or {},
        "exhaustive": raw.get("exhaustive"),
        "release": raw.get("release"),
        "supersedesSourceId": raw.get("supersedesSourceId"),
        "captureMode": raw.get("captureMode") or "source_file",
        "captureNote": raw.get("captureNote"),
    }
    return {k: v for k, v in out.items() if v is not None}


def _ensure_registration(root: Path, candidate: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    sid = str(candidate["sourceId"])
    existing = _manifest_source(root, sid)
    if existing is not None:
        return existing, False
    reg = candidate.get("registration")
    if not isinstance(reg, dict):
        raise RuntimeError(f"official source is not registered and has no reviewed registration: {sid}")
    manifest_path = root / "data/source/official_source_manifest.json"
    manifest = _read(manifest_path)
    status = str(reg.get("status") or "")
    supersedes = reg.get("supersedesSourceId")
    if supersedes:
        old = next((x for x in manifest.get("sources", []) if str(x.get("id")) == str(supersedes)), None)
        if old is None:
            raise RuntimeError(f"registration supersedes unknown source: {supersedes}")
        if status in {"current_overlay", "current_index", "current_change_record"}:
            expected_old_status = {"current_overlay": "current_overlay", "current_index": "current_index", "current_change_record": "current_change_record"}[status]
            if old.get("status") != expected_old_status:
                raise RuntimeError(f"superseded source is not {expected_old_status}: {supersedes}")
            old["status"] = "superseded_history"
            old["supersededBy"] = sid
            old["effectiveUntil"] = reg.get("effectiveFrom")
    new_meta = {k: v for k, v in reg.items() if k != "supersedesSourceId"}
    new_meta["id"] = sid
    manifest.setdefault("sources", []).append(new_meta)
    _dump(manifest_path, manifest)
    return new_meta, True

def _normalize_candidate(root: Path, raw: dict[str, Any], idx: int, tx_dir: Path) -> dict[str, Any]:
    kind = str(raw.get("kind") or "")
    if kind not in SUPPORTED_KINDS:
        raise ValueError(f"unsupported candidate kind: {kind}")
    source_id = _validate_id(str(raw.get("sourceId") or ""))
    file_path = Path(str(raw.get("file") or "")).expanduser().resolve()
    if not file_path.exists() or not file_path.is_file():
        raise FileNotFoundError(file_path)
    size = file_path.stat().st_size
    if size <= 0 or size > _candidate_limit(kind):
        raise ValueError(f"candidate size out of bounds for {kind}: {size}")
    registration = _normalize_registration(raw.get("registration"), source_id) if kind == "official_snapshot" else None
    target = _validate_reviewed_target(raw.get("target")) if kind == "reviewed_file" else None
    if kind == "reviewed_file":
        try:
            json.loads(file_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"reviewed file must be valid JSON: {exc}") from exc
    if kind == "official_snapshot" and _manifest_source(root, source_id) is None and registration is None:
        # Unknown authority identities are allowed only with an explicit registration
        # object. The automation never invents source type/status/precedence metadata.
        raise ValueError(f"official source is not registered in manifest: {source_id}")
    suffix = file_path.suffix.lower()[:12]
    safe_name = f"{idx:03d}_{source_id}{suffix}"
    dest = tx_dir / "inputs" / safe_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(file_path, dest)
    return {
        "candidateId": f"C{idx:03d}",
        "kind": kind,
        "sourceId": source_id,
        "inputFile": str(dest.relative_to(root)),
        "inputSha256": sha256_file(dest),
        "byteLength": size,
        "effectiveFrom": raw.get("effectiveFrom"),
        "published": raw.get("published"),
        "mediaType": raw.get("mediaType"),
        "sourceType": raw.get("sourceType"),
        "sourceUrl": raw.get("sourceUrl"),
        "registration": registration,
        "target": target,
    }


def create_transaction(root: Path, spec: dict[str, Any], transaction_id: str | None = None) -> dict[str, Any]:
    root = Path(root).resolve()
    candidates = list(spec.get("candidates") or [])
    if not candidates:
        raise ValueError("update transaction requires at least one candidate")
    baseline = project_fingerprint(root)
    tx_id = _validate_id(transaction_id or _default_tx_id(spec), transaction=True)
    tx_dir = _tx_dir(root, tx_id)
    if tx_dir.exists():
        raise FileExistsError(f"transaction already exists: {tx_id}")
    tx_dir.mkdir(parents=True)
    try:
        normalized = [_normalize_candidate(root, c, i, tx_dir) for i, c in enumerate(candidates, start=1)]
        request = {
            "schemaVersion": SCHEMA_VERSION,
            "transactionId": tx_id,
            "createdAt": _now(),
            "status": "created",
            "baselineFingerprint": baseline,
            "candidateCount": len(normalized),
            "candidates": normalized,
            "note": spec.get("note"),
        }
        _dump_sealed(tx_dir / "request.json", request)
        _dump(tx_dir / "status.json", {"transactionId": tx_id, "status": "created", "updatedAt": _now()})
        return request
    except Exception:
        shutil.rmtree(tx_dir, ignore_errors=True)
        raise


def load_transaction(root: Path, tx_id: str) -> dict[str, Any]:
    tx_dir = _tx_dir(Path(root).resolve(), tx_id)
    req = tx_dir / "request.json"
    if not req.exists():
        raise FileNotFoundError(f"unknown transaction: {tx_id}")
    return _read_sealed(req)


def _assert_inputs_unchanged(root: Path, request: dict[str, Any]) -> None:
    for c in request.get("candidates", []):
        p = root / c["inputFile"]
        if not p.exists() or sha256_file(p) != c.get("inputSha256"):
            raise RuntimeError(f"transaction input drift detected: {c.get('candidateId')}")


def _assert_baseline_current(root: Path, request: dict[str, Any]) -> None:
    current = project_fingerprint(root)
    expected = request.get("baselineFingerprint") or {}
    if current.get("sha256") != expected.get("sha256"):
        raise RuntimeError("transaction baseline is stale; create a new transaction against the current project state")


def _clone_project(root: Path) -> tuple[Path, Path]:
    parent = Path(tempfile.mkdtemp(prefix="riftkeep-update-work-"))
    clone = parent / root.name

    def ignore(path: str, names: list[str]) -> set[str]:
        p = Path(path)
        ignored = {n for n in names if n in {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".git"} or n.endswith((".pyc", ".pyo"))}
        try:
            rel = p.resolve().relative_to(root.resolve())
            if str(rel).replace("\\", "/") == "data":
                ignored.add("update_transactions")
        except Exception:
            pass
        return ignored

    shutil.copytree(root, clone, ignore=ignore)
    return parent, clone


def _snapshot_previous_sha(root: Path, source_id: str) -> str | None:
    ptr = root / "data/source/snapshots" / source_id / "latest.json"
    if not ptr.exists():
        return None
    try:
        return str(_read(ptr).get("sha256") or "") or None
    except Exception:
        return None


def stage_transaction(root: Path, tx_id: str) -> dict[str, Any]:
    root = Path(root).resolve()
    request = load_transaction(root, tx_id)
    _assert_inputs_unchanged(root, request)
    _assert_baseline_current(root, request)
    tx_dir = _tx_dir(root, tx_id)
    work_parent, clone = _clone_project(root)
    rows: list[dict[str, Any]] = []
    blockers: list[dict[str, str]] = []
    review_reasons: list[dict[str, str]] = []
    try:
        for c in request.get("candidates", []):
            inp = root / c["inputFile"]
            kind = c["kind"]
            sid = c["sourceId"]
            if kind == "reviewed_file":
                target_rel = _validate_reviewed_target(c.get("target"))
                target = clone / target_rel
                try:
                    json.loads(inp.read_text(encoding="utf-8"))
                    before_sha = sha256_file(target) if target.exists() else None
                    after_sha = sha256_file(inp)
                    changed = before_sha != after_sha
                    rows.append({
                        "candidateId": c["candidateId"], "kind": kind, "sourceId": sid,
                        "target": target_rel, "changed": changed, "validationPassed": True,
                        "reviewRequired": changed, "stageStatus": "changed" if changed else "no_change",
                        "previousSha256": before_sha, "candidateSha256": after_sha,
                    })
                    if changed:
                        review_reasons.append({"candidateId": c["candidateId"], "reason": f"reviewed_support_file_change_requires_human_review:{target_rel}"})
                except Exception as exc:
                    blockers.append({"candidateId": c["candidateId"], "reason": f"reviewed_file_error:{type(exc).__name__}:{exc}"})
                    rows.append({"candidateId": c["candidateId"], "kind": kind, "sourceId": sid, "target": target_rel, "stageStatus": "error"})
                continue
            if kind in RULE_FAMILY:
                try:
                    staged = stage_rules_update(clone, RULE_FAMILY[kind], inp, sid, c.get("effectiveFrom"))
                    row = {
                        "candidateId": c["candidateId"], "kind": kind, "sourceId": sid,
                        "changed": True,
                        "validationPassed": bool((staged.get("validation") or {}).get("passed")),
                        "technicalSafeToPromote": bool((staged.get("diff") or {}).get("safeToAutoPromote")),
                        "stageStatus": staged.get("status"),
                        "changeCounts": (staged.get("diff") or {}).get("changeCounts") or {},
                        "reviewRequired": True,
                    }
                    rows.append(row)
                    if not row["validationPassed"]:
                        blockers.append({"candidateId": c["candidateId"], "reason": "rule_pdf_validation_failed"})
                    review_reasons.append({"candidateId": c["candidateId"], "reason": "new_rule_document_requires_human_review"})
                except Exception as exc:
                    blockers.append({"candidateId": c["candidateId"], "reason": f"stage_error:{type(exc).__name__}:{exc}"})
                    rows.append({"candidateId": c["candidateId"], "kind": kind, "sourceId": sid, "changed": True, "reviewRequired": True, "stageStatus": "error"})
            else:
                try:
                    meta, newly_registered = _ensure_registration(clone, c)
                except Exception as exc:
                    blockers.append({"candidateId": c["candidateId"], "reason": f"registration_error:{type(exc).__name__}:{exc}"})
                    rows.append({"candidateId": c["candidateId"], "kind": kind, "sourceId": sid, "stageStatus": "error"})
                    continue
                previous_sha = _snapshot_previous_sha(clone, sid)
                try:
                    snap = import_official_snapshot(
                        clone, sid, inp,
                        media_type=c.get("mediaType"), source_type=c.get("sourceType") or meta.get("type"),
                        source_url=c.get("sourceUrl") or meta.get("url"), published=c.get("published"),
                        effective_from=c.get("effectiveFrom"),
                    )
                    changed = bool((snap.get("diffFromPrevious") or {}).get("changed")) and snap.get("sha256") != previous_sha
                    valid = bool((snap.get("validation") or {}).get("passed"))
                    row = {
                        "candidateId": c["candidateId"], "kind": kind, "sourceId": sid,
                        "sourceType": snap.get("sourceType"), "authorityStatus": (snap.get("authority") or {}).get("status"),
                        "changed": changed, "validationPassed": valid,
                        "previousSha256": previous_sha, "candidateSha256": snap.get("sha256"),
                        "changeCounts": (snap.get("diffFromPrevious") or {}).get("changeCounts") or {},
                        "sectionCount": snap.get("sectionCount"),
                        "reviewRequired": changed or newly_registered,
                        "newSourceRegistration": newly_registered,
                        "stageStatus": "changed" if changed or newly_registered else "no_change",
                    }
                    rows.append(row)
                    if not valid:
                        blockers.append({"candidateId": c["candidateId"], "reason": "official_snapshot_validation_failed"})
                    if newly_registered:
                        review_reasons.append({"candidateId": c["candidateId"], "reason": "new_official_source_registration_requires_human_review"})
                    if changed:
                        review_reasons.append({"candidateId": c["candidateId"], "reason": f"official_{snap.get('sourceType')}_change_requires_human_review"})
                except Exception as exc:
                    blockers.append({"candidateId": c["candidateId"], "reason": f"stage_error:{type(exc).__name__}:{exc}"})
                    rows.append({"candidateId": c["candidateId"], "kind": kind, "sourceId": sid, "stageStatus": "error"})

        changed_count = sum(1 for r in rows if r.get("changed") or r.get("newSourceRegistration"))
        review_required = bool(review_reasons)
        if blockers:
            status = "blocked"
        elif review_required:
            status = "review_required"
        elif changed_count:
            status = "ready"
        else:
            status = "no_changes"
        plan = {
            "schemaVersion": SCHEMA_VERSION,
            "transactionId": tx_id,
            "stagedAt": _now(),
            "status": status,
            "baselineFingerprint": request.get("baselineFingerprint"),
            "candidateCount": len(rows),
            "materialChangeCount": changed_count,
            "reviewRequired": review_required,
            "reviewReasons": review_reasons,
            "blockers": blockers,
            "candidates": rows,
        }
        _dump_sealed(tx_dir / "plan.json", plan)
        _dump(tx_dir / "status.json", {"transactionId": tx_id, "status": status, "updatedAt": _now()})
        return plan
    finally:
        shutil.rmtree(work_parent, ignore_errors=True)


def approve_transaction(root: Path, tx_id: str, reviewer: str, notes: str | None = None) -> dict[str, Any]:
    root = Path(root).resolve(); tx_dir = _tx_dir(root, tx_id)
    plan_path = tx_dir / "plan.json"
    if not plan_path.exists():
        raise RuntimeError("transaction must be staged before approval")
    plan = _read_sealed(plan_path)
    if plan.get("blockers"):
        raise RuntimeError("blocked transaction cannot be approved")
    reviewer = str(reviewer or "").strip()
    if not reviewer:
        raise ValueError("reviewer is required")
    record = {
        "schemaVersion": SCHEMA_VERSION,
        "transactionId": tx_id,
        "approved": True,
        "reviewer": reviewer,
        "notes": notes,
        "approvedAt": _now(),
        "planSha256": sha256_file(plan_path),
        "reviewReasons": plan.get("reviewReasons") or [],
    }
    _dump_sealed(tx_dir / "review.json", record)
    _dump(tx_dir / "status.json", {"transactionId": tx_id, "status": "approved", "updatedAt": _now()})
    return record


def _approval_valid(tx_dir: Path, plan: dict[str, Any]) -> bool:
    if not plan.get("reviewRequired"):
        return True
    p = tx_dir / "review.json"
    if not p.exists():
        return False
    try:
        _read_sealed(tx_dir / "plan.json")
        r = _read_sealed(p)
    except Exception:
        return False
    return bool(r.get("approved")) and r.get("planSha256") == sha256_file(tx_dir / "plan.json")


def _apply_candidates(clone: Path, source_root: Path, request: dict[str, Any], approved: bool) -> list[dict[str, Any]]:
    applied: list[dict[str, Any]] = []
    for c in request.get("candidates", []):
        inp = source_root / c["inputFile"]
        kind = c["kind"]; sid = c["sourceId"]
        if kind == "reviewed_file":
            target_rel = _validate_reviewed_target(c.get("target"))
            json.loads(inp.read_text(encoding="utf-8"))
            target = clone / target_rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(inp, target)
            applied.append({"candidateId": c["candidateId"], "kind": kind, "sourceId": sid, "result": {"target": target_rel, "sha256": sha256_file(target)}})
            continue
        if kind in RULE_FAMILY:
            stage = stage_rules_update(clone, RULE_FAMILY[kind], inp, sid, c.get("effectiveFrom"))
            if not (stage.get("validation") or {}).get("passed"):
                raise RuntimeError(f"cannot apply invalid staged PDF: {sid}")
            result = promote_staged_update(clone, RULE_FAMILY[kind], sid, approve_review=approved)
            applied.append({"candidateId": c["candidateId"], "kind": kind, "sourceId": sid, "result": result})
        else:
            meta, _ = _ensure_registration(clone, c)
            snap = import_official_snapshot(
                clone, sid, inp,
                media_type=c.get("mediaType"), source_type=c.get("sourceType") or meta.get("type"),
                source_url=c.get("sourceUrl") or meta.get("url"), published=c.get("published"),
                effective_from=c.get("effectiveFrom"),
            )
            if not (snap.get("validation") or {}).get("passed"):
                raise RuntimeError(f"cannot apply invalid official snapshot: {sid}")
            applied.append({
                "candidateId": c["candidateId"], "kind": kind, "sourceId": sid,
                "result": {"sha256": snap.get("sha256"), "changed": (snap.get("diffFromPrevious") or {}).get("changed"), "sectionCount": snap.get("sectionCount")},
            })
    return applied


def _ignore_tree_rel(rel: str) -> bool:
    rel = rel.replace("\\", "/")
    return rel.startswith("data/update_transactions/") or "/__pycache__/" in f"/{rel}/" or rel.endswith((".pyc", ".pyo"))


def _tree_map(root: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for p in sorted(x for x in root.rglob("*") if x.is_file()):
        rel = str(p.relative_to(root)).replace("\\", "/")
        if _ignore_tree_rel(rel):
            continue
        out[rel] = {"sha256": sha256_file(p), "bytes": p.stat().st_size}
    return out


def _tree_diff(before_root: Path, after_root: Path) -> list[dict[str, Any]]:
    a = _tree_map(before_root); b = _tree_map(after_root)
    rows: list[dict[str, Any]] = []
    for rel in sorted(set(a) | set(b)):
        if rel not in a:
            rows.append({"path": rel, "change": "ADDED", "beforeSha256": None, "afterSha256": b[rel]["sha256"], "bytes": b[rel]["bytes"]})
        elif rel not in b:
            rows.append({"path": rel, "change": "REMOVED", "beforeSha256": a[rel]["sha256"], "afterSha256": None, "bytes": 0})
        elif a[rel]["sha256"] != b[rel]["sha256"]:
            rows.append({"path": rel, "change": "CHANGED", "beforeSha256": a[rel]["sha256"], "afterSha256": b[rel]["sha256"], "bytes": b[rel]["bytes"]})
    return rows


def _write_publish_bundle(clone: Path, tx_dir: Path, changes: list[dict[str, Any]]) -> tuple[str, int]:
    bundle = tx_dir / "publish_bundle.zip"
    bundle.unlink(missing_ok=True)
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for row in changes:
            if row["change"] == "REMOVED":
                continue
            p = clone / row["path"]
            if not p.exists() or sha256_file(p) != row["afterSha256"]:
                raise RuntimeError(f"publish bundle source drift: {row['path']}")
            z.write(p, row["path"])
    return sha256_file(bundle), bundle.stat().st_size


def rehearse_transaction(root: Path, tx_id: str, gate_runner: GateRunner | None = None) -> dict[str, Any]:
    root = Path(root).resolve(); request = load_transaction(root, tx_id); tx_dir = _tx_dir(root, tx_id)
    _assert_inputs_unchanged(root, request); _assert_baseline_current(root, request)
    plan_path = tx_dir / "plan.json"
    if not plan_path.exists():
        raise RuntimeError("transaction must be staged before rehearsal")
    plan = _read_sealed(plan_path)
    if plan.get("blockers"):
        raise RuntimeError("blocked transaction cannot be rehearsed")
    if int(plan.get("materialChangeCount") or 0) == 0:
        result = {
            "schemaVersion": SCHEMA_VERSION,
            "transactionId": tx_id,
            "rehearsedAt": _now(),
            "passed": True,
            "publishReady": False,
            "noChanges": True,
            "baselineFingerprint": request.get("baselineFingerprint"),
            "approvalUsed": False,
            "appliedCandidates": [],
            "fileChangeCount": 0,
            "fileChanges": [],
            "publishBundle": None,
            "publishBundleSha256": None,
            "publishBundleBytes": 0,
            "releaseGate": {"passed": True, "skipped": True, "reason": "no_material_changes"},
        }
        _dump_sealed(tx_dir / "rehearsal.json", result)
        _dump(tx_dir / "status.json", {"transactionId": tx_id, "status": "no_changes", "updatedAt": _now()})
        return result
    if plan.get("reviewRequired") and not _approval_valid(tx_dir, plan):
        raise RuntimeError("material update requires current explicit review approval")
    approved = _approval_valid(tx_dir, plan)
    work_parent, clone = _clone_project(root)
    try:
        applied = _apply_candidates(clone, root, request, approved)
        runner = gate_runner or (lambda r: run_release_gate(r))
        gate = runner(clone)
        changes = _tree_diff(root, clone)
        bundle_sha = None; bundle_bytes = 0
        if gate.get("passed"):
            bundle_sha, bundle_bytes = _write_publish_bundle(clone, tx_dir, changes)
        result = {
            "schemaVersion": SCHEMA_VERSION,
            "transactionId": tx_id,
            "rehearsedAt": _now(),
            "passed": bool(gate.get("passed")),
            "publishReady": bool(gate.get("passed")),
            "baselineFingerprint": request.get("baselineFingerprint"),
            "approvalUsed": approved,
            "appliedCandidates": applied,
            "fileChangeCount": len(changes),
            "fileChanges": changes,
            "publishBundle": "publish_bundle.zip" if bundle_sha else None,
            "publishBundleSha256": bundle_sha,
            "publishBundleBytes": bundle_bytes,
            "releaseGate": summarize_release_gate(gate),
        }
        _dump_sealed(tx_dir / "rehearsal.json", result)
        _dump(tx_dir / "status.json", {"transactionId": tx_id, "status": "rehearsed" if result["passed"] else "rehearsal_failed", "updatedAt": _now()})
        return result
    finally:
        shutil.rmtree(work_parent, ignore_errors=True)


def _make_rollback_bundle(root: Path, tx_dir: Path, changes: list[dict[str, Any]]) -> Path:
    rollback = tx_dir / "rollback_bundle.zip"
    rollback.unlink(missing_ok=True)
    manifest: list[dict[str, Any]] = []
    with zipfile.ZipFile(rollback, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for row in changes:
            p = root / row["path"]
            existed = p.exists()
            manifest.append({"path": row["path"], "existed": existed, "sha256": sha256_file(p) if existed else None})
            if existed:
                z.write(p, row["path"])
        z.writestr("__rollback_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return rollback


def _restore_rollback(root: Path, rollback: Path) -> None:
    with zipfile.ZipFile(rollback) as z:
        manifest = json.loads(z.read("__rollback_manifest.json"))
        members = set(z.namelist())
        for row in manifest:
            target = root / row["path"]
            if row["existed"]:
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp = target.with_name(target.name + ".rollback-tmp")
                tmp.write_bytes(z.read(row["path"]))
                os.replace(tmp, target)
            else:
                target.unlink(missing_ok=True)


def _apply_publish_bundle(root: Path, tx_dir: Path, rehearsal: dict[str, Any]) -> None:
    bundle = tx_dir / str(rehearsal.get("publishBundle") or "")
    if not bundle.exists() or sha256_file(bundle) != rehearsal.get("publishBundleSha256"):
        raise RuntimeError("publish bundle missing or hash mismatch")
    changes = list(rehearsal.get("fileChanges") or [])
    by_path = {r["path"]: r for r in changes}
    with zipfile.ZipFile(bundle) as z:
        if z.testzip() is not None:
            raise RuntimeError("publish bundle ZIP integrity failure")
        for name in z.namelist():
            if name not in by_path or by_path[name].get("change") == "REMOVED":
                raise RuntimeError(f"unexpected publish bundle member: {name}")
            data = z.read(name)
            if _sha256_bytes(data) != by_path[name].get("afterSha256"):
                raise RuntimeError(f"publish bundle member hash mismatch: {name}")
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".publish-tmp")
            tmp.write_bytes(data)
            os.replace(tmp, target)
        for row in changes:
            if row["change"] == "REMOVED":
                (root / row["path"]).unlink(missing_ok=True)
    for row in changes:
        p = root / row["path"]
        if row["change"] == "REMOVED":
            if p.exists(): raise RuntimeError(f"failed to remove published path: {row['path']}")
        elif not p.exists() or sha256_file(p) != row.get("afterSha256"):
            raise RuntimeError(f"published path verification failed: {row['path']}")


def publish_transaction(root: Path, tx_id: str, gate_runner: GateRunner | None = None) -> dict[str, Any]:
    root = Path(root).resolve(); request = load_transaction(root, tx_id); tx_dir = _tx_dir(root, tx_id)
    _assert_inputs_unchanged(root, request); _assert_baseline_current(root, request)
    rehearsal_path = tx_dir / "rehearsal.json"
    if not rehearsal_path.exists():
        raise RuntimeError("transaction must pass rehearsal before publish")
    rehearsal = _read_sealed(rehearsal_path)
    if not rehearsal.get("publishReady") or not rehearsal.get("passed"):
        raise RuntimeError("rehearsal did not pass")
    changes = list(rehearsal.get("fileChanges") or [])
    rollback = _make_rollback_bundle(root, tx_dir, changes)
    rollback_sha = sha256_file(rollback)
    runner = gate_runner or (lambda r: run_release_gate(r))
    try:
        _apply_publish_bundle(root, tx_dir, rehearsal)
        gate = runner(root)
        if not gate.get("passed"):
            raise RuntimeError("post-publish release gate failed")
        result = {
            "schemaVersion": SCHEMA_VERSION,
            "transactionId": tx_id,
            "status": "published",
            "publishedAt": _now(),
            "fileChangeCount": len(changes),
            "publishBundleSha256": rehearsal.get("publishBundleSha256"),
            "rollbackBundleSha256": rollback_sha,
            "postPublishReleaseGate": summarize_release_gate(gate),
            "postPublishFingerprint": project_fingerprint(root),
            "rolledBack": False,
        }
        _dump_sealed(tx_dir / "publish.json", result)
        _dump(tx_dir / "status.json", {"transactionId": tx_id, "status": "published", "updatedAt": _now()})
        return result
    except Exception as exc:
        _restore_rollback(root, rollback)
        result = {
            "schemaVersion": SCHEMA_VERSION,
            "transactionId": tx_id,
            "status": "rolled_back",
            "failedAt": _now(),
            "error": f"{type(exc).__name__}: {exc}",
            "rollbackBundleSha256": rollback_sha,
            "rolledBack": True,
        }
        _dump_sealed(tx_dir / "publish.json", result)
        _dump(tx_dir / "status.json", {"transactionId": tx_id, "status": "rolled_back", "updatedAt": _now()})
        raise RuntimeError(result["error"])


def transaction_status(root: Path, tx_id: str) -> dict[str, Any]:
    root = Path(root).resolve(); tx_dir = _tx_dir(root, tx_id)
    request = load_transaction(root, tx_id)
    out: dict[str, Any] = {"transactionId": tx_id, "request": request}
    for name in ("status", "plan", "review", "rehearsal", "publish"):
        p = tx_dir / f"{name}.json"
        if not p.exists():
            out[name] = None
        elif name == "status":
            out[name] = _read(p)
        else:
            out[name] = _read_sealed(p)
    out["currentFingerprint"] = project_fingerprint(root)
    out["baselineCurrent"] = out["currentFingerprint"].get("sha256") == (request.get("baselineFingerprint") or {}).get("sha256")
    return out


def _default_fetcher(url: str, timeout: int) -> tuple[bytes, str]:
    validate_official_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": "RiftKeepRules/1.0 (+update-automation)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        announced = resp.headers.get("Content-Length")
        if announced and int(announced) > MAX_SOURCE_BYTES:
            raise ValueError("official source exceeds maximum size")
        raw = resp.read(MAX_SOURCE_BYTES + 1)
        if len(raw) > MAX_SOURCE_BYTES:
            raise ValueError("official source exceeds maximum size")
        ctype = resp.headers.get_content_type() or "text/html"
        if ctype not in {"text/html", "application/xhtml+xml", "text/plain"}:
            raise ValueError(f"unsupported official source content type: {ctype}")
        return raw, ctype


def poll_registered_source(root: Path, source_id: str, *, timeout: int = 30, fetcher: Fetcher | None = None, transaction_id: str | None = None) -> dict[str, Any]:
    root = Path(root).resolve(); source_id = _validate_id(source_id)
    meta = _manifest_source(root, source_id)
    if meta is None:
        raise ValueError(f"official source is not registered: {source_id}")
    url = str(meta.get("url") or "")
    if not url:
        raise ValueError(f"registered source has no fetchable URL: {source_id}")
    validate_official_url(url)
    raw, media_type = (fetcher or _default_fetcher)(url, timeout)
    if len(raw) <= 0 or len(raw) > MAX_SOURCE_BYTES:
        raise ValueError("fetched source size out of bounds")
    suffix = ".html" if "html" in media_type else ".txt"
    with tempfile.NamedTemporaryFile(prefix=f"riftkeep-{source_id}-", suffix=suffix, delete=False) as f:
        tmp = Path(f.name); f.write(raw)
    try:
        request = create_transaction(root, {"note": f"polled registered source {source_id}", "candidates": [{
            "kind": "official_snapshot", "sourceId": source_id, "file": str(tmp),
            "mediaType": media_type, "sourceType": meta.get("type"), "sourceUrl": url,
            "published": meta.get("published"), "effectiveFrom": meta.get("effectiveFrom"),
        }]}, transaction_id=transaction_id)
        return request
    finally:
        tmp.unlink(missing_ok=True)
