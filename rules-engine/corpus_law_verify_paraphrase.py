"""Check the hypothesis: in the non-exact-quote SEMANTIC_MISROUTE rows, the corpus systematically
swaps only the rule's LEADING word (If/When/etc -> Suppose), with everything after that first
word matching verbatim. If true, stripping the first word from both sides before the substring
check is a safe, narrow extension - not a fuzzy/similarity guess, just tolerating one known
systematic templating substitution."""
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
    return re.sub(r"\s+", " ", (s or "").replace("’", "'")).strip().rstrip(".").casefold()

def strip_first_word(s: str) -> str:
    parts = s.split(" ", 1)
    return parts[1] if len(parts) > 1 else s

total = 0
exact_echo = 0
first_word_swap_match = 0
neither = 0
neither_samples = []

with open(CORPUS, encoding="utf-8", newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        total += 1
        question = row["question"]
        rule_ids = [r.strip() for r in row["ruleIds"].split(";") if r.strip()] if row.get("ruleIds") else []
        if not rule_ids:
            continue
        official = rules_by_id.get(rule_ids[0])
        if not official:
            continue
        text = official.get("normativeText") or official.get("text") or ""
        if len(text.strip()) < 40:
            continue
        nq, nt = normalize(question), normalize(text)
        if nt in nq:
            exact_echo += 1
        elif strip_first_word(nt) in nq and len(strip_first_word(nt)) > 30:
            first_word_swap_match += 1
        else:
            neither += 1
            if len(neither_samples) < 10:
                neither_samples.append({"caseId": row["caseId"], "ruleId": rule_ids[0], "question": question[:200], "official": text[:200]})

print(f"Total rows with a cited rule >=40 chars: {exact_echo + first_word_swap_match + neither}")
print(f"Exact verbatim quote (already handled): {exact_echo}")
print(f"First-word-swap match (new candidate fix): {first_word_swap_match}")
print(f"Neither (genuinely different / needs other work): {neither}")
print("\nSample 'neither' rows:")
for s in neither_samples:
    print(json.dumps(s, indent=2, ensure_ascii=False))
