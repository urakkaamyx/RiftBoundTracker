from __future__ import annotations

import re
from typing import Any


# Deck Construction (Core Rule 103 family) as a first-class obligation family, following the
# same pattern as every other obligation in proof.py/rule_programs.py: detect an obligation from
# the question, derive boolean facts the compiled rule_programs.py cases key off of, and let the
# existing proof engine render a verified verdict. This module intentionally has no dependency on
# scenario.py's Fact/Truth classes to avoid a circular import - it returns plain
# (factName, "true"|"false", source) triples that scenario.extract_facts wraps into real Facts.

_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "thirty five": 35, "thirty-five": 35, "thirty nine": 39, "thirty-nine": 39,
    "forty": 40, "thirty": 30,
}


def _extract_number(q: str) -> int | None:
    m = re.search(r"\b(\d+)\b", q)
    if m:
        return int(m.group(1))
    for word in sorted(_NUMBER_WORDS, key=len, reverse=True):
        if re.search(r"\b" + re.escape(word) + r"\b", q):
            return _NUMBER_WORDS[word]
    return None


def _extract_operator(q: str) -> str:
    if re.search(r"\bmore than\b", q):
        return "greater_than"
    if re.search(r"\bfewer than\b|\bless than\b", q):
        return "less_than"
    if re.search(r"\bat least\b", q):
        return "at_least"
    if re.search(r"\bat most\b|\bup to\b", q):
        return "at_most"
    return "equal"


def _requested_quantity(q: str) -> tuple[str, int] | None:
    """Parse a natural-language quantity + comparison operator from a deck question.

    "multiple" with no explicit number is treated as "more than 1" - RiftKeep 1.0.1's Deck
    Construction patch (section 13) lists it as a supported cardinality word alongside numerals.
    """
    if re.search(r"\bmultiple\b", q) and not re.search(r"\d", q):
        return ("greater_than", 1)
    n = _extract_number(q)
    if n is None:
        return None
    return (_extract_operator(q), n)


def _exceeds(qty: tuple[str, int] | None, limit: int) -> bool | None:
    """True if the requested quantity necessarily exceeds `limit`, False if it necessarily
    satisfies it, None if undetermined (caller should leave the fact unset -> UNKNOWN)."""
    if qty is None:
        return None
    op, n = qty
    if op == "greater_than":
        return n >= limit
    if op == "at_least":
        return n > limit
    if op == "equal":
        return n > limit
    if op in ("less_than", "at_most"):
        return None if n <= limit + 1 else True
    return None


def _below_minimum(qty: tuple[str, int] | None, minimum: int) -> bool | None:
    if qty is None:
        return None
    op, n = qty
    if op in ("less_than", "at_most"):
        return n <= minimum
    if op == "equal":
        return n < minimum
    if op == "at_least":
        return None if n >= minimum else True
    if op == "greater_than":
        return None if n >= minimum - 1 else True
    return None


def _not_exactly(qty: tuple[str, int] | None, exact: int) -> bool | None:
    if qty is None:
        return None
    op, n = qty
    if op == "equal":
        return n != exact
    if op in ("greater_than", "at_least") and n >= exact:
        return True
    if op in ("less_than", "at_most") and n <= exact:
        return True
    return None


# ---------------------------------------------------------------------------
# Obligation detection - mirrors proof.py's detect_obligations() regex style.
# ---------------------------------------------------------------------------

_PROXIMITY_CHARS = 40


def _near(q: str, pattern_a: str, pattern_b: str, max_distance: int = _PROXIMITY_CHARS) -> bool:
    """True if a match of pattern_a and a match of pattern_b occur within max_distance
    characters of each other anywhere in q. Co-occurrence anywhere in a long question is not
    enough on its own: an anchor word can appear incidentally (a zone-name list mentioning "Rune
    Deck", a card quoted verbatim mentioning "Champion Legend") while a common trigger word like
    "require"/"deck"/"need" shows up unrelated, far away, in a completely different clause.
    Confirmed as a real false positive before this guard existed: a question listing zone names
    including "Rune Deck" plus an unrelated closing "What does the rule require?" incorrectly
    fired rune_deck_count, and a question just describing where a Champion Legend starts the game
    incorrectly fired champion_legend_count. Requiring the two signals to actually sit near each
    other keeps genuine quantity questions ("Can I use 13 runes?", "How many Legends can my deck
    contain?") matching while rejecting incidental co-occurrence."""
    a_spans = [m.start() for m in re.finditer(pattern_a, q)]
    if not a_spans:
        return False
    b_spans = [m.start() for m in re.finditer(pattern_b, q)]
    if not b_spans:
        return False
    return any(abs(a - b) <= max_distance for a in a_spans for b in b_spans)


def detect_deck_obligations(q: str) -> list[str]:
    out: list[str] = []
    if (
        "control" not in q
        and _near(q, r"\b(?:champion )?legends?\b", r"\bplay|have|run|use|put|include|allow|need|contain|multiple|deck\b")
    ):
        out.append("champion_legend_count")
    if (
        _near(q, r"\bmain deck\b", r"\bhow many\b|\d+(?!\.)|\bthirty\b|\bforty\b|\bat least\b|\bat most\b|\bmore than\b|\bfewer than\b|\bless than\b|\bmultiple\b|\bonly\b|\bexactly\b")
        or (
            re.search(r"\bcards?\b(?!\s*[.:])", q)
            and not re.search(r"\bsignature|rune|battlefield|cop(?:y|ies)\b", q)
            # (?!\s*[.:]) excludes "cards" used as a section-label word ("...resolving Playing
            # Cards.", "Rules question about Cards:") rather than a countable noun - confirmed
            # as a real false positive source across the corpus's own question-template
            # prefixes. \d+(?!\.) excludes a numbered-list marker like "4. Pay the card's costs"
            # - a step number sitting right next to the word "card" is not a deck-size quantity,
            # also confirmed directly: a question quoting rule text with a numbered procedure
            # step next to "card's" fired main_deck_minimum via this exact adjacency.
            and _near(q, r"\bcards?\b(?!\s*[.:])", r"\b\d+(?!\.)\b|\bthirty\b|\bforty\b")
        )
    ):
        out.append("main_deck_minimum")
    if (
        re.search(r"\bcop(?:y|ies)\b", q)
        and _near(q, r"\bcop(?:y|ies)\b", r"\bcard\b|\bchosen champion\b|\bsame name\b|\bsame-named\b|\bnamed card\b")
        and not re.search(r"\bempowered|buff|temporary|trait|might\b", q)
        and "battlefield" not in q
    ):
        out.append("same_name_copy_limit")
    if "signature" in q and _near(q, r"\bsignature\b", r"\bcard|limit|champion|zone|chosen\b"):
        out.append("signature_limit")
    if re.search(r"\brunes?\b", q) and _near(q, r"\brunes?\b", r"\bhow many\b|\bneed\b|\brequire\b|\bcontain\b|\d(?!\.)"):
        out.append("rune_deck_count")
    if "battlefield" in q and _near(q, r"\bbattlefields?\b", r"\bcop(?:y|ies)\b|\bsame name\b|\bsame-named\b|\bduplicate\b|\btwo of the same\b"):
        out.append("battlefield_duplicate_limit")
    elif (
        "battlefield" in q
        and _near(q, r"\bbattlefields?\b", r"\bhow many\b|\bneed\b|\brequire\b")
        and not re.search(r"\btarget|contested|score|control|lose|losing\b", q)
    ):
        out.append("battlefield_count_requirement")
    return out


# ---------------------------------------------------------------------------
# Fact derivation - each obligation's facts are only meaningful once its obligation is
# actually detected, but deriving them unconditionally is harmless (they're simply unused
# otherwise) and keeps this module the single place deck-construction language lives.
# ---------------------------------------------------------------------------

def deck_construction_facts(q: str) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []

    def setf(name: str, value: bool, source: str) -> None:
        out.append((name, "true" if value else "false", source))

    # Champion Legend count - Rule 103.1: exactly 1.
    if re.search(r"\b(?:champion )?legends?\b", q) and "control" not in q:
        if re.search(r"\bhow many\b", q):
            setf("deck_legend_count_how_many", True, "question asks how many Champion Legends a deck may/must have")
        else:
            qty = _requested_quantity(q)
            exceeds = _exceeds(qty, 1)
            if exceeds is True:
                setf("deck_legend_count_exceeds_one", True, f"question requests {qty[0]} {qty[1]} Champion Legend(s)")
            elif exceeds is False:
                setf("deck_legend_count_exceeds_one", False, "question requests exactly 1 Champion Legend")

    # Main Deck minimum - Rule 103.2: at least 40 cards.
    if re.search(r"\bmain deck\b", q) or re.search(r"\bcards?\b", q):
        if re.search(r"\bhow many\b", q) and "main deck" in q:
            setf("deck_main_deck_how_many", True, "question asks how many cards a Main Deck needs")
        else:
            qty = _requested_quantity(q)
            below = _below_minimum(qty, 40)
            if below is True:
                setf("deck_main_deck_below_minimum", True, f"question requests {qty[0]} {qty[1]} cards")
            elif below is False:
                setf("deck_main_deck_below_minimum", False, "question requests at least 40 cards")

    # Same-named copy limit - Rule 103.2.b: up to 3 copies of the same named card.
    if re.search(r"\bcop(?:y|ies)\b", q):
        if re.search(r"\bchosen champion\b", q) and re.search(r"\bcount|toward|include|plus\b", q):
            setf("deck_copy_limit_chosen_champion_question", True, "question asks whether the Chosen Champion counts toward the same-named copy limit")
        elif re.search(r"\bhow many\b", q):
            setf("deck_copy_limit_how_many", True, "question asks how many copies of the same named card are allowed")
        else:
            qty = _requested_quantity(q)
            exceeds = _exceeds(qty, 3)
            if exceeds is True:
                setf("deck_copy_limit_exceeds_three", True, f"question requests {qty[0]} {qty[1]} copies of the same named card")
            elif exceeds is False:
                setf("deck_copy_limit_exceeds_three", False, "question requests 3 or fewer copies of the same named card")

    # Signature card limit - Rule 103.2.d: max 3 total Signature cards, matching Champion tag.
    if "signature" in q:
        if re.search(r"\bdifferent champion\b|\banother champion\b|\bfrom .* champion\b", q):
            setf("deck_signature_different_champion_question", True, "question asks whether Signature cards from a different Champion tag are allowed")
        elif re.search(r"\bchosen champion\b", q):
            setf("deck_signature_as_chosen_champion_question", True, "question asks whether a Signature card can be the Chosen Champion")
        elif re.search(r"\bhow many\b", q):
            setf("deck_signature_how_many", True, "question asks how many Signature cards a deck may contain")
        else:
            qty = _requested_quantity(q)
            exceeds = _exceeds(qty, 3)
            if exceeds is True:
                setf("deck_signature_exceeds_three", True, f"question requests {qty[0]} {qty[1]} Signature cards")
            elif exceeds is False:
                setf("deck_signature_exceeds_three", False, "question requests 3 or fewer Signature cards")

    # Rune Deck count - Rule 103.3: exactly 12 Rune Cards.
    if re.search(r"\brunes?\b", q):
        if re.search(r"\bdomain identity\b|\boutside .* domain\b", q):
            setf("deck_rune_domain_identity_question", True, "question asks whether a Rune outside the deck's Domain Identity is allowed")
        elif re.search(r"\bhow many\b", q):
            setf("deck_rune_count_how_many", True, "question asks how many Rune Cards a deck needs")
        else:
            qty = _requested_quantity(q)
            not_exact = _not_exactly(qty, 12)
            if not_exact is True:
                setf("deck_rune_count_not_twelve", True, f"question requests {qty[0]} {qty[1]} runes")
            elif not_exact is False:
                setf("deck_rune_count_not_twelve", False, "question requests exactly 12 runes")

    # Battlefield duplicate-name limit - Rule 103.4.c.
    if "battlefield" in q and re.search(r"\bcop(?:y|ies)\b|\bsame name\b|\bsame-named\b|\bduplicate\b|\btwo of the same\b", q):
        setf("deck_battlefield_duplicate_question", True, "question asks about using more than one Battlefield of the same name")

    return out
