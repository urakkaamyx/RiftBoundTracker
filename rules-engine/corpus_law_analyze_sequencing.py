"""Quantify the 'I plan to resolve CardA and then CardB in the same turn. CardA currently reads:
"..." ' template within clarification_failures.csv - does the corpus's expectedAnswer for these
really just want a card-text/keyword explanation (not a resolved interaction ruling)?"""
import csv
import re
from pathlib import Path

csv.field_size_limit(2**31 - 1)
ROOT = Path(__file__).parent
CORPUS = ROOT / "data" / "corpus_law" / "strict_rules" / "clarification_failures.csv"

PATTERN = re.compile(r"^I plan to resolve .+ and then .+ in the same turn\.", re.I)

total = 0
matches_template = 0
expected_is_pure_explanation = 0
sample = []

with open(CORPUS, encoding="utf-8", newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        total += 1
        q = row["question"]
        if PATTERN.match(q):
            matches_template += 1
            expected = row["expectedAnswer"]
            if re.match(r"^[\w \-,'()]+ uses [\w \-]+\. Its current effective text is:", expected):
                expected_is_pure_explanation += 1
                if len(sample) < 3:
                    sample.append({"caseId": row["caseId"], "engine": row["engineAnswer"][:200]})

print(f"Total clarification_failures rows: {total}")
print(f"Match 'I plan to resolve A and then B' template: {matches_template} ({matches_template/total*100:.1f}%)")
print(f"  of those, expected is pure 'CardX uses Keyword. Its effective text is...' explanation: {expected_is_pure_explanation}")
print()
import json
for s in sample:
    print(json.dumps(s, indent=2, ensure_ascii=False))
