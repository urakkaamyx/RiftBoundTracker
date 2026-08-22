#!/usr/bin/env python3
from __future__ import annotations

import http.client
import json
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import riftkeep_rules.product_api as product_api_module
from riftkeep_rules.api_http import MAX_BODY_BYTES, create_server, start_test_server
from riftkeep_rules.product_api import API_VERSION, ProductApiError, ProductApiService, SEARCH_KINDS

checks = 0
failures: list[dict[str, Any]] = []


def check(name: str, ok: bool, detail: Any = None) -> None:
    global checks
    checks += 1
    if not ok:
        failures.append({"check": name, "detail": detail})


def expect_api_error(name: str, fn, *, status: int, code: str) -> ProductApiError | None:
    try:
        fn()
    except ProductApiError as exc:
        check(name, exc.status == status and exc.code == code, {"status": exc.status, "code": exc.code, "details": exc.details})
        return exc
    except Exception as exc:
        check(name, False, f"unexpected {type(exc).__name__}: {exc}")
        return None
    check(name, False, "no error raised")
    return None


def contains_path_leak(value: Any) -> bool:
    raw = json.dumps(value, ensure_ascii=False).casefold()
    return "/mnt/" in raw or "\\mnt\\" in raw or "riftkeeprules_recovery" in raw.casefold()


contract = json.loads((ROOT / "contracts/product_api_contract.json").read_text(encoding="utf-8"))
service = ProductApiService(ROOT)

# T135 — contract/error model.
check("product API contract schema version is 1", contract.get("schemaVersion") == 1, contract.get("schemaVersion"))
check("product API contract version matches runtime", contract.get("apiVersion") == API_VERSION, {"contract": contract.get("apiVersion"), "runtime": API_VERSION})
check("product API contract keeps engine authoritative", (contract.get("policy") or {}).get("engineIsAuthority") is True, contract.get("policy"))
check("product API contract forbids filesystem path exposure", (contract.get("policy") or {}).get("filesystemPathsExposed") is False, contract.get("policy"))
check("product API contract forbids fuzzy card identity lookup", (contract.get("policy") or {}).get("fuzzyCardIdentityLookup") is False, contract.get("policy"))
check("stable error envelope is declared", (contract.get("errorEnvelope") or {}).get("ok") is False and "error" in (contract.get("errorEnvelope") or {}), contract.get("errorEnvelope"))
check("all required product service methods are declared", set((contract.get("serviceMethods") or {}).keys()) == {"status", "search", "getRule", "getCard", "ask", "getEvidence", "sources", "changes"}, contract.get("serviceMethods"))
check("all required HTTP routes are declared", len(contract.get("httpRoutes") or []) == 8, contract.get("httpRoutes"))

# T136 — status/authority/source summary.
status = service.status()
check("status succeeds", status.get("ok") is True and status.get("apiVersion") == API_VERSION, status)
check("status reports 2381 Core rules", (status.get("corpus") or {}).get("coreRules") == 2381, status.get("corpus"))
check("status reports 935 Tournament rules", (status.get("corpus") or {}).get("tournamentRules") == 935, status.get("corpus"))
check("status reports 1304 cards", (status.get("corpus") or {}).get("cards") == 1304, status.get("corpus"))
check("status reports 35 current FAQ sections", (status.get("corpus") or {}).get("currentFaqSections") == 35, status.get("corpus"))
check("status reports 63 errata events", (status.get("corpus") or {}).get("officialErrataEvents") == 63, status.get("corpus"))
check("status reports current gameplay authority complete", (status.get("authority") or {}).get("currentRulesComplete") is True, status.get("authority"))
check("status reports current Core source ID", (status.get("sources") or {}).get("coreSourceId") == "core-rules-2026-07-16", status.get("sources"))
check("status reports current Tournament source ID", (status.get("sources") or {}).get("tournamentSourceId") == "tournament-rules-2026-07-16", status.get("sources"))
check("status reports Vendetta active overlay", "vendetta-faq-2026-08-14" in (status.get("sources") or {}).get("activeOverlays", []), status.get("sources"))
check("status does not leak filesystem paths", not contains_path_leak(status), status)

sources = service.sources()
check("sources succeeds", sources.get("ok") is True, sources)
check("sources exposes registered official sources", len(sources.get("officialSources") or []) >= 15, len(sources.get("officialSources") or []))
check("sources strips localSnapshot fields", all("localSnapshot" not in x and "localStructuredSnapshot" not in x for x in sources.get("officialSources", [])), sources.get("officialSources"))
check("sources strips archived filesystem locations", not contains_path_leak(sources), sources)
check("Core source history current pointer is correct", ((sources.get("ruleVersionHistories") or {}).get("core") or {}).get("currentSourceId") == "core-rules-2026-07-16", sources.get("ruleVersionHistories"))
check("Tournament source history current pointer is correct", ((sources.get("ruleVersionHistories") or {}).get("tournament") or {}).get("currentSourceId") == "tournament-rules-2026-07-16", sources.get("ruleVersionHistories"))

# T137 — unified search.
gank = service.search("Ganking", limit=5)
check("Ganking search succeeds", gank.get("ok") is True and gank.get("returned", 0) > 0, gank)
check("Ganking search returns keyword rule 810", any(x.get("kind") == "rule" and x.get("ruleId") == "810" for x in gank.get("results", [])), gank.get("results"))
check("Ganking search result has exact canonical text", any(x.get("ruleId") == "810" and x.get("text") == "Ganking" for x in gank.get("results", [])), gank.get("results"))
card_search = service.search("Svellsongur", kinds=["card"], limit=10)
check("card-only search returns only cards", card_search.get("returned", 0) > 0 and all(x.get("kind") == "card" for x in card_search.get("results", [])), card_search.get("results"))
check("card-only search finds Svellsongur", any(x.get("name") == "Svellsongur" for x in card_search.get("results", [])), card_search.get("results"))
faq_search = service.search("Might copyable trait", kinds=["official_ruling"], limit=10)
check("official-ruling search is filterable", all(x.get("kind") == "official_ruling" for x in faq_search.get("results", [])), faq_search.get("results"))
check("official-ruling search finds current FAQ", any(str(x.get("evidenceId") or "").startswith("O:vendetta-faq-2026-08-14:") for x in faq_search.get("results", [])), faq_search.get("results"))
p1 = service.search("Ganking", limit=1, offset=0)
p2 = service.search("Ganking", limit=1, offset=1)
check("search pagination returns distinct rows", p1["results"][0]["id"] != p2["results"][0]["id"], {"p1": p1["results"], "p2": p2["results"]})
check("search pagination reports hasMore", p1.get("hasMore") is True, p1)
check("search results do not leak filesystem paths", not contains_path_leak(gank) and not contains_path_leak(card_search), {"rules": gank, "cards": card_search})
check("search kind allowlist is frozen", set(SEARCH_KINDS) == {"rule", "card", "official_ruling", "official_ruling_history", "errata", "official_source", "patch_note_history"}, SEARCH_KINDS)
expect_api_error("empty search rejected", lambda: service.search("  "), status=400, code="invalid_parameter")
expect_api_error("unsupported search kind rejected", lambda: service.search("Ganking", kinds=["filesystem"]), status=400, code="invalid_search_kind")
expect_api_error("search limit zero rejected", lambda: service.search("Ganking", limit=0), status=400, code="parameter_out_of_range")
expect_api_error("search limit over maximum rejected", lambda: service.search("Ganking", limit=101), status=400, code="parameter_out_of_range")
expect_api_error("negative search offset rejected", lambda: service.search("Ganking", offset=-1), status=400, code="parameter_out_of_range")
expect_api_error("overlong search query rejected", lambda: service.search("x" * 501), status=400, code="parameter_too_long")

# T138 — exact family-aware rule lookup.
r347 = service.get_rule("347.1.b", family="core")
check("Core 347.1.b exact text preserved", (r347.get("rule") or {}).get("text") == "When that Chain closes, Focus passes to the next Player in Turn Order.", r347)
check("Core rule lookup returns R citation", r347.get("citationId") == "R:347.1.b", r347)
check("Core rule lookup exposes provenance", (r347.get("rule") or {}).get("sourceId") == "core-rules-2026-07-16" and (r347.get("rule") or {}).get("internalRuleId"), r347)
tr104 = service.get_rule("104.1", family="tournament")
check("Tournament 104.1 lookup succeeds", tr104.get("family") == "tournament" and "takes precedence" in (tr104.get("rule") or {}).get("text", ""), tr104)
check("Tournament rule lookup returns TR citation", tr104.get("citationId") == "TR:104.1", tr104)
amb = expect_api_error("overlapping rule ID requires family", lambda: service.get_rule("000"), status=409, code="ambiguous_rule_id")
check("ambiguous rule error lists both families", amb is not None and amb.details.get("families") == ["core", "tournament"], amb.details if amb else None)
expect_api_error("invalid rules family rejected", lambda: service.get_rule("347", family="magic"), status=400, code="invalid_rules_family")
expect_api_error("missing Core rule rejected", lambda: service.get_rule("9999.1", family="core"), status=404, code="rule_not_found")
check("rule lookup does not leak filesystem paths", not contains_path_leak(r347) and not contains_path_leak(tr104), {"core": r347, "tr": tr104})

# T139 — exact card lookup and provenance.
sv_id = service.get_card("jdg-059-221")
check("printing-ID card lookup succeeds", sv_id.get("lookup") == "printing_id" and sv_id.get("matchCount") == 1, sv_id)
check("printing-ID lookup returns Svellsongur", (sv_id.get("matches") or [{}])[0].get("name") == "Svellsongur", sv_id.get("matches"))
sv_name = service.get_card("Svellsongur")
check("exact-name lookup is case-insensitive and can return variants", sv_name.get("lookup") == "exact_name" and sv_name.get("matchCount", 0) >= 1 and len(sv_name.get("gameplayVariants") or []) >= sv_name.get("matchCount", 0), sv_name)
check("card lookup exposes effective-text provenance", all(x.get("textSource") and x.get("effectiveTextSha256") for x in sv_name.get("matches", [])), sv_name.get("matches"))
check("card lookup exposes C citation", all(str(x.get("citationId") or "").startswith("C:") for x in sv_name.get("matches", [])), sv_name.get("matches"))
check("card lookup states fuzzy matching was not used", (sv_name.get("policy") or {}).get("fuzzyIdentityLookupUsed") is False, sv_name.get("policy"))
expect_api_error("card typo does not fuzzy-match", lambda: service.get_card("Svellsongurr"), status=404, code="card_not_found")
err_card = service.get_card("ogn-005-298")
check("errata-affected card exposes official timeline", bool((err_card.get("matches") or [{}])[0].get("officialErrataTimeline")), err_card.get("matches"))
check("card lookup does not leak filesystem paths", not contains_path_leak(err_card), err_card)

# T140 — Ask-Rules product response and deterministic parity.
q1 = "If my unit is already tapped, can I tap it again to pay a cost?"
api_ask = service.ask(q1)
raw_ask = service.engine.ask(q1)
check("Ask succeeds", api_ask.get("ok") is True and api_ask.get("question") == q1, api_ask)
check("Ask preserves backend-rendered answer exactly", api_ask.get("answer") == raw_ask.get("answer"), {"api": api_ask.get("answer"), "engine": raw_ask.get("answer")})
check("Ask preserves deterministic answer exactly", api_ask.get("deterministicAnswer") == raw_ask.get("deterministicAnswer"), None)
check("Ask returns one decided issue", len(api_ask.get("issues", [])) == 1 and api_ask["issues"][0].get("status") == "decided", api_ask.get("issues"))
check("Ask returns fixed no verdict", api_ask["issues"][0].get("verdict") == "no", api_ask.get("issues"))
check("Ask reports proof verification", (api_ask["issues"][0].get("proof") or {}).get("verified") is True, api_ask["issues"][0].get("proof"))
check("Ask returns governing citations", set(api_ask.get("citations", [])) >= {"R:414.1", "R:414.1.b", "R:414.1.c", "R:414.4"}, api_ask.get("citations"))
check("Ask explicitly says LLM not used for adjudication", (api_ask.get("llm") or {}).get("usedForAdjudication") is False, api_ask.get("llm"))
check("Ask reports current authority complete", (api_ask.get("authority") or {}).get("currentRulesComplete") is True, api_ask.get("authority"))
check("Ask product response does not expose raw retrieval internals", all("retrieval" not in x and "evidenceCatalog" not in x for x in api_ask.get("issues", [])), api_ask.get("issues"))
check("Ask product response does not leak filesystem paths", not contains_path_leak(api_ask), api_ask)

multi_q = "Can I summon a unit straight to a battlefield I control and is it contested?"
multi = service.ask(multi_q)
check("multipart Ask preserves two issue order", len(multi.get("issues", [])) == 2 and [x.get("index") for x in multi["issues"]] == [0, 1], multi.get("issues"))
check("multipart Ask verdicts are yes then no", [x.get("verdict") for x in multi["issues"]] == ["yes", "no"], multi.get("issues"))
conditional = service.ask("Can I play a unit to a battlefield?")
check("conditional Ask does not invent a verdict", conditional["issues"][0].get("status") == "conditional" and conditional["issues"][0].get("verdict") == "conditional", conditional.get("issues"))
check("conditional Ask returns clarification", any(x.get("fact") == "actor_controls_battlefield" for x in conditional["issues"][0].get("clarifyingQuestions", [])), conditional["issues"][0].get("clarifyingQuestions"))

promotions = json.loads((ROOT / "data/gold/gold_c_promotions.json").read_text(encoding="utf-8"))
promo = (promotions.get("promotions") or [])[0]
card_ask = service.ask(promo["question"])
check("promoted M13 Ask remains decided through Product API", all(x.get("status") == "decided" for x in card_ask.get("issues", [])), card_ask.get("issues"))
check("promoted M13 Ask exposes card-interaction proof provenance", any((x.get("proof") or {}).get("cardInteractionPrograms") for x in card_ask.get("issues", [])), card_ask.get("issues"))
expect_api_error("empty Ask question rejected", lambda: service.ask("  "), status=400, code="invalid_parameter")
expect_api_error("overlong Ask question rejected", lambda: service.ask("x" * 4001), status=400, code="parameter_too_long")

# Simulate authority loss without mutating the project. Service must fail before engine.ask.
original_authority_status = service.engine.authority_status
try:
    service.engine.authority_status = {"currentRulesComplete": False, "missing": [{"sourceId": "synthetic", "reason": "test"}]}
    expect_api_error("Ask fails closed when current authority is incomplete", lambda: service.ask("Can I play a unit?"), status=503, code="authority_incomplete")
finally:
    service.engine.authority_status = original_authority_status

# T141 — evidence/source history/what-changed.
e414 = service.get_evidence("R:414.1.b")
check("Core evidence resolver returns exact rule", (e414.get("evidence") or {}).get("text") == "A Game Object that is already Exhausted cannot be Exhausted again.", e414)
tr_e = service.get_evidence("TR:104.1")
check("Tournament evidence resolver returns tournament kind", (tr_e.get("evidence") or {}).get("kind") == "tournament_rule", tr_e)
card_e = service.get_evidence("C:jdg-059-221")
check("card evidence resolver returns exact printing", (card_e.get("evidence") or {}).get("id") == "jdg-059-221", card_e)
faq_e = service.get_evidence("O:vendetta-faq-2026-08-14:0030")
check("FAQ evidence resolver returns current official ruling", (faq_e.get("evidence") or {}).get("kind") == "official_ruling" and (faq_e.get("evidence") or {}).get("sourceId") == "vendetta-faq-2026-08-14", faq_e)
errata_e = service.get_evidence("E:origins-errata:008")
check("errata evidence resolver returns old/new text", (errata_e.get("evidence") or {}).get("kind") == "card_errata" and (errata_e.get("evidence") or {}).get("oldText") and (errata_e.get("evidence") or {}).get("newText"), errata_e)
expect_api_error("unknown evidence rejected", lambda: service.get_evidence("R:9999.9"), status=404, code="evidence_not_found")
check("evidence responses do not leak filesystem paths", not any(contains_path_leak(x) for x in (e414, tr_e, card_e, faq_e, errata_e)), None)

core_changes = service.changes("core")
check("current Core changes endpoint succeeds", core_changes.get("ok") is True and core_changes.get("sourceId") == "core-rules-2026-07-16", core_changes)
check("single-version Core history reports no previous version", core_changes.get("hasPreviousVersion") is False and core_changes.get("previous") is None, core_changes)
check("changes endpoint states PDF diff authority", "PDF-to-PDF" in core_changes.get("note", ""), core_changes)
expect_api_error("invalid changes family rejected", lambda: service.changes("deck"), status=400, code="invalid_rules_family")
expect_api_error("unknown changes source rejected", lambda: service.changes("core", source_id="missing"), status=404, code="version_not_found")

# Synthetic adjacent-version history proves future detailed change records can be surfaced.
with tempfile.TemporaryDirectory(prefix="riftkeep_api_changes_") as td:
    tmp = Path(td)
    hp = tmp / "data/source/rule_versions/core/history.json"
    hp.parent.mkdir(parents=True)
    hp.write_text(json.dumps({"schemaVersion": 1, "family": "core", "currentSourceId": "core-new", "versions": [
        {"sourceId": "core-old", "status": "superseded", "sourceSha256": "a" * 64, "ruleCount": 10},
        {"sourceId": "core-new", "status": "current", "sourceSha256": "b" * 64, "ruleCount": 11, "previousSourceId": "core-old", "changeCounts": {"ADDED": 1}}
    ]}), encoding="utf-8")
    dp = tmp / "data/source/rule_versions/core/staged/core-new/diff.json"
    dp.parent.mkdir(parents=True)
    dp.write_text(json.dumps({"changeCounts": {"ADDED": 1}, "changes": [{"classification": "ADDED", "newRuleId": "999"}]}), encoding="utf-8")
    fake = object.__new__(ProductApiService)
    fake.root = tmp
    fake._allow_missing_runtime_guard_for_fixture = True
    fake._histories = {"core": json.loads(hp.read_text(encoding="utf-8"))}
    synthetic = ProductApiService.changes(fake, "core")
    check("adjacent-version changes report previous source", synthetic.get("hasPreviousVersion") is True and synthetic.get("previousSourceId") == "core-old", synthetic)
    check("adjacent-version changes expose frozen counts", synthetic.get("changeCounts") == {"ADDED": 1}, synthetic)
    check("adjacent-version changes expose detailed diff when available", synthetic.get("detailedChangesAvailable") is True and synthetic.get("changes") == [{"classification": "ADDED", "newRuleId": "999"}], synthetic)

# T142/T143 — actual HTTP adapter.
server, thread = start_test_server(ROOT, service=service)
port = int(server.server_address[1])
base = f"http://127.0.0.1:{port}"


def http_json(path: str, *, method: str = "GET", body: Any = None, headers: dict[str, str] | None = None) -> tuple[int, dict[str, Any], Any]:
    data = None
    req_headers = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(base + path, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8")), resp.headers
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8")), exc.headers

try:
    code, payload, headers = http_json("/v1/status")
    check("HTTP status route returns 200 JSON", code == 200 and payload.get("ok") is True, {"code": code, "payload": payload})
    check("HTTP status route sends no-store", headers.get("Cache-Control") == "no-store", dict(headers.items()))
    check("HTTP status route sends API version header", headers.get("X-RiftKeep-API-Version") == API_VERSION, dict(headers.items()))
    check("HTTP Server header does not expose Python version", "Python" not in (headers.get("Server") or ""), headers.get("Server"))

    code, payload, _ = http_json("/v1/search?q=Ganking&kind=rule&limit=2&offset=0")
    check("HTTP search route works", code == 200 and payload.get("returned") == 2 and all(x.get("kind") == "rule" for x in payload.get("results", [])), payload)
    code, payload, _ = http_json("/v1/rules/core/347.1.b")
    check("HTTP rule route works", code == 200 and (payload.get("rule") or {}).get("ruleId") == "347.1.b", payload)
    card_name_path = "/v1/cards/" + urllib.parse.quote("Vilemaw's Lair", safe="")
    code, payload, _ = http_json(card_name_path)
    check("HTTP exact-name card route handles URL encoding", code == 200 and all(x.get("name") == "Vilemaw's Lair" for x in payload.get("matches", [])), payload)
    ev_path = "/v1/evidence/" + urllib.parse.quote("O:vendetta-faq-2026-08-14:0030", safe="")
    code, payload, _ = http_json(ev_path)
    check("HTTP evidence route resolves encoded evidence IDs", code == 200 and (payload.get("evidence") or {}).get("sourceId") == "vendetta-faq-2026-08-14", payload)
    code, payload, _ = http_json("/v1/sources")
    check("HTTP sources route works", code == 200 and payload.get("ok") is True, payload)
    code, payload, _ = http_json("/v1/changes?family=core")
    check("HTTP changes route works", code == 200 and payload.get("family") == "core", payload)
    code, payload, _ = http_json("/v1/ask", method="POST", body={"question": q1})
    check("HTTP Ask route returns deterministic verdict", code == 200 and payload.get("issues", [{}])[0].get("verdict") == "no", payload)
    check("HTTP Ask matches service answer", payload.get("answer") == api_ask.get("answer"), None)

    code, payload, _ = http_json("/v1/ask")
    check("GET on Ask route returns stable 405", code == 405 and (payload.get("error") or {}).get("code") == "method_not_allowed", payload)
    code, payload, _ = http_json("/v1/status", method="POST", body={})
    check("POST on GET route returns stable 405", code == 405 and (payload.get("error") or {}).get("code") == "method_not_allowed", payload)
    code, payload, _ = http_json("/v1/missing")
    check("unknown HTTP route returns JSON 404", code == 404 and (payload.get("error") or {}).get("code") == "route_not_found", payload)
    code, payload, _ = http_json("/v1/status?extra=1")
    check("unknown query parameter rejected", code == 400 and (payload.get("error") or {}).get("code") == "unknown_query_parameters", payload)
    code, payload, _ = http_json("/v1/search")
    check("missing search q rejected", code == 400 and (payload.get("error") or {}).get("code") == "missing_parameter", payload)
    code, payload, _ = http_json("/v1/search?q=Ganking&limit=1&limit=2")
    check("duplicate query parameter rejected", code == 400 and (payload.get("error") or {}).get("code") == "duplicate_parameter", payload)
    code, payload, _ = http_json("/v1/ask", method="POST", body={"question": q1, "verdict": "yes"})
    check("unknown Ask body fields rejected", code == 400 and (payload.get("error") or {}).get("code") == "unknown_fields", payload)
    code, payload, _ = http_json("/v1/ask", method="POST", body={})
    check("missing Ask question field rejected", code == 400 and (payload.get("error") or {}).get("code") == "missing_field", payload)
    code, payload, _ = http_json("/v1/ask", method="POST", body={"question": q1}, headers={"Content-Type": "text/plain"})
    check("non-JSON Ask content type rejected", code == 415 and (payload.get("error") or {}).get("code") == "unsupported_media_type", payload)

    # Raw invalid JSON.
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    conn.request("POST", "/v1/ask", body=b"{bad", headers={"Content-Type": "application/json", "Content-Length": "4"})
    resp = conn.getresponse(); raw = json.loads(resp.read().decode("utf-8")); conn.close()
    check("invalid JSON returns stable 400", resp.status == 400 and (raw.get("error") or {}).get("code") == "invalid_json", raw)

    # Oversized request rejected before reading the body.
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    conn.putrequest("POST", "/v1/ask")
    conn.putheader("Content-Type", "application/json")
    conn.putheader("Content-Length", str(MAX_BODY_BYTES + 1))
    conn.endheaders()
    resp = conn.getresponse(); raw = json.loads(resp.read().decode("utf-8")); conn.close()
    check("oversized HTTP body returns 413", resp.status == 413 and (raw.get("error") or {}).get("code") == "payload_too_large", raw)

    for method in ("PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
        conn.request(method, "/v1/status")
        resp = conn.getresponse()
        body = resp.read()
        # HEAD semantics may suppress a response body at the HTTP client even though the
        # handler emits the same JSON status; status is the transport contract here.
        ok = resp.status == 405
        if body:
            try:
                ok = ok and (json.loads(body.decode("utf-8")).get("error") or {}).get("code") == "method_not_allowed"
            except Exception:
                ok = False
        conn.close()
        check(f"HTTP {method} is method-limited", ok, {"status": resp.status, "body": body[:200].decode("utf-8", "replace")})

    # URI length guard.
    code, payload, _ = http_json("/v1/search?q=" + ("x" * 4100))
    check("overlong HTTP URI returns 414", code == 414 and (payload.get("error") or {}).get("code") == "uri_too_long", {"code": code, "payload": payload})
finally:
    server.shutdown(); server.server_close(); thread.join(2)

# Binding safety is enforced before a non-loopback socket is opened.
try:
    create_server(ROOT, host="0.0.0.0", port=0)
except ValueError as exc:
    check("non-loopback bind requires explicit opt-in", "allow_remote" in str(exc), str(exc))
else:
    check("non-loopback bind requires explicit opt-in", False, "server unexpectedly created")

# Internal exceptions are sanitized to a stable 500 without traceback/path leakage.
class FailingService:
    def status(self):
        raise RuntimeError("secret /mnt/private/path should never escape")

fail_server, fail_thread = start_test_server(ROOT, service=FailingService())  # type: ignore[arg-type]
fail_port = int(fail_server.server_address[1])
try:
    req = urllib.request.Request(f"http://127.0.0.1:{fail_port}/v1/status")
    try:
        urllib.request.urlopen(req, timeout=10)
    except urllib.error.HTTPError as exc:
        payload = json.loads(exc.read().decode("utf-8"))
        check("unexpected HTTP exceptions become stable 500", exc.code == 500 and (payload.get("error") or {}).get("code") == "internal_error", payload)
        check("HTTP 500 does not leak exception text/path", "secret" not in json.dumps(payload) and "/mnt/" not in json.dumps(payload), payload)
finally:
    fail_server.shutdown(); fail_server.server_close(); fail_thread.join(2)

# Service output should be deterministic for identical inputs when no provider is configured.
check("status response deterministic", service.status() == service.status(), None)
check("search response deterministic", service.search("Ganking", limit=5) == service.search("Ganking", limit=5), None)
check("rule lookup response deterministic", service.get_rule("347.1.b", family="core") == service.get_rule("347.1.b", family="core"), None)
check("card lookup response deterministic", service.get_card("jdg-059-221") == service.get_card("jdg-059-221"), None)

metrics = {
    "schemaVersion": 1,
    "apiVersion": API_VERSION,
    "serviceMethods": sorted((contract.get("serviceMethods") or {}).keys()),
    "httpRouteCount": len(contract.get("httpRoutes") or []),
    "searchKinds": list(SEARCH_KINDS),
    "currentAuthorityComplete": (status.get("authority") or {}).get("currentRulesComplete"),
    "loopbackDefault": True,
    "maxBodyBytes": MAX_BODY_BYTES,
    "filesystemPathsExposed": False,
}
(ROOT / "data/validation/product_api_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
report = {"schemaVersion": 1, "passed": not failures, "checkCount": checks, "failureCount": len(failures), "failures": failures, "metrics": metrics}
(ROOT / "data/validation/product_api_test_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"passed": report["passed"], "checkCount": checks, "failureCount": len(failures), "failures": failures[:20], "metrics": metrics}, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["passed"] else 1)
