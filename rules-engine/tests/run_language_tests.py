#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from riftkeep_rules.engine import RulesEngine
from riftkeep_rules.player_language import normalize_player_language
from riftkeep_rules.retrieval import decompose_question

engine = RulesEngine(ROOT, require_current_authority=False)
checks = 0
failures: list[dict[str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not ok:
        failures.append({"check": name, "detail": detail})


def fact_map(result: dict) -> dict[str, str]:
    return {x["name"]: str(getattr(x.get("value"), "value", x.get("value"))) for x in result.get("facts", [])}


# T41 — transparent aliases and ambiguity reporting.
tap = normalize_player_language("If my unit is already tapped, can I tap it again?")
check("tap/tapped aliases are transparent", tap["text"] == "If my unit is already Exhausted, can I Exhaust it again?", str(tap))
check("tap transformation records both source terms", {x["from"].casefold() for x in tap["transformations"]} == {"tapped", "tap"}, str(tap["transformations"]))
check("normalization preserves original question", tap["original"] == "If my unit is already tapped, can I tap it again?", str(tap))

untap = normalize_player_language("An untapped unit can untap")
check("untap aliases use Ready vocabulary", untap["text"] == "An Ready unit can Ready", str(untap))

cast = normalize_player_language("I am casting this after I cast the first spell")
check("cast morphology maps to Play vocabulary", "Playing" in cast["text"] and "play the first spell" in cast["text"], str(cast))

summon = normalize_player_language("I summoned one unit and summon another")
check("summon morphology maps to Play vocabulary", summon["text"] == "I played one unit and play another", str(summon))

grave = normalize_player_language("Put it in my graveyard, not the discard pile")
check("graveyard/discard pile aliases map to Trash", grave["text"] == "Put it in my Trash, not the Trash", str(grave))

battle = normalize_player_language("If my unit dies in battle, what happens?")
check("ambiguous battle is not silently transformed", battle["changed"] is False and battle["text"] == battle["original"], str(battle))
check("ambiguous battle is explicitly surfaced", any(x.get("term") == "battle" for x in battle.get("ambiguousTerms", [])), str(battle))

# T43 — safe multipart decomposition keeps the question verb and antecedent retrieval context.
parts = decompose_question("Can I summon a unit straight to a battlefield I control and is it contested?")
check("multipart decomposition produces two issues", len(parts) == 2, str(parts))
if len(parts) == 2:
    check("follow-up keeps leading question verb", parts[1]["text"].casefold() == "is it contested", str(parts[1]))
    ctx = parts[1]["retrievalQuery"].casefold()
    check("follow-up carries unit antecedent", "unit" in ctx, ctx)
    check("follow-up carries battlefield antecedent", "battlefield" in ctx, ctx)
    check("follow-up carries normalized Play antecedent", "play" in ctx, ctx)

parts2 = decompose_question("Can I play a unit to my base and can I Ready it afterward?")
check("and-can follow-up preserves can", len(parts2) == 2 and parts2[1]["text"].casefold().startswith("can i ready"), str(parts2))

# T42 — normalized text is actually consumed by facts, action detection, proof and retrieval.
tapped_cost = engine.ask("If my unit is already tapped, can I tap it again to pay a cost?")
check("engine preserves full original question", tapped_cost["question"] == "If my unit is already tapped, can I tap it again to pay a cost?", tapped_cost["question"])
check("engine exposes normalized interpretation", tapped_cost["questionInterpretation"]["text"] == "If my unit is already Exhausted, can I Exhaust it again to pay a cost?", str(tapped_cost["questionInterpretation"]))
fm = fact_map(tapped_cost)
check("facts are extracted from normalized Exhausted wording", fm.get("object_already_exhausted") == "true", str(fm))
check("proof obligations see normalized Exhaust wording", "exhaust_state" in tapped_cost["issues"][0]["proof"]["obligations"], str(tapped_cost["issues"][0]["proof"]))
actions = {x["name"] for x in tapped_cost.get("mentionedGameActions", [])}
check("Game Action detection sees Exhaust from tap alias", "Exhaust" in actions, str(actions))
check("tap-as-cost colloquial ruling is deterministic", tapped_cost["issues"][0]["ruling"]["status"] == "decided" and "no" in [o.get("verdict") for o in tapped_cost["issues"][0]["ruling"].get("outcomes", [])], tapped_cost.get("answer", ""))
check("tap alias retrieval closes governing Exhaust rule", "414.4" in tapped_cost["issues"][0]["retrieval"]["evidenceRuleIds"], str(tapped_cost["issues"][0]["retrieval"]["evidenceRuleIds"]))

summon_base = engine.ask("Can I summon a unit to my base?")
check("summon alias reaches Unit-play proof", "unit_play_location" in summon_base["issues"][0]["proof"]["obligations"], str(summon_base["issues"][0]["proof"]))
check("summon-to-base colloquial question decides yes", "yes" in [o.get("verdict") for o in summon_base["issues"][0]["ruling"].get("outcomes", [])], summon_base.get("answer", ""))
check("summon alias retrieves default valid-location rule", all(r in summon_base["issues"][0]["retrieval"]["evidenceRuleIds"] for r in ("355.2", "355.2.a")), str(summon_base["issues"][0]["retrieval"]["evidenceRuleIds"]))

multipart = engine.ask("Can I summon a unit straight to a battlefield I control and is it contested?")
check("multipart engine result contains two adjudicated issues", len(multipart["issues"]) == 2, str(multipart.get("issues")))
if len(multipart["issues"]) == 2:
    v0 = [o.get("verdict") for o in multipart["issues"][0]["ruling"].get("outcomes", [])]
    v1 = [o.get("verdict") for o in multipart["issues"][1]["ruling"].get("outcomes", [])]
    check("multipart first issue resolves play permission", "yes" in v0, str(v0))
    check("multipart second issue resolves Contested", "no" in v1, str(v1))
    check("multipart second issue retains antecedent retrieval context", all(x in multipart["issues"][1]["retrievalContext"].casefold() for x in ("unit", "battlefield", "play")), multipart["issues"][1]["retrievalContext"])

# Authoritative evidence must remain canonical; only the player's interpretation changes.
core_by_id = {r["ruleId"]: r["normativeText"] for r in engine.core["rules"]}
for outcome in tapped_cost["issues"][0]["ruling"].get("outcomes", []):
    for ev in outcome.get("evidence", []):
        rid = ev.get("ruleId")
        if rid in core_by_id:
            check(f"authoritative evidence unchanged for {rid}", ev.get("text") == core_by_id[rid], str(ev))

# T44 — conditional rulings request exact missing predicates rather than guessing.
missing_control = engine.ask("Can I play a unit to a battlefield?")
clar = missing_control["issues"][0].get("clarifyingQuestions", [])
check("unknown battlefield control produces conditional ruling", missing_control["issues"][0]["ruling"]["status"] == "conditional", missing_control.get("answer", ""))
check("missing battlefield-control fact generates clarification", any(x.get("fact") == "actor_controls_battlefield" for x in clar), str(clar))

hidden = engine.ask("I have a Hidden card at a battlefield I control, but my last unit dies. Do I recycle it or remove it from battle?")
hidden_clar = hidden["issues"][0].get("clarifyingQuestions", [])
hidden_facts = {x.get("fact") for x in hidden_clar}
check("Hidden lifecycle remains conditional without timing facts", hidden["issues"][0]["ruling"]["status"] == "conditional", hidden.get("answer", ""))
check("Hidden clarification asks Open-State fact", "turn_is_open_state" in hidden_facts, str(hidden_clar))
check("Hidden clarification asks Combat fact", "combat_ongoing_at_battlefield" in hidden_facts, str(hidden_clar))
check("Hidden clarification asks Showdown fact", "showdown_ongoing_at_battlefield" in hidden_facts, str(hidden_clar))

# T45 — ambiguity boundary: no silent Battle -> Combat/Battlefield/Showdown conversion.
ambiguous = engine.ask("If my unit dies in battle, what happens?")
check("ambiguous term remains reported at engine boundary", any(x.get("term") == "battle" for x in ambiguous["questionInterpretation"].get("ambiguousTerms", [])), str(ambiguous["questionInterpretation"]))
amb_fm = fact_map(ambiguous)
check("ambiguous battle does not invent Combat state", "combat_ongoing_at_battlefield" not in amb_fm, str(amb_fm))
check("ambiguous battle does not invent Showdown state", "showdown_ongoing_at_battlefield" not in amb_fm, str(amb_fm))

out = {"passed": not failures, "checkCount": checks, "failureCount": len(failures), "failures": failures}
(ROOT / "data/validation/language_test_report.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=2))
raise SystemExit(0 if not failures else 1)
