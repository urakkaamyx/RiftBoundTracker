from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

PRODUCT_NAME = "RiftKeep Rules Engine"
PRODUCT_VERSION = "1.0.4"
RELEASE_LINE = "stable"
PRODUCT_API_VERSION = "v1"
STABLE_MANIFEST_SCHEMA_VERSION = 1

# Hashes intentionally exclude MILESTONE.json and the generated manifest itself:
# candidate -> released promotion changes milestone metadata, and a manifest cannot
# include its own hash. The final release ZIP is separately sealed by its .sha256.
CRITICAL_ARTIFACTS: tuple[str, ...] = (
    "pyproject.toml",
    "src/riftkeep_rules/__init__.py",
    "src/riftkeep_rules/release_identity.py",
    "src/riftkeep_rules/product_api.py",
    "src/riftkeep_rules/api_http.py",
    "src/riftkeep_rules/runtime_hardening.py",
    "src/riftkeep_rules/update_automation.py",
    "src/riftkeep_rules/release_candidate_audit.py",
    "src/riftkeep_rules/release_gate.py",
    "src/riftkeep_rules/audit.py",
    "validate_all.py",
    "audit_project.py",
    "build_stable_release_manifest.py",
    "stable_clean_install.py",
    "riftkeep.py",
    "serve_api.py",
    "web/index.html",
    "web/styles.css",
    "web/app.js",
    "contracts/product_api_contract.json",
    "contracts/ui_contract.json",
    "contracts/update_automation.schema.json",
    "contracts/runtime_hardening.schema.json",
    "contracts/release_candidate_audit.schema.json",
    "contracts/stable_release_contract.schema.json",
    "contracts/stable_release_manifest.schema.json",
    "data/canonical/stable_release_contract.json",
    "data/canonical/release_candidate_audit_contract.json",
    "data/canonical/core_rules.json",
    "data/canonical/tournament_rules.json",
    "data/canonical/cards.json",
    "data/canonical/official_errata_history.json",
    "data/canonical/compiled_rule_catalog.json",
    "data/canonical/rule_programs.json",
    "data/canonical/card_interaction_programs.json",
    "data/source/current_authority_overlay.json",
    "data/source/rule_versions/core/history.json",
    "data/source/rule_versions/tournament/history.json",
    "tests/run_update_automation_tests.py",
    "tests/run_production_hardening_tests.py",
    "tests/run_release_candidate_audit_tests.py",
    "tests/run_stable_release_tests.py",
    "RELEASE_NOTES_1.0.md",
    "KNOWN_LIMITATIONS_1.0.md",
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_stable_release_manifest(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    contract = _load(root / "data/canonical/stable_release_contract.json")
    core = _load(root / "data/canonical/core_rules.json")
    tournament = _load(root / "data/canonical/tournament_rules.json")
    cards = _load(root / "data/canonical/cards.json")
    errata = _load(root / "data/canonical/official_errata_history.json")
    overlay = _load(root / "data/source/current_authority_overlay.json")
    core_history = _load(root / "data/source/rule_versions/core/history.json")
    tournament_history = _load(root / "data/source/rule_versions/tournament/history.json")

    missing = [rel for rel in CRITICAL_ARTIFACTS if not (root / rel).is_file()]
    if missing:
        raise RuntimeError("stable release critical artifacts missing: " + ", ".join(missing))

    artifact_hashes = {
        rel: {"sha256": sha256_file(root / rel), "bytes": (root / rel).stat().st_size}
        for rel in CRITICAL_ARTIFACTS
    }
    return {
        "schemaVersion": STABLE_MANIFEST_SCHEMA_VERSION,
        "product": dict(contract["product"]),
        "compatibility": dict(contract["compatibility"]),
        "policies": dict(contract["policies"]),
        "knownLimitations": list(contract["knownLimitations"]),
        "semanticVersioning": dict(contract["semanticVersioning"]),
        "authority": {
            "coreSourceId": core_history.get("currentSourceId"),
            "coreSourceSha256": sha256_file(root / "data/source/core_rules.pdf"),
            "tournamentSourceId": tournament_history.get("currentSourceId"),
            "tournamentSourceSha256": sha256_file(root / "data/source/tournament_rules.pdf"),
            "currentFaqSourceId": overlay.get("sourceId"),
            "currentFaqSha256": sha256_file(root / "data/source/official_text/vendetta_faq_2026-08-14.txt"),
            "cardSourceSha256": (cards.get("metadata") or {}).get("sourceSha256"),
        },
        "corpus": {
            "coreRules": len(core.get("rules") or []),
            "tournamentRules": len(tournament.get("rules") or []),
            "cards": len(cards.get("cards") or []),
            "currentFaqSections": (overlay.get("localSnapshot") or {}).get("sectionCount"),
            "officialErrataEvents": errata.get("errataEventCount"),
            "errataAffectedPrintings": errata.get("effectiveCardPrintingCount"),
        },
        "certifiedReleaseSuiteCount": 19,
        "artifactHashes": artifact_hashes,
    }


def write_stable_release_manifest(root: Path) -> dict[str, Any]:
    from .runtime_hardening import atomic_write_json

    manifest = build_stable_release_manifest(root)
    atomic_write_json(Path(root) / "data/canonical/stable_release_manifest.json", manifest)
    return manifest


def validate_stable_release_manifest(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    path = root / "data/canonical/stable_release_manifest.json"
    if not path.is_file():
        return {"passed": False, "errors": ["stable_release_manifest_missing"], "artifactCount": 0}
    actual = _load(path)
    errors: list[str] = []
    try:
        expected = build_stable_release_manifest(root)
    except Exception as exc:
        return {"passed": False, "errors": [f"manifest_rebuild_failed:{type(exc).__name__}:{exc}"], "artifactCount": 0}
    for key in ("schemaVersion", "product", "compatibility", "policies", "knownLimitations", "semanticVersioning", "authority", "corpus", "certifiedReleaseSuiteCount"):
        if actual.get(key) != expected.get(key):
            errors.append(f"manifest_field_mismatch:{key}")
    actual_hashes = actual.get("artifactHashes") or {}
    expected_hashes = expected.get("artifactHashes") or {}
    if set(actual_hashes) != set(expected_hashes):
        errors.append("artifact_hash_inventory_paths_mismatch")
    for rel, expected_row in expected_hashes.items():
        actual_row = actual_hashes.get(rel) or {}
        if actual_row.get("sha256") != expected_row.get("sha256") or actual_row.get("bytes") != expected_row.get("bytes"):
            errors.append(f"artifact_hash_mismatch:{rel}")
    return {
        "passed": not errors,
        "errors": errors,
        "artifactCount": len(expected_hashes),
        "productVersion": (actual.get("product") or {}).get("version"),
        "apiVersion": (actual.get("compatibility") or {}).get("productApi"),
        "certifiedReleaseSuiteCount": actual.get("certifiedReleaseSuiteCount"),
    }
