from __future__ import annotations

from typing import Any

from .scenario import Truth


def _fact_map(facts: list[Any]) -> dict[str, Truth]:
    return {getattr(f, "name", ""): getattr(f, "value", Truth.UNKNOWN) for f in facts}


def clarification_questions(issue: str, ruling: dict[str, Any], obligations: list[str], facts: list[Any], named_cards: list[dict[str, Any]] | None = None) -> list[dict[str, str]]:
    """Return bounded deterministic questions for facts a compiled ruling knows it lacks.

    This is not a generic guesser. It only asks questions tied to explicit predicates
    already used by compiled adjudication families.
    """
    if ruling.get("status") != "conditional":
        return []
    fm = _fact_map(facts)
    out: list[dict[str, str]] = []

    def add(fact: str, question: str, why: str) -> None:
        if fm.get(fact, Truth.UNKNOWN) == Truth.UNKNOWN and not any(x["fact"] == fact for x in out):
            out.append({"fact": fact, "question": question, "whyNeeded": why})

    obs = set(obligations)
    if {"hidden_lifecycle", "battlefield_control_loss"} & obs:
        add("turn_is_open_state", "Is the game in an Open State when this Cleanup would happen?", "Cleanup/control-loss timing can depend on the current game state.")
        add("combat_ongoing_at_battlefield", "Is Combat ongoing at that battlefield?", "Control/Cleanup processing can be delayed or differ while Combat is ongoing.")
        add("showdown_ongoing_at_battlefield", "Is a Showdown ongoing at that battlefield?", "Control/Cleanup processing can depend on an ongoing Showdown.")
    if "contested_on_entry" in obs:
        add("unit_controller_already_controls_battlefield", "Does the Unit's controller already control that battlefield?", "Contested-on-entry depends on whether the entering Unit's controller already controls the battlefield.")
        add("battlefield_already_contested", "Is that battlefield already Contested?", "The Contested application rule checks the battlefield's current status.")
    if "unit_play_location" in obs:
        add("actor_controls_battlefield", "Do you control the battlefield you want to play the Unit to?", "The default valid Battlefield destination depends on control.")
    if "card_rule_precedence" in obs and named_cards:
        for card in named_cards:
            if "while i'm at a battlefield" in (card.get("effectiveText") or "").lower():
                add("named_card_at_battlefield", f"Is {card.get('name')} currently at a battlefield?", "That card's restriction is conditional on being at a battlefield.")
                break
    if "ready_state" in obs:
        add("unit_already_ready", "Is the object already Ready before the instruction?", "Ready is a state-change action and the prior state matters.")
    if "exhaust_state" in obs:
        add("object_already_exhausted", "Is the object already Exhausted before the instruction or cost?", "Exhaust legality depends on the object's current state.")
    if "stun_state" in obs:
        add("unit_already_stunned", "Is the Unit already Stunned?", "A Unit already Stunned cannot become Stunned again.")
    if "battlefield_count_requirement" in obs:
        add("deck_mode_of_play", "Which Mode of Play are you using?", "The number of Battlefields required for a deck is dictated by the Mode of Play.")

    return out[:4]
