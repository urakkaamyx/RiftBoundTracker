from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from typing import Any

from .errata import canonical_card_identity
from .scenario import CARD_NAME_STRIP_RE, detect_named_cards


_EFFECT_TAGS: list[tuple[str, re.Pattern[str]]] = [
    ("play", re.compile(r"\bplay(?:s|ed|ing)?\b", re.I)),
    ("copy", re.compile(r"\b(?:copy|copies|copied|copying)\b", re.I)),
    ("attach", re.compile(r"\battach(?:es|ed|ing)?\b|\bequip(?:s|ped|ping)?\b", re.I)),
    ("detach", re.compile(r"\bdetach(?:es|ed|ing)?\b", re.I)),
    ("replace", re.compile(r"\breplac(?:e|es|ed|ing|ement)\b|\binstead\b", re.I)),
    ("trigger", re.compile(r"\btrigger(?:s|ed|ing)?\b|\bwhen\b|\bwhenever\b", re.I)),
    ("move", re.compile(r"\bmove(?:s|d|ing)?\b", re.I)),
    ("recall", re.compile(r"\brecall(?:s|ed|ing)?\b", re.I)),
    ("return_to_hand", re.compile(r"\breturn(?:s|ed|ing)?\b[^.]{0,120}\b(?:hand|hands)\b", re.I)),
    ("banish", re.compile(r"\bbanish(?:es|ed|ing)?\b", re.I)),
    ("kill", re.compile(r"\bkill(?:s|ed|ing)?\b|\bdie(?:s|d|ing)?\b", re.I)),
    ("damage", re.compile(r"\bdamage\b|\bdeal(?:s|t|ing)?\b", re.I)),
    ("ready", re.compile(r"\b(?:ready|readies|readied|readying)\b", re.I)),
    ("exhaust", re.compile(r"\bexhaust(?:s|ed|ing)?\b|:rb_exhaust:", re.I)),
    ("stun", re.compile(r"\bstun(?:s|ned|ning)?\b", re.I)),
    ("empower", re.compile(r"\bempower(?:s|ed|ing)?\b|\bdisempower(?:s|ed|ing)?\b", re.I)),
    ("control", re.compile(r"\bcontrol(?:s|led|ling)?\b", re.I)),
    ("might", re.compile(r"\bmight\b|:rb_might:", re.I)),
    ("choose", re.compile(r"\bchoose|chooses|chosen|choice|choices\b", re.I)),
    ("counter", re.compile(r"\bcounter(?:s|ed|ing)?\b", re.I)),
    ("draw", re.compile(r"\bdraw(?:s|n|ing)?\b", re.I)),
    ("discard", re.compile(r"\bdiscard(?:s|ed|ing)?\b", re.I)),
    ("recycle", re.compile(r"\brecycl(?:e|es|ed|ing)\b", re.I)),
    ("add_resource", re.compile(r"\badd\b", re.I)),
    ("heal", re.compile(r"\bheal(?:s|ed|ing)?\b", re.I)),
]

_REFERENCE_RE = re.compile(r"\b(this|that|it|its|them|they|here|me|my|you|your|friendly|enemy|opponent(?:'s|’s)?)\b", re.I)
_TRIGGER_START = re.compile(r"^(?:\[[^\]]+\]\s*[—-]\s*)?(?:when|whenever|at the (?:start|end)|after|before)\b", re.I)
_REPLACEMENT_RE = re.compile(r"\bwould\b.*\binstead\b|\binstead\b", re.I)
_CONTINUOUS_START = re.compile(r"^(?:while|as long as|during|other\b|your\b|friendly\b|enemy\b|opponents?\b|i have\b|this has\b)", re.I)
_ACTIVATED_RE = re.compile(r"(?:^|\s)(?:[^.]{0,80}:\s+|:rb_exhaust::\s*)", re.I)

_STOP = {
    "what", "when", "does", "do", "will", "can", "could", "would", "should", "the", "a", "an", "and", "or", "if", "then", "this", "that", "with", "from", "your", "my", "their", "they", "them", "unit", "card", "spell", "ability", "play", "played", "playing", "effect", "happen", "happens", "how", "while", "have", "having", "into", "after", "before", "during", "there", "here",
}


def _hash_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _norm(text: str) -> str:
    s = (text or "").replace("’", "'").replace("‘", "'").casefold()
    s = re.sub(r"[^a-z0-9'!]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _tokens(text: str) -> set[str]:
    return {t for t in _norm(text).split() if len(t) > 2 and t not in _STOP}


def _clause_spans(text: str) -> list[tuple[int, int, str]]:
    """Conservatively split concatenated database card text without changing text."""
    if not text:
        return []
    boundary = re.compile(
        r"(?<=[.!?])(?=\[|[A-Z])"
        r"|(?<=\))(?=\[)"
        r"|(?<=\))(?=(?:When|Whenever|While|If|As|At|Other|Your|Friendly|Enemy|Opponents?|I\b|This\b))"
    )
    starts = [0] + [m.end() for m in boundary.finditer(text)]
    out: list[tuple[int, int, str]] = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        raw = text[start:end]
        left = len(raw) - len(raw.lstrip())
        right = len(raw.rstrip())
        a, b = start + left, start + right
        if a < b:
            out.append((a, b, text[a:b]))
    return out


def _ability_kind(clause: str) -> str:
    s = clause.strip()
    if _REPLACEMENT_RE.search(s):
        return "replacement"
    if _TRIGGER_START.search(s):
        return "triggered"
    if _ACTIVATED_RE.search(s):
        return "activated"
    if _CONTINUOUS_START.search(s):
        return "continuous"
    return "instruction_or_static"


def _game_actions(semantic_ir: dict[str, Any]) -> list[tuple[str, str]]:
    rows = []
    for c in semantic_ir.get("conceptCatalog", {}).get("concepts", []):
        if c.get("category") == "game_action" and c.get("name") and c.get("ruleId"):
            rows.append((str(c["name"]), str(c["ruleId"])))
    rows.sort(key=lambda x: len(x[0]), reverse=True)
    return rows


def _compile_printing(card: dict[str, Any], actions: list[tuple[str, str]]) -> dict[str, Any]:
    text = str(card.get("effectiveText") or "")
    identity = canonical_card_identity(card.get("name"))
    canonical_name = CARD_NAME_STRIP_RE.sub("", str(card.get("name") or "")).strip()
    clauses = []
    for index, (start, end, clause) in enumerate(_clause_spans(text), 1):
        action_refs = []
        low = clause.casefold()
        for name, rid in actions:
            n = name.casefold()
            if re.search(rf"(?<![a-z0-9]){re.escape(n)}(?:s|ed|ing)?(?![a-z0-9])", low):
                action_refs.append({"name": name, "ruleId": rid})
        keyword_refs = []
        for token in card.get("textMarkup") or []:
            span = token.get("span") or []
            if len(span) != 2 or span[1] <= start or span[0] >= end:
                continue
            for ref in token.get("conceptRefs") or []:
                if ref.get("category") == "keyword":
                    keyword_refs.append({"name": ref.get("name"), "ruleId": ref.get("ruleId"), "conceptId": ref.get("conceptId")})
        tags = sorted({name for name, pattern in _EFFECT_TAGS if pattern.search(clause)})
        refs = sorted({m.group(1).casefold().replace("’", "'") for m in _REFERENCE_RE.finditer(clause)})
        clauses.append({
            "clauseId": f"{card['id']}:CL{index}",
            "index": index,
            "span": [start, end],
            "text": clause,
            "textSha256": _hash_text(clause),
            "abilityKind": _ability_kind(clause),
            "effectTags": tags,
            "gameActionRefs": action_refs,
            "keywordRefs": keyword_refs,
            "unresolvedReferenceTerms": refs,
        })
    return {
        "cardId": str(card["id"]),
        "name": card.get("name"),
        "canonicalName": canonical_name,
        "identityKey": identity,
        "setId": card.get("setId"),
        "collectorCode": card.get("collectorCode"),
        "type": card.get("type"),
        "supertype": card.get("supertype"),
        "effectiveText": text,
        "effectiveTextSha256": _hash_text(text),
        "textSource": card.get("textSource"),
        "officialErrataEventIds": [x.get("entryId") for x in card.get("officialErrataTimeline") or [] if x.get("entryId")],
        "referencedConceptIds": list(card.get("referencedConceptIds") or []),
        "clauses": clauses,
    }


def _faq_answer(doc: dict[str, Any]) -> str:
    text = str(doc.get("text") or "")
    q = str(doc.get("question") or "").strip()
    if q and text.startswith(q):
        return text[len(q):].lstrip("\n ")
    return text


def compile_card_interaction_catalog(cards: dict[str, Any], semantic_ir: dict[str, Any], supplemental: dict[str, Any]) -> dict[str, Any]:
    actions = _game_actions(semantic_ir)
    printings = [_compile_printing(c, actions) for c in cards.get("cards", [])]
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in printings:
        groups[p["identityKey"]].append(p)
    identities = []
    for key, rows in sorted(groups.items()):
        identities.append({
            "identityKey": key,
            "canonicalName": rows[0]["canonicalName"],
            "printingIds": [r["cardId"] for r in rows],
            "printingCount": len(rows),
            "effectiveTextHashes": sorted({r["effectiveTextSha256"] for r in rows}),
            "distinctEffectiveTextCount": len({r["effectiveTextSha256"] for r in rows}),
        })

    faq_programs = []
    for doc in supplemental.get("documents", []):
        if not doc.get("question"):
            continue
        named = detect_named_cards(str(doc["question"]), cards)
        identities_in_question = sorted({canonical_card_identity(c.get("name")) for c in named if canonical_card_identity(c.get("name"))})
        answer = _faq_answer(doc)
        faq_programs.append({
            "programId": f"FAQI:{doc['evidenceId']}",
            "evidenceId": doc["evidenceId"],
            "sourceId": doc.get("sourceId"),
            "question": doc.get("question"),
            "questionNormalized": _norm(str(doc.get("question") or "")),
            "questionTokens": sorted(_tokens(str(doc.get("question") or ""))),
            "requiredCardIdentityKeys": identities_in_question,
            "compilerFamily": doc.get("compilerFamily"),
            "rulingRole": doc.get("rulingRole"),
            "officialAnswerText": answer,
            "officialAnswerSha256": _hash_text(answer),
            "authority": doc.get("authority"),
        })

    kinds = Counter(c["abilityKind"] for p in printings for c in p["clauses"])
    tags = Counter(tag for p in printings for c in p["clauses"] for tag in c["effectTags"])
    return {
        "schemaVersion": 1,
        "printingCount": len(printings),
        "identityCount": len(identities),
        "faqProgramCount": len(faq_programs),
        "clauseCount": sum(len(p["clauses"]) for p in printings),
        "abilityKindCounts": dict(sorted(kinds.items())),
        "effectTagCounts": dict(sorted(tags.items())),
        "policy": {
            "effectiveTextIsAuthoritativeInput": True,
            "clauseClassificationIsStructuralNotAdjudicative": True,
            "unresolvedReferencesAreNotGuessed": True,
            "faqProgramsRequireAuthorityAndIdentityMatching": True,
        },
        "printings": printings,
        "identities": identities,
        "faqPrograms": faq_programs,
    }


def match_faq_interaction(question: str, named_cards: list[dict[str, Any]], catalog: dict[str, Any]) -> dict[str, Any] | None:
    qn = _norm(question)
    qt = _tokens(question)
    named_ids = {canonical_card_identity(c.get("name")) for c in named_cards if canonical_card_identity(c.get("name"))}
    candidates = []
    for p in catalog.get("faqPrograms", []):
        required = set(p.get("requiredCardIdentityKeys") or [])
        if required and not required.issubset(named_ids):
            continue
        pn = str(p.get("questionNormalized") or "")
        pt = set(p.get("questionTokens") or [])
        exact = qn == pn
        seq = SequenceMatcher(None, qn, pn, autojunk=False).ratio() if qn and pn else 0.0
        inter = len(qt & pt)
        jaccard = inter / max(1, len(qt | pt))
        containment = inter / max(1, min(len(qt), len(pt)))
        if exact:
            score = 1.0
        else:
            score = max(seq * 0.62 + jaccard * 0.38, containment * 0.86)
        # High confidence only. A program with no explicit card identity must be nearly
        # exact because it cannot use card identity as a disambiguating anchor.
        threshold = 0.72 if required else 0.90
        if score >= threshold:
            candidates.append((score, exact, p))
    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    best = candidates[0]
    runner = candidates[1][0] if len(candidates) > 1 else 0.0
    if not best[1] and best[0] - runner < 0.08:
        return None
    p = best[2]
    return {
        "programId": p["programId"],
        "evidenceId": p["evidenceId"],
        "sourceId": p.get("sourceId"),
        "compilerFamily": p.get("compilerFamily"),
        "rulingRole": p.get("rulingRole"),
        "requiredCardIdentityKeys": list(p.get("requiredCardIdentityKeys") or []),
        "matchScore": round(best[0], 4),
        "exactQuestionMatch": bool(best[1]),
        "officialAnswerSha256": p.get("officialAnswerSha256"),
        "authority": p.get("authority"),
    }


def build_card_interaction_context(question: str, named_cards: list[dict[str, Any]], scenario_model: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    by_card = {p["cardId"]: p for p in catalog.get("printings", [])}
    identity_rows = {x["identityKey"]: x for x in catalog.get("identities", [])}
    named = []
    for c in named_cards:
        row = by_card.get(str(c.get("id")))
        if not row:
            continue
        named.append({
            "cardId": row["cardId"], "name": row["name"], "canonicalName": row["canonicalName"],
            "identityKey": row["identityKey"], "effectiveTextSha256": row["effectiveTextSha256"],
            "clauseIds": [x["clauseId"] for x in row["clauses"]],
            "effectTags": sorted({t for x in row["clauses"] for t in x["effectTags"]}),
        })
    object_bindings = []
    for obj in scenario_model.get("objects", []):
        ids = list(obj.get("printingIds") or [])
        matches = [by_card[x] for x in ids if x in by_card]
        identity = canonical_card_identity(obj.get("canonicalName")) if obj.get("canonicalName") else None
        if not matches and identity and identity in identity_rows:
            ids = list(identity_rows[identity].get("printingIds") or [])
            matches = [by_card[x] for x in ids if x in by_card]
        if not matches:
            continue
        object_bindings.append({
            "objectId": obj.get("objectId"),
            "identityKey": matches[0]["identityKey"],
            "printingIds": [x["cardId"] for x in matches],
            "effectiveTextHashes": sorted({x["effectiveTextSha256"] for x in matches}),
            "clauseIds": sorted({c["clauseId"] for x in matches for c in x["clauses"]}),
            "bindingSource": "scenario_card_identity",
        })
    faq_match = match_faq_interaction(question, named_cards, catalog)
    return {
        "schemaVersion": 1,
        "namedCards": named,
        "scenarioObjectBindings": object_bindings,
        "officialFaqInteractionMatch": faq_match,
        "appliesGameRules": False,
        "changesVerdict": False,
        "policy": "M13 structural context only until a separately regression-proven interaction executor is invoked.",
    }
