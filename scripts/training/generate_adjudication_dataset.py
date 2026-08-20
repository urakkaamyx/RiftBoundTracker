"""
Generates a fine-tuning dataset for the adjudicate -> validate -> explain pipeline
(Riftbound_Ask_Rules_Upgrade_Architecture.md), for the Qwen3-1.7B option in LocalAiModelCatalog.cs.

This is a SEPARATE dataset/script from generate_dataset.py, not a replacement of it —
generate_dataset.py stays exactly as it is for retraining Qwen2.5-1.5B on the original single-pass
ExplainAsync shape. This script targets the two NEW prompt shapes LocalLlmExplanationProvider.cs
added this session (AdjudicateAsync / ExplainAdjudicationAsync), which no model has ever been
trained on before — that's the actual reason real-model testing showed adjudication validating on
only ~1/14 attempts and drifting onto hallucinated questions: the model had zero fine-tuning
exposure to this task shape, and prompt/grammar engineering alone hit a ceiling fixing that.

IMPORTANT — keep this file's prompts/formatting byte-for-byte in sync with
LocalLlmExplanationProvider.cs's AdjudicationSystemPrompt, AdjudicatedExplanationSystemPrompt,
BuildAdjudicationUserMessage, and BuildAdjudicatedExplanationUserMessage. If those change, update
the matching constants/functions here in the same change — see generate_dataset.py's own docstring
for why this matters (fine-tuning against a prompt shape the model won't see at inference time
teaches habits that don't transfer).

Three categories of examples, all sharing the two-message-pair structure (one ADJUDICATE example +
one EXPLAIN example per underlying ruling):

1. Hand-verified interaction rulings — the highest-value category. Each is a real rules question
   with an answer verified directly against the current rules corpus (not self-distilled — the
   whole reason this dataset exists is that the un-fine-tuned model isn't reliable enough to
   self-distil FROM for this task shape). Covers exactly the interaction classes real testing this
   session found the model struggling with: Contested/control conditions, Tank (damage-assignment
   priority, not targeting), Exhaust/Ready state, Stun, Counter, Might vs. marked damage, Shield
   stacking, Burn Out, Vision. Several paraphrases per ruling so the model generalizes the
   underlying fact instead of memorizing one exact phrasing.
2. Errata and legality — deterministic, templated from the real corpus (mirrors generate_dataset.py's
   categories 4/5/5b), reshaped into Yes/No adjudications.
3. Insufficient-evidence calibration — genuinely off-topic questions, plus questions about
   plausible-sounding mechanics that don't exist in this game (e.g. "Blinded", confirmed zero
   corpus mentions) — without this category, fine-tuning erodes "I don't know" in favor of guessing,
   same reasoning as generate_dataset.py category 6.

Also writes a smaller supplementary set of single-pass (ExplainAsync-shape) examples for rule
lookups and card-ability descriptions — genuinely descriptive "what does X do" / "what does rule N
say" questions don't fit the adjudication format's Yes/No/Insufficient shape naturally (there's no
ruling to decide, just a fact to state), and whatever model gets selected in Settings still uses
ExplainAsync as the fallback whenever adjudication doesn't validate. Training only on the new shape
would leave that fallback path worse than before for this model, not just "not yet improved".

Output: scripts/training/output/adjudication-dataset.jsonl
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
# Requires the app running locally (for /api/card-text-symbols humanization) — see generate_dataset.py's
# own README section for the port-isolation note; never point this at a real running install.
API_BASE = f"http://localhost:{os.environ.get('RIFTKEEP_API_PORT', '5080')}"
OUT_DIR = Path(__file__).resolve().parent / "output"
OUT_PATH = OUT_DIR / "adjudication-dataset.jsonl"

BRACKET_KEYWORD_RE = re.compile(r"\[([A-Za-z][A-Za-z\s\-]*)\]")
_symbol_map = None


def api(path):
    with urllib.request.urlopen(API_BASE + path, timeout=30) as resp:
        return json.loads(resp.read())


def get_symbol_map():
    """Mirrors CardTextSymbolCatalogService.HumanizeAsync — fetched from the live API rather than
    duplicated by hand so this can never silently drift from the real token/label catalog."""
    global _symbol_map
    if _symbol_map is None:
        _symbol_map = [(s["token"], s["label"]) for s in api("/api/card-text-symbols")]
    return _symbol_map


def humanize(text):
    if not text:
        return text
    for token, label in get_symbol_map():
        text = text.replace(token, label)
    return text


def describe_card_text(name, humanized_text):
    """Turns a card's raw printed text into a correct, plainly-worded description — mirrors
    generate_dataset.py's function of the same name exactly (see that file's docstring for why this
    quotes the card's real text whole rather than hand-parsing/rewriting it into a bespoke sentence:
    an earlier attempt at that produced genuinely broken output for cards with a cost annotation
    between the bracket and its reminder text)."""
    if not BRACKET_KEYWORD_RE.search(humanized_text):
        return f"{name}'s printed text says: \"{humanized_text}\""
    return (
        f"{name}'s printed text says: \"{humanized_text}\" "
        "Any \"[Keyword] (...)\" segment in that text names an official keyword, and the "
        "parenthetical immediately after it is that keyword's own rule — not a separate note, and "
        "not an instruction to the reader."
    )

# Mirrors LocalLlmExplanationProvider.cs's AdjudicationSystemPrompt constant exactly.
ADJUDICATION_SYSTEM_PROMPT = (
    "You are a rules adjudicator for the Riftbound trading card game. Your ONLY job is to decide\n"
    "the correct ruling from the evidence supplied below — you are not writing the player-facing\n"
    "answer here, only the internal ruling.\n"
    "\n"
    "Rules:\n"
    "- Cite evidence only by its E<number> id (e.g. E1, E3). Never type a rule number and never\n"
    "  invent a citation that isn't in the supplied evidence.\n"
    "- Use only the supplied evidence. Never use outside knowledge of other card games, and never\n"
    "  invent a rule or mechanic that isn't in the evidence.\n"
    "- If the question asks about more than one thing, treat each as its own issue.\n"
    "- Evidence is often a conditional built on negations (\"applies if X is not Y\") — work out\n"
    "  literally which side of each \"not\" the actual situation falls on before deciding ANSWER.\n"
    "- If the supplied evidence does not establish the answer, ANSWER is \"Insufficient\" — say so,\n"
    "  do not guess.\n"
    "- You will usually be given far more evidence than any one issue needs. Most of it is\n"
    "  irrelevant to any given issue — that is normal and expected. REASON cites only the 1-3\n"
    "  ids that actually decide this issue. Never work through the evidence id by id, never\n"
    "  summarize what every id says, and never repeat the same sentence structure for multiple\n"
    "  ids — that is a mistake, not thoroughness.\n"
    "\n"
    "Output exactly this shape, one block per issue, nothing else — no other text:\n"
    "ISSUE: <restate the sub-question in your own words>\n"
    "ANSWER: Yes|No|Insufficient\n"
    "REASON: <ONE sentence, citing only the 1-3 E-ids that decide this issue — not a tour of the evidence>\n"
    "EVIDENCE: <comma-separated E ids used for this issue, e.g. E1, E3>\n"
    "MISSING: <only include this line if ANSWER is Insufficient>\n"
    "---\n"
    "(repeat the ISSUE block above for each additional issue, each followed by its own ---)\n"
    "VERDICT: <one line: Yes / No / Mixed / Insufficient evidence>\n"
    "\n"
    "Example — simple question:\n"
    "ISSUE: Does Exhaust let a card be played from the trash?\n"
    "ANSWER: No\n"
    "REASON: E1 defines Exhaust as a cost-paying keyword and says nothing about the trash zone.\n"
    "EVIDENCE: E1\n"
    "---\n"
    "VERDICT: No\n"
    "\n"
    "Example — two issues, one is a negation:\n"
    "ISSUE: Can a unit be played to a battlefield its controller already controls?\n"
    "ANSWER: Yes\n"
    "REASON: E1 lists a controlled battlefield as a valid location a unit can enter.\n"
    "EVIDENCE: E1\n"
    "---\n"
    "ISSUE: Does that make the battlefield Contested?\n"
    "ANSWER: No\n"
    "REASON: E2 only applies Contested when the arriving unit's controller does NOT already\n"
    "control the battlefield; since they already do, that condition is false.\n"
    "EVIDENCE: E2\n"
    "---\n"
    "VERDICT: Mixed\n"
    "\n"
    "Example — insufficient evidence:\n"
    "ISSUE: Can a player sacrifice a Rune to draw a card?\n"
    "ANSWER: Insufficient\n"
    "REASON: The supplied evidence describes Runes only as a payment cost; nothing supplied\n"
    "mentions sacrificing a Rune or a resulting draw effect.\n"
    "EVIDENCE: E1\n"
    "MISSING: A rule or card ability that grants a draw effect from sacrificing a Rune.\n"
    "---\n"
    "VERDICT: Insufficient evidence\n"
    "\n"
    "The three examples above are for OUTPUT FORMAT ONLY. Their questions, evidence ids, and\n"
    "answers are not real and do not apply here. You will now be given a real question and a\n"
    "real, numbered evidence list in the user turn — adjudicate ONLY that question, using ONLY\n"
    "that evidence. Do not reuse or repeat any example's question or reasoning."
)

# Mirrors AdjudicatedExplanationSystemPrompt exactly.
EXPLANATION_SYSTEM_PROMPT = (
    "You are a rules-reference assistant for the Riftbound trading card game, writing the\n"
    "player-facing answer. THE RULING BELOW HAS ALREADY BEEN DETERMINED — do not re-adjudicate\n"
    "it, do not change any Yes/No/Insufficient answer given, and do not reach a different\n"
    "conclusion than the one supplied. Your only job is to communicate the already-decided ruling\n"
    "clearly and naturally, using the supplied rule text to show why it's correct.\n"
    "\n"
    "For each issue: give the direct answer first, explain briefly in plain language, quote the\n"
    "rule text that establishes it, and — for anything conditional or negated — explicitly\n"
    "connect the rule's condition to the player's actual situation (state what the condition\n"
    "requires, state what's actually true here, state the result). If there is more than one\n"
    "issue, address them as clearly separated points and end with a short conclusion; for a\n"
    "single issue, do not force a numbered list or an artificial conclusion section.\n"
    "\n"
    "If an issue's answer is \"Insufficient\", say plainly that the supplied evidence doesn't\n"
    "establish an answer — never guess or fill the gap with outside knowledge.\n"
    "\n"
    "Write flowing plain-language prose only. The ruling below is internal bookkeeping for you to\n"
    "read, not a template to echo — never repeat its \"Issue:\"/\"Answer:\"/\"Reason:\"/\"Supporting rule\n"
    "text:\"/\"Overall verdict:\" labels or structure in your response, and never reply with anything\n"
    "resembling \"thank you for providing...\" or an offer of further assistance. A player asked a\n"
    "rules question and is waiting for the answer, not a receipt."
)

# Mirrors LocalLlmExplanationProvider.cs's SystemPrompt exactly (for the supplementary single-pass set).
SINGLE_PASS_SYSTEM_PROMPT = (
    "You are a rules-reference assistant for the Riftbound trading card game. Answer only from\n"
    "the official rules evidence supplied below. If the evidence does not clearly establish the\n"
    "answer, say so plainly instead of guessing. Never invent a ruling that isn't supported by\n"
    "the evidence. Prefer current Core Rules over Tournament Rules, errata, or historical\n"
    "material when they overlap. Clearly distinguish what a rule directly says from any\n"
    "interpretation you're making. Keep the answer concise — a few sentences, not an essay.\n"
    "A card's own printed text is valid evidence of what that card does — if it's supplied below,\n"
    "describe the card's effect directly instead of calling the evidence insufficient.\n"
    "Rules text is often a conditional built on negations (\"applies if X is not Y and Z does not\n"
    "W\") — before answering, work out literally which side of each \"not\" the actual situation in\n"
    "the question falls on. Getting a negation backwards produces the opposite of the correct\n"
    "ruling, which is worse than not answering at all."
)

PER_ITEM_CAP = 1400
TOTAL_BUDGET = 9000


def cap(text, max_chars):
    return text if len(text) <= max_chars else text[:max_chars] + "…"


def build_evidence_ref_text(eid, label, authority, current, full_text):
    hist = "" if current else ", historical"
    return f"{eid} [{label}] ({authority}{hist})\n{cap(full_text, PER_ITEM_CAP)}"


def build_adjudication_user_message(question, evidence_parts):
    """evidence_parts: list of (eid, label, authority, current, full_text) already in E-order."""
    used = 0
    parts = []
    for eid, label, authority, current, full_text in evidence_parts:
        part = build_evidence_ref_text(eid, label, authority, current, full_text)
        if used >= TOTAL_BUDGET:
            break
        remaining = TOTAL_BUDGET - used
        if len(part) > remaining:
            part = cap(part, remaining)
        parts.append(part)
        used += len(part)
    evidence_text = "\n\n".join(parts)
    return (
        f"Adjudicate this real question — it is not one of the system prompt's examples:\n"
        f"Question: {question}\n\nEvidence:\n{evidence_text}"
        f"\n\nReminder — the real question you must adjudicate is: {question}"
    )


def build_adjudicated_explanation_user_message(question, issues, verdict):
    """issues: list of dicts {question, answer, reason, quotes: [(label, authority, current, full_text)]}"""
    joined = "\n\n---\n\n".join(
        f"Issue: {i['question']}\nAnswer: {i['answer']}\nReason: {i['reason']}\n"
        f"Supporting rule text:\n" + "\n\n".join(
            f"[{label}] ({authority}{'' if current else ', historical'})\n{full_text}"
            for label, authority, current, full_text in i["quotes"]
        )
        for i in issues
    )
    return f"Question: {question}\n\nRuling (already determined — explain it, do not change it):\n{joined}\n\nOverall verdict: {verdict}"


def adjudication_assistant_text(issues, verdict):
    blocks = []
    for issue in issues:
        lines = [f"ISSUE: {issue['question']}", f"ANSWER: {issue['answer']}", f"REASON: {issue['reason']}",
                  f"EVIDENCE: {', '.join(issue['evidence_ids'])}"]
        if issue.get("missing"):
            lines.append(f"MISSING: {issue['missing']}")
        blocks.append("\n".join(lines))
    return "\n---\n".join(blocks) + f"\n---\nVERDICT: {verdict}"


def make_adjudication_example(question, evidence_parts, issues, verdict):
    return {"messages": [
        {"role": "system", "content": ADJUDICATION_SYSTEM_PROMPT},
        {"role": "user", "content": build_adjudication_user_message(question, evidence_parts)},
        {"role": "assistant", "content": adjudication_assistant_text(issues, verdict)},
    ]}


def make_explanation_example(question, issues, verdict, explanation):
    return {"messages": [
        {"role": "system", "content": EXPLANATION_SYSTEM_PROMPT},
        {"role": "user", "content": build_adjudicated_explanation_user_message(question, issues, verdict)},
        {"role": "assistant", "content": explanation},
    ]}


def make_single_pass_example(question, sources, answer):
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
    evidence_text = "\n\n".join(parts)
    user = f"Question: {question}\n\nRules evidence:\n{evidence_text}"
    return {"messages": [
        {"role": "system", "content": SINGLE_PASS_SYSTEM_PROMPT},
        {"role": "user", "content": user},
        {"role": "assistant", "content": answer},
    ]}


def rule_row(cur, number):
    row = cur.execute(
        "SELECT RuleNumber, Title, Text FROM RuleEntries WHERE RuleNumber = ? AND IsCurrent = 1", (number,)
    ).fetchone()
    if row is None:
        raise ValueError(f"Rule {number} not found in corpus — dataset/corpus have drifted, fix before training")
    return row


def evidence_from_rules(cur, rule_numbers):
    """Builds (eid, label, authority, current, full_text) tuples, E1..En, for a list of rule numbers."""
    parts = []
    for i, number in enumerate(rule_numbers, start=1):
        row = rule_row(cur, number)
        label = f"Rule {row['RuleNumber']}" if row["RuleNumber"] else row["Title"]
        parts.append((f"E{i}", label, "CoreRules", True, row["Text"]))
    return parts


_ALL_RULE_NUMBERS_CACHE = None


def evidence_from_rules_with_noise(cur, rule_numbers, total_count=16):
    """Round-2 testing found training on small, clean 2-3-item evidence packets for hand-crafted
    rulings didn't reliably transfer to the ~16-item noisy packets RulesEvidenceService actually
    retrieves at inference time — a directly-trained fact (Might vs. marked damage) regressed to
    "insufficient evidence" once real retrieval surrounded it with noise the training data never
    showed, and the model had never practiced finding the 1-3 relevant ids inside a large,
    mostly-irrelevant field. This pads the real (signal) evidence out to `total_count` with random
    unrelated current rules, then shuffles the combined list so the signal isn't reliably at a fixed
    position — matching what real retrieval actually hands the model.

    Returns (evidence_list, clean_to_padded_id_map): the padded, shuffled evidence list, and a map
    from the ORIGINAL E1..En (position within `rule_numbers`, before padding/shuffling) to the new
    E-id after shuffling — callers built their issue's evidence_ids/REASON text against the clean
    numbering and need this to remap both onto the padded, shuffled result (see remap_issue).
    """
    global _ALL_RULE_NUMBERS_CACHE
    signal = evidence_from_rules(cur, rule_numbers)
    if _ALL_RULE_NUMBERS_CACHE is None:
        cur.execute("SELECT RuleNumber FROM RuleEntries WHERE IsCurrent = 1 AND RuleNumber IS NOT NULL")
        _ALL_RULE_NUMBERS_CACHE = [row["RuleNumber"] for row in cur.fetchall()]
    exclude = set(rule_numbers)
    pool = [n for n in _ALL_RULE_NUMBERS_CACHE if n not in exclude]
    noise_count = max(0, total_count - len(signal))
    noise_numbers = random.sample(pool, min(noise_count, len(pool)))
    noise = [(None,) + tuple(evidence_from_rules(cur, [n])[0][1:]) for n in noise_numbers]

    combined = list(signal) + noise
    random.shuffle(combined)
    id_map = {}
    final = []
    for i, (clean_eid, label, authority, current, text) in enumerate(combined, start=1):
        new_eid = f"E{i}"
        if clean_eid is not None:
            id_map[clean_eid] = new_eid
        final.append((new_eid, label, authority, current, text))
    return final, id_map


def remap_issue(issue, id_map):
    """Rewrites an issue's evidence_ids and any inline E<n> references in its REASON text from the
    clean (pre-padding) numbering to the padded/shuffled numbering — see evidence_from_rules_with_noise.
    Goes through a placeholder pass first so a chain like E1->E5, E5->E9 can't double-substitute."""
    reason = issue["reason"]
    for clean_id, new_id in id_map.items():
        reason = re.sub(rf'\b{clean_id}\b', f'￹{new_id}￹', reason)
    reason = reason.replace('￹', '')
    new_issue = dict(issue)
    new_issue["reason"] = reason
    new_issue["evidence_ids"] = [id_map[e] for e in issue["evidence_ids"]]
    return new_issue


# ---------------------------------------------------------------------------
# Category 1: hand-verified interaction rulings.
#
# Every REASON/answer here was checked directly against the current rules corpus this session
# (not self-distilled), the same way the real test-scenario ground truth earlier in this session
# was verified. `rule_numbers` are pulled live from RuleEntries so evidence text always matches
# whatever's actually in the synced corpus, not a stale hardcoded copy.
# ---------------------------------------------------------------------------
RULING_CASES = [
    {
        "rule_numbers": ["190.3.a", "190.3.a.1"],
        "questions": [
            "If I play a unit to a battlefield I already control, does that make it Contested?",
            "My opponent already controls a battlefield and I move a unit there — is it Contested now?",
            "Does moving a unit onto a battlefield its controller already controls apply Contested status?",
        ],
        "answer": "No",
        "reason": "E2 only applies Contested when the arriving unit's controller does NOT already control the battlefield; since they already do, that condition is false.",
        "evidence_ids": ["E2"],
        "verdict": "No",
        "explanation": (
            "No — moving a unit onto a battlefield its controller already controls does not make it "
            "Contested. Contested status only applies when a unit's controller does NOT already "
            "control the battlefield it's moving to: \"Units moving to or being played to a "
            "battlefield apply Contested status if that battlefield is not already Contested and "
            "that Unit's controller does not already control that battlefield.\" Here the controller "
            "already controls the battlefield, so that second condition is false and Contested is "
            "never applied."
        ),
    },
    {
        "rule_numbers": ["190.3.a", "190.3.a.1"],
        "questions": [
            "If I play a unit to a battlefield I don't control, and it isn't already Contested, does that make it Contested?",
            "A battlefield isn't Contested and I don't control it — if I move a unit there, does it become Contested?",
        ],
        "answer": "Yes",
        "reason": "E2 applies Contested when the battlefield isn't already Contested and the arriving unit's controller doesn't already control it — both conditions are met here.",
        "evidence_ids": ["E2"],
        "verdict": "Yes",
        "explanation": (
            "Yes — that battlefield becomes Contested. Contested status applies \"if that battlefield "
            "is not already Contested and that Unit's controller does not already control that "
            "battlefield.\" Both parts of that condition are true in this situation (it isn't already "
            "Contested, and you don't already control it), so moving your unit there applies "
            "Contested status to it."
        ),
    },
    {
        "rule_numbers": ["190.3.a.1"],
        "questions": [
            "If a battlefield is already Contested and another unit moves there, does that apply Contested again?",
            "Does moving a second unit to an already-Contested battlefield contest it a second time?",
        ],
        "answer": "No",
        "reason": "E1 only applies Contested status \"if that battlefield is not already Contested\" — it's already Contested here, so that condition is false.",
        "evidence_ids": ["E1"],
        "verdict": "No",
        "explanation": (
            "No — a second unit moving to a battlefield that's already Contested doesn't apply "
            "Contested again. The rule that grants Contested status explicitly requires \"that "
            "battlefield is not already Contested\"; since it already is, that condition isn't met, "
            "so this move doesn't trigger anything new (the battlefield simply stays Contested from "
            "whatever originally applied it)."
        ),
    },
    {
        "rule_numbers": ["815.1.b", "815.1.c.2", "465.2.c.6"],
        "questions": [
            "If I have Tank on my unit, do spells from enemies have to target me first as well?",
            "Does Tank on my unit force enemy spells to target it before other units?",
            "My unit has Tank — does that make it a required target for enemy spells too?",
        ],
        "answer": "No",
        "reason": "E1 defines Tank purely as a COMBAT DAMAGE assignment priority (\"assigned lethal damage before any other unit\" during the Combat Damage step); it says nothing about spell targeting.",
        "evidence_ids": ["E1"],
        "verdict": "No",
        "explanation": (
            "No — Tank has nothing to do with spell targeting. Tank only governs combat damage "
            "assignment priority: it's \"functionally short for 'I must be assigned lethal damage "
            "before any other unit with the same controller as me that does not have [Tank] during "
            "the Combat Damage step.'\" That's specifically about how a player assigns COMBAT damage "
            "during the Combat Damage step — it doesn't require enemy spells to target that unit at "
            "all. Whether a spell can target it depends entirely on that spell's own targeting text, "
            "not on Tank."
        ),
    },
    {
        "rule_numbers": ["815.2"],
        "questions": [
            "If a unit has Tank twice, does that do anything extra?",
            "Does having two instances of Tank on the same unit stack?",
        ],
        "answer": "No",
        "reason": "E1 states multiple instances of Tank are redundant.",
        "evidence_ids": ["E1"],
        "verdict": "No",
        "explanation": (
            "No — multiple instances of Tank on the same unit are redundant. Having Tank twice "
            "doesn't do anything a single instance of Tank doesn't already do."
        ),
    },
    {
        "rule_numbers": ["414.2", "415.2"],
        "questions": [
            "If a unit is Exhausted, can a spell that can only target Ready units target it?",
            "My unit is Exhausted — can an enemy spell that requires targeting a Ready unit target it?",
        ],
        "answer": "No",
        "reason": "E1/E2 establish Exhausted and Ready as the two states a Game Object can reference; a spell restricted to Ready targets can't target something in the Exhausted state.",
        "evidence_ids": ["E1", "E2"],
        "verdict": "No",
        "explanation": (
            "No — a spell that can only target Ready units can't target an Exhausted one. Exhausted "
            "and Ready are the two states a Game Object can be in for these purposes; a unit that's "
            "Exhausted isn't Ready, so it doesn't meet a spell's requirement to target only Ready "
            "units."
        ),
    },
    {
        "rule_numbers": ["414.1.b", "414.1.c"],
        "questions": [
            "If I exhaust a unit that's already exhausted, does anything happen?",
            "Can I exhaust a unit that is already exhausted?",
        ],
        "answer": "No",
        "reason": "E1 says an already-Exhausted Game Object cannot be Exhausted again, and E2 says if something instructs it anyway, nothing additional happens.",
        "evidence_ids": ["E1", "E2"],
        "verdict": "No",
        "explanation": (
            "No — nothing extra happens. A Game Object that's already Exhausted can't be Exhausted "
            "again, and if something instructs it to be Exhausted anyway, that instruction just does "
            "nothing additional."
        ),
    },
    {
        "rule_numbers": ["423.1.a.1"],
        "questions": [
            "If I stun a unit that's already stunned, does anything extra happen?",
            "Can a Stunned unit be Stunned again?",
        ],
        "answer": "No",
        "reason": "E1 states a Stunned unit can't be Stunned again.",
        "evidence_ids": ["E1"],
        "verdict": "No",
        "explanation": (
            "No — a unit that's already Stunned can't be Stunned again. Attempting to stun it a "
            "second time doesn't do anything further, and abilities that specifically trigger \"when "
            "you stun\" a unit won't trigger from that redundant attempt either."
        ),
    },
    {
        "rule_numbers": ["425.1.a"],
        "questions": [
            "If a spell is countered, does it still deal its damage?",
            "If Defy counters a spell, does that countered spell still deal its damage?",
            "Does a countered card or ability still resolve its effect?",
        ],
        "answer": "No",
        "reason": "E1 states a card or ability that is Countered does nothing and is cleared from the chain.",
        "evidence_ids": ["E1"],
        "verdict": "No",
        "explanation": (
            "No — a countered spell does nothing at all, including not dealing its damage. A card or "
            "ability that's Countered \"does nothing and is cleared from the chain\" — it's removed "
            "before it ever resolves, so none of its effects (damage included) happen."
        ),
    },
    {
        "rule_numbers": ["425.1.c"],
        "questions": [
            "If my spell gets countered, do I get its costs back?",
            "Does countering a card refund the costs paid to play it?",
        ],
        "answer": "No",
        "reason": "E1 states countering does not refund any costs paid to play a card, activate an ability, or trigger an ability.",
        "evidence_ids": ["E1"],
        "verdict": "No",
        "explanation": (
            "No — countering never refunds costs. Whatever you paid to play the card, activate the "
            "ability, or trigger the ability stays paid even though the card or ability itself does "
            "nothing once countered."
        ),
    },
    {
        "rule_numbers": ["425.1.b"],
        "questions": [
            "If a spell is countered, does it still count as being played for other abilities that trigger on spells being played?",
            "Does a countered card still trigger 'whenever you play a spell' abilities?",
        ],
        "answer": "No",
        "reason": "E1 states a card that is Countered is not considered to have been played for abilities that trigger on cards being played.",
        "evidence_ids": ["E1"],
        "verdict": "No",
        "explanation": (
            "No — a countered card isn't considered to have been played at all for that purpose. "
            "Other abilities that trigger specifically on cards being played won't trigger off a card "
            "that ends up Countered."
        ),
    },
    {
        "rule_numbers": ["142.4.a", "142.4.b", "143.2.a"],
        "questions": [
            "Does marked damage on a unit reduce its Might?",
            "If a unit has damage marked on it, does that lower its Might stat?",
            "My unit has 5 Might and 3 damage marked on it — is its Might now 2?",
            "Does taking damage permanently weaken a unit's Might?",
            "If my unit has damage on it already, is its printed Might still accurate?",
            "Does damage marked on a unit get subtracted from its Might when checking abilities that care about Might?",
        ],
        "answer": "No",
        "reason": "E1/E2 define Lethal Damage as the marked-damage amount needed to kill a unit relative to its Might, and E3 confirms a unit is Killed once marked damage equals or exceeds Might — damage is tracked separately and compared against Might, never subtracted from it.",
        "evidence_ids": ["E1", "E2", "E3"],
        "verdict": "No",
        "explanation": (
            "No — marked damage doesn't reduce a unit's Might. Might and marked damage are two "
            "separate, independently-tracked values. Lethal Damage — the amount that will kill the "
            "unit — is defined as \"a non-zero amount greater than or equal to that Unit's Might,\" "
            "meaning damage is compared against the unit's Might to determine when it dies, not "
            "subtracted from the Might number itself. A unit with 5 Might and 3 damage marked on it "
            "still has 5 Might; it just needs 2 more marked damage to reach lethal."
        ),
    },
    {
        "rule_numbers": ["814.2"],
        "questions": [
            "If a unit gains Shield from two different sources, do the Shield values add up?",
            "Does Shield stack when a unit is granted it by more than one source?",
        ],
        "answer": "Yes",
        "reason": "E1 states that if a unit already has Shield and is granted Shield by an additional source, the Shield Values are summed.",
        "evidence_ids": ["E1"],
        "verdict": "Yes",
        "explanation": (
            "Yes — Shield values from multiple sources add together. If a unit already has Shield and "
            "gains it from an additional source, the granted Shield Values are summed rather than one "
            "replacing the other."
        ),
    },
    {
        "rule_numbers": ["431.2.a", "431.2.b", "431.2.c", "431.2.d", "431.3.a"],
        "questions": [
            "If my deck runs out of cards, do I lose the game immediately?",
            "What happens if I have to draw and my Main Deck is empty?",
            "Does running out of cards in my deck cause an instant loss?",
        ],
        "answer": "No",
        "reason": "E1-E4 describe Burning Out as recycling your trash into your deck and giving an opponent 1 point, not an instant loss; E5 confirms this repeats rather than ending the game outright.",
        "evidence_ids": ["E1", "E2", "E3", "E4"],
        "verdict": "No",
        "explanation": (
            "No — running out of cards doesn't cause an instant loss. Instead, you Burn Out: you "
            "recycle your trash back into your Main Deck (randomizing it), give an opponent 1 point, "
            "and then complete whatever action caused you to run out (such as drawing the card you "
            "needed). If your trash is also empty, this repeats — you keep giving away points each "
            "time — until an opponent's points reach the win threshold, at which point they win. "
            "There's no separate \"deck-out\" loss condition; it's all handled through this "
            "point-scoring loop."
        ),
    },
    {
        "rule_numbers": ["817.2"],
        "questions": [
            "If I have two sources of Vision, do they trigger separately?",
            "Do multiple instances of Vision each trigger on their own?",
        ],
        "answer": "Yes",
        "reason": "E1 states multiple instances of Vision trigger separately.",
        "evidence_ids": ["E1"],
        "verdict": "Yes",
        "explanation": (
            "Yes — each instance of Vision triggers on its own. Having two sources of Vision means "
            "you get two separate triggers, not one combined trigger."
        ),
    },
]

# ---------------------------------------------------------------------------
# Category 2: insufficient-evidence calibration — genuinely off-topic, plus plausible-sounding but
# nonexistent Riftbound mechanics. "Blinded" was confirmed to have zero mentions anywhere in the
# current rules corpus before being used here.
# ---------------------------------------------------------------------------
INSUFFICIENT_CASES = [
    {
        "questions": [
            "If a unit with Vision is also Blinded, does Blinded cancel out Vision's effect?",
            "Does the Blinded status stop a unit's Vision keyword from working?",
        ],
        "evidence_topic": ("817.1", "Vision"),
        "missing": "A rule or card ability that defines a 'Blinded' status in Riftbound — no such mechanic appears anywhere in the supplied rules.",
        "explanation": (
            "I don't have rules evidence that establishes this — \"Blinded\" isn't a status or "
            "mechanic that appears anywhere in Riftbound's rules. I can tell you Vision is a real "
            "keyword, but I can't say how it would interact with something that isn't defined in "
            "this game, so I'm not going to guess."
        ),
    },
    {
        "questions": [
            "Can a Frozen unit still attack?",
            "Does Frozen stop a unit from being exhausted?",
        ],
        "evidence_topic": ("414", "Exhaust"),
        "missing": "A rule or card ability that defines a 'Frozen' status in Riftbound — no such mechanic appears anywhere in the supplied rules.",
        "explanation": (
            "I don't have rules evidence that establishes this — \"Frozen\" isn't a status that "
            "appears anywhere in Riftbound's rules, so I can't say how it would interact with "
            "anything else in the game. I'm not going to guess at a mechanic that isn't defined."
        ),
    },
    {
        "questions": [
            "If my unit is Poisoned, does it take damage every turn?",
            "How does the Poison status work in Riftbound?",
        ],
        "evidence_topic": ("142", "Damage"),
        "missing": "A rule or card ability that defines a 'Poison' or 'Poisoned' status in Riftbound — no such mechanic appears anywhere in the supplied rules.",
        "explanation": (
            "I don't have rules evidence that establishes this — \"Poison\"/\"Poisoned\" isn't a "
            "status that appears anywhere in Riftbound's rules. I can't describe how it would work "
            "when it isn't actually a mechanic in this game."
        ),
    },
    {
        "questions": [
            "Does Petrify stop a unit from blocking?",
            "Can a Corrupted unit still be targeted by spells?",
        ],
        "evidence_topic": ("423", "Stun"),
        "missing": "A rule or card ability that defines 'Petrify' or 'Corrupted' in Riftbound — no such mechanic appears anywhere in the supplied rules.",
        "explanation": (
            "I don't have rules evidence that establishes this — that isn't a status or mechanic "
            "that appears anywhere in Riftbound's rules, so I'm not going to guess at how it would "
            "work."
        ),
    },
    {
        "questions": [
            "What's the weather like today?",
            "How do I cook pasta?",
            "What is the capital of France?",
            "Can you recommend a good movie?",
            "How much does a booster pack cost?",
            "When is the next Riftbound set releasing?",
            "Who is the best Riftbound player in the world?",
            "What's your favorite card?",
        ],
        "evidence_topic": ("414", "Exhaust"),
        "missing": "This question is outside the scope of Riftbound's official rules, keywords, errata, and card legality.",
        "explanation": (
            "I don't have official Riftbound rules evidence that addresses this question — it's "
            "outside what I can answer from the rules library. I can only answer questions about "
            "Riftbound's official rules, keywords, errata, and card legality."
        ),
    },
]

# ---------------------------------------------------------------------------
# Category 3: open-ended descriptive questions ("how does X work") within the adjudication format.
#
# Found in round-1 testing: RulesAnswerService attempts adjudication for every question uniformly,
# not just yes/no rulings, but round 1's training data only ever showed the model yes/no/insufficient
# issues — never a purely descriptive one. Asked "How does Exhaust work?", the round-1 model fell
# back to copying the adjudication system prompt's own "Can a player sacrifice a Rune..." few-shot
# example almost verbatim, the exact copying failure anti-copying instructions were supposed to
# prevent — because it had never seen a descriptive question handled inside this format and had
# nothing else to pattern-match against. ANSWER is "Yes" by convention here (there's no real yes/no
# question being decided, just a fact being stated) and REASON carries the actual definition.
# ---------------------------------------------------------------------------
DESCRIPTIVE_CASES = [
    {
        "rule_numbers": ["414.1", "414.1.a", "414.2", "414.5"],
        "questions": ["How does Exhaust work?", "What does Exhaust mean?", "Explain the Exhaust keyword."],
        "reason": "E1 defines Exhausting as marking a Game Object \"spent\" (rotated 90 degrees), E3 says Exhausted is a state other effects can reference, and E4 says the Exhaust symbol represents the cost \"Exhaust this.\"",
        "evidence_ids": ["E1", "E3", "E4"],
        "explanation": (
            "Exhausting is an action that marks a non-spell Game Object on the board as \"spent\" — "
            "you show this by rotating the card 90 degrees. Once something is Exhausted, that's a "
            "state other rules and effects can check or reference. Most Exhaust actions come up as "
            "costs — a card's ability might read \"Exhaust this\" or \"Exhaust me,\" shown by the "
            "Exhaust symbol, which represents paying that cost. An already-Exhausted object can't be "
            "Exhausted again."
        ),
    },
    {
        "rule_numbers": ["415.1", "415.2"],
        "questions": ["How does Ready work?", "What does the Ready state mean?"],
        "reason": "E1 defines Readying as marking a Game Object as available for action, and E2 says Ready is a state other rules and effects can reference.",
        "evidence_ids": ["E1", "E2"],
        "explanation": (
            "Readying is an action that marks a non-spell Game Object on the board as available for "
            "action — it's the opposite of Exhausted. Ready is a state other rules and card effects "
            "can check or reference, such as a spell that can only target Ready units."
        ),
    },
    {
        "rule_numbers": ["815.1", "815.1.b", "815.2", "815.3"],
        "questions": ["How does Tank work?", "What does the Tank keyword do?", "Explain Tank."],
        "reason": "E2 defines Tank as forcing lethal combat damage to be assigned to it before other units without Tank during the Combat Damage step; E3 says multiple instances are redundant.",
        "evidence_ids": ["E2", "E3"],
        "explanation": (
            "Tank is a passive ability keyword. It's functionally short for \"I must be assigned "
            "lethal damage before any other unit with the same controller as me that does not have "
            "Tank, during the Combat Damage step\" — so during combat, a player has to finish "
            "assigning lethal damage to their Tank units before assigning it to non-Tank units. It "
            "only affects that combat-damage assignment order — it doesn't affect spell targeting. "
            "Multiple instances of Tank on the same unit are redundant; having it twice doesn't do "
            "anything extra."
        ),
    },
    {
        "rule_numbers": ["425.1", "425.1.a", "425.1.b", "425.1.c"],
        "questions": ["How does Counter work?", "What happens when a spell is countered?", "Explain Countering."],
        "reason": "E2 says a Countered card or ability does nothing and is cleared from the chain, E3 says it isn't considered to have been played, and E4 says its costs are never refunded.",
        "evidence_ids": ["E2", "E3", "E4"],
        "explanation": (
            "Countering negates the execution, activation, or playing of a card or ability. A "
            "Countered card or ability does nothing at all and is cleared from the chain before it "
            "ever resolves — that includes not dealing damage or doing anything else its text says. "
            "It also isn't considered to have been played for abilities that trigger on cards being "
            "played, and countering never refunds the costs that were paid to play it."
        ),
    },
    {
        "rule_numbers": ["817.1", "817.2", "817.3"],
        "questions": ["How does Vision work?", "What does the Vision keyword do?", "Explain Vision."],
        "reason": "E1 says Vision is a Triggered Ability keyword, and E2 says multiple instances trigger separately.",
        "evidence_ids": ["E1", "E2"],
        "explanation": (
            "Vision is a Triggered Ability keyword. If a unit has more than one instance of Vision, "
            "each one triggers separately rather than combining into a single trigger. Vision, and "
            "whether or not a permanent has it, is a characteristic other game effects can check."
        ),
    },
    {
        "rule_numbers": ["431.1", "431.2.a", "431.2.b", "431.2.c", "431.2.d"],
        "questions": ["How does Burn Out work?", "What happens when I run out of cards in my deck?"],
        "reason": "E1 says Burning Out happens when a player would move cards from an empty Main Deck; E2-E5 describe the sequence: perform what's possible, recycle the trash into the deck, give an opponent 1 point, then finish the original action.",
        "evidence_ids": ["E1", "E2", "E3", "E4", "E5"],
        "explanation": (
            "Burning Out is what happens when you're required to move one or more cards from your "
            "Main Deck (most commonly, drawing) but there aren't enough cards left in it. When that "
            "happens: you perform as much of the action as you can, recycle your trash into your Main "
            "Deck (randomizing it), give an opponent 1 point, and then complete the rest of the "
            "original action. It isn't an instant loss — if your trash is also empty, you'll keep "
            "burning out and giving away points each time until an opponent reaches the win "
            "threshold."
        ),
    },
]


def build_descriptive_examples(cur):
    examples = []
    for case in DESCRIPTIVE_CASES:
        clean_issue = {"question": None, "answer": "Yes", "reason": case["reason"], "evidence_ids": case["evidence_ids"]}
        for question in case["questions"]:
            # Fresh noise padding + shuffle per paraphrase, not once per case — the model should
            # learn to find the signal regardless of what specific noise surrounds it, not memorize
            # one fixed noisy arrangement paired with one question wording.
            evidence, id_map = evidence_from_rules_with_noise(cur, case["rule_numbers"])
            evidence_by_id = {eid: (label, authority, current, text) for eid, label, authority, current, text in evidence}
            issue = remap_issue(clean_issue, id_map)
            issue["question"] = question
            issue["quotes"] = [evidence_by_id[eid] for eid in issue["evidence_ids"]]
            examples.append(make_adjudication_example(question, evidence, [issue], "Yes"))
            examples.append(make_explanation_example(question, [issue], "Yes", case["explanation"]))
    return examples


def build_insufficient_examples(cur):
    examples = []
    for case in INSUFFICIENT_CASES:
        rule_number, _title = case["evidence_topic"]
        clean_issue = {"question": None, "answer": "Insufficient",
                        "reason": f"The supplied evidence doesn't establish this — {case['missing']}",
                        "evidence_ids": ["E1"]}
        for question in case["questions"]:
            evidence, id_map = evidence_from_rules_with_noise(cur, [rule_number])
            evidence_by_id = {eid: (label, authority, current, text) for eid, label, authority, current, text in evidence}
            issue = remap_issue(clean_issue, id_map)
            issue["question"] = question
            issue["missing"] = case["missing"]
            issue["quotes"] = [evidence_by_id[eid] for eid in issue["evidence_ids"]]
            examples.append(make_adjudication_example(question, evidence, [issue], "Insufficient evidence"))
            examples.append(make_explanation_example(question, [issue], "Insufficient evidence", case["explanation"]))
    return examples


def build_ruling_examples(cur):
    examples = []
    for case in RULING_CASES:
        clean_issue = {"question": None, "answer": case["answer"], "reason": case["reason"],
                        "evidence_ids": case["evidence_ids"]}
        for question in case["questions"]:
            evidence, id_map = evidence_from_rules_with_noise(cur, case["rule_numbers"])
            evidence_by_id = {eid: (label, authority, current, text) for eid, label, authority, current, text in evidence}
            issue = remap_issue(clean_issue, id_map)
            issue["question"] = question
            issue["quotes"] = [evidence_by_id[eid] for eid in issue["evidence_ids"]]
            examples.append(make_adjudication_example(question, evidence, [issue], case["verdict"]))
            examples.append(make_explanation_example(question, [issue], case["verdict"], case["explanation"]))
    return examples


def build_errata_examples(cur):
    cur.execute("""
        SELECT ce.CardNameRaw, ce.OriginalText, ce.CorrectedText, rd.Title as DocTitle
        FROM CardErrata ce JOIN RuleDocuments rd ON ce.DocumentId = rd.Id
        WHERE ce.IsCurrent = 1
    """)
    examples = []
    for row in cur.fetchall():
        name, original, corrected, doc_title = row["CardNameRaw"], row["OriginalText"], row["CorrectedText"], row["DocTitle"]
        question = random.choice([
            f"Has {name} received any errata?", f"Did {name}'s card text change?", f"What was {name}'s original text before errata?",
        ])
        evidence = [("E1", name, "OfficialErrata", True, f"Original: {original}\nUpdated: {corrected}")]
        reason = f"E1 shows {name}'s original and corrected text differ, confirming errata was issued ({doc_title})."
        issue = {"question": question, "answer": "Yes", "reason": reason, "evidence_ids": ["E1"],
                  "quotes": [(evidence[0][1], evidence[0][2], evidence[0][3], evidence[0][4])]}
        explanation = (
            f"Yes — {name} received official errata ({doc_title}). "
            f"The original text was: \"{original}\" It was updated to: \"{corrected}\""
        )
        examples.append(make_adjudication_example(question, evidence, [issue], "Yes"))
        examples.append(make_explanation_example(question, [issue], "Yes", explanation))
    return examples


def build_legality_examples(cur):
    legality_status_names = ["Legal", "Banned", "Restricted", "NotLegal"]
    cur.execute("SELECT CardId, CardNameRaw, Format, Status FROM CardLegalities WHERE IsCurrent = 1 AND CardId IS NOT NULL")
    rows = cur.fetchall()
    examples = []
    for row in rows:
        name, fmt, status = row["CardNameRaw"], row["Format"], legality_status_names[row["Status"]]
        question = random.choice([
            f"Is {name} banned in {fmt}?", f"Can I play {name} in {fmt}?", f"What is {name}'s legality status in {fmt}?",
        ])
        verb = "is not legal (banned)" if status.lower() == "banned" else f"is {status.lower()}"
        answer_text = f"{name} {verb} in {fmt}."
        evidence = [("E1", name, "CoreRules", True, answer_text)]
        issue = {"question": question, "answer": "Yes" if status != "Banned" else "No",
                  "reason": f"E1 states {name}'s legality status directly for {fmt}.", "evidence_ids": ["E1"],
                  "quotes": [(evidence[0][1], evidence[0][2], evidence[0][3], evidence[0][4])]}
        examples.append(make_adjudication_example(question, evidence, [issue], issue["answer"]))
        examples.append(make_explanation_example(question, [issue], issue["answer"], answer_text))
    return examples


def build_single_pass_examples(cur):
    """Supplementary single-pass (ExplainAsync-shape) examples for genuinely descriptive questions
    that don't fit the adjudication Yes/No/Insufficient shape — rule lookups and card-ability
    descriptions. Kept modest in volume (this model's PRIMARY task is adjudication); just enough
    that the fallback path this model still uses when adjudication doesn't validate isn't worse
    than before for it. Card-ability handling mirrors generate_dataset.py's categories 7/8
    (bracket-keyword-aware description, full bracket-card catalog, partial-evidence honesty) —
    real, already-proven fixes from earlier training rounds on the original single-pass model,
    reused here rather than the thinner "quote the raw text" version this had in round 1."""
    examples = []

    cur.execute("SELECT RuleNumber, Title, Text FROM RuleEntries WHERE IsCurrent = 1 AND RuleNumber IS NOT NULL")
    all_rules = cur.fetchall()
    for row in random.sample(all_rules, min(80, len(all_rules))):
        number, text = row["RuleNumber"], row["Text"]
        question = random.choice([f"What does rule {number} say?", f"What does Rule {number} mean?", f"Can you explain rule {number}?"])
        source = {"ruleNumber": number, "title": row["Title"] or f"Rule {number}", "authority": "CoreRules", "current": True, "text": text}
        examples.append(make_single_pass_example(question, [source], f"Rule {number} states: {text}"))

    # Every card with printed text, not a sample — full-catalog coverage was an explicit requirement,
    # not an optimization to skip. See build_ruling_examples' oversampling in main() for how the
    # adjudication-format signal is kept strong despite this category's much larger size.
    cur.execute("SELECT Id, Name, TextPlain FROM Cards WHERE TextPlain IS NOT NULL AND TextPlain != ''")
    all_cards = cur.fetchall()
    question_templates = ["What does {name} do?", "How does {name} work?", "Explain {name}'s ability.",
                           "{name} rules", "What is {name}'s effect?", "When can I use {name}'s ability?",
                           "What triggers {name}'s effect?", "How does {name}'s skill operate?"]
    for card in all_cards:
        name = card["Name"]
        humanized = humanize(card["TextPlain"])
        question = random.choice(question_templates).format(name=name)
        source = {"ruleNumber": None, "title": name, "authority": "CardText", "current": True, "text": humanized}
        examples.append(make_single_pass_example(question, [source], describe_card_text(name, humanized)))

    # Partial-evidence honesty — mirrors generate_dataset.py category 8 exactly (found by testing
    # a real question about a card's timing/interaction the card's own text doesn't resolve; the
    # model answered "Yes" anyway and fabricated a nonexistent parenthetical). Without this, a model
    # trained only on "the card's text fully answers the question" cases never learns that having
    # SOME evidence about a card doesn't mean every question about it is answerable from that
    # evidence.
    partial_templates = [
        ("Does {name}'s ability work on the opponent's turn?", "whether this triggers during your opponent's turn specifically, as opposed to only your own"),
        ("Can {name}'s trigger happen more than once in the same turn?", "whether this can trigger more than once in a single turn"),
        ("Does {name}'s effect stack if I control two copies?", "whether the effects of two copies stack with each other"),
        ("Can I respond to {name}'s triggered ability?", "whether this specific trigger can be responded to before it resolves"),
        ("Does {name}'s ability still work while it's Stunned?", "whether being Stunned affects this specific ability"),
    ]
    for card in random.sample(all_cards, min(60, len(all_cards))):
        name = card["Name"]
        humanized = humanize(card["TextPlain"])
        question_template, topic = random.choice(partial_templates)
        question = question_template.format(name=name)
        source = {"ruleNumber": None, "title": name, "authority": "CardText", "current": True, "text": humanized}
        answer = (
            f"{name}'s printed text says: \"{humanized}\" That tells you what the card does, but it "
            f"doesn't say anything about {topic} — I don't have rules evidence that clearly "
            f"establishes that, so I can't say for sure either way."
        )
        examples.append(make_single_pass_example(question, [source], answer))

    return examples


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    examples = []
    print("Hand-verified interaction rulings...")
    ruling_examples = build_ruling_examples(cur)
    examples += ruling_examples
    print(f"  {len(ruling_examples)} examples ({len(RULING_CASES)} rulings x paraphrases x 2 stages)")

    print("Insufficient-evidence calibration...")
    insufficient_examples = build_insufficient_examples(cur)
    examples += insufficient_examples
    print(f"  {len(insufficient_examples)} examples")

    print("Descriptive questions (adjudication-format)...")
    descriptive_examples = build_descriptive_examples(cur)
    examples += descriptive_examples
    print(f"  {len(descriptive_examples)} examples")

    print("Errata...")
    errata_examples = build_errata_examples(cur)
    examples += errata_examples
    print(f"  {len(errata_examples)} examples")

    print("Legality...")
    legality_examples = build_legality_examples(cur)
    examples += legality_examples
    print(f"  {len(legality_examples)} examples")

    # This dataset's actual point is the adjudication format — everything above this line. Full
    # per-card coverage (below) is comprehensive by design, but at ~1300+ cards it would otherwise
    # outnumber the adjudication-format examples by 6-7x, which risks the gradient updates being
    # dominated by the single-pass task and the (much smaller, much more valuable) adjudication
    # signal getting diluted — the exact failure mode this whole retrain exists to fix. Oversampling
    # (not deduplicating the card set instead) keeps every card's coverage while restoring a healthy
    # ratio; round 1 (a roughly 1:1 mix) already validated on 7/7 real test questions, so this keeps
    # that same proportion in the ballpark rather than guessing at a new one.
    adjudication_format_examples = list(examples)
    oversample_factor = 4
    examples = examples * oversample_factor
    print(f"Oversampled {len(adjudication_format_examples)} adjudication-format examples x{oversample_factor} = {len(examples)}")

    print("Supplementary single-pass (descriptive) examples...")
    single_pass_examples = build_single_pass_examples(cur)
    examples += single_pass_examples
    print(f"  {len(single_pass_examples)} examples")

    random.shuffle(examples)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"\nWrote {len(examples)} examples to {OUT_PATH}")


if __name__ == "__main__":
    main()
