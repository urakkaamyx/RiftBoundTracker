from __future__ import annotations

import re
from typing import Any

from .scenario import Fact, Truth, fact_map


# Applicability is evaluated by a declarative, regression-tested predicate registry.
from .predicates import evaluate_rule_applicability
from .rule_programs import evaluate_rule_programs


def evaluate_known_applicability(rule_id: str, facts: list[Fact]):
    # Backward-compatible facade used by adjudication templates.
    return evaluate_rule_applicability(rule_id, facts)


def _rule_lookup(evidence: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {r["ruleId"]: r for r in evidence}


def _citation(rule_id: str, by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    r = by_id[rule_id]
    return {
        "evidenceId": f"R:{rule_id}",
        "ruleId": rule_id,
        "text": r.get("normativeText") or r.get("text") or "",
        "pageStart": r.get("pageStart"),
        "pageEnd": r.get("pageEnd"),
        "sourceId": r.get("sourceId"),
    }


_OUTCOME_STOPWORDS = {
    "the", "a", "an", "is", "it", "if", "my", "your", "their", "this", "that",
    "does", "do", "can", "could", "would", "should", "to", "of", "for", "and",
    "or", "be", "been", "being", "as", "on", "in", "when", "with", "by", "from",
    "was", "were", "will",
}


def _outcome_tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(t) > 2 and t not in _OUTCOME_STOPWORDS}


def _outcome_basis(outcome: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for e in outcome.get("evidence") or []:
        if e.get("evidenceId") and e["evidenceId"] not in out:
            out.append(e["evidenceId"])
    for key in ("cardEvidence", "sourceEvidence"):
        e = outcome.get(key)
        if isinstance(e, dict) and e.get("evidenceId") and e["evidenceId"] not in out:
            out.append(e["evidenceId"])
    for e in outcome.get("additionalSourceEvidence") or []:
        if isinstance(e, dict) and e.get("evidenceId") and e["evidenceId"] not in out:
            out.append(e["evidenceId"])
    return out


def _select_specific_true_outcome(issue: str, outcomes: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [o for o in outcomes if o.get("truth") == "true" and o.get("effectStatus") != "superseded_in_scenario"]
    if not candidates:
        return None
    issue_tokens = _outcome_tokens(issue)
    scored = []
    for index, outcome in enumerate(candidates):
        overlap = len(issue_tokens & _outcome_tokens(str(outcome.get("claim") or "")))
        # Stable tie-breaking preserves legacy ordering when specificity is equal.
        scored.append((overlap, -index, outcome))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return scored[0][2]


def adjudicate_issue(issue: str, proof: dict[str, Any], facts: list[Fact], named_cards: list[dict[str, Any]], official_evidence: list[dict[str, Any]] | None = None, rule_programs: dict[str, Any] | None = None) -> dict[str, Any]:
    by_id = _rule_lookup(proof.get("decisiveRules", []))
    all_evidence = proof.get("decisiveRules", [])
    obligations = proof.get("obligations", [])
    outcomes: list[dict[str, Any]] = []
    derived: dict[str, Truth] = fact_map(facts)
    q = (issue or "").lower().replace("’", "'")
    official_by_id = {str(x.get("evidenceId")): x for x in (official_evidence or []) if x.get("evidenceId")}
    interpreted_overlay_ids: list[str] = []

    def source_evidence(eid: str) -> dict[str, Any] | None:
        d = official_by_id.get(eid)
        if not d:
            return None
        return {
            "evidenceId": eid,
            "sourceId": d.get("sourceId"),
            "title": d.get("title") or "Official ruling",
            "heading": d.get("heading"),
            "text": d.get("text") or "",
            "published": d.get("published"),
            "effectiveFrom": d.get("effectiveFrom"),
            "sourceUrl": d.get("sourceUrl"),
            "authority": d.get("authority") or {},
        }

    def has(*ids: str) -> bool:
        return all(x in by_id for x in ids)

    def cites(*ids: str) -> list[dict[str, Any]]:
        return [_citation(x, by_id) for x in ids if x in by_id]

    program_outcomes, program_consumed, rule_program_diagnostics = evaluate_rule_programs(
        rule_programs or {"programs": []}, obligations, facts, by_id, evaluate_known_applicability
    )
    outcomes.extend(program_outcomes)

    if "unit_play_location" in obligations and has("355.2.a"):
        default_app = evaluate_known_applicability("355.2.a", facts)
        special_app = evaluate_known_applicability("355.2.b", facts) if "355.2.b" in by_id else None
        dest_base = derived.get("unit_play_destination_is_base", Truth.UNKNOWN)
        if default_app.applicability == Truth.TRUE:
            destination = "Base" if dest_base == Truth.TRUE else "Battlefield its controller controls"
            outcomes.append({
                "claim": f"A Unit may be played directly to its controller's {destination} as a default valid location.",
                "verdict": "yes",
                "truth": "true",
                "evidence": cites("355.2", "355.2.a"),
                "applicability": default_app.to_dict(),
            })
        elif special_app and special_app.applicability == Truth.TRUE:
            outcomes.append({
                "claim": "Although the destination is not a default valid Unit-play location, the stated Game Effect grants permission and makes that location valid for this play.",
                "verdict": "yes_by_effect_permission",
                "truth": "true",
                "evidence": cites("355.2", "355.2.a", "355.2.b"),
                "applicability": {"default": default_app.to_dict(), "specialPermission": special_app.to_dict()},
            })
        elif default_app.applicability == Truth.FALSE and (derived.get("query_scope_default_rules_only") == Truth.TRUE or not special_app or special_app.applicability == Truth.FALSE):
            outcomes.append({
                "claim": "The destination is not a default valid Unit-play location, and the stated scenario does not provide a Game Effect that makes it valid.",
                "verdict": "no_on_this_rule",
                "truth": "false",
                "evidence": cites("355.2", "355.2.a", "355.2.b"),
                "applicability": {"default": default_app.to_dict(), "specialPermission": special_app.to_dict() if special_app else None},
            })
        elif default_app.applicability == Truth.FALSE:
            outcomes.append({
                "claim": "The destination is not valid by default, but a Game Effect could grant permission to use a normally invalid Unit-play location; the question does not establish whether such permission exists.",
                "verdict": "conditional",
                "truth": "unknown",
                "evidence": cites("355.2", "355.2.a", "355.2.b"),
                "applicability": {"default": default_app.to_dict(), "specialPermission": special_app.to_dict() if special_app else None},
            })
        else:
            outcomes.append({
                "claim": "The Unit-play destination is not sufficiently established to decide whether it is a default valid location.",
                "verdict": "conditional",
                "truth": "unknown",
                "evidence": cites("355.2", "355.2.a", "355.2.b"),
                "applicability": {"default": default_app.to_dict(), "specialPermission": special_app.to_dict() if special_app else None},
            })

    if "contested_on_entry" in obligations and has("190.3.a.1"):
        app = evaluate_known_applicability("190.3.a.1", facts)
        if app.applicability == Truth.FALSE:
            if derived.get("unit_controller_already_controls_battlefield") == Truth.TRUE:
                claim = "The Unit's arrival does not newly apply Contested because its controller already controls that Battlefield."
            elif derived.get("battlefield_already_contested") == Truth.TRUE:
                claim = "The Unit's arrival does not newly apply Contested under 190.3.a.1 because that Battlefield is already Contested."
            else:
                claim = "The stated conditions for newly applying Contested under 190.3.a.1 are not all satisfied."
            outcomes.append({
                "claim": claim,
                "verdict": "no",
                "truth": "false",
                "evidence": cites("190.3.a", "190.3.a.1"),
                "applicability": app.to_dict(),
            })
        elif app.applicability == Truth.TRUE:
            outcomes.append({
                "claim": "The Unit's arrival applies Contested because the battlefield is not already Contested and the Unit's controller does not already control it.",
                "verdict": "yes",
                "truth": "true",
                "evidence": cites("190.3.a", "190.3.a.1"),
                "applicability": app.to_dict(),
            })
        else:
            outcomes.append({
                "claim": "Whether the Unit's arrival newly applies Contested depends on whether the battlefield is already Contested and whether the Unit's controller already controls it.",
                "verdict": "conditional",
                "truth": "unknown",
                "evidence": cites("190.3.a", "190.3.a.1"),
                "applicability": app.to_dict(),
            })

    # Cleanup proof chain. We explicitly propagate the result of 323.6 into 323.7 rather than making rules compete.
    if "hidden_lifecycle" in obligations:
        control_rule = "323.6" if "323.6" in by_id else ("190.4.c" if "190.4.c" in by_id else None)
        if control_rule:
            control_app = evaluate_known_applicability(control_rule, facts)
            if control_app.applicability == Truth.TRUE:
                derived["actor_controls_battlefield"] = Truth.FALSE
                # Rebuild facts including the derived post-step control fact.
                propagated = list(facts) + [Fact("actor_controls_battlefield", Truth.FALSE, f"derived after applying {control_rule}", "derived")]
                hidden_app = evaluate_known_applicability("323.7", propagated) if "323.7" in by_id else None
                outcomes.append({
                    "claim": "During Cleanup, after battlefield control is lost for having no Units there in an Open State with no ongoing Combat/Showdown, the following Cleanup task removes Hidden cards from that now-uncontrolled Battlefield to their owners' Trash.",
                    "verdict": "remove_to_trash" if hidden_app and hidden_app.applicability == Truth.TRUE else "conditional",
                    "truth": "true" if hidden_app and hidden_app.applicability == Truth.TRUE else "unknown",
                    "evidence": cites("323.6", "323.7", "190.4.c", "811.1.b"),
                    "orderedProof": [x for x in [control_app.to_dict(), hidden_app.to_dict() if hidden_app else None] if x],
                })
            elif control_app.applicability == Truth.FALSE:
                outcomes.append({
                    "claim": "The Cleanup control-loss condition is false in the stated scenario, so this proof does not establish that the Hidden card is removed for loss of battlefield control at that Cleanup.",
                    "verdict": "no_on_this_sequence",
                    "truth": "false",
                    "evidence": cites(control_rule, "323.7", "811.1.b"),
                    "applicability": control_app.to_dict(),
                })
            else:
                outcomes.append({
                    "claim": "The Hidden-card outcome is conditional because losing battlefield control requires an Open State with no ongoing Combat or Showdown; the question does not establish all of those facts.",
                    "verdict": "conditional",
                    "truth": "unknown",
                    "evidence": cites("190.4.c", "323.6", "323.7", "811.1.b"),
                    "applicability": control_app.to_dict(),
                })

    if "prevent_damage" in obligations and "437.4" in by_id:
        app = evaluate_known_applicability("437.4", facts)
        dealt_fact = derived.get("damage_was_dealt", Truth.UNKNOWN)
        if app.applicability == Truth.TRUE:
            outcomes.append({
                "claim": "If all of the damage is prevented, that damage is not considered to have been dealt to the Unit at all.",
                "verdict": "no_damage_dealt",
                "truth": "true",
                "evidence": cites("437.2", "437.2.a", "437.4", "417.1.b"),
                "applicability": app.to_dict(),
            })
        elif dealt_fact == Truth.TRUE:
            outcomes.append({
                "claim": "Some damage remains after prevention, so damage is still dealt; only a resulting amount of 0 is equivalent to no damage being dealt.",
                "verdict": "damage_dealt",
                "truth": "true",
                "evidence": cites("437.2", "437.2.a", "437.4", "417.1.b"),
                "applicability": app.to_dict(),
            })
        else:
            outcomes.append({
                "claim": "Prevent reduces the damage event; only if the resulting dealt amount is 0 is it equivalent to no damage being dealt.",
                "verdict": "conditional",
                "truth": "unknown",
                "evidence": cites("437.2", "437.2.a", "437.4", "417.1.b"),
                "applicability": app.to_dict(),
            })

    if "counter_resolution" in obligations and has("425.1", "425.1.a", "425.1.b"):
        countered = derived.get("chain_item_countered", Truth.UNKNOWN)
        if countered == Truth.TRUE:
            outcomes.append({
                "claim": "A Countered card or ability does nothing and is cleared from the chain. A Countered card is not considered played for abilities that trigger on cards being played, and paid costs are not refunded.",
                "verdict": "no",
                "truth": "true",
                "evidence": cites("425.1", "425.1.a", "425.1.a.1", "425.1.b", "425.1.c", "419.4.a.1"),
                "applicability": evaluate_known_applicability("425.1", facts).to_dict(),
            })
        else:
            outcomes.append({
                "claim": "The Counter consequences depend on the card or ability actually being Countered; that fact is not established.",
                "verdict": "conditional",
                "truth": "unknown",
                "evidence": cites("425.1", "425.1.a", "425.1.b", "425.1.c"),
            })

    if "mistarget_resolution" in obligations and has("359.3.e.1", "359.3.e.7", "359.3.e.10"):
        all_bad = derived.get("all_targets_illegal_on_resolution", Truth.UNKNOWN)
        some_bad = derived.get("some_target_illegal_on_resolution", Truth.UNKNOWN)
        some_good = derived.get("some_targets_remain_legal_on_resolution", Truth.UNKNOWN)
        if all_bad == Truth.TRUE:
            outcomes.append({
                "claim": "The spell still resolves, but an instruction whose entire set of targets is invalid or unavailable does not execute. A spell can therefore resolve with no effect and still count as played.",
                "verdict": "resolves_no_effect",
                "truth": "true",
                "evidence": cites("359.3.e.1", "359.3.e.2", "359.3.e.7", "359.3.e.10"),
                "applicability": evaluate_known_applicability("359.3.e.7", facts).to_dict(),
            })
        elif some_bad == Truth.TRUE and some_good == Truth.TRUE and "359.3.e.8" in by_id:
            outcomes.append({
                "claim": "The spell still resolves. With some targets invalid and others still valid, the instruction executes only on the targets that remain available and legal.",
                "verdict": "partial_resolution",
                "truth": "true",
                "evidence": cites("359.3.e.1", "359.3.e.2", "359.3.e.8"),
            })
        else:
            outcomes.append({
                "claim": "Resolution depends on how many targets remain legal and available when the relevant instruction begins resolving.",
                "verdict": "conditional",
                "truth": "unknown",
                "evidence": cites("359.3.e.1", "359.3.e.2", "359.3.e.7", "359.3.e.10"),
            })

    if "recall_not_move" in obligations and has("455", "456", "456.1"):
        is_recall = derived.get("action_is_recall", Truth.UNKNOWN)
        if is_recall == Truth.TRUE:
            outcomes.append({
                "claim": "A Recall relocates a Permanent to its Base, but it is explicitly not a Move. It therefore does not trigger abilities that trigger from Move actions, and movement restrictions do not prevent the Recall.",
                "verdict": "no",
                "truth": "true",
                "evidence": cites("455", "456", "456.1", "456.3", "458.1"),
                "applicability": evaluate_known_applicability("456", facts).to_dict(),
            })
        else:
            outcomes.append({
                "claim": "This compiled ruling applies only if the relocation is actually a Recall.",
                "verdict": "conditional",
                "truth": "unknown",
                "evidence": cites("455", "456", "456.1"),
            })

    if "conquer_scoring" in obligations and has("469.1", "470"):
        app = evaluate_known_applicability("469.1", facts)
        if app.applicability == Truth.TRUE:
            outcomes.append({
                "claim": "Gaining Control of a Battlefield you have not yet Scored this turn is a Conquer. A player can Score that Battlefield only once per turn.",
                "verdict": "yes",
                "truth": "true",
                "evidence": cites("469.1", "470", "471.2.a"),
                "applicability": app.to_dict(),
            })
        elif derived.get("battlefield_already_scored_this_turn") == Truth.TRUE:
            outcomes.append({
                "claim": "Gaining Control of a Battlefield already Scored this turn does not satisfy the Conquer definition for scoring it again; that Battlefield can be Scored only once per turn.",
                "verdict": "no",
                "truth": "false",
                "evidence": cites("469.1", "470"),
                "applicability": app.to_dict(),
            })
        else:
            outcomes.append({
                "claim": "Whether gaining Control is a Conquer depends on whether that Battlefield has already been Scored this turn.",
                "verdict": "conditional",
                "truth": "unknown",
                "evidence": cites("469.1", "470"),
                "applicability": app.to_dict(),
            })

    if "hold_scoring" in obligations and has("469.2", "470"):
        app = evaluate_known_applicability("469.2", facts)
        if app.applicability == Truth.TRUE:
            outcomes.append({
                "claim": "Maintaining Control of a Battlefield you have not yet Scored this turn during your Beginning Phase is a Hold. A player can Score that Battlefield only once per turn.",
                "verdict": "yes",
                "truth": "true",
                "evidence": cites("469.2", "470", "471.2.b"),
                "applicability": app.to_dict(),
            })
        elif derived.get("battlefield_already_scored_this_turn") == Truth.TRUE:
            outcomes.append({
                "claim": "A Battlefield already Scored this turn cannot be Scored again through Hold that turn.",
                "verdict": "no",
                "truth": "false",
                "evidence": cites("469.2", "470"),
                "applicability": app.to_dict(),
            })
        else:
            outcomes.append({
                "claim": "Whether this is a Hold depends on maintaining Control during the Beginning Phase and whether that Battlefield has already been Scored this turn.",
                "verdict": "conditional",
                "truth": "unknown",
                "evidence": cites("469.2", "470"),
                "applicability": app.to_dict(),
            })

    # Targeting vs permission/restriction text. Rule 355.10.b explicitly prevents
    # location restrictions/permissions from becoming targets merely because they are named.
    if "untargetable_legality" in obligations and has("355.8", "355.9", "355.9.b", "758", "758.1"):
        at_choice = derived.get("target_untargetable_at_choice", Truth.UNKNOWN)
        after_choice = derived.get("target_became_untargetable_after_targeted", Truth.UNKNOWN)
        if at_choice == Truth.TRUE:
            outcomes.append({
                "claim": "An object that is Untargetable for the indicated spell or ability when targets are chosen is not a legal target, so that choice cannot be used to legally put/finalize the spell or ability on the chain.",
                "verdict": "cannot_target",
                "truth": "true",
                "evidence": cites("355.8", "355.9", "355.9.b", "757", "758"),
                "applicability": evaluate_known_applicability("758", facts).to_dict(),
            })
        elif after_choice == Truth.TRUE:
            outcomes.append({
                "claim": "If an object becomes Untargetable after it was legally chosen and before resolution, the spell or ability mistargets that object on resolution and instructions related to it are ignored.",
                "verdict": "mistargets_on_resolution",
                "truth": "true",
                "evidence": cites("758", "758.1", "359.3.e.5"),
                "applicability": evaluate_known_applicability("758.1", facts).to_dict(),
            })
        else:
            outcomes.append({
                "claim": "Untargetable changes legality differently depending on whether it already applied when the target was chosen or arose only after the target was chosen.",
                "verdict": "conditional",
                "truth": "unknown",
                "evidence": cites("355.8", "355.9.b", "758", "758.1"),
            })

    # Vendetta FAQ overlay: linked instruction failures distinguish mistargeted/ignored
    # instructions from negated instructions. This compiled path is allowed to consume only
    # the exact full-source official evidence ID registered by the proof obligation.
    if "linked_instructions_current_faq" in obligations and has("359.3.e.14", "359.3.e.14.a", "359.3.e.14.b"):
        eid = "O:vendetta-faq-2026-08-14:0035"
        src = source_evidence(eid)
        mistargeted = derived.get("earlier_linked_instruction_mistargeted", Truth.UNKNOWN)
        negated = derived.get("earlier_linked_instruction_negated", Truth.UNKNOWN)
        direct = derived.get("later_linked_instruction_directly_references_action", Truth.UNKNOWN)
        if src and mistargeted == Truth.TRUE:
            interpreted_overlay_ids.append(eid)
            outcomes.append({
                "claim": "A mistargeted earlier linked instruction is ignored; because it did not execute, the later linked instruction is ignored as well.",
                "verdict": "later_ignored",
                "truth": "true",
                "evidence": cites("359.3.e.14", "359.3.e.14.a"),
                "sourceEvidence": src,
            })
        elif src and negated == Truth.TRUE and direct == Truth.TRUE:
            interpreted_overlay_ids.append(eid)
            outcomes.append({
                "claim": "The earlier instruction is negated rather than ignored, but the later linked instruction directly depends on the Game Action that failed, so that later instruction does not execute.",
                "verdict": "later_does_not_execute",
                "truth": "true",
                "evidence": cites("359.3.e.14", "359.3.e.14.b"),
                "sourceEvidence": src,
            })
        elif src and negated == Truth.TRUE:
            interpreted_overlay_ids.append(eid)
            outcomes.append({
                "claim": "The earlier instruction is negated rather than ignored. Negation alone does not suppress a later linked instruction that does not directly depend on the failed Game Action, so the later instruction still executes.",
                "verdict": "later_executes",
                "truth": "true",
                "evidence": cites("359.3.e.14", "359.3.e.14.a", "359.3.e.14.b"),
                "sourceEvidence": src,
            })
        elif src:
            interpreted_overlay_ids.append(eid)
            outcomes.append({
                "claim": "The linked-instruction outcome depends on whether the earlier instruction mistargeted (ignored) or was instead prevented, replaced, or impossible (negated), and whether the later instruction directly references the failed Game Action.",
                "verdict": "conditional",
                "truth": "unknown",
                "evidence": cites("359.3.e.14", "359.3.e.14.a", "359.3.e.14.b"),
                "sourceEvidence": src,
            })

    if "replacement_order" in obligations and has("372", "372.1", "372.2", "373"):
        same_event = derived.get("multiple_replacement_effects_same_event", Truth.UNKNOWN)
        simultaneous = derived.get("simultaneous_replaceable_events", Truth.UNKNOWN)
        controlled_object = derived.get("affected_object_has_controller", Truth.UNKNOWN)
        affected_player = derived.get("affected_entity_is_player", Truth.UNKNOWN)
        uncontrolled_bf = derived.get("affected_object_uncontrolled_battlefield", Truth.UNKNOWN)
        if same_event == Truth.TRUE and controlled_object == Truth.TRUE:
            outcomes.append({
                "claim": "When multiple Replacement Effects apply to the same event acting on a controlled object, that object's controller determines the order in which those Replacement Effects apply.",
                "verdict": "controller_orders",
                "truth": "true",
                "evidence": cites("370.1", "372"),
                "applicability": evaluate_known_applicability("372", facts).to_dict(),
            })
        elif same_event == Truth.TRUE and affected_player == Truth.TRUE:
            outcomes.append({
                "claim": "When multiple Replacement Effects apply to the same event acting on a player, that player determines their order.",
                "verdict": "affected_player_orders",
                "truth": "true",
                "evidence": cites("370.1", "372", "372.1"),
                "applicability": evaluate_known_applicability("372.1", facts).to_dict(),
            })
        elif same_event == Truth.TRUE and uncontrolled_bf == Truth.TRUE:
            outcomes.append({
                "claim": "When multiple Replacement Effects apply to the same event acting on an Uncontrolled Battlefield, the Current Turn Player determines their order.",
                "verdict": "current_turn_player_orders",
                "truth": "true",
                "evidence": cites("370.1", "372", "372.2"),
                "applicability": evaluate_known_applicability("372.2", facts).to_dict(),
            })
        elif simultaneous == Truth.TRUE:
            outcomes.append({
                "claim": "Simultaneous replaceable events are treated separately for Replacement Effects. Applied Replacement Effects are still ordered; effects with the same controller are ordered by that controller, and simultaneous effects with different controllers execute in turn order.",
                "verdict": "separate_events",
                "truth": "true",
                "evidence": cites("373", "373.1", "373.1.a"),
                "applicability": evaluate_known_applicability("373", facts).to_dict(),
            })
        elif same_event == Truth.TRUE:
            outcomes.append({
                "claim": "The order of multiple Replacement Effects on one event depends on what entity is being acted on: a controlled object, a player, or an Uncontrolled Battlefield.",
                "verdict": "conditional",
                "truth": "unknown",
                "evidence": cites("372", "372.1", "372.2"),
            })

    if "play_finalize_semantics" in obligations and has("419.1", "419.4", "419.4.a", "419.4.a.1", "419.4.b", "425.1"):
        countered = derived.get("chain_item_countered", Truth.UNKNOWN)
        finalized = derived.get("chain_item_was_finalized", Truth.UNKNOWN)
        triggered = derived.get("played_check_is_triggered", Truth.UNKNOWN)
        non_triggered = derived.get("played_check_is_non_triggered", Truth.UNKNOWN)
        resolved = derived.get("card_resolved", Truth.UNKNOWN)
        if countered == Truth.TRUE and triggered == Truth.TRUE:
            outcomes.append({
                "claim": "A Countered card does not satisfy abilities that trigger on a card being played, because those triggers occur only when playing is completed by the card's resolution.",
                "verdict": "no_trigger",
                "truth": "true",
                "evidence": cites("419.4", "419.4.a", "419.4.a.1", "425.1"),
                "applicability": evaluate_known_applicability("419.4.a.1", facts).to_dict(),
            })
        elif finalized == Truth.TRUE and non_triggered == Truth.TRUE:
            outcomes.append({
                "claim": "A non-triggered ability that checks whether cards have been played checks whether the card was Finalized, so a Finalized card can satisfy that check even if it is later Countered.",
                "verdict": "counts_for_nontriggered_check",
                "truth": "true",
                "evidence": cites("419.1", "419.4", "419.4.b", "425.1"),
                "applicability": evaluate_known_applicability("419.4.b", facts).to_dict(),
            })
        elif resolved == Truth.TRUE and triggered == Truth.TRUE:
            outcomes.append({
                "claim": "For a triggered ability that triggers when a card is played, the act of playing is completed by resolution; the trigger condition is therefore satisfied when that resolution completes.",
                "verdict": "trigger_condition_satisfied",
                "truth": "true",
                "evidence": cites("419.4", "419.4.a"),
            })
        else:
            outcomes.append({
                "claim": "Riftbound distinguishes triggered 'when played' checks from non-triggered checks: triggered checks depend on resolution, while non-triggered checks reference Finalization. The question does not establish enough of those facts to choose one result.",
                "verdict": "conditional",
                "truth": "unknown",
                "evidence": cites("419.1", "419.4", "419.4.a", "419.4.a.1", "419.4.b", "425.1"),
            })

    if "copy_effect_semantics" in obligations and has("477", "477.1", "477.1.b", "477.1.b.1", "477.1.b.1.a", "477.1.b.1.b"):
        eid = "O:vendetta-faq-2026-08-14:0009"
        src = source_evidence(eid)
        copy_applied = derived.get("copy_effect_applied", Truth.UNKNOWN)
        source_temp = derived.get("copy_source_has_temporary_modification", Truth.UNKNOWN)
        receiver_temp = derived.get("copy_receiver_has_existing_temporary_might_mod", Truth.UNKNOWN)
        if src and copy_applied == Truth.TRUE and receiver_temp == Truth.TRUE:
            interpreted_overlay_ids.append(eid)
            outcomes.append({
                "claim": "A copy effect replaces/adds the receiving object's copyable traits, while temporary modifications already applied to the receiving object remain in place.",
                "verdict": "receiver_mod_remains",
                "truth": "true",
                "evidence": cites("477", "477.1", "477.1.b", "477.1.b.1", "477.1.b.1.a", "477.1.b.1.b"),
                "sourceEvidence": src,
            })
        elif src and copy_applied == Truth.TRUE and source_temp == Truth.TRUE:
            interpreted_overlay_ids.append(eid)
            outcomes.append({
                "claim": "A copy effect copies the source object's copyable traits, not temporary statuses or modifications such as Empowered, Buff, attacker/defender designations, or temporary Might changes.",
                "verdict": "temporary_mod_not_copied",
                "truth": "true",
                "evidence": cites("477", "477.1", "477.1.b", "477.1.b.1", "477.1.b.1.a", "477.1.b.1.b"),
                "sourceEvidence": src,
            })
        elif src:
            interpreted_overlay_ids.append(eid)
            outcomes.append({
                "claim": "Copy effects replace/add only copyable traits as specified by the copy effect. Whether a particular changed property is copied depends on whether it is a copyable trait or merely a temporary modification/status.",
                "verdict": "conditional",
                "truth": "unknown",
                "evidence": cites("477", "477.1", "477.1.b", "477.1.b.1", "477.1.b.1.a", "477.1.b.1.b"),
                "sourceEvidence": src,
            })

    if "layer_intermediate_state" in obligations and has("477", "477.1", "477.3"):
        eid = "O:vendetta-faq-2026-08-14:0030"
        src = source_evidence(eid)
        asks = derived.get("question_asks_intermediate_layer_state", Truth.UNKNOWN)
        if src and asks == Truth.TRUE:
            interpreted_overlay_ids.append(eid)
            outcomes.append({
                "claim": "Layer evaluation does not create an intermediate trigger window between trait-altering and arithmetic results, so a Might value that exists only as an intermediate conceptual layer step does not become a separately triggerable game state.",
                "verdict": "no_intermediate_trigger_window",
                "truth": "true",
                "evidence": cites("477", "477.1", "477.3"),
                "sourceEvidence": src,
            })
        elif src:
            interpreted_overlay_ids.append(eid)
            outcomes.append({
                "claim": "The current official layer clarification is relevant, but the question does not establish that it is asking about an intermediate layer-only value.",
                "verdict": "conditional",
                "truth": "unknown",
                "evidence": cites("477", "477.1", "477.3"),
                "sourceEvidence": src,
            })


    # Current Vendetta FAQ compilers. These consume exact full-source evidence IDs;
    # each path is deliberately narrow enough to preserve UNKNOWN rather than generalize
    # a card-specific ruling beyond what the official source supports.
    if "copy_might_current_faq" in obligations and has("477", "477.1", "477.1.a.1", "477.1.b", "477.1.b.1", "477.1.b.1.a", "477.1.b.1.b"):
        eid = "O:vendetta-faq-2026-08-14:0030"
        src = source_evidence(eid)
        if src:
            interpreted_overlay_ids.append(eid)
            outcomes.append({
                "claim": "Under the current Vendetta FAQ, Might is a copyable trait. A copy effect can therefore replace or add the copied object's Might, even though temporary Might increases/decreases remain temporary modifications rather than source traits to copy.",
                "verdict": "might_is_copyable_current",
                "truth": "true",
                "evidence": cites("477", "477.1", "477.1.a.1", "477.1.b", "477.1.b.1", "477.1.b.1.a", "477.1.b.1.b"),
                "sourceEvidence": src,
                "precedence": ["current official FAQ override", "Core Rules 477.1.b.1.a"],
            })

    if "flow_leave_chain_current_faq" in obligations and has("829", "829.1.b", "829.1.b.1"):
        eid = "O:vendetta-faq-2026-08-14:0002"
        src = source_evidence(eid)
        if src:
            interpreted_overlay_ids.append(eid)
            outcomes.append({
                "claim": "A spell played for its Flow cost is banished if it leaves the Chain after becoming Finalized for a reason other than its own execution. Countering it with Abandon and attempting to return it to hand still causes Flow's delayed replacement to banish it.",
                "verdict": "flow_spell_banished",
                "truth": "true",
                "evidence": cites("829", "829.1.b", "829.1.b.1"),
                "sourceEvidence": src,
            })

    if "replacement_chosen_event" in obligations and has("370.1", "370.1.b"):
        eid = "O:vendetta-faq-2026-08-14:0004"
        src = source_evidence(eid)
        if src:
            interpreted_overlay_ids.append(eid)
            outcomes.append({
                "claim": "A Replacement Effect whose qualifying event is defined around the object a spell or ability chooses applies only to the qualifying chosen-object event; similar effects on other unchosen objects are separate events and are not replaced by that effect.",
                "verdict": "only_qualifying_chosen_event_replaced",
                "truth": "true",
                "evidence": cites("370.1", "370.1.b"),
                "sourceEvidence": src,
            })

    if "replacement_inherits_modifiers" in obligations and has("375"):
        eid = "O:vendetta-faq-2026-08-14:0005"
        src = source_evidence(eid)
        if src:
            interpreted_overlay_ids.append(eid)
            outcomes.append({
                "claim": "When a Replacement Effect replaces an event that the generating Game Effect modified, the replacement event inherits those modifications. A limitation such as 'to a minimum of 1' therefore remains attached to the replaced event.",
                "verdict": "replacement_inherits_modifiers",
                "truth": "true",
                "evidence": cites("375"),
                "sourceEvidence": src,
            })

    if "replacement_missing_counter_event" in obligations and has("370.1", "370.1.c", "425.1"):
        eid = "O:vendetta-faq-2026-08-14:0006"
        src = source_evidence(eid)
        if src:
            interpreted_overlay_ids.append(eid)
            outcomes.append({
                "claim": "A Replacement Effect cannot replace a qualifying event that never occurs. If a spell cannot be Countered, an attempted Counter fails; an effect that depended on the resulting counter/removal event has no event to replace.",
                "verdict": "no_replacement_without_qualifying_event",
                "truth": "true",
                "evidence": cites("370.1", "370.1.c", "425.1"),
                "sourceEvidence": src,
            })

    if "rebuttal_remake_choices" in obligations and has("355.15"):
        eid = "O:vendetta-faq-2026-08-14:0008"
        src = source_evidence(eid)
        if src:
            interpreted_overlay_ids.append(eid)
            if (re.search(r"\b(?:leave|keep) .*illegal.*(?:unchanged|same)|(?:unchanged|same).*illegal.*(?:leave|keep)\b", q) or re.search(r"\bmust .*unchanged.*legal|unchanged.*must .*legal\b", q)) and re.search(r"\bremak|new choice|change\b", q):
                claim = "If Rebuttal's controller chooses to remake any choices, every choice they do not remake must still be legal. They cannot remake some choices while deliberately leaving another unchanged illegal choice."
                verdict = "unchanged_choices_must_be_legal"
                truth = "true"
            elif re.search(r"\b(?:no|none|zero) (?:new choices|choices remade)|\b(?:do not|don't|choose not to) (?:remake|make (?:any )?new choices)\b", q):
                claim = "Rebuttal's controller may choose not to make any new choices. In that case, the existing choices remain in their current state, including an already-illegal choice."
                verdict = "may_keep_all_existing_choices"
                truth = "true"
            else:
                claim = "When Rebuttal allows new choices, its controller may remake any number of targets or modes. Choices not remade stay the same, but if any choices are remade then each unchanged choice must be legal."
                verdict = "may_remake_any_number_of_choices"
                truth = "true"
            outcomes.append({"claim": claim, "verdict": verdict, "truth": truth, "evidence": cites("355.15"), "sourceEvidence": src})

    if "attach_replacement_sequence" in obligations and has("369.1", "370.1.a.2", "370.1.b.1", "434"):
        eid = "O:vendetta-faq-2026-08-14:0010"
        src = source_evidence(eid)
        if src:
            interpreted_overlay_ids.append(eid)
            outcomes.append({
                "claim": "For Shady Spectacles/Svellsongur-style replacement effects, the Attach event executes first and the copy/text event instructed by the replacement executes afterward; the two events are not simultaneous. A triggered ability gained only by the later copy therefore cannot see the already-completed Attach event.",
                "verdict": "attach_then_copy_not_simultaneous",
                "truth": "true",
                "evidence": cites("369.1", "370.1.a.2", "370.1.b.1", "434"),
                "sourceEvidence": src,
            })

    if "copied_ability_new_instance" in obligations and has("477.1.b", "477.1.b.1"):
        eid = "O:vendetta-faq-2026-08-14:0011"
        src = source_evidence(eid)
        if src:
            interpreted_overlay_ids.append(eid)
            outcomes.append({
                "claim": "Reapplying a copy effect can create a new instance of copied rules text/abilities while the underlying Game Object remains the same. Temporary modifications on that object remain, but the newly copied ability is a distinct ability instance.",
                "verdict": "copied_ability_is_new_instance",
                "truth": "true",
                "evidence": cites("477.1.b", "477.1.b.1"),
                "sourceEvidence": src,
            })

    if "multi_type_reflexive_trigger" in obligations and has("387.1.b"):
        eid = "O:vendetta-faq-2026-08-14:0013"
        src = source_evidence(eid)
        if src:
            interpreted_overlay_ids.append(eid)
            outcomes.append({
                "claim": "A 'Do the following' reflexive-trigger template creates each corresponding Reflexive Trigger whose listed condition/type is satisfied. A card with multiple applicable types can therefore create multiple triggers, rather than choosing only one unless the ability says 'Do one of the following.'",
                "verdict": "all_applicable_reflexive_triggers_created",
                "truth": "true",
                "evidence": cites("387.1.b"),
                "sourceEvidence": src,
            })

    if "naming_rules" in obligations and has("761", "761.1", "761.2", "762", "762.1", "762.2", "763"):
        eid = "O:vendetta-faq-2026-08-14:0015"
        src = source_evidence(eid)
        if src:
            interpreted_overlay_ids.append(eid)
            if re.search(r"\bdoes(?:n't| not) exist|nonexistent|not printed\b", q):
                claim = "You cannot name a card or tag that does not exist in Riftbound; a card named for this purpose must also be legal in the Format being played."
                verdict = "cannot_name_nonexistent_object"
            elif re.search(r"\bambiguous|two (?:different )?cards|more than one.*could|could refer to two|just .*kai'?sa\b", q):
                claim = "An ambiguous description does not successfully name a card; the information supplied must uniquely identify one card."
                verdict = "ambiguous_name_not_valid"
            elif re.search(r"\bunique(?:ly)? identif|description|describe .*card\b", q):
                claim = "You may name a card by a combination of traits/characteristics that uniquely identifies it; stating the exact printed name is not required if the identification is unambiguous."
                verdict = "unique_description_allowed"
            else:
                claim = "A card may be named by its exact name or by information that uniquely identifies it. Nonexistent cards/tags cannot be named, and card names must be legal in the current Format."
                verdict = "naming_rules"
            outcomes.append({"claim": claim, "verdict": verdict, "truth": "true", "evidence": cites("761", "761.1", "761.2", "762", "762.1", "762.2", "763"), "sourceEvidence": src})

    if "kayle_empowered_stacks" in obligations and has("002", "441.1", "441.1.b", "441.1.c", "441.1.c.1"):
        eids = ["O:vendetta-faq-2026-08-14:0016", "O:vendetta-faq-2026-08-14:0017"]
        srcs = [source_evidence(e) for e in eids]
        if all(srcs):
            interpreted_overlay_ids.extend(eids)
            if "disempower" in q:
                claim = "Kayle, Justified uses the Golden Rule to have a stacking Empowered status. Disempowering her removes one Empowered status, not all of her stacks."
                verdict = "remove_one_empowered_stack"
            elif re.search(r"\b(?:already|three|3).*empowered|empowered .*3|activate .*empower\b", q):
                claim = "Kayle's Empower ability may be activated even when she already has three Empowered statuses. At three stacks the ability can resolve, but no additional Empower event/status is produced."
                verdict = "ability_may_activate_but_no_additional_empower"
            else:
                claim = "Kayle, Justified is a card-specific Golden Rule exception: her Empowered status can stack up to three rather than being binary."
                verdict = "kayle_empowered_stacks_to_three"
            outcomes.append({"claim": claim, "verdict": verdict, "truth": "true", "evidence": cites("002", "441.1", "441.1.b", "441.1.c", "441.1.c.1"), "sourceEvidence": srcs[0], "additionalSourceEvidence": [s for s in srcs[1:] if s]})

    if "finalize_vs_resolve_control" in obligations and has("419.4", "419.4.a", "419.4.b"):
        eid = "O:vendetta-faq-2026-08-14:0019"
        src = source_evidence(eid)
        if src:
            interpreted_overlay_ids.append(eid)
            outcomes.append({
                "claim": "Changing control of a spell after Finalization does not change who Finalized it. Triggered checks that care about a spell you control resolving use the controller at resolution, while non-triggered checks of whether a player played/Finalized a card remain tied to who Finalized it.",
                "verdict": "resolution_control_differs_from_finalizer",
                "truth": "true",
                "evidence": cites("419.4", "419.4.a", "419.4.b"),
                "sourceEvidence": src,
            })

    if "swap_replacement_current_faq" in obligations and has("370.1", "433", "433.1", "433.1.a"):
        eid = "O:vendetta-faq-2026-08-14:0021"
        src = source_evidence(eid)
        if src:
            interpreted_overlay_ids.append(eid)
            outcomes.append({
                "claim": "Swap first calculates the difference and creates two distinct effects: an increase and a decrease. A Replacement Effect that qualifies for the decrease can replace that decrease independently without undoing the separately generated increase.",
                "verdict": "swap_creates_independent_increase_and_decrease",
                "truth": "true",
                "evidence": cites("370.1", "433", "433.1", "433.1.a"),
                "sourceEvidence": src,
            })

    if "replacement_missing_stun_event" in obligations and has("370.1", "423.1.a.1"):
        eid = "O:vendetta-faq-2026-08-14:0022"
        src = source_evidence(eid)
        if src:
            interpreted_overlay_ids.append(eid)
            outcomes.append({
                "claim": "A Stun instruction that cannot actually perform the Stun Game Action (for example because the unit is already Stunned or cannot be Stunned) produces no Stun event for a Replacement Effect to replace.",
                "verdict": "no_stun_event_to_replace",
                "truth": "true",
                "evidence": cites("370.1", "423.1.a.1"),
                "sourceEvidence": src,
            })

    if "replacement_missing_might_event" in obligations and has("370.1", "477.3.b"):
        eid = "O:vendetta-faq-2026-08-14:0023"
        src = source_evidence(eid)
        if src:
            interpreted_overlay_ids.append(eid)
            outcomes.append({
                "claim": "If an arithmetic limitation snapshots a Might decrease to -0, no Might-decrease event occurs. A Replacement Effect that requires a -M event therefore has no qualifying event to replace.",
                "verdict": "no_might_decrease_event_to_replace",
                "truth": "true",
                "evidence": cites("370.1", "477.3.b"),
                "sourceEvidence": src,
            })

    if "dependent_keyword_reference" in obligations and has("727.1", "727.1.b", "727.1.b.1"):
        eid = "O:vendetta-faq-2026-08-14:0025"
        src = source_evidence(eid)
        if src:
            interpreted_overlay_ids.append(eid)
            outcomes.append({
                "claim": "A Dependent Ability remains present for reference/evaluation even while its Dependent Keyword condition is unmet and the ability is Inactive. Other effects can therefore identify or gain that ability before its condition is true.",
                "verdict": "inactive_dependent_ability_can_be_referenced",
                "truth": "true",
                "evidence": cites("727.1", "727.1.b", "727.1.b.1"),
                "sourceEvidence": src,
            })

    if "competing_positive_play_requirements" in obligations and has("355.2", "355.2.a", "355.2.b"):
        eid = "O:vendetta-faq-2026-08-14:0027"
        src = source_evidence(eid)
        if src:
            interpreted_overlay_ids.append(eid)
            outcomes.append({
                "claim": "When multiple mandatory positive requirements instruct the same Unit to be played to different locations and none is a restriction/prohibition, the current official ruling lets the player choose one requirement and ignore the others. This does not override 'can't' or 'only' restrictions.",
                "verdict": "choose_one_positive_play_requirement",
                "truth": "true",
                "evidence": cites("355.2", "355.2.a", "355.2.b"),
                "sourceEvidence": src,
            })

    if "cant_beats_can_play_location" in obligations and has("054", "054.1", "054.2", "355.2.b", "369.3"):
        eid = "O:vendetta-faq-2026-08-14:0028"
        src = source_evidence(eid)
        if src:
            interpreted_overlay_ids.append(eid)
            outcomes.append({
                "claim": "A play-location permission cannot overcome a contradictory 'can't'/'only' restriction. If no legal location remains during finalization, the play cannot finalize and the actions taken as part of playing the card are undone. A separate enters-the-board Replacement Effect can operate differently because it changes the entry event rather than granting play permission.",
                "verdict": "restriction_beats_play_location_permission",
                "truth": "true",
                "evidence": cites("054", "054.1", "054.2", "355.2.b", "369.3"),
                "sourceEvidence": src,
            })

    if "legend_control_current_faq" in obligations:
        eid = "O:vendetta-faq-2026-08-14:0029"
        src = source_evidence(eid)
        if src:
            interpreted_overlay_ids.append(eid)
            outcomes.append({
                "claim": "A player controls their own Legend. Legend control normally cannot change, but the Legend is still a controlled Game Object for effects that ask whether you control it.",
                "verdict": "yes_control_own_legend",
                "truth": "true",
                "evidence": cites("188", "189"),
                "sourceEvidence": src,
            })

    if "invalid_other_base_play" in obligations and has("355.2", "355.2.a"):
        eid = "O:vendetta-faq-2026-08-14:0031"
        src = source_evidence(eid)
        if src:
            interpreted_overlay_ids.append(eid)
            outcomes.append({
                "claim": "A Unit cannot be played to another player's Base. If an effect instructs an owner to play a Unit to a Base other than that player's own, the play is illegal at the final legality check; the item returns to its prior zone and actions taken for the attempted play are undone.",
                "verdict": "cannot_play_to_other_players_base",
                "truth": "true",
                "evidence": cites("355.2", "355.2.a", "359.2"),
                "sourceEvidence": src,
            })

    if "become_state_transition" in obligations:
        eid = "O:vendetta-faq-2026-08-14:0032"
        src = source_evidence(eid)
        if src:
            interpreted_overlay_ids.append(eid)
            outcomes.append({
                "claim": "A trigger that checks whether an object 'becomes' a state requires a transition into that state. Remaining within the state while its numeric value changes does not create another 'becomes' event.",
                "verdict": "requires_transition_into_state",
                "truth": "true",
                "evidence": cites("124"),
                "sourceEvidence": src,
            })

    if "ignore_deflect_scope" in obligations and has("766", "767"):
        eid = "O:vendetta-faq-2026-08-14:0033"
        src = source_evidence(eid)
        if src:
            interpreted_overlay_ids.append(eid)
            outcomes.append({
                "claim": "When an effect instructs you to ignore Deflect for a specified spell/action, those Deflect abilities are treated as Inactive only for that specified action/procedure. The permission does not carry over to a different spell or action.",
                "verdict": "deflect_ignored_only_for_specified_action",
                "truth": "true",
                "evidence": cites("766", "767"),
                "sourceEvidence": src,
            })

    if "delayed_trigger_attribution" in obligations and has("411.4", "411.5", "411.6", "428.5", "428.5.d"):
        eid = "O:vendetta-faq-2026-08-14:0034"
        src = source_evidence(eid)
        if src:
            interpreted_overlay_ids.append(eid)
            outcomes.append({
                "claim": "A delayed triggered ability generated by a spell can be attributed the Kill action it performs, and that Kill can also be attributed back to the spell that generated the ability. Responsibility remains with the controller of the resolving ability as defined by the Game Action responsibility rules.",
                "verdict": "kill_attribution_propagates_to_generating_spell",
                "truth": "true",
                "evidence": cites("411.4", "411.5", "411.6", "428.5", "428.5.d"),
                "sourceEvidence": src,
            })

    # Card restriction conflict: compile the narrow pattern now; ambiguous card text remains uncompiled.
    if "card_rule_precedence" in obligations and named_cards:
        for card in named_cards:
            text = card.get("effectiveText") or ""
            low = text.lower()
            if "opponents can only play units to their base" in low:
                at_bf = derived.get("named_card_at_battlefield", Truth.UNKNOWN)
                if at_bf == Truth.TRUE:
                    outcomes.append({
                        "claim": f"While {card['name']} is at a battlefield, its restriction limits opponents to playing Units to their Base, overriding a default permission to play to controlled battlefields.",
                        "verdict": "restricted_to_base",
                        "truth": "true",
                        "cardEvidence": {
                            "evidenceId": f"C:{card['id']}",
                            "cardId": card["id"],
                            "name": card["name"],
                            "text": text,
                        },
                        "evidence": cites("002", "054", "054.1", "054.2", "355.2.a"),
                        "precedence": ["card restriction", "Golden Rule", "Can't beats Can / only restriction", "default play-location permission"],
                    })
                elif at_bf == Truth.FALSE:
                    outcomes.append({
                        "claim": f"{card['name']}'s restriction is inactive because the card is not at a battlefield in the stated scenario.",
                        "verdict": "restriction_inactive",
                        "truth": "false",
                        "cardEvidence": {"evidenceId": f"C:{card['id']}", "cardId": card["id"], "name": card["name"], "text": text},
                        "evidence": cites("002", "054.2", "355.2.a"),
                    })
                else:
                    outcomes.append({
                        "claim": f"{card['name']}'s restriction matters only while it is at a battlefield; that condition is not established.",
                        "verdict": "conditional",
                        "truth": "unknown",
                        "cardEvidence": {"evidenceId": f"C:{card['id']}", "cardId": card["id"], "name": card["name"], "text": text},
                        "evidence": cites("002", "054.2", "355.2.a"),
                    })

    if not outcomes:
        return {
            "status": "insufficient",
            "issue": issue,
            "reason": "No deterministic adjudication template can yet prove a verdict for the detected obligations. Evidence remains available for later compilation or LLM-assisted interpretation.",
            "outcomes": [],
            "effectiveVerdict": None,
            "interpretedOfficialOverlayEvidenceIds": interpreted_overlay_ids,
            "ruleProgramDiagnostics": rule_program_diagnostics,
        }

    # Precedence resolution happens after individual propositions are established.
    # A default permission remains true as a general rule even when a specific current
    # card restriction makes it unavailable in the actual scenario.
    effective = None
    restricted = next((o for o in outcomes if o.get("verdict") == "restricted_to_base"), None)
    invalid_other_base = next((o for o in outcomes if o.get("verdict") == "cannot_play_to_other_players_base"), None)
    might_copyable = next((o for o in outcomes if o.get("verdict") == "might_is_copyable_current"), None)
    default_play = next((o for o in outcomes if o.get("verdict") == "yes" and "played directly" in o.get("claim", "")), None)
    if might_copyable:
        for o in outcomes:
            if o is not might_copyable and o.get("verdict") == "conditional" and any(e.get("ruleId", "").startswith("477") for e in o.get("evidence", [])):
                o["effectStatus"] = "superseded_in_scenario"
                o["supersededBy"] = "current_might_copyable_override"
        effective = {
            "verdict": "might_is_copyable_current",
            "reason": might_copyable.get("claim"),
            "basis": [e.get("evidenceId") for e in might_copyable.get("evidence", [])] + [((might_copyable.get("sourceEvidence") or {}).get("evidenceId"))],
        }
    elif invalid_other_base:
        for o in outcomes:
            if o is not invalid_other_base and o.get("verdict") == "conditional" and any(e.get("ruleId") in {"355.2", "355.2.a", "355.2.b"} for e in o.get("evidence", [])):
                o["effectStatus"] = "superseded_in_scenario"
                o["supersededBy"] = "current_other_base_prohibition"
        effective = {
            "verdict": "cannot_play_to_other_players_base",
            "reason": invalid_other_base.get("claim"),
            "basis": [e.get("evidenceId") for e in invalid_other_base.get("evidence", [])] + [((invalid_other_base.get("sourceEvidence") or {}).get("evidenceId"))],
        }
    elif restricted:
        if default_play is not None:
            default_play["effectStatus"] = "superseded_in_scenario"
            default_play["supersededBy"] = "card_restriction"
        effective = {
            "verdict": "no",
            "reason": "The card's active 'only' restriction controls the scenario over the default play-location permission.",
            "basis": [restricted.get("cardEvidence", {}).get("evidenceId"), "R:002", "R:054.2", "R:355.2.a"],
        }
    elif default_play is not None and any(o.get("verdict") == "restriction_inactive" for o in outcomes):
        effective = {
            "verdict": "yes",
            "reason": "The card-specific restriction is inactive in the stated location, so the default controlled-Battlefield play permission remains effective.",
            "basis": ["R:355.2.a"] + [o.get("cardEvidence", {}).get("evidenceId") for o in outcomes if o.get("verdict") == "restriction_inactive"],
        }
    elif len(outcomes) == 1:
        o = outcomes[0]
        effective = {"verdict": o.get("verdict"), "reason": o.get("claim"), "basis": _outcome_basis(o)}
    elif not any(x.get("truth") == "unknown" and x.get("effectStatus") != "superseded_in_scenario" for x in outcomes):
        chosen = _select_specific_true_outcome(issue, outcomes)
        if chosen is not None:
            effective = {"verdict": chosen.get("verdict"), "reason": chosen.get("claim"), "basis": _outcome_basis(chosen)}
    elif any(x.get("truth") == "unknown" for x in outcomes):
        # A general rule can be known while a potentially controlling special-case
        # condition is unknown. Do not lead with the general-rule answer as though the
        # scenario were decided.
        unknowns = [x for x in outcomes if x.get("truth") == "unknown"]
        effective = {
            "verdict": "conditional",
            "reason": unknowns[0].get("claim") or "A potentially controlling condition is not established.",
            "basis": [e.get("evidenceId") for o in outcomes for e in o.get("evidence", [])],
        }

    unresolved_unknown = any(x["truth"] == "unknown" and x.get("effectStatus") != "superseded_in_scenario" for x in outcomes)
    if unresolved_unknown and not restricted and not invalid_other_base and not might_copyable:
        status = "conditional"
    else:
        status = "decided"
    return {"status": status, "issue": issue, "outcomes": outcomes, "effectiveVerdict": effective, "interpretedOfficialOverlayEvidenceIds": interpreted_overlay_ids, "ruleProgramDiagnostics": rule_program_diagnostics}
