from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .errata import canonical_card_identity


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


# Tournament context is opt-in. It is activated ONLY by one of these explicit keywords/phrases -
# never inferred from generic card-game language. In particular "deck", bare "legal"/"illegal",
# and phrases like "can I play"/"can I use"/"can I run"/"can I include"/"allowed" are deliberately
# NOT signals here: they're common in ordinary gameplay and deck-construction questions and must
# not be sufficient on their own, or in combination with each other, to trigger tournament/format
# routing. Only an explicit keyword from this list does. See RiftKeep 1.0.1's Core-First Tournament
# Context Routing patch.
_STRONG_FORMAT_PHRASES = (
    "tournament legal", "tournament legality", "tournament rules", "tournament deck",
    "tournament play", "tournament",
    "sanctioned event", "sanctioned",
    "2v2 constructed", "constructed", "2v2",
    "format legal", "format legality", "format",
    "ban list", "banned", "restricted",
    "event policy", "match procedure", "round", "judge call",
    "deck registration", "deck list", "penalty",
    "game loss", "match loss", "disqualification",
)
# Word-boundary matching, not substring - a naive "phrase in q" check let "format" match inside
# "information" and would let "round" match inside "background". q is already normalized to
# single spaces between alnum runs, so \b...\b is exact for both single- and multi-word phrases.
_STRONG_FORMAT_PATTERNS = [re.compile(r"\b" + re.escape(p) + r"\b") for p in _STRONG_FORMAT_PHRASES]

_QUANTITY_WORDS = {
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "multiple", "several", "another",
}


def _has_quantity_language(q: str) -> bool:
    # Deck-construction quantity questions ("how many", "two", "more than one", "13 runes") are
    # Core Rule 103 questions regardless of whether a strong keyword like "tournament deck" also
    # appears in the same sentence (e.g. "two Champion Legends in a tournament deck" is still a
    # Core quantity question, not a banned-list lookup). \b\d+\b deliberately does not match the
    # digit embedded in a token like "2v2", which is itself a strong format keyword, not a quantity.
    if "how many" in q or "more than one" in q:
        return True
    if re.search(r"\b\d+\b", q):
        return True
    return bool(set(q.split()) & _QUANTITY_WORDS)


def is_legality_question(question: str) -> bool:
    q = _norm(question)
    # "legal/illegal target on resolution" is game-rule legality, not format legality.
    if ("target" in q or "targets" in q) and any(x in q for x in ("resolve", "resolution", "mistarget")):
        return False
    # "banned"/"ban list" are inherently format-legality concepts - they route to format legality
    # on their own, without requiring the player to also say "tournament".
    if "banned" in q.split() or re.search(r"\bban list\b", q):
        return True
    if _has_quantity_language(q):
        return False
    return any(p.search(q) for p in _STRONG_FORMAT_PATTERNS)


def _find_subject(question: str, named_cards: list[dict[str, Any]], all_names: list[str]) -> str | None:
    if named_cards:
        return named_cards[0].get("name")
    q = _norm(question)
    candidates = sorted(all_names, key=len, reverse=True)
    for name in candidates:
        if _norm(name) in q:
            return name
    return None


def adjudicate_legality(root: Path, question: str, named_cards: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not is_legality_question(question):
        return None
    p = root / "data/source/rules_hub_metadata.json"
    if not p.exists():
        return {
            "status": "insufficient", "issue": question, "outcomes": [], "effectiveVerdict": None,
            "reason": "Current Rules Hub legality data is not locally available."
        }
    hub = json.loads(p.read_text(encoding="utf-8"))
    q = _norm(question)
    mode = "twoVsTwoConstructed" if re.search(r"\b2v2\b|\btwo vs two\b|\btwo versus two\b", q) else "constructed"
    data = hub[mode]
    banned_entries: list[tuple[str, str]] = []
    for cat, names in data.get("banned", {}).items():
        for name in names:
            banned_entries.append((cat, name))
    subject = _find_subject(question, named_cards, [n for _, n in banned_entries])
    if not subject:
        return {
            "status": "conditional", "issue": question, "outcomes": [], "effectiveVerdict": None,
            "reason": "The legality question is recognized, but no specific card, battlefield, or legend could be resolved."
        }
    subject_identity = canonical_card_identity(subject)
    match = next(((cat, n) for cat, n in banned_entries if canonical_card_identity(n) == subject_identity), None)
    mode_label = "2v2 Constructed" if mode == "twoVsTwoConstructed" else "Constructed"
    if match:
        verdict = "banned"
        claim = f"{subject} is on the current {mode_label} banned list."
        category = match[0]
    else:
        verdict = "legal"
        claim = f"{subject} is not on the current {mode_label} banned list captured from the Rules Hub. This only establishes ban-list status, not every deckbuilding requirement."
        category = None
    ev = {
        "evidenceId": "O:rules-hub-current:legality",
        "sourceId": "rules-hub-current",
        "title": "Official Riftbound Rules Hub",
        "sourceUrl": hub.get("sourceUrl"),
        "lastUpdated": data.get("lastUpdated"),
        "category": category,
        "text": claim,
    }
    outcome = {"claim": claim, "verdict": verdict, "truth": "true", "sourceEvidence": ev, "evidence": []}
    return {
        "status": "decided", "issue": question, "outcomes": [outcome],
        "effectiveVerdict": {"verdict": verdict, "reason": claim, "basis": [ev["evidenceId"]]},
        "legalityMode": mode_label,
    }
