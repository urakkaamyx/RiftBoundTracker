#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from riftkeep_rules.api_http import STATIC_ROUTES, STATIC_SECURITY_HEADERS, start_test_server

checks = 0
failures: list[dict[str, object]] = []


def check(name: str, condition: bool, detail: object = None) -> None:
    global checks
    checks += 1
    if not condition:
        failures.append({"check": name, "detail": detail})


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class MarkupAudit(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.labels_for: list[str] = []
        self.tags: list[tuple[str, dict[str, str]]] = []
        self.external_refs: list[str] = []
        self.scripts: list[dict[str, str]] = []
        self.stylesheets: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        d = {k: (v or "") for k, v in attrs}
        self.tags.append((tag, d))
        if d.get("id"):
            self.ids.append(d["id"])
        if tag == "label" and d.get("for"):
            self.labels_for.append(d["for"])
        if tag == "script":
            self.scripts.append(d)
            src = d.get("src", "")
            if src.startswith(("http://", "https://", "//")):
                self.external_refs.append(src)
        if tag == "link":
            self.stylesheets.append(d)
            href = d.get("href", "")
            if href.startswith(("http://", "https://", "//")):
                self.external_refs.append(href)
        for attr in ("src", "href"):
            value = d.get(attr, "")
            if value.startswith(("http://", "https://", "//")):
                self.external_refs.append(value)


def http(base: str, path: str, *, method: str = "GET", body: dict | None = None) -> tuple[int, dict[str, str], bytes]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            return response.status, dict(response.headers.items()), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers.items()), exc.read()


contract = load_json(ROOT / "contracts/ui_contract.json")
release_manifest = load_json(ROOT / "MILESTONE.json")
html_text = (ROOT / "web/index.html").read_text(encoding="utf-8")
css_text = (ROOT / "web/styles.css").read_text(encoding="utf-8")
js_text = (ROOT / "web/app.js").read_text(encoding="utf-8")
parser = MarkupAudit()
parser.feed(html_text)

# T146: contract / no-rules-logic boundary.
check("ui_contract_schema_v1", contract.get("schemaVersion") == 1, contract)
policy = contract.get("policy") or {}
check("ui_contract_product_api_only", policy.get("productApiIsOnlyDataAuthority") is True, policy)
check("ui_contract_browser_adjudication_false", policy.get("browserAdjudicationLogic") is False, policy)
check("ui_contract_browser_evidence_selection_false", policy.get("browserEvidenceSelectionLogic") is False, policy)
check("ui_contract_browser_card_identity_inference_false", policy.get("browserCardIdentityInference") is False, policy)
check("ui_contract_browser_rule_semantics_false", policy.get("browserRuleSemantics") is False, policy)
check("ui_contract_same_origin", policy.get("sameOriginApiOnly") is True, policy)
check("ui_contract_no_external_runtime", policy.get("externalRuntimeDependencies") is False, policy)
check("ui_contract_no_dynamic_html", policy.get("dynamicHtmlInjection") is False, policy)
check("ui_contract_no_paths", policy.get("filesystemPathsExposed") is False, policy)
check("ui_contract_all_product_surfaces", set(contract.get("surfaces") or []) == {"ask_rules", "search", "card_rule_detail", "evidence", "sources_history", "changes"}, contract.get("surfaces"))
check("ui_contract_static_allowlist_matches_server", set(contract.get("staticRoutes") or []) == set(STATIC_ROUTES), {"contract": contract.get("staticRoutes"), "server": list(STATIC_ROUTES)})

# T147/T152: HTML shell + accessibility.
check("html_has_language", '<html lang="en">' in html_text)
check("html_has_viewport", 'name="viewport"' in html_text)
check("html_unique_ids", len(parser.ids) == len(set(parser.ids)), {"ids": len(parser.ids), "unique": len(set(parser.ids))})
check("html_labels_resolve", all(target in set(parser.ids) for target in parser.labels_for), parser.labels_for)
check("html_skip_link", 'class="skip-link"' in html_text and 'href="#main-content"' in html_text)
check("html_main_landmark", any(tag == "main" and attrs.get("id") == "main-content" for tag, attrs in parser.tags))
check("html_nav_labeled", any(tag == "nav" and attrs.get("aria-label") for tag, attrs in parser.tags))
check("html_footer_landmark", any(tag == "footer" for tag, _ in parser.tags))
check("html_live_status", sum(1 for tag, attrs in parser.tags if attrs.get("aria-live") == "polite") >= 3)
check("html_dialog_labeled", any(tag == "dialog" and attrs.get("aria-labelledby") for tag, attrs in parser.tags))
check("ask_textarea_labeled", "ask-question" in parser.labels_for)
check("search_input_labeled", "search-query" in parser.labels_for)
check("search_kind_labeled", "search-kind" in parser.labels_for)
check("changes_family_labeled", "changes-family" in parser.labels_for)
check("ask_maxlength_4000", 'id="ask-question"' in html_text and 'maxlength="4000"' in html_text)
check("search_maxlength_500", 'id="search-query"' in html_text and 'maxlength="500"' in html_text)
check("ask_form_present", 'id="ask-form"' in html_text)
check("search_form_present", 'id="search-form"' in html_text)
check("evidence_dialog_present", 'id="evidence-dialog"' in html_text)
check("sources_view_present", 'id="view-sources"' in html_text)
check("authority_indicator_present", 'id="authority-pill"' in html_text)
check("proof_badge_present", 'id="answer-proof"' in html_text)
check("issue_list_present", 'id="issue-list"' in html_text)
check("clarification_render_hook", "clarifyingQuestions" in js_text)
check("keyboard_ctrl_enter", 'event.ctrlKey' in js_text and 'requestSubmit' in js_text)
check("reduced_motion_css", "prefers-reduced-motion" in css_text)
check("visible_focus_css", ":focus-visible" in css_text)
check("responsive_breakpoints", css_text.count("@media") >= 3, css_text.count("@media"))

# T153: offline and injection boundaries.
check("html_no_external_refs", not parser.external_refs, parser.external_refs)
check("html_only_local_script", len(parser.scripts) == 1 and parser.scripts[0].get("src") == "/app.js", parser.scripts)
check("html_only_local_stylesheet", any(x.get("href") == "/styles.css" for x in parser.stylesheets), parser.stylesheets)
for token in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function", "DOMParser"):
    check(f"js_forbids_{re.sub('[^a-zA-Z0-9]+', '_', token).strip('_')}", token not in js_text, token)
check("js_fetches_only_relative_api", not re.search(r"fetch\(\s*[`\"'](?:https?:)?//", js_text), "external fetch")
check("js_no_remote_url_literals", not re.search(r"https?://", js_text, re.I), "remote URL literal")
check("css_no_remote_import", "@import" not in css_text and not re.search(r"url\(\s*['\"]?https?://", css_text, re.I))
check("js_no_rule_id_literal_logic", not re.search(r"\b(?:R:|TR:)?\d{3}(?:\.\d+)?\b", js_text), "rule-number-like literal in app.js")
for phrase in ("can't beats can", "cant beats can", "replacement effect", "untargetable", "contested_on_entry", "unit_play_location"):
    check(f"js_no_semantic_phrase_{re.sub('[^a-z]+', '_', phrase.lower()).strip('_')}", phrase.lower() not in js_text.lower(), phrase)
check("js_uses_api_evidence_resolution", "/v1/evidence/" in js_text)
check("js_uses_api_ask", 'api("/v1/ask"' in js_text)
check("js_uses_api_search", "/v1/search?" in js_text)
check("js_uses_api_sources", 'api("/v1/sources")' in js_text)
check("js_uses_api_changes", "/v1/changes?family=" in js_text)
check("js_uses_api_rule_detail", "/v1/rules/" in js_text)
check("js_uses_api_card_detail", "/v1/cards/" in js_text)
check("js_does_not_use_image_urls", "imageUrl" not in js_text, "remote card images are intentionally not loaded in M15")

# Static server / security headers and real product paths.
server, thread = start_test_server(ROOT)
host, port = server.server_address
base = f"http://{host}:{port}"
try:
    expected_types = {
        "/": "text/html",
        "/index.html": "text/html",
        "/styles.css": "text/css",
        "/app.js": "text/javascript",
    }
    for path, content_type in expected_types.items():
        status, headers, raw = http(base, path)
        check(f"http_static_{path.replace('/', '_') or 'root'}_200", status == 200, status)
        check(f"http_static_{path.replace('/', '_') or 'root'}_type", headers.get("Content-Type", "").startswith(content_type), headers.get("Content-Type"))
        check(f"http_static_{path.replace('/', '_') or 'root'}_nonempty", len(raw) > 100, len(raw))
        check(f"http_static_{path.replace('/', '_') or 'root'}_no_store", headers.get("Cache-Control") == "no-store", headers.get("Cache-Control"))
        for header, value in STATIC_SECURITY_HEADERS.items():
            check(f"http_{path.replace('/', '_') or 'root'}_{header.lower().replace('-', '_')}", headers.get(header) == value, headers.get(header))
    status, headers, raw = http(base, "/")
    check("http_root_csp_self_script", "script-src 'self'" in headers.get("Content-Security-Policy", ""), headers.get("Content-Security-Policy"))
    check("http_root_csp_self_connect", "connect-src 'self'" in headers.get("Content-Security-Policy", ""), headers.get("Content-Security-Policy"))
    check("http_root_csp_blocks_objects", "object-src 'none'" in headers.get("Content-Security-Policy", ""), headers.get("Content-Security-Policy"))
    check("http_root_frame_denied", headers.get("X-Frame-Options") == "DENY", headers.get("X-Frame-Options"))
    check("http_root_no_python_server_version", "Python" not in headers.get("Server", ""), headers.get("Server"))

    # Exact static allowlist: traversal / arbitrary file exposure cannot escape web/.
    for path in ("/../MILESTONE.json", "/%2e%2e/MILESTONE.json", "/web/index.html", "/ROADMAP.md", "/favicon.ico"):
        status, headers, raw = http(base, path)
        check(f"http_static_reject_{re.sub('[^a-zA-Z0-9]+', '_', path)}", status == 404, {"path": path, "status": status, "body": raw[:200].decode('utf-8', 'replace')})
        check(f"http_static_reject_json_{re.sub('[^a-zA-Z0-9]+', '_', path)}", headers.get("Content-Type", "").startswith("application/json"), headers.get("Content-Type"))
    status, headers, raw = http(base, "/", method="POST", body={})
    check("http_post_static_405", status == 405, status)
    body = json.loads(raw)
    check("http_post_static_stable_error", body.get("error", {}).get("code") == "method_not_allowed", body)

    # Same-origin API paths used by the UI.
    status, _, raw = http(base, "/v1/status")
    status_payload = json.loads(raw)
    check("http_ui_status_200", status == 200 and status_payload.get("ok") is True, status_payload)
    check("http_ui_authority_complete", status_payload.get("authority", {}).get("currentRulesComplete") is True, status_payload.get("authority"))
    expected_release = {
        "milestone": release_manifest.get("milestone"),
        "releaseStatus": release_manifest.get("releaseStatus"),
        "tasksCompletedThrough": release_manifest.get("tasksCompletedThrough"),
    }
    actual_release = status_payload.get("release", {})
    check(
        "http_ui_release_matches_manifest",
        actual_release.get("milestone") == expected_release["milestone"]
        and actual_release.get("releaseStatus") == expected_release["releaseStatus"]
        and actual_release.get("tasksCompletedThrough") == expected_release["tasksCompletedThrough"]
        and actual_release.get("releaseStatus") in {"candidate", "released"},
        {"expected": expected_release, "actual": actual_release},
    )

    status, _, raw = http(base, "/v1/search?q=Ganking&kind=rule&limit=5&offset=0")
    search = json.loads(raw)
    check("http_ui_search_200", status == 200 and search.get("ok") is True, search)
    check("http_ui_search_results", search.get("returned", 0) > 0, search)
    check("http_ui_search_bounded", search.get("returned", 0) <= 5, search)

    status, _, raw = http(base, "/v1/cards/ogn-019-298")
    card = json.loads(raw)
    check("http_ui_card_200", status == 200 and card.get("ok") is True, card)
    check("http_ui_card_exact_identity", card.get("matches", [{}])[0].get("id") == "ogn-019-298", card)

    status, _, raw = http(base, "/v1/rules/core/355.2")
    rule = json.loads(raw)
    check("http_ui_rule_200", status == 200 and rule.get("ok") is True, rule)
    check("http_ui_rule_exact", rule.get("rule", {}).get("ruleId") == "355.2", rule)

    status, _, raw = http(base, "/v1/evidence/R%3A355.2")
    evidence = json.loads(raw)
    check("http_ui_evidence_200", status == 200 and evidence.get("ok") is True, evidence)
    check("http_ui_evidence_authoritative_text", bool(evidence.get("evidence", {}).get("text")), evidence)

    status, _, raw = http(base, "/v1/sources")
    sources = json.loads(raw)
    check("http_ui_sources_200", status == 200 and sources.get("ok") is True, sources)
    check("http_ui_sources_histories", set((sources.get("ruleVersionHistories") or {}).keys()) == {"core", "tournament"}, sources.get("ruleVersionHistories"))

    status, _, raw = http(base, "/v1/changes?family=core")
    changes = json.loads(raw)
    check("http_ui_changes_200", status == 200 and changes.get("ok") is True, changes)
    check("http_ui_changes_family", changes.get("family") == "core", changes)

    status, _, raw = http(base, "/v1/ask", method="POST", body={"question": "Can I summon a unit to my base?"})
    ask = json.loads(raw)
    check("http_ui_ask_200", status == 200 and ask.get("ok") is True, ask)
    check("http_ui_ask_issue", len(ask.get("issues") or []) == 1, ask.get("issues"))
    check("http_ui_ask_verdict_yes", ask.get("issues", [{}])[0].get("verdict") == "yes", ask.get("issues"))
    check("http_ui_ask_proof_verified", ask.get("issues", [{}])[0].get("proof", {}).get("verified") is True, ask.get("issues"))
    check("http_ui_ask_citations", bool(ask.get("issues", [{}])[0].get("citations")), ask.get("issues"))

    status, _, raw = http(base, "/v1/ask", method="POST", body={"question": "Can I play a unit to a battlefield?"})
    conditional = json.loads(raw)
    check("http_ui_conditional_ask_200", status == 200 and conditional.get("ok") is True, conditional)
    issue = (conditional.get("issues") or [{}])[0]
    check("http_ui_conditional_status", issue.get("status") == "conditional", issue)
    check("http_ui_conditional_clarification", bool(issue.get("clarifyingQuestions")), issue)

    # UI/API errors remain sanitized JSON.
    status, headers, raw = http(base, "/v1/evidence/not-real")
    missing = json.loads(raw)
    check("http_ui_missing_evidence_404", status == 404, status)
    check("http_ui_missing_evidence_json", missing.get("error", {}).get("code") == "evidence_not_found", missing)
    check("http_ui_missing_evidence_no_path", "/mnt/" not in raw.decode("utf-8", "replace"), raw[:300])
finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)

metrics = {
    "schemaVersion": 1,
    "checkCount": checks,
    "staticRouteCount": len(STATIC_ROUTES),
    "externalRuntimeDependencies": 0,
    "sameOriginApiOnly": True,
    "dynamicHtmlInjection": False,
    "browserAdjudicationLogic": False,
    "browserEvidenceSelectionLogic": False,
    "accessibilityLandmarks": True,
    "responsive": True,
    "securityHeaders": sorted(STATIC_SECURITY_HEADERS),
}
report = {"passed": not failures, "checkCount": checks, "failureCount": len(failures), "failures": failures, "metrics": metrics}
(ROOT / "data/validation/ui_integration_metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
(ROOT / "data/validation/ui_integration_test_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))
raise SystemExit(0 if not failures else 1)
