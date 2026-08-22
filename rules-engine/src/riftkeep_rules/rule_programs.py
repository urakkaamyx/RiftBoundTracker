from __future__ import annotations

from typing import Any

from .rule_compiler import text_hash
from .scenario import Fact, Truth, fact_map


# Declarative executable programs.  These are intentionally narrow and backed by
# existing regression rulings.  Source text guards prevent a future Core Rules PDF
# from silently continuing to execute stale semantics after any governing rule text
# changes.
PROGRAM_SPECS: list[dict[str, Any]] = [
    {
        "programId": "discard-to-trash",
        "obligation": "discard_to_trash",
        "evidenceRuleIds": ["422", "422.1", "422.1.a", "422.1.b"],
        "sourceTextGuards": {
            "422": "Discard",
            "422.1": "Discarding a card is moving it from a player's hand directly into their trash without activating or executing its normal rules text.",
            "422.1.a": "The player who is performing the action chooses which cards to send to their Trash, and may use Private Information to do so.",
            "422.1.b": "“When I am discarded” abilities or other Triggered Abilities that trigger on discarding are executed after discarding has occurred.",
        },
        "cases": [{
            "when": [], "verdict": "yes", "truth": "true",
            "claim": "Discarding a card moves it directly from its player's hand to that player's Trash without executing the card's normal rules text.",
            "evidenceRuleIds": ["422", "422.1", "422.1.a", "422.1.b"],
        }],
        "fallback": None,
    },
    {
        "programId": "replace-not-play",
        "obligation": "replacement_not_play",
        "evidenceRuleIds": ["438", "438.1"],
        "sourceTextGuards": {
            "438": "Replace",
            "438.1": "Replacing is the act of Creating a token in the place of another card or token without playing it while inheriting all effects or statuses of the game object it replaced.",
        },
        "cases": [{
            "when": [], "verdict": "no", "truth": "true",
            "claim": "Replacing creates a token in another object's place without playing that token.",
            "evidenceRuleIds": ["438", "438.1"],
        }],
        "fallback": None,
    },
    {
        "programId": "ready-binary-state",
        "obligation": "ready_state",
        "evidenceRuleIds": ["415.1", "415.1.b", "415.1.c"],
        "sourceTextGuards": {
            "415.1": "Readying is an action that marks a non-spell Game Object on the board as available for action.",
            "415.1.b": "A Unit that is already Ready cannot be Readied again.",
            "415.1.c": "If a Unit is instructed to be Readied while it is already Ready, nothing additional happens.",
        },
        "cases": [{
            "when": [{"fact": "unit_already_ready", "op": "is_true"}],
            "verdict": "no", "truth": "true",
            "claim": "An already Ready Unit cannot be Readied again; an instruction to Ready it causes nothing additional to happen, so there is no new Ready event from that instruction.",
            "evidenceRuleIds": ["415.1", "415.1.b", "415.1.c"],
            "applicabilityRuleId": "415.1.b",
        }],
        "fallback": {
            "verdict": "conditional", "truth": "unknown",
            "claim": "This compiled ruling only resolves the already-Ready case; the question does not establish that state.",
            "evidenceRuleIds": ["415.1", "415.1.b", "415.1.c"],
        },
    },
    {
        "programId": "exhaust-binary-state-and-cost",
        "obligation": "exhaust_state",
        "evidenceRuleIds": ["414.1", "414.1.b", "414.1.c", "414.4"],
        "sourceTextGuards": {
            "414.1": "Exhausting is an action that marks a non-spell Game Object on the board as \"spent.\"",
            "414.1.b": "A Game Object that is already Exhausted cannot be Exhausted again.",
            "414.1.c": "If a Game Object is instructed to be Exhausted while it is already Exhausted, nothing additional happens.",
            "414.4": "When Exhausting is listed as a Cost, then the Action must be able to be completed for the cost to be paid.",
        },
        "cases": [
            {
                "when": [{"fact": "object_already_exhausted", "op": "is_true"}, {"fact": "exhaust_is_cost", "op": "is_true"}],
                "verdict": "no", "truth": "true",
                "claim": "An already Exhausted Game Object cannot be Exhausted again, so an Exhaust cost cannot be paid with it because the required action cannot be completed.",
                "evidenceRuleIds": ["414.1", "414.1.b", "414.1.c", "414.4"],
                "applicabilityRuleId": "414.4",
            },
            {
                "when": [{"fact": "object_already_exhausted", "op": "is_true"}],
                "verdict": "no", "truth": "true",
                "claim": "An already Exhausted Game Object cannot be Exhausted again; an instruction to Exhaust it causes nothing additional to happen.",
                "evidenceRuleIds": ["414.1", "414.1.b", "414.1.c"],
                "applicabilityRuleId": "414.1.b",
            },
        ],
        "fallback": {
            "verdict": "conditional", "truth": "unknown",
            "claim": "Whether this Exhaust instruction or cost can be performed depends on the object's current Exhausted state and whether Exhaust is being paid as a cost.",
            "evidenceRuleIds": ["414.1.b", "414.1.c", "414.4"],
        },
    },
    {
        "programId": "stun-binary-state",
        "obligation": "stun_state",
        "evidenceRuleIds": ["423.1.a", "423.1.a.1"],
        "sourceTextGuards": {
            "423.1.a": "Stunned is a binary state. A Unit is Stunned or it isn't.",
            "423.1.a.1": "A Stunned Unit can not be Stunned again.",
        },
        "cases": [{
            "when": [{"fact": "unit_already_stunned", "op": "is_true"}],
            "verdict": "no", "truth": "true",
            "claim": "Stunned is a binary state, and a Unit that is already Stunned cannot be Stunned again; no new Stun action occurs.",
            "evidenceRuleIds": ["423.1.a", "423.1.a.1"],
            "applicabilityRuleId": "423.1.a.1",
        }],
        "fallback": {
            "verdict": "conditional", "truth": "unknown",
            "claim": "This compiled ruling only resolves the already-Stunned case; the question does not establish that state.",
            "evidenceRuleIds": ["423.1.a", "423.1.a.1"],
        },
    },
    {
        "programId": "play-location-not-target",
        "obligation": "targeting_permission_restriction",
        "evidenceRuleIds": ["355.10", "355.10.b"],
        "sourceTextGuards": {
            "355.10": "A game object, player, or zone mentioned in the text of a spell, activated ability, or triggered ability is a target UNLESS any of the following are true:",
            "355.10.b": "It is included only as part of a targeting restriction for another choice or only as a restriction or permission for a game action. e.g., “Kill a unit at a battlefield” targets a unit, but not a battlefield, because the units are targets and “at a battlefield” is a restriction. e.g., “Kill all units at a battlefield” targets a battlefield, but not any units. e.g., “Play a unit from your hand to a battlefield” doesn’t target a battlefield.",
        },
        "cases": [{
            "when": [{"fact": "battlefield_mention_is_play_location_only", "op": "is_true"}],
            "verdict": "no", "truth": "true",
            "claim": "A Battlefield mentioned only as the destination, restriction, or permission for playing a Unit is not itself a target.",
            "evidenceRuleIds": ["355.10", "355.10.b"],
            "applicabilityRuleId": "355.10.b",
        }],
        "fallback": {
            "verdict": "conditional", "truth": "unknown",
            "claim": "Whether the mentioned Battlefield is a target depends on whether it is merely a restriction/permission for another Game Action or is independently chosen as a target.",
            "evidenceRuleIds": ["355.10", "355.10.b"],
        },
    },
    {
        "programId": "combat-damage-replacement-assignment",
        "obligation": "combat_replacement_assignment",
        "evidenceRuleIds": ["465.2.c.1", "465.2.c.5"],
        "sourceTextGuards": {
            "465.2.c.1": "Assigning Damage is not Dealing Damage.",
            "465.2.c.5": "When assigning damage in this way, replacement effects that would apply to the resulting damage are considered to apply to the assignment instead.",
        },
        "cases": [{
            "when": [{"fact": "combat_damage_replacement_effect_applies", "op": "is_true"}],
            "verdict": "apply_during_assignment", "truth": "true",
            "claim": "During combat damage assignment, Replacement Effects that would apply to the resulting combat damage are considered to apply to the assignment instead. Assignment itself is not Dealing Damage.",
            "evidenceRuleIds": ["465.2.c.1", "465.2.c.5"],
            "applicabilityRuleId": "465.2.c.5",
        }],
        "fallback": {
            "verdict": "conditional", "truth": "unknown",
            "claim": "This combat rule applies when a Replacement Effect would modify the resulting combat damage; the question does not establish that condition.",
            "evidenceRuleIds": ["465.2.c.1", "465.2.c.5"],
        },
    },
    {
        "programId": "trigger-condition-snapshot",
        "obligation": "trigger_snapshot",
        "evidenceRuleIds": ["359.3.f.3", "383.2", "383.2.c"],
        "sourceTextGuards": {
            "359.3.f.3": "Some information used by triggered abilities is referenced from the trigger condition of the ability. This information is checked when the trigger condition is fulfilled.",
            "383.2": "Triggered Abilities have a Condition and an Effect.",
            "383.2.c": "The Condition of a Trigger is evaluated after a potentially inciting event has been processed.",
        },
        "cases": [{
            "when": [{"fact": "trigger_uses_information_from_condition", "op": "is_true"}],
            "verdict": "snapshot_at_trigger", "truth": "true",
            "claim": "Information referenced from a triggered ability's trigger condition is checked when that trigger condition is fulfilled; later changes do not cause that referenced information to be re-read on resolution unless another rule or instruction requires it.",
            "evidenceRuleIds": ["359.3.f.3", "383.2", "383.2.c"],
            "applicabilityRuleId": "359.3.f.3",
        }],
        "fallback": {
            "verdict": "conditional", "truth": "unknown",
            "claim": "This snapshot rule applies only to information referenced from the trigger condition itself; that relationship is not established in the question.",
            "evidenceRuleIds": ["359.3.f.3", "383.2", "383.2.c"],
        },
    },
    # Deck Construction (Rule 103 family). See RiftKeep 1.0.1's Deck Construction Obligation
    # Integration Fix - these are ordinary declarative programs like every other one in this
    # file; the only thing distinctive about Deck Construction is that its facts are numeric
    # quantities rather than binary game-state predicates (see deck_construction.py).
    {
        "programId": "deck-champion-legend-count",
        "obligation": "champion_legend_count",
        "evidenceRuleIds": ["103", "103.1"],
        "sourceTextGuards": {
            "103": "To play Riftbound, a player must have a Main Deck, a Rune Deck, a Champion Legend, and a number of Battlefields determined by the Mode of Play. These are collectively referred to as a player’s deck.",
            "103.1": "1 Champion Legend",
        },
        "cases": [
            {
                "when": [{"fact": "deck_legend_count_exceeds_one", "op": "is_true"}],
                "verdict": "no", "truth": "true",
                "claim": "A deck requires exactly 1 Champion Legend; more than one is not allowed.",
                "evidenceRuleIds": ["103", "103.1"],
            },
            {
                "when": [{"fact": "deck_legend_count_exceeds_one", "op": "is_false"}],
                "verdict": "yes", "truth": "true",
                "claim": "A deck requires exactly 1 Champion Legend, and this satisfies that requirement.",
                "evidenceRuleIds": ["103", "103.1"],
            },
            {
                "when": [{"fact": "deck_legend_count_how_many", "op": "is_true"}],
                "verdict": "exactly_one_required", "truth": "true",
                "claim": "Rule 103.1 sets this as a fixed requirement, not a range: precisely 1 Champion Legend, no more and no fewer.",
                "evidenceRuleIds": ["103", "103.1"],
            },
        ],
        "fallback": {
            "verdict": "exactly_one_required", "truth": "true",
            "claim": "A deck requires exactly 1 Champion Legend.",
            "evidenceRuleIds": ["103", "103.1"],
        },
    },
    {
        "programId": "deck-main-deck-minimum",
        "obligation": "main_deck_minimum",
        "evidenceRuleIds": ["103.2"],
        "sourceTextGuards": {
            "103.2": "A Main Deck of at least 40 cards: A Chosen Champion Unit, as well as Units, Gear, and Spells",
        },
        "cases": [
            {
                "when": [{"fact": "deck_main_deck_below_minimum", "op": "is_true"}],
                "verdict": "no", "truth": "true",
                "claim": "A Main Deck must contain at least 40 cards.",
                "evidenceRuleIds": ["103.2"],
            },
            {
                "when": [{"fact": "deck_main_deck_below_minimum", "op": "is_false"}],
                "verdict": "yes", "truth": "true",
                "claim": "40 is a minimum, not an exact count, so this satisfies the Main Deck size requirement (subject to any other deck-construction rules).",
                "evidenceRuleIds": ["103.2"],
            },
            {
                "when": [{"fact": "deck_main_deck_how_many", "op": "is_true"}],
                "verdict": "at_least_forty_required", "truth": "true",
                "claim": "That is a minimum, not an exact count - a larger Main Deck is not invalid merely for exceeding 40.",
                "evidenceRuleIds": ["103.2"],
            },
        ],
        "fallback": {
            "verdict": "at_least_forty_required", "truth": "true",
            "claim": "A Main Deck must contain at least 40 cards.",
            "evidenceRuleIds": ["103.2"],
        },
    },
    {
        "programId": "deck-same-name-copy-limit",
        "obligation": "same_name_copy_limit",
        "evidenceRuleIds": ["103.2.b", "103.2.b.1", "103.2.b.2"],
        "sourceTextGuards": {
            "103.2.b": "Your Main Deck can include up to 3 copies of the same named card.",
            "103.2.b.1": "This includes your Chosen Champion.",
            "103.2.b.2": "Cards have different names even if they represent the same character.",
        },
        "cases": [
            {
                "when": [{"fact": "deck_copy_limit_chosen_champion_question", "op": "is_true"}],
                "verdict": "chosen_champion_counts_toward_limit", "truth": "true",
                "claim": "The up-to-3-copies limit includes your Chosen Champion; it is not an additional copy on top of the limit.",
                "evidenceRuleIds": ["103.2.b", "103.2.b.1"],
            },
            {
                "when": [{"fact": "deck_copy_limit_exceeds_three", "op": "is_true"}],
                "verdict": "no", "truth": "true",
                "claim": "A Main Deck can include up to 3 copies of the same named card, including your Chosen Champion.",
                "evidenceRuleIds": ["103.2.b", "103.2.b.1"],
            },
            {
                "when": [{"fact": "deck_copy_limit_exceeds_three", "op": "is_false"}],
                "verdict": "yes", "truth": "true",
                "claim": "Up to 3 copies of the same named card is allowed, and this satisfies that limit.",
                "evidenceRuleIds": ["103.2.b"],
            },
            {
                "when": [{"fact": "deck_copy_limit_how_many", "op": "is_true"}],
                "verdict": "up_to_three_allowed", "truth": "true",
                "claim": "This includes your Chosen Champion. Note cards have different names even if they represent the same character, so this limit is per exact card name.",
                "evidenceRuleIds": ["103.2.b", "103.2.b.1", "103.2.b.2"],
            },
        ],
        "fallback": {
            "verdict": "up_to_three_allowed", "truth": "true",
            "claim": "A Main Deck can include up to 3 copies of the same named card, including your Chosen Champion.",
            "evidenceRuleIds": ["103.2.b", "103.2.b.1"],
        },
    },
    {
        "programId": "deck-signature-limit",
        "obligation": "signature_limit",
        "evidenceRuleIds": ["103.2.d", "103.2.d.1", "103.2.d.2", "103.2.d.3"],
        "sourceTextGuards": {
            "103.2.d": "Your deck may only contain 3 total Signature cards that have the same Champion tag as your Champion Legend.",
            "103.2.d.1": "Regardless of name, a deck may only contain a sum total of 3 Signature cards.",
            "103.2.d.2": "All of the Signature cards must have the Champion tag that corresponds to the Champion Legend of the deck.",
            "103.2.d.3": "Signature cards are not Champion units and cannot be placed in the Champion Zone.",
        },
        "cases": [
            {
                "when": [{"fact": "deck_signature_different_champion_question", "op": "is_true"}],
                "verdict": "no", "truth": "true",
                "claim": "Every Signature card in a deck must share the Champion tag of that deck's Champion Legend.",
                "evidenceRuleIds": ["103.2.d", "103.2.d.2"],
            },
            {
                "when": [{"fact": "deck_signature_as_chosen_champion_question", "op": "is_true"}],
                "verdict": "no", "truth": "true",
                "claim": "Signature cards are not Champion units and cannot be placed in the Champion Zone, so a Signature card cannot be your Chosen Champion.",
                "evidenceRuleIds": ["103.2.d.3"],
            },
            {
                "when": [{"fact": "deck_signature_exceeds_three", "op": "is_true"}],
                "verdict": "no", "truth": "true",
                "claim": "A deck may contain at most 3 total Signature cards, regardless of name.",
                "evidenceRuleIds": ["103.2.d", "103.2.d.1"],
            },
            {
                "when": [{"fact": "deck_signature_exceeds_three", "op": "is_false"}],
                "verdict": "yes", "truth": "true",
                "claim": "Up to 3 total Signature cards is allowed, provided they share the deck's Champion tag, and this satisfies that limit.",
                "evidenceRuleIds": ["103.2.d", "103.2.d.1"],
            },
            {
                "when": [{"fact": "deck_signature_how_many", "op": "is_true"}],
                "verdict": "up_to_three_total_required", "truth": "true",
                "claim": "A deck may contain at most 3 total Signature cards, all sharing the Champion tag of that deck's Champion Legend.",
                "evidenceRuleIds": ["103.2.d", "103.2.d.1", "103.2.d.2"],
            },
        ],
        "fallback": {
            "verdict": "up_to_three_total_required", "truth": "true",
            "claim": "A deck may contain at most 3 total Signature cards, all sharing the Champion tag of that deck's Champion Legend; Signature cards cannot be the Chosen Champion.",
            "evidenceRuleIds": ["103.2.d", "103.2.d.1", "103.2.d.2", "103.2.d.3"],
        },
    },
    {
        "programId": "deck-rune-deck-count",
        "obligation": "rune_deck_count",
        "evidenceRuleIds": ["103.3", "103.3.a", "103.3.a.1"],
        "sourceTextGuards": {
            "103.3": "Rune Deck",
            "103.3.a": "12 Rune Cards",
            "103.3.a.1": "Cards in the Rune Deck must be of the Domain Identity of your Champion Legend.",
        },
        "cases": [
            {
                "when": [{"fact": "deck_rune_domain_identity_question", "op": "is_true"}],
                "verdict": "must_match_domain_identity", "truth": "true",
                "claim": "Cards in the Rune Deck must be of the Domain Identity of your Champion Legend.",
                "evidenceRuleIds": ["103.3.a.1"],
            },
            {
                "when": [{"fact": "deck_rune_count_not_twelve", "op": "is_true"}],
                "verdict": "no", "truth": "true",
                "claim": "A Rune Deck must contain exactly 12 Rune Cards.",
                "evidenceRuleIds": ["103.3", "103.3.a"],
            },
            {
                "when": [{"fact": "deck_rune_count_not_twelve", "op": "is_false"}],
                "verdict": "yes", "truth": "true",
                "claim": "Exactly 12 Rune Cards satisfies the Rune Deck requirement.",
                "evidenceRuleIds": ["103.3", "103.3.a"],
            },
            {
                "when": [{"fact": "deck_rune_count_how_many", "op": "is_true"}],
                "verdict": "exactly_twelve_required", "truth": "true",
                "claim": "That is a fixed count, not a minimum - a Rune Deck is kept and shuffled separately from the Main Deck.",
                "evidenceRuleIds": ["103.3", "103.3.a"],
            },
        ],
        "fallback": {
            "verdict": "exactly_twelve_required", "truth": "true",
            "claim": "A Rune Deck must contain exactly 12 Rune Cards, kept and shuffled separately from the Main Deck, and matching the Domain Identity of your Champion Legend.",
            "evidenceRuleIds": ["103.3", "103.3.a", "103.3.a.1"],
        },
    },
    {
        "programId": "deck-battlefield-duplicate-limit",
        "obligation": "battlefield_duplicate_limit",
        "evidenceRuleIds": ["103.4", "103.4.c"],
        "sourceTextGuards": {
            "103.4": "Battlefields",
            "103.4.c": "Cannot include more than one of a Battlefield of the same name when there are more than one required for the deck.",
        },
        "cases": [{
            "when": [{"fact": "deck_battlefield_duplicate_question", "op": "is_true"}],
            "verdict": "no", "truth": "true",
            "claim": "A deck cannot include more than one Battlefield of the same name when more than one Battlefield is required for that deck.",
            "evidenceRuleIds": ["103.4.c"],
        }],
        "fallback": {
            "verdict": "conditional", "truth": "unknown",
            "claim": "Whether a duplicate-named Battlefield is allowed depends on whether more than one Battlefield is required for this deck.",
            "evidenceRuleIds": ["103.4.c"],
        },
    },
    {
        "programId": "deck-battlefield-count-requirement",
        "obligation": "battlefield_count_requirement",
        "evidenceRuleIds": ["103.4", "103.4.a"],
        "sourceTextGuards": {
            "103.4": "Battlefields",
            "103.4.a": "The number will be dictated by your Mode of Play.",
        },
        "cases": [],
        "fallback": {
            "verdict": "conditional", "truth": "unknown",
            "claim": "The number of Battlefields required for a deck is dictated by your Mode of Play, so this can't be answered with a single number without knowing which Mode of Play you're using.",
            "evidenceRuleIds": ["103.4", "103.4.a"],
        },
    },
    {
        "programId": "attach-exhausted-state-independence",
        "obligation": "attach_exhausted_state_legality",
        "evidenceRuleIds": ["719.4", "434.2", "434.2.a"],
        "sourceTextGuards": {
            "719.4": "The Exhausted and Ready state of the Top-Most card does not affect nor change the status of the Attached cards and vice versa.",
            "434.2": "Attaching is a Limited Action.",
            "434.2.a": "Players may only Attach cards when directed to by Game Effects.",
        },
        "cases": [{
            "when": [], "verdict": "yes", "truth": "true",
            "claim": "Exhausted/Ready state does not prevent a card from being Attached, or from having a card Attached to it - the Top-Most card's Exhausted/Ready state is explicitly independent of its Attached cards' status, and vice versa. Attaching only happens when a Game Effect directs it (such as a Gear's Equip ability), and that Game Effect's own wording controls what it actually requires - typically that you control the unit, not that you control the battlefield it's at.",
            "evidenceRuleIds": ["719.4", "434.2", "434.2.a"],
        }],
        "fallback": None,
    },
]


def _norm(text: str) -> str:
    return " ".join((text or "").strip().split())


def compile_rule_programs(core: dict[str, Any]) -> dict[str, Any]:
    by_id = {str(r.get("ruleId")): r for r in core.get("rules", [])}
    programs: list[dict[str, Any]] = []
    for spec in PROGRAM_SPECS:
        errors: list[str] = []
        guards: dict[str, dict[str, str]] = {}
        for rid, expected in spec.get("sourceTextGuards", {}).items():
            actual_rule = by_id.get(rid)
            actual = _norm((actual_rule or {}).get("normativeText") or (actual_rule or {}).get("text") or "")
            expected_norm = _norm(expected)
            guards[rid] = {
                "expectedTextHash": text_hash(expected_norm),
                "actualTextHash": text_hash(actual),
            }
            if not actual_rule:
                errors.append(f"missing_rule:{rid}")
            elif actual != expected_norm:
                errors.append(f"source_text_changed:{rid}")
        missing_evidence = [rid for rid in spec.get("evidenceRuleIds", []) if rid not in by_id]
        errors.extend(f"missing_evidence_rule:{rid}" for rid in missing_evidence)
        row = dict(spec)
        row["sourceTextGuardHashes"] = guards
        row["valid"] = not errors
        row["executable"] = not errors
        row["validationErrors"] = errors
        row["compilerVersion"] = 1
        programs.append(row)
    return {
        "schemaVersion": 1,
        "programCount": len(programs),
        "validProgramCount": sum(1 for p in programs if p.get("valid")),
        "programs": programs,
        "policy": "Only explicit regression-tested programs execute. Every program is disabled if any guarded governing rule text changes or required evidence is missing.",
    }


def _truth_not(v: Truth) -> Truth:
    return Truth.FALSE if v == Truth.TRUE else Truth.TRUE if v == Truth.FALSE else Truth.UNKNOWN


def _eval_clause(clause: dict[str, Any], facts: dict[str, Truth]) -> Truth:
    raw = facts.get(str(clause.get("fact")), Truth.UNKNOWN)
    op = clause.get("op", "is_true")
    if op == "is_true":
        return raw
    if op in {"not", "is_false"}:
        return _truth_not(raw)
    return Truth.UNKNOWN


def _case_state(clauses: list[dict[str, Any]], facts: dict[str, Truth]) -> Truth:
    if not clauses:
        return Truth.TRUE
    vals = [_eval_clause(c, facts) for c in clauses]
    if any(v == Truth.FALSE for v in vals):
        return Truth.FALSE
    if all(v == Truth.TRUE for v in vals):
        return Truth.TRUE
    return Truth.UNKNOWN


def evaluate_rule_programs(
    compiled: dict[str, Any],
    obligations: list[str],
    facts: list[Fact],
    by_rule_id: dict[str, dict[str, Any]],
    applicability_fn,
) -> tuple[list[dict[str, Any]], set[str], list[dict[str, Any]]]:
    """Evaluate matching programs and return outcomes, consumed obligations, diagnostics."""
    fm = fact_map(facts)
    obligation_set = set(obligations)
    outcomes: list[dict[str, Any]] = []
    consumed: set[str] = set()
    diagnostics: list[dict[str, Any]] = []

    def cite(rid: str) -> dict[str, Any]:
        r = by_rule_id[rid]
        return {
            "evidenceId": f"R:{rid}", "ruleId": rid,
            "text": r.get("normativeText") or r.get("text") or "",
            "pageStart": r.get("pageStart"), "pageEnd": r.get("pageEnd"),
            "sourceId": r.get("sourceId"),
        }

    for program in compiled.get("programs", []):
        obligation = str(program.get("obligation") or "")
        if obligation not in obligation_set:
            continue
        diag = {"programId": program.get("programId"), "obligation": obligation, "executed": False, "reason": None}
        if not program.get("valid") or not program.get("executable"):
            diag["reason"] = "program_invalid_or_disabled"
            diagnostics.append(diag)
            continue
        missing = [rid for rid in program.get("evidenceRuleIds", []) if rid not in by_rule_id]
        if missing:
            diag["reason"] = "required_evidence_not_in_proof"
            diag["missingEvidenceRuleIds"] = missing
            diagnostics.append(diag)
            continue
        # Runtime guard: compiled expected hashes must still match the decisive evidence.
        drift: list[str] = []
        for rid, guard in (program.get("sourceTextGuardHashes") or {}).items():
            if rid not in by_rule_id:
                drift.append(rid)
                continue
            actual = by_rule_id[rid].get("normativeText") or by_rule_id[rid].get("text") or ""
            if text_hash(actual) != guard.get("expectedTextHash"):
                drift.append(rid)
        if drift:
            diag["reason"] = "runtime_source_drift"
            diag["driftRuleIds"] = drift
            diagnostics.append(diag)
            continue

        selected = None
        for case in program.get("cases", []):
            if _case_state(case.get("when") or [], fm) == Truth.TRUE:
                selected = case
                break
        if selected is None:
            selected = program.get("fallback")
        if selected is None:
            diag["reason"] = "no_matching_case"
            diagnostics.append(diag)
            continue

        evidence_ids = selected.get("evidenceRuleIds") or program.get("evidenceRuleIds") or []
        outcome = {
            "claim": selected.get("claim") or "",
            "verdict": selected.get("verdict") or "conditional",
            "truth": selected.get("truth") or "unknown",
            "evidence": [cite(rid) for rid in evidence_ids if rid in by_rule_id],
            "ruleProgram": {"programId": program.get("programId"), "compilerVersion": program.get("compilerVersion")},
        }
        app_rule = selected.get("applicabilityRuleId")
        if app_rule:
            outcome["applicability"] = applicability_fn(app_rule, facts).to_dict()
        outcomes.append(outcome)
        consumed.add(obligation)
        diag["executed"] = True
        diag["reason"] = "matched_case" if selected in program.get("cases", []) else "fallback"
        diag["verdict"] = outcome["verdict"]
        diagnostics.append(diag)
    return outcomes, consumed, diagnostics
