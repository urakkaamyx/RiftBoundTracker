from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

KEYWORD_RANGE = range(805, 830)
GAME_ACTION_RANGE = range(413, 445)


def classify_semantics(text: str) -> list[str]:
    t = (text or "").lower()
    tags: set[str] = set()
    if re.search(r"\b(can't|cannot|can not|may not)\b", t):
        tags.add("prohibition")
    if re.search(r"\bonly\b", t):
        tags.add("restriction")
    permission_text = re.sub(r"\b(?:can't|cannot|can not|may not)\b", " ", t)
    if re.search(r"\bmay\b|\bcan\b|\bpermission\b", permission_text):
        tags.add("permission")
    if re.search(r"\bmust\b|required\b|requires?\b", t):
        tags.add("requirement")
    if re.search(r"\bif\b|\bwhen\b|\bwhile\b|\bunless\b|\bas long as\b", t):
        tags.add("conditional")
    if re.search(r"\binstead\b|\bwould\b", t):
        tags.add("replacement_candidate")
    if re.search(r"\btrigger", t):
        tags.add("trigger")
    if re.search(r"\bcost\b|\bpay\b", t):
        tags.add("cost")
    if re.search(r"\btarget", t):
        tags.add("targeting")
    if re.search(r"\bcleanup\b", t):
        tags.add("cleanup")
    if re.search(r"\bcombat\b", t):
        tags.add("combat")
    if re.search(r"\bshowdown\b", t):
        tags.add("showdown")
    if re.search(r"\bchain\b", t):
        tags.add("chain")
    if re.match(r"^(is|are|means|the concept of|the act of)\b", t) or " is defined " in t:
        tags.add("definition_candidate")
    if re.match(r"^\d+[a-z]?\.\s", t):
        tags.add("procedure_step")
    return sorted(tags)


def _term_from_root(rule: dict[str, Any]) -> str | None:
    text = (rule.get("normativeText") or "").strip()
    if not text or len(text) > 80:
        return None
    if text.endswith((".", ":", ";")):
        return None
    if len(text.split()) > 8:
        return None
    return text


def build_graph(core: dict[str, Any], cards: dict[str, Any]) -> dict[str, Any]:
    rules = core["rules"]
    by_id = {r["ruleId"]: r for r in rules}
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    for r in rules:
        nodes.append(
            {
                "id": f"rule:{r['ruleId']}",
                "kind": "rule",
                "ruleId": r["ruleId"],
                "internalRuleId": r["internalRuleId"],
                "label": r.get("normativeText", "")[:160],
                "semanticTags": classify_semantics(r.get("normativeText", "")),
                "majorSectionRuleId": r.get("majorSectionRuleId"),
                "majorSectionTitle": r.get("majorSectionTitle"),
                "visualSubsection": r.get("visualSubsection"),
            }
        )
        if r.get("parentRuleId"):
            edges.append({"from": f"rule:{r['parentRuleId']}", "to": f"rule:{r['ruleId']}", "type": "PARENT_OF", "evidence": "numbering"})
        for ref in r.get("resolvedCrossReferences", []):
            edges.append({"from": f"rule:{r['ruleId']}", "to": f"rule:{ref}", "type": "EXPLICIT_REFERENCE", "evidence": "rule_text"})
        if r.get("majorSectionRuleId") and r["ruleId"] != r["majorSectionRuleId"]:
            edges.append({"from": f"rule:{r['ruleId']}", "to": f"rule:{r['majorSectionRuleId']}", "type": "IN_MAJOR_SECTION", "evidence": "pdf_typography"})

    keywords: dict[str, dict[str, Any]] = {}
    for n in KEYWORD_RANGE:
        r = by_id.get(str(n))
        if not r:
            continue
        term = _term_from_root(r)
        if not term:
            continue
        k = term.lower()
        keywords[k] = {"name": term, "ruleId": str(n)}
        nodes.append({"id": f"keyword:{k}", "kind": "keyword", "label": term, "ruleId": str(n)})
        edges.append({"from": f"keyword:{k}", "to": f"rule:{n}", "type": "DEFINED_BY", "evidence": "keyword_glossary"})

    game_actions: dict[str, dict[str, Any]] = {}
    for n in GAME_ACTION_RANGE:
        r = by_id.get(str(n))
        if not r:
            continue
        term = _term_from_root(r)
        if not term:
            continue
        k = term.lower()
        game_actions[k] = {"name": term, "ruleId": str(n)}
        nodes.append({"id": f"action:{k}", "kind": "game_action", "label": term, "ruleId": str(n)})
        edges.append({"from": f"action:{k}", "to": f"rule:{n}", "type": "DEFINED_BY", "evidence": "game_actions_section"})

    # Card markup links use the typed card-text compiler when available. This avoids
    # treating every lexical mention as equivalent and resolves collisions such as
    # [Empower] (Keyword 827) versus prose "empower" (Game Action 441).
    for c in cards["cards"]:
        cid = str(c["id"])
        txt = (c.get("effectiveText") or "").lower()
        nodes.append({"id": f"card:{cid}", "kind": "card", "label": c.get("name"), "cardType": c.get("type")})

        typed = list(c.get("textMarkup") or [])
        if typed:
            seen_links: set[tuple[str, str]] = set()
            for token in typed:
                for ref in token.get("conceptRefs") or []:
                    cat = ref.get("category")
                    name = str(ref.get("name") or "").lower()
                    if cat == "keyword" and name in keywords:
                        key = ("keyword", name)
                        if key not in seen_links:
                            edges.append({
                                "from": f"card:{cid}", "to": f"keyword:{name}",
                                "type": "USES_KEYWORD_MARKUP", "evidence": "card_text_typed_markup",
                                "token": token.get("token"),
                            })
                            seen_links.add(key)
                    elif cat == "game_action" and name in game_actions:
                        key = ("action", name)
                        if key not in seen_links:
                            edges.append({
                                "from": f"card:{cid}", "to": f"action:{name}",
                                "type": "USES_GAME_ACTION_MARKUP", "evidence": "card_text_typed_markup",
                                "token": token.get("token"),
                            })
                            seen_links.add(key)

            # Prose still matters for Game Actions. Add lexical action links only for
            # action names not already represented by typed markup. These are evidence
            # of terminology use, not proof that an action occurs in a scenario.
            for k in game_actions:
                if ("action", k) in seen_links:
                    continue
                if re.search(rf"\b{re.escape(k)}(?:s|ed|ing)?\b", txt):
                    edges.append({
                        "from": f"card:{cid}", "to": f"action:{k}",
                        "type": "USES_GAME_ACTION_TERM", "evidence": "card_text_lexical",
                    })
        else:
            # Backward-compatible fallback for unannotated card corpora.
            for k in keywords:
                if re.search(rf"\b{re.escape(k)}\b", txt):
                    edges.append({"from": f"card:{cid}", "to": f"keyword:{k}", "type": "USES_KEYWORD_TERM", "evidence": "card_text_lexical"})
            for k in game_actions:
                if re.search(rf"\b{re.escape(k)}(?:s|ed|ing)?\b", txt):
                    edges.append({"from": f"card:{cid}", "to": f"action:{k}", "type": "USES_GAME_ACTION_TERM", "evidence": "card_text_lexical"})

    # Where a Keyword explicitly invokes a same-name Game Action, represent that
    # relationship directly. This is proven from the keyword family text, not inferred
    # merely because the names happen to collide.
    for k, kw in keywords.items():
        action = game_actions.get(k)
        if not action:
            continue
        root = int(kw["ruleId"])
        family = [r for r in rules if r.get("rootRuleId") == str(root)]
        phrase = re.compile(rf"\b{re.escape(k)}\s+action\b", re.I)
        support = next((r for r in family if phrase.search(r.get("normativeText") or "")), None)
        if support:
            edges.append({
                "from": f"keyword:{k}", "to": f"action:{k}",
                "type": "KEYWORD_PERFORMS_GAME_ACTION",
                "evidence": f"rule:{support['ruleId']}",
            })

    # Explicit precedence relations from the Core Rules themselves.
    # Rule 002 is Golden Rule, 054 is Can't beats Can; we connect their descendants to the concept nodes.
    if "002" in by_id:
        nodes.append({"id": "concept:golden_rule", "kind": "precedence_concept", "label": "Golden Rule"})
        edges.append({"from": "concept:golden_rule", "to": "rule:002", "type": "DEFINED_BY", "evidence": "core_rules"})
    if "054" in by_id:
        nodes.append({"id": "concept:cant_beats_can", "kind": "precedence_concept", "label": "Can't beats Can"})
        edges.append({"from": "concept:cant_beats_can", "to": "rule:054", "type": "DEFINED_BY", "evidence": "core_rules"})

    return {
        "metadata": {
            "ruleNodeCount": len(rules),
            "keywordCount": len(keywords),
            "gameActionCount": len(game_actions),
            "cardNodeCount": len(cards["cards"]),
            "edgeCount": len(edges),
            "conservative": True,
            "note": "Semantic edges are emitted only when supported by numbering, explicit references, document structure, glossary membership, or lexical card term use.",
        },
        "catalogs": {"keywords": keywords, "gameActions": game_actions},
        "nodes": nodes,
        "edges": edges,
    }


def adjacency(graph: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in graph["edges"]:
        out[e["from"]].append(e)
    return dict(out)
