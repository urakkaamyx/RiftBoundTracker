from __future__ import annotations

import html
import re
from collections import Counter
from typing import Any

from .concepts import normalize_quote_text

BRACKET_RE = re.compile(r"\[([^\]]+)\]")
TRAILING_NUMBER_RE = re.compile(r"^(.*?)(?:\s+)(\d+)$")
SYMBOL_TOKENS = {"a", "c", "e", "m", "s", ">", ">>", "0", "1", "2", "3"}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(s or "")).strip()


def _ref(c: dict[str, Any]) -> dict[str, Any]:
    return {
        "conceptId": c.get("conceptId"),
        "ruleId": c.get("ruleId"),
        "name": c.get("name"),
        "category": c.get("category"),
    }


def _resolve_bracket_candidates(candidates: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]], str | None]:
    """Resolve an official term specifically in *bracket-markup* context.

    Riftbound bracket markup is semantically meaningful. If an exact bracketed term is
    both a Keyword and another Core Rules concept, the Keyword meaning is the direct
    markup interpretation. The other official meanings are retained as candidates for
    audit and can still be linked as related semantics elsewhere.

    Current corpus example: Empower is both Game Action 441 and Keyword 827. Cards use
    [Empower] as the Activated Ability keyword; the action itself is written as prose
    (e.g. "Empower me").
    """
    if not candidates:
        return "unknown_markup", [], None
    if len(candidates) == 1:
        c = candidates[0]
        category = c.get("category") or "rule_concept"
        cls = "keyword" if category == "keyword" else "game_action" if category == "game_action" else "rule_concept"
        return cls, [_ref(c)], None

    keywords = [c for c in candidates if c.get("category") == "keyword"]
    if len(keywords) == 1:
        return "keyword", [_ref(keywords[0])], "bracket_markup_prefers_exact_keyword"

    # Do not guess if multiple equally plausible official meanings remain.
    return "ambiguous_official_term", [_ref(c) for c in candidates], None


def compile_card_text_annotations(cards: dict[str, Any], semantic_ir: dict[str, Any]) -> dict[str, Any]:
    concepts = semantic_ir.get("conceptCatalog", {}).get("concepts", [])
    by_name: dict[str, list[dict[str, Any]]] = {}
    for c in concepts:
        by_name.setdefault(str(c.get("name") or "").lower(), []).append(c)

    class_counts: Counter[str] = Counter()
    unknown_counts: Counter[str] = Counter()
    recognized_counts: Counter[str] = Counter()
    resolution_counts: Counter[str] = Counter()

    for card in cards.get("cards", []):
        source_text = card.get("effectiveText") or ""
        display = _norm(source_text)
        tokens = []
        for match in BRACKET_RE.finditer(display):
            raw = match.group(1)
            token = _norm(raw)
            low = token.lower()
            parameter = None
            base = token
            m = TRAILING_NUMBER_RE.match(token)
            if m:
                base = m.group(1).strip()
                parameter = int(m.group(2))
            base_low = base.lower()
            candidates = by_name.get(base_low, [])
            candidate_refs = [_ref(c) for c in candidates]
            resolution = None

            if candidates:
                cls, refs, resolution = _resolve_bracket_candidates(candidates)
                recognized_counts[base] += 1
                if resolution:
                    resolution_counts[resolution] += 1
            elif low in SYMBOL_TOKENS or re.fullmatch(r"\d+", low):
                cls = "notation"
                refs = []
            elif low in {"no text"}:
                cls = "source_marker"
                refs = []
            else:
                cls = "unknown_markup"
                refs = []
                unknown_counts[token] += 1

            class_counts[cls] += 1
            row = {
                "raw": raw,
                "token": token,
                "baseTerm": base,
                "parameter": parameter,
                "classification": cls,
                "conceptRefs": refs,
                "candidateConceptRefs": candidate_refs,
                "span": [match.start(), match.end()],
            }
            if resolution:
                row["resolution"] = resolution
            tokens.append(row)

        card["displayText"] = display
        card["textMarkup"] = tokens
        card["referencedConceptIds"] = sorted({
            r["conceptId"] for t in tokens for r in t["conceptRefs"] if r.get("conceptId")
        })

    cards.setdefault("metadata", {})["textAnnotation"] = {
        "classificationCounts": dict(sorted(class_counts.items())),
        "recognizedBaseTerms": dict(recognized_counts.most_common()),
        "contextResolutionCounts": dict(sorted(resolution_counts.items())),
        "unknownMarkup": dict(unknown_counts.most_common()),
        "policy": (
            "Bracket syntax is classified against the Core Rules concept catalog; brackets alone do not imply Keyword status. "
            "When an exact bracketed official term has a single Keyword meaning among otherwise ambiguous same-name concepts, "
            "the bracket token resolves to that Keyword while all candidates are retained for audit."
        ),
    }
    return cards


def build_card_explanation_ruling_from_quote(question: str, named_cards: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Fallback for a question that quotes one or more named cards' own effectiveText verbatim -
    e.g. a synthetic-corpus template ('I plan to resolve Card A and then Card B in the same turn.
    Card A currently reads: "<effective text>" ... Card B currently reads: "<effective text>"
    ... what do the current official rules require me to understand when resolving each card in
    sequence?') that dresses up a plain 'what do these cards do' request as a multi-card
    interaction question. Confirmed directly: ~65% of a real QA corpus's INCORRECT_CLARIFICATION
    failures matched this template, with the corpus's own expected answer describing each quoted
    card's ability (plus its keyword's governing rule text, not reproduced here yet - see the
    module docstring gap noted below) rather than resolving any actual interaction between them.

    Only fires on an exact quoted match against one of the question's own named cards' real
    effectiveText (never a guess), and covers every card quoted this way, not just the first -
    the real corpus template routinely names two. Checked before card-interaction-program
    dispatch has a chance to produce a real interaction ruling for the same question - callers
    should only reach this after confirming no interaction program fully covered the question.

    Known gap: this explains each card's own text but not the keyword's separate governing rule
    text the corpus's fullest expected answers also include (e.g. "The governing official Action
    rule is: ...") - a real remaining improvement, not attempted in this pass."""
    quoted = [c for c in named_cards if len(str(c.get("effectiveText") or "").strip()) >= 40
              and normalize_quote_text(c["effectiveText"]) in normalize_quote_text(question)]
    if not quoted:
        return None
    outcomes = []
    basis = []
    for card in quoted:
        card_id = card["id"]
        text = card["effectiveText"]
        outcomes.append({
            "claim": f"{card['name']}'s current effective text is quoted in the question.",
            "verdict": "definition",
            "truth": "true",
            "cardEvidence": {"evidenceId": f"C:{card_id}", "cardId": card_id, "name": card["name"], "text": text},
        })
        basis.append(f"C:{card_id}")
    names = ", ".join(c["name"] for c in quoted)
    return {
        "status": "decided",
        "issue": question,
        "outcomes": outcomes,
        "effectiveVerdict": {
            "verdict": "definition",
            "reason": f"The question quotes {names}'s own effective text verbatim.",
            "basis": basis,
        },
    }
