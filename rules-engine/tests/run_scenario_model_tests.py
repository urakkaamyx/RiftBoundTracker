#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from riftkeep_rules.engine import RulesEngine
from riftkeep_rules.player_language import normalize_player_language
from riftkeep_rules.scenario_model import build_scenario_model

cards = json.loads((ROOT / "data/canonical/cards.json").read_text(encoding="utf-8"))
engine = RulesEngine(ROOT, require_current_authority=False)
checks = 0
failures: list[dict[str, str]] = []


def check(name: str, ok: bool, detail: object = "") -> None:
    global checks
    checks += 1
    if not ok:
        failures.append({"check": name, "detail": str(detail)})


def model(q: str) -> dict:
    interp = normalize_player_language(q)["text"]
    return build_scenario_model(q, interp, cards)


def rels(m: dict, typ: str) -> list[dict]:
    return [x for x in m.get("relations", []) if x.get("type") == typ]


def states(m: dict, name: str) -> list[dict]:
    return [x for x in m.get("states", []) if x.get("state") == name]


# T57 — contract shape and explicit non-adjudicative policy.
schema = json.loads((ROOT / "contracts/scenario_model.schema.json").read_text(encoding="utf-8"))
required = set(schema.get("required", []))
m = model("My unit is Ready.")
check("scenario model contract required keys present", required <= set(m), sorted(required - set(m)))
check("scenario model schema version fixed", m.get("schemaVersion") == 1, m.get("schemaVersion"))
check("scenario model does not apply game rules", m["policy"].get("appliesGameRules") is False, m["policy"])
check("scenario model does not advance state", m["policy"].get("advancesGameState") is False, m["policy"])
check("scenario model assumption ledger starts empty", m.get("assumptions") == [], m.get("assumptions"))

# T58 — object normalization and card provenance.
m = model("Renekton, Brute attacks while Shady Spectacles is attached.")
named = [o for o in m["objects"] if o.get("canonicalCardIdentity")]
check("named cards become stable scenario objects", {o["canonicalCardIdentity"] for o in named} == {"renekton brute", "shady spectacles"}, named)
ren = next(o for o in named if o["canonicalCardIdentity"] == "renekton brute")
check("Renekton retains all printing provenance", len(ren.get("printingIds", [])) == 3, ren)
check("scenario object IDs are deterministic sequence", [o["objectId"] for o in m["objects"]] == [f"O{i}" for i in range(1, len(m["objects"])+1)], m["objects"])
check("named card kind is retained", ren.get("kind") == "Unit", ren)

# T59 — zones and locations.
m = model("Player 2 controls a stunned unit in base and owns a card in their Trash.")
zone_types = {z["zoneType"] for z in m["zones"]}
check("Base is represented as Board zone", any(z["zoneType"] == "Base" and z["boardGroup"] == "Board" for z in m["zones"]), m["zones"])
check("Trash is represented as Non-Board zone", any(z["zoneType"] == "Trash" and z["boardGroup"] == "Non-Board" for z in m["zones"]), m["zones"])
trash = next(z for z in m["zones"] if z["zoneType"] == "Trash")
check("their Trash resolves to unique explicit Player 2", trash.get("associatedPlayerId") == "P_PLAYER_2", trash)
check("Base is represented as a Location", any(l["locationType"] == "Base" for l in m["locations"]), m["locations"])
check("unspecified Base player stays unknown", any(u.get("kind") == "zone_player" and u.get("zoneId") == next(z["zoneId"] for z in m["zones"] if z["zoneType"] == "Base") for u in m["unknowns"]), m["unknowns"])
check("unspecified Base produces clarification", any(q.get("kind") == "zone_player" and "Base" in q.get("question", "") for q in m["clarifyingQuestions"]), m["clarifyingQuestions"])
check("unit explicitly in Base has current location relation", len([r for r in rels(m, "located_at") if r.get("objectId") == "O1"]) == 1, m["relations"])
check("owned card explicitly in Trash has current zone relation", any(r.get("type") == "located_at" and r.get("objectId") == "O3" and r.get("zoneId") == trash["zoneId"] for r in m["relations"]), m["relations"])

m = model("I move a unit from a battlefield to my Base.")
move = next(e for e in m["events"] if e["type"] == "move")
src = [r for r in rels(m, "event_source") if r.get("eventId") == move["eventId"]]
dst = [r for r in rels(m, "event_destination") if r.get("eventId") == move["eventId"]]
check("Move records explicit source zone", len(src) == 1 and next(z for z in m["zones"] if z["zoneId"] == src[0]["zoneId"])["zoneType"] == "Battlefield", {"src":src,"zones":m["zones"]})
check("Move records explicit destination zone", len(dst) == 1 and next(z for z in m["zones"] if z["zoneId"] == dst[0]["zoneId"])["zoneType"] == "Base", {"dst":dst,"zones":m["zones"]})
check("event destination is not asserted as current location", not rels(m, "located_at"), m["relations"])
check("event destination policy is explicit", m["policy"].get("eventDestinationsAreCurrentLocations") is False, m["policy"])

m = model("A spell is on the Chain.")
chain = next(z for z in m["zones"] if z["zoneType"] == "Chain")
check("Chain is global Non-Board zone", chain["boardGroup"] == "Non-Board" and chain.get("associatedPlayerId") is None, chain)
check("global Chain does not create player unknown", not any(u.get("zoneId") == chain["zoneId"] for u in m["unknowns"]), m["unknowns"])

# T60 — explicit states only.
m = model("My Hidden card is at a Contested battlefield and my Stunned unit is Exhausted.")
check("Hidden state captured", len(states(m, "Hidden")) == 1, m["states"])
check("Contested state captured on Battlefield", len(states(m, "Contested")) == 1 and next(o for o in m["objects"] if o["objectId"] == states(m,"Contested")[0]["objectId"])["kind"] == "Battlefield", m["states"])
check("Stunned state captured on Unit", len(states(m, "Stunned")) == 1, m["states"])
check("Exhausted predicate state captured", len(states(m, "Exhausted")) == 1, m["states"])
check("Hidden adjective no longer creates fake Hide event", "hide" not in {e["type"] for e in m["events"]}, m["events"])

m = model("I stun a unit.")
check("Stun instruction is event not preexisting Stunned state", any(e["type"] == "stun" for e in m["events"]) and not states(m, "Stunned"), {"events":m["events"],"states":m["states"]})

m = model("An empowered Renekton, Brute attacks.")
check("named-card Empowered state captured", len(states(m, "Empowered")) == 1 and states(m,"Empowered")[0]["objectId"] == next(o["objectId"] for o in m["objects"] if o.get("canonicalCardIdentity") == "renekton brute"), m["states"])

# T61 — owner/controller are explicit and distinct from discourse possession.
m = model("Player 2 controls a stunned unit in base and owns a card in their Trash.")
check("qualified controlled Unit relation survives", any(r["type"] == "controls" and r.get("subjectPlayerId") == "P_PLAYER_2" and r.get("objectId") == "O1" for r in m["relations"]), m["relations"])
check("coordinated owns relation survives", any(r["type"] == "owns" and r.get("subjectPlayerId") == "P_PLAYER_2" and r.get("objectId") == "O3" for r in m["relations"]), m["relations"])

m = model("I control Renekton, Brute at a battlefield.")
check("explicit control can target named card object", any(r["type"] == "controls" and r.get("objectId") == "O1" for r in m["relations"]), m["relations"])

m = model("My unit dies.")
check("my unit remains discourse possession only", len(rels(m, "discourse_possession")) == 1, m["relations"])
check("my unit does not infer controls", not rels(m, "controls"), m["relations"])
check("my unit does not infer owns", not rels(m, "owns"), m["relations"])

# T62 — references and temporal edges.
m = model("I have a unit. It dies.")
check("resolved pronoun maps to scenario object ID", len(m["references"]) == 1 and m["references"][0]["status"] == "resolved" and m["references"][0].get("resolvedObjectId") == "O1", m["references"])

m = model("I have a unit and a spell. It moves to Banishment.")
ref = m["references"][0]
check("ambiguous pronoun stays ambiguous", ref["status"] == "ambiguous" and set(ref["candidateObjectIds"]) == {"O1","O2"}, ref)
check("ambiguous pronoun becomes typed unknown", any(u.get("kind") == "reference" and u.get("referenceId") == ref["referenceId"] for u in m["unknowns"]), m["unknowns"])
check("clarification uses normalized object IDs", any(set(q.get("candidateObjectIds", [])) == {"O1","O2"} for q in m["clarifyingQuestions"] if q.get("kind") == "reference"), m["clarifyingQuestions"])

m = model("My unit dies, then I play a spell, then I move a unit.")
check("then event chain retained", [(r["firstEventId"],r["secondEventId"]) for r in m["temporalRelations"] if r["type"] == "before"] == [("EV1","EV2"),("EV2","EV3")], m["temporalRelations"])

m = model("While my unit attacks, I play a spell.")
check("while becomes overlaps edge", len(m["temporalRelations"]) == 1 and m["temporalRelations"][0]["type"] == "overlaps", m["temporalRelations"])

m = model("My unit dies and I play a spell.")
check("plain and creates no temporal edge", m["temporalRelations"] == [], m["temporalRelations"])
check("plain and leaves event order unstated", all(e["ordering"] == "unstated" for e in m["events"]), m["events"])

# T63 — unknown/assumption provenance.
m = model("A unit is in base.")
check("player-relative Base without player is typed unknown", any(u.get("kind") == "zone_player" for u in m["unknowns"]), m["unknowns"])
check("unknown zone player does not create assumption", m["assumptions"] == [], m["assumptions"])

m = model("Player 2 controls a unit. Player 3 owns a spell. It moves to their Hand.")
check("multiple third-party players keep their Hand ambiguous", any(u.get("kind") == "zone_player" for u in m["unknowns"]), {"players":m["players"],"unknowns":m["unknowns"]})
check("multiple third-party ambiguity stays assumption-free", m["assumptions"] == [], m["assumptions"])

# Player-language normalization feeds M7 structure but preserves original text.
r = engine.ask("If my unit is already tapped, can I tap it again to pay a cost?")
sm = r["scenarioModel"]
check("engine exposes scenarioModel", sm.get("schemaVersion") == 1, sm)
check("scenarioModel preserves original player wording", sm["originalText"] == "If my unit is already tapped, can I tap it again to pay a cost?", sm["originalText"])
check("scenarioModel consumes normalized interpretation", "Exhausted" in sm["interpretedText"] and "Exhaust" in sm["interpretedText"], sm["interpretedText"])
check("normalized tapped wording creates Exhausted state", len(states(sm, "Exhausted")) == 1, sm["states"])
check("scenarioModel integration does not gain adjudicative authority", r["enginePolicy"].get("scenarioModelAppliesGameRules") is False, r["enginePolicy"])

# Integration must not change a known M6 ruling.
r = engine.ask("Can I play a unit to a battlefield I control and does it become Contested?")
check("M7 integration preserves multipart ruling count", len(r["issues"]) == 2, r["issues"])
if len(r["issues"]) == 2:
    check("M7 integration preserves play permission verdict", "yes" in [o.get("verdict") for o in r["issues"][0]["ruling"].get("outcomes",[])], r["issues"][0]["ruling"])
    check("M7 integration preserves controlled-battlefield Contested verdict", "no" in [o.get("verdict") for o in r["issues"][1]["ruling"].get("outcomes",[])], r["issues"][1]["ruling"])

# M7 safety: unresolved scenario-model clarification is additive, not a guessed fact.
r = engine.ask("A unit is in base. Can it move?")
check("scenario-model zone clarification reaches engine result", any(x.get("source") == "scenario_model" and x.get("kind") == "zone_player" for x in r.get("clarifyingQuestions",[])), r.get("clarifyingQuestions"))
check("scenario-model clarification does not populate assumptions", r["scenarioModel"]["assumptions"] == [], r["scenarioModel"])

out = {"passed": not failures, "checkCount": checks, "failureCount": len(failures), "failures": failures}
(ROOT / "data/validation/scenario_model_test_report.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=2))
raise SystemExit(0 if not failures else 1)
