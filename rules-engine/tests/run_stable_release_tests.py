#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import socket
import subprocess
import sys
import tomllib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import riftkeep_rules
from riftkeep_rules.api_http import start_test_server
from riftkeep_rules.product_api import ProductApiService
from riftkeep_rules.release_gate import TEST_SCRIPTS
from riftkeep_rules.release_identity import (
    CRITICAL_ARTIFACTS,
    PRODUCT_API_VERSION,
    PRODUCT_NAME,
    PRODUCT_VERSION,
    RELEASE_LINE,
    validate_stable_release_manifest,
)

checks = 0
failures: list[dict[str, object]] = []


def check(name: str, condition: bool, detail: object = None) -> None:
    global checks
    checks += 1
    if not condition:
        failures.append({"check": name, "detail": detail})


def load(rel: str):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


# Product/package identity.
pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
check("pyproject package name", pyproject["project"]["name"] == "riftkeep-rules-engine", pyproject["project"])
check("pyproject stable version matches PRODUCT_VERSION", pyproject["project"]["version"] == PRODUCT_VERSION, pyproject["project"]["version"])
check("package __version__ 1.0.0", riftkeep_rules.__version__ == PRODUCT_VERSION, riftkeep_rules.__version__)
check("stable product name", PRODUCT_NAME == "RiftKeep Rules Engine", PRODUCT_NAME)
check("stable release line", RELEASE_LINE == "stable", RELEASE_LINE)
check("Product API remains v1", PRODUCT_API_VERSION == "v1", PRODUCT_API_VERSION)

contract = load("data/canonical/stable_release_contract.json")
check("stable contract schema v1", contract.get("schemaVersion") == 1, contract)
check("stable contract product version", (contract.get("product") or {}).get("version") == PRODUCT_VERSION, contract.get("product"))
check("stable contract release line", (contract.get("product") or {}).get("releaseLine") == RELEASE_LINE, contract.get("product"))
compat = contract.get("compatibility") or {}
check("compatibility API v1", compat.get("productApi") == "v1", compat)
check("compatibility SQLite schema v1", compat.get("sqliteIndexSchema") == 1, compat)
check("compatibility update schema v1", compat.get("updateTransactionSchema") == 1, compat)
check("compatibility runtime schema v1", compat.get("runtimeHardeningSchema") == 1, compat)
check("compatibility M18 audit schema v1", compat.get("releaseCandidateAuditSchema") == 1, compat)
check("compatibility UI schema v1", compat.get("uiContractSchema") == 1, compat)
check("compatibility UI version", compat.get("uiVersion") == "m15-v1", compat)
check("compatibility Python >=3.11", compat.get("pythonMinimum") == "3.11", compat)
policies = contract.get("policies") or {}
for key, expected in {
    "currentAuthorityRequiredForAsk": True,
    "normalServingRequiresNetwork": False,
    "llmOptionalForCorrectness": True,
    "browserContainsAdjudicationLogic": False,
    "adjudicationCached": False,
    "runtimeDriftFailsClosed": True,
    "sourceUpdatesRequireTransactionalGate": True,
    "latestTwoMilestoneRetention": True,
}.items():
    check(f"stable policy {key}", policies.get(key) is expected, policies)
semver = contract.get("semanticVersioning") or {}
check("semver major policy documented", bool(semver.get("major")), semver)
check("semver minor policy documented", bool(semver.get("minor")), semver)
check("semver patch policy documented", bool(semver.get("patch")), semver)
check("authority update versioning policy documented", bool(semver.get("authorityUpdates")), semver)

limitations = {x.get("code"): x for x in contract.get("knownLimitations") or []}
check("exact three Stable 1.0 known limitations", set(limitations) == {"gold_c_report_only_remaining", "historical_patch_note_bodies_incomplete", "historical_faq_bodies_incomplete"}, limitations)
check("18 Gold-C report-only declared", limitations.get("gold_c_report_only_remaining", {}).get("count") == 18, limitations)
check("4 historical patch bodies declared", limitations.get("historical_patch_note_bodies_incomplete", {}).get("count") == 4, limitations)
check("3 historical FAQ bodies declared", limitations.get("historical_faq_bodies_incomplete", {}).get("count") == 3, limitations)
check("known limitations do not affect current authority", all(x.get("currentAuthorityImpact") is False for x in limitations.values()), limitations)

# Stable manifest and critical artifact hash inventory.
manifest_result = validate_stable_release_manifest(ROOT)
check("stable release manifest validates", manifest_result.get("passed") is True, manifest_result)
manifest = load("data/canonical/stable_release_manifest.json")
check("stable manifest schema v1", manifest.get("schemaVersion") == 1, manifest)
check("stable manifest product identity", manifest.get("product") == contract.get("product"), manifest.get("product"))
check("stable manifest compatibility identity", manifest.get("compatibility") == compat, manifest.get("compatibility"))
check("stable manifest has 19 certified suites", manifest.get("certifiedReleaseSuiteCount") == 19, manifest.get("certifiedReleaseSuiteCount"))
hashes = manifest.get("artifactHashes") or {}
check("stable manifest critical path set exact", set(hashes) == set(CRITICAL_ARTIFACTS), {"expected": len(CRITICAL_ARTIFACTS), "actual": len(hashes)})
check("stable manifest critical artifact count", len(hashes) >= 30, len(hashes))
for rel in CRITICAL_ARTIFACTS:
    row = hashes.get(rel) or {}
    path = ROOT / rel
    check(f"stable artifact exists: {rel}", path.is_file(), rel)
    check(f"stable artifact hash shape: {rel}", isinstance(row.get("sha256"), str) and len(row.get("sha256")) == 64 and row.get("bytes") == path.stat().st_size, row)

# Authority/corpus identity in the manifest.
authority = manifest.get("authority") or {}
check("stable Core source ID", authority.get("coreSourceId") == "core-rules-2026-07-16", authority)
check("stable Tournament source ID", authority.get("tournamentSourceId") == "tournament-rules-2026-07-16", authority)
check("stable FAQ source ID", authority.get("currentFaqSourceId") == "vendetta-faq-2026-08-14", authority)
check("stable source SHA fields present", all(isinstance(authority.get(k), str) and len(authority[k]) == 64 for k in ("coreSourceSha256", "tournamentSourceSha256", "currentFaqSha256", "cardSourceSha256")), authority)
corpus = manifest.get("corpus") or {}
check("stable Core count", corpus.get("coreRules") == 2381, corpus)
check("stable Tournament count", corpus.get("tournamentRules") == 935, corpus)
check("stable card count", corpus.get("cards") == 1304, corpus)
check("stable FAQ count", corpus.get("currentFaqSections") == 35, corpus)
check("stable errata event count", corpus.get("officialErrataEvents") == 63, corpus)
check("stable errata printing count", corpus.get("errataAffectedPrintings") == 91, corpus)

# M18 conformance inheritance and prior suites.
m18 = load("data/validation/m18_conformance_report.json")
check("M18 release candidate inherited", m18.get("releaseCandidateReady") is True and m18.get("criticalHighFindings") == 0, m18)
rc = load("data/validation/release_candidate_audit.json")
check("M18 independent audit inherited", rc.get("passed") is True and rc.get("blockingFindingCount") == 0, rc)
check("M18 expected medium limitation remains one", (rc.get("findingCounts") or {}).get("Medium") == 1, rc.get("findingCounts"))
prior_reports = {
    "core_test_report.json": 164,
    "definition_lookup_test_report.json": 120,
    "regression_report.json": 99,
    "language_test_report.json": 42,
    "scenario_language_test_report.json": 43,
    "scenario_model_test_report.json": 58,
    "compiler_test_report.json": 42,
    "proof_engine_test_report.json": 72,
    "llm_interpretation_test_report.json": 84,
    "llm_explanation_test_report.json": 80,
    "gold_corpus_report.json": 34,
    "card_interaction_test_report.json": 74,
    "product_api_test_report.json": 132,
    "ui_integration_test_report.json": 148,
    "update_test_report.json": 29,
    "update_automation_test_report.json": 70,
    "production_hardening_test_report.json": 74,
    "release_candidate_audit_test_report.json": 48,
}
for name, expected in prior_reports.items():
    d = load("data/validation/" + name)
    actual = d.get("checkCount", d.get("caseCount"))
    check(f"inherited certified report {name}", d.get("passed") is True and actual == expected, {"actual": actual, "expected": expected})

# Release-gate integration.
check("Stable acceptance is 19th certified suite", len(TEST_SCRIPTS) == 19 and TEST_SCRIPTS[-1] == "tests/run_stable_release_tests.py", TEST_SCRIPTS)
check("Definition suite remains certified", "tests/run_definition_lookup_tests.py" in TEST_SCRIPTS, TEST_SCRIPTS)
check("M18 audit remains certified", "tests/run_release_candidate_audit_tests.py" in TEST_SCRIPTS, TEST_SCRIPTS)

# Product API + Definition Lookup stable identity.
service = ProductApiService(ROOT)
status = service.status()
release = status.get("release") or {}
check("Product API status version 1.0.0", release.get("productVersion") == PRODUCT_VERSION, release)
check("Product API status release line stable", release.get("releaseLine") == RELEASE_LINE, release)
check("Product API status still v1", status.get("apiVersion") == "v1", status)
check("Product API current authority complete", (status.get("authority") or {}).get("currentRulesComplete") is True, status.get("authority"))
definition = service.ask("What does Deflect do?")
issue = (definition.get("issues") or [{}])[0]
check("Stable Definition Lookup backend verdict", issue.get("verdict") == "definition", issue)
check("Stable Definition Lookup proof verified", (issue.get("proof") or {}).get("verified") is True, issue.get("proof"))
check("Stable Definition Lookup has Core citations", bool(issue.get("citations")) and all(x.startswith("R:") for x in issue.get("citations") or []), issue.get("citations"))

# Stable launcher/self-check with network blocked in-process.
spec = importlib.util.spec_from_file_location("riftkeep_launcher", ROOT / "riftkeep.py")
launcher = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(launcher)
original_connect = socket.socket.connect
def blocked_connect(self, address):
    raise AssertionError(f"unexpected network access during stable self-check: {address}")
socket.socket.connect = blocked_connect
try:
    self_check = launcher.run_self_check(ROOT)
finally:
    socket.socket.connect = original_connect
check("stable self-check passes", self_check.get("ok") is True, self_check)
check("stable self-check offline", self_check.get("networkRequired") is False, self_check)
check("stable self-check manifest passes", (self_check.get("stableManifest") or {}).get("passed") is True, self_check.get("stableManifest"))
check("stable self-check runtime passes", (self_check.get("runtime") or {}).get("passed") is True, self_check.get("runtime"))
cli = subprocess.run([sys.executable, str(ROOT / "riftkeep.py"), "status", "--compact"], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=90)
check("stable launcher status exit zero", cli.returncode == 0, cli.stdout[-2000:])
try:
    cli_status = json.loads(cli.stdout)
except Exception:
    cli_status = {}
check("stable launcher status product version", (cli_status.get("release") or {}).get("productVersion") == PRODUCT_VERSION, cli_status)

# Real HTTP / UI identity.
server, thread = start_test_server(ROOT, service=service)
host, port = server.server_address
try:
    with urllib.request.urlopen(f"http://{host}:{port}/v1/status", timeout=30) as response:
        http_status = json.loads(response.read())
        req_id = response.headers.get("X-RiftKeep-Request-Id")
    check("stable HTTP status version", (http_status.get("release") or {}).get("productVersion") == PRODUCT_VERSION, http_status.get("release"))
    check("stable HTTP status release line", (http_status.get("release") or {}).get("releaseLine") == RELEASE_LINE, http_status.get("release"))
    check("stable HTTP request ID", isinstance(req_id, str) and req_id.startswith("rk-"), req_id)
finally:
    server.shutdown(); server.server_close(); thread.join(timeout=5)
app = (ROOT / "web/app.js").read_text(encoding="utf-8")
check("UI renders stable productVersion from backend", "release.productVersion" in app and "RiftKeep ${release.productVersion}" in app, None)
check("UI remains backend-only adjudication", "browserAdjudicationLogic" not in app and "/v1/ask" in app, None)

# Documentation / known-limitations parity.
notes = (ROOT / "RELEASE_NOTES_1.0.md").read_text(encoding="utf-8")
known = (ROOT / "KNOWN_LIMITATIONS_1.0.md").read_text(encoding="utf-8")
check("release notes identify 1.0", "RiftKeep Rules Engine 1.0" in notes and "Product API" in notes, None)
check("release notes document stable launcher", "python riftkeep.py self-check" in notes and "python riftkeep.py serve" in notes, None)
check("known limitations document 18 Gold-C", "Eighteen" in known and "report-only" in known, None)
check("known limitations document patch bodies", "Four" in known and "patch-note" in known, None)
check("known limitations document historical FAQs", "Three" in known and "historical FAQ" in known, None)
check("known limitations explain optional LLM", "optional" in known.casefold() and "LLM" in known, None)

# Clean-install rehearsal becomes mandatory once T201 writes it.
clean_path = ROOT / "data/validation/stable_clean_install_audit.json"
check("Stable 1.0 clean-install audit exists", clean_path.is_file(), str(clean_path))
if clean_path.is_file():
    clean = json.loads(clean_path.read_text(encoding="utf-8"))
    check("Stable 1.0 clean-install audit passes", clean.get("passed") is True, clean)
    check("Stable clean install offline self-check", clean.get("selfCheckPassed") is True and clean.get("networkRequired") is False, clean)
    check("Stable clean install API/UI/definition", clean.get("apiPassed") is True and clean.get("uiPassed") is True and clean.get("definitionPassed") is True, clean)
else:
    check("Stable 1.0 clean-install audit passes", False, None)
    check("Stable clean install offline self-check", False, None)
    check("Stable clean install API/UI/definition", False, None)

metrics = {
    "schemaVersion": 1,
    "checkCount": checks,
    "productVersion": PRODUCT_VERSION,
    "productApiVersion": PRODUCT_API_VERSION,
    "criticalArtifactCount": len(CRITICAL_ARTIFACTS),
    "certifiedReleaseSuiteCount": len(TEST_SCRIPTS),
    "manifestPassed": manifest_result.get("passed"),
    "currentAuthorityComplete": (status.get("authority") or {}).get("currentRulesComplete"),
    "networkRequiredForServing": False,
    "m18CriticalHighBlockers": m18.get("criticalHighFindings"),
}
report = {"passed": not failures, "checkCount": checks, "failureCount": len(failures), "failures": failures, "metrics": metrics}
(ROOT / "data/validation/stable_release_test_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["passed"] else 1)
