import csv
import sys
from pathlib import Path

sys.path.insert(0, "src")
from riftkeep_rules.engine import RulesEngine

csv.field_size_limit(2**31 - 1)
ROOT = Path(__file__).parent

engine = RulesEngine(ROOT, require_current_authority=False)

for fname in ["wrong_verdicts.csv", "clarification_failures.csv", "coverage_gaps.csv"]:
    path = ROOT / "data" / "corpus_law" / "strict_rules" / fname
    rows = []
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if "work together" in row["question"]:
                rows.append(row)
    resolved = 0
    for row in rows:
        result = engine.ask(row["question"])
        issue = result["issues"][0]
        verdict = (issue["ruling"].get("effectiveVerdict") or {}).get("verdict")
        if verdict == "definition":
            resolved += 1
    print(f"{fname}: {resolved}/{len(rows)} parent-child cases now resolve via definition")
