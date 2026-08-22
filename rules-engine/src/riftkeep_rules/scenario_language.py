from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .errata import canonical_card_identity
from .scenario import CARD_NAME_STRIP_RE


_OBJECT_KIND = {
    "unit": "Unit", "units": "Unit",
    "gear": "Gear",
    "battlefield": "Battlefield", "battlefields": "Battlefield",
    "spell": "Spell", "spells": "Spell",
    "card": "Card", "cards": "Card",
    "legend": "Legend", "legends": "Legend",
    "base": "Base", "bases": "Base",
}

_ENTITY_RE = re.compile(r"\b(units?|gear|battlefields?|spells?|cards?|legends?|bases?)\b", re.I)
_REFERENCE_RE = re.compile(r"\b(the other unit|that unit|this unit|that card|this card|that spell|this spell|that gear|this gear|that battlefield|this battlefield|it|they|them)\b", re.I)
_PLAYER_RE = re.compile(r"\b(player\s+[1-9]\d*|my opponent|the opponent|an opponent|opponent)\b", re.I)

_EVENT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("gain_control", re.compile(r"\bgain(?:s|ed|ing)? control\b", re.I)),
    ("lose_control", re.compile(r"\blose(?:s|lost|losing)? control\b", re.I)),
    ("deal_damage", re.compile(r"\bdeal(?:s|t|ing)? damage\b", re.I)),
    ("finalize", re.compile(r"\bfinaliz(?:e|es|ed|ing)\b", re.I)),
    ("resolve", re.compile(r"\bresolv(?:e|es|ed|ing)\b", re.I)),
    ("counter", re.compile(r"\bcounter(?:s|ed|ing)?\b", re.I)),
    ("attach", re.compile(r"\battach(?:es|ed|ing)?\b", re.I)),
    ("detach", re.compile(r"\bdetach(?:es|ed|ing)?\b", re.I)),
    ("exhaust", re.compile(r"\bexhaust(?:s|ed|ing)?\b", re.I)),
    ("ready", re.compile(r"\b(?:ready|readies|readied|readying)\b", re.I)),
    ("stun", re.compile(r"\b(?:stun|stuns|stunning)\b|\bstunned\b(?!\s+(?:unit|gear|card|spell|battlefield|legend)\b)", re.I)),
    ("recall", re.compile(r"\brecall(?:s|ed|ing)?\b", re.I)),
    ("recycle", re.compile(r"\brecycl(?:e|es|ed|ing)\b", re.I)),
    ("banish", re.compile(r"\bbanish(?:es|ed|ing)?\b", re.I)),
    ("replace", re.compile(r"\breplac(?:e|es|ed|ing)\b", re.I)),
    ("copy", re.compile(r"\bcopy|copies|copied|copying\b", re.I)),
    ("play", re.compile(r"\bplay(?:s|ed|ing)?\b", re.I)),
    ("attack", re.compile(r"\battack(?:s|ed|ing)?\b", re.I)),
    ("defend", re.compile(r"\bdefend(?:s|ed|ing)?\b", re.I)),
    ("move", re.compile(r"\bmove(?:s|d|ing)?\b", re.I)),
    ("die", re.compile(r"\bdie|dies|died|dying\b", re.I)),
    ("kill", re.compile(r"\bkill(?:s|ed|ing)?\b", re.I)),
    ("destroy", re.compile(r"\bdestroy(?:s|ed|ing)?\b", re.I)),
    ("trigger", re.compile(r"\btrigger(?:s|ed|ing)?\b", re.I)),
    ("heal", re.compile(r"\bheal(?:s|ed|ing)?\b", re.I)),
    ("hide", re.compile(r"\b(?:hide|hides|hid|hiding)\b", re.I)),
    ("draw", re.compile(r"\bdraw(?:s|n|ing)?\b", re.I)),
    ("discard", re.compile(r"\bdiscard(?:s|ed|ing)?\b", re.I)),
]


_CARD_CANDIDATE_CACHE: dict[int, list[tuple[str, list[dict[str, Any]], str, re.Pattern[str]]]] = {}


def _card_name_candidates(cards: dict[str, Any]) -> list[tuple[str, list[dict[str, Any]], str, re.Pattern[str]]]:
    key = id(cards)
    cached = _CARD_CANDIDATE_CACHE.get(key)
    if cached is not None:
        return cached
    groups: dict[str, list[dict[str, Any]]] = {}
    for c in cards.get("cards", []):
        identity = canonical_card_identity(c.get("name"))
        if identity:
            groups.setdefault(identity, []).append(c)
    rows: list[tuple[str, list[dict[str, Any]], str, re.Pattern[str]]] = []
    for identity, printings in groups.items():
        canonical_name = CARD_NAME_STRIP_RE.sub("", str(printings[0].get("name") or "")).strip()
        rows.append((identity, printings, canonical_name, _name_pattern(canonical_name)))
    rows.sort(key=lambda row: len(row[2]), reverse=True)
    _CARD_CANDIDATE_CACHE[key] = rows
    return rows


@dataclass
class _Span:
    start: int
    end: int

    def overlaps(self, other: "_Span") -> bool:
        return self.start < other.end and other.start < self.end


def _name_pattern(name: str) -> re.Pattern[str]:
    base = CARD_NAME_STRIP_RE.sub("", name or "").strip()
    words = re.findall(r"[A-Za-z0-9']+", base)
    if not words:
        return re.compile(r"(?!x)x")
    # Allow punctuation/spacing differences such as "Gangplank Naval" vs
    # "Gangplank, Naval" while still requiring all literal name words in order.
    return re.compile(r"(?<![A-Za-z0-9'])" + r"[\s,\-–—]+".join(re.escape(w) for w in words) + r"(?:['’]s)?(?![A-Za-z0-9'])", re.I)


def _entity_label(e: dict[str, Any]) -> str:
    if e.get("canonicalName"):
        return str(e["canonicalName"])
    return str(e.get("surface") or e.get("kind") or e.get("entityId"))


def _player_id(actor: str) -> str:
    a = " ".join(actor.casefold().split())
    if a in {"i", "me", "my", "myself"}:
        return "P_SELF"
    if a in {"you", "your"}:
        return "P_ADDRESSEE"
    if "opponent" in a:
        return "P_OPPONENT_1"
    m = re.search(r"player\s+(\d+)", a)
    return f"P_PLAYER_{m.group(1)}" if m else "P_UNKNOWN"


def _ensure_player(players: dict[str, dict[str, Any]], pid: str, surface: str, role: str | None = None) -> None:
    if pid not in players:
        players[pid] = {"playerId": pid, "mentions": [], "role": role or "explicit_player"}
    if surface and surface not in players[pid]["mentions"]:
        players[pid]["mentions"].append(surface)


def _possessive_before(text: str, start: int) -> tuple[str | None, str | None]:
    left = text[max(0, start - 28):start]
    patterns = [
        (r"\bmy\s+$", "P_SELF"),
        (r"\byour\s+$", "P_ADDRESSEE"),
        (r"\b(?:my\s+)?opponent(?:'s|’s)\s+$", "P_OPPONENT_1"),
        (r"\bplayer\s+(\d+)(?:'s|’s)\s+$", None),
        (r"\btheir\s+$", "P_UNKNOWN"),
    ]
    for pat, pid in patterns:
        m = re.search(pat, left, re.I)
        if m:
            if pid is None:
                pid = f"P_PLAYER_{m.group(1)}"
            return pid, m.group(0).strip()
    return None, None


def _reference_determiner_before(text: str, start: int) -> bool:
    return bool(re.search(r"\b(?:that|this|the other)\s+$", text[max(0, start - 14):start], re.I))


def _clause_boundaries(text: str) -> list[int]:
    bounds = [0]
    for m in re.finditer(r"[?.!;,]|\b(?:then|after|before|while)\b", text, re.I):
        bounds.append(m.end())
    bounds.append(len(text) + 1)
    return sorted(set(bounds))


def _clause_index(pos: int, bounds: list[int]) -> int:
    idx = 0
    for i, b in enumerate(bounds):
        if b <= pos:
            idx = i
        else:
            break
    return idx


def _nearest_entity(entities: list[dict[str, Any]], pos: int, *, before: bool, kind: str | None = None) -> dict[str, Any] | None:
    candidates = [e for e in entities if (kind is None or e.get("kind") == kind)]
    if before:
        candidates = [e for e in candidates if int(e.get("end", 0)) <= pos]
        candidates.sort(key=lambda e: int(e.get("end", 0)), reverse=True)
    else:
        candidates = [e for e in candidates if int(e.get("start", 0)) >= pos]
        candidates.sort(key=lambda e: int(e.get("start", 0)))
    return candidates[0] if candidates else None


def _extract_named_card_entities(text: str, cards: dict[str, Any]) -> tuple[list[dict[str, Any]], list[_Span]]:
    candidates = _card_name_candidates(cards)
    entities: list[dict[str, Any]] = []
    occupied: list[_Span] = []
    seen_mentions: set[tuple[str, int, int]] = set()
    for identity, printings, canonical_name, pat in candidates:
        for m in pat.finditer(text):
            span = _Span(m.start(), m.end())
            if any(span.overlaps(o) for o in occupied):
                continue
            key = (identity, m.start(), m.end())
            if key in seen_mentions:
                continue
            seen_mentions.add(key)
            occupied.append(span)
            types = sorted({str(c.get("type") or "Card") for c in printings})
            entities.append({
                "entityId": "",  # assigned after sorting with generic entities
                "kind": types[0] if len(types) == 1 else "Card",
                "surface": m.group(0),
                "start": m.start(),
                "end": m.end(),
                "source": "named_card",
                "canonicalCardIdentity": identity,
                "canonicalName": canonical_name,
                "printingIds": sorted(str(c.get("id")) for c in printings if c.get("id")),
                "printingNames": sorted({str(c.get("name")) for c in printings if c.get("name")}),
            })
    return entities, occupied


def _extract_entities(text: str, cards: dict[str, Any]) -> list[dict[str, Any]]:
    entities, occupied = _extract_named_card_entities(text, cards)
    for m in _ENTITY_RE.finditer(text):
        span = _Span(m.start(), m.end())
        if any(span.overlaps(o) for o in occupied):
            continue
        if _reference_determiner_before(text, m.start()):
            continue
        kind = _OBJECT_KIND[m.group(1).casefold()]
        possessor, poss_surface = _possessive_before(text, m.start())
        entities.append({
            "entityId": "",
            "kind": kind,
            "surface": m.group(0),
            "start": m.start(),
            "end": m.end(),
            "source": "generic_noun",
            "number": "plural" if m.group(1).casefold().endswith("s") and m.group(1).casefold() not in {"spell", "base"} else "singular",
            "discoursePossessor": possessor,
            "possessiveSurface": poss_surface,
        })
    entities.sort(key=lambda e: (int(e["start"]), -(int(e["end"]) - int(e["start"]))))
    for i, e in enumerate(entities, 1):
        e["entityId"] = f"E{i}"
    return entities


def _extract_players(text: str, entities: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    players: dict[str, dict[str, Any]] = {}
    if re.search(r"\b(?:i|me|my|mine|myself)\b", text, re.I):
        _ensure_player(players, "P_SELF", "I/my", "speaker")
    if re.search(r"\b(?:you|your|yours)\b", text, re.I):
        _ensure_player(players, "P_ADDRESSEE", "you/your", "addressee")
    for m in _PLAYER_RE.finditer(text):
        pid = _player_id(m.group(0))
        _ensure_player(players, pid, m.group(0), "opponent" if "opponent" in m.group(0).casefold() else "named_player")
    for e in entities:
        pid = e.get("discoursePossessor")
        if pid:
            _ensure_player(players, str(pid), str(e.get("possessiveSurface") or pid), "discourse_reference")
    return players


def _extract_relations(text: str, entities: list[dict[str, Any]], players: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    relations: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def add(kind: str, subject: str, obj: str, basis: str, confidence: str = "explicit") -> None:
        key = (kind, subject, obj)
        if key in seen:
            return
        seen.add(key)
        relations.append({"type": kind, "subjectId": subject, "objectId": obj, "basis": basis, "confidence": confidence})

    # English possessives establish discourse reference only. They are deliberately
    # not game-rule control/ownership relations.
    for e in entities:
        if e.get("discoursePossessor"):
            add("discourse_possession", str(e["discoursePossessor"]), str(e["entityId"]), str(e.get("possessiveSurface") or "possessive"), "surface_only")

    actor_pat = r"(?P<actor>I|you|my opponent|the opponent|an opponent|opponent|player\s+[1-9]\d*)"
    noun_pat = r"(?P<noun>unit|gear|battlefield|spell|card|legend|base)"
    # Allow explicit state/adjective words between the article and object noun:
    # "Player 2 controls a stunned unit" / "I own an empowered unit".
    desc = r"(?:[A-Za-z][A-Za-z'’-]*\s+){0,4}?"

    # "I control a unit" / "Player 2 owns that spell".
    for m in re.finditer(actor_pat + r"\s+(?P<verb>controls|control|owns|own)\s+(?:a|an|the|that|this|my|your)?\s*" + desc + noun_pat, text, re.I):
        pid = _player_id(m.group("actor")); _ensure_player(players, pid, m.group("actor"))
        kind = _OBJECT_KIND[m.group("noun").casefold()]
        ent = _nearest_entity(entities, m.start("noun"), before=False, kind=kind) or _nearest_entity(entities, m.start("noun"), before=True, kind=kind)
        if ent:
            add("explicit_control" if m.group("verb").casefold().startswith("control") else "explicit_ownership", pid, ent["entityId"], m.group(0))

    # Explicit actor + verb followed by a named card. The card database supplies the
    # object's kind, so the sentence need not say "unit"/"gear" after the verb.
    actor_verb = re.compile(actor_pat + r"\s+(?P<verb>controls|control|owns|own)\b", re.I)
    for m in actor_verb.finditer(text):
        pid = _player_id(m.group("actor")); _ensure_player(players, pid, m.group("actor"))
        after = [e for e in entities if int(e.get("start", 0)) >= m.end() and int(e.get("start", 0)) - m.end() <= 50]
        after.sort(key=lambda e: int(e.get("start", 0)))
        if after:
            ent = after[0]
            between = text[m.end():int(ent.get("start", 0))]
            if not re.search(r"[.;?!]", between):
                add("explicit_control" if m.group("verb").casefold().startswith("control") else "explicit_ownership", pid, ent["entityId"], text[m.start():int(ent.get("end", 0))])

    # "the battlefield I control" / "a unit Player 2 owns".
    for m in re.finditer(noun_pat + r"\s+" + actor_pat + r"\s+(?P<verb>controls|control|owns|own)", text, re.I):
        pid = _player_id(m.group("actor")); _ensure_player(players, pid, m.group("actor"))
        kind = _OBJECT_KIND[m.group("noun").casefold()]
        ent = _nearest_entity(entities, m.start("noun"), before=True, kind=kind) or _nearest_entity(entities, m.start("noun"), before=False, kind=kind)
        if ent:
            add("explicit_control" if m.group("verb").casefold().startswith("control") else "explicit_ownership", pid, ent["entityId"], m.group(0))

    # "unit controlled/owned by my opponent".
    for m in re.finditer(noun_pat + r"\s+(?:is\s+)?(?P<verb>controlled|owned)\s+by\s+" + actor_pat, text, re.I):
        pid = _player_id(m.group("actor")); _ensure_player(players, pid, m.group("actor"))
        kind = _OBJECT_KIND[m.group("noun").casefold()]
        ent = _nearest_entity(entities, m.start("noun"), before=True, kind=kind) or _nearest_entity(entities, m.start("noun"), before=False, kind=kind)
        if ent:
            add("explicit_control" if m.group("verb").casefold() == "controlled" else "explicit_ownership", pid, ent["entityId"], m.group(0))

    # Coordinated same-subject verb: "Player 2 controls a stunned unit and owns a card".
    # This is explicit grammatical continuation, not an inferred game-state relation.
    for m in re.finditer(r"\band\s+(?P<verb>controls|control|owns|own)\s+(?:a|an|the|that|this)?\s*" + desc + noun_pat, text, re.I):
        left = text[max(0, m.start() - 120):m.start()]
        actors = list(re.finditer(r"\b(I|you|my opponent|the opponent|an opponent|opponent|player\s+[1-9]\d*)\b", left, re.I))
        if not actors:
            continue
        actor_surface = actors[-1].group(0)
        pid = _player_id(actor_surface); _ensure_player(players, pid, actor_surface)
        kind = _OBJECT_KIND[m.group("noun").casefold()]
        ent = _nearest_entity(entities, m.start("noun"), before=False, kind=kind) or _nearest_entity(entities, m.start("noun"), before=True, kind=kind)
        if ent:
            add("explicit_control" if m.group("verb").casefold().startswith("control") else "explicit_ownership", pid, ent["entityId"], m.group(0))
    return relations

def _reference_kind(surface: str) -> str | None:
    s = surface.casefold()
    for noun, kind in _OBJECT_KIND.items():
        if re.search(rf"\b{re.escape(noun)}\b", s):
            return kind
    return None


def _contextual_reference_kind(text: str, end: int) -> tuple[str | None, str | None]:
    """Return a type constraint only for vocabulary with an exclusive game-object domain.

    This is not nearest-noun guessing.  For example, Contested is a Battlefield status,
    so in "is it Contested?" a prior Unit is not a compatible antecedent at all.
    Keep this table deliberately small and auditable.
    """
    right = text[end:end + 48]
    if re.match(r"\s+(?:is\s+|becomes?\s+|be\s+)?contested\b", right, re.I):
        return "Battlefield", "Contested is a Battlefield status"
    return None, None


def _extract_references(text: str, entities: list[dict[str, Any]], players: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    refs: list[dict[str, Any]] = []
    clarifications: list[dict[str, Any]] = []
    bounds = _clause_boundaries(text)
    for i, m in enumerate(_REFERENCE_RE.finditer(text), 1):
        surface = m.group(0)
        kind = _reference_kind(surface)
        contextual_kind, contextual_basis = _contextual_reference_kind(text, m.end())
        if kind is None and contextual_kind is not None:
            kind = contextual_kind
        current_clause = _clause_index(m.start(), bounds)
        preceding = [e for e in entities if int(e.get("end", 0)) <= m.start() and (kind is None or e.get("kind") == kind)]
        # Prefer the current/previous discourse clause, but never pick the nearest noun
        # when multiple candidates remain valid.
        local = [e for e in preceding if current_clause - _clause_index(int(e.get("start", 0)), bounds) <= 2]
        candidates = local or preceding
        if surface.casefold() in {"they", "them"}:
            player_candidates = [p for p in players.values() if p.get("playerId") not in {"P_SELF", "P_ADDRESSEE"}]
            if len(player_candidates) == 1:
                refs.append({"referenceId": f"REF{i}", "surface": surface, "start": m.start(), "end": m.end(), "status": "resolved", "resolvedPlayerId": player_candidates[0]["playerId"], "candidateEntityIds": [], "basis": "single explicit third-party player antecedent"})
                continue
        candidate_ids = [e["entityId"] for e in candidates]
        if len(candidate_ids) == 1:
            refs.append({"referenceId": f"REF{i}", "surface": surface, "start": m.start(), "end": m.end(), "status": "resolved", "resolvedEntityId": candidate_ids[0], "candidateEntityIds": candidate_ids, "basis": contextual_basis or "single compatible prior entity"})
        elif len(candidate_ids) > 1:
            row = {"referenceId": f"REF{i}", "surface": surface, "start": m.start(), "end": m.end(), "status": "ambiguous", "candidateEntityIds": candidate_ids, "basis": "multiple compatible prior entities; nearest-noun binding intentionally refused"}
            refs.append(row)
            labels = [_entity_label(e) for e in candidates]
            clarifications.append({"kind": "reference", "referenceId": row["referenceId"], "question": f"When you say '{surface}', which object do you mean: " + ", ".join(labels) + "?", "candidateEntityIds": candidate_ids, "whyNeeded": "Multiple prior objects are compatible with this reference."})
        else:
            row = {"referenceId": f"REF{i}", "surface": surface, "start": m.start(), "end": m.end(), "status": "unresolved", "candidateEntityIds": [], "basis": "no compatible prior entity"}
            refs.append(row)
            clarifications.append({"kind": "reference", "referenceId": row["referenceId"], "question": f"What does '{surface}' refer to here?", "candidateEntityIds": [], "whyNeeded": "No compatible antecedent was stated."})
    return refs, clarifications


def _extract_events(text: str, entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    raw: list[tuple[int, int, str, str]] = []
    occupied: list[_Span] = []
    for event_type, pat in _EVENT_PATTERNS:
        for m in pat.finditer(text):
            span = _Span(m.start(), m.end())
            if any(span.overlaps(o) for o in occupied):
                continue
            occupied.append(span)
            raw.append((m.start(), m.end(), event_type, m.group(0)))
    raw.sort()
    bounds = _clause_boundaries(text)
    events: list[dict[str, Any]] = []
    for i, (start, end, etype, surface) in enumerate(raw, 1):
        ci = _clause_index(start, bounds)
        refs = [e["entityId"] for e in entities if _clause_index(int(e.get("start", 0)), bounds) == ci]
        events.append({"eventId": f"EV{i}", "type": etype, "surface": surface, "start": start, "end": end, "clauseIndex": ci, "entityIds": refs, "ordering": "unstated"})
    return events


def _event_before(events: list[dict[str, Any]], pos: int) -> dict[str, Any] | None:
    rows = [e for e in events if int(e["end"]) <= pos]
    return max(rows, key=lambda e: int(e["end"])) if rows else None


def _event_after(events: list[dict[str, Any]], pos: int) -> dict[str, Any] | None:
    rows = [e for e in events if int(e["start"]) >= pos]
    return min(rows, key=lambda e: int(e["start"])) if rows else None


def _extract_temporal_relations(text: str, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def add(kind: str, a: dict[str, Any] | None, b: dict[str, Any] | None, basis: str) -> None:
        if not a or not b or a["eventId"] == b["eventId"]:
            return
        key = (kind, a["eventId"], b["eventId"])
        if key in seen:
            return
        seen.add(key)
        out.append({"type": kind, "firstEventId": a["eventId"], "secondEventId": b["eventId"], "basis": basis, "confidence": "explicit"})
        if kind == "before":
            a["ordering"] = "explicit"
            b["ordering"] = "explicit"

    for m in re.finditer(r"\bthen\b", text, re.I):
        add("before", _event_before(events, m.start()), _event_after(events, m.end()), m.group(0))

    for connector in ("after", "before", "while"):
        for m in re.finditer(rf"\b{connector}\b", text, re.I):
            prev = _event_before(events, m.start())
            nxt = _event_after(events, m.end())
            comma = text.find(",", m.end())
            second = _event_after(events, comma + 1) if comma >= 0 else None
            # Prefix form: "After X, Y" / "Before X, Y" / "While X, Y".
            prefix = not prev or text.rfind(",", 0, m.start()) >= (prev["end"] if prev else -1)
            if prefix and nxt and second and int(nxt["start"]) < comma:
                if connector == "after":
                    add("before", nxt, second, text[m.start():comma + 1])
                elif connector == "before":
                    add("before", second, nxt, text[m.start():comma + 1])
                else:
                    add("overlaps", nxt, second, text[m.start():comma + 1])
                continue
            # Infix form: "X after Y" means Y before X; "X before Y" means X before Y.
            if connector == "after":
                add("before", nxt, prev, m.group(0))
            elif connector == "before":
                add("before", prev, nxt, m.group(0))
            else:
                add("overlaps", prev, nxt, m.group(0))
    return out


def analyze_scenario_language(question: str, cards: dict[str, Any]) -> dict[str, Any]:
    text = question or ""
    entities = _extract_entities(text, cards)
    players = _extract_players(text, entities)
    relations = _extract_relations(text, entities, players)
    references, clarifications = _extract_references(text, entities, players)
    events = _extract_events(text, entities)
    temporal = _extract_temporal_relations(text, events)
    unresolved = [r for r in references if r.get("status") in {"ambiguous", "unresolved"}]
    return {
        "schemaVersion": 1,
        "originalText": text,
        "players": list(players.values()),
        "entities": entities,
        "relations": relations,
        "references": references,
        "unresolvedReferences": unresolved,
        "events": events,
        "temporalRelations": temporal,
        # Critical invariant: this layer records only explicit language. It does not
        # fill gaps with default game-state assumptions.
        "assumptions": [],
        "clarifyingQuestions": clarifications,
        "policy": {
            "englishPossessionImpliesGameControl": False,
            "englishPossessionImpliesGameOwnership": False,
            "ambiguousReferencesBindToNearestNoun": False,
            "unstatedTemporalOrderIsInferred": False,
        },
    }
