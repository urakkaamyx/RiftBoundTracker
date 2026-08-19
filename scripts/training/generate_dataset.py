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
  7. Card ability questions (templated) — a card's OWN printed text supplied as evidence, the way
     RulesEvidenceService.FindCardEvidenceAsync surfaces it for a free-text name match. Deliberately
     weighted toward cards whose text uses the "[Keyword] (reminder text)" bracket pattern (roughly
     44% of the catalog, e.g. "[Accelerate] (You may pay 1 Energy and a Fury Rune as an additional
     cost to have me enter ready.)") — this exact shape was never in the dataset before and it
     showed: verified directly against a real deployed model that a card whose ONLY evidence was one
     bracket-keyword block made it echo its own system prompt back as the "answer" instead of
     describing the card, and a second, narrower prompt-only fix for that made a DIFFERENT card
     (Draven - Vanquisher) worse — regressed to skipping its real ability and fabricating a rule
     citation that doesn't exist. A prompt tweak alone couldn't fix this reliably; the model needs
     to have actually seen this evidence shape during fine-tuning.

IMPORTANT — keep this file's evidence formatting a faithful mirror of the C# it's training the
model to match, not merely "close enough": LocalLlmExplanationProvider.cs's BuildUserMessage is the
actual inference-time prompt builder. Every constant and format string below (SYSTEM_PROMPT,
PER_ITEM_CAP, TOTAL_BUDGET, the "[Label] (Authority) Title\nText" evidence shape) must match it
exactly, or the model is being fine-tuned against a prompt distribution it will never actually see
at inference time — which is worse than not fine-tuning on that behavior at all, since it teaches
the model habits that don't transfer. If you change BuildUserMessage's prompt construction, update
the matching constants/functions here in the same change.

Usage: start the app (`dotnet run`) with a synced Rules library, enable local AI in Settings so
categories 2/3 can self-distill, then run this script. See README.md in this folder for the full
retrain/convert/quantize/host workflow.

Output: JSONL, one {"messages": [...]} chat example per line, matching the exact system prompt
and user-message shape LocalLlmExplanationProvider.cs uses at inference time.
"""
import json
import os
import random
import re
import sqlite3
import urllib.request
from pathlib import Path

random.seed(42)

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "src" / "RiftBoundTracker.App" / "App_Data" / "riftbound.db"
# Override with RIFTKEEP_API_PORT when testing against an isolated dev instance on a non-default
# port (e.g. 5199) instead of a real running install on 5080 — this script calls
# /api/rules/local-ai/configure, which flips a real setting, so never point it at an app instance
# you don't want mutated.
API_BASE = f"http://localhost:{os.environ.get('RIFTKEEP_API_PORT', '5080')}"
OUT_DIR = Path(__file__).resolve().parent / "output"
OUT_PATH = OUT_DIR / "dataset.jsonl"

# Mirrors LocalLlmExplanationProvider.cs's SystemPrompt constant exactly.
SYSTEM_PROMPT = (
    "You are a rules-reference assistant for the Riftbound trading card game. Answer only from\n"
    "the official rules evidence supplied below. If the evidence does not clearly establish the\n"
    "answer, say so plainly instead of guessing. Never invent a ruling that isn't supported by\n"
    "the evidence. Prefer current Core Rules over Tournament Rules, errata, or historical\n"
    "material when they overlap. Clearly distinguish what a rule directly says from any\n"
    "interpretation you're making. Keep the answer concise — a few sentences, not an essay.\n"
    "A card's own printed text is valid evidence of what that card does — if it's supplied below,\n"
    "describe the card's effect directly instead of calling the evidence insufficient."
)

# Mirrors BuildUserMessage's Cap/perItemCap/totalBudget exactly — see LocalLlmExplanationProvider.cs.
PER_ITEM_CAP = 900
TOTAL_BUDGET = 5500

BRACKET_KEYWORD_RE = re.compile(r"\[([A-Za-z][A-Za-z\s\-]*)\]")

_symbol_map = None


def api(path, method="GET", body=None):
    url = API_BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                  headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def set_local_ai(enabled):
    api("/api/rules/local-ai/configure", "POST", {"enabled": enabled})


def get_symbol_map():
    """Mirrors CardTextSymbolCatalogService.HumanizeAsync — fetched from the live API rather than
    duplicated by hand so this can never silently drift from the real token/label catalog."""
    global _symbol_map
    if _symbol_map is None:
        symbols = api("/api/card-text-symbols")
        _symbol_map = [(s["token"], s["label"]) for s in symbols]
    return _symbol_map


def humanize(text):
    if not text:
        return text
    for token, label in get_symbol_map():
        text = text.replace(token, label)
    return text


def cap(text, max_chars):
    return text if len(text) <= max_chars else text[:max_chars] + "…"


def build_evidence_text(sources):
    """Mirrors BuildUserMessage's evidenceParts + running total-budget truncation exactly."""
    used = 0
    parts = []
    for s in sources:
        label = f"Rule {s['ruleNumber']}" if s.get("ruleNumber") else s["title"]
        authority_note = s["authority"] + ("" if s["current"] else ", historical")
        text = cap(s["text"], PER_ITEM_CAP)
        part = f"[{label}] ({authority_note}) {s['title']}\n{text}"
        if used >= TOTAL_BUDGET:
            break
        remaining = TOTAL_BUDGET - used
        if len(part) > remaining:
            part = cap(part, remaining)
        parts.append(part)
        used += len(part)
    return "\n\n".join(parts)


def build_user_message(question, sources, card_context_name=None, card_context_text=None):
    # card_context_* models RulesQuestionAnalysis.CardContext — the explicit "Ask About This Card"
    # cardId flow, NOT a free-text name match (that's CardEvidence, folded into `sources` below).
    # Keep these distinct: production only ever adds this block for the explicit-cardId flow.
    card_block = ""
    if card_context_name:
        text_line = f"\n{card_context_text}" if card_context_text else ""
        card_block = f"\n\nThe question is specifically about this card:\n[{card_context_name}]{text_line}"
    return f"Question: {question}{card_block}\n\nRules evidence:\n{build_evidence_text(sources)}"


def make_example(question, sources, answer, card_context_name=None, card_context_text=None):
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_message(question, sources, card_context_name, card_context_text)},
            {"role": "assistant", "content": answer},
        ]
    }


def describe_card_text(name, humanized_text):
    """Turns a card's raw printed text into a correct, plainly-worded description — used as the
    fine-tuning TARGET, so this can't be self-distilled from the (currently unreliable for this
    exact shape) live model.

    Deliberately does NOT try to surgically parse and rewrite the text into a bespoke sentence per
    card — real card text has too many shapes for that to be reliable (a keyword can have a cost
    annotation between the bracket and its reminder text, e.g. "[Empower] 2 Energy (...)"; a
    keyword name can also appear a second time bare, mid-sentence, referring back to itself, e.g.
    "...if this is [Empowered], give..."; some cards have no reminder text at all). An earlier
    version of this function tried to strip and reassemble those pieces and produced genuinely
    broken output — an empty "if this is , give..." — for exactly that cost-annotation case,
    caught by inspecting the generated dataset before ever starting a training run on it.

    Instead: quote the card's real text whole (always correct, since it's the actual data) and
    teach the one general reading rule the model needs — that "[Keyword] (parenthetical)" is that
    keyword's own rule, not flavor text or a stage direction — via a fixed explanatory clause
    repeated across every bracket-bearing example. Teaching the pattern generally, many times, over
    real varied text is more reliable than hand-parsing each instance.
    """
    if not BRACKET_KEYWORD_RE.search(humanized_text):
        return f"{name}'s printed text says: \"{humanized_text}\""
    return (
        f"{name}'s printed text says: \"{humanized_text}\" "
        "Any \"[Keyword] (...)\" segment in that text names an official keyword, and the "
        "parenthetical immediately after it is that keyword's own rule — not a separate note, and "
        "not an instruction to the reader."
    )


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
                  "current": True, "text": text}
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
        sources = [{"ruleNumber": s["ruleNumber"], "title": s["title"], "authority": s["authority"],
                    "current": s["current"], "text": s.get("fullText") or s["snippet"]} for s in result["sources"]]
        examples.append(make_example(question, sources, result["answer"]))
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
        sources = [{"ruleNumber": s["ruleNumber"], "title": s["title"], "authority": s["authority"],
                    "current": s["current"], "text": s.get("fullText") or s["snippet"]} for s in result["sources"]]
        examples.append(make_example(question, sources, result["answer"]))
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
                  "text": f"Original: {original}\nUpdated: {corrected}"}
        answer = (
            f"Yes — {name} received official errata ({doc_title}). "
            f"The original text was: \"{original}\" It was updated to: \"{corrected}\""
        )
        # No card-context block here — a free-text name match becomes CardEvidence in `sources`
        # (production's CardNotes), not RulesQuestionAnalysis.CardContext. That block is only ever
        # populated by the explicit "Ask About This Card" cardId flow.
        examples.append(make_example(question, [source], answer))
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
                  "text": f"{name} is {status} in {fmt}."}
        examples.append(make_example(question, [source], legality_answer(name, fmt, status)))
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
                    "text": f"{name} is {legality_status_names[r['Status']]} in {r['Format']}."} for r in rows]
        for target in rows:
            fmt, status = target["Format"], legality_status_names[target["Status"]]
            question = random.choice([
                f"Is {name} banned in {fmt} specifically?", f"What is {name}'s legality in {fmt}?", f"Can I play {name} in {fmt}?",
            ])
            others = ", ".join(f"{legality_status_names[r['Status']]} in {r['Format']}" for r in rows if r is not target)
            answer = legality_answer(name, fmt, status)
            if others:
                answer += f" (It is also {others}.)"
            examples.append(make_example(question, sources, answer))
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
                  "authority": "CoreRules", "current": True, "text": padding["Text"]}
        answer = (
            "I don't have official Riftbound rules evidence that addresses this question — it's "
            "outside what I can answer from the rules library. I can only answer questions about "
            "Riftbound's official rules, keywords, errata, and card legality."
        )
        examples.append(make_example(question, [source], answer))
    print(f"  {len(off_topic_questions)} examples")

    print("Category 7: card ability questions (own printed text as evidence)...")
    cur.execute("SELECT Id, Name, TextPlain FROM Cards WHERE TextPlain IS NOT NULL AND TextPlain != ''")
    all_cards = cur.fetchall()
    bracket_cards = [c for c in all_cards if BRACKET_KEYWORD_RE.search(c["TextPlain"])]
    plain_cards = [c for c in all_cards if not BRACKET_KEYWORD_RE.search(c["TextPlain"])]
    # Weighted toward bracket-keyword cards (~44% of the catalog) since that's the exact shape that
    # broke — but plain-text cards are included too so the model doesn't overfit to "always expect
    # brackets."
    sample_cards = (
        random.sample(bracket_cards, min(180, len(bracket_cards)))
        + random.sample(plain_cards, min(90, len(plain_cards)))
    )
    random.shuffle(sample_cards)
    question_templates = [
        "What does {name} do?", "How does {name} work?", "Can you tell me the rules of {name}?",
        "{name} rules", "Explain {name}'s ability.", "What is {name}'s effect?",
    ]
    count7 = 0
    for card in sample_cards:
        name = card["Name"]
        humanized = humanize(card["TextPlain"])
        question = random.choice(question_templates).format(name=name)
        source = {"ruleNumber": None, "title": name, "authority": "CardText", "current": True, "text": humanized}
        answer = describe_card_text(name, humanized)
        examples.append(make_example(question, [source], answer))
        count7 += 1
    print(f"  {count7} examples ({min(180, len(bracket_cards))} bracket-keyword, {min(90, len(plain_cards))} plain)")

    random.shuffle(examples)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"\nTotal examples: {len(examples)}")
    print(f"Written to: {OUT_PATH}")


if __name__ == "__main__":
    main()
