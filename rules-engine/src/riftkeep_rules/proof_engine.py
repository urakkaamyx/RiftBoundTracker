from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from .predicates import PREDICATE_SPECS, evaluate_rule_applicability
from .scenario import Fact


def _rule_order_key(rule_id: str) -> tuple:
    parts = re.split(r"[.]", rule_id or "")
    out: list[tuple[int, Any]] = []
    for p in parts:
        m = re.match(r"^(\d+)([a-z]*)$", p, flags=re.I)
        if m:
            out.append((0, int(m.group(1))))
            out.append((1, m.group(2) or ""))
        else:
            out.append((2, p))
    return tuple(out)


def _evidence_kind(eid: str) -> str:
    if eid.startswith("R:"):
        return "core_rule"
    if eid.startswith("C:"):
        return "card_text"
    if eid.startswith("O:"):
        return "official_ruling"
    return "unknown"


def _selected_outcomes(ruling: dict[str, Any]) -> list[dict[str, Any]]:
    effective = ruling.get("effectiveVerdict") or {}
    verdict = effective.get("verdict")
    reason = effective.get("reason")
    outcomes = list(ruling.get("outcomes") or [])
    selected = [o for o in outcomes if o.get("effectStatus") != "superseded_in_scenario" and (o.get("verdict") == verdict or (reason and o.get("claim") == reason))]
    return selected


def _outcome_evidence_ids(outcome: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for e in outcome.get("evidence") or []:
        if e.get("evidenceId"):
            out.append(str(e["evidenceId"]))
    for key in ("cardEvidence", "sourceEvidence"):
        e = outcome.get(key)
        if isinstance(e, dict) and e.get("evidenceId"):
            out.append(str(e["evidenceId"]))
    for key in ("additionalCardEvidence", "additionalSourceEvidence"):
        for e in outcome.get(key) or []:
            if isinstance(e, dict) and e.get("evidenceId"):
                out.append(str(e["evidenceId"]))
    return out


def _explicit_conflicts(ruling: dict[str, Any]) -> list[dict[str, Any]]:
    """Only detect conflicts that outcomes explicitly declare as sharing a conflictKey.

    M9 refuses to infer semantic contradiction from different verdict labels alone.
    That would itself be an unsafe adjudication step.
    """
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for o in ruling.get("outcomes") or []:
        key = o.get("conflictKey")
        if key and o.get("truth") == "true" and o.get("effectStatus") != "superseded_in_scenario":
            groups[str(key)].append(o)
    out: list[dict[str, Any]] = []
    for key, rows in groups.items():
        verdicts = sorted({str(r.get("verdict")) for r in rows})
        if len(verdicts) > 1:
            out.append({"conflictKey": key, "verdicts": verdicts, "resolved": False, "reason": "multiple unsuperseded true outcomes explicitly claim the same conflict domain"})
    for o in ruling.get("outcomes") or []:
        if o.get("effectStatus") == "superseded_in_scenario":
            out.append({
                "conflictKey": o.get("conflictKey") or f"superseded:{o.get('verdict')}",
                "verdicts": [o.get("verdict")],
                "resolved": True,
                "resolution": o.get("supersededBy"),
                "reason": "outcome explicitly superseded during scenario precedence resolution",
            })
    return out


def build_proof_trace(
    issue: str,
    proof: dict[str, Any],
    ruling: dict[str, Any],
    facts: list[Fact],
    evidence_catalog: list[dict[str, Any]],
    compiled_rule_catalog: dict[str, Any],
) -> dict[str, Any]:
    catalog_by_id = {str(e.get("evidenceId")): e for e in evidence_catalog if e.get("evidenceId")}
    compiled_by_rule = {str(r.get("ruleId")): r for r in compiled_rule_catalog.get("rules", []) if r.get("ruleId")}
    effective = ruling.get("effectiveVerdict") or {}
    basis = [str(x) for x in (effective.get("basis") or []) if x]
    selected = _selected_outcomes(ruling)

    accepted_ids: list[str] = []
    for eid in basis:
        if eid not in accepted_ids:
            accepted_ids.append(eid)
    for outcome in selected:
        for eid in _outcome_evidence_ids(outcome):
            if eid not in accepted_ids:
                accepted_ids.append(eid)
    for eid in ruling.get("interpretedOfficialOverlayEvidenceIds") or []:
        if eid and str(eid) not in accepted_ids:
            accepted_ids.append(str(eid))
    for eid in ruling.get("officialOverlayEvidenceIds") or []:
        if eid and str(eid) not in accepted_ids:
            accepted_ids.append(str(eid))

    accepted = []
    for idx, eid in enumerate(accepted_ids, start=1):
        row = catalog_by_id.get(eid)
        accepted.append({
            "evidenceId": eid,
            "kind": (row or {}).get("kind") or _evidence_kind(eid),
            "sourceId": (row or {}).get("sourceId"),
            "ruleId": (row or {}).get("ruleId"),
            "order": idx,
            "reason": "effective_verdict_basis" if eid in basis else "selected_or_interpreted_authority_evidence",
            "presentInCatalog": row is not None,
        })

    applicability: list[dict[str, Any]] = []
    app_by_rule: dict[str, dict[str, Any]] = {}
    for r in proof.get("decisiveRules") or []:
        rid = str(r.get("ruleId") or "")
        if rid not in PREDICATE_SPECS:
            continue
        app = evaluate_rule_applicability(rid, facts).to_dict()
        app["compiled"] = True
        applicability.append(app)
        app_by_rule[rid] = app

    # Ordered adjudication may intentionally derive a post-step state before applying
    # a later rule (for example Cleanup 323.6 losing control before 323.7 checks Hidden).
    # Those ordered applicability records override a flat re-evaluation against the
    # initial scenario facts.
    ordered_applicability: list[dict[str, Any]] = []
    for outcome in selected:
        for index, app in enumerate(outcome.get("orderedProof") or []):
            if not isinstance(app, dict) or not app.get("ruleId"):
                continue
            row = dict(app)
            row["compiled"] = str(row.get("ruleId")) in PREDICATE_SPECS
            row["evaluationContext"] = "initial_state" if index == 0 else "post_prior_procedure_step"
            ordered_applicability.append(row)
            app_by_rule[str(row["ruleId"])] = row
    if ordered_applicability:
        replaced_ids = {str(x.get("ruleId")) for x in ordered_applicability}
        applicability = [x for x in applicability if str(x.get("ruleId")) not in replaced_ids] + ordered_applicability

    accepted_set = set(accepted_ids)
    superseded_eids: set[str] = set()
    for o in ruling.get("outcomes") or []:
        if o.get("effectStatus") == "superseded_in_scenario":
            superseded_eids.update(_outcome_evidence_ids(o))

    rejected: list[dict[str, Any]] = []
    seen_rejected: set[str] = set()
    for r in proof.get("decisiveRules") or []:
        rid = str(r.get("ruleId") or "")
        eid = f"R:{rid}"
        if eid in accepted_set or eid in seen_rejected:
            continue
        seen_rejected.add(eid)
        app = app_by_rule.get(rid)
        if eid in superseded_eids:
            reason = "superseded_by_precedence"
        elif app and app.get("applicability") == "false":
            reason = "applicability_false"
        elif app and app.get("applicability") == "unknown":
            reason = "applicability_unknown"
        else:
            reason = "context_not_required_for_selected_conclusion"
        rejected.append({"evidenceId": eid, "kind": "core_rule", "ruleId": rid, "reason": reason})

    for e in evidence_catalog:
        eid = str(e.get("evidenceId") or "")
        if not eid.startswith("O:") or eid in accepted_set or eid in seen_rejected:
            continue
        seen_rejected.add(eid)
        rejected.append({"evidenceId": eid, "kind": e.get("kind") or "official_ruling", "reason": "official_context_not_required_for_selected_conclusion"})

    precedence: list[dict[str, Any]] = []
    for o in ruling.get("outcomes") or []:
        if o.get("precedence"):
            precedence.append({"kind": "declared_precedence_chain", "outcomeVerdict": o.get("verdict"), "chain": list(o.get("precedence") or [])})
        if o.get("effectStatus") == "superseded_in_scenario":
            precedence.append({"kind": "scenario_supersession", "outcomeVerdict": o.get("verdict"), "supersededBy": o.get("supersededBy")})
        src = o.get("sourceEvidence")
        if isinstance(src, dict) and (src.get("authority") or {}).get("precedence"):
            precedence.append({"kind": "official_source_precedence", "evidenceId": src.get("evidenceId"), "precedence": (src.get("authority") or {}).get("precedence")})

    conflicts = _explicit_conflicts(ruling)

    rule_programs: list[dict[str, Any]] = []
    for outcome in selected:
        rp = outcome.get("ruleProgram")
        if not isinstance(rp, dict) or not rp.get("programId"):
            continue
        row = {
            "programId": rp.get("programId"),
            "compilerVersion": rp.get("compilerVersion"),
            "outcomeVerdict": outcome.get("verdict"),
            "evidenceIds": _outcome_evidence_ids(outcome),
        }
        if row not in rule_programs:
            rule_programs.append(row)

    card_interaction_programs: list[dict[str, Any]] = []
    for outcome in selected:
        cp = outcome.get("cardInteractionProgram")
        if not isinstance(cp, dict) or not cp.get("programId"):
            continue
        row = {
            "programId": cp.get("programId"),
            "evidenceId": cp.get("evidenceId"),
            "outcomeVerdict": outcome.get("verdict"),
            "evidenceIds": _outcome_evidence_ids(outcome),
            "cardClauseRefs": list(cp.get("cardClauseRefs") or []),
            "sourceGuards": cp.get("sourceGuards") or {},
        }
        if row not in card_interaction_programs:
            card_interaction_programs.append(row)

    state_transitions: list[dict[str, Any]] = []
    if any(str(x.get("ruleId")) == "323.6" and x.get("applicability") == "true" for x in ordered_applicability) and any(str(x.get("ruleId")) == "323.7" for x in ordered_applicability):
        state_transitions.append({
            "afterRuleId": "323.6",
            "beforeRuleId": "323.7",
            "fact": "actor_controls_battlefield",
            "toValue": "false",
            "provenance": "ordered adjudication: battlefield control is lost before the following Hidden-card Cleanup task",
        })

    dependencies: list[dict[str, Any]] = []
    for a in accepted:
        rid = a.get("ruleId")
        if not rid:
            continue
        compiled = compiled_by_rule.get(str(rid)) or {}
        for dep in compiled.get("dependencies") or []:
            eid = f"R:{dep}"
            dependencies.append({
                "fromEvidenceId": a["evidenceId"],
                "toEvidenceId": eid,
                "ruleId": dep,
                "presentInEvidenceCatalog": eid in catalog_by_id,
                "accepted": eid in accepted_set,
                "relation": "explicit_rule_reference",
            })

    # Ordered same-root chains preserve canonical procedure order (e.g. 323.6 -> 323.7).
    roots: dict[str, list[str]] = defaultdict(list)
    for a in accepted:
        rid = a.get("ruleId")
        if rid:
            roots[str(rid).split(".")[0]].append(str(rid))
    ordered_chains: list[dict[str, Any]] = []
    for root, ids in roots.items():
        unique = sorted(set(ids), key=_rule_order_key)
        if len(unique) >= 2:
            ordered_chains.append({"kind": "canonical_rule_order", "rootRuleId": root, "ruleIds": unique})
    obligations = set(proof.get("obligations") or [])
    if "replacement_order" in obligations:
        ordered_chains.append({"kind": "replacement_ordering", "ruleIds": [x for x in ["370.1", "372", "372.1", "372.2", "373", "373.1", "373.1.a"] if f"R:{x}" in accepted_set or any(str(r.get("ruleId")) == x for r in proof.get("decisiveRules") or [])]})
    if {"hidden_lifecycle", "battlefield_control_loss"} & obligations:
        cleanup = [x for x in ["323.5", "323.6", "323.7"] if any(str(r.get("ruleId")) == x for r in proof.get("decisiveRules") or [])]
        if cleanup:
            ordered_chains.append({"kind": "cleanup_procedure", "ruleIds": cleanup})
    if {"play_finalize_semantics", "trigger_snapshot", "counter_resolution"} & obligations:
        timing_ids = [a.get("ruleId") for a in accepted if a.get("ruleId")]
        if timing_ids:
            ordered_chains.append({"kind": "timing_dependency", "ruleIds": timing_ids})

    # Fact steps are limited to facts actually referenced by compiled applicability or selected outcomes.
    fact_names: list[str] = []
    for app in applicability:
        for p in app.get("predicates") or []:
            basis_text = str(p.get("basis") or "")
            if basis_text.startswith("scenario fact: "):
                name = basis_text.split(": ", 1)[1]
                if name not in fact_names:
                    fact_names.append(name)
    fm = {f.name: f for f in facts}
    steps: list[dict[str, Any]] = []
    step_n = 1
    for name in fact_names:
        f = fm.get(name)
        steps.append({"stepId": f"S{step_n}", "kind": "scenario_fact", "factId": f"F:{name}", "fact": name, "value": getattr(f.value, "value", f.value) if f else "unknown", "source": f.source if f else None})
        step_n += 1
    for app in applicability:
        steps.append({"stepId": f"S{step_n}", "kind": "applicability", "ruleId": app.get("ruleId"), "result": app.get("applicability"), "predicates": app.get("predicates") or []})
        step_n += 1
    for transition in state_transitions:
        steps.append({"stepId": f"S{step_n}", "kind": "state_transition", **transition})
        step_n += 1
    for rp in rule_programs:
        steps.append({"stepId": f"S{step_n}", "kind": "rule_program", **rp})
        step_n += 1
    for cp in card_interaction_programs:
        steps.append({"stepId": f"S{step_n}", "kind": "card_interaction_program", **cp})
        step_n += 1
    for a in accepted:
        steps.append({"stepId": f"S{step_n}", "kind": "authority_evidence", "evidenceId": a["evidenceId"], "evidenceKind": a["kind"], "ruleId": a.get("ruleId")})
        step_n += 1
    for p in precedence:
        steps.append({"stepId": f"S{step_n}", "kind": "precedence", **p})
        step_n += 1
    if ruling.get("effectiveVerdict"):
        steps.append({"stepId": f"S{step_n}", "kind": "conclusion", "verdict": effective.get("verdict"), "reason": effective.get("reason"), "basis": basis})

    completeness = {
        "knownObligations": list(proof.get("obligations") or []),
        "missingRequiredEvidence": list(proof.get("missingRequiredEvidence") or []),
        "evidenceCompleteForKnownObligations": bool(proof.get("evidenceCompleteForKnownObligations")),
        "acceptedEvidenceCount": len(accepted),
        "rejectedEvidenceCount": len(rejected),
    }

    trace = {
        "schemaVersion": 1,
        "issue": issue,
        "rulingStatus": ruling.get("status") or "unknown",
        "effectiveVerdict": effective.get("verdict"),
        "steps": steps,
        "acceptedEvidence": accepted,
        "rejectedEvidence": rejected,
        "applicability": applicability,
        "precedence": precedence,
        "conflicts": conflicts,
        "rulePrograms": rule_programs,
        "cardInteractionPrograms": card_interaction_programs,
        "orderedChains": ordered_chains,
        "stateTransitions": state_transitions,
        "dependencies": dependencies,
        "completeness": completeness,
    }
    trace["verification"] = verify_proof_trace(trace, ruling, evidence_catalog)
    return trace


def verify_proof_trace(trace: dict[str, Any], ruling: dict[str, Any], evidence_catalog: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    status = str(ruling.get("status") or "")
    effective = ruling.get("effectiveVerdict") or {}
    catalog_ids = {str(e.get("evidenceId")) for e in evidence_catalog if e.get("evidenceId")}

    if status in {"decided", "conditional"}:
        if not effective.get("verdict"):
            errors.append("missing_effective_verdict")
        basis = [str(x) for x in (effective.get("basis") or []) if x]
        if not basis:
            errors.append("effective_verdict_has_no_basis")
        missing_basis = [eid for eid in basis if eid not in catalog_ids]
        if missing_basis:
            errors.append("basis_evidence_missing_from_catalog:" + ",".join(missing_basis))
        if trace.get("completeness", {}).get("missingRequiredEvidence"):
            errors.append("known_obligation_evidence_incomplete")
        if any(not c.get("resolved") for c in trace.get("conflicts") or []):
            errors.append("unresolved_proof_conflict")
        if status == "decided" and not trace.get("acceptedEvidence"):
            errors.append("decided_ruling_has_no_accepted_evidence")

    # Insufficient rulings are valid fail-closed states and need no fabricated conclusion.
    return {
        "passed": not errors,
        "errors": errors,
        "policy": "Verification checks support/closure only. It never invents or changes a verdict; callers may fail closed when verification fails.",
    }
