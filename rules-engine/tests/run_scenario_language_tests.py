#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from riftkeep_rules.scenario_language import analyze_scenario_language

cards = json.loads((ROOT / "data/canonical/cards.json").read_text(encoding="utf-8"))
checks = 0
failures: list[dict[str, str]] = []


def check(name: str, ok: bool, detail: object = "") -> None:
    global checks
    checks += 1
    if not ok:
        failures.append({"check": name, "detail": str(detail)})


def one(q: str) -> dict:
    return analyze_scenario_language(q, cards)


def rels(a: dict, kind: str) -> list[dict]:
    return [r for r in a.get("relations", []) if r.get("type") == kind]


def event_types(a: dict) -> list[str]:
    return [str(e.get("type")) for e in a.get("events", [])]


# T47/T50 — discourse possession is not game control/ownership.
a = one("My unit dies.")
check("my unit creates a Unit entity", len(a["entities"]) == 1 and a["entities"][0]["kind"] == "Unit", a["entities"])
check("my unit records discourse possession", len(rels(a, "discourse_possession")) == 1, a["relations"])
check("my unit does not infer control", not rels(a, "explicit_control"), a["relations"])
check("my unit does not infer ownership", not rels(a, "explicit_ownership"), a["relations"])
check("scenario assumptions start empty", a["assumptions"] == [], a["assumptions"])
check("scenario policy explicitly forbids possession->control", a["policy"]["englishPossessionImpliesGameControl"] is False, a["policy"])

b = one("A unit I control dies.")
check("relative clause I control is explicit control", len(rels(b, "explicit_control")) == 1 and rels(b, "explicit_control")[0]["subjectId"] == "P_SELF", b["relations"])

c = one("I control a unit and Player 2 owns a spell.")
check("subject-first control relation resolves", any(r["subjectId"] == "P_SELF" and r["type"] == "explicit_control" for r in c["relations"]), c["relations"])
check("Player 2 ownership relation resolves", any(r["subjectId"] == "P_PLAYER_2" and r["type"] == "explicit_ownership" for r in c["relations"]), c["relations"])
check("multiple explicit players are retained", {p["playerId"] for p in c["players"]} >= {"P_SELF", "P_PLAYER_2"}, c["players"])

d = one("A unit controlled by my opponent dies.")
check("controlled-by opponent relation resolves", len(rels(d, "explicit_control")) == 1 and rels(d, "explicit_control")[0]["subjectId"] == "P_OPPONENT_1", d["relations"])

# T51 — references resolve only when unique; ambiguity stays unresolved.
a = one("I have a unit. It dies.")
check("single antecedent pronoun resolves", len(a["references"]) == 1 and a["references"][0]["status"] == "resolved", a["references"])
check("resolved pronoun points to prior Unit", a["references"][0].get("resolvedEntityId") == a["entities"][0]["entityId"], a["references"])

b = one("I have a unit and another unit. It dies.")
check("two compatible antecedents keep it ambiguous", len(b["references"]) == 1 and b["references"][0]["status"] == "ambiguous", b["references"])
check("ambiguous reference retains both candidates", len(b["references"][0].get("candidateEntityIds", [])) == 2, b["references"])
check("ambiguous reference creates clarification", len(b["clarifyingQuestions"]) == 1 and b["clarifyingQuestions"][0]["kind"] == "reference", b["clarifyingQuestions"])
check("nearest-noun binding is explicitly disabled", b["policy"]["ambiguousReferencesBindToNearestNoun"] is False, b["policy"])

c = one("It dies.")
check("pronoun without antecedent remains unresolved", len(c["unresolvedReferences"]) == 1 and c["unresolvedReferences"][0]["status"] == "unresolved", c["unresolvedReferences"])
check("unresolved pronoun asks what it refers to", len(c["clarifyingQuestions"]) == 1 and "refer" in c["clarifyingQuestions"][0]["question"].casefold(), c["clarifyingQuestions"])

d = one("I have a unit and a spell. That unit dies.")
check("typed demonstrative filters incompatible Spell", len(d["references"]) == 1 and d["references"][0]["status"] == "resolved", d["references"])
check("typed demonstrative resolves to Unit", d["references"][0].get("resolvedEntityId") == next(e["entityId"] for e in d["entities"] if e["kind"] == "Unit"), d["references"])


# Semantic compatibility can narrow a pronoun without nearest-noun guessing.
e = one("Can I play a unit to a battlefield I control and is it Contested?")
check("Contested pronoun resolves by exclusive Battlefield type", len(e["references"]) == 1 and e["references"][0]["status"] == "resolved", e["references"])
if e["references"]:
    bf = next(x for x in e["entities"] if x["kind"] == "Battlefield")
    check("Contested pronoun resolves to Battlefield not Unit", e["references"][0].get("resolvedEntityId") == bf["entityId"], e["references"] )

# T49 — only explicit temporal language creates ordering.
a = one("My unit dies, then I play a spell.")
check("then creates two events", event_types(a) == ["die", "play"], a["events"])
check("then creates explicit before relation", len(a["temporalRelations"]) == 1 and a["temporalRelations"][0]["type"] == "before" and a["temporalRelations"][0]["firstEventId"] == "EV1" and a["temporalRelations"][0]["secondEventId"] == "EV2", a["temporalRelations"])

b = one("I play a spell after my unit dies.")
check("infix after reverses textual event order", len(b["temporalRelations"]) == 1 and b["temporalRelations"][0]["firstEventId"] == "EV2" and b["temporalRelations"][0]["secondEventId"] == "EV1", b["temporalRelations"])

c = one("After my unit dies, I play a spell.")
check("prefix after orders subordinate event first", len(c["temporalRelations"]) == 1 and c["temporalRelations"][0]["firstEventId"] == "EV1" and c["temporalRelations"][0]["secondEventId"] == "EV2", c["temporalRelations"])

d = one("I play a spell before my unit dies.")
check("infix before preserves textual order", len(d["temporalRelations"]) == 1 and d["temporalRelations"][0]["firstEventId"] == "EV1" and d["temporalRelations"][0]["secondEventId"] == "EV2", d["temporalRelations"])

e = one("Before my unit dies, I play a spell.")
check("prefix before orders main event first", len(e["temporalRelations"]) == 1 and e["temporalRelations"][0]["firstEventId"] == "EV2" and e["temporalRelations"][0]["secondEventId"] == "EV1", e["temporalRelations"])

f = one("While my unit attacks, I play a spell.")
check("attack is recognized as an event", event_types(f) == ["attack", "play"], f["events"])
check("while records overlap rather than before", len(f["temporalRelations"]) == 1 and f["temporalRelations"][0]["type"] == "overlaps", f["temporalRelations"])

g = one("My unit dies and I play a spell.")
check("and alone does not invent event order", len(g["events"]) == 2 and g["temporalRelations"] == [], {"events": g["events"], "temporal": g["temporalRelations"]})
check("unstated event order remains marked unstated", all(e["ordering"] == "unstated" for e in g["events"]), g["events"])
check("policy forbids inferred unstated order", g["policy"]["unstatedTemporalOrderIsInferred"] is False, g["policy"])

# Multiple explicit connectors should retain a chain rather than collapsing it.
h = one("My unit dies, then I play a spell, then I move a unit.")
check("multiple then connectors retain all events", event_types(h) == ["die", "play", "move"], h["events"])
check("multiple then connectors create event chain", {(r["firstEventId"], r["secondEventId"]) for r in h["temporalRelations"] if r["type"] == "before"} == {("EV1", "EV2"), ("EV2", "EV3")}, h["temporalRelations"])

# T53 — real card DB: gameplay identity is canonical but printing provenance remains.
a = one("Renekton, Brute attacks.")
ren = [e for e in a["entities"] if e.get("canonicalCardIdentity") == "renekton brute"]
check("Renekton Brute resolves as named-card entity", len(ren) == 1 and ren[0]["canonicalName"] == "Renekton, Brute", ren)
check("Renekton Brute retains all printings", len(ren) == 1 and len(ren[0]["printingIds"]) == 3, ren)
check("named card preserves gameplay type", len(ren) == 1 and ren[0]["kind"] == "Unit", ren)

b = one("Renekton, Brute has Shady Spectacles attached.")
named = [e for e in b["entities"] if e.get("canonicalCardIdentity")]
check("two named cards remain separate gameplay identities", {e["canonicalCardIdentity"] for e in named} == {"renekton brute", "shady spectacles"}, named)
check("named-card provenance is never collapsed across identities", all(e.get("printingIds") for e in named) and len({pid for e in named for pid in e["printingIds"]}) == sum(len(e["printingIds"]) for e in named), named)

# T52 — assumption ledger stays explicit and empty across complex input.
c = one("After my opponent's unit dies, that card moves and then it is recalled.")
check("complex scenario still invents no assumptions", c["assumptions"] == [], c)
check("complex scenario surfaces unresolved references rather than guessing", len(c["unresolvedReferences"]) >= 1, c["references"])

out = {"passed": not failures, "checkCount": checks, "failureCount": len(failures), "failures": failures}
(ROOT / "data/validation/scenario_language_test_report.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=2))
raise SystemExit(0 if not failures else 1)
