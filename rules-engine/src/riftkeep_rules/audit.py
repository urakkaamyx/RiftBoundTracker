from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .authority import load_authority_status
from .version_integrity import validate_rule_version_integrity
from .release_identity import validate_stable_release_manifest


def _load(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def run_project_audit(root: Path) -> dict[str, Any]:
    critical: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: Any = None, severity: str = "critical") -> None:
        row = {"name": name, "passed": bool(ok)}
        if detail is not None:
            row["detail"] = detail
        checks.append(row)
        if ok:
            return
        finding = {"code": name, "detail": detail}
        (critical if severity == "critical" else warnings).append(finding)

    required = [
        "audit_project.py", "validate_all.py", "update_core_rules.py", "update_tournament_rules.py",
        "sync_official_sources.py", "src/riftkeep_rules/audit.py", "src/riftkeep_rules/rule_updates.py",
        "src/riftkeep_rules/version_integrity.py", "src/riftkeep_rules/scenario_language.py",
        "src/riftkeep_rules/scenario_model.py", "contracts/scenario_model.schema.json",
        "src/riftkeep_rules/rule_compiler.py", "src/riftkeep_rules/rule_programs.py", "src/riftkeep_rules/compiler_metrics.py",
        "contracts/compiled_rule_catalog.schema.json", "contracts/rule_programs.schema.json",
        "src/riftkeep_rules/proof_engine.py", "contracts/proof_trace.schema.json",
        "src/riftkeep_rules/llm_interpretation.py", "src/riftkeep_rules/llm_provider.py", "contracts/llm_interpretation.schema.json",
        "src/riftkeep_rules/llm_explanation.py", "contracts/llm_explanation.schema.json",
        "contracts/gold_case.schema.json", "data/gold/gold_corpus.json", "data/gold/gold_manifest.json",
        "src/riftkeep_rules/card_interactions.py", "contracts/card_interaction_catalog.schema.json", "data/canonical/card_interaction_catalog.json", "tests/run_card_interaction_tests.py",
        "contracts/product_api_contract.json", "src/riftkeep_rules/product_api.py", "src/riftkeep_rules/api_http.py", "serve_api.py", "tests/run_product_api_tests.py",
        "contracts/ui_contract.json", "web/index.html", "web/styles.css", "web/app.js", "tests/run_ui_integration_tests.py",
        "contracts/update_automation.schema.json", "src/riftkeep_rules/release_gate.py", "src/riftkeep_rules/update_automation.py", "update_automation.py", "tests/run_update_automation_tests.py",
        "contracts/runtime_hardening.schema.json", "data/canonical/runtime_hardening_contract.json", "src/riftkeep_rules/runtime_hardening.py", "tests/run_production_hardening_tests.py", "data/validation/runtime_hardening_integrity.json",
        "contracts/release_candidate_audit.schema.json", "data/canonical/release_candidate_audit_contract.json", "src/riftkeep_rules/release_candidate_audit.py", "tests/run_release_candidate_audit_tests.py", "data/validation/release_candidate_audit.json", "data/validation/m18_conformance_report.json",
        "contracts/stable_release_contract.schema.json", "contracts/stable_release_manifest.schema.json", "data/canonical/stable_release_contract.json", "data/canonical/stable_release_manifest.json", "src/riftkeep_rules/release_identity.py", "build_stable_release_manifest.py", "stable_clean_install.py", "riftkeep.py", "tests/run_stable_release_tests.py", "data/validation/stable_clean_install_audit.json", "RELEASE_NOTES_1.0.md", "KNOWN_LIMITATIONS_1.0.md",
        "generate_gold_corpus.py", "tests/run_gold_corpus_tests.py", "tests/run_definition_lookup_tests.py", "tests/run_scenario_language_tests.py", "tests/run_scenario_model_tests.py", "tests/run_compiler_tests.py", "tests/run_proof_engine_tests.py", "tests/run_llm_interpretation_tests.py", "tests/run_llm_explanation_tests.py", "data/source/rule_versions/core/history.json",
        "data/source/rule_versions/tournament/history.json", "data/source/core_rules.pdf",
        "data/source/tournament_rules.pdf", "data/source/riftbound_cards.json",
        "data/source/official_source_manifest.json", "data/canonical/core_rules.json",
        "data/canonical/tournament_rules.json", "data/canonical/cards.json", "data/index/rules.sqlite",
    ]
    missing_files = [x for x in required if not (root / x).exists()]
    check("required_recovery_files_present", not missing_files, missing_files)

    core = _load(root / "data/canonical/core_rules.json", {}) or {}
    tr = _load(root / "data/canonical/tournament_rules.json", {}) or {}
    cards = _load(root / "data/canonical/cards.json", {}) or {}
    core_rules = list(core.get("rules", []))
    tr_rules = list(tr.get("rules", []))
    card_rows = list(cards.get("cards", []))

    check("core_rule_count_2381", len(core_rules) == 2381, len(core_rules))
    check("tournament_rule_count_935", len(tr_rules) == 935, len(tr_rules))
    check("combined_numbered_rule_count_3316", len(core_rules) + len(tr_rules) == 3316, len(core_rules) + len(tr_rules))
    check("card_count_1304", len(card_rows) == 1304, len(card_rows))
    check("core_no_duplicate_visible_ids", len({r.get('ruleId') for r in core_rules}) == len(core_rules))
    check("tournament_no_duplicate_visible_ids", len({r.get('ruleId') for r in tr_rules}) == len(tr_rules))
    check("core_no_duplicate_internal_ids", len({r.get('internalRuleId') for r in core_rules}) == len(core_rules))
    check("tournament_no_duplicate_internal_ids", len({r.get('internalRuleId') for r in tr_rules}) == len(tr_rules))
    check("core_no_empty_numbered_bodies", all(str(r.get("text") or "").strip() for r in core_rules))
    check("tournament_no_empty_numbered_bodies", all(str(r.get("text") or "").strip() for r in tr_rules))
    by_core = {r.get("ruleId"): r for r in core_rules}
    check("critical_347_1_b_preserved", (by_core.get("347.1.b") or {}).get("normativeText") == "When that Chain closes, Focus passes to the next Player in Turn Order.", (by_core.get("347.1.b") or {}).get("normativeText"))

    parser = _load(root / "data/validation/parser_validation.json", {}) or {}
    check("core_parser_validation_passes", bool((parser.get("core") or {}).get("passed")), parser.get("core"))
    check("tournament_parser_validation_passes", bool((parser.get("tournament") or {}).get("passed")), parser.get("tournament"))
    errata = _load(root / "data/validation/errata_validation.json", {}) or {}
    check("errata_validation_passes", bool(errata.get("passed")), errata)
    check("errata_event_count_63", errata.get("errataEventCount") == 63, errata.get("errataEventCount"))
    check("errata_affected_printings_91", errata.get("effectiveCardPrintingCount") == 91, errata.get("effectiveCardPrintingCount"))

    overlay = _load(root / "data/validation/current_overlay_integrity.json", {}) or {}
    check("current_overlay_integrity_passes", bool(overlay.get("passed")), overlay.get("errors"))
    vendetta = next((x for x in overlay.get("sources", []) if x.get("sourceId") == "vendetta-faq-2026-08-14"), {})
    check("vendetta_faq_has_35_sections", vendetta.get("sectionCount") == 35, vendetta.get("sectionCount"))
    overrides = _load(root / "data/canonical/effective_rule_overrides.json", {}) or {}
    check("effective_rule_overrides_valid", bool(overrides.get("valid")) and overrides.get("recordCount") == 1, overrides)

    compiled_catalog = _load(root / "data/canonical/compiled_rule_catalog.json", {}) or {}
    rule_programs = _load(root / "data/canonical/rule_programs.json", {}) or {}
    compiler_metrics = _load(root / "data/validation/rule_compiler_metrics.json", {}) or {}
    check("compiled_rule_catalog_has_2381_rules", (compiled_catalog.get("metadata") or {}).get("ruleCount") == 2381 and len(compiled_catalog.get("rules", [])) == 2381, (compiled_catalog.get("metadata") or {}))
    check("compiled_rule_catalog_safe_non_executable_default", (compiled_catalog.get("metadata") or {}).get("executableRuleCount") == 0, (compiled_catalog.get("metadata") or {}))
    check("rule_programs_all_valid", rule_programs.get("programCount") == 8 and rule_programs.get("validProgramCount") == 8, {"programCount": rule_programs.get("programCount"), "validProgramCount": rule_programs.get("validProgramCount")})
    check("m8_migrated_eight_adjudication_families", compiler_metrics.get("migratedAdjudicationFamilyCount") == 8, compiler_metrics)

    version_integrity = validate_rule_version_integrity(root)
    check("rule_version_integrity_passes", bool(version_integrity.get("passed")), version_integrity.get("errors"))
    # Persist the live result so validation/audit never relies on a stale version report.
    (root / "data/validation/rule_version_integrity.json").write_text(json.dumps(version_integrity, ensure_ascii=False, indent=2), encoding="utf-8")

    expected_tests = {
        "core_test_report.json": 164,
        "definition_lookup_test_report.json": 120,
        "regression_report.json": 99,
        "language_test_report.json": 42,
        "scenario_language_test_report.json": 43,
        "scenario_model_test_report.json": 58,
        "compiler_test_report.json": 42,
        "proof_engine_test_report.json": 72,
        "llm_interpretation_test_report.json": 84,
        "llm_explanation_test_report.json": 80,
        "gold_corpus_report.json": 34,
        "card_interaction_test_report.json": 74,
        "product_api_test_report.json": 132,
        "ui_integration_test_report.json": 148,
        "update_automation_test_report.json": 70,
        "production_hardening_test_report.json": 74,
        "release_candidate_audit_test_report.json": 48,
        "stable_release_test_report.json": 191,
        "update_test_report.json": 29,
    }
    for filename, expected in expected_tests.items():
        report = _load(root / "data/validation" / filename, {}) or {}
        count = report.get("checkCount", report.get("caseCount"))
        check(f"{filename}_passes", bool(report.get("passed")), report.get("failures"))
        check(f"{filename}_baseline_count", isinstance(count, int) and count >= expected, {"expectedMinimum": expected, "actual": count})

    gold = _load(root / "data/gold/gold_corpus.json", {}) or {}
    gold_manifest = _load(root / "data/gold/gold_manifest.json", {}) or {}
    gold_metrics = _load(root / "data/validation/gold_corpus_metrics.json", {}) or {}
    gold_ids = [x.get("caseId") for x in gold.get("cases", [])]
    check("gold_corpus_frozen_1846", gold.get("frozen") is True and gold.get("caseCount") == 1846 and len(gold_ids) == 1846, {"caseCount": gold.get("caseCount"), "actualRows": len(gold_ids)})
    check("gold_corpus_case_ids_unique", len(set(gold_ids)) == len(gold_ids), {"duplicates": len(gold_ids) - len(set(gold_ids))})
    check("gold_corpus_not_engine_derived", gold.get("derivedExpectationsFromEngine") is False and all(x.get("derivedFromEngine") is False for x in gold.get("cases", [])))
    check("gold_manifest_frozen", gold_manifest.get("frozen") is True and (gold_manifest.get("policy") or {}).get("runnerMayRegenerateExpectations") is False, gold_manifest.get("policy"))
    check("gold_metrics_thresholds", gold_metrics.get("totalCases") == 1846 and gold_metrics.get("goldASemanticGroups") == 99 and gold_metrics.get("realCardRecordsCovered") == 1304 and gold_metrics.get("currentFaqSectionsCovered") == 35 and gold_metrics.get("officialErrataEventsCovered") == 63 and gold_metrics.get("updateDiffFixturesCovered") == 12 and gold_metrics.get("forwardCardInteractionFixtures") == 34 and gold_metrics.get("goldCPromotedReleaseGating") == 16 and gold_metrics.get("goldCRemainingReportOnly") == 18, gold_metrics)

    card_interactions = _load(root / "data/canonical/card_interaction_catalog.json", {}) or {}
    card_programs = _load(root / "data/canonical/card_interaction_programs.json", {}) or {}
    card_promotions = _load(root / "data/gold/gold_c_promotions.json", {}) or {}
    card_metrics = _load(root / "data/validation/card_interaction_metrics.json", {}) or {}
    check("card_interaction_catalog_all_1304_printings", card_interactions.get("printingCount") == 1304 and len(card_interactions.get("printings", [])) == 1304, card_interactions.get("printingCount"))
    check("card_interaction_catalog_34_faq_programs", card_interactions.get("faqProgramCount") == 34 and len(card_interactions.get("faqPrograms", [])) == 34, card_interactions.get("faqProgramCount"))
    check("card_interaction_catalog_structural_compiler_nonadjudicative", (card_interactions.get("policy") or {}).get("clauseClassificationIsStructuralNotAdjudicative") is True, card_interactions.get("policy"))
    check("card_interaction_executor_16_source_guarded_programs", card_programs.get("programCount") == 16 and card_programs.get("validProgramCount") == 16 and all(x.get("valid") and x.get("executable") for x in card_programs.get("programs", [])), {"programCount": card_programs.get("programCount"), "validProgramCount": card_programs.get("validProgramCount")})
    check("card_interaction_promotions_frozen_16_of_34", card_promotions.get("frozen") is True and card_promotions.get("derivedExpectationsFromEngine") is False and card_promotions.get("promotionCount") == 16 and card_promotions.get("remainingReportOnlyCount") == 18, card_promotions)
    check("card_interaction_metrics_m13_gate", card_metrics.get("printingCount") == 1304 and card_metrics.get("faqProgramCount") == 34 and card_metrics.get("goldCFixtureCount") == 34 and card_metrics.get("goldCPromotedExecutable") == 16 and card_metrics.get("goldCRemainingReportOnly") == 18 and card_metrics.get("validExecutableProgramCount") == 16 and card_metrics.get("structuralContextAloneAppliesGameRules") is False and card_metrics.get("guardedExecutorCanApplyGameRules") is True, card_metrics)

    product_contract = _load(root / "contracts/product_api_contract.json", {}) or {}
    product_metrics = _load(root / "data/validation/product_api_metrics.json", {}) or {}
    check("product_api_contract_v1", product_contract.get("schemaVersion") == 1 and product_contract.get("apiVersion") == "v1", product_contract)
    check("product_api_engine_authority_boundary", (product_contract.get("policy") or {}).get("engineIsAuthority") is True and (product_contract.get("policy") or {}).get("transportContainsNoAdjudicationLogic") is True, product_contract.get("policy"))
    check("product_api_no_filesystem_or_fuzzy_identity", (product_contract.get("policy") or {}).get("filesystemPathsExposed") is False and (product_contract.get("policy") or {}).get("fuzzyCardIdentityLookup") is False, product_contract.get("policy"))
    check("product_api_metrics_m14_gate", product_metrics.get("apiVersion") == "v1" and len(product_metrics.get("serviceMethods") or []) == 8 and product_metrics.get("httpRouteCount") == 8 and product_metrics.get("currentAuthorityComplete") is True and product_metrics.get("loopbackDefault") is True and product_metrics.get("maxBodyBytes") == 65536 and product_metrics.get("filesystemPathsExposed") is False, product_metrics)

    ui_contract = _load(root / "contracts/ui_contract.json", {}) or {}
    ui_metrics = _load(root / "data/validation/ui_integration_metrics.json", {}) or {}
    ui_policy = ui_contract.get("policy") or {}
    check("ui_contract_m15_v1", ui_contract.get("schemaVersion") == 1 and ui_contract.get("uiVersion") == "m15-v1", ui_contract)
    check("ui_product_api_only_boundary", ui_policy.get("productApiIsOnlyDataAuthority") is True and ui_policy.get("browserAdjudicationLogic") is False and ui_policy.get("browserEvidenceSelectionLogic") is False and ui_policy.get("browserRuleSemantics") is False, ui_policy)
    check("ui_offline_same_origin_boundary", ui_policy.get("sameOriginApiOnly") is True and ui_policy.get("externalRuntimeDependencies") is False and ui_policy.get("dynamicHtmlInjection") is False and ui_policy.get("filesystemPathsExposed") is False, ui_policy)
    check("ui_metrics_m15_gate", ui_metrics.get("checkCount", 0) >= 148 and ui_metrics.get("staticRouteCount") == 4 and ui_metrics.get("externalRuntimeDependencies") == 0 and ui_metrics.get("sameOriginApiOnly") is True and ui_metrics.get("dynamicHtmlInjection") is False and ui_metrics.get("browserAdjudicationLogic") is False and ui_metrics.get("browserEvidenceSelectionLogic") is False and ui_metrics.get("accessibilityLandmarks") is True and ui_metrics.get("responsive") is True, ui_metrics)

    update_automation = _load(root / "data/validation/update_automation_test_report.json", {}) or {}
    update_metrics = update_automation.get("metrics") or {}
    check("update_automation_schema_v1", update_metrics.get("schemaVersion") == 1, update_metrics)
    check("update_automation_candidate_kinds", set(update_metrics.get("supportedCandidateKinds") or []) == {"core_rules_pdf", "tournament_rules_pdf", "official_snapshot", "reviewed_file"}, update_metrics.get("supportedCandidateKinds"))
    check("update_automation_explicit_human_review", update_metrics.get("explicitHumanReviewForMaterialChanges") is True, update_metrics)
    check("update_automation_isolated_rehearsal", update_metrics.get("isolatedRehearsal") is True, update_metrics)
    check("update_automation_hash_bound_publish", update_metrics.get("hashBoundPublishBundle") is True, update_metrics)
    check("update_automation_stale_baseline_protection", update_metrics.get("staleBaselineProtection") is True, update_metrics)
    check("update_automation_post_publish_gate", update_metrics.get("postPublishReleaseGate") is True, update_metrics)
    check("update_automation_rollback_on_failure", update_metrics.get("rollbackOnGateFailure") is True, update_metrics)
    check("update_automation_official_host_allowlist", update_metrics.get("registeredOfficialHostAllowlist") is True, update_metrics)
    check("update_automation_sealed_transaction_documents", update_metrics.get("sealedTransactionDocuments") is True, update_metrics)
    check("update_automation_certified_release_suite_count", update_metrics.get("certifiedReleaseTestCount") == 19, update_metrics)

    runtime_contract = _load(root / "data/canonical/runtime_hardening_contract.json", {}) or {}
    runtime_integrity = _load(root / "data/validation/runtime_hardening_integrity.json", {}) or {}
    production_hardening = _load(root / "data/validation/production_hardening_test_report.json", {}) or {}
    runtime_metrics = production_hardening.get("metrics") or {}
    runtime_policy = runtime_contract.get("policies") or {}
    check("runtime_hardening_contract_v1", runtime_contract.get("schemaVersion") == 1, runtime_contract)
    check("runtime_hardening_integrity_passes", runtime_integrity.get("passed") is True and runtime_integrity.get("artifactCount") == 18, {"passed": runtime_integrity.get("passed"), "artifactCount": runtime_integrity.get("artifactCount"), "errors": runtime_integrity.get("errors")})
    check("runtime_hardening_sqlite_schema_v1", (runtime_integrity.get("sqlite") or {}).get("passed") is True and (runtime_integrity.get("sqlite") or {}).get("userVersion") == 1, runtime_integrity.get("sqlite"))
    check("runtime_hardening_offline_serving", runtime_integrity.get("networkRequiredForServing") is False and runtime_metrics.get("networkRequiredForServing") is False, {"integrity": runtime_integrity.get("networkRequiredForServing"), "metrics": runtime_metrics.get("networkRequiredForServing")})
    check("runtime_hardening_cache_and_adjudication_policy", (runtime_contract.get("cache") or {}).get("bounded") is True and (runtime_contract.get("cache") or {}).get("threadSafe") is True and (runtime_contract.get("cache") or {}).get("deepCopyResults") is True and (runtime_contract.get("cache") or {}).get("adjudicationCached") is False and runtime_metrics.get("adjudicationCached") is False and (runtime_metrics.get("searchCache") or {}).get("maxEntries") == 256, {"cache": runtime_contract.get("cache"), "metrics": runtime_metrics})
    check("runtime_hardening_atomic_index", runtime_metrics.get("atomicIndexReplacement") is True, runtime_metrics)
    check("runtime_hardening_drift_fail_closed", runtime_metrics.get("runtimeDriftFailClosed") is True, runtime_metrics)
    check("runtime_hardening_corruption_fail_closed", runtime_metrics.get("startupCorruptionFailClosed") is True, runtime_metrics)
    check("runtime_hardening_contract_fail_closed", runtime_policy.get("failStartupOnCorruption") is True and runtime_policy.get("failClosedOnRuntimeDrift") is True and runtime_policy.get("readOnlySqliteAtRuntime") is True and runtime_policy.get("atomicCanonicalWrites") is True and runtime_policy.get("networkRequiredForServing") is False, runtime_policy)

    release_candidate = _load(root / "data/validation/release_candidate_audit.json", {}) or {}
    m18_conformance = _load(root / "data/validation/m18_conformance_report.json", {}) or {}
    release_candidate_tests = _load(root / "data/validation/release_candidate_audit_test_report.json", {}) or {}
    check("m18_release_candidate_zero_blockers", release_candidate.get("passed") is True and release_candidate.get("blockingFindingCount") == 0 and (release_candidate.get("findingCounts") or {}).get("Critical") == 0 and (release_candidate.get("findingCounts") or {}).get("High") == 0, {"passed": release_candidate.get("passed"), "blockers": release_candidate.get("blockingFindingCount"), "findings": release_candidate.get("findingCounts")})
    check("m18_conformance_ready", m18_conformance.get("releaseCandidateReady") is True and m18_conformance.get("criticalHighFindings") == 0, m18_conformance)
    check("m18_adversarial_audit_gate", release_candidate_tests.get("passed") is True and release_candidate_tests.get("checkCount") == 48, release_candidate_tests)

    stable_contract = _load(root / "data/canonical/stable_release_contract.json", {}) or {}
    stable_manifest = _load(root / "data/canonical/stable_release_manifest.json", {}) or {}
    stable_manifest_validation = validate_stable_release_manifest(root)
    stable_clean = _load(root / "data/validation/stable_clean_install_audit.json", {}) or {}
    stable_tests = _load(root / "data/validation/stable_release_test_report.json", {}) or {}
    check("stable_1_0_contract_identity", (stable_contract.get("product") or {}).get("version") == "1.0.0" and (stable_contract.get("product") or {}).get("releaseLine") == "stable" and (stable_contract.get("compatibility") or {}).get("productApi") == "v1", stable_contract)
    check("stable_1_0_manifest_identity", (stable_manifest.get("product") or {}).get("version") == "1.0.0" and stable_manifest.get("certifiedReleaseSuiteCount") == 19 and len(stable_manifest.get("artifactHashes") or {}) >= 30, {"product": stable_manifest.get("product"), "suiteCount": stable_manifest.get("certifiedReleaseSuiteCount"), "artifactCount": len(stable_manifest.get("artifactHashes") or {})})
    check("stable_1_0_manifest_hash_inventory", stable_manifest_validation.get("passed") is True and stable_manifest_validation.get("artifactCount") == len(stable_manifest.get("artifactHashes") or {}), stable_manifest_validation)
    check("stable_1_0_clean_install", stable_clean.get("passed") is True and stable_clean.get("selfCheckPassed") is True and stable_clean.get("apiPassed") is True and stable_clean.get("uiPassed") is True and stable_clean.get("definitionPassed") is True and stable_clean.get("readOnlyIndexPassed") is True and stable_clean.get("networkRequired") is False, stable_clean)
    check("stable_1_0_acceptance_gate", stable_tests.get("passed") is True and stable_tests.get("checkCount") == 191 and (stable_tests.get("metrics") or {}).get("productVersion") == "1.0.0" and (stable_tests.get("metrics") or {}).get("certifiedReleaseSuiteCount") == 19, stable_tests)

    authority = load_authority_status(root)
    check("current_gameplay_authority_complete", bool(authority.get("currentRulesComplete")), authority.get("missing"))
    for coverage_key, warning_code in (
        ("officialPatchNoteHistory", "historical_patch_note_bodies_incomplete"),
        ("historicalFaqArchive", "historical_faq_bodies_incomplete"),
    ):
        cov = (authority.get("coverage") or {}).get(coverage_key) or {}
        if not cov.get("complete"):
            warnings.append({"code": warning_code, "detail": cov.get("missing") or [], "blocking": False})

    # These two warning classes are intentionally non-blocking.  No other source
    # family is allowed to be partial without being surfaced as a critical problem.
    for key, cov in (authority.get("coverage") or {}).items():
        if key in {"officialPatchNoteHistory", "historicalFaqArchive"}:
            continue
        check(f"authority_coverage_{key}", bool(cov.get("complete")), cov.get("missing"))

    report = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "passed": not critical,
        "criticalIssueCount": len(critical),
        "warningCount": len(warnings),
        "criticalIssues": critical,
        "warnings": warnings,
        "checks": checks,
        "baseline": {
            "coreRules": len(core_rules), "tournamentRules": len(tr_rules), "combinedNumberedRules": len(core_rules) + len(tr_rules),
            "cards": len(card_rows), "currentGameplayAuthorityComplete": authority.get("currentRulesComplete"),
        },
        "note": "The historical patch-note and superseded-FAQ archive warnings are non-blocking for current gameplay authority but must remain visible until their complete official bodies are mirrored.",
    }
    out = root / "data/validation/project_audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
