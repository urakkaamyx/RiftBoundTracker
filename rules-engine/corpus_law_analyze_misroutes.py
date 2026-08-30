"""Diagnostic pass over the RiftKeep_Corpus_Checkpoint_80000 SEMANTIC_MISROUTE bucket.

Quantifies:
  1. How many rows are the degenerate "echo" pattern - the corpus phrased a rule's own
     text as a question ("The situation involves this rule concept: <TEXT>. How is that
     supposed to work?") and set expectedAnswer to that same <TEXT> verbatim. These aren't
     real adjudication obligations; the engine's "insufficient" response may be structurally
     correct, just routed through the wrong subsystem (should be a direct rule-text lookup,
     not the strict-rules proof pipeline).
  2. For the echo-pattern rows, whether the *quoted* rule text actually matches the official
     compiled core_rules.json text for the cited ruleId - confirms whether the corpus itself
     is accurately derived from the real official PDF (per the user's expectation) before we
     trust it as the signal to fix routing against.
  3. A sample of non-echo rows (genuine free-form expected answers) for manual review -
     these are the ones that might indicate real proof/compilation gaps, not just routing.
"""
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
CORPUS = ROOT / "data" / "corpus_law" / "strict_rules" / "semantic_misroutes.csv"
CORE_RULES = ROOT / "data" / "canonical" / "core_rules.json"

csv.field_size_limit(2**31 - 1)

with open(CORE_RULES, encoding="utf-8") as f:
    rules_by_id = {r["ruleId"]: r for r in json.load(f)["rules"]}

def normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().rstrip(".").lower()

total = 0
echo_pattern = 0
echo_matches_official = 0
echo_mismatches_official = []
non_echo_samples = []

with open(CORPUS, encoding="utf-8", newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        total += 1
        question = row["question"]
        expected = row["expectedAnswer"]
        rule_ids = [r.strip() for r in row["ruleIds"].split(";") if r.strip()] if row.get("ruleIds") else []

        is_echo = normalize(expected) in normalize(question)
        if is_echo:
            echo_pattern += 1
            if rule_ids:
                official = rules_by_id.get(rule_ids[0])
                if official:
                    off_text = normalize(official.get("normativeText") or official.get("text") or "")
                    if normalize(expected) == off_text or normalize(expected) in off_text or off_text in normalize(expected):
                        echo_matches_official += 1
                    else:
                        if len(echo_mismatches_official) < 15:
                            echo_mismatches_official.append({
                                "caseId": row["caseId"], "ruleId": rule_ids[0],
                                "expected": expected, "official": official.get("normativeText") or official.get("text"),
                            })
        else:
            if len(non_echo_samples) < 20:
                non_echo_samples.append({
                    "caseId": row["caseId"], "ruleIds": rule_ids,
                    "question": question[:200], "expected": expected[:300], "engine": row["engineAnswer"][:300],
                })

print(f"Total SEMANTIC_MISROUTE rows: {total}")
print(f"Echo pattern (expected == embedded rule text in question): {echo_pattern} ({echo_pattern/total*100:.1f}%)")
print(f"  of those, expected text matches official core_rules.json for cited rule: {echo_matches_official} ({echo_matches_official/echo_pattern*100:.1f}% of echo rows)" if echo_pattern else "")
print(f"Non-echo (genuine free-form expected answer): {total - echo_pattern} ({(total-echo_pattern)/total*100:.1f}%)")

print("\n=== Sample echo-pattern MISMATCHES against official text (corpus may be wrong here) ===")
for r in echo_mismatches_official:
    print(json.dumps(r, indent=2, ensure_ascii=False))

print("\n=== Sample NON-echo rows (potential genuine engine gaps) ===")
for r in non_echo_samples[:10]:
    print(json.dumps(r, indent=2, ensure_ascii=False))
