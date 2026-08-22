#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import riftkeep_rules.engine as engine_module
from riftkeep_rules.engine import RulesEngine
from riftkeep_rules.proof_engine import build_proof_trace, verify_proof_trace

checks = 0
failures: list[dict[str, str]] = []


def check(name: str, ok: bool, detail: object = "") -> None:
    global checks
    checks += 1
    if not ok:
        failures.append({"check": name, "detail": str(detail)})


def ask(engine: RulesEngine, question: str) -> dict:
    result = engine.ask(question)
    check(f"question returned an issue: {question[:42]}", bool(result.get("issues")), result)
    return result["issues"][0] if result.get("issues") else {}


def accepted_ids(trace: dict) -> set[str]:
    return {str(x.get("evidenceId")) for x in trace.get("acceptedEvidence", []) if x.get("evidenceId")}


def rejected_reason(trace: dict, eid: str) -> str | None:
    row = next((x for x in trace.get("rejectedEvidence", []) if x.get("evidenceId") == eid), None)
    return row.get("reason") if row else None


def app(trace: dict, rid: str) -> dict:
    return next((x for x in trace.get("applicability", []) if str(x.get("ruleId")) == rid), {})


engine = RulesEngine(ROOT, require_current_authority=False)
compiled_catalog = json.loads((ROOT / "data/canonical/compiled_rule_catalog.json").read_text(encoding="utf-8"))
contract = json.loads((ROOT / "contracts/proof_trace.schema.json").read_text(encoding="utf-8"))

# T78 — proof contract is versioned and complete.
required_keys = {
    "schemaVersion", "issue", "rulingStatus", "effectiveVerdict", "steps",
    "acceptedEvidence", "rejectedEvidence", "applicability", "precedence",
    "conflicts", "rulePrograms", "orderedChains", "stateTransitions",
    "dependencies", "completeness", "verification",
}
check("proof contract schema version is 1", contract.get("properties", {}).get("schemaVersion", {}).get("const") == 1, contract)
check("proof contract requires all M9 trace fields", required_keys <= set(contract.get("required", [])), contract.get("required"))

# T79/T80/T81 — simple decision: facts, acceptance, rejection, applicability.
play = ask(engine, "Can I play a unit directly to a battlefield I control?")
pt = play.get("proofTrace") or {}
check("normal issue exposes proofTrace", bool(pt), play.keys())
check("normal decided proof verifies", (pt.get("verification") or {}).get("passed") is True, pt.get("verification"))
check("trace effective verdict matches ruling", pt.get("effectiveVerdict") == (play.get("ruling", {}).get("effectiveVerdict") or {}).get("verdict") == "yes", (pt.get("effectiveVerdict"), play.get("ruling")))
check("accepted play basis contains 355.2 and 355.2.a", {"R:355.2", "R:355.2.a"} <= accepted_ids(pt), pt.get("acceptedEvidence"))
check("accepted real evidence exists in evidence catalog", all(x.get("presentInCatalog") for x in pt.get("acceptedEvidence", [])), pt.get("acceptedEvidence"))
check("355.2.a applicability is TRUE", app(pt, "355.2.a").get("applicability") == "true", pt.get("applicability"))
check("190.3.a.1 applicability is FALSE in controlled battlefield scenario", app(pt, "190.3.a.1").get("applicability") == "false", pt.get("applicability"))
check("355.2.b applicability remains UNKNOWN without special permission", app(pt, "355.2.b").get("applicability") == "unknown", pt.get("applicability"))
check("FALSE applicability is explicitly rejected", rejected_reason(pt, "R:190.3.a.1") == "applicability_false", pt.get("rejectedEvidence"))
check("UNKNOWN applicability is explicitly rejected", rejected_reason(pt, "R:355.2.b") == "applicability_unknown", pt.get("rejectedEvidence"))
check("unneeded evidence is explicitly classified", any(x.get("reason") == "context_not_required_for_selected_conclusion" for x in pt.get("rejectedEvidence", [])), pt.get("rejectedEvidence"))
check("proof ends with explicit conclusion step", bool(pt.get("steps")) and pt["steps"][-1].get("kind") == "conclusion", pt.get("steps"))

# Replacement ordering: explicit applicability and ordering family.
repl = ask(engine, "If two replacement effects apply to the same event affecting my unit, who chooses their order?")
rt = repl["proofTrace"]
check("replacement-order proof verifies", rt["verification"]["passed"] is True, rt["verification"])
check("controlled-object replacement rule 372 applies TRUE", app(rt, "372").get("applicability") == "true", rt.get("applicability"))
check("other replacement ownership branches remain UNKNOWN", all(app(rt, rid).get("applicability") == "unknown" for rid in ("372.1", "372.2", "373")), rt.get("applicability"))
check("replacement proof records ordering chain", any(x.get("kind") == "replacement_ordering" and "372" in x.get("ruleIds", []) for x in rt.get("orderedChains", [])), rt.get("orderedChains"))

# Conditional proof: UNKNOWN applicability is preserved rather than guessed.
repl_unknown = ask(engine, "If two replacement effects apply to the same event, who chooses their order?")
rut = repl_unknown["proofTrace"]
check("conditional replacement ruling remains conditional", repl_unknown.get("ruling", {}).get("status") == "conditional" and rut.get("rulingStatus") == "conditional", repl_unknown.get("ruling"))
check("conditional proof still verifies", rut["verification"]["passed"] is True, rut["verification"])
check("conditional replacement proof preserves UNKNOWN matrix", all(app(rut, rid).get("applicability") == "unknown" for rid in ("372", "372.1", "372.2")), rut.get("applicability"))
check("conditional proof still has accepted basis", {"R:372", "R:372.1", "R:372.2"} <= accepted_ids(rut), rut.get("acceptedEvidence"))

# T83 — ordered Cleanup proof must evaluate later rules against derived state.
hidden = ask(engine, "During an Open State with no Combat or Showdown ongoing, I have a Hidden card at a battlefield I control and my last unit there dies. At the following Cleanup, is the Hidden card removed?")
ht = hidden["proofTrace"]
check("Hidden ordered proof verifies", ht["verification"]["passed"] is True, ht["verification"])
check("Hidden accepts 323.6 then 323.7", {"R:323.6", "R:323.7"} <= accepted_ids(ht), ht.get("acceptedEvidence"))
check("Cleanup chain preserves 323.6 -> 323.7", any(x.get("kind") == "cleanup_procedure" and x.get("ruleIds") == ["323.6", "323.7"] for x in ht.get("orderedChains", [])), ht.get("orderedChains"))
check("323.6 evaluates against initial state", app(ht, "323.6").get("evaluationContext") == "initial_state" and app(ht, "323.6").get("applicability") == "true", ht.get("applicability"))
check("323.7 evaluates after prior procedure step", app(ht, "323.7").get("evaluationContext") == "post_prior_procedure_step" and app(ht, "323.7").get("applicability") == "true", ht.get("applicability"))
check("Hidden proof records derived control loss", any(x.get("fact") == "actor_controls_battlefield" and x.get("toValue") == "false" and x.get("afterRuleId") == "323.6" and x.get("beforeRuleId") == "323.7" for x in ht.get("stateTransitions", [])), ht.get("stateTransitions"))
check("derived state transition is an ordered proof step", any(x.get("kind") == "state_transition" and x.get("fact") == "actor_controls_battlefield" for x in ht.get("steps", [])), ht.get("steps"))

# T82 — current FAQ precedence and card-vs-rule precedence are traceable.
might = ask(engine, "Is Might a copyable trait when one unit becomes a copy of another?")
mt = might["proofTrace"]
check("Might FAQ override proof verifies", mt["verification"]["passed"] is True, mt["verification"])
check("Might proof accepts exact FAQ evidence", "O:vendetta-faq-2026-08-14:0030" in accepted_ids(mt), mt.get("acceptedEvidence"))
check("Might proof records declared override chain", any(x.get("kind") == "declared_precedence_chain" and "current official FAQ override" in x.get("chain", []) for x in mt.get("precedence", [])), mt.get("precedence"))
check("Might proof records official source precedence", any(x.get("kind") == "official_source_precedence" and x.get("evidenceId") == "O:vendetta-faq-2026-08-14:0030" for x in mt.get("precedence", [])), mt.get("precedence"))
check("unselected FAQ context is explicitly rejected", rejected_reason(mt, "O:vendetta-faq-2026-08-14:0009") == "official_context_not_required_for_selected_conclusion", mt.get("rejectedEvidence"))

mage = ask(engine, "Mageseeker Warden is at a battlefield. Can my opponent play a unit directly to a battlefield they control?")
mgt = mage["proofTrace"]
check("card precedence proof verifies", mgt["verification"]["passed"] is True, mgt["verification"])
check("card precedence accepts card text and governing rules", {"C:ogn-070-298", "R:002", "R:054.2", "R:355.2.a"} <= accepted_ids(mgt), mgt.get("acceptedEvidence"))
check("default permission is marked superseded", rejected_reason(mgt, "R:355.2") == "superseded_by_precedence", mgt.get("rejectedEvidence"))
check("card precedence trace records scenario supersession", any(x.get("kind") == "scenario_supersession" and x.get("supersededBy") == "card_restriction" for x in mgt.get("precedence", [])), mgt.get("precedence"))
check("superseded outcome conflict is resolved", any(x.get("resolved") is True and x.get("resolution") == "card_restriction" for x in mgt.get("conflicts", [])), mgt.get("conflicts"))

# Timing/dependency trace.
counter = ask(engine, "If my spell is countered, does it count as played for a 'when you play a spell' trigger?")
ct = counter["proofTrace"]
check("counter proof verifies", ct["verification"]["passed"] is True, ct["verification"])
check("counter proof records timing dependency chain", any(x.get("kind") == "timing_dependency" for x in ct.get("orderedChains", [])), ct.get("orderedChains"))
check("explicit rule reference dependency is surfaced", any(x.get("fromEvidenceId") == "R:419.4.a.1" and x.get("toEvidenceId") == "R:425" for x in ct.get("dependencies", [])), ct.get("dependencies"))

# M8 program provenance survives into M9 proof traces.
discard = ask(engine, "If I discard a card, does it go to my graveyard?")
dt = discard["proofTrace"]
check("Rule Program ruling proof verifies", dt["verification"]["passed"] is True, dt["verification"])
check("proof trace preserves Rule Program provenance", any(x.get("programId") == "discard-to-trash" and x.get("compilerVersion") == 1 for x in dt.get("rulePrograms", [])), dt.get("rulePrograms"))
check("Rule Program is represented as ordered trace step", any(x.get("kind") == "rule_program" and x.get("programId") == "discard-to-trash" for x in dt.get("steps", [])), dt.get("steps"))
check("Rule Program evidence is accepted", {"R:422", "R:422.1", "R:422.1.a", "R:422.1.b"} <= accepted_ids(dt), dt.get("acceptedEvidence"))

# Older multi-outcome bookkeeping gaps now have selected, verifiable effective verdicts.
rebuttal = ask(engine, "If Rebuttal gains control of an opponent's Finalized spell, does that change who Finalized or played the spell for a non-triggered check?")
check("Rebuttal selects FAQ-backed effective verdict", (rebuttal["ruling"].get("effectiveVerdict") or {}).get("verdict") == "resolution_control_differs_from_finalizer" and rebuttal["proofTrace"]["verification"]["passed"] is True, rebuttal.get("ruling"))
check("Rebuttal basis includes FAQ 0019", "O:vendetta-faq-2026-08-14:0019" in accepted_ids(rebuttal["proofTrace"]), rebuttal["proofTrace"].get("acceptedEvidence"))

stun = ask(engine, "If empowered Gangplank is already Stunned and an effect tries to Stun him, is there a Stun event for his replacement effect to replace?")
check("already-Stunned replacement selects FAQ-backed verdict", (stun["ruling"].get("effectiveVerdict") or {}).get("verdict") == "no_stun_event_to_replace" and "O:vendetta-faq-2026-08-14:0022" in accepted_ids(stun["proofTrace"]), stun.get("ruling"))

zero = ask(engine, "If Stupefy would reduce Might by -0, is there a Might-decrease event for a replacement effect to replace?")
check("minus-zero replacement selects FAQ-backed verdict", (zero["ruling"].get("effectiveVerdict") or {}).get("verdict") == "no_might_decrease_event_to_replace" and "O:vendetta-faq-2026-08-14:0023" in accepted_ids(zero["proofTrace"]), zero.get("ruling"))

# T84/T86 — adversarial proof verification must fail closed on unsupported/tampered proofs.
synthetic_catalog = [{"evidenceId": "R:1", "kind": "core_rule", "ruleId": "1", "text": "Synthetic evidence"}]
synthetic_proof = {"obligations": [], "missingRequiredEvidence": [], "evidenceCompleteForKnownObligations": True, "decisiveRules": []}

bad_basis_ruling = {
    "status": "decided",
    "effectiveVerdict": {"verdict": "yes", "reason": "synthetic", "basis": ["R:TAMPERED"]},
    "outcomes": [],
}
bad_basis = build_proof_trace("synthetic tampered basis", synthetic_proof, bad_basis_ruling, [], synthetic_catalog, compiled_catalog)
check("tampered basis fails verification", bad_basis["verification"]["passed"] is False, bad_basis["verification"])
check("tampered basis reports missing catalog evidence", any(x.startswith("basis_evidence_missing_from_catalog:R:TAMPERED") for x in bad_basis["verification"]["errors"]), bad_basis["verification"])

conflict_ruling = {
    "status": "decided",
    "effectiveVerdict": {"verdict": "yes", "reason": "synthetic", "basis": ["R:1"]},
    "outcomes": [
        {"claim": "A", "verdict": "yes", "truth": "true", "conflictKey": "same-domain", "evidence": [{"evidenceId": "R:1", "ruleId": "1"}]},
        {"claim": "B", "verdict": "no", "truth": "true", "conflictKey": "same-domain", "evidence": [{"evidenceId": "R:1", "ruleId": "1"}]},
    ],
}
conflict_trace = build_proof_trace("synthetic conflict", synthetic_proof, conflict_ruling, [], synthetic_catalog, compiled_catalog)
check("explicit unresolved conflict fails verification", conflict_trace["verification"]["passed"] is False and "unresolved_proof_conflict" in conflict_trace["verification"]["errors"], conflict_trace)
check("explicit conflict appears in trace", any(x.get("conflictKey") == "same-domain" and x.get("resolved") is False for x in conflict_trace.get("conflicts", [])), conflict_trace.get("conflicts"))

missing_proof = {"obligations": ["synthetic"], "missingRequiredEvidence": ["R:2"], "evidenceCompleteForKnownObligations": False, "decisiveRules": []}
missing_ruling = {"status": "decided", "effectiveVerdict": {"verdict": "yes", "reason": "synthetic", "basis": ["R:1"]}, "outcomes": []}
missing_trace = build_proof_trace("synthetic incomplete proof", missing_proof, missing_ruling, [], synthetic_catalog, compiled_catalog)
check("known obligation evidence gap fails verification", "known_obligation_evidence_incomplete" in missing_trace["verification"]["errors"], missing_trace["verification"])

no_basis_ruling = {"status": "decided", "effectiveVerdict": {"verdict": "yes", "reason": "synthetic", "basis": []}, "outcomes": []}
no_basis_trace = build_proof_trace("synthetic no basis", synthetic_proof, no_basis_ruling, [], synthetic_catalog, compiled_catalog)
check("decided ruling with no basis fails verification", "effective_verdict_has_no_basis" in no_basis_trace["verification"]["errors"], no_basis_trace["verification"])
check("decided ruling with no accepted evidence fails verification", "decided_ruling_has_no_accepted_evidence" in no_basis_trace["verification"]["errors"], no_basis_trace["verification"])

insufficient_ruling = {"status": "insufficient", "effectiveVerdict": None, "outcomes": [], "reason": "synthetic missing facts"}
insufficient_trace = build_proof_trace("synthetic insufficient", synthetic_proof, insufficient_ruling, [], synthetic_catalog, compiled_catalog)
check("insufficient fail-closed state is a valid proof state", insufficient_trace["verification"]["passed"] is True and insufficient_trace.get("effectiveVerdict") is None, insufficient_trace)

# Engine integration must actually fail closed if proof verification fails; it may not repair the verdict.
original_builder = engine_module.build_proof_trace
try:
    def forced_failure(*args, **kwargs):
        return {
            "schemaVersion": 1, "issue": "forced", "rulingStatus": "decided", "effectiveVerdict": "yes",
            "steps": [], "acceptedEvidence": [], "rejectedEvidence": [], "applicability": [], "precedence": [],
            "conflicts": [], "rulePrograms": [], "orderedChains": [], "stateTransitions": [], "dependencies": [],
            "completeness": {"knownObligations": [], "missingRequiredEvidence": [], "evidenceCompleteForKnownObligations": True, "acceptedEvidenceCount": 0, "rejectedEvidenceCount": 0},
            "verification": {"passed": False, "errors": ["synthetic_forced_failure"]},
        }
    engine_module.build_proof_trace = forced_failure
    forced = engine.ask("Can I play a unit directly to a battlefield I control?")["issues"][0]
finally:
    engine_module.build_proof_trace = original_builder
check("engine fails closed when proof verification fails", forced.get("ruling", {}).get("status") == "insufficient" and forced.get("ruling", {}).get("proofVerificationErrors") == ["synthetic_forced_failure"], forced.get("ruling"))
check("engine preserves failed proof trace instead of hiding it", forced.get("proofTrace", {}).get("failClosedApplied") is True, forced.get("proofTrace"))
check("engine keeps original adjudication under baseRuling for diagnostics", (forced.get("ruling", {}).get("baseRuling") or {}).get("status") == "decided", forced.get("ruling"))

report = {"passed": not failures, "checkCount": checks, "failureCount": len(failures), "failures": failures}
(ROOT / "data/validation/proof_engine_test_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["passed"] else 1)
