"""
Generates a LoRA fine-tuning dataset for the Ask Rules local model, built entirely from the real
synced Riftbound rules corpus (via the running app's own API — the exact same evidence-gathering
and prompt-formatting code paths used at inference time, so training and inference distributions
match). Categories:

  1. Direct rule-number lookups (templated answer — correct by construction)
  2. Keyword "how does X work" questions (self-distilled: real answer from the already-verified
     RAG pipeline, captured as a training target)
  3. Concept-based natural-language questions (self-distilled)
  4. Errata questions (templated)
  5. Legality questions (templated), plus 5b. multi-format legality questions (a card with more
     than one format's status supplied together, so the model learns to answer the SPECIFIC format
     asked instead of picking whichever fact comes first in the evidence)
  6. Insufficient-evidence / off-topic questions (templated honest refusal) — critical: without
     this category, fine-tuning could erode the model's willingness to say "I don't know."

Usage: start the app (`dotnet run`) with a synced Rules library, enable local AI in Settings so
categories 2/3 can self-distill, then run this script. See README.md in this folder for the full
retrain/convert/quantize/host workflow.

Output: JSONL, one {"messages": [...]} chat example per line, matching the exact system prompt
and user-message shape LocalLlmExplanationProvider.cs uses at inference time.
"""
import json
import random
import sqlite3
import urllib.request
from pathlib import Path

random.seed(42)

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "src" / "RiftBoundTracker.App" / "App_Data" / "riftbound.db"
API_BASE = "http://localhost:5099"
OUT_DIR = Path(__file__).resolve().parent / "output"
OUT_PATH = OUT_DIR / "dataset.jsonl"

SYSTEM_PROMPT = (
    "You are a rules-reference assistant for the Riftbound trading card game. Answer only from\n"
    "the official rules evidence supplied below. If the evidence does not clearly establish the\n"
    "answer, say so plainly instead of guessing. Never invent a ruling that isn't supported by\n"
    "the evidence. Prefer current Core Rules over Tournament Rules, errata, or historical\n"
    "material when they overlap. Clearly distinguish what a rule directly says from any\n"
    "interpretation you're making. Keep the answer concise — a few sentences, not an essay."
)


def api(path, method="GET", body=None):
    url = API_BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                  headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def set_local_ai(enabled):
    api("/api/rules/local-ai/configure", "POST", {"enabled": enabled})


def build_evidence_text(sources):
    parts = []
    for s in sources:
        label = f"Rule {s['ruleNumber']}" if s.get("ruleNumber") else s["title"]
        authority_note = s["authority"] + ("" if s["current"] else ", historical")
        parts.append(f"[{label}] ({authority_note}) {s['title']}\n{s['snippet']}")
    return "\n\n".join(parts)


def build_user_message(question, sources, card_names=None):
    card_text = ""
    if card_names:
        card_text = "\n\nThe question is specifically about this card: " + ", ".join(card_names)
    return f"Question: {question}{card_text}\n\nRules evidence:\n{build_evidence_text(sources)}"


def make_example(question, sources, answer, card_names=None):
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_message(question, sources, card_names)},
            {"role": "assistant", "content": answer},
        ]
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    examples = []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    print("Category 1: direct rule-number lookups...")
    cur.execute("SELECT RuleNumber, Title, Text FROM RuleEntries WHERE IsCurrent = 1 AND RuleNumber IS NOT NULL")
    all_rules = cur.fetchall()
    sample_rules = random.sample(all_rules, min(150, len(all_rules)))
    for row in sample_rules:
        number, text = row["RuleNumber"], row["Text"]
        question = random.choice([
            f"What does rule {number} say?", f"What does Rule {number} mean?", f"Can you explain rule {number}?",
        ])
        source = {"ruleNumber": number, "title": row["Title"] or f"Rule {number}", "authority": "CoreRules",
                  "current": True, "snippet": text[:220]}
        examples.append(make_example(question, [source], f"Rule {number} states: {text}"))
    print(f"  {len(sample_rules)} examples")

    print("Category 2: keyword questions (self-distilled, calls the live model)...")
    set_local_ai(True)
    cur.execute("SELECT Id, Name FROM RuleKeywords")
    keywords = cur.fetchall()
    keyword_templates = ["How does {kw} work?", "What is {kw}?", "Explain {kw}.", "What does {kw} mean in Riftbound?"]
    count2 = 0
    for kw in keywords:
        question = random.choice(keyword_templates).format(kw=kw["Name"])
        try:
            result = api("/api/rules/ask", "POST", {"question": question})
        except Exception as ex:
            print(f"  skip (error): {question} — {ex}")
            continue
        if not result.get("answerGenerated") or not result.get("sources"):
            print(f"  skip (no answer/evidence): {question}")
            continue
        examples.append(make_example(question, result["sources"], result["answer"]))
        count2 += 1
        print(f"  [{count2}/{len(keywords)}] {question}")
    print(f"  {count2} examples")

    print("Category 3: concept-based natural questions (self-distilled)...")
    concept_questions = [
        "What happens when my unit dies at a battlefield?",
        "Can I remove a unit from combat instead of recycling it?",
        "How does control of a battlefield work?",
        "What does it mean for a card to be hidden?",
        "How do I win a fight during combat?",
        "When do triggered abilities go off?",
        "How does resolving the chain work?",
        "Can I move a unit to another battlefield during ganking?",
        "What are the rules for tapping and untapping cards?",
        "How do I build a legal deck around my Champion Legend?",
        "How does healing work in Riftbound?",
        "What happens if a unit is stunned?",
        "Can I exhaust a unit that is already exhausted?",
        "What does it mean when a card is banished?",
        "How does the Domain Identity of my deck get determined?",
    ]
    count3 = 0
    for question in concept_questions:
        try:
            result = api("/api/rules/ask", "POST", {"question": question})
        except Exception as ex:
            print(f"  skip (error): {question} — {ex}")
            continue
        if not result.get("answerGenerated") or not result.get("sources"):
            print(f"  skip (no answer/evidence): {question}")
            continue
        examples.append(make_example(question, result["sources"], result["answer"]))
        count3 += 1
        print(f"  [{count3}/{len(concept_questions)}] {question}")
    print(f"  {count3} examples")
    set_local_ai(False)

    print("Category 4: errata questions...")
    cur.execute("""
        SELECT ce.CardNameRaw, ce.OriginalText, ce.CorrectedText, rd.Title as DocTitle
        FROM CardErrata ce JOIN RuleDocuments rd ON ce.DocumentId = rd.Id
        WHERE ce.IsCurrent = 1
    """)
    errata_rows = cur.fetchall()
    for row in errata_rows:
        name, original, corrected, doc_title = row["CardNameRaw"], row["OriginalText"], row["CorrectedText"], row["DocTitle"]
        question = random.choice([
            f"Has {name} received any errata?", f"What was {name}'s original text before errata?", f"Did {name}'s card text change?",
        ])
        source = {"ruleNumber": None, "title": name, "authority": "OfficialErrata", "current": True,
                  "snippet": f"Original: {original}\nUpdated: {corrected}"}
        answer = (
            f"Yes — {name} received official errata ({doc_title}). "
            f"The original text was: \"{original}\" It was updated to: \"{corrected}\""
        )
        examples.append(make_example(question, [source], answer, card_names=[name]))
    print(f"  {len(errata_rows)} examples")

    print("Category 5: legality questions...")
    legality_status_names = ["Legal", "Banned", "Restricted", "NotLegal"]
    cur.execute("SELECT CardId, CardNameRaw, Format, Status FROM CardLegalities WHERE IsCurrent = 1 AND CardId IS NOT NULL")
    legality_rows = cur.fetchall()

    def legality_answer(name, fmt, status):
        verb = "is not legal (banned)" if status.lower() == "banned" else f"is {status.lower()}"
        return f"{name} {verb} in {fmt}."

    for row in legality_rows:
        name, fmt, status = row["CardNameRaw"], row["Format"], legality_status_names[row["Status"]]
        question = random.choice([
            f"Is {name} banned in {fmt}?", f"Can I play {name} in {fmt}?", f"What is {name}'s legality status in {fmt}?",
        ])
        source = {"ruleNumber": None, "title": name, "authority": "CoreRules", "current": True,
                  "snippet": f"{name} is {status} in {fmt}."}
        examples.append(make_example(question, [source], legality_answer(name, fmt, status), card_names=[name]))
    print(f"  {len(legality_rows)} examples")

    print("Category 5b: multi-format legality questions...")
    by_card = {}
    for row in legality_rows:
        by_card.setdefault(row["CardId"], []).append(row)
    count5b = 0
    for card_id, rows in by_card.items():
        if len(rows) < 2:
            continue
        name = rows[0]["CardNameRaw"]
        sources = [{"ruleNumber": None, "title": name, "authority": "CoreRules", "current": True,
                    "snippet": f"{name} is {legality_status_names[r['Status']]} in {r['Format']}."} for r in rows]
        for target in rows:
            fmt, status = target["Format"], legality_status_names[target["Status"]]
            question = random.choice([
                f"Is {name} banned in {fmt} specifically?", f"What is {name}'s legality in {fmt}?", f"Can I play {name} in {fmt}?",
            ])
            others = ", ".join(f"{legality_status_names[r['Status']]} in {r['Format']}" for r in rows if r is not target)
            answer = legality_answer(name, fmt, status)
            if others:
                answer += f" (It is also {others}.)"
            examples.append(make_example(question, sources, answer, card_names=[name]))
            count5b += 1
    print(f"  {count5b} examples")

    print("Category 6: insufficient-evidence / off-topic questions...")
    off_topic_questions = [
        "What's the weather like today?", "How do I cook pasta?", "What is the capital of France?",
        "Can you recommend a good movie?", "How much does a booster pack cost?",
        "When is the next Riftbound set releasing?", "Who is the best player in the world?", "What's your favorite card?",
    ]
    random_rules_for_padding = random.sample(all_rules, len(off_topic_questions))
    for question, padding in zip(off_topic_questions, random_rules_for_padding):
        source = {"ruleNumber": padding["RuleNumber"], "title": padding["Title"] or f"Rule {padding['RuleNumber']}",
                  "authority": "CoreRules", "current": True, "snippet": padding["Text"][:220]}
        answer = (
            "I don't have official Riftbound rules evidence that addresses this question — it's "
            "outside what I can answer from the rules library. I can only answer questions about "
            "Riftbound's official rules, keywords, errata, and card legality."
        )
        examples.append(make_example(question, [source], answer))
    print(f"  {len(off_topic_questions)} examples")

    random.shuffle(examples)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"\nTotal examples: {len(examples)}")
    print(f"Written to: {OUT_PATH}")


if __name__ == "__main__":
    main()
