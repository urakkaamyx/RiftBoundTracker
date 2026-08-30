"""Quantify the 'How do Core Rules X and Y work together...Parent rule: <parent text>' template
across all strict_rules failure CSVs - is it a large, tractable pattern like the others?"""
import csv
import re
from pathlib import Path

csv.field_size_limit(2**31 - 1)
ROOT = Path(__file__).parent
FILES = [
    "wrong_verdicts.csv", "semantic_misroutes.csv", "clarification_failures.csv",
    "coverage_gaps.csv", "irrelevant_proofs.csv",
]

PATTERN = re.compile(r"How do Core Rules? [\d.]+ and [\d.]+ work together", re.I)
EXPECTED_PATTERN = re.compile(r"^Rule [\d.]+ is a direct subrule of Rule [\d.]+\.", re.I)

for fname in FILES:
    path = ROOT / "data" / "corpus_law" / "strict_rules" / fname
    if not path.exists():
        continue
    total = 0
    matches = 0
    expected_matches_template = 0
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            total += 1
            if PATTERN.search(row["question"]):
                matches += 1
                if EXPECTED_PATTERN.match(row["expectedAnswer"]):
                    expected_matches_template += 1
    print(f"{fname}: {matches}/{total} match parent-child template ({matches/total*100:.1f}%), {expected_matches_template} confirm the exact expected-answer shape")
