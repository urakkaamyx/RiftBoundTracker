from __future__ import annotations

import re
from typing import Any

# Player vocabulary only. These mappings do not define game rules and never alter
# authoritative source text. They exist solely to interpret common TCG phrasing.
# Each replacement is intentionally narrow and every transformation is returned to
# the caller for audit/display.
_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"\buntapped\b", re.I), "Ready", "common TCG 'untapped' -> Riftbound Ready"),
    (re.compile(r"\buntapping\b", re.I), "Readying", "common TCG 'untapping' -> Riftbound Readying"),
    (re.compile(r"\buntap\b", re.I), "Ready", "common TCG 'untap' -> Riftbound Ready"),
    (re.compile(r"\btapped\b", re.I), "Exhausted", "common TCG 'tapped' -> Riftbound Exhausted"),
    (re.compile(r"\btapping\b", re.I), "Exhausting", "common TCG 'tapping' -> Riftbound Exhausting"),
    (re.compile(r"\btap\b", re.I), "Exhaust", "common TCG 'tap' -> Riftbound Exhaust"),
    (re.compile(r"\bcasting\b", re.I), "Playing", "common TCG 'casting' -> Riftbound Playing"),
    (re.compile(r"\bcasted\b", re.I), "played", "common TCG 'casted' -> Riftbound played"),
    (re.compile(r"\bcasts\b", re.I), "plays", "common TCG 'casts' -> Riftbound plays"),
    (re.compile(r"\bcast\b", re.I), "play", "common TCG 'cast' -> Riftbound Play"),
    (re.compile(r"\bsummoning\b", re.I), "Playing", "common TCG 'summoning' -> Riftbound Playing"),
    (re.compile(r"\bsummoned\b", re.I), "played", "common TCG 'summoned' -> Riftbound played"),
    (re.compile(r"\bsummons\b", re.I), "plays", "common TCG 'summons' -> Riftbound plays"),
    (re.compile(r"\bsummon\b", re.I), "play", "common TCG 'summon' -> Riftbound Play"),
    (re.compile(r"\bgraveyard\b", re.I), "Trash", "common TCG 'graveyard' -> Riftbound Trash"),
    (re.compile(r"\bdiscard pile\b", re.I), "Trash", "common TCG 'discard pile' -> Riftbound Trash"),
]

# Terms that are common in player speech but are unsafe to reinterpret without more
# context. They are surfaced instead of silently mapped.  "battle" is the canonical
# regression boundary because it could refer to a Battlefield, Combat, or Showdown.
_AMBIGUOUS: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r"\bbattle\b", re.I),
        "battle",
        "'battle' is not an official one-to-one alias; it may refer to a Battlefield, Combat, or Showdown",
    ),
]


def normalize_player_language(text: str) -> dict[str, Any]:
    original = text or ""
    current = original
    transformations: list[dict[str, str]] = []
    for pattern, replacement, reason in _PATTERNS:
        matches = list(pattern.finditer(current))
        if not matches:
            continue
        original_terms: list[str] = []
        seen: set[str] = set()
        for m in matches:
            term = m.group(0)
            if term.casefold() not in seen:
                seen.add(term.casefold())
                original_terms.append(term)
        current = pattern.sub(replacement, current)
        for term in original_terms:
            transformations.append({"from": term, "to": replacement, "reason": reason})

    ambiguous_terms: list[dict[str, str]] = []
    for pattern, term, reason in _AMBIGUOUS:
        if pattern.search(current):
            ambiguous_terms.append({"term": term, "reason": reason})

    return {
        "original": original,
        "text": current,
        "changed": current != original,
        "transformations": transformations,
        "ambiguousTerms": ambiguous_terms,
    }
