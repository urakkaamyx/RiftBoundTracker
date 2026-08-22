from __future__ import annotations

import json
import re
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .vocabulary import retrieval_action_terms
from .player_language import normalize_player_language
from .runtime_hardening import INDEX_SCHEMA_VERSION, open_readonly_sqlite

TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’-]*")

# Retrieval vocabulary, not rules. These aliases map common player phrasing to official terminology.
ALIASES: dict[str, tuple[str, ...]] = {
    "damage": ("deal", "damage", "marked damage"),
    "takes damage": ("deal", "dealt damage", "damage"),
    "take damage": ("deal", "dealt damage", "damage"),
    "dies": ("kill", "killed", "lethal damage", "cleanup"),
    "die": ("kill", "killed", "lethal damage"),
    "dead": ("kill", "killed", "lethal damage"),
    "play unit": ("play", "playing cards", "valid location", "unit"),
    "play units": ("play", "playing cards", "valid location", "unit"),
    "battlefield i control": ("battlefield control", "controlled battlefield", "control"),
    "battlefield you control": ("battlefield control", "controlled battlefield", "control"),
    "contested": ("contested", "control", "showdown", "combat"),
    "hidden": ("hidden", "hide", "cleanup"),
    "recycle": ("recycle",),
    "move": ("move", "movement"),
    "ready": ("ready",),
    "exhaust": ("exhaust",),
    "counter": ("counter", "chain"),
    "flow": ("flow", "chain"),
}

STOP = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being", "to", "of", "in", "on", "at", "for",
    "and", "or", "but", "if", "then", "do", "does", "did", "can", "could", "would", "should", "i", "you", "my", "your",
    "it", "this", "that", "them", "they", "their", "with", "from", "as", "have", "has", "had", "when", "what", "which",
}


def _tokens(text: str) -> list[str]:
    return [m.group(0).lower().replace("’", "'") for m in TOKEN_RE.finditer(text or "")]


def expand_query(text: str) -> dict[str, Any]:
    low = (text or "").lower().replace("’", "'")
    raw = _tokens(low)
    terms: list[str] = [x for x in raw if x not in STOP and len(x) > 1]
    aliases: list[str] = []
    for phrase, expanded in ALIASES.items():
        if phrase in low:
            aliases.extend(expanded)
    aliases.extend(retrieval_action_terms(low))
    # Keep exact official-looking capitalized/card terms available as phrases from caller text.
    all_terms = []
    seen = set()
    for t in terms + aliases:
        t = t.strip().lower()
        if t and t not in seen:
            seen.add(t)
            all_terms.append(t)
    return {"original": text, "terms": all_terms, "aliases": aliases}


_FOLLOWUP_SPLIT_RE = re.compile(
    r"\s+and\s+(?=(?:does|do|can|could|would|should|is|are|will|what happens if|what if)\b)",
    re.I,
)

_CONTEXT_ANCHORS = (
    "unit", "battlefield", "base", "hidden", "damage", "combat", "showdown",
    "chain", "spell", "ability", "gear", "rune", "play", "move", "kill",
    "deal", "hide", "exhaust", "ready", "stun", "counter", "target",
)


def _split_question_clauses(question: str) -> list[str]:
    """Split only on explicit question boundaries and safe follow-up conjunctions.

    The leading question verb of the follow-up is preserved.  For example,
    ``... and is it Contested?`` becomes ``is it Contested`` rather than the lossy
    ``it Contested`` produced by the earlier splitter.
    """
    q = re.sub(r"\s+", " ", (question or "").strip())
    if not q:
        return []
    pieces: list[str] = []
    for sentence in re.split(r"\?+\s*", q):
        sentence = sentence.strip(" ?.,")
        if not sentence:
            continue
        pieces.extend(x.strip(" ?.,") for x in _FOLLOWUP_SPLIT_RE.split(sentence) if x.strip(" ?.,"))
    return pieces


def decompose_question(question: str) -> list[dict[str, str]]:
    """Conservative deterministic issue decomposition with antecedent retrieval context.

    ``text`` always preserves the player's original wording for that issue.
    ``retrievalQuery`` may append official-vocabulary anchors from an earlier clause
    when a follow-up relies on pronouns such as ``it``/``that``.  The added anchors
    affect retrieval only; they do not alter the issue that is adjudicated.
    """
    pieces = _split_question_clauses(question)
    if not pieces:
        return []
    if len(pieces) == 1:
        return [{"text": pieces[0], "retrievalQuery": pieces[0]}]

    # Antecedent anchors are discovered from normalized player language so aliases
    # such as summon->Play contribute the same retrieval context as official terms.
    head_normalized = normalize_player_language(pieces[0])["text"].casefold()
    context_terms: list[str] = []
    for phrase in _CONTEXT_ANCHORS:
        if re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", head_normalized):
            context_terms.append(phrase)

    out = [{"text": pieces[0], "retrievalQuery": pieces[0]}]
    for part in pieces[1:]:
        part_normalized = normalize_player_language(part)["text"].casefold()
        # Only append missing anchors.  This keeps the follow-up readable and avoids
        # duplicating words it already states explicitly.
        missing = [x for x in context_terms if not re.search(rf"(?<![a-z0-9]){re.escape(x)}(?![a-z0-9])", part_normalized)]
        retrieval_query = part + ((" " + " ".join(missing)) if missing else "")
        out.append({"text": part, "retrievalQuery": retrieval_query})
    return out


def _fts_expr(terms: Iterable[str]) -> str:
    parts = []
    for t in terms:
        toks = _tokens(t)
        if not toks:
            continue
        if len(toks) == 1:
            parts.append(f'"{toks[0]}"')
        else:
            parts.append('"' + " ".join(toks) + '"')
    # OR is high-recall; ranking + evidence closure will narrow it.
    return " OR ".join(parts) or '"riftbound"'


def build_index(db_path: Path, core: dict[str, Any], cards: dict[str, Any], supplemental: dict[str, Any] | None = None) -> None:
    """Build and validate a replacement index before atomically swapping it live.

    A parser/build failure must never destroy the last known-good runtime index.
    The temporary database lives in the same directory so os.replace is atomic on
    supported local filesystems.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{db_path.name}.", suffix=".tmp", dir=str(db_path.parent))
    os.close(fd)
    tmp_path = Path(raw_tmp)
    con: sqlite3.Connection | None = None
    try:
        con = sqlite3.connect(tmp_path)
        con.executescript(
            """
            PRAGMA journal_mode=DELETE;
            CREATE TABLE docs_meta (
                doc_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                rule_id TEXT,
                card_id TEXT,
                title TEXT,
                source_id TEXT,
                payload_json TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE docs_fts USING fts5(
                doc_id UNINDEXED,
                title,
                normative,
                example,
                major_section,
                subsection,
                aliases,
                tokenize='unicode61 remove_diacritics 2'
            );
            """
        )
        for r in core["rules"]:
            title = ""
            if r["depth"] == 1 and len((r.get("normativeText") or "").split()) <= 10:
                title = r.get("normativeText") or ""
            aliases = " ".join([r.get("majorSectionTitle") or "", r.get("visualSubsection") or ""])
            payload = json.dumps(r, ensure_ascii=False)
            doc_id = f"rule:{r['ruleId']}"
            con.execute(
                "INSERT INTO docs_meta VALUES (?,?,?,?,?,?,?)",
                (doc_id, "rule", r["ruleId"], None, title, r["sourceId"], payload),
            )
            con.execute(
                "INSERT INTO docs_fts VALUES (?,?,?,?,?,?,?)",
                (
                    doc_id,
                    title,
                    r.get("normativeText") or "",
                    r.get("exampleText") or "",
                    r.get("majorSectionTitle") or "",
                    r.get("visualSubsection") or "",
                    aliases,
                ),
            )
        for c in cards["cards"]:
            doc_id = f"card:{c['id']}"
            payload = json.dumps(c, ensure_ascii=False)
            title = c.get("name") or ""
            con.execute(
                "INSERT INTO docs_meta VALUES (?,?,?,?,?,?,?)",
                (doc_id, "card", None, str(c["id"]), title, "cards-database-snapshot", payload),
            )
            con.execute(
                "INSERT INTO docs_fts VALUES (?,?,?,?,?,?,?)",
                (doc_id, title, c.get("displayText") or c.get("effectiveText") or "", "", c.get("type") or "", c.get("setLabel") or "", " ".join((c.get("domains") or []) + [str(t.get("baseTerm") or "") for t in c.get("textMarkup", []) if t.get("classification") in {"keyword", "game_action", "rule_concept", "ambiguous_official_term"}])),
            )
        for d in (supplemental or {}).get("documents", []):
            evidence_id = str(d.get("evidenceId") or "")
            if not evidence_id:
                continue
            source_type = str(d.get("sourceType") or "official_article")
            authority_status = str((d.get("authority") or {}).get("status") or "")
            if source_type == "official_faq":
                kind = "official_ruling" if authority_status == "current_overlay" else "official_ruling_history"
            elif source_type == "card_errata":
                kind = "errata"
            elif source_type == "patch_notes":
                kind = "patch_note_history"
            else:
                kind = "official_source"
            doc_id = "official:" + evidence_id
            title = str(d.get("question") or d.get("heading") or d.get("title") or d.get("sourceId") or "")
            payload = json.dumps(d, ensure_ascii=False)
            con.execute(
                "INSERT INTO docs_meta VALUES (?,?,?,?,?,?,?)",
                (doc_id, kind, None, None, title, d.get("sourceId"), payload),
            )
            con.execute(
                "INSERT INTO docs_fts VALUES (?,?,?,?,?,?,?)",
                (doc_id, title, d.get("text") or "", "", d.get("sourceType") or "", d.get("heading") or "", " ".join(d.get("explicitRuleReferences") or [])),
            )
        con.execute(f"PRAGMA user_version={INDEX_SCHEMA_VERSION}")
        con.commit()
        quick = str(con.execute("PRAGMA quick_check").fetchone()[0])
        if quick != "ok":
            raise RuntimeError(f"new search index failed SQLite quick_check: {quick}")
        con.close()
        con = None
        os.replace(tmp_path, db_path)
        try:
            dfd = os.open(str(db_path.parent), os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except OSError:
            pass
    finally:
        if con is not None:
            con.close()
        tmp_path.unlink(missing_ok=True)
        for suffix in ("-journal", "-wal", "-shm"):
            Path(str(tmp_path) + suffix).unlink(missing_ok=True)


@dataclass
class Hit:
    doc_id: str
    kind: str
    score: float
    rule_id: str | None
    card_id: str | None
    title: str | None
    payload: dict[str, Any]


def search(db_path: Path, query: str, limit: int = 30, kinds: tuple[str, ...] = ("rule", "card", "official_ruling", "errata", "official_source"), offset: int = 0) -> list[Hit]:
    expanded = expand_query(query)
    expr = _fts_expr(expanded["terms"])
    con = open_readonly_sqlite(db_path)
    placeholders = ",".join("?" for _ in kinds)
    # bm25 lower is better. Normative text and title carry much more weight than examples.
    sql = f"""
        SELECT m.*, bm25(docs_fts, 0.0, 8.0, 6.0, 0.8, 2.5, 2.0, 1.5) AS rank
        FROM docs_fts
        JOIN docs_meta m ON m.doc_id = docs_fts.doc_id
        WHERE docs_fts MATCH ? AND m.kind IN ({placeholders})
        ORDER BY rank ASC
        LIMIT ? OFFSET ?
    """
    rows = con.execute(sql, (expr, *kinds, limit, offset)).fetchall()
    con.close()
    return [
        Hit(
            doc_id=r["doc_id"],
            kind=r["kind"],
            score=float(r["rank"]),
            rule_id=r["rule_id"],
            card_id=r["card_id"],
            title=r["title"],
            payload=json.loads(r["payload_json"]),
        )
        for r in rows
    ]


def evidence_closure(core: dict[str, Any], seed_rule_ids: Iterable[str], max_rules: int = 60) -> list[dict[str, Any]]:
    """Expand seed rules to a bounded evidence packet.

    Expansion order: seed -> parent -> children -> siblings -> explicit cross-references.
    This is deliberately local and bounded; it does not recursively flood the full graph.
    """
    by_id = {r["ruleId"]: r for r in core["rules"]}
    queue: list[tuple[str, str]] = []
    for rid in seed_rule_ids:
        if rid in by_id:
            queue.append((rid, "seed"))
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    qi = 0
    while qi < len(queue) and len(out) < max_rules:
        rid, reason = queue[qi]
        qi += 1
        if rid in seen or rid not in by_id:
            continue
        seen.add(rid)
        r = dict(by_id[rid])
        r["closureReason"] = reason
        out.append(r)
        if r.get("parentRuleId"):
            queue.append((r["parentRuleId"], f"parent_of:{rid}"))
        for cid in r.get("childRuleIds", []):
            queue.append((cid, f"child_of:{rid}"))
        # siblings are important for conditions/exceptions sitting adjacent to the hit.
        for sid in r.get("siblingRuleIds", []):
            queue.append((sid, f"sibling_of:{rid}"))
        for ref in r.get("resolvedCrossReferences", []):
            queue.append((ref, f"explicit_ref_from:{rid}"))
    return out


def retrieve_issue(db_path: Path, core: dict[str, Any], issue: str, top_k: int = 20, closure_limit: int = 60) -> dict[str, Any]:
    hits = search(db_path, issue, limit=top_k, kinds=("rule", "card", "official_ruling", "errata", "official_source"))
    rule_hits = [h for h in hits if h.kind == "rule"]
    card_hits = [h for h in hits if h.kind == "card"]
    official_hits = [h for h in hits if h.kind not in {"rule", "card"}]
    seed_ids = [h.rule_id for h in rule_hits if h.rule_id]
    # Official rulings often name the exact Core Rules that support the ruling. Those
    # references are authoritative evidence dependencies, not guessed relevance, so
    # they seed closure alongside lexical rule hits.
    official_ref_ids: list[str] = []
    known_ids = {r["ruleId"] for r in core.get("rules", [])}
    for hit in official_hits:
        for rid in hit.payload.get("explicitRuleReferences", []) or []:
            if rid in known_ids and rid not in official_ref_ids:
                official_ref_ids.append(rid)
    ordered_seed_ids = []
    for rid in official_ref_ids + seed_ids:
        if rid and rid not in ordered_seed_ids:
            ordered_seed_ids.append(rid)
    closure = evidence_closure(core, ordered_seed_ids[:12], max_rules=closure_limit)
    return {
        "issue": issue,
        "queryExpansion": expand_query(issue),
        "rankedHits": [
            {"docId": h.doc_id, "kind": h.kind, "score": h.score, "ruleId": h.rule_id, "cardId": h.card_id, "title": h.title}
            for h in hits
        ],
        "evidenceRules": closure,
        "cardCandidates": [h.payload for h in card_hits[:8]],
        "officialEvidence": [h.payload for h in official_hits[:12]],
        "officialReferencedRuleIds": official_ref_ids,
    }
