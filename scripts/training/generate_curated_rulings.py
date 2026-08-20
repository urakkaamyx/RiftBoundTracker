"""
Builds src/RiftBoundTracker.App/App_Data/CuratedRulings.json — a hand-verified + community-FAQ-
sourced lookup table of real rules rulings, each with an already-correct, already-readable answer.

Why this exists: four rounds of fine-tuning Qwen3-1.7B on the adjudicate/explain task shape showed
the model's RULING quality (not just its output format) is inconsistent — the same directly-trained
fact could come out correct or hedge into "insufficient evidence" depending on the run, and fixing
one failure tended to shuffle in a different one elsewhere rather than shrinking the failure count.
For the class of questions this file covers (a bounded, curatable set of real player questions), the
model doesn't need to DECIDE the ruling — it already IS decided, verified against the real rules
corpus or by riftboundfaq.com's community. RulesAnswerService checks this table first; only a
question that doesn't match anything here reaches the LLM-driven adjudicate/explain pipeline at all.

Two sources, both already-verified:
1. Hand-verified interaction rulings (imported from generate_adjudication_dataset.py's RULING_CASES)
   — the same facts checked directly against the corpus this session, now serving as ground truth
   at INFERENCE time, not just as training data.
2. riftboundfaq.com (CC BY-SA 4.0) — real community Q&A with precise rule citations, covering 47
   card-specific pages and 13 general-rules/mechanics pages. Its own answer text ships directly as
   the explanation; it's already correct, cited, and readable — no LLM rewrite needed.

Keyword tags (auto-derived via RuleEntryKeywords for FAQ entries, hand-set for RULING_CASES) let
the C# matcher require topical alignment with the question's own detected keywords, not just prose
similarity — a stricter bar than training data needs, since a false-positive match here would serve
a confidently wrong answer with no LLM in the loop to hedge.
"""
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_dataset import fetch_faq_mdx, parse_faq_mdx  # noqa: E402
from generate_adjudication_dataset import RULING_CASES, DESCRIPTIVE_CASES, INSUFFICIENT_CASES  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "src" / "RiftBoundTracker.App" / "App_Data" / "riftbound.db"
# NOT App_Data — that directory is <Content Remove="App_Data/**" /> in the csproj (runtime-only:
# db, images, keys, none of it ships in the build). This needs to actually ship with the app, so it
# lives in RulesData/ instead, with an explicit CopyToOutputDirectory entry in the csproj (same
# pattern already used there for "Run with debug console.bat").
OUT_PATH = REPO_ROOT / "src" / "RiftBoundTracker.App" / "RulesData" / "CuratedRulings.json"

FAQ_PAGES = [
    "general-rules/abilities.mdx", "general-rules/chain-and-priority.mdx",
    "general-rules/costs-and-payments.mdx", "general-rules/movement.mdx",
    "general-rules/playing-cards.mdx", "general-rules/showdowns.mdx", "general-rules/targeting.mdx",
    "mechanics/ambush.mdx", "mechanics/deathknell.mdx", "mechanics/empower.mdx",
    "mechanics/equipment.mdx", "mechanics/flow.mdx", "mechanics/repeat.mdx",
    "cards/abandoned-hall.mdx", "cards/akshan-mischievous.mdx", "cards/alpha-strike.mdx",
    "cards/aphelios-exalted.mdx", "cards/applied-researchers.mdx", "cards/arcane-shift.mdx",
    "cards/astral-heron.mdx", "cards/azir-sovereign.mdx", "cards/baited-hook.mdx",
    "cards/baron-nashor.mdx", "cards/bone-skewer.mdx", "cards/brynhir-thundersong.mdx",
    "cards/call-to-battle.mdx", "cards/consuming-curse.mdx", "cards/diana-lunari.mdx",
    "cards/emperors-dais.mdx", "cards/endless-riches.mdx", "cards/ezreal-prodigy.mdx",
    "cards/fallen-feline.mdx", "cards/flash.mdx", "cards/gangplank-naval.mdx",
    "cards/glasc-mixologist.mdx", "cards/heedless-resurrection.mdx", "cards/hidden-blade.mdx",
    "cards/irelia-fervent.mdx", "cards/irresistible-faefolk.mdx", "cards/karthus-eternal.mdx",
    "cards/kennen-storm-of-shuriken.mdx", "cards/khazix-mutating-horror.mdx", "cards/lacerate.mdx",
    "cards/lilting-lullaby.mdx", "cards/lotus-trap.mdx", "cards/lux-crownguard.mdx",
    "cards/nocturne-horrifying.mdx", "cards/promising-future.mdx", "cards/rebuttal.mdx",
    "cards/ruined-rex.mdx", "cards/sacrifice.mdx", "cards/shadow-assassin.mdx",
    "cards/shadowblade-lurker.mdx", "cards/shady-spectacles.mdx", "cards/smite.mdx",
    "cards/sunken-temple.mdx", "cards/switcheroo.mdx", "cards/temporal-breach.mdx",
    "cards/thrill-of-the-hunt.mdx", "cards/vex-apathetic.mdx", "cards/vex-cheerless.mdx",
]

FAQ_ATTRIBUTION = (
    "riftboundfaq.com by Christian I. (Near) and contributors, CC BY-SA 4.0, "
    "https://github.com/ChristianIvicevic/riftboundfaq"
)
FAQ_MAX_ANSWER_CHARS = 1200


def keywords_for_rule_numbers(cur, rule_numbers):
    """Auto-derives official keyword tags for a set of cited rule numbers via RuleEntryKeywords —
    lets FAQ entries require topical alignment with the question's own detected keywords without
    hand-tagging 159 entries individually."""
    names = set()
    for number in rule_numbers:
        cur.execute("""
            SELECT rk.Name FROM RuleEntries re
            JOIN RuleEntryKeywords rek ON rek.RuleEntryId = re.Id
            JOIN RuleKeywords rk ON rk.Id = rek.KeywordId
            WHERE re.RuleNumber = ? AND re.IsCurrent = 1
        """, (number,))
        names.update(row[0] for row in cur.fetchall())
    return sorted(names)


def infer_answer(cleaned_text):
    lower = cleaned_text.strip().lower()
    if re.match(r"^yes\b", lower):
        return "Yes"
    if re.match(r"^no\b", lower):
        return "No"
    return "Yes"  # descriptive/informational answer, not phrased as a yes/no ruling


def build_from_ruling_cases():
    entries = []
    for i, case in enumerate(RULING_CASES):
        entries.append({
            "id": f"ruling-{i}",
            "source": "hand-verified",
            "paraphrases": case["questions"],
            "ruleNumbers": case["rule_numbers"],
            "answer": case["answer"],
            "explanation": case["explanation"],
        })
    return entries


def build_from_descriptive_cases():
    entries = []
    for i, case in enumerate(DESCRIPTIVE_CASES):
        entries.append({
            "id": f"descriptive-{i}",
            "source": "hand-verified",
            "paraphrases": case["questions"],
            "ruleNumbers": case["rule_numbers"],
            "answer": "Yes",
            "explanation": case["explanation"],
        })
    return entries


def build_from_insufficient_cases():
    entries = []
    for i, case in enumerate(INSUFFICIENT_CASES):
        rule_number, _title = case["evidence_topic"]
        entries.append({
            "id": f"insufficient-{i}",
            "source": "hand-verified",
            "paraphrases": case["questions"],
            "ruleNumbers": [rule_number],
            "answer": "Insufficient",
            "explanation": case["explanation"],
        })
    return entries


def build_from_faq(cur):
    entries = []
    skipped_no_evidence = 0
    skipped_too_long = 0
    for path in FAQ_PAGES:
        try:
            raw = fetch_faq_mdx(path)
        except Exception as ex:
            print(f"  skip page (fetch failed): {path} — {ex}")
            continue
        for question, answer, rule_numbers in parse_faq_mdx(raw):
            if len(answer) > FAQ_MAX_ANSWER_CHARS:
                skipped_too_long += 1
                continue
            resolved_numbers = []
            for number in rule_numbers:
                cur.execute("SELECT 1 FROM RuleEntries WHERE RuleNumber = ? AND IsCurrent = 1", (number,))
                if cur.fetchone():
                    resolved_numbers.append(number)
            if not resolved_numbers:
                skipped_no_evidence += 1
                continue
            entries.append({
                "id": f"faq-{path}-{len(entries)}",
                "source": "riftboundfaq.com",
                "paraphrases": [question],
                "ruleNumbers": resolved_numbers,
                "answer": infer_answer(answer),
                "explanation": answer.strip() + f"\n\n(Source: {FAQ_ATTRIBUTION})",
                "keywords": keywords_for_rule_numbers(cur, resolved_numbers),
            })
    print(f"  FAQ: {len(entries)} entries ({skipped_no_evidence} skipped: no citation resolved, "
          f"{skipped_too_long} skipped: answer too long)")
    return entries


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    print("Hand-verified rulings...")
    ruling_entries = build_from_ruling_cases()
    print(f"  {len(ruling_entries)} entries")

    print("Hand-verified descriptive questions...")
    descriptive_entries = build_from_descriptive_cases()
    print(f"  {len(descriptive_entries)} entries")

    print("Hand-verified insufficient-evidence calibration...")
    insufficient_entries = build_from_insufficient_cases()
    print(f"  {len(insufficient_entries)} entries")

    for entry in ruling_entries + descriptive_entries + insufficient_entries:
        entry["keywords"] = keywords_for_rule_numbers(cur, entry["ruleNumbers"])

    print("Community FAQ (riftboundfaq.com)...")
    faq_entries = build_from_faq(cur)

    all_entries = ruling_entries + descriptive_entries + insufficient_entries + faq_entries
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_entries, f, ensure_ascii=False, indent=2)

    print(f"\nWrote {len(all_entries)} curated rulings to {OUT_PATH}")


if __name__ == "__main__":
    main()
