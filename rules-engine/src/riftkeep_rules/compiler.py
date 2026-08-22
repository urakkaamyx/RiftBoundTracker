from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from .graph import classify_semantics
from .rule_compiler import parse_conditions, parse_modalities, classify_effect_types

TITLE_RE = re.compile(r"^[A-Z][A-Za-z0-9'’\- ]{1,79}$")


def is_concept_title(rule: dict[str, Any]) -> bool:
    if rule.get("depth") != 1:
        return False
    text = (rule.get("normativeText") or "").strip()
    if not text or len(text.split()) > 8 or len(text) > 80:
        return False
    if text.endswith((".", ":", ";", "?", "!")):
        return False
    return bool(TITLE_RE.match(text))


def build_concept_catalog(core: dict[str, Any]) -> dict[str, Any]:
    concepts: list[dict[str, Any]] = []
    for r in core["rules"]:
        if not is_concept_title(r):
            continue
        term = r["normativeText"].strip()
        rid_num = int(r["rootRuleId"])
        category = "rule_concept"
        if 413 <= rid_num <= 444:
            category = "game_action"
        elif 805 <= rid_num <= 829:
            category = "keyword"
        elif rid_num == 800:
            category = "keyword_section"
        elif r.get("majorSectionRuleId") == r["ruleId"]:
            category = "major_section"
        aliases = {term.lower()}
        # Conservative morphology for search/definition access only. Keep this
        # deliberately narrow: it is an alias layer, never authoritative text.
        low = term.lower()
        if low.endswith("ing") and len(low) > 5:
            aliases.add(low[:-3])
        if low.endswith("ies") and len(low) > 4:
            aliases.add(low[:-3] + "y")
        elif low.endswith("s") and not low.endswith(("ss", "us", "is")) and len(low) > 3:
            aliases.add(low[:-1])
        elif not low.endswith("s"):
            if low.endswith("y") and len(low) > 2 and low[-2] not in "aeiou":
                aliases.add(low[:-1] + "ies")
            else:
                aliases.add(low + "s")
        concepts.append(
            {
                "conceptId": f"concept:{r['ruleId']}",
                "name": term,
                "ruleId": r["ruleId"],
                "category": category,
                "aliases": sorted(aliases),
                "majorSectionRuleId": r.get("majorSectionRuleId"),
                "majorSectionTitle": r.get("majorSectionTitle"),
            }
        )
    return {"count": len(concepts), "concepts": concepts}


def parse_rule_ir(rule: dict[str, Any]) -> dict[str, Any]:
    text = (rule.get("normativeText") or "").strip()
    conditions, effect, confidence = parse_conditions(text)
    modalities = parse_modalities(text)
    effect_types = classify_effect_types(text, modalities)
    return {
        "ruleId": rule["ruleId"],
        "internalRuleId": rule["internalRuleId"],
        "sourceId": rule["sourceId"],
        "text": text,
        "conditions": conditions,
        "effectText": effect,
        "parseConfidence": confidence,
        "modality": modalities,
        "effectTypes": effect_types,
        "semanticTags": classify_semantics(text),
        "dependencies": list(dict.fromkeys(str(x) for x in (rule.get("resolvedCrossReferences") or []) if x)),
        "executable": False,
        "note": "Textual semantic IR only; conditions are not executable unless a deterministic Rule Program explicitly supports them.",
    }


def compile_semantic_ir(core: dict[str, Any]) -> dict[str, Any]:
    catalog = build_concept_catalog(core)
    concepts = catalog["concepts"]
    mentions: dict[str, list[str]] = defaultdict(list)
    # Prefer longer concept names to avoid matching a shorter term inside a longer one.
    ordered = sorted(concepts, key=lambda c: len(c["name"]), reverse=True)
    for r in core["rules"]:
        text = (r.get("normativeText") or "").lower()
        for c in ordered:
            name = c["name"].lower()
            # Avoid a rule claiming to mention itself solely because its title is its entire text.
            if r["ruleId"] == c["ruleId"] and text.strip() == name:
                continue
            if re.search(rf"(?<![a-z0-9]){re.escape(name)}(?:s|ed|ing)?(?![a-z0-9])", text):
                mentions[r["ruleId"]].append(c["conceptId"])
    rules = []
    for r in core["rules"]:
        ir = parse_rule_ir(r)
        ir["mentionedConceptIds"] = mentions.get(r["ruleId"], [])
        rules.append(ir)
    return {
        "metadata": {
            "conceptCount": len(concepts),
            "ruleIrCount": len(rules),
            "executableRuleCount": 0,
            "policy": "Semantic parsing is conservative. Textual condition decomposition is not treated as executable logic until separately compiled and tested.",
        },
        "conceptCatalog": catalog,
        "rules": rules,
    }
