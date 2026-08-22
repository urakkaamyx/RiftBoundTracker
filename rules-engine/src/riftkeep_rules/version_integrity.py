from __future__ import annotations

import hashlib
import os
import tempfile
import json
from pathlib import Path
from typing import Any


def _atomic_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


FAMILIES: dict[str, dict[str, str]] = {
    "core": {
        "manifestType": "core_rules_pdf",
        "liveFile": "core_rules.pdf",
        "canonicalFile": "core_rules.json",
        "stablePrefix": "RK-CR",
        "title": "Riftbound Core Rules",
    },
    "tournament": {
        "manifestType": "tournament_rules_pdf",
        "liveFile": "tournament_rules.pdf",
        "canonicalFile": "tournament_rules.json",
        "stablePrefix": "RK-TR",
        "title": "Riftbound Tournament Rules",
    },
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _manifest(root: Path) -> dict[str, Any]:
    p = root / "data/source/official_source_manifest.json"
    if not p.exists():
        raise FileNotFoundError(p)
    return _read_json(p, {})


def current_manifest_source(root: Path, family: str) -> dict[str, Any]:
    cfg = FAMILIES[family]
    sources = _manifest(root).get("sources", [])
    rows = [s for s in sources if s.get("type") == cfg["manifestType"] and s.get("status") == "current"]
    if len(rows) != 1:
        raise RuntimeError(f"expected exactly one current {family} source, found {len(rows)}")
    return rows[0]


def history_path(root: Path, family: str) -> Path:
    return root / "data/source/rule_versions" / family / "history.json"


def load_history(root: Path, family: str) -> dict[str, Any]:
    p = history_path(root, family)
    return _read_json(p, {"schemaVersion": 1, "family": family, "versions": []})


def current_history_version(root: Path, family: str) -> dict[str, Any] | None:
    rows = [x for x in load_history(root, family).get("versions", []) if x.get("status") == "current"]
    return rows[0] if len(rows) == 1 else None


def bootstrap_version_ledger(root: Path, family: str) -> dict[str, Any]:
    """Create a one-version ledger from the already validated current baseline.

    This is recovery/bootstrap only. It does not invent an older version or simulate a
    promotion. The current PDF, current canonical parse, and manifest source must agree.
    """
    cfg = FAMILIES[family]
    manifest_src = current_manifest_source(root, family)
    live = root / "data/source" / str(manifest_src.get("localSnapshot") or cfg["liveFile"])
    canonical = root / "data/canonical" / cfg["canonicalFile"]
    if not live.exists() or not canonical.exists():
        raise FileNotFoundError(f"cannot bootstrap {family}: current PDF/canonical artifact missing")
    doc = _read_json(canonical, {})
    source_id = str(manifest_src["id"])
    actual_sha = sha256_file(live)
    parsed_sha = str((doc.get("metadata") or {}).get("sourceSha256") or "")
    parsed_source = str((doc.get("metadata") or {}).get("sourceId") or "")
    if parsed_sha != actual_sha or parsed_source != source_id:
        raise RuntimeError(f"cannot bootstrap {family}: canonical source metadata does not match live PDF/manifest")

    hp = history_path(root, family)
    version_dir = hp.parent / source_id
    version_dir.mkdir(parents=True, exist_ok=True)
    parsed_path = version_dir / "parsed_rules.json"
    _atomic_json(parsed_path, doc)
    version = {
        "sourceId": source_id,
        "status": "current",
        "sourceSha256": actual_sha,
        "sourceFile": str(live.relative_to(root)),
        "parsedRules": str(parsed_path.relative_to(root)),
        "ruleCount": len(doc.get("rules", [])),
        "previousSourceId": None,
        "nextSourceId": None,
        "effectiveFrom": manifest_src.get("effectiveFrom") or manifest_src.get("published"),
    }
    _atomic_json(version_dir / "version.json", version)
    history = {"schemaVersion": 1, "family": family, "currentSourceId": source_id, "versions": [version]}
    hp.parent.mkdir(parents=True, exist_ok=True)
    _atomic_json(hp, history)
    return history


def ensure_version_ledgers(root: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for family in FAMILIES:
        hp = history_path(root, family)
        result[family] = load_history(root, family) if hp.exists() else bootstrap_version_ledger(root, family)
    return result


def validate_rule_version_integrity(root: Path) -> dict[str, Any]:
    errors: list[str] = []
    families: dict[str, Any] = {}
    for family, cfg in FAMILIES.items():
        fam: dict[str, Any] = {"passed": True, "checks": {}, "errors": []}
        hp = history_path(root, family)
        fam["checks"]["historyExists"] = hp.exists()
        if not hp.exists():
            fam["errors"].append("history_missing")
            errors.append(f"{family}:history_missing")
            fam["passed"] = False
            families[family] = fam
            continue
        try:
            history = load_history(root, family)
            manifest_src = current_manifest_source(root, family)
        except Exception as exc:
            fam["errors"].append(f"metadata_error:{type(exc).__name__}:{exc}")
            errors.append(f"{family}:metadata_error")
            fam["passed"] = False
            families[family] = fam
            continue
        versions = list(history.get("versions", []))
        current = [v for v in versions if v.get("status") == "current"]
        fam["checks"]["exactlyOneCurrentVersion"] = len(current) == 1
        fam["checks"]["historyCurrentPointerMatches"] = len(current) == 1 and history.get("currentSourceId") == current[0].get("sourceId")
        fam["checks"]["manifestCurrentMatchesLedger"] = len(current) == 1 and manifest_src.get("id") == current[0].get("sourceId")
        if len(current) == 1:
            v = current[0]
            live = root / "data/source" / str(manifest_src.get("localSnapshot") or cfg["liveFile"])
            parsed_path = root / str(v.get("parsedRules") or "")
            version_meta = hp.parent / str(v.get("sourceId")) / "version.json"
            fam["checks"]["livePdfExists"] = live.exists()
            fam["checks"]["parsedSnapshotExists"] = parsed_path.exists()
            fam["checks"]["versionMetadataExists"] = version_meta.exists()
            actual_sha = sha256_file(live) if live.exists() else None
            fam["checks"]["livePdfHashMatchesLedger"] = actual_sha == v.get("sourceSha256")
            if parsed_path.exists():
                parsed = _read_json(parsed_path, {})
                meta = parsed.get("metadata") or {}
                fam["checks"]["parsedSourceIdMatchesLedger"] = meta.get("sourceId") == v.get("sourceId")
                fam["checks"]["parsedSourceHashMatchesLedger"] = meta.get("sourceSha256") == v.get("sourceSha256")
                rules = parsed.get("rules", [])
                fam["checks"]["ruleCountMatchesLedger"] = len(rules) == v.get("ruleCount")
                internal = [r.get("internalRuleId") for r in rules]
                fam["checks"]["internalRuleIdsUnique"] = len(internal) == len(set(internal)) and all(internal)
            else:
                for k in ("parsedSourceIdMatchesLedger", "parsedSourceHashMatchesLedger", "ruleCountMatchesLedger", "internalRuleIdsUnique"):
                    fam["checks"][k] = False
        for k, ok in fam["checks"].items():
            if not ok:
                fam["errors"].append(k)
                errors.append(f"{family}:{k}")
        fam["passed"] = not fam["errors"]
        fam["versionCount"] = len(versions)
        fam["currentSourceId"] = current[0].get("sourceId") if len(current) == 1 else None
        families[family] = fam
    return {"schemaVersion": 1, "passed": not errors, "errors": errors, "families": families}


def assert_live_sources_untampered(root: Path) -> None:
    report = validate_rule_version_integrity(root)
    if not report.get("passed"):
        raise RuntimeError("rule-version/source integrity failure: " + "; ".join(report.get("errors", [])))
