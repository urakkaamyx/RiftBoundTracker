from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from .scenario import Fact, Truth, fact_map


# Declarative registry of rule conditions that are safe to execute deterministically.
# Each spec is backed by regression tests. Rules not present here remain UNKNOWN rather
# than being interpreted heuristically at adjudication time.
PREDICATE_SPECS: dict[str, dict[str, Any]] = {
    "190.3.a.1": {
        "all": [
            {"fact": "battlefield_already_contested", "op": "not", "label": "battlefield is not already Contested"},
            {"fact": "unit_controller_already_controls_battlefield", "op": "not", "label": "unit controller does not already control battlefield"},
        ],
        "note": "Both stated conditions of 190.3.a.1 must hold for this rule to newly apply Contested.",
    },
    "190.4.c": {
        "all": [
            {"fact": "actor_has_units_at_battlefield_after_event", "op": "not", "label": "player has no units at battlefield"},
            {"fact": "turn_is_open_state", "op": "is_true", "label": "turn is in an Open State"},
            {"fact": "combat_ongoing_at_battlefield", "op": "not", "label": "no Combat ongoing there"},
            {"fact": "showdown_ongoing_at_battlefield", "op": "not", "label": "no Showdown ongoing there"},
        ],
        "note": "Battlefield-control loss is conditional on occupancy and game state.",
    },
    "323.6": {
        "sameAs": "190.4.c",
        "note": "Cleanup performs the same no-Units/Open-State/no-Combat/no-Showdown battlefield-control check.",
    },
    "323.5": {
        "all": [
            {"fact": "unit_has_lethal_damage", "op": "is_true", "label": "unit has Lethal Damage"},
            {"fact": "cleanup_occurs", "op": "is_true", "label": "Cleanup occurs"},
        ],
        "note": "323.5 is the Cleanup task that kills units with Lethal Damage.",
    },
    "323.7": {
        "all": [
            {"fact": "hidden_card_at_battlefield", "op": "is_true", "label": "hidden card is at battlefield"},
            {"fact": "actor_controls_battlefield", "op": "not", "label": "battlefield is not controlled by same player"},
        ],
        "note": "Within Cleanup, 323.7 removes Hidden cards from battlefields no longer controlled by the same player.",
    },
    "355.2.a": {
        "any": [
            {"fact": "unit_play_destination_is_base", "op": "is_true", "label": "destination is the controller's Base"},
            {"fact": "unit_controller_already_controls_battlefield", "op": "is_true", "label": "destination battlefield is controlled by unit controller"},
        ],
        "note": "By default, a Unit may enter at its controller's Base or a Battlefield its controller controls.",
    },
    "355.2.b": {
        "all": [
            {"fact": "game_effect_grants_play_location_permission", "op": "is_true", "label": "a Game Effect grants permission for the normally invalid location"},
        ],
        "note": "A Game Effect can make a normally invalid Unit-play location valid for that play.",
    },
    "437.4": {
        "all": [
            {"fact": "damage_was_dealt", "op": "not", "label": "all damage is prevented / damage not dealt"},
        ],
        "note": "When all damage is prevented, it is not considered dealt at all.",
    },
    "415.1.b": {"all": [{"fact": "unit_already_ready", "op": "is_true", "label": "unit is already Ready"}], "note": "An already Ready Unit cannot be Readied again."},
    "414.1.b": {"all": [{"fact": "object_already_exhausted", "op": "is_true", "label": "object is already Exhausted"}], "note": "An already Exhausted Game Object cannot be Exhausted again."},
    "414.4": {"all": [{"fact": "exhaust_is_cost", "op": "is_true", "label": "Exhaust is listed as a cost"}, {"fact": "object_already_exhausted", "op": "not", "label": "the Exhaust action can be completed"}], "note": "An Exhaust cost can only be paid if the Exhaust action can be completed."},
    "423.1.a.1": {"all": [{"fact": "unit_already_stunned", "op": "is_true", "label": "unit is already Stunned"}], "note": "A Stunned Unit cannot be Stunned again."},
    "425.1": {"all": [{"fact": "chain_item_countered", "op": "is_true", "label": "card or ability is Countered"}], "note": "Counter consequences apply to a Countered chain item."},
    "359.3.e.7": {"all": [{"fact": "all_targets_illegal_on_resolution", "op": "is_true", "label": "all instruction targets are invalid/unavailable on resolution"}], "note": "An instruction with no valid/available targets will not execute."},
    "456": {"all": [{"fact": "action_is_recall", "op": "is_true", "label": "the relocation is a Recall"}], "note": "Recall is explicitly not a Move."},
    "469.1": {"all": [{"fact": "gains_control_of_battlefield", "op": "is_true", "label": "player gains Control of a Battlefield"}, {"fact": "battlefield_already_scored_this_turn", "op": "not", "label": "battlefield was not yet Scored this turn"}], "note": "That combination is the definition of Conquer."},
    "469.2": {"all": [{"fact": "maintains_control_of_battlefield", "op": "is_true", "label": "player maintains Control of a Battlefield"}, {"fact": "battlefield_already_scored_this_turn", "op": "not", "label": "battlefield was not yet Scored this turn"}, {"fact": "during_beginning_phase", "op": "is_true", "label": "during the Beginning Phase"}], "note": "That combination is the definition of Hold."},
    "355.10.b": {"all": [{"fact": "battlefield_mention_is_play_location_only", "op": "is_true", "label": "battlefield is mentioned only as a play restriction/permission"}], "note": "A game object or zone mentioned only as a restriction or permission for a Game Action is not a target."},
    "758": {"all": [{"fact": "target_untargetable_at_choice", "op": "is_true", "label": "object is Untargetable when target choices are made"}], "note": "Untargetable objects are not legal targets for the indicated spells and abilities."},
    "758.1": {"all": [{"fact": "target_became_untargetable_after_targeted", "op": "is_true", "label": "object becomes Untargetable after being chosen and before resolution"}], "note": "The spell/ability mistargets that object on resolution."},
    "372": {"all": [{"fact": "multiple_replacement_effects_same_event", "op": "is_true", "label": "multiple Replacement Effects apply to the same event"}, {"fact": "affected_object_has_controller", "op": "is_true", "label": "the affected object has a controller"}], "note": "The controller of the affected object orders Replacement Effects applying to the same event."},
    "372.1": {"all": [{"fact": "multiple_replacement_effects_same_event", "op": "is_true", "label": "multiple Replacement Effects apply to the same event"}, {"fact": "affected_entity_is_player", "op": "is_true", "label": "a player is being acted on"}], "note": "The affected player orders the Replacement Effects."},
    "372.2": {"all": [{"fact": "multiple_replacement_effects_same_event", "op": "is_true", "label": "multiple Replacement Effects apply to the same event"}, {"fact": "affected_object_uncontrolled_battlefield", "op": "is_true", "label": "the affected object is an Uncontrolled Battlefield"}], "note": "The Current Turn Player orders Replacement Effects on an Uncontrolled Battlefield."},
    "373": {"all": [{"fact": "simultaneous_replaceable_events", "op": "is_true", "label": "multiple replaceable events occur simultaneously"}], "note": "Each simultaneous event is treated separately for Replacement Effects."},
    "465.2.c.5": {"all": [{"fact": "combat_damage_replacement_effect_applies", "op": "is_true", "label": "a Replacement Effect would apply to resulting combat damage"}], "note": "Such Replacement Effects are considered during combat damage assignment instead."},
    "419.4.a.1": {"all": [{"fact": "chain_item_countered", "op": "is_true", "label": "the card was Countered"}, {"fact": "played_check_is_triggered", "op": "is_true", "label": "the check is a triggered played-card ability"}], "note": "A Countered card does not satisfy triggered abilities that trigger on cards being played."},
    "419.4.b": {"all": [{"fact": "chain_item_was_finalized", "op": "is_true", "label": "the card was Finalized"}, {"fact": "played_check_is_non_triggered", "op": "is_true", "label": "the check is non-triggered"}], "note": "Non-triggered played-card checks reference whether the card was Finalized."},
    "359.3.f.3": {"all": [{"fact": "trigger_uses_information_from_condition", "op": "is_true", "label": "the triggered ability references information from its trigger condition"}], "note": "Referenced trigger-condition information is checked when the trigger condition is fulfilled."},
}


def t_not(x: Truth) -> Truth:
    if x == Truth.TRUE:
        return Truth.FALSE
    if x == Truth.FALSE:
        return Truth.TRUE
    return Truth.UNKNOWN


def t_and(xs: list[Truth]) -> Truth:
    if any(x == Truth.FALSE for x in xs):
        return Truth.FALSE
    if xs and all(x == Truth.TRUE for x in xs):
        return Truth.TRUE
    return Truth.UNKNOWN


def t_or(xs: list[Truth]) -> Truth:
    if any(x == Truth.TRUE for x in xs):
        return Truth.TRUE
    if xs and all(x == Truth.FALSE for x in xs):
        return Truth.FALSE
    return Truth.UNKNOWN


@dataclass
class PredicateResult:
    predicate: str
    value: Truth
    basis: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["value"] = self.value.value
        return d


@dataclass
class RuleApplicability:
    rule_id: str
    applicability: Truth
    predicates: list[PredicateResult]
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "ruleId": self.rule_id,
            "applicability": self.applicability.value,
            "predicates": [x.to_dict() for x in self.predicates],
            "note": self.note,
        }


def _resolve_spec(rule_id: str) -> dict[str, Any] | None:
    spec = PREDICATE_SPECS.get(rule_id)
    if not spec:
        return None
    if spec.get("sameAs"):
        base = _resolve_spec(str(spec["sameAs"]))
        if not base:
            return None
        merged = dict(base)
        merged["note"] = spec.get("note") or base.get("note")
        return merged
    return spec


def _eval_clause(clause: dict[str, Any], fm: dict[str, Truth]) -> PredicateResult:
    fact_name = str(clause["fact"])
    raw = fm.get(fact_name, Truth.UNKNOWN)
    op = clause.get("op", "is_true")
    if op == "is_true":
        value = raw
    elif op == "not":
        value = t_not(raw)
    elif op == "is_false":
        value = Truth.TRUE if raw == Truth.FALSE else Truth.FALSE if raw == Truth.TRUE else Truth.UNKNOWN
    else:
        value = Truth.UNKNOWN
    return PredicateResult(
        str(clause.get("label") or fact_name),
        value,
        f"scenario fact: {fact_name}",
    )


def evaluate_rule_applicability(rule_id: str, facts: list[Fact]) -> RuleApplicability:
    spec = _resolve_spec(rule_id)
    if not spec:
        return RuleApplicability(rule_id, Truth.UNKNOWN, [], "No compiled applicability predicate for this rule yet; do not guess.")
    fm = fact_map(facts)
    all_predicates = [_eval_clause(c, fm) for c in spec.get("all", [])]
    any_predicates = [_eval_clause(c, fm) for c in spec.get("any", [])]
    predicates = all_predicates + any_predicates
    parts: list[Truth] = []
    if all_predicates:
        parts.append(t_and([p.value for p in all_predicates]))
    if any_predicates:
        parts.append(t_or([p.value for p in any_predicates]))
    value = t_and(parts) if parts else Truth.UNKNOWN
    return RuleApplicability(rule_id, value, predicates, str(spec.get("note") or ""))


def registry_snapshot() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "compiledRuleCount": len(PREDICATE_SPECS),
        "compiledRuleIds": sorted(PREDICATE_SPECS.keys(), key=lambda x: [int(p) if p.isdigit() else p for p in x.replace('.', ' ').split()]),
        "rules": PREDICATE_SPECS,
        "policy": "Only explicitly registered and regression-tested predicates are executable. Unregistered rules evaluate to UNKNOWN rather than being guessed.",
    }
