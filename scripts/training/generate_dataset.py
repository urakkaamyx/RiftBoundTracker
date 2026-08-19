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
  8. Partial-evidence honesty (templated) — a card's own text as the only evidence, paired with a
     question about a specific interaction/timing detail that text doesn't resolve (found by
     testing: a real deployed model answered a timing question "Yes" with no supporting evidence at
     all, and fabricated a nonexistent "parenthetical" by reflexively echoing category 7's answer
     template onto a card with no brackets). Teaches that having some evidence about a card doesn't
     mean every specific question about it is answerable from that evidence.
  9. Combined card evidence (templated) — the small set of cards (~17) that have CardText AND a
     legality row AND/OR errata, all supplied together exactly as FindCardEvidenceAsync actually
     assembles them for a generic free-text question. Categories 4/5/7 only ever trained on ONE
     evidence type in isolation; a real generic question about a card with more than one type
     surfaced a worse version of the same regurgitation problem category 8 targets — verified
     directly: asked generically about Draven - Vanquisher (which has all three), the model dumped
     the raw evidence blocks almost verbatim and invented a fake "OfficialRuleHint:" label that
     appears nowhere in the real evidence or system prompt.
  10. Might vs damage-marked scenario reasoning (templated, answer computed programmatically, never
      self-distilled) — found by testing a real question about whether damage reduces a unit's
      Might (it doesn't; damage is a separate marked value). Retrieval found the exactly-right
      rules every time, but the model answered inconsistently across repeated identical questions.
      None of categories 1-9 teach APPLYING a rule to a hypothetical numeric scenario — they're all
      either direct lookup, self-distillation, or evidence recitation, which is a different skill
      from "given this rule and these numbers, what happens." Swept across a range of Might/damage
      combinations against the same three rules so the model sees the pattern generalized, not
      memorized for one specific pair of numbers.
  11. Community FAQ interaction/timing questions (riftboundfaq.com, CC BY-SA 4.0 — see
      FAQ_ATTRIBUTION) — real Q&A entries generalizing category 10's fix beyond one mechanic. Each
      entry's cited rule numbers are looked up against OUR OWN synced corpus (never the FAQ's own
      text) to build evidence, so the evidence shape matches what real retrieval actually produces;
      entries whose citations don't resolve, or whose answer is too long, are skipped. Starts with
      general-rules + mechanics (13 pages) only — not yet the 47 card-specific pages — to keep this
      a modest, testable dataset-size increase given round 3/4's instability from size growth alone.

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

# Community FAQ (riftboundfaq.com) — real Q&A entries with precise rule citations, reviewed
# against a specific Core Rules version, covering interaction/timing questions no other category
# here can generate (they require actually knowing the correct ruling, not just quoting a card or
# a single rule). Content is CC BY-SA 4.0 — https://github.com/ChristianIvicevic/riftboundfaq,
# authored by Christian I. (Near) and contributors. Used here as fine-tuning data with attribution;
# never redistributed verbatim as app content. See FAQ_PATHS below for exactly which pages.
FAQ_REPO_RAW_BASE = "https://raw.githubusercontent.com/ChristianIvicevic/riftboundfaq/main/content/(rulings)"
FAQ_ATTRIBUTION = (
    "riftboundfaq.com by Christian I. (Near) and contributors, CC BY-SA 4.0, "
    "https://github.com/ChristianIvicevic/riftboundfaq"
)
FAQ_MAX_ANSWER_CHARS = 900

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


def fetch_faq_mdx(relative_path):
    url = f"{FAQ_REPO_RAW_BASE}/{relative_path}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read().decode("utf-8")


def clean_faq_text(text):
    """Converts the FAQ's MDX/JSX markup to plain readable text — <Card name="X" /> -> X,
    <Rule number="N" /> -> "Rule N" (with a leading space; the source often has no space before the
    tag, e.g. "...the trash.<Rule number="X" />", which without this reads as "trash.Rule X"), bare
    self-closing keyword components like <Empower /> -> their tag name, Callout wrappers dropped
    (their contents kept), markdown links -> link text, bold markers stripped, and any H2-H4
    subheading still left over (from an H3 inside the H2 section this became one answer for) turned
    into an inline lead-in instead of raw "### Heading [#anchor]" markdown."""
    text = re.sub(r'<Card\s+name="([^"]+)"\s*/>', r'\1', text)
    text = re.sub(r'<Rule\s+number="([^"]+)"\s*/>', r' Rule \1', text)
    text = re.sub(r'<Callout[^>]*>', '', text)
    text = text.replace('</Callout>', '')
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'<(\w+)\s*/>', r'\1', text)  # remaining bare keyword components, e.g. <Empower />
    text = re.sub(r'^#{2,4}\s+(.*?)\s*\[#[\w-]+\]\s*$', r'\1:', text, flags=re.MULTILINE)
    text = text.replace('**', '')
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()


def parse_faq_mdx(raw_content):
    """Splits one FAQ page into (question, cleaned_answer, cited_rule_numbers) tuples, one per H2
    section ("## Question text [#anchor]"). H3 subsections within one H2 are kept as part of that
    H2's answer, not split out separately — they're sub-parts of one question, not new questions."""
    fm_match = re.match(r'^---\n.*?\n---\n(.*)$', raw_content, re.DOTALL)
    if not fm_match:
        return []
    body = fm_match.group(1)
    entries = []
    for section in re.split(r'\n## ', body)[1:]:
        header_line, _, rest = section.partition('\n')
        heading_match = re.match(r'^(.*?)\s*\[#[\w-]+\]\s*$', header_line.strip())
        if not heading_match:
            continue
        question = heading_match.group(1).strip()
        rule_numbers = list(dict.fromkeys(re.findall(r'<Rule\s+number="([^"]+)"\s*/>', rest)))
        answer = clean_faq_text(rest)
        entries.append((question, answer, rule_numbers))
    return entries


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
    # This is round 2's exact sampling (full bracket catalog + 200 plain) — the only configuration
    # of several tried that produced a stable Qwen3 model, and what's actually hosted as
    # ask-rules-model-qwen3-1.7b-v1 today. Two follow-up attempts changed this ratio to fix a real,
    # separately-confirmed bug (Arena Kingpin's answer picking up an inapplicable bracket-keyword
    # sentence despite having no brackets), and BOTH attempts — one with bracket cards capped to
    # 400, one with the cap removed again but category 8 pulled back down — produced models with
    # repetition-loop degeneration and, once, a factually-reversed legality answer, none of which
    # round 2 ever showed. Isolated retraining with only epochs/learning-rate changed (not yet
    # tried) is the next real lever; simply reverting to the known-stable ratio here so this file
    # matches what's actually shipped rather than an unproven experiment.
    bracket_sample = list(bracket_cards)
    plain_sample_7 = random.sample(plain_cards, min(200, len(plain_cards)))
    sample_cards = bracket_sample + plain_sample_7
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
    print(f"  {count7} examples ({len(bracket_sample)} bracket-keyword, {len(plain_sample_7)} plain)")

    print("Category 8: partial-evidence honesty (a card's text exists but doesn't resolve the specific question)...")
    # Found by testing a real question ("Does Darius Trifarian's +2 Might buff work on opponent's
    # turn?"): the evidence pipeline correctly found the card's own text, but the model answered
    # "Yes" anyway — the card's text says WHAT it does, not WHETHER it works under this specific
    # timing/interaction condition, and nothing in that evidence resolves it either way. It also
    # fabricated a "parenthetical" that doesn't exist in this card's text at all, echoing category
    # 7's bracket-keyword answer template onto a card that has no brackets — reflexive template
    # matching instead of actually reading the evidence. Without examples like these, a model
    # fine-tuned only on category 7 (which always has enough evidence to fully answer) never learns
    # that having SOME evidence about a card doesn't mean every specific question about it is
    # answerable from that evidence.
    partial_evidence_templates = [
        ("Does {name}'s ability work on the opponent's turn?", "whether this triggers during your opponent's turn specifically, as opposed to only your own"),
        ("Can {name}'s trigger happen more than once in the same turn?", "whether this can trigger more than once in a single turn"),
        ("Does {name}'s effect stack if I control two copies?", "whether the effects of two copies stack with each other"),
        ("Can I respond to {name}'s triggered ability?", "whether this specific trigger can be responded to before it resolves"),
        ("What happens if {name} leaves the board before its ability resolves?", "what happens if this card leaves the board after the ability triggers but before it resolves"),
        ("Does {name}'s ability still work while it's Stunned?", "whether being Stunned affects this specific ability"),
        ("Does {name}'s effect apply retroactively to units already on the board?", "whether this effect applies retroactively to things already in play when it starts applying"),
    ]
    # This is round 2's exact sampling and answer wording — the only configuration that produced a
    # stable Qwen3 model. Round 2 (160 examples, this wording) showed real but incomplete progress
    # on the Darius test case: the model correctly SAID the evidence didn't establish the answer,
    # then guessed one anyway in the same breath. Two follow-up attempts tried to fix that —
    # raising the count to 320 with a more explicit "I'm not going to guess" wording, then pulling
    # it back to 220 with the same reworded wording — and BOTH produced repetition-loop
    # degeneration on unrelated questions (Exhaust, unit death) that round 2 never showed, even at
    # 220, which is close to round 2's own 160. That rules out "just the count" as the sole cause;
    # the reworded template itself, or the interaction with category 7's total size, may be
    # contributing. Reverting fully to round 2's proven state (count AND wording) rather than
    # shipping an unproven partial fix — see scripts/training/README.md for how to resume this
    # investigation (isolating epochs/learning-rate is the next untried lever, not another dataset
    # ratio change).
    partial_sample = random.sample(all_cards, min(160, len(all_cards)))
    count8 = 0
    for card in partial_sample:
        name = card["Name"]
        humanized = humanize(card["TextPlain"])
        question_template, topic = random.choice(partial_evidence_templates)
        question = question_template.format(name=name)
        source = {"ruleNumber": None, "title": name, "authority": "CardText", "current": True, "text": humanized}
        answer = (
            f"{name}'s printed text says: \"{humanized}\" That tells you what the card does, but it "
            f"doesn't say anything about {topic} — I don't have rules evidence that clearly "
            f"establishes that, so I can't say for sure either way."
            f"reporting one."
        )
        examples.append(make_example(question, [source], answer))
        count8 += 1
    print(f"  {count8} examples")

    print("Category 9: combined card evidence (text + legality/errata together)...")
    # A generic free-text question about a card (e.g. "What does Draven - Vanquisher do?") surfaces
    # EVERY applicable CardEvidence item at once — FindCardEvidenceAsync always adds CardText first,
    # then every legality row, then every errata row, in that order (see RulesEvidenceService.cs).
    # Category 7 only ever trained on a single CardText item alone; category 4/5 only ever trained
    # on a single legality/errata item alone. Neither covers what actually happens for one of the
    # ~17 cards that have BOTH — verified directly: asked about Draven - Vanquisher (which has all
    # three: CardText, a CoreRules legality row, and an OfficialErrata row) and the model regurgitated
    # the raw evidence blocks almost verbatim, including inventing a fake "OfficialRuleHint:" label
    # that appears nowhere in the real evidence or system prompt — it had never seen this combined
    # shape and fell back on base-model habits instead of synthesizing an answer.
    legality_status_names_local = ["Legal", "Banned", "Restricted", "NotLegal"]
    cur.execute("SELECT Id, Name, TextPlain FROM Cards WHERE TextPlain IS NOT NULL AND TextPlain != ''")
    combo_candidates = cur.fetchall()
    count9 = 0
    for card in combo_candidates:
        cur.execute("SELECT Format, Status FROM CardLegalities WHERE CardId = ? AND IsCurrent = 1", (card["Id"],))
        legalities = cur.fetchall()
        cur.execute("""
            SELECT ce.OriginalText, ce.CorrectedText, rd.Title as DocTitle FROM CardErrata ce
            JOIN RuleDocuments rd ON ce.DocumentId = rd.Id
            WHERE ce.CardNameRaw = ? AND ce.IsCurrent = 1
        """, (card["Name"],))
        errata = cur.fetchall()
        if not legalities and not errata:
            continue

        name = card["Name"]
        humanized = humanize(card["TextPlain"])
        sources = [{"ruleNumber": None, "title": name, "authority": "CardText", "current": True, "text": humanized}]
        answer_parts = [describe_card_text(name, humanized)]

        for l in legalities:
            status = legality_status_names_local[l["Status"]]
            sources.append({"ruleNumber": None, "title": name, "authority": "CoreRules", "current": True,
                             "text": f"{name} is {status} in {l['Format']}."})
            verb = "is not legal (banned)" if status.lower() == "banned" else f"is {status.lower()}"
            answer_parts.append(f"{name} {verb} in {l['Format']}.")

        for e in errata:
            sources.append({"ruleNumber": None, "title": name, "authority": "OfficialErrata", "current": True,
                             "text": f"Original: {e['OriginalText']}\nUpdated: {e['CorrectedText']}"})
            answer_parts.append(
                f"It also received official errata ({e['DocTitle']}): the original text was "
                f"\"{e['OriginalText']}\", updated to \"{e['CorrectedText']}\"."
            )

        question = random.choice(question_templates).format(name=name)
        examples.append(make_example(question, sources, " ".join(answer_parts)))
        count9 += 1
    print(f"  {count9} examples")

    print("Category 10: Might vs damage-marked scenario reasoning...")
    # Reported directly: "If my card has 8 might and someone does 2 damage, does that make my
    # might 6 or does my might stay at an 8...?" — RulesEvidenceService found exactly the right
    # rules (142, 142.4.b, 143.2.a), but the trained model answered inconsistently across repeated
    # identical questions, including once claiming Might is directly reduced by damage. It isn't —
    # damage is tracked as a separate "marked" value; a unit's Might itself never changes from
    # combat damage. None of categories 1-9 ever taught APPLYING a rule to a hypothetical numeric
    # scenario — they're all either direct lookup, keyword self-distillation, or evidence
    # recitation, none of which is the same skill as "given this rule and these numbers, what
    # happens." This category is templated with the answer computed programmatically (never
    # self-distilled — the model was already wrong at this, so its own output can't be a training
    # target) across a spread of Might/damage combinations against the same three real rules, so
    # the model sees the pattern applied consistently rather than to one specific number pair.
    might_damage_source = [
        {"ruleNumber": "142", "title": "Rule 142", "authority": "CoreRules", "current": True,
         "text": "Damage is a marked value that is applied to Units."},
        {"ruleNumber": "142.4.b", "title": "Rule 142.4.b", "authority": "CoreRules", "current": True,
         "text": ("Lethal Damage for a Unit is a non-zero amount greater than or equal to that Unit's Might. "
                   "Example: A unit has 5 [M] and 3 damage marked on it. Frigid Touch is played targeting that "
                   "unit. When it resolves, the unit's Might becomes 3, and it will have lethal damage marked "
                   "on it. Example: A unit has 0 [M]. In order to have lethal damage marked on it, it must "
                   "have at least 1 damage marked on it.")},
        {"ruleNumber": "143.2.a", "title": "Rule 143.2.a", "authority": "CoreRules", "current": True,
         "text": "If a Unit ever has nonzero damage marked on it equalling or exceeding its Might, it is Killed."},
    ]
    might_question_templates = [
        "If my unit has {might} might and takes {damage} damage, does its might become {remaining} or does its might stay at {might}?",
        "My unit has {might} might. If it takes {damage} damage, is it dead?",
        "Does {damage} damage reduce my {might}-might unit's might, or is damage tracked separately?",
        "I have a {might} might unit with {damage} damage marked on it. How much more damage does it need to die?",
    ]
    count10 = 0
    for might in range(2, 13):
        damage_values = sorted({0, 1, might // 2, might - 1, might} & set(range(0, might + 1)))
        for damage in damage_values:
            needed = might - damage
            is_dead = damage >= might
            question = random.choice(might_question_templates).format(might=might, damage=damage, remaining=needed)
            fate = (
                f"With {damage} damage marked and {might} Might, the unit already has lethal damage marked "
                f"on it and is Killed." if is_dead else
                f"With {damage} damage marked and {might} Might, the unit is not dead — it would take a "
                f"total of {might} damage marked to kill it, so {needed} more damage would do it."
            )
            answer = (
                f"No — your unit's Might stays at {might}. Damage is a separate marked value, not a "
                f"subtraction from Might (Rule 142: \"Damage is a marked value that is applied to Units.\"). "
                f"A unit is Killed once its marked damage equals or exceeds its Might (Rule 143.2.a). {fate}"
            )
            examples.append(make_example(question, might_damage_source, answer))
            count10 += 1
    print(f"  {count10} examples")

    print("Category 11: community FAQ interaction/timing questions (riftboundfaq.com)...")
    # Real Q&A entries covering exactly the gap category 10 was hand-built to patch for one
    # mechanic (Might vs damage) — interaction/timing questions that require actually knowing the
    # correct ruling, which no other category here can generate at scale (they all either quote a
    # card, quote one rule, or self-distill from a model that's already shown it gets this kind of
    # reasoning wrong). Starting with general-rules + mechanics only (13 pages), not the 47
    # card-specific pages — round 3/4 showed dataset SIZE growth alone can destabilize training, so
    # this stays a modest, testable addition; the card pages are a natural next step once this is
    # confirmed stable. See FAQ_ATTRIBUTION above — CC BY-SA 4.0, used here as fine-tuning
    # material with attribution, never redistributed as app content.
    faq_paths = [
        "general-rules/abilities.mdx", "general-rules/chain-and-priority.mdx",
        "general-rules/costs-and-payments.mdx", "general-rules/movement.mdx",
        "general-rules/playing-cards.mdx", "general-rules/showdowns.mdx", "general-rules/targeting.mdx",
        "mechanics/ambush.mdx", "mechanics/deathknell.mdx", "mechanics/empower.mdx",
        "mechanics/equipment.mdx", "mechanics/flow.mdx", "mechanics/repeat.mdx",
    ]
    count11 = 0
    skipped_no_evidence = 0
    skipped_too_long = 0
    for path in faq_paths:
        try:
            raw = fetch_faq_mdx(path)
        except Exception as ex:
            print(f"  skip (fetch failed): {path} — {ex}")
            continue
        for question, answer, rule_numbers in parse_faq_mdx(raw):
            if len(answer) > FAQ_MAX_ANSWER_CHARS:
                skipped_too_long += 1
                continue
            sources = []
            for number in rule_numbers:
                cur.execute("SELECT Title, Text FROM RuleEntries WHERE RuleNumber = ? AND IsCurrent = 1", (number,))
                row = cur.fetchone()
                if row is None:
                    continue
                sources.append({"ruleNumber": number, "title": row["Title"] or f"Rule {number}",
                                 "authority": "CoreRules", "current": True, "text": row["Text"]})
            if not sources:
                skipped_no_evidence += 1
                continue
            examples.append(make_example(question, sources, answer))
            count11 += 1
    print(f"  {count11} examples ({skipped_no_evidence} skipped: no citation resolved against the "
          f"synced corpus, {skipped_too_long} skipped: answer over {FAQ_MAX_ANSWER_CHARS} chars)")

    random.shuffle(examples)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"\nTotal examples: {len(examples)}")
    print(f"Written to: {OUT_PATH}")


if __name__ == "__main__":
    main()
