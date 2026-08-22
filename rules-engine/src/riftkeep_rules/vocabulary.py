from __future__ import annotations

import re
from typing import Any

# Conservative player-language aliases for official Core Rules Game Actions.
# These are vocabulary mappings, not rulings. They only say which official term a
# player phrase is likely referring to; applicability still comes from evidence/rules.
GAME_ACTION_ALIASES: dict[str, dict[str, Any]] = {
    "Draw": {"ruleId": "413", "phrases": ["draw", "draws", "drew"]},
    "Exhaust": {"ruleId": "414", "phrases": ["exhaust", "exhausts", "exhausted"]},
    "Ready": {"ruleId": "415", "phrases": ["ready", "readies", "readied"]},
    "Recycle": {"ruleId": "416", "phrases": ["recycle", "recycles", "recycled"]},
    "Deal": {"ruleId": "417", "phrases": ["deal damage", "deals damage", "dealt damage", "take damage", "takes damage", "took damage", "damage"]},
    "Heal": {"ruleId": "418", "phrases": ["heal", "heals", "healed"]},
    "Play": {"ruleId": "419", "phrases": ["play", "plays", "played", "playing"]},
    "Move": {"ruleId": "420", "phrases": ["move", "moves", "moved", "moving"]},
    "Hide": {"ruleId": "421", "phrases": ["hide", "hides", "hid", "hidden"]},
    "Discard": {"ruleId": "422", "phrases": ["discard", "discards", "discarded"]},
    "Stun": {"ruleId": "423", "phrases": ["stun", "stuns", "stunned"]},
    "Reveal": {"ruleId": "424", "phrases": ["reveal", "reveals", "revealed"]},
    "Counter": {"ruleId": "425", "phrases": ["counter", "counters", "countered"]},
    "Buff": {"ruleId": "426", "phrases": ["buff", "buffs", "buffed"]},
    "Banish": {"ruleId": "427", "phrases": ["banish", "banishes", "banished"]},
    "Kill": {"ruleId": "428", "phrases": ["kill", "kills", "killed", "dies", "died", "die"]},
    "Add": {"ruleId": "429", "phrases": ["add", "adds", "added"]},
    "Channel": {"ruleId": "430", "phrases": ["channel", "channels", "channeled", "channelled"]},
    "Burn Out": {"ruleId": "431", "phrases": ["burn out", "burns out", "burned out", "burnt out"]},
    "Double": {"ruleId": "432", "phrases": ["double", "doubles", "doubled"]},
    "Swap": {"ruleId": "433", "phrases": ["swap", "swaps", "swapped"]},
    "Attach": {"ruleId": "434", "phrases": ["attach", "attaches", "attached"]},
    "Detach": {"ruleId": "435", "phrases": ["detach", "detaches", "detached"]},
    "Predict": {"ruleId": "436", "phrases": ["predict", "predicts", "predicted"]},
    "Prevent": {"ruleId": "437", "phrases": ["prevent", "prevents", "prevented", "preventing"]},
    "Replace": {"ruleId": "438", "phrases": ["replace", "replaces", "replaced", "replacement"]},
    "Create": {"ruleId": "439", "phrases": ["create", "creates", "created"]},
    "Burn": {"ruleId": "440", "phrases": ["burn", "burns", "burned", "burnt"]},
    "Empower": {"ruleId": "441", "phrases": ["empower", "empowers", "empowered"]},
    "Disempower": {"ruleId": "442", "phrases": ["disempower", "disempowers", "disempowered"]},
    "Skip": {"ruleId": "443", "phrases": ["skip", "skips", "skipped"]},
    "Pay": {"ruleId": "444", "phrases": ["pay", "pays", "paid"]},
}


def _contains_phrase(text: str, phrase: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text))


def detect_game_actions(text: str) -> list[dict[str, Any]]:
    low = (text or "").lower().replace("’", "'")
    out: list[dict[str, Any]] = []
    for name, meta in GAME_ACTION_ALIASES.items():
        hits = [p for p in meta["phrases"] if _contains_phrase(low, p)]
        if hits:
            out.append({"name": name, "ruleId": meta["ruleId"], "matchedPhrases": hits})
    return out


def retrieval_action_terms(text: str) -> list[str]:
    terms: list[str] = []
    for hit in detect_game_actions(text):
        terms.extend([hit["name"].lower(), f"game action {hit['name'].lower()}"])
        # Deal is the important rules-language bridge for player-facing damage phrasing.
        if hit["name"] == "Deal":
            terms.extend(["dealt damage", "marked damage"])
    return list(dict.fromkeys(terms))
