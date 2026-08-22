#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import sqlite3
import sys
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from riftkeep_rules.api_http import start_test_server
from riftkeep_rules.product_api import ProductApiError, ProductApiService
from riftkeep_rules.retrieval import build_index
from riftkeep_rules.runtime_hardening import (
    INDEX_SCHEMA_VERSION,
    RUNTIME_ARTIFACTS,
    BoundedLruCache,
    atomic_write_json,
    open_readonly_sqlite,
    runtime_artifact_signature,
    validate_runtime_artifacts,
)

checks = 0
failures: list[dict[str, object]] = []


def check(name: str, condition: bool, detail: object = None) -> None:
    global checks
    checks += 1
    if not condition:
        failures.append({"check": name, "detail": detail})


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


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


contract = json.loads((ROOT / "data/canonical/runtime_hardening_contract.json").read_text(encoding="utf-8"))
schema = json.loads((ROOT / "contracts/runtime_hardening.schema.json").read_text(encoding="utf-8"))
check("contract_schema_v1", contract.get("schemaVersion") == 1, contract)
check("contract_schema_document_present", schema.get("title") == "RiftKeep Production Runtime Hardening Contract", schema.get("title"))
check("contract_artifacts_match_code", tuple(contract.get("runtimeArtifacts") or []) == RUNTIME_ARTIFACTS, {"contract": contract.get("runtimeArtifacts"), "code": RUNTIME_ARTIFACTS})
check("contract_index_schema_version", contract.get("indexSchemaVersion") == INDEX_SCHEMA_VERSION == 1, contract.get("indexSchemaVersion"))
check("contract_cache_bounded", (contract.get("cache") or {}).get("bounded") is True)
check("contract_cache_threadsafe", (contract.get("cache") or {}).get("threadSafe") is True)
check("contract_cache_deepcopy", (contract.get("cache") or {}).get("deepCopyResults") is True)
check("contract_no_adjudication_cache", (contract.get("cache") or {}).get("adjudicationCached") is False)
for key in ("failStartupOnCorruption", "failClosedOnRuntimeDrift", "readOnlySqliteAtRuntime", "atomicCanonicalWrites"):
    check(f"policy_{key}", (contract.get("policies") or {}).get(key) is True, contract.get("policies"))
check("policy_offline_serving", (contract.get("policies") or {}).get("networkRequiredForServing") is False, contract.get("policies"))

# Live startup integrity / migration contract.
started = time.perf_counter()
runtime = validate_runtime_artifacts(ROOT)
startup_seconds = time.perf_counter() - started
check("runtime_integrity_pass", runtime.get("passed") is True, runtime.get("errors"))
check("runtime_artifact_count", runtime.get("artifactCount") == len(RUNTIME_ARTIFACTS), runtime.get("artifactCount"))
check("runtime_sqlite_quick_check", (runtime.get("sqlite") or {}).get("quickCheck") == "ok", runtime.get("sqlite"))
check("runtime_sqlite_user_version", (runtime.get("sqlite") or {}).get("userVersion") == INDEX_SCHEMA_VERSION, runtime.get("sqlite"))
check("runtime_sqlite_doc_count", (runtime.get("sqlite") or {}).get("docCount", 0) > 3000, runtime.get("sqlite"))
check("runtime_versions_integrity", (runtime.get("ruleVersionIntegrity") or {}).get("passed") is True, runtime.get("ruleVersionIntegrity"))
check("runtime_overlay_integrity", (runtime.get("currentOverlayIntegrity") or {}).get("passed") is True, runtime.get("currentOverlayIntegrity"))
check("runtime_authority_complete", (runtime.get("authority") or {}).get("currentRulesComplete") is True, runtime.get("authority"))
check("runtime_serving_offline", runtime.get("networkRequiredForServing") is False, runtime)
check("runtime_snapshot_id_sha", len(str(runtime.get("snapshotId") or "")) == 64, runtime.get("snapshotId"))

# Explicit read-only/query-only SQLite behavior.
con = open_readonly_sqlite(ROOT / "data/index/rules.sqlite")
try:
    query_only = int(con.execute("PRAGMA query_only").fetchone()[0])
    user_version = int(con.execute("PRAGMA user_version").fetchone()[0])
    check("readonly_query_only_on", query_only == 1, query_only)
    check("readonly_schema_v1", user_version == INDEX_SCHEMA_VERSION, user_version)
    write_blocked = False
    try:
        con.execute("DELETE FROM docs_meta WHERE 1=0")
    except sqlite3.OperationalError:
        write_blocked = True
    check("readonly_write_blocked", write_blocked, write_blocked)
finally:
    con.close()

# Atomic file writes preserve the old file if replace itself fails.
with tempfile.TemporaryDirectory(prefix="rk_m17_atomic_") as td:
    target = Path(td) / "state.json"
    atomic_write_json(target, {"generation": 1})
    check("atomic_write_initial", json.loads(target.read_text()) == {"generation": 1})
    import riftkeep_rules.runtime_hardening as rh
    original_replace = rh.os.replace
    def fail_replace(src, dst):
        raise OSError("synthetic replace failure")
    rh.os.replace = fail_replace
    failed = False
    try:
        atomic_write_json(target, {"generation": 2})
    except OSError:
        failed = True
    finally:
        rh.os.replace = original_replace
    check("atomic_replace_failure_raised", failed)
    check("atomic_replace_failure_preserves_old", json.loads(target.read_text()) == {"generation": 1}, target.read_text())
    check("atomic_replace_temp_cleaned", not list(Path(td).glob(".state.json.*.tmp")), list(Path(td).iterdir()))

# Interrupted index build must leave the last good live index byte-identical.
with tempfile.TemporaryDirectory(prefix="rk_m17_index_") as td:
    db = Path(td) / "rules.sqlite"
    shutil.copy2(ROOT / "data/index/rules.sqlite", db)
    before = sha(db)
    failed = False
    try:
        build_index(db, {"not_rules": []}, {"cards": []}, {"documents": []})
    except Exception:
        failed = True
    check("index_bad_build_fails", failed)
    check("index_bad_build_preserves_live", sha(db) == before, {"before": before, "after": sha(db)})
    check("index_bad_build_temp_clean", not list(Path(td).glob(".rules.sqlite.*.tmp")), list(Path(td).iterdir()))

# Bounded cache semantics and mutation isolation.
cache: BoundedLruCache[str, dict] = BoundedLruCache(max_entries=2)
found, _ = cache.get("missing")
check("cache_initial_miss", found is False)
cache.set("a", {"v": [1]})
cache.set("b", {"v": [2]})
found, a = cache.get("a")
check("cache_hit", found is True and a == {"v": [1]}, a)
a["v"].append(99)  # type: ignore[index]
found, a2 = cache.get("a")
check("cache_deepcopy_isolation", a2 == {"v": [1]}, a2)
cache.set("c", {"v": [3]})
stats = cache.stats()
check("cache_bound_enforced", stats["entries"] == 2 and stats["maxEntries"] == 2, stats)
check("cache_eviction_recorded", stats["evictions"] == 1, stats)
found_b, _ = cache.get("b")
check("cache_lru_evicted_oldest", found_b is False, cache.stats())

# Product service runtime guard + deterministic bounded search cache.
svc = ProductApiService(ROOT)
status = svc.status()
check("service_runtime_startup_validated", status.get("runtime", {}).get("startupValidated") is True, status.get("runtime"))
check("service_runtime_snapshot_current", status.get("runtime", {}).get("snapshotCurrent") is True, status.get("runtime"))
check("service_runtime_not_degraded", status.get("runtime", {}).get("degraded") is False, status.get("runtime"))
check("service_no_adjudication_cache", status.get("runtime", {}).get("adjudicationCached") is False, status.get("runtime"))
first = svc.search("Ganking", kinds=["rule"], limit=5)
first["results"].append({"tampered": True})
second = svc.search("Ganking", kinds=["rule"], limit=5)
check("service_search_cache_result_immutable", not any(x.get("tampered") for x in second.get("results", [])), second.get("results"))
cache_stats = svc.status().get("runtime", {}).get("searchCache", {})
check("service_search_cache_hit", cache_stats.get("hits", 0) >= 1, cache_stats)
check("service_search_cache_bounded_256", cache_stats.get("maxEntries") == 256, cache_stats)

# Concurrent deterministic read behavior.  Search concurrency also exercises one
# read-only SQLite connection per request; asks exercise shared immutable engine data.
def do_search(i: int):
    return svc.search("Ganking", kinds=["rule"], limit=5)["results"]
with ThreadPoolExecutor(max_workers=12) as ex:
    rows = list(ex.map(do_search, range(36)))
check("concurrent_search_all_equal", all(x == rows[0] for x in rows), len(rows))

def do_ask(i: int):
    r = svc.ask("Can I summon a unit to my base?")
    return r["issues"][0]["verdict"], r["issues"][0]["proof"]["verified"], r["citations"]
with ThreadPoolExecutor(max_workers=6) as ex:
    asks = list(ex.map(do_ask, range(12)))
check("concurrent_ask_all_equal", all(x == asks[0] for x in asks), asks)
check("concurrent_ask_verified", asks[0][0] == "yes" and asks[0][1] is True, asks[0])

# Normal serving must remain fully offline.  Any attempted socket connection fails.
original_connect = socket.socket.connect
def blocked_connect(self, address):
    raise AssertionError(f"unexpected network access: {address}")
socket.socket.connect = blocked_connect
try:
    offline_search = svc.search("Ganking", kinds=["rule"], limit=3)
    offline_ask = svc.ask("Can I summon a unit to my base?")
finally:
    socket.socket.connect = original_connect
check("offline_search_works", offline_search.get("returned", 0) > 0, offline_search)
check("offline_ask_works", offline_ask.get("issues", [{}])[0].get("verdict") == "yes", offline_ask.get("issues"))

# HTTP request IDs/counters and real threaded serving.
server, thread = start_test_server(ROOT, service=svc)
host, port = server.server_address
base = f"http://{host}:{port}"
try:
    def req(i: int):
        status_code, headers, raw = http(base, "/v1/search?q=Ganking&kind=rule&limit=3&offset=0")
        return status_code, headers.get("X-RiftKeep-Request-Id"), json.loads(raw)
    with ThreadPoolExecutor(max_workers=10) as ex:
        responses = list(ex.map(req, range(20)))
    ids = [x[1] for x in responses]
    check("http_concurrent_all_200", all(x[0] == 200 for x in responses), [x[0] for x in responses])
    check("http_request_ids_present", all(isinstance(x, str) and x.startswith("rk-") for x in ids), ids)
    check("http_request_ids_unique", len(set(ids)) == len(ids), ids)
    metrics = server.runtime_metrics.snapshot()
    check("http_metrics_request_count", metrics.get("requests") >= 20, metrics)
    check("http_metrics_no_content_storage", metrics.get("storesRequestContent") is False, metrics)
    check("http_metrics_active_returns_zero", metrics.get("active") == 0, metrics)
    status_code, headers, raw = http(base, "/not-a-route")
    check("http_error_request_id_present", status_code == 404 and headers.get("X-RiftKeep-Request-Id", "").startswith("rk-"), {"status": status_code, "id": headers.get("X-RiftKeep-Request-Id")})
    check("http_metrics_error_count", server.runtime_metrics.snapshot().get("errors", 0) >= 1, server.runtime_metrics.snapshot())
finally:
    server.shutdown(); server.server_close(); thread.join(timeout=5)

# Live read-only calls must not mutate serving-critical artifacts.
before_sig = runtime_artifact_signature(ROOT)
svc.search("Counter a spell", kinds=["rule", "card"], limit=5)
svc.get_rule("355.2", family="core")
svc.get_card("ogn-019-298")
svc.ask("Can I summon a unit to my base?")
after_sig = runtime_artifact_signature(ROOT)
check("normal_serving_does_not_mutate_runtime_artifacts", before_sig == after_sig)

# Disposable project corruption/drift tests.
def ignore_cache(_path: str, names: list[str]):
    return {n for n in names if n in {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"} or n.endswith((".pyc", ".pyo"))}

with tempfile.TemporaryDirectory(prefix="rk_m17_project_") as td:
    work = Path(td) / "RiftKeepRules_Engine"
    shutil.copytree(ROOT, work, ignore=ignore_cache)
    good = ProductApiService(work)
    # Runtime drift: touching a private runtime file changes only the disposable tree.
    drift_file = work / "data/canonical/effective_rule_overrides.json"
    os.utime(drift_file, None)
    degraded = good.status().get("runtime", {})
    check("runtime_drift_status_degraded", degraded.get("snapshotCurrent") is False and degraded.get("degraded") is True, degraded)
    drift_blocked = False
    try:
        good.search("Ganking", kinds=["rule"], limit=3)
    except ProductApiError as exc:
        drift_blocked = exc.status == 503 and exc.code == "runtime_snapshot_changed"
    check("runtime_drift_search_fail_closed", drift_blocked)
    ask_blocked = False
    try:
        good.ask("Can I summon a unit to my base?")
    except ProductApiError as exc:
        ask_blocked = exc.status == 503 and exc.code == "runtime_snapshot_changed"
    check("runtime_drift_ask_fail_closed", ask_blocked)

    # Fresh startup with truncated JSON must fail before serving.
    original = drift_file.read_bytes()
    drift_file.write_text('{"schemaVersion":', encoding="utf-8")
    corrupt_json_blocked = False
    try:
        ProductApiService(work)
    except RuntimeError:
        corrupt_json_blocked = True
    check("startup_truncated_json_blocked", corrupt_json_blocked)
    drift_file.write_bytes(original)

    # Unknown SQLite schema version is a migration error.
    db = work / "data/index/rules.sqlite"
    con = sqlite3.connect(db)
    con.execute("PRAGMA user_version=999")
    con.commit(); con.close()
    wrong_schema_blocked = False
    try:
        ProductApiService(work)
    except RuntimeError:
        wrong_schema_blocked = True
    check("startup_unknown_index_schema_blocked", wrong_schema_blocked)
    con = sqlite3.connect(db); con.execute(f"PRAGMA user_version={INDEX_SCHEMA_VERSION}"); con.commit(); con.close()

    # Corrupt SQLite bytes must fail quick/open checks.
    good_db = db.read_bytes()
    db.write_bytes(b"not-a-sqlite-database")
    corrupt_db_blocked = False
    try:
        ProductApiService(work)
    except RuntimeError:
        corrupt_db_blocked = True
    check("startup_corrupt_sqlite_blocked", corrupt_db_blocked)
    db.write_bytes(good_db)

    restored = validate_runtime_artifacts(work)
    check("disposable_runtime_recovers_after_restore", restored.get("passed") is True, restored.get("errors"))

# Structural guarantees: key writers/runtime code must use hardening primitives.
build_src = (ROOT / "src/riftkeep_rules/build.py").read_text(encoding="utf-8")
retrieval_src = (ROOT / "src/riftkeep_rules/retrieval.py").read_text(encoding="utf-8")
update_src = (ROOT / "src/riftkeep_rules/update_automation.py").read_text(encoding="utf-8")
official_src = (ROOT / "src/riftkeep_rules/official_sources.py").read_text(encoding="utf-8")
product_src = (ROOT / "src/riftkeep_rules/product_api.py").read_text(encoding="utf-8")
check("build_uses_atomic_json", "atomic_write_json" in build_src, None)
check("index_uses_atomic_replace", "os.replace(tmp_path, db_path)" in retrieval_src and "PRAGMA quick_check" in retrieval_src, None)
check("runtime_search_uses_readonly_connection", "open_readonly_sqlite(db_path)" in retrieval_src, None)
check("update_records_use_atomic_json", "atomic_write_json" in update_src and "atomic_write_text" in update_src, None)
check("official_snapshot_pointers_atomic", "_atomic_json(snap_dir / \"latest.json\"" in official_src, None)
check("product_has_runtime_guard", "RuntimeArtifactGuard" in product_src and "runtime_snapshot_changed" in product_src, None)
check("product_does_not_cache_ask", 'cache_key = ("ask"' not in product_src, None)

metrics = {
    "schemaVersion": 1,
    "checkCount": checks,
    "runtimeArtifactCount": len(RUNTIME_ARTIFACTS),
    "indexSchemaVersion": INDEX_SCHEMA_VERSION,
    "startupValidationSeconds": round(startup_seconds, 4),
    "searchCache": svc.status().get("runtime", {}).get("searchCache", {}),
    "httpMetrics": server.runtime_metrics.snapshot(),
    "networkRequiredForServing": False,
    "adjudicationCached": False,
    "atomicIndexReplacement": True,
    "runtimeDriftFailClosed": True,
    "startupCorruptionFailClosed": True,
}
report = {"passed": not failures, "checkCount": checks, "failureCount": len(failures), "failures": failures, "metrics": metrics}
out = ROOT / "data/validation/production_hardening_test_report.json"
out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
(ROOT / "data/validation/production_hardening_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if not failures else 1)
