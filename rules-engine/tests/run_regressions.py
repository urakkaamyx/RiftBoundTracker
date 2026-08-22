#!/usr/bin/env python3
from pathlib import Path
import json, sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from riftkeep_rules.engine import RulesEngine

engine = RulesEngine(ROOT, require_current_authority=False)
cases = json.loads((ROOT / "tests/regression_cases.json").read_text(encoding="utf-8"))
failures = []
report = []
for case in cases:
    result = engine.ask(case["question"])
    checks = []
    for exp in case["expected"]:
        issue = result["issues"][exp["issue"]]
        ruling = issue["ruling"]
        ok = ruling["status"] == exp["status"]
        reasons = []
        if not ok:
            reasons.append(f"status {ruling['status']} != {exp['status']}")
        all_evidence = set(issue["retrieval"]["evidenceRuleIds"])
        missing = [r for r in exp.get("requiredRules", []) if r not in all_evidence]
        if missing:
            ok = False
            reasons.append(f"missing evidence {missing}")
        if "effectiveVerdict" in exp:
            got = (ruling.get("effectiveVerdict") or {}).get("verdict")
            if got != exp["effectiveVerdict"]:
                ok = False
                reasons.append(f"effective verdict {got} != {exp['effectiveVerdict']}")
        if "verdict" in exp:
            verdicts = [o.get("verdict") for o in ruling.get("outcomes", [])]
            if exp["verdict"] not in verdicts:
                ok = False
                reasons.append(f"verdict {exp['verdict']} not in {verdicts}")
        if "requiredCard" in exp:
            cards = {c["id"] for c in result.get("namedCards", [])}
            if exp["requiredCard"] not in cards:
                ok = False
                reasons.append(f"card {exp['requiredCard']} not resolved")
        if "requiredOfficialEvidence" in exp:
            official_ids = {str(x.get("evidenceId")) for x in issue.get("retrieval", {}).get("officialEvidence", []) if x.get("evidenceId")}
            missing_official = [eid for eid in exp.get("requiredOfficialEvidence", []) if eid not in official_ids]
            if missing_official:
                ok = False
                reasons.append(f"missing official evidence {missing_official}")
        checks.append({"passed": ok, "reasons": reasons})
        if not ok:
            failures.append({"case": case["name"], "reasons": reasons})
    report.append({"name": case["name"], "checks": checks, "answer": result["answer"]})

out = {"passed": not failures, "caseCount": len(cases), "failures": failures, "cases": report}
(ROOT / "data/validation/regression_report.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"passed": out["passed"], "caseCount": len(cases), "failureCount": len(failures), "failures": failures}, indent=2))
raise SystemExit(0 if not failures else 1)
