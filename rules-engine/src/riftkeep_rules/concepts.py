from __future__ import annotations

import re
from typing import Any

from .compiler import is_concept_title

DEFINITION_PATTERNS = [
    re.compile(r"\bwhat does\b.*\bmean\b", re.I),
    re.compile(r"\bwhat is\b", re.I),
    re.compile(r"\bdefine\b", re.I),
    re.compile(r"\bhow does\b.*\bwork\b", re.I),
    re.compile(r"\brules? for\b", re.I),
    re.compile(r"\bexplain\b", re.I),
]


def _normalize_direct_definition_target(text: str) -> str:
    target = (text or "").strip().replace("’", "'")
    target = re.sub(r"^[\[\(\{\"']+|[\]\)\}\"']+$", "", target).strip()
    target = re.sub(r"^the\s+", "", target, flags=re.I)
    target = re.sub(r"\s+(?:keyword|game action|rule|ability)$", "", target, flags=re.I).strip()
    # Parameterized keywords such as Shield 2 still ask for the Shield definition.
    target = re.sub(r"\s+\d+$", "", target).strip()
    return re.sub(r"\s+", " ", target).casefold()


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


def is_definition_intent(question: str, concepts: list[dict[str, Any]] | None = None) -> bool:
    if any(p.search(question or "") for p in DEFINITION_PATTERNS):
        return True
    # Player phrasing such as "What does Tank do?" is a definition lookup only
    # when the entire subject is an explicitly matched rules concept. This avoids
    # hijacking scenario questions such as "What does my unit do after I play it?".
    return _is_exact_do_definition(question, concepts)


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
    matches.sort(key=lambda c: (-len(c["matchedAlias"]), int(c["ruleId"])))
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
