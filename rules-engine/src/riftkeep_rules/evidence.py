from __future__ import annotations

from typing import Any


def rule_evidence(rule: dict[str, Any]) -> dict[str, Any]:
    rid = str(rule.get("ruleId") or "")
    return {
        "evidenceId": f"R:{rid}",
        "kind": "core_rule",
        "ruleId": rid,
        "text": rule.get("normativeText") or rule.get("text") or "",
        "exampleText": rule.get("exampleText") or "",
        "pageStart": rule.get("pageStart"),
        "pageEnd": rule.get("pageEnd"),
        "sourceId": rule.get("sourceId"),
        "internalRuleId": rule.get("internalRuleId"),
    }


def card_evidence(card: dict[str, Any]) -> dict[str, Any]:
    cid = str(card.get("id") or "")
    return {
        "evidenceId": f"C:{cid}",
        "kind": "card_text",
        "cardId": cid,
        "name": card.get("name"),
        "cardType": card.get("type"),
        "text": card.get("effectiveText") or "",
        "sourceId": "cards-database-snapshot",
    }


def official_evidence(doc: dict[str, Any]) -> dict[str, Any]:
    eid = str(doc.get("evidenceId") or "")
    return {
        "evidenceId": eid,
        "kind": "official_ruling" if doc.get("sourceType") == "official_faq" else str(doc.get("sourceType") or "official_source"),
        "sourceId": doc.get("sourceId"),
        "title": doc.get("title"),
        "heading": doc.get("heading"),
        "question": doc.get("question"),
        "text": doc.get("text") or "",
        "published": doc.get("published"),
        "effectiveFrom": doc.get("effectiveFrom"),
        "sourceUrl": doc.get("sourceUrl"),
        "authority": doc.get("authority") or {},
        "explicitRuleReferences": doc.get("explicitRuleReferences") or [],
    }


def build_issue_evidence_catalog(
    rules: list[dict[str, Any]],
    named_cards: list[dict[str, Any]],
    official_docs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build a sealed, deduplicated catalog for deterministic/LLM reasoning.

    The model may cite only these IDs. Exact quotations are rendered from these backend
    objects after validation; the model is never the source of authoritative wording.
    """
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(row: dict[str, Any]) -> None:
        eid = row.get("evidenceId")
        if not eid or eid in seen:
            return
        seen.add(str(eid))
        out.append(row)

    for r in rules:
        add(rule_evidence(r))
    for c in named_cards:
        add(card_evidence(c))
    for d in official_docs:
        add(official_evidence(d))
    return out


def evidence_id_set(catalog: list[dict[str, Any]]) -> set[str]:
    return {str(x["evidenceId"]) for x in catalog if x.get("evidenceId")}
