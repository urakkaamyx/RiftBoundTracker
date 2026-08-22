#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from riftkeep_rules.authority import load_authority_status
from riftkeep_rules.version_integrity import validate_rule_version_integrity


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_report(path: Path) -> dict:
    if not path.exists():
        return {"exists": False, "passed": False, "path": str(path.relative_to(ROOT))}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"exists": True, "passed": False, "path": str(path.relative_to(ROOT)), "error": f"{type(exc).__name__}: {exc}"}
    return {
        "exists": True,
        "passed": bool(data.get("passed")),
        "path": str(path.relative_to(ROOT)),
        "modifiedAt": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        "report": data,
    }


def main() -> int:
    parser_report = ROOT / "data/validation/parser_validation.json"
    errata_report = ROOT / "data/validation/errata_validation.json"
    overlay_report = ROOT / "data/validation/current_overlay_integrity.json"
    rule_version_report = ROOT / "data/validation/rule_version_integrity.json"
    test_paths = {
        "core": ROOT / "data/validation/core_test_report.json",
        "definitions": ROOT / "data/validation/definition_lookup_test_report.json",
        "regressions": ROOT / "data/validation/regression_report.json",
        "language": ROOT / "data/validation/language_test_report.json",
        "scenarioLanguage": ROOT / "data/validation/scenario_language_test_report.json",
        "scenarioModel": ROOT / "data/validation/scenario_model_test_report.json",
        "compiler": ROOT / "data/validation/compiler_test_report.json",
        "proofEngine": ROOT / "data/validation/proof_engine_test_report.json",
        "llmInterpretation": ROOT / "data/validation/llm_interpretation_test_report.json",
        "llmExplanation": ROOT / "data/validation/llm_explanation_test_report.json",
        "goldCorpus": ROOT / "data/validation/gold_corpus_report.json",
        "cardInteractions": ROOT / "data/validation/card_interaction_test_report.json",
        "productApi": ROOT / "data/validation/product_api_test_report.json",
        "uiIntegration": ROOT / "data/validation/ui_integration_test_report.json",
        "updateAutomation": ROOT / "data/validation/update_automation_test_report.json",
        "productionHardening": ROOT / "data/validation/production_hardening_test_report.json",
        "releaseCandidateAudit": ROOT / "data/validation/release_candidate_audit_test_report.json",
        "stableRelease": ROOT / "data/validation/stable_release_test_report.json",
        "updates": ROOT / "data/validation/update_test_report.json",
    }
    tests = {k: load_report(v) for k, v in test_paths.items()}
    parser = json.loads(parser_report.read_text(encoding="utf-8")) if parser_report.exists() else {}
    errata = json.loads(errata_report.read_text(encoding="utf-8")) if errata_report.exists() else {}
    overlay_integrity = json.loads(overlay_report.read_text(encoding="utf-8")) if overlay_report.exists() else {}
    rule_version_integrity = json.loads(rule_version_report.read_text(encoding="utf-8")) if rule_version_report.exists() else validate_rule_version_integrity(ROOT)
    sources = {
        "coreRulesPdf": ROOT / "data/source/core_rules.pdf",
        "tournamentRulesPdf": ROOT / "data/source/tournament_rules.pdf",
        "cardsJson": ROOT / "data/source/riftbound_cards.json",
        "officialSourceManifest": ROOT / "data/source/official_source_manifest.json",
    }
    source_integrity = {}
    for key, path in sources.items():
        source_integrity[key] = {
            "path": str(path.relative_to(ROOT)),
            "exists": path.exists(),
            "bytes": path.stat().st_size if path.exists() else None,
            "sha256": sha256(path) if path.exists() else None,
        }
    canonical_targets = [
        ROOT / "data/canonical/core_rules.json",
        ROOT / "data/canonical/tournament_rules.json",
        ROOT / "data/canonical/cards.json",
        ROOT / "data/canonical/official_errata_history.json",
        ROOT / "data/canonical/knowledge_graph.json",
        ROOT / "data/canonical/effective_rule_overrides.json",
        ROOT / "data/canonical/compiled_rule_catalog.json",
        ROOT / "data/canonical/rule_programs.json",
        ROOT / "data/canonical/card_interaction_catalog.json",
        ROOT / "data/canonical/card_interaction_programs.json",
        ROOT / "contracts/card_interaction_catalog.schema.json",
        ROOT / "contracts/card_interaction_programs.schema.json",
        ROOT / "src/riftkeep_rules/card_interactions.py",
        ROOT / "src/riftkeep_rules/card_interaction_executor.py",
        ROOT / "contracts/product_api_contract.json",
        ROOT / "src/riftkeep_rules/product_api.py",
        ROOT / "src/riftkeep_rules/api_http.py",
        ROOT / "serve_api.py",
        ROOT / "contracts/ui_contract.json",
        ROOT / "web/index.html",
        ROOT / "web/styles.css",
        ROOT / "web/app.js",
        ROOT / "tests/run_ui_integration_tests.py",
        ROOT / "tests/run_definition_lookup_tests.py",
        ROOT / "contracts/update_automation.schema.json",
        ROOT / "src/riftkeep_rules/release_gate.py",
        ROOT / "src/riftkeep_rules/update_automation.py",
        ROOT / "update_automation.py",
        ROOT / "tests/run_update_automation_tests.py",
        ROOT / "contracts/runtime_hardening.schema.json",
        ROOT / "data/canonical/runtime_hardening_contract.json",
        ROOT / "src/riftkeep_rules/runtime_hardening.py",
        ROOT / "tests/run_production_hardening_tests.py",
        ROOT / "contracts/release_candidate_audit.schema.json",
        ROOT / "data/canonical/release_candidate_audit_contract.json",
        ROOT / "src/riftkeep_rules/release_candidate_audit.py",
        ROOT / "tests/run_release_candidate_audit_tests.py",
        ROOT / "contracts/stable_release_contract.schema.json",
        ROOT / "contracts/stable_release_manifest.schema.json",
        ROOT / "data/canonical/stable_release_contract.json",
        ROOT / "src/riftkeep_rules/release_identity.py",
        ROOT / "build_stable_release_manifest.py",
        ROOT / "stable_clean_install.py",
        ROOT / "riftkeep.py",
        ROOT / "tests/run_stable_release_tests.py",
        ROOT / "RELEASE_NOTES_1.0.md",
        ROOT / "KNOWN_LIMITATIONS_1.0.md",
        ROOT / "data/validation/runtime_hardening_integrity.json",
        ROOT / "data/validation/rule_compiler_metrics.json",
        ROOT / "contracts/llm_interpretation.schema.json",
        ROOT / "src/riftkeep_rules/llm_interpretation.py",
        ROOT / "contracts/llm_explanation.schema.json",
        ROOT / "src/riftkeep_rules/llm_explanation.py",
        ROOT / "contracts/gold_case.schema.json",
        ROOT / "data/gold/gold_corpus.json",
        ROOT / "data/gold/gold_manifest.json",
        ROOT / "data/gold/gold_c_promotions.json",
        ROOT / "data/validation/current_overlay_integrity.json",
        ROOT / "data/validation/rule_version_integrity.json",
        ROOT / "data/source/rule_versions/core/history.json",
        ROOT / "data/source/rule_versions/tournament/history.json",
        ROOT / "data/index/rules.sqlite",
    ]
    canonical_mtime = max((p.stat().st_mtime for p in canonical_targets if p.exists()), default=0)
    for row in tests.values():
        if row.get("exists"):
            mtime = (ROOT / row["path"]).stat().st_mtime
            row["freshForCurrentBuild"] = mtime >= canonical_mtime
        else:
            row["freshForCurrentBuild"] = False

    authority = load_authority_status(ROOT)
    stable_generated = [
        ROOT / "data/canonical/stable_release_manifest.json",
        ROOT / "data/validation/stable_clean_install_audit.json",
    ]
    passed = (
        bool((parser.get("core") or {}).get("passed"))
        and bool((parser.get("tournament") or {}).get("passed"))
        and bool(errata.get("passed"))
        and bool(overlay_integrity.get("passed"))
        and bool(rule_version_integrity.get("passed"))
        and all(x.get("passed") and x.get("freshForCurrentBuild") for x in tests.values())
        and all(x["exists"] for x in source_integrity.values())
        and all(p.exists() for p in canonical_targets)
        and all(p.exists() for p in stable_generated)
    )
    result = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "parserValidation": {"core": (parser.get("core") or {}).get("passed"), "tournament": (parser.get("tournament") or {}).get("passed")},
        "errataValidation": errata,
        "currentOverlayIntegrity": overlay_integrity,
        "ruleVersionIntegrity": rule_version_integrity,
        "tests": tests,
        "sourceIntegrity": source_integrity,
        "canonicalArtifactsPresent": {str(p.relative_to(ROOT)): p.exists() for p in canonical_targets},
        "stableGeneratedArtifactsPresent": {str(p.relative_to(ROOT)): p.exists() for p in stable_generated},
        "authorityStatus": authority,
        "operationalReadiness": {
            "engineValidated": passed,
            "currentGameplayAuthorityComplete": bool(authority.get("currentRulesComplete")),
            "currentGameplayBlockers": authority.get("missing") or [],
            "note": "Engine validation and current-authority completeness are independent. Default gameplay adjudication fails closed when an active official override source is not locally mirrored.",
        },
    }
    out = ROOT / "data/validation/validation_summary.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "passed": passed,
        "parser": result["parserValidation"],
        "errata": {"passed": errata.get("passed"), "events": errata.get("errataEventCount"), "printings": errata.get("effectiveCardPrintingCount")},
        "currentOverlayIntegrity": {"passed": overlay_integrity.get("passed"), "sources": overlay_integrity.get("activeOverlayCount")},
        "ruleVersionIntegrity": {"passed": rule_version_integrity.get("passed"), "families": {k: v.get("currentSourceId") for k, v in (rule_version_integrity.get("families") or {}).items()}},
        "tests": {k: {"passed": v.get("passed"), "fresh": v.get("freshForCurrentBuild"), "count": (v.get("report") or {}).get("checkCount", (v.get("report") or {}).get("caseCount"))} for k, v in tests.items()},
        "authority": result["operationalReadiness"],
        "report": str(out),
    }, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
