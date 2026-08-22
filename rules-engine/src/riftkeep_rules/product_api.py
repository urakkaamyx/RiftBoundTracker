from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .authority import load_authority_status
from .engine import RulesEngine
from .retrieval import Hit, search as retrieval_search
from .version_integrity import FAMILIES, load_history
from .runtime_hardening import BoundedLruCache, RuntimeArtifactGuard
from .release_identity import PRODUCT_VERSION, RELEASE_LINE
from .llm_provider import provider_from_env

API_VERSION = "v1"
SCHEMA_VERSION = 1
SEARCH_LIMIT_MAX = 100
SEARCH_OFFSET_MAX = 10_000
SEARCH_QUERY_MAX = 500
QUESTION_MAX = 4_000

SEARCH_KINDS = (
    "rule",
    "card",
    "official_ruling",
    "official_ruling_history",
    "errata",
    "official_source",
    "patch_note_history",
)


class ProductApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.status = int(status)
        self.code = str(code)
        self.message = str(message)
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error": {"code": self.code, "message": self.message, "details": self.details},
        }


def _load(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _bounded_int(value: Any, *, name: str, default: int, minimum: int, maximum: int) -> int:
    if value is None or value == "":
        return default
    try:
        out = int(value)
    except (TypeError, ValueError) as exc:
        raise ProductApiError(400, "invalid_parameter", f"{name} must be an integer.", {"parameter": name}) from exc
    if out < minimum or out > maximum:
        raise ProductApiError(
            400,
            "parameter_out_of_range",
            f"{name} must be between {minimum} and {maximum}.",
            {"parameter": name, "minimum": minimum, "maximum": maximum},
        )
    return out


def _exact_text(value: Any, *, name: str, maximum: int, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ProductApiError(400, "invalid_parameter", f"{name} must be a string.", {"parameter": name})
    out = value.strip()
    if not out and not allow_empty:
        raise ProductApiError(400, "invalid_parameter", f"{name} cannot be empty.", {"parameter": name})
    if len(out) > maximum:
        raise ProductApiError(400, "parameter_too_long", f"{name} exceeds the maximum length.", {"parameter": name, "maximum": maximum})
    return out


def _safe_source(source: dict[str, Any]) -> dict[str, Any]:
    keep = (
        "id", "type", "status", "url", "title", "published", "effectiveFrom", "effectiveUntil",
        "supersededBy", "supersededReason", "release", "authorityScope", "precedence", "sourceSha256",
        "previousSourceId",
    )
    return {k: source.get(k) for k in keep if source.get(k) is not None}


def _safe_version(row: dict[str, Any]) -> dict[str, Any]:
    keep = (
        "sourceId", "status", "sourceSha256", "ruleCount", "previousSourceId", "nextSourceId", "effectiveFrom",
        "promotedAt", "reviewApprovalRequired", "reviewApproved", "changeCounts",
    )
    return {k: row.get(k) for k in keep if row.get(k) is not None}


def _hit_summary(hit: Hit) -> dict[str, Any]:
    p = hit.payload
    row: dict[str, Any] = {
        "id": hit.doc_id,
        "kind": hit.kind,
        "score": hit.score,
        "title": hit.title or p.get("name") or p.get("question") or p.get("heading") or "",
        "sourceId": p.get("sourceId"),
    }
    if hit.kind == "rule":
        row.update({
            "ruleId": hit.rule_id,
            "text": p.get("normativeText") or p.get("text") or "",
            "exampleText": p.get("exampleText") or "",
            "pageStart": p.get("pageStart"),
            "pageEnd": p.get("pageEnd"),
            "majorSectionTitle": p.get("majorSectionTitle"),
        })
    elif hit.kind == "card":
        row.update({
            "cardId": hit.card_id,
            "name": p.get("name"),
            "cardType": p.get("type"),
            "setId": p.get("setId"),
            "setLabel": p.get("setLabel"),
            "collectorCode": p.get("collectorCode"),
            "effectiveText": p.get("effectiveText") or p.get("displayText") or "",
            "textSource": p.get("textSource"),
        })
    else:
        row.update({
            "evidenceId": p.get("evidenceId"),
            "question": p.get("question"),
            "heading": p.get("heading"),
            "published": p.get("published"),
            "effectiveFrom": p.get("effectiveFrom"),
            "text": p.get("text") or "",
        })
    return {k: v for k, v in row.items() if v is not None}


class ProductApiService:
    """Stable product-facing boundary over the deterministic RiftKeep engine.

    This class intentionally exposes a smaller contract than RulesEngine.  Product/UI
    callers receive conclusions, citations and authoritative lookup data, while internal
    retrieval candidates, filesystem locations and implementation-only structures remain
    private to the engine.
    """

    def __init__(self, root: Path, *, require_current_authority: bool = True, engine: RulesEngine | None = None):
        self.root = Path(root)
        self.require_current_authority = bool(require_current_authority)
        # Deep validation happens once at startup.  Requests thereafter use a cheap
        # stat signature and fail closed if an M16 publish changes runtime bytes.
        self.runtime_guard = RuntimeArtifactGuard(self.root, require_current_authority=require_current_authority)
        self._search_cache: BoundedLruCache[tuple[Any, ...], dict[str, Any]] = BoundedLruCache(max_entries=256)
        if engine is not None:
            self.engine = engine
        else:
            llm_provider = provider_from_env()
            self.engine = RulesEngine(
                self.root,
                require_current_authority=require_current_authority,
                interpretation_provider=llm_provider,
                explanation_provider=llm_provider,
            )
        self.core = _load(self.root / "data/canonical/core_rules.json", {"rules": []})
        self.tournament = _load(self.root / "data/canonical/tournament_rules.json", {"rules": []})
        self.cards = _load(self.root / "data/canonical/cards.json", {"cards": []})
        self.supplemental = _load(self.root / "data/canonical/supplemental_sources.json", {"documents": []})
        self.errata = _load(self.root / "data/canonical/official_errata.json", {"records": []})
        self.card_interactions = _load(self.root / "data/canonical/card_interaction_catalog.json", {"printings": [], "identities": []})
        self.manifest = _load(self.root / "data/source/official_source_manifest.json", {"sources": []})
        self.milestone = _load(self.root / "MILESTONE.json", {})
        self.db = self.root / "data/index/rules.sqlite"
        self._core_by_id = {str(r.get("ruleId")): r for r in self.core.get("rules", [])}
        self._tournament_by_id = {str(r.get("ruleId")): r for r in self.tournament.get("rules", [])}
        self._cards_by_id = {str(c.get("id")): c for c in self.cards.get("cards", [])}
        self._cards_by_name: dict[str, list[dict[str, Any]]] = {}
        for card in self.cards.get("cards", []):
            self._cards_by_name.setdefault(str(card.get("name") or "").casefold(), []).append(card)
        self._official_by_evidence = {str(d.get("evidenceId")): d for d in self.supplemental.get("documents", []) if d.get("evidenceId")}
        self._errata_by_entry = {str(d.get("entryId")): d for d in self.errata.get("records", []) if d.get("entryId")}
        self._interaction_printing = {str(p.get("cardId")): p for p in self.card_interactions.get("printings", []) if p.get("cardId")}
        self._interaction_identity = {str(p.get("identityKey")): p for p in self.card_interactions.get("identities", []) if p.get("identityKey")}
        self._histories = {family: load_history(self.root, family) for family in FAMILIES}

    def _assert_runtime_current(self) -> None:
        guard = getattr(self, "runtime_guard", None)
        if guard is None:
            # A deliberately minimal synthetic fixture may opt out when exercising
            # pure history formatting against an isolated temporary history tree.
            # Normal ProductApiService construction never sets this flag and always
            # installs a validated RuntimeArtifactGuard.
            if getattr(self, "_allow_missing_runtime_guard_for_fixture", False):
                return
            raise ProductApiError(503, "runtime_guard_unavailable", "Runtime integrity guard is unavailable; restart the service from a validated project tree.")
        try:
            guard.assert_unchanged()
        except RuntimeError as exc:
            raise ProductApiError(503, "runtime_snapshot_changed", "Runtime authority/index files changed after server startup; restart the service after the update transaction completes.", {"snapshotId": guard.snapshot_id}) from exc

    def status(self) -> dict[str, Any]:
        authority = self.engine.authority_status
        corpus = self.milestone.get("corpus") or {}
        return {
            "ok": True,
            "apiVersion": API_VERSION,
            "schemaVersion": SCHEMA_VERSION,
            "release": {
                "productVersion": PRODUCT_VERSION,
                "releaseLine": RELEASE_LINE,
                "milestone": self.milestone.get("milestone"),
                "releaseStatus": self.milestone.get("releaseStatus"),
                "tasksCompletedThrough": self.milestone.get("tasksCompletedThrough"),
            },
            "corpus": {
                "coreRules": corpus.get("coreRules", len(self.core.get("rules", []))),
                "tournamentRules": corpus.get("tournamentRules", len(self.tournament.get("rules", []))),
                "cards": corpus.get("cards", len(self.cards.get("cards", []))),
                "currentFaqSections": corpus.get("currentFaqSections", len(self.supplemental.get("documents", []))),
                "officialErrataEvents": corpus.get("officialErrataEvents", len(self.errata.get("records", []))),
            },
            "authority": authority,
            "sources": {
                "coreSourceId": (self.core.get("metadata") or {}).get("sourceId"),
                "tournamentSourceId": (self.tournament.get("metadata") or {}).get("sourceId"),
                "activeOverlays": authority.get("activeOverlays", []),
            },
            "runtime": {
                **self.runtime_guard.diagnostics(),
                "searchCache": self._search_cache.stats(),
                "adjudicationCached": False,
            },
            "policy": {
                "currentAuthorityRequiredForAsk": self.require_current_authority,
                "filesystemPathsExposed": False,
                "engineIsAuthority": True,
                "networkRequiredForServing": False,
            },
        }

    def search(self, query: str, *, kinds: Iterable[str] | None = None, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        self._assert_runtime_current()
        q = _exact_text(query, name="q", maximum=SEARCH_QUERY_MAX)
        limit = _bounded_int(limit, name="limit", default=20, minimum=1, maximum=SEARCH_LIMIT_MAX)
        offset = _bounded_int(offset, name="offset", default=0, minimum=0, maximum=SEARCH_OFFSET_MAX)
        requested = tuple(kinds or ("rule", "card", "official_ruling", "errata", "official_source"))
        unknown = [k for k in requested if k not in SEARCH_KINDS]
        if unknown:
            raise ProductApiError(400, "invalid_search_kind", "One or more search kinds are not supported.", {"unsupported": unknown, "allowed": list(SEARCH_KINDS)})
        if not requested:
            raise ProductApiError(400, "invalid_search_kind", "At least one search kind is required.", {"allowed": list(SEARCH_KINDS)})
        cache_key = ("search", self.runtime_guard.snapshot_id, q, requested, limit, offset)
        found, cached = self._search_cache.get(cache_key)
        if found and cached is not None:
            return cached
        hits = retrieval_search(self.db, q, limit=limit + 1, kinds=requested, offset=offset)
        page = hits[:limit]
        result = {
            "ok": True,
            "apiVersion": API_VERSION,
            "query": q,
            "kinds": list(requested),
            "offset": offset,
            "limit": limit,
            "returned": len(page),
            "hasMore": len(hits) > len(page),
            "results": [_hit_summary(x) for x in page],
        }
        self._search_cache.set(cache_key, result)
        return result

    def get_rule(self, rule_id: str, *, family: str | None = None) -> dict[str, Any]:
        self._assert_runtime_current()
        rid = _exact_text(rule_id, name="ruleId", maximum=64)
        fam = family.casefold().strip() if isinstance(family, str) else None
        if fam is not None and fam not in {"core", "tournament"}:
            raise ProductApiError(400, "invalid_rules_family", "family must be 'core' or 'tournament'.", {"family": family})
        in_core = rid in self._core_by_id
        in_tr = rid in self._tournament_by_id
        if fam is None:
            if in_core and in_tr:
                raise ProductApiError(409, "ambiguous_rule_id", "This rule ID exists in both Core and Tournament Rules; specify a family.", {"ruleId": rid, "families": ["core", "tournament"]})
            if in_core:
                fam = "core"
            elif in_tr:
                fam = "tournament"
            else:
                raise ProductApiError(404, "rule_not_found", "Rule was not found.", {"ruleId": rid})
        by_id = self._core_by_id if fam == "core" else self._tournament_by_id
        row = by_id.get(rid)
        if row is None:
            raise ProductApiError(404, "rule_not_found", "Rule was not found in the requested family.", {"ruleId": rid, "family": fam})
        navigation = {
            "parentRuleId": row.get("parentRuleId"),
            "previousRuleId": row.get("previousRuleId"),
            "nextRuleId": row.get("nextRuleId"),
            "childRuleIds": list(row.get("childRuleIds") or []),
            "resolvedCrossReferences": list(row.get("resolvedCrossReferences") or []),
            "unresolvedCrossReferences": list(row.get("unresolvedCrossReferences") or []),
        }
        return {
            "ok": True,
            "apiVersion": API_VERSION,
            "family": fam,
            "rule": {
                "ruleId": rid,
                "internalRuleId": row.get("internalRuleId"),
                "text": row.get("normativeText") or row.get("text") or "",
                "exampleText": row.get("exampleText") or "",
                "pageStart": row.get("pageStart"),
                "pageEnd": row.get("pageEnd"),
                "sourceId": row.get("sourceId"),
                "majorSectionRuleId": row.get("majorSectionRuleId"),
                "majorSectionTitle": row.get("majorSectionTitle"),
                "visualSubsection": row.get("visualSubsection"),
                "textSha256": row.get("textSha256"),
                "navigation": navigation,
            },
            "citationId": ("R:" if fam == "core" else "TR:") + rid,
        }

    def _card_public(self, card: dict[str, Any]) -> dict[str, Any]:
        cid = str(card.get("id") or "")
        interaction = self._interaction_printing.get(cid) or {}
        return {
            "id": cid,
            "name": card.get("name"),
            "setId": card.get("setId"),
            "setLabel": card.get("setLabel"),
            "collectorCode": card.get("collectorCode"),
            "collectorNumber": card.get("collectorNumber"),
            "type": card.get("type"),
            "supertype": card.get("supertype"),
            "rarity": card.get("rarity"),
            "domains": list(card.get("domains") or []),
            "energy": card.get("energy"),
            "might": card.get("might"),
            "power": card.get("power"),
            "effectiveText": card.get("effectiveText") or "",
            "databaseText": card.get("databaseText") or "",
            "knownPrintedText": card.get("knownPrintedText"),
            "textSource": card.get("textSource"),
            "officialErrataTimeline": list(card.get("officialErrataTimeline") or []),
            "imageUrl": card.get("imageUrl"),
            "interactionIdentityKey": interaction.get("identityKey"),
            "effectiveTextSha256": interaction.get("effectiveTextSha256"),
            "citationId": f"C:{cid}",
        }

    def get_card(self, identifier: str) -> dict[str, Any]:
        self._assert_runtime_current()
        ident = _exact_text(identifier, name="card", maximum=256)
        exact = self._cards_by_id.get(ident)
        if exact is not None:
            selected = [exact]
            lookup = "printing_id"
        else:
            selected = list(self._cards_by_name.get(ident.casefold(), []))
            lookup = "exact_name"
        if not selected:
            raise ProductApiError(404, "card_not_found", "No card matched the exact printing ID or exact card name.", {"identifier": ident, "fuzzyLookupUsed": False})
        variant_ids: list[str] = []
        identity_keys = {str((self._interaction_printing.get(str(c.get("id"))) or {}).get("identityKey") or "") for c in selected}
        identity_keys.discard("")
        for key in sorted(identity_keys):
            identity = self._interaction_identity.get(key) or {}
            variant_ids.extend(str(x) for x in identity.get("printingIds", []) if str(x) not in variant_ids)
        variants = [self._cards_by_id[x] for x in variant_ids if x in self._cards_by_id]
        if not variants:
            variants = selected
        return {
            "ok": True,
            "apiVersion": API_VERSION,
            "lookup": lookup,
            "identifier": ident,
            "matchCount": len(selected),
            "matches": [self._card_public(x) for x in selected],
            "gameplayVariants": [self._card_public(x) for x in variants],
            "policy": {"fuzzyIdentityLookupUsed": False},
        }

    def ask(self, question: str) -> dict[str, Any]:
        self._assert_runtime_current()
        q = _exact_text(question, name="question", maximum=QUESTION_MAX)
        authority = self.engine.authority_status
        if self.require_current_authority and not authority.get("currentRulesComplete"):
            raise ProductApiError(503, "authority_incomplete", "Current gameplay authority is incomplete; adjudication is unavailable.", {"missing": authority.get("missing", [])})
        result = self.engine.ask(q)
        issues: list[dict[str, Any]] = []
        all_citations: list[str] = []
        for idx, issue in enumerate(result.get("issues", [])):
            ruling = issue.get("ruling") or {}
            trace = issue.get("proofTrace") or {}
            effective = ruling.get("effectiveVerdict") or {}
            accepted = [str(x.get("evidenceId")) for x in trace.get("acceptedEvidence", []) if x.get("evidenceId")]
            if not accepted:
                for out in ruling.get("outcomes", []) or []:
                    for ev in out.get("evidence", []) or []:
                        eid = ev.get("evidenceId")
                        if eid and str(eid) not in accepted:
                            accepted.append(str(eid))
            for eid in accepted:
                if eid not in all_citations:
                    all_citations.append(eid)
            issues.append({
                "index": idx,
                "question": issue.get("issue"),
                "interpretedQuestion": issue.get("interpretedIssue"),
                "status": ruling.get("status"),
                "verdict": effective.get("verdict"),
                "conclusion": effective.get("reason"),
                "clarifyingQuestions": list(issue.get("clarifyingQuestions") or []),
                "citations": accepted,
                "proof": {
                    "verified": bool((trace.get("verification") or {}).get("passed")),
                    "errors": list((trace.get("verification") or {}).get("errors") or []),
                    "evidenceComplete": bool((trace.get("completeness") or {}).get("evidenceCompleteForKnownObligations", False)),
                    "failClosedApplied": bool(trace.get("failClosedApplied")),
                    "rulePrograms": list(trace.get("rulePrograms") or []),
                    "cardInteractionPrograms": list(trace.get("cardInteractionPrograms") or []),
                },
            })
        return {
            "ok": True,
            "apiVersion": API_VERSION,
            "question": q,
            "answer": result.get("answer") or "",
            "deterministicAnswer": result.get("deterministicAnswer") or "",
            "issues": issues,
            "clarifyingQuestions": list(result.get("clarifyingQuestions") or []),
            "namedCards": [{"id": c.get("id"), "name": c.get("name"), "citationId": f"C:{c.get('id')}"} for c in result.get("namedCards", [])],
            "citations": all_citations,
            "authority": {
                "currentRulesComplete": bool((result.get("authorityStatus") or {}).get("currentRulesComplete")),
                "activeOverlays": list((result.get("authorityStatus") or {}).get("activeOverlays") or []),
            },
            "llm": {
                "interpretationAccepted": bool((result.get("llmInterpretation") or {}).get("accepted")),
                "explanationAccepted": bool((result.get("llmExplanation") or {}).get("accepted")),
                "usedForAdjudication": False,
            },
        }

    def get_evidence(self, evidence_id: str) -> dict[str, Any]:
        self._assert_runtime_current()
        eid = _exact_text(evidence_id, name="evidenceId", maximum=256)
        if eid.startswith("R:"):
            rid = eid[2:]
            row = self._core_by_id.get(rid)
            if row:
                return {"ok": True, "apiVersion": API_VERSION, "evidence": {"evidenceId": eid, "kind": "core_rule", "ruleId": rid, "text": row.get("normativeText") or "", "exampleText": row.get("exampleText") or "", "pageStart": row.get("pageStart"), "pageEnd": row.get("pageEnd"), "sourceId": row.get("sourceId"), "internalRuleId": row.get("internalRuleId")}}
        if eid.startswith("TR:"):
            rid = eid[3:]
            row = self._tournament_by_id.get(rid)
            if row:
                return {"ok": True, "apiVersion": API_VERSION, "evidence": {"evidenceId": eid, "kind": "tournament_rule", "ruleId": rid, "text": row.get("normativeText") or "", "exampleText": row.get("exampleText") or "", "pageStart": row.get("pageStart"), "pageEnd": row.get("pageEnd"), "sourceId": row.get("sourceId"), "internalRuleId": row.get("internalRuleId")}}
        if eid.startswith("C:"):
            cid = eid[2:]
            row = self._cards_by_id.get(cid)
            if row:
                return {"ok": True, "apiVersion": API_VERSION, "evidence": {"evidenceId": eid, "kind": "card_text", **self._card_public(row)}}
        doc = self._official_by_evidence.get(eid)
        if doc:
            return {"ok": True, "apiVersion": API_VERSION, "evidence": {"evidenceId": eid, "kind": "official_ruling" if doc.get("sourceType") == "official_faq" else doc.get("sourceType"), "sourceId": doc.get("sourceId"), "title": doc.get("title"), "heading": doc.get("heading"), "question": doc.get("question"), "text": doc.get("text") or "", "published": doc.get("published"), "effectiveFrom": doc.get("effectiveFrom"), "sourceUrl": doc.get("sourceUrl"), "authority": doc.get("authority") or {}, "explicitRuleReferences": list(doc.get("explicitRuleReferences") or [])}}
        errata_key = eid[2:] if eid.startswith("E:") else eid
        er = self._errata_by_entry.get(errata_key)
        if er:
            return {"ok": True, "apiVersion": API_VERSION, "evidence": {"evidenceId": f"E:{errata_key}", "kind": "card_errata", "entryId": errata_key, "sourceId": er.get("sourceId"), "sourceUrl": er.get("sourceUrl"), "published": er.get("published"), "release": er.get("release"), "cardName": er.get("cardName"), "oldText": er.get("oldText"), "newText": er.get("newText"), "page": er.get("page")}}
        raise ProductApiError(404, "evidence_not_found", "Evidence ID was not found.", {"evidenceId": eid})

    def sources(self) -> dict[str, Any]:
        self._assert_runtime_current()
        authority = self.engine.authority_status
        histories = {family: {"currentSourceId": self._histories[family].get("currentSourceId"), "versions": [_safe_version(x) for x in self._histories[family].get("versions", [])]} for family in FAMILIES}
        return {
            "ok": True,
            "apiVersion": API_VERSION,
            "authority": authority,
            "officialSources": [_safe_source(x) for x in self.manifest.get("sources", [])],
            "ruleVersionHistories": histories,
        }

    def changes(self, family: str, *, source_id: str | None = None) -> dict[str, Any]:
        self._assert_runtime_current()
        fam = _exact_text(family, name="family", maximum=32).casefold()
        if fam not in FAMILIES:
            raise ProductApiError(400, "invalid_rules_family", "family must be 'core' or 'tournament'.", {"family": family})
        history = self._histories[fam]
        versions = list(history.get("versions", []))
        if not versions:
            raise ProductApiError(404, "version_history_not_found", "No version history exists for this rules family.", {"family": fam})
        if source_id is None:
            target = next((x for x in versions if x.get("sourceId") == history.get("currentSourceId")), versions[-1])
        else:
            sid = _exact_text(source_id, name="sourceId", maximum=128)
            target = next((x for x in versions if x.get("sourceId") == sid), None)
            if target is None:
                raise ProductApiError(404, "version_not_found", "Requested rules version was not found.", {"family": fam, "sourceId": sid})
        previous_id = target.get("previousSourceId")
        previous = next((x for x in versions if x.get("sourceId") == previous_id), None) if previous_id else None
        details: list[dict[str, Any]] = []
        diff_path = self.root / "data/source/rule_versions" / fam / "staged" / str(target.get("sourceId")) / "diff.json"
        if diff_path.exists():
            diff = _load(diff_path, {})
            details = list(diff.get("changes") or [])
        return {
            "ok": True,
            "apiVersion": API_VERSION,
            "family": fam,
            "sourceId": target.get("sourceId"),
            "previousSourceId": previous_id,
            "hasPreviousVersion": previous is not None,
            "current": _safe_version(target),
            "previous": _safe_version(previous) if previous else None,
            "changeCounts": dict(target.get("changeCounts") or {}),
            "detailedChangesAvailable": bool(details),
            "changes": details,
            "note": "PDF-to-PDF version diff is authoritative for Core/Tournament rule changes; patch notes are non-exhaustive context.",
        }
