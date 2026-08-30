"""Re-run a random sample of the SEMANTIC_MISROUTE bucket through the live (fixed) engine to
measure real impact of build_definition_ruling_from_retrieval, before touching more of the
80,000-case corpus."""
import csv
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, "src")
from riftkeep_rules.engine import RulesEngine

csv.field_size_limit(2**31 - 1)

ROOT = Path(__file__).parent
CORPUS = ROOT / "data" / "corpus_law" / "strict_rules" / "semantic_misroutes.csv"

random.seed(42)
with open(CORPUS, encoding="utf-8", newline="") as f:
    rows = list(csv.DictReader(f))
sample = random.sample(rows, 300)

engine = RulesEngine(ROOT, require_current_authority=False)

now_definition = 0
now_still_insufficient = 0
now_other = 0
examples_fixed = []
examples_still_broken = []

for row in sample:
    result = engine.ask(row["question"])
    issue = result["issues"][0]
    status = issue["ruling"].get("status")
    verdict = (issue["ruling"].get("effectiveVerdict") or {}).get("verdict")
    if verdict == "definition":
        now_definition += 1
        if len(examples_fixed) < 5:
            examples_fixed.append({"caseId": row["caseId"], "question": row["question"][:150]})
    elif status == "insufficient":
        now_still_insufficient += 1
        if len(examples_still_broken) < 5:
            examples_still_broken.append({"caseId": row["caseId"], "question": row["question"][:150]})
    else:
        now_other += 1

print(f"Sample size: {len(sample)}")
print(f"Now resolved via definition lookup: {now_definition} ({now_definition/len(sample)*100:.1f}%)")
print(f"Still insufficient: {now_still_insufficient} ({now_still_insufficient/len(sample)*100:.1f}%)")
print(f"Other (adjudicated some other way): {now_other} ({now_other/len(sample)*100:.1f}%)")
print("\nSample fixed:")
for e in examples_fixed:
    print(" ", e)
print("\nSample still broken:")
for e in examples_still_broken:
    print(" ", e)
