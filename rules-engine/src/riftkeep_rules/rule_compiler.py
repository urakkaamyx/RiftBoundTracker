from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import Any


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def text_hash(text: str) -> str:
    return hashlib.sha256(_norm(text).encode("utf-8")).hexdigest()


def _positive_permission_text(low: str) -> str:
    """Mask negative permission phrases before looking for positive can/may."""
    return re.sub(r"\b(?:can't|cannot|can not|may not)\b", " ", low)


def parse_modalities(text: str) -> list[str]:
    low = _norm(text).casefold()
    positive = _positive_permission_text(low)
    out: set[str] = set()
    if re.search(r"\b(?:can't|cannot|can not|may not)\b", low):
        out.add("prohibition")
    if re.search(r"\bonly\b", low):
        out.add("restriction")
    if re.search(r"\b(?:may|can)\b", positive):
        out.add("permission")
    if re.search(r"\b(?:must|required|requires?)\b", low):
        out.add("requirement")
    return sorted(out)


def parse_conditions(text: str) -> tuple[list[dict[str, Any]], str, str]:
    """Conservative textual condition decomposition; never makes text executable."""
    src = _norm(text)
    conditions: list[dict[str, Any]] = []
    effect = src
    confidence = "none"

    m = re.match(r"^(If|When|While)\s+(.+?),\s+(.+)$", src, flags=re.I)
    if m:
        conditions.append({"connector": m.group(1).casefold(), "text": m.group(2).strip(), "polarity": "positive"})
        effect = m.group(3).strip()
        confidence = "high"
    else:
        m = re.match(r"^(.+?)\s+(if|while)\s+(.+)$", src, flags=re.I)
        if m and len(m.group(1).split()) >= 3:
            effect = m.group(1).strip()
            conditions.append({"connector": m.group(2).casefold(), "text": m.group(3).strip(), "polarity": "positive"})
            confidence = "medium"

    if " unless " in effect.casefold():
        parts = re.split(r"\s+unless\s+", effect, maxsplit=1, flags=re.I)
        if len(parts) == 2:
            effect = parts[0].strip()
            conditions.append({"connector": "unless", "text": parts[1].strip(), "polarity": "negative"})
            confidence = "medium" if confidence == "none" else confidence
    return conditions, effect, confidence


def classify_effect_types(text: str, modalities: list[str]) -> list[str]:
    low = _norm(text).casefold()
    out = set(modalities)
    if re.search(r"\breplacement effect\b|\binstead\b", low):
        out.add("replacement")
    if re.search(r"\btrigger(?:ed|s|ing)?\b", low):
        out.add("trigger")
    if re.search(r"\bcost\b|\bpay\b", low):
        out.add("cost")
    if re.search(r"\btarget(?:s|ed|ing)?\b", low):
        out.add("targeting")
    if re.search(r"\bmove(?:s|d|ing)?\b|\bmoving\b", low):
        out.add("movement")
    if re.search(r"\bready|readied|readying|exhaust|exhausted|stun|stunned|contested|empowered\b", low):
        out.add("state_change_or_status")
    if re.match(r"^(?:[A-Za-z][A-Za-z '\-]+\s+)?(?:is|are|means)\b", _norm(text)) or " is defined " in low:
        out.add("definition_candidate")
    return sorted(out)


def compile_rule_catalog(core: dict[str, Any]) -> dict[str, Any]:
    rules: list[dict[str, Any]] = []
    modality_counts: Counter[str] = Counter()
    effect_counts: Counter[str] = Counter()
    conditional_count = 0
    for r in core.get("rules", []):
        text = r.get("normativeText") or r.get("text") or ""
        conditions, effect_text, confidence = parse_conditions(text)
        modalities = parse_modalities(text)
        effects = classify_effect_types(text, modalities)
        if conditions:
            conditional_count += 1
        modality_counts.update(modalities)
        effect_counts.update(effects)
        dependencies = list(dict.fromkeys(str(x) for x in (r.get("resolvedCrossReferences") or []) if x))
        rules.append({
            "ruleId": r["ruleId"],
            "internalRuleId": r["internalRuleId"],
            "sourceId": r["sourceId"],
            "sourceText": _norm(text),
            "sourceTextHash": text_hash(text),
            "conditions": conditions,
            "effectText": effect_text,
            "modalities": modalities,
            "effectTypes": effects,
            "dependencies": dependencies,
            "parentRuleId": r.get("parentRuleId"),
            "majorSectionRuleId": r.get("majorSectionRuleId"),
            "executable": False,
            "compilerConfidence": confidence,
            "note": "Structural semantic compilation only. This rule is not executable unless an independently validated Rule Program references it.",
        })
    return {
        "schemaVersion": 1,
        "metadata": {
            "ruleCount": len(rules),
            "executableRuleCount": 0,
            "conditionalRuleCount": conditional_count,
            "modalityCounts": dict(sorted(modality_counts.items())),
            "effectTypeCounts": dict(sorted(effect_counts.items())),
            "policy": "All Core Rules receive deterministic structural metadata. Catalog entries remain non-executable until a separately regression-tested Rule Program compiles them into logic.",
        },
        "rules": rules,
    }
