from __future__ import annotations

import json
from pathlib import Path

from .graph import build_graph
from .compiler import compile_semantic_ir
from .rule_compiler import compile_rule_catalog
from .rule_programs import compile_rule_programs
from .compiler_metrics import build_compiler_metrics
from .parser import load_cards, parse_numbered_pdf, validate_pdf_parse
from .retrieval import build_index
from .official_sources import compile_supplemental_sources
from .overrides import compile_effective_rule_overrides
from .authority import load_authority_status
from .card_text import compile_card_text_annotations
from .card_interactions import compile_card_interaction_catalog
from .card_interaction_executor import compile_interaction_executor_programs
from .predicates import registry_snapshot
from .errata import compile_official_errata, apply_official_errata, build_compiled_errata_history, validate_errata_history
from .source_integrity import validate_current_overlays
from .version_integrity import current_manifest_source, ensure_version_ledgers, validate_rule_version_integrity, assert_live_sources_untampered
from .runtime_hardening import atomic_write_json, validate_runtime_artifacts


def dump(path: Path, data) -> None:
    atomic_write_json(path, data)


def build(root: Path) -> dict:
    src = root / "data/source"
    canon = root / "data/canonical"
    valid = root / "data/validation"
    idx = root / "data/index/rules.sqlite"

    # The live convenience PDFs are bound to immutable version ledgers.  A direct
    # file replacement outside the stage/promote workflow must fail before parsing.
    ensure_version_ledgers(root)
    assert_live_sources_untampered(root)
    core_source = current_manifest_source(root, "core")
    tournament_source = current_manifest_source(root, "tournament")
    core = parse_numbered_pdf(src / str(core_source.get("localSnapshot") or "core_rules.pdf"), str(core_source["id"]), "RK-CR", "Riftbound Core Rules")
    tournament = parse_numbered_pdf(src / str(tournament_source.get("localSnapshot") or "tournament_rules.pdf"), str(tournament_source["id"]), "RK-TR", "Riftbound Tournament Rules")
    cards = load_cards(src / "riftbound_cards.json")
    supplemental = compile_supplemental_sources(root)
    official_errata = compile_official_errata(root)
    cards, errata_application = apply_official_errata(cards, official_errata)
    # Preserve the complete official old/new timeline as its own canonical artifact.
    # build_compiled_errata_history is idempotent for effective text and re-links the
    # compiled source records to gameplay identities for audit/update workflows.
    official_errata_history = build_compiled_errata_history(cards, official_errata)
    expected_errata_sources = {str(d.get("sourceId")) for d in official_errata.get("sourceDocuments", []) if d.get("sourceId")}
    errata_validation = validate_errata_history(official_errata_history, expected_errata_sources)
    semantic_ir = compile_semantic_ir(core)
    compiled_rule_catalog = compile_rule_catalog(core)
    rule_programs = compile_rule_programs(core)
    compiler_metrics = build_compiler_metrics(root, compiled_rule_catalog, rule_programs)
    cards = compile_card_text_annotations(cards, semantic_ir)
    card_interaction_catalog = compile_card_interaction_catalog(cards, semantic_ir, supplemental)
    card_interaction_programs = compile_interaction_executor_programs(card_interaction_catalog, core)
    graph = build_graph(core, cards)
    effective_overrides = compile_effective_rule_overrides(supplemental, core)

    core_validation = validate_pdf_parse(src / str(core_source.get("localSnapshot") or "core_rules.pdf"), core)
    tournament_validation = validate_pdf_parse(src / str(tournament_source.get("localSnapshot") or "tournament_rules.pdf"), tournament)
    validation = {
        "status": "ok" if core_validation["passed"] and tournament_validation["passed"] else "error",
        "core": core_validation,
        "tournament": tournament_validation,
        "criticalSpotChecks": {
            "347.1.a": next((r["normativeText"] for r in core["rules"] if r["ruleId"] == "347.1.a"), None),
            "347.1.b": next((r["normativeText"] for r in core["rules"] if r["ruleId"] == "347.1.b"), None),
            "705.1": next((r["normativeText"] for r in tournament["rules"] if r["ruleId"] == "705.1"), None),
        },
    }

    dump(canon / "core_rules.json", core)
    dump(canon / "tournament_rules.json", tournament)
    dump(canon / "cards.json", cards)
    dump(canon / "card_interaction_catalog.json", card_interaction_catalog)
    dump(canon / "card_interaction_programs.json", card_interaction_programs)
    dump(canon / "knowledge_graph.json", graph)
    dump(canon / "semantic_ir.json", semantic_ir)
    dump(canon / "compiled_rule_catalog.json", compiled_rule_catalog)
    dump(canon / "rule_programs.json", rule_programs)
    dump(valid / "rule_compiler_metrics.json", compiler_metrics)
    predicates = registry_snapshot()
    dump(canon / "predicate_registry.json", predicates)
    dump(canon / "supplemental_sources.json", supplemental)
    dump(canon / "official_errata.json", official_errata)
    dump(canon / "official_errata_history.json", official_errata_history)
    dump(canon / "effective_rule_overrides.json", effective_overrides)
    dump(valid / "errata_application.json", errata_application)
    dump(valid / "errata_validation.json", errata_validation)
    dump(valid / "parser_validation.json", validation)
    rule_version_integrity = validate_rule_version_integrity(root)
    dump(valid / "rule_version_integrity.json", rule_version_integrity)
    if not rule_version_integrity.get("passed"):
        raise RuntimeError("rule-version integrity failed after build: " + "; ".join(rule_version_integrity.get("errors", [])))
    build_index(idx, core, cards, supplemental)
    authority_status = load_authority_status(root)
    overlay_integrity = validate_current_overlays(root)
    dump(valid / "current_overlay_integrity.json", overlay_integrity)
    dump(valid / "source_sync_status.json", {"authorityStatus": authority_status, "supplemental": {"snapshotCount": supplemental["snapshotCount"], "documentCount": supplemental["documentCount"]}, "currentOverlayIntegrity": overlay_integrity})
    runtime_integrity = validate_runtime_artifacts(root)
    dump(valid / "runtime_hardening_integrity.json", runtime_integrity)
    if not runtime_integrity.get("passed"):
        raise RuntimeError("runtime hardening integrity failed after build: " + "; ".join(runtime_integrity.get("errors") or []))
    return {
        "coreRules": len(core["rules"]),
        "tournamentRules": len(tournament["rules"]),
        "cards": len(cards["cards"]),
        "cardInteractionPrintings": card_interaction_catalog["printingCount"],
        "cardInteractionIdentities": card_interaction_catalog["identityCount"],
        "cardInteractionClauses": card_interaction_catalog["clauseCount"],
        "cardInteractionFaqPrograms": card_interaction_catalog["faqProgramCount"],
        "cardInteractionExecutablePrograms": card_interaction_programs["validProgramCount"],
        "graphEdges": len(graph["edges"]),
        "concepts": semantic_ir["metadata"]["conceptCount"],
        "compiledSemanticRules": compiled_rule_catalog["metadata"]["ruleCount"],
        "compiledExecutableRulePrograms": rule_programs["validProgramCount"],
        "migratedAdjudicationFamilies": compiler_metrics["migratedAdjudicationFamilyCount"],
        "remainingHandCodedFamilies": compiler_metrics["remainingHandCodedFamilyCount"],
        "compiledApplicabilityRules": predicates["compiledRuleCount"],
        "parserValidation": validation["status"],
        "supplementalSnapshots": supplemental["snapshotCount"],
        "supplementalDocuments": supplemental["documentCount"],
        "officialErrataRecords": official_errata["recordCount"],
        "officialErrataCardsAffected": errata_application["cardsAffected"],
        "officialErrataValidation": "ok" if errata_validation["passed"] else "error",
        "effectiveRuleOverrides": effective_overrides["recordCount"],
        "effectiveRuleOverridesValid": effective_overrides["valid"],
        "currentAuthorityComplete": authority_status["currentRulesComplete"],
        "currentOverlayIntegrity": "ok" if overlay_integrity["passed"] else "error",
        "ruleVersionIntegrity": "ok" if rule_version_integrity["passed"] else "error",
        "runtimeHardeningIntegrity": "ok" if runtime_integrity["passed"] else "error",
        "runtimeSnapshotId": runtime_integrity.get("snapshotId"),
        "coreSourceId": core_source["id"],
        "tournamentSourceId": tournament_source["id"],
        "index": str(idx),
    }


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    print(json.dumps(build(root), indent=2))
