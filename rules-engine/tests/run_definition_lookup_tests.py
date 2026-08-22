#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from riftkeep_rules.engine import RulesEngine

engine = RulesEngine(ROOT, require_current_authority=False)
failures: list[dict[str, str]] = []
checks = 0


def check(name: str, ok: bool, detail: object = "") -> None:
    global checks
    checks += 1
    if not ok:
        failures.append({"check": name, "detail": str(detail)[:4000]})


def definition_root(question: str, expected_rule_id: str) -> tuple[bool, dict]:
    result = engine.ask(question)
    issue = result["issues"][0]
    ruling = issue["ruling"]
    ev = {
        str(e.get("ruleId"))
        for outcome in ruling.get("outcomes", [])
        for e in outcome.get("evidence", [])
        if e.get("ruleId")
    }
    effective = ruling.get("effectiveVerdict") or {}
    ok = (
        ruling.get("status") == "decided"
        and effective.get("verdict") == "definition"
        and expected_rule_id in ev
        and bool((issue.get("proofTrace") or {}).get("verification", {}).get("passed"))
    )
    return ok, {"status": ruling.get("status"), "effective": effective, "evidence": sorted(ev)[:80]}


concepts = engine.semantic_ir["conceptCatalog"]["concepts"]
keywords = [c for c in concepts if c.get("category") == "keyword"]
game_actions = [c for c in concepts if c.get("category") == "game_action"]
rule_concepts = [c for c in concepts if c.get("category") == "rule_concept"]

# Every current keyword must be directly explainable with the natural player phrasing
# that originally exposed this bug: "What does X do?".
for c in keywords:
    ok, detail = definition_root(f"What does {c['name']} do?", str(c["ruleId"]))
    check(f"keyword do-definition {c['ruleId']} {c['name']}", ok, detail)

# Every Game Action must use the same definition path; being executable/migrated is
# irrelevant to whether its authoritative definition can be looked up.
for c in game_actions:
    ok, detail = definition_root(f"What does {c['name']} do?", str(c["ruleId"]))
    check(f"game-action do-definition {c['ruleId']} {c['name']}", ok, detail)

# Every ordinary named Core rule concept remains directly reachable independently of
# whether an adjudication family exists for it.
for c in rule_concepts:
    ok, detail = definition_root(f"Explain {c['name']}.", str(c["ruleId"]))
    check(f"rule-concept definition {c['ruleId']} {c['name']}", ok, detail)

# Conservative morphology for section headings that are plural in the Core Rules.
for question, rid in [
    ("What does Recall do?", "454"),
    ("What does Chain do?", "327"),
    ("What does Triggered Ability do?", "382"),
    ("What does Passive Ability do?", "363"),
    ("What does Replacement Effect do?", "367"),
    ("What does Rune Pool do?", "165"),
]:
    ok, detail = definition_root(question, rid)
    check(f"singularized definition {question}", ok, detail)

# Parameterized keywords and player wording wrappers must still select the base keyword.
for question, rid in [
    ("What does Shield 2 do?", "814"),
    ("What does the Tank keyword do?", "815"),
]:
    ok, detail = definition_root(question, rid)
    check(f"parameter/wrapper definition {question}", ok, detail)

# Empower intentionally has two official meanings: Game Action 441 and Keyword 827.
emp = engine.ask("What does Empower do?")
emp_rules = {
    str(e.get("ruleId"))
    for outcome in emp["issues"][0]["ruling"].get("outcomes", [])
    for e in outcome.get("evidence", [])
    if e.get("ruleId")
}
check(
    "Empower do-definition preserves both official meanings",
    emp["issues"][0]["ruling"].get("status") == "decided" and {"441", "827"}.issubset(emp_rules),
    sorted(emp_rules),
)

# The new do-phrase path is exact-concept only. Scenario questions must never be
# converted into generic Unit/Spell definitions just because they use "what does ... do".
for q in [
    "What does my unit do after I play it?",
    "What does this spell do when it resolves?",
]:
    result = engine.ask(q)
    is_def = any(
        o.get("verdict") == "definition"
        for issue in result.get("issues", [])
        for o in issue.get("ruling", {}).get("outcomes", [])
    )
    check(f"scenario do-question not hijacked: {q}", not is_def, result.get("answer", ""))

out = {
    "passed": not failures,
    "checkCount": checks,
    "failureCount": len(failures),
    "metrics": {
        "keywordCount": len(keywords),
        "gameActionCount": len(game_actions),
        "ruleConceptCount": len(rule_concepts),
        "naturalDoPhraseCoverage": True,
        "singularPluralAliasCoverage": True,
        "proofVerifiedDefinitions": True,
        "scenarioFalsePositiveGuard": True,
    },
    "failures": failures,
}
(ROOT / "data/validation/definition_lookup_test_report.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(out, ensure_ascii=False, indent=2))
raise SystemExit(0 if not failures else 1)
