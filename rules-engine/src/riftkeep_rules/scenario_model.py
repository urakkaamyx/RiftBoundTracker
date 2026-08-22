from __future__ import annotations

import re
from typing import Any

from .scenario_language import analyze_scenario_language


_ZONE_PATTERNS: list[tuple[str, str, bool, re.Pattern[str]]] = [
    ("MainDeckZone", "Non-Board", True, re.compile(r"\b(?:main\s+deck(?:\s+zone)?|main deck)\b", re.I)),
    ("RuneDeckZone", "Non-Board", True, re.compile(r"\brune\s+deck(?:\s+zone)?\b", re.I)),
    ("ChampionZone", "Non-Board", True, re.compile(r"\bchampion\s+zone\b", re.I)),
    ("LegendZone", "Board", True, re.compile(r"\blegend\s+zone\b", re.I)),
    ("FacedownZone", "Board", True, re.compile(r"\bfacedown\s+zone\b", re.I)),
    ("Banishment", "Non-Board", True, re.compile(r"\bbanishment\b", re.I)),
    ("Trash", "Non-Board", True, re.compile(r"\btrash(?:es)?\b", re.I)),
    ("Hand", "Non-Board", True, re.compile(r"\bhand\b", re.I)),
    ("Chain", "Non-Board", False, re.compile(r"\b(?:the\s+)?chain\b", re.I)),
    ("Base", "Board", True, re.compile(r"\bbases?\b", re.I)),
    ("Battlefield", "Board", False, re.compile(r"\bbattlefields?\b", re.I)),
]

_STATE_WORDS: dict[str, tuple[str, ...]] = {
    "Ready": ("ready",),
    "Exhausted": ("exhausted",),
    "Stunned": ("stunned",),
    "Hidden": ("hidden",),
    "Empowered": ("empowered",),
    "Contested": ("contested",),
    "Temporary": ("temporary",),
    "Attacker": ("attacker",),
    "Defender": ("defender",),
}


def _span(start: int, end: int, text_kind: str = "interpreted") -> dict[str, Any]:
    return {"textKind": text_kind, "start": int(start), "end": int(end)}


def _possessor_before(text: str, start: int, players: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    left = text[max(0, start - 34):start]
    patterns = [
        (r"\bmy\s+$", "P_SELF"),
        (r"\byour\s+$", "P_ADDRESSEE"),
        (r"\b(?:my\s+)?opponent(?:'s|’s)\s+$", "P_OPPONENT_1"),
        (r"\bplayer\s+(\d+)(?:'s|’s)\s+$", None),
    ]
    for pat, pid in patterns:
        m = re.search(pat, left, re.I)
        if m:
            if pid is None:
                pid = f"P_PLAYER_{m.group(1)}"
            return pid, m.group(0).strip()
    # "their" is resolved only if exactly one explicit third-party player exists.
    m = re.search(r"\btheir\s+$", left, re.I)
    if m:
        third = [p["playerId"] for p in players if p.get("playerId") not in {"P_SELF", "P_ADDRESSEE", "P_UNKNOWN"}]
        if len(third) == 1:
            return third[0], m.group(0).strip()
        return "P_UNKNOWN", m.group(0).strip()
    return None, None


def _overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _extract_zones(text: str, players: list[dict[str, Any]], objects: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    zones: list[dict[str, Any]] = []
    locations: list[dict[str, Any]] = []
    unknowns: list[dict[str, Any]] = []
    occupied: list[tuple[int, int]] = []
    # Longest textual matches first so "main deck" is not fragmented by later patterns.
    candidates: list[tuple[int, int, str, str, bool, str]] = []
    for zone_type, group, player_relative, pat in _ZONE_PATTERNS:
        for m in pat.finditer(text):
            candidates.append((m.start(), m.end(), zone_type, group, player_relative, m.group(0)))
    candidates.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    for start, end, zone_type, group, player_relative, surface in candidates:
        if any(_overlaps((start, end), x) for x in occupied):
            continue
        occupied.append((start, end))
        pid, poss = _possessor_before(text, start, players)
        if not player_relative:
            pid = None
        zone_id = f"Z{len(zones)+1}"
        row = {
            "zoneId": zone_id,
            "zoneType": zone_type,
            "boardGroup": group,
            "surface": surface,
            "associatedPlayerId": pid,
            "playerAssociationBasis": poss,
            "provenance": {"source": "explicit_text", "span": _span(start, end)},
        }
        zones.append(row)
        if player_relative and pid in {None, "P_UNKNOWN"}:
            unknowns.append({
                "unknownId": f"U_ZONE_{zone_id}",
                "kind": "zone_player",
                "zoneId": zone_id,
                "whyUnknown": f"The player associated with '{poss or surface}' was not uniquely stated.",
            })
        if zone_type in {"Base", "Battlefield"}:
            matching = [o for o in objects if o.get("kind") == zone_type and _overlaps((start, end), (int(o["provenance"]["span"]["start"]), int(o["provenance"]["span"]["end"])))]
            obj_id = matching[0]["objectId"] if matching else None
            locations.append({
                "locationId": f"L{len(locations)+1}",
                "locationType": zone_type,
                "surface": surface,
                "zoneId": zone_id,
                "objectId": obj_id,
                "associatedPlayerId": pid,
                "provenance": {"source": "explicit_text", "span": _span(start, end)},
            })
    return zones, locations, unknowns


def _object_span(obj: dict[str, Any]) -> tuple[int, int]:
    sp = obj.get("provenance", {}).get("span", {})
    return int(sp.get("start", 0)), int(sp.get("end", 0))


def _extract_states(text: str, objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    states: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    forbidden_between = {"unit", "units", "card", "cards", "gear", "spell", "spells", "battlefield", "battlefields", "base", "bases", "legend", "legends", "in", "at", "on", "to", "from"}
    for obj in objects:
        start, end = _object_span(obj)
        left_start = max(0, start - 42)
        left = text[left_start:start]
        right = text[end:min(len(text), end + 55)]
        for state, words in _STATE_WORDS.items():
            word_alt = "|".join(re.escape(x) for x in words)
            lm = None
            # Find the last state word in the immediate left context and verify that
            # only harmless adjective material sits between it and this object.
            left_matches = list(re.finditer(rf"\b(?P<state>{word_alt})\b", left, re.I))
            if left_matches:
                cand = left_matches[-1]
                tail = left[cand.end():]
                tail_tokens = {x.casefold() for x in re.findall(r"[A-Za-z][A-Za-z'’-]*", tail)}
                if len(tail) <= 24 and not (tail_tokens & forbidden_between):
                    lm = cand
            # Predicate form: "the unit is already Stunned".
            rm = re.match(rf"\s+(?:is|was|remains?|stays?)\s+(?:already\s+|currently\s+)?(?P<state>{word_alt})\b", right, re.I)
            if not lm and not rm:
                continue
            key = (obj["objectId"], state)
            if key in seen:
                continue
            seen.add(key)
            if lm:
                ss = left_start + lm.start("state"); ee = left_start + lm.end("state")
                basis = text[ss:end]
            else:
                ss = end + rm.start("state"); ee = end + rm.end("state")
                basis = text[start:ee]
            states.append({
                "stateId": f"S{len(states)+1}",
                "objectId": obj["objectId"],
                "state": state,
                "value": True,
                "provenance": {"source": "explicit_text", "basis": basis, "span": _span(ss, ee)},
            })
    return states

def _same_clause(text: str, a_end: int, b_start: int) -> bool:
    if b_start < a_end:
        return False
    return not bool(re.search(r"[,.!?;]", text[a_end:b_start]))


def _location_relations(text: str, objects: list[dict[str, Any]], zones: list[dict[str, Any]], locations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rels: list[dict[str, Any]] = []
    place_by_zone = {l["zoneId"]: l for l in locations}
    for obj in objects:
        if obj.get("kind") in {"Base", "Battlefield"}:
            continue
        os, oe = _object_span(obj)
        for zone in zones:
            zs = int(zone["provenance"]["span"]["start"]); ze = int(zone["provenance"]["span"]["end"])
            if zs <= oe or not _same_clause(text, oe, zs):
                continue
            between = text[oe:zs]
            if not re.search(r"\b(?:is|was|remains?|stays?|sits?)?\s*(?:at|in|on)\s+(?:a|an|the|my|your|their|opponent(?:'s|’s)?|player\s+\d+(?:'s|’s)?)?\s*$", between, re.I):
                continue
            location_id = (place_by_zone.get(zone["zoneId"]) or {}).get("locationId")
            rels.append({
                "relationId": "",
                "type": "located_at",
                "objectId": obj["objectId"],
                "zoneId": zone["zoneId"],
                "locationId": location_id,
                "provenance": {"source": "explicit_text", "basis": text[os:ze], "span": _span(os, ze)},
            })
            break
    return rels


def _normalize_relations(language: dict[str, Any], object_map: dict[str, str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for rel in language.get("relations", []):
        typ = {"explicit_control": "controls", "explicit_ownership": "owns"}.get(rel.get("type"), rel.get("type"))
        row = {
            "relationId": "",
            "type": typ,
            "subjectPlayerId": rel.get("subjectId"),
            "objectId": object_map.get(str(rel.get("objectId"))),
            "provenance": {"source": "scenario_language", "basis": rel.get("basis"), "confidence": rel.get("confidence")},
        }
        out.append(row)
    return out


def _event_place_relations(text: str, events: list[dict[str, Any]], zones: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ev in events:
        es = int(ev["provenance"]["span"]["start"]); ee = int(ev["provenance"]["span"]["end"])
        for zone in zones:
            zs = int(zone["provenance"]["span"]["start"])
            if zs < ee or zs - ee > 90 or not _same_clause(text, ee, zs):
                continue
            between = text[ee:zs]
            if re.search(r"\bfrom\b", between, re.I):
                if not any(x.get("eventId") == ev["eventId"] and x.get("type") == "event_source" for x in out):
                    out.append({"relationId": "", "type": "event_source", "eventId": ev["eventId"], "zoneId": zone["zoneId"], "provenance": {"source": "explicit_text", "basis": text[es:int(zone["provenance"]["span"]["end"])], "span": _span(es, int(zone["provenance"]["span"]["end"]))}})
            if re.search(r"\b(?:to|into)\b", between, re.I):
                if not any(x.get("eventId") == ev["eventId"] and x.get("type") == "event_destination" for x in out):
                    out.append({"relationId": "", "type": "event_destination", "eventId": ev["eventId"], "zoneId": zone["zoneId"], "provenance": {"source": "explicit_text", "basis": text[es:int(zone["provenance"]["span"]["end"])], "span": _span(es, int(zone["provenance"]["span"]["end"]))}})
    return out


def build_scenario_model(original_text: str, interpreted_text: str, cards: dict[str, Any], language_analysis: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a normalized, non-adjudicative game-state representation.

    M7 invariant: this model contains only language-supported structure. It does not
    apply rules, advance game state, infer default controllers/owners, or guess a
    reference/temporal order that the player did not state.
    """
    language = language_analysis if language_analysis is not None else analyze_scenario_language(interpreted_text, cards)
    players = [dict(p) for p in language.get("players", [])]

    objects: list[dict[str, Any]] = []
    object_map: dict[str, str] = {}
    for ent in language.get("entities", []):
        oid = f"O{len(objects)+1}"
        object_map[str(ent.get("entityId"))] = oid
        row = {
            "objectId": oid,
            "sourceEntityId": ent.get("entityId"),
            "kind": ent.get("kind"),
            "surface": ent.get("surface"),
            "canonicalCardIdentity": ent.get("canonicalCardIdentity"),
            "canonicalName": ent.get("canonicalName"),
            "printingIds": list(ent.get("printingIds") or []),
            "discoursePossessorPlayerId": ent.get("discoursePossessor"),
            "provenance": {"source": ent.get("source"), "span": _span(ent.get("start", 0), ent.get("end", 0))},
        }
        objects.append(row)

    zones, locations, zone_unknowns = _extract_zones(interpreted_text, players, objects)
    states = _extract_states(interpreted_text, objects)
    relations = _normalize_relations(language, object_map)
    relations.extend(_location_relations(interpreted_text, objects, zones, locations))

    references: list[dict[str, Any]] = []
    unknowns: list[dict[str, Any]] = list(zone_unknowns)
    clarifications = []
    for raw in language.get("clarifyingQuestions", []):
        row = dict(raw)
        if row.get("candidateEntityIds") is not None:
            row["candidateObjectIds"] = [object_map[x] for x in row.get("candidateEntityIds", []) if x in object_map]
            row.pop("candidateEntityIds", None)
        clarifications.append(row)
    for ref in language.get("references", []):
        row = {
            "referenceId": ref.get("referenceId"),
            "surface": ref.get("surface"),
            "status": ref.get("status"),
            "resolvedObjectId": object_map.get(str(ref.get("resolvedEntityId"))) if ref.get("resolvedEntityId") else None,
            "resolvedPlayerId": ref.get("resolvedPlayerId"),
            "candidateObjectIds": [object_map[x] for x in ref.get("candidateEntityIds", []) if x in object_map],
            "provenance": {"source": "scenario_language", "basis": ref.get("basis"), "span": _span(ref.get("start", 0), ref.get("end", 0), "interpreted")},
        }
        references.append(row)
        if row["status"] in {"ambiguous", "unresolved"}:
            unknowns.append({
                "unknownId": f"U_REF_{row['referenceId']}",
                "kind": "reference",
                "referenceId": row["referenceId"],
                "whyUnknown": str(ref.get("basis") or "reference is unresolved"),
            })

    events: list[dict[str, Any]] = []
    for ev in language.get("events", []):
        events.append({
            "eventId": ev.get("eventId"),
            "type": ev.get("type"),
            "surface": ev.get("surface"),
            "mentionedObjectIds": [object_map[x] for x in ev.get("entityIds", []) if x in object_map],
            "ordering": ev.get("ordering"),
            "provenance": {"source": "scenario_language", "span": _span(ev.get("start", 0), ev.get("end", 0))},
        })
    relations.extend(_event_place_relations(interpreted_text, events, zones))

    temporal = []
    for rel in language.get("temporalRelations", []):
        temporal.append({
            "type": rel.get("type"),
            "firstEventId": rel.get("firstEventId"),
            "secondEventId": rel.get("secondEventId"),
            "confidence": rel.get("confidence"),
            "provenance": {"source": "scenario_language", "basis": rel.get("basis")},
        })

    # Assign deterministic relation IDs only after all relation sources are combined.
    for i, rel in enumerate(relations, 1):
        rel["relationId"] = f"REL{i}"

    # Add M7-specific clarification for ambiguous player-relative zones.
    for u in zone_unknowns:
        zid = u.get("zoneId")
        zone = next((z for z in zones if z.get("zoneId") == zid), None)
        clarifications.append({
            "kind": "zone_player",
            "zoneId": zid,
            "question": f"Which player's {zone.get('zoneType') if zone else 'zone'} do you mean?",
            "whyNeeded": u.get("whyUnknown"),
        })

    return {
        "schemaVersion": 1,
        "originalText": original_text or "",
        "interpretedText": interpreted_text or "",
        "players": players,
        "objects": objects,
        "zones": zones,
        "locations": locations,
        "states": states,
        "relations": relations,
        "references": references,
        "events": events,
        "temporalRelations": temporal,
        "unknowns": unknowns,
        "clarifyingQuestions": clarifications,
        "assumptions": list(language.get("assumptions") or []),
        "policy": {
            "appliesGameRules": False,
            "advancesGameState": False,
            "englishPossessionImpliesGameControl": False,
            "englishPossessionImpliesGameOwnership": False,
            "ambiguousReferencesAreGuessed": False,
            "unstatedTemporalOrderIsInferred": False,
            "unstatedStatusIsInferred": False,
            "eventDestinationsAreCurrentLocations": False,
        },
    }
