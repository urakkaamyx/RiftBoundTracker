#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from riftkeep_rules.engine import RulesEngine
from riftkeep_rules.predicates import evaluate_rule_applicability
from riftkeep_rules.rule_compiler import compile_rule_catalog, parse_conditions, parse_modalities
from riftkeep_rules.rule_programs import compile_rule_programs, evaluate_rule_programs
from riftkeep_rules.scenario import Fact, Truth

checks = 0
failures: list[dict[str, str]] = []


def check(name: str, ok: bool, detail: object = "") -> None:
    global checks
    checks += 1
    if not ok:
        failures.append({"check": name, "detail": str(detail)})


core = json.loads((ROOT / "data/canonical/core_rules.json").read_text(encoding="utf-8"))
catalog = json.loads((ROOT / "data/canonical/compiled_rule_catalog.json").read_text(encoding="utf-8"))
programs = json.loads((ROOT / "data/canonical/rule_programs.json").read_text(encoding="utf-8"))
metrics = json.loads((ROOT / "data/validation/rule_compiler_metrics.json").read_text(encoding="utf-8"))
by_catalog = {r["ruleId"]: r for r in catalog["rules"]}
by_core = {r["ruleId"]: r for r in core["rules"]}

# T68/T70 — full structural contract and safe non-executable default.
check("compiled catalog has all 2381 Core Rules", catalog["metadata"]["ruleCount"] == 2381 and len(catalog["rules"]) == 2381, catalog["metadata"])
check("structural catalog has zero implicitly executable rules", catalog["metadata"]["executableRuleCount"] == 0 and all(r["executable"] is False for r in catalog["rules"]), catalog["metadata"])
check("every compiled rule has source hash", all(len(r.get("sourceTextHash", "")) == 64 for r in catalog["rules"]))
check("every compiled rule preserves source/internal IDs", all(r.get("ruleId") and r.get("internalRuleId") and r.get("sourceId") for r in catalog["rules"]))
check("explicit Core cross-reference becomes dependency", "197" in by_catalog["107.1.b"]["dependencies"], by_catalog["107.1.b"])

# T69 — modality and condition parsing.
check("cannot rule is prohibition", "prohibition" in by_catalog["103.2.d.3"]["modalities"], by_catalog["103.2.d.3"])
check("cannot rule is not false positive permission", "permission" not in by_catalog["103.2.d.3"]["modalities"], by_catalog["103.2.d.3"])
check("only restriction is recognized", "restriction" in by_catalog["054.2"]["modalities"], by_catalog["054.2"])
check("must requirement is represented somewhere", catalog["metadata"]["modalityCounts"].get("requirement", 0) > 0, catalog["metadata"])
check("combat replacement rule is replacement tagged", "replacement" in by_catalog["465.2.c.5"]["effectTypes"], by_catalog["465.2.c.5"])
check("leading When clause direction parsed", by_catalog["465.2.c.5"]["conditions"] and by_catalog["465.2.c.5"]["conditions"][0]["connector"] == "when", by_catalog["465.2.c.5"])
conds, effect, confidence = parse_conditions("If A is true, do B unless C is true")
check("unless is represented as negative condition", any(c.get("connector") == "unless" and c.get("polarity") == "negative" for c in conds), conds)
check("negative permission masking works standalone", parse_modalities("This cannot be played.") == ["prohibition"], parse_modalities("This cannot be played."))

# T71 — all initial programs are guarded and valid.
# 15 as of RiftKeep 1.0.1's Deck Construction Obligation Integration Fix: the original 8 plus 7
# Rule 103 (Deck Construction) programs (champion_legend_count, main_deck_minimum,
# same_name_copy_limit, signature_limit, rune_deck_count, battlefield_duplicate_limit,
# battlefield_count_requirement).
check("fifteen executable Rule Programs compiled", programs["programCount"] == 15 and programs["validProgramCount"] == 15, (programs["programCount"], programs["validProgramCount"]))
check("every program carries source text guard hashes", all(p.get("sourceTextGuardHashes") and p.get("valid") and p.get("executable") for p in programs["programs"]))
check("program obligations are unique", len({p["obligation"] for p in programs["programs"]}) == 15)

# Source drift must fail closed at compile time.
mutated = copy.deepcopy(core)
for r in mutated["rules"]:
    if r["ruleId"] == "415.1.b":
        r["normativeText"] += " SYNTHETIC CHANGE"
        break
mutated_programs = compile_rule_programs(mutated)
ready_mut = next(p for p in mutated_programs["programs"] if p["programId"] == "ready-binary-state")
check("compile-time rule text drift disables program", ready_mut["valid"] is False and ready_mut["executable"] is False and "source_text_changed:415.1.b" in ready_mut["validationErrors"], ready_mut)

# T72 — evaluator behavior and runtime drift guard.
ready_fact = [Fact("unit_already_ready", Truth.TRUE, "test")]
out, consumed, diag = evaluate_rule_programs(programs, ["ready_state"], ready_fact, by_core, evaluate_rule_applicability)
check("TRUE fact executes Ready program", consumed == {"ready_state"} and out and out[0]["verdict"] == "no", (out, consumed, diag))
false_fact = [Fact("unit_already_ready", Truth.FALSE, "test")]
out, consumed, diag = evaluate_rule_programs(programs, ["ready_state"], false_fact, by_core, evaluate_rule_applicability)
check("FALSE fact does not invent permission", consumed == {"ready_state"} and out and out[0]["truth"] == "unknown" and out[0]["verdict"] == "conditional", (out, consumed, diag))
out, consumed, diag = evaluate_rule_programs(programs, ["ready_state"], [], by_core, evaluate_rule_applicability)
check("UNKNOWN fact uses explicit conditional fallback", consumed == {"ready_state"} and out and out[0]["truth"] == "unknown", (out, consumed, diag))

runtime_drift_rules = copy.deepcopy(by_core)
runtime_drift_rules["415.1.b"] = dict(runtime_drift_rules["415.1.b"])
runtime_drift_rules["415.1.b"]["normativeText"] += " SYNTHETIC RUNTIME CHANGE"
out, consumed, diag = evaluate_rule_programs(programs, ["ready_state"], ready_fact, runtime_drift_rules, evaluate_rule_applicability)
check("runtime rule text drift refuses execution", not out and not consumed and any(d.get("reason") == "runtime_source_drift" for d in diag), diag)

# Ordered cases: Exhaust-as-cost must choose the stronger first case.
exhaust_facts = [Fact("object_already_exhausted", Truth.TRUE, "test"), Fact("exhaust_is_cost", Truth.TRUE, "test")]
out, consumed, diag = evaluate_rule_programs(programs, ["exhaust_state"], exhaust_facts, by_core, evaluate_rule_applicability)
check("ordered program cases choose Exhaust-cost consequence", out and "cost cannot be paid" in out[0]["claim"], out)

# T73/T74 — migrated engine outcomes are program-backed, and legacy branches are gone.
engine = RulesEngine(ROOT, require_current_authority=False)
examples = {
    "discard-to-trash": "If I discard a card, does it go to my Trash?",
    "replace-not-play": "If an effect replaces a card with a token, was the token played?",
    "ready-binary-state": "If an effect tells me to Ready a unit that is already Ready, does it become Ready again?",
    "exhaust-binary-state-and-cost": "Can I Exhaust a unit that is already Exhausted to pay an Exhaust cost?",
    "stun-binary-state": "If my unit is already Stunned and an effect tries to Stun it again, is it Stunned again?",
    "play-location-not-target": "Does playing a unit to a battlefield target that battlefield?",
    "combat-damage-replacement-assignment": "Do replacement effects that modify combat damage apply during combat damage assignment?",
    "trigger-condition-snapshot": "If a triggered ability uses information from its trigger condition, is it checked then or on resolution?",
}
for program_id, question in examples.items():
    ruling = engine.ask(question)["issues"][0]["ruling"]
    used = [o.get("ruleProgram", {}).get("programId") for o in ruling.get("outcomes", [])]
    check(f"engine outcome uses Rule Program {program_id}", program_id in used, used)

adjudicator_src = (ROOT / "src/riftkeep_rules/adjudicator.py").read_text(encoding="utf-8")
for obligation in ["discard_to_trash", "replacement_not_play", "ready_state", "exhaust_state", "stun_state", "targeting_permission_restriction", "combat_replacement_assignment", "trigger_snapshot"]:
    check(f"legacy branch removed: {obligation}", f'if "{obligation}" in obligations' not in adjudicator_src)

# T75 — coverage metrics are durable and internally consistent.
check("coverage metrics report 2381 semantic rules", metrics.get("semanticRuleCount") == 2381, metrics)
check("coverage metrics report eight migrated families", metrics.get("migratedAdjudicationFamilyCount") == 8, metrics)
check("coverage metrics report fewer remaining hand-coded families", isinstance(metrics.get("remainingHandCodedFamilyCount"), int) and metrics["remainingHandCodedFamilyCount"] < 47, metrics)
check("replacement coverage metric is nonzero", metrics.get("replacementTaggedRuleCount", 0) > 0, metrics)

report = {"passed": not failures, "checkCount": checks, "failureCount": len(failures), "failures": failures}
(ROOT / "data/validation/compiler_test_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["passed"] else 1)
