from __future__ import annotations

import re
from typing import Any

from .compiler import is_concept_title, TOKEN_DEFINITION_RE


def _ruleid_sort_key(rule_id: str) -> tuple:
    """Order key for rule IDs that may be plain ("706") or dotted ("187.1") - concept ruleIds were
    previously always plain (only depth==1 title rules qualified), but Rule 187's token catalog
    concepts are dotted, and a bare int() cast can't parse those."""
    parts: list[tuple[int, Any]] = []
    for p in re.split(r"[.]", rule_id or ""):
        m = re.match(r"^(\d+)([a-z]*)$", p, flags=re.I)
        if m:
            parts.append((0, int(m.group(1))))
            parts.append((1, m.group(2) or ""))
        else:
            parts.append((2, p))
    return tuple(parts)


DEFINITION_PATTERNS = [
    re.compile(r"\bwhat does\b.*\bmean\b", re.I),
    re.compile(r"\bwhat is\b", re.I),
    re.compile(r"\bdefine\b", re.I),
    re.compile(r"\bhow does\b.*\bwork\b", re.I),
    re.compile(r"\brules? for\b", re.I),
    re.compile(r"\bexplain\b", re.I),
]


# Only words that could never themselves be a real concept's own name - "game action" and "rule"
# are deliberately handled as atomic two/one-word PHRASES below instead, not added here, because
# "Action" and (in principle) "Rule" can be real standalone keyword names on their own (confirmed
# directly: rule 806 is literally the keyword "Action" - an earlier version of this set included
# bare "action", which normalized "Action" itself down to an empty string and broke its own lookup).
_FILLER_WORDS = {"the", "a", "an", "token", "tokens", "card", "cards", "keyword", "keywords", "ability", "abilities"}
_TYPE_PHRASE_RE = re.compile(r"^(?:keyword|game action|rule|ability)\s+|\s+(?:keyword|game action|rule|ability)$", re.I)


def _normalize_direct_definition_target(text: str) -> str:
    target = (text or "").strip().replace("’", "'")
    target = re.sub(r"^[\[\(\{\"']+|[\]\)\}\"']+$", "", target).strip()
    # Parameterized keywords such as Shield 2 still ask for the Shield definition.
    target = re.sub(r"\s+\d+$", "", target).strip()
    # Strip a leading/trailing type-word phrase and single filler words repeatedly and in either
    # order - "Token Brush Card", "Brush Token", and "the Brush" should all reduce the same way
    # "Brush" alone does. Interior words are never touched, so a real concept name like "Brush
    # battlefield" (where "battlefield" isn't filler, it's the actual name) is unaffected.
    changed = True
    while changed:
        changed = False
        stripped = _TYPE_PHRASE_RE.sub("", target).strip()
        if stripped != target:
            target, changed = stripped, True
        words = target.split()
        if words and words[0].casefold() in _FILLER_WORDS:
            words.pop(0)
            target, changed = " ".join(words), True
        elif words and words[-1].casefold() in _FILLER_WORDS:
            words.pop()
            target, changed = " ".join(words), True
    return re.sub(r"\s+", " ", target).strip().casefold()


def _is_bare_concept_mention(question: str, concepts: list[dict[str, Any]] | None) -> bool:
    """A question that, once filler words are stripped, IS entirely a known concept's name/alias
    and nothing else - "Brush", "brush battlefield", "Token Brush Card" - is a definition lookup by
    construction: there's no other reasonable thing a bare card/token/keyword name typed into Ask
    Rules could mean. Confirmed missing directly: the earlier Rule 187 token-catalog fix added the
    concepts themselves but every existing definition-intent trigger requires an explicit phrase
    ("what is", "explain", "how do I play") - a bare mention with no such phrase never reached the
    concept lookup at all despite the concept being right there in the catalog."""
    if not concepts:
        return False
    target = _normalize_direct_definition_target(question)
    if not target:
        return False
    for concept in concepts:
        names = [concept.get("name", ""), *concept.get("aliases", [])]
        for name in names:
            if _normalize_direct_definition_target(str(name)) == target:
                return True
    return False


def _is_exact_do_definition(question: str, concepts: list[dict[str, Any]] | None) -> bool:
    if not concepts:
        return False
    m = re.match(r"^\s*what\s+does\s+(.+?)\s+do\s*[?.!]*\s*$", question or "", flags=re.I)
    if not m:
        return False
    target = _normalize_direct_definition_target(m.group(1))
    if not target:
        return False
    for concept in concepts:
        names = [concept.get("name", ""), *concept.get("aliases", [])]
        for name in names:
            if _normalize_direct_definition_target(str(name)) == target:
                return True
    return False


def _is_exact_how_to_play_definition(question: str, concepts: list[dict[str, Any]] | None) -> bool:
    if not concepts:
        return False
    m = re.match(r"^\s*how\s+(?:do|can|would)\s+(?:i|you)\s+play\s+(.+?)\s*[?.!]*\s*$", question or "", flags=re.I)
    if not m:
        m = re.match(r"^\s*how\s+to\s+play\s+(.+?)\s*[?.!]*\s*$", question or "", flags=re.I)
    if not m:
        return False
    target = _normalize_direct_definition_target(m.group(1))
    if not target:
        return False
    for concept in concepts:
        names = [concept.get("name", ""), *concept.get("aliases", [])]
        for name in names:
            if _normalize_direct_definition_target(str(name)) == target:
                return True
    return False


def is_definition_intent(question: str, concepts: list[dict[str, Any]] | None = None) -> bool:
    if any(p.search(question or "") for p in DEFINITION_PATTERNS):
        return True
    # Player phrasing such as "What does Tank do?" is a definition lookup only
    # when the entire subject is an explicitly matched rules concept. This avoids
    # hijacking scenario questions such as "What does my unit do after I play it?".
    if _is_exact_do_definition(question, concepts):
        return True
    # Similarly, "How do I play the Brush Battlefield card?" only becomes a definition
    # lookup when its entire subject is an explicit concept - most things named this way
    # aren't cards you play at all (e.g. Rule 187's tokens, created by other effects rather
    # than played from hand), so the honest answer is what it actually is, not a decline.
    # Ordinary gameplay questions like "How do I play a unit to a battlefield I control?"
    # never exactly match a concept name/alias, so they fall through untouched.
    if _is_exact_how_to_play_definition(question, concepts):
        return True
    # A bare mention with no question phrase at all - "Brush", "brush battlefield", "Token Brush
    # Card" - still needs to resolve; nothing else could reasonably route it anywhere else.
    return _is_bare_concept_mention(question, concepts)


def find_concepts(question: str, semantic_ir: dict[str, Any], max_matches: int = 8) -> list[dict[str, Any]]:
    q = (question or "").lower().replace("’", "'")
    matches = []
    for c in semantic_ir.get("conceptCatalog", {}).get("concepts", []):
        names = sorted(set([c["name"].lower()] + [a.lower() for a in c.get("aliases", [])]), key=len, reverse=True)
        hit = None
        for name in names:
            if len(name) < 3:
                continue
            if re.search(rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])", q):
                hit = name
                break
        if hit:
            matches.append({**c, "matchedAlias": hit})
    matches.sort(key=lambda c: (-len(c["matchedAlias"]), _ruleid_sort_key(c["ruleId"])))
    # Avoid major-section umbrella concepts when a more specific concept is explicitly matched.
    specific = [m for m in matches if m["category"] not in {"major_section", "keyword_section"}]
    return (specific or matches)[:max_matches]


def concept_rule_bundle(core: dict[str, Any], concept: dict[str, Any], max_rules: int = 60) -> list[dict[str, Any]]:
    rid = concept["ruleId"]
    rules = core["rules"]
    start = next((i for i, r in enumerate(rules) if r["ruleId"] == rid), None)
    if start is None:
        return []
    rows: list[dict[str, Any]] = []
    for i in range(start, len(rules)):
        r = rules[i]
        if i > start and r.get("depth") == 1 and is_concept_title(r):
            break
        # Rule 187's token catalog is unlike Mighty-style families (706 "Mighty" is a bare title
        # whose definition legitimately spans untitled sibling rules 707-711, stopped only by the
        # next real title at 712): each token type is itself a complete, self-contained definition
        # in one sentence, immediately followed by an unrelated sibling token's definition rather
        # than a continuation. Reaching another one mid-walk means the current concept's bundle is
        # already complete.
        if i > start and TOKEN_DEFINITION_RE.match(r.get("normativeText") or ""):
            break
        rows.append(r)
        if len(rows) >= max_rules:
            break
    return rows


def build_definition_ruling(question: str, core: dict[str, Any], concepts: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not concepts or not is_definition_intent(question, concepts):
        return None
    # If the same official term has multiple rule meanings (for example Empower is
    # both a Game Action and a Keyword), return every exact-name family rather than
    # silently picking the lower rule number. Unrelated partial matches stay excluded.
    primary = concepts[0]
    primary_name = primary["name"].strip().lower()
    selected = [c for c in concepts if c["name"].strip().lower() == primary_name]
    if not selected:
        selected = [primary]

    evidence: list[dict[str, Any]] = []
    seen: set[str] = set()
    for concept in selected:
        for r in concept_rule_bundle(core, concept):
            if not r.get("normativeText") or r["ruleId"] in seen:
                continue
            seen.add(r["ruleId"])
            evidence.append({
                "evidenceId": f"R:{r['ruleId']}",
                "ruleId": r["ruleId"],
                "text": r.get("normativeText") or r.get("text") or "",
                "pageStart": r.get("pageStart"),
                "pageEnd": r.get("pageEnd"),
                "sourceId": r.get("sourceId"),
            })
    if not evidence:
        return None
    if len(selected) == 1:
        claim = f"Official {selected[0]['category'].replace('_',' ')} rules for {selected[0]['name']}."
        reason = f"Showing the authoritative rule family for {selected[0]['name']}."
    else:
        cats = ", ".join(c["category"].replace("_", " ") for c in selected)
        claim = f"{primary['name']} has multiple official rules meanings ({cats}); all matching rule families are included."
        reason = f"Showing all authoritative rule families named {primary['name']}."
    return {
        "status": "decided",
        "issue": question,
        "outcomes": [
            {
                "claim": claim,
                "verdict": "definition",
                "truth": "true",
                "evidence": evidence,
                "concept": primary,
                "concepts": selected,
            }
        ],
        "effectiveVerdict": {"verdict": "definition", "reason": reason, "basis": [e["evidenceId"] for e in evidence]},
    }


def normalize_quote_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("’", "'").replace("‘", "'")).strip().rstrip(".").casefold()


def _question_quotes_rule_verbatim(question: str, rule: dict[str, Any]) -> bool:
    """True when a rule's own normativeText appears verbatim (post-normalization) inside the
    question. A synthetic-corpus pattern ("The situation involves this rule concept: <rule
    text>. How is that supposed to work?") embeds the real rule sentence directly - full-text
    retrieval finds the right rule for these far more reliably than concept-name substring
    matching does (a keyword like "Play" or "Action" appearing incidentally in unrelated
    phrasing can otherwise hijack the concept match; confirmed directly against real failing
    questions). Requiring an exact quoted substring rather than topical similarity keeps this
    from ever guessing: either the question is quoting this specific rule's own words or it
    isn't - a bare section title (e.g. "Beginning Phase", 15 chars) is excluded by length alone
    since it trivially appears inside any ordinary scenario question that mentions that
    phase/section by name; confirmed directly as a real false positive against gold-corpus
    regression case GA-041 ("During my Beginning Phase..." hijacked by rule 315.2's bare title
    "Beginning Phase" before this guard existed). Deliberately no terminal-punctuation
    requirement on top of that: plenty of legitimate rule clauses are spec/table-style entries
    with no trailing period (e.g. Rule 103.2's 94-char Main Deck clause), and requiring one
    excluded those real matches without adding any actual safety over the length check alone."""
    text = rule.get("normativeText") or rule.get("text") or ""
    if len(text.strip()) < 40:
        return False
    return normalize_quote_text(text) in normalize_quote_text(question)


def build_definition_ruling_from_retrieval(question: str, top_rules: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Fallback definition lookup for a question that quotes a rule's own text verbatim but
    doesn't name a catalog concept (or would otherwise match the wrong one via
    build_definition_ruling's concept-name search). Only fires on an exact quoted match against
    one of retrieval's own top-ranked rules for this question - never a topical guess, and
    independent of is_definition_intent's phrase patterns since directly quoting a rule's text
    is itself unambiguous evidence of a rule-lookup regardless of how the question is phrased
    around it."""
    for rule in top_rules:
        if _question_quotes_rule_verbatim(question, rule):
            rule_id = rule["ruleId"]
            evidence = [{
                "evidenceId": f"R:{rule_id}",
                "ruleId": rule_id,
                "text": rule.get("normativeText") or rule.get("text") or "",
                "pageStart": rule.get("pageStart"),
                "pageEnd": rule.get("pageEnd"),
                "sourceId": rule.get("sourceId"),
            }]
            return {
                "status": "decided",
                "issue": question,
                "outcomes": [{
                    "claim": f"Official rule text quoted in the question (Rule {rule_id}).",
                    "verdict": "definition",
                    "truth": "true",
                    "evidence": evidence,
                }],
                "effectiveVerdict": {
                    "verdict": "definition",
                    "reason": f"The question quotes Rule {rule_id} verbatim.",
                    "basis": [f"R:{rule_id}"],
                },
            }
    return None


def card_referenced_concepts(card: dict[str, Any], semantic_ir: dict[str, Any], max_matches: int = 12) -> list[dict[str, Any]]:
    """Return rule concepts that a card explicitly carries as rules shorthand.

    For evidence closure we automatically expand only official Keywords. Ordinary words
    such as Unit, Gear, Ability, Ready, or Play can occur frequently in card prose and
    would flood the packet. Those concepts are instead driven by the player's issue.
    """
    text = (card.get("effectiveText") or "").lower().replace("’", "'")
    found = []
    for c in semantic_ir.get("conceptCatalog", {}).get("concepts", []):
        if c.get("category") != "keyword":
            continue
        name = c["name"].lower()
        if re.search(rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])", text):
            found.append(c)
    found.sort(key=lambda c: int(c["ruleId"]))
    return found[:max_matches]


def merge_concept_evidence(core: dict[str, Any], evidence: list[dict[str, Any]], concepts: list[dict[str, Any]], max_rules: int = 130) -> list[dict[str, Any]]:
    out = [dict(r) for r in evidence]
    seen = {r["ruleId"] for r in out}
    for c in concepts:
        for r in concept_rule_bundle(core, c, max_rules=40):
            if r["ruleId"] in seen:
                continue
            x = dict(r)
            x["closureReason"] = f"concept_family:{c['name']}"
            out.append(x)
            seen.add(r["ruleId"])
            if len(out) >= max_rules:
                return out
    return out
