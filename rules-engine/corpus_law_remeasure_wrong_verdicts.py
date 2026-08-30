import csv
import random
import sys
from pathlib import Path

sys.path.insert(0, "src")
from riftkeep_rules.engine import RulesEngine

csv.field_size_limit(2**31 - 1)

ROOT = Path(__file__).parent
CORPUS = ROOT / "data" / "corpus_law" / "strict_rules" / "wrong_verdicts.csv"

random.seed(42)
with open(CORPUS, encoding="utf-8", newline="") as f:
    rows = list(csv.DictReader(f))
sample = random.sample(rows, min(300, len(rows)))

engine = RulesEngine(ROOT, require_current_authority=False)

now_definition = 0
now_insufficient = 0
now_other = 0
other_examples = []

for row in sample:
    result = engine.ask(row["question"])
    issue = result["issues"][0]
    status = issue["ruling"].get("status")
    verdict = (issue["ruling"].get("effectiveVerdict") or {}).get("verdict")
    if verdict == "definition":
        now_definition += 1
    elif status == "insufficient":
        now_insufficient += 1
    else:
        now_other += 1
        if len(other_examples) < 8:
            other_examples.append({
                "caseId": row["caseId"], "verdict": verdict,
                "question": row["question"][:150], "expected": row["expectedAnswer"][:150],
                "engineWas": row["engineAnswer"][:150],
            })

print(f"Sample size: {len(sample)}")
print(f"Now resolved via definition lookup: {now_definition} ({now_definition/len(sample)*100:.1f}%)")
print(f"Now insufficient: {now_insufficient} ({now_insufficient/len(sample)*100:.1f}%)")
print(f"Other (non-definition verdict, still possibly wrong): {now_other} ({now_other/len(sample)*100:.1f}%)")
print("\nSample 'other' rows:")
import json
for e in other_examples:
    print(json.dumps(e, indent=2, ensure_ascii=False))
