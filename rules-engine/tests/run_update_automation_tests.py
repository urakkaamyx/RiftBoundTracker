#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import riftkeep_rules.update_automation as ua
from riftkeep_rules.release_gate import FINAL_SCRIPTS, TEST_SCRIPTS

checks = 0
failures: list[dict[str, str]] = []


def check(name: str, ok: bool, detail: object = "") -> None:
    global checks
    checks += 1
    if not ok:
        failures.append({"check": name, "detail": str(detail)[:4000]})


def expect_raises(name: str, fn, contains: str | None = None) -> None:
    try:
        fn()
    except Exception as exc:
        text = f"{type(exc).__name__}: {exc}"
        check(name, contains is None or contains.casefold() in text.casefold(), text)
    else:
        check(name, False, "did not raise")


def copy_project(dst: Path) -> None:
    def ignore(path, names):
        out = {n for n in names if n in {"__pycache__", ".pytest_cache", ".git"} or n.endswith((".pyc", ".pyo"))}
        if Path(path).name == "data" and "update_transactions" in names:
            out.add("update_transactions")
        return out
    shutil.copytree(ROOT, dst, ignore=ignore)


def pass_gate(_: Path) -> dict:
    return {"passed": True, "commandCount": 17, "completedCommandCount": 17, "commands": []}


def fail_gate(_: Path) -> dict:
    return {"passed": False, "commandCount": 17, "completedCommandCount": 4, "commands": [{"passed": False, "argv": ["synthetic-failure"], "output": "forced failure"}]}


with tempfile.TemporaryDirectory(prefix="riftkeep-m16-tests-") as td:
    tr = Path(td) / "RiftKeepRules_Engine"
    copy_project(tr)
    faq = tr / "data/source/official_text/vendetta_faq_2026-08-14.txt"
    current_faq_sha = ua.sha256_file(faq)

    # T157 — contract and baseline fingerprint behavior.
    schema = json.loads((tr / "contracts/update_automation.schema.json").read_text(encoding="utf-8"))
    check("update transaction schema version", schema.get("properties", {}).get("schemaVersion", {}).get("const") == 1, schema)
    kinds = set(schema.get("properties", {}).get("candidates", {}).get("items", {}).get("properties", {}).get("kind", {}).get("enum", []))
    check("schema covers all supported candidate kinds", kinds == ua.SUPPORTED_KINDS, kinds)
    fp1 = ua.project_fingerprint(tr)
    # Validation/report churn must not stale a transaction.
    v = tr / "data/validation/synthetic-m16.json"; v.write_text("{}", encoding="utf-8")
    fp2 = ua.project_fingerprint(tr)
    check("validation report churn excluded from baseline fingerprint", fp1 == fp2, (fp1, fp2))
    v.unlink()
    # Code/source changes must stale it.
    probe = tr / "src/riftkeep_rules/m16_fingerprint_probe.py"; probe.write_text("X=1\n", encoding="utf-8")
    fp3 = ua.project_fingerprint(tr)
    check("source/code change alters baseline fingerprint", fp3["sha256"] != fp1["sha256"], (fp1, fp3))
    probe.unlink()
    check("fingerprint returns nonzero file count", fp1["fileCount"] > 100, fp1)

    nochange = ua.create_transaction(tr, {"candidates": [{"kind": "official_snapshot", "sourceId": "vendetta-faq-2026-08-14", "file": str(faq)}]}, "m16-nochange")
    check("transaction copies immutable input", (tr / nochange["candidates"][0]["inputFile"]).exists(), nochange)
    check("transaction stores input hash", nochange["candidates"][0]["inputSha256"] == current_faq_sha, nochange)
    check("transaction input path is project-relative", not Path(nochange["candidates"][0]["inputFile"]).is_absolute(), nochange)
    check("transaction baseline matches current project", ua.transaction_status(tr, "m16-nochange")["baselineCurrent"] is True, ua.transaction_status(tr, "m16-nochange"))
    expect_raises("duplicate transaction ID refused", lambda: ua.create_transaction(tr, {"candidates": [{"kind": "official_snapshot", "sourceId": "vendetta-faq-2026-08-14", "file": str(faq)}]}, "m16-nochange"), "already exists")
    expect_raises("invalid source ID rejected", lambda: ua.create_transaction(tr, {"candidates": [{"kind": "official_snapshot", "sourceId": "../bad", "file": str(faq)}]}, "m16-bad-source"), "invalid source")
    expect_raises("unsupported candidate kind rejected", lambda: ua.create_transaction(tr, {"candidates": [{"kind": "mystery", "sourceId": "x", "file": str(faq)}]}, "m16-bad-kind"), "unsupported")
    expect_raises("unregistered official source refused", lambda: ua.create_transaction(tr, {"candidates": [{"kind": "official_snapshot", "sourceId": "future-unknown-faq", "file": str(faq)}]}, "m16-unknown"), "not registered")

    # No-op source polling/stage never advances live source and never publishes metadata churn.
    ptr = tr / "data/source/snapshots/vendetta-faq-2026-08-14/latest.json"
    ptr_before = ptr.read_bytes()
    plan0 = ua.stage_transaction(tr, "m16-nochange")
    check("identical current FAQ stages as no changes", plan0["status"] == "no_changes" and plan0["materialChangeCount"] == 0, plan0)
    check("no-change stage requires no review", plan0["reviewRequired"] is False, plan0)
    check("staging is non-destructive to live latest pointer", ptr.read_bytes() == ptr_before, plan0)
    reh0 = ua.rehearse_transaction(tr, "m16-nochange", gate_runner=pass_gate)
    check("no-change rehearsal skips release gate", reh0.get("noChanges") is True and reh0.get("releaseGate", {}).get("skipped") is True, reh0)
    check("no-change rehearsal creates no publish bundle", not reh0.get("publishReady") and reh0.get("publishBundle") is None, reh0)
    expect_raises("no-change transaction cannot publish", lambda: ua.publish_transaction(tr, "m16-nochange", gate_runner=pass_gate), "rehearsal did not pass")

    # Input immutability.
    drift = ua.create_transaction(tr, {"candidates": [{"kind": "official_snapshot", "sourceId": "vendetta-faq-2026-08-14", "file": str(faq)}]}, "m16-input-drift")
    drift_input = tr / drift["candidates"][0]["inputFile"]
    drift_input.write_bytes(drift_input.read_bytes() + b"\nchanged")
    expect_raises("transaction input drift blocks stage", lambda: ua.stage_transaction(tr, "m16-input-drift"), "input drift")

    # Invalid official snapshot is quarantined/blocked in isolation.
    bad = Path(td) / "bad-faq.txt"; bad.write_text("not an FAQ", encoding="utf-8")
    ua.create_transaction(tr, {"candidates": [{"kind": "official_snapshot", "sourceId": "vendetta-faq-2026-08-14", "file": str(bad)}]}, "m16-invalid-faq")
    bad_plan = ua.stage_transaction(tr, "m16-invalid-faq")
    check("invalid current FAQ blocks transaction", bad_plan["status"] == "blocked" and bool(bad_plan["blockers"]), bad_plan)
    expect_raises("blocked transaction cannot be approved", lambda: ua.approve_transaction(tr, "m16-invalid-faq", "Judge"), "blocked")
    expect_raises("blocked transaction cannot rehearse", lambda: ua.rehearse_transaction(tr, "m16-invalid-faq", gate_runner=pass_gate), "blocked")

    # T158 — safe registered-source polling with injectable fetcher.
    raw = faq.read_bytes()
    poll = ua.poll_registered_source(tr, "vendetta-faq-2026-08-14", fetcher=lambda url, timeout: (raw, "text/plain"), transaction_id="m16-poll")
    check("poll creates immutable transaction", poll["transactionId"] == "m16-poll" and poll["candidateCount"] == 1, poll)
    check("poll preserves fetched bytes hash", poll["candidates"][0]["inputSha256"] == hashlib.sha256(raw).hexdigest(), poll)
    check("poll candidate carries official snapshot kind", poll["candidates"][0]["kind"] == "official_snapshot", poll)

    # T159/T160/T161 — changed authority source must review, then can rehearse only after approval.
    changed1 = Path(td) / "vendetta-changed-1.txt"
    changed1.write_text(faq.read_text(encoding="utf-8") + "\nM16 review fixture one.", encoding="utf-8")
    ua.create_transaction(tr, {"note": "changed FAQ test", "candidates": [{"kind": "official_snapshot", "sourceId": "vendetta-faq-2026-08-14", "file": str(changed1)}]}, "m16-changed")
    plan1 = ua.stage_transaction(tr, "m16-changed")
    check("changed FAQ requires review", plan1["status"] == "review_required" and plan1["reviewRequired"], plan1)
    check("changed FAQ reports material change", plan1["materialChangeCount"] == 1 and plan1["candidates"][0].get("changed") is True, plan1)
    check("changed FAQ validation remains required", plan1["candidates"][0].get("validationPassed") is True, plan1)
    expect_raises("rehearsal refuses missing approval", lambda: ua.rehearse_transaction(tr, "m16-changed", gate_runner=pass_gate), "review approval")
    approval = ua.approve_transaction(tr, "m16-changed", "M16 Test Judge", "reviewed source diff")
    check("approval records reviewer and plan hash", approval["approved"] and approval["reviewer"] == "M16 Test Judge" and len(approval["planSha256"]) == 64, approval)
    reh1 = ua.rehearse_transaction(tr, "m16-changed", gate_runner=pass_gate)
    check("approved changed FAQ rehearsal passes", reh1["passed"] and reh1["publishReady"], reh1)
    check("rehearsal creates hash-bound publish bundle", reh1.get("publishBundle") == "publish_bundle.zip" and len(reh1.get("publishBundleSha256") or "") == 64, reh1)
    check("rehearsal records exact file diff", reh1["fileChangeCount"] > 0 and any("snapshots/vendetta-faq" in r["path"] for r in reh1["fileChanges"]), reh1["fileChanges"][:20])
    check("rehearsal did not change live source pointer", ptr.read_bytes() == ptr_before, reh1)

    # T162/T163 — successful publish uses exact rehearsed bytes and records post-publish manifest.
    pub1 = ua.publish_transaction(tr, "m16-changed", gate_runner=pass_gate)
    check("successful publish status", pub1["status"] == "published" and not pub1["rolledBack"], pub1)
    latest1 = json.loads(ptr.read_text(encoding="utf-8"))
    check("publish advances live snapshot to reviewed candidate", latest1["sha256"] == hashlib.sha256(changed1.read_bytes()).hexdigest(), latest1)
    check("publish records post-publish fingerprint", len(pub1.get("postPublishFingerprint", {}).get("sha256", "")) == 64, pub1)
    check("publish retains rollback hash", len(pub1.get("rollbackBundleSha256") or "") == 64, pub1)
    check("transaction status reports published", ua.transaction_status(tr, "m16-changed")["status"]["status"] == "published", ua.transaction_status(tr, "m16-changed")["status"])

    # Rollback test starts from the now-published fixture and must return exactly to it.
    ptr_published = ptr.read_bytes()
    changed2 = Path(td) / "vendetta-changed-2.txt"
    changed2.write_text(changed1.read_text(encoding="utf-8") + "\nM16 review fixture two.", encoding="utf-8")
    ua.create_transaction(tr, {"candidates": [{"kind": "official_snapshot", "sourceId": "vendetta-faq-2026-08-14", "file": str(changed2)}]}, "m16-rollback")
    plan2 = ua.stage_transaction(tr, "m16-rollback")
    ua.approve_transaction(tr, "m16-rollback", "M16 Test Judge")
    reh2 = ua.rehearse_transaction(tr, "m16-rollback", gate_runner=pass_gate)
    check("rollback fixture rehearse ready", plan2["reviewRequired"] and reh2["publishReady"], (plan2, reh2))
    expect_raises("failed post-publish gate raises after rollback", lambda: ua.publish_transaction(tr, "m16-rollback", gate_runner=fail_gate), "post-publish")
    check("failed publish restores previous latest pointer byte-for-byte", ptr.read_bytes() == ptr_published, json.loads(ptr.read_text()))
    rolled = json.loads((tr / "data/update_transactions/m16-rollback/publish.json").read_text())
    check("failed publish records rollback status", rolled["status"] == "rolled_back" and rolled["rolledBack"] is True, rolled)

    # Stale baseline refuses exact bundle before any write.
    ua.create_transaction(tr, {"candidates": [{"kind": "official_snapshot", "sourceId": "vendetta-faq-2026-08-14", "file": str(changed2)}]}, "m16-stale")
    ua.stage_transaction(tr, "m16-stale"); ua.approve_transaction(tr, "m16-stale", "M16 Test Judge"); ua.rehearse_transaction(tr, "m16-stale", gate_runner=pass_gate)
    readme = tr / "README.md"; readme.write_text(readme.read_text(encoding="utf-8") + "\n<!-- stale baseline fixture -->\n", encoding="utf-8")
    expect_raises("stale project baseline blocks publish", lambda: ua.publish_transaction(tr, "m16-stale", gate_runner=pass_gate), "baseline is stale")
    check("stale publish leaves live source untouched", ptr.read_bytes() == ptr_published, json.loads(ptr.read_text()))

    # Restore README content for subsequent current-baseline transactions.
    text = readme.read_text(encoding="utf-8").replace("\n<!-- stale baseline fixture -->\n", "")
    readme.write_text(text, encoding="utf-8")

    # Rule-document routing is exercised with orchestration fakes; lower-level real PDF
    # stage/promote semantics remain covered by run_update_tests.py.
    core_pdf = tr / "data/source/core_rules.pdf"
    original_stage, original_promote = ua.stage_rules_update, ua.promote_staged_update
    try:
        def fake_stage(clone, family, pdf, sid, effective):
            return {"validation": {"passed": True}, "diff": {"safeToAutoPromote": True, "changeCounts": {"UNCHANGED": 2381 if family == "core" else 935}}, "status": "ready_for_promotion"}
        def fake_promote(clone, family, sid, approve_review=False):
            marker = clone / f"data/source/{family}_automation_marker.txt"
            marker.write_text(f"{sid}|{approve_review}", encoding="utf-8")
            return {"status": "promoted", "family": family, "sourceId": sid}
        ua.stage_rules_update = fake_stage; ua.promote_staged_update = fake_promote
        ua.create_transaction(tr, {"candidates": [{"kind": "core_rules_pdf", "sourceId": "core-rules-m16-synthetic", "file": str(core_pdf), "effectiveFrom": "2099-01-01"}]}, "m16-core-route")
        core_plan = ua.stage_transaction(tr, "m16-core-route")
        check("Core PDF automation route always requires human review", core_plan["reviewRequired"] and core_plan["candidates"][0]["technicalSafeToPromote"], core_plan)
        ua.approve_transaction(tr, "m16-core-route", "M16 Test Judge")
        core_reh = ua.rehearse_transaction(tr, "m16-core-route", gate_runner=pass_gate)
        check("Core PDF rehearsal uses promotion route", core_reh["publishReady"] and any(r["path"].endswith("core_automation_marker.txt") for r in core_reh["fileChanges"]), core_reh["fileChanges"])
        core_pub = ua.publish_transaction(tr, "m16-core-route", gate_runner=pass_gate)
        check("Core PDF synthetic route publishes exact rehearsed marker", core_pub["status"] == "published" and (tr / "data/source/core_automation_marker.txt").read_text() == "core-rules-m16-synthetic|True", core_pub)
    finally:
        ua.stage_rules_update, ua.promote_staged_update = original_stage, original_promote

    # Reviewed companion metadata can travel through the same transaction without
    # allowing arbitrary project-file replacement. This is how a new FAQ can carry
    # reviewed authority/catalog metadata without direct live file surgery.
    catalog_live = tr / "data/source/official_ruling_catalog.json"
    catalog_candidate = Path(td) / "catalog-reviewed.json"
    catalog_doc = json.loads(catalog_live.read_text(encoding="utf-8"))
    catalog_doc["m16ReviewFixture"] = {"reviewed": True}
    catalog_candidate.write_text(json.dumps(catalog_doc, indent=2), encoding="utf-8")
    ua.create_transaction(tr, {"candidates": [{
        "kind": "reviewed_file", "sourceId": "vendetta-faq-2026-08-14",
        "file": str(catalog_candidate), "target": "data/source/official_ruling_catalog.json"
    }]}, "m16-reviewed-file")
    rf_plan = ua.stage_transaction(tr, "m16-reviewed-file")
    check("reviewed companion file requires approval", rf_plan["reviewRequired"] and rf_plan["candidates"][0]["target"] == "data/source/official_ruling_catalog.json", rf_plan)
    ua.approve_transaction(tr, "m16-reviewed-file", "M16 Test Judge")
    rf_reh = ua.rehearse_transaction(tr, "m16-reviewed-file", gate_runner=pass_gate)
    check("reviewed companion file rehearses through hash-bound bundle", rf_reh["publishReady"] and any(r["path"] == "data/source/official_ruling_catalog.json" for r in rf_reh["fileChanges"]), rf_reh["fileChanges"])
    rf_pub = ua.publish_transaction(tr, "m16-reviewed-file", gate_runner=pass_gate)
    check("reviewed companion file can publish only after review", rf_pub["status"] == "published" and json.loads(catalog_live.read_text()).get("m16ReviewFixture", {}).get("reviewed") is True, rf_pub)
    expect_raises("reviewed file cannot target arbitrary project path", lambda: ua.create_transaction(tr, {"candidates": [{"kind": "reviewed_file", "sourceId": "x", "file": str(catalog_candidate), "target": "README.md"}]}, "m16-review-path"), "not allowlisted")
    invalid_json = Path(td) / "invalid-reviewed.json"; invalid_json.write_text("{bad json", encoding="utf-8")
    expect_raises("reviewed file must be valid JSON", lambda: ua.create_transaction(tr, {"candidates": [{"kind": "reviewed_file", "sourceId": "x", "file": str(invalid_json), "target": "data/source/current_authority_overlay.json"}]}, "m16-review-json"), "valid JSON")

    # New official source IDs require explicit registration metadata; the engine never
    # invents source type/status/precedence. Historical registration is supported.
    new_hist = ua.create_transaction(tr, {"candidates": [{
        "kind": "official_snapshot", "sourceId": "m16-new-historical-faq", "file": str(changed2),
        "registration": {
            "type": "official_faq", "status": "superseded_history",
            "url": "https://playriftbound.com/en-us/news/rules-and-releases/m16-test-history/",
            "published": "2099-01-01", "authorityScope": ["historical_rules_context"]
        }
    }]}, "m16-register-history")
    check("new source registration metadata is frozen in transaction", new_hist["candidates"][0].get("registration", {}).get("type") == "official_faq", new_hist)
    hist_plan = ua.stage_transaction(tr, "m16-register-history")
    check("new official source registration always requires review", hist_plan["reviewRequired"] and hist_plan["candidates"][0].get("newSourceRegistration") is True, hist_plan)
    ua.approve_transaction(tr, "m16-register-history", "M16 Test Judge")
    hist_reh = ua.rehearse_transaction(tr, "m16-register-history", gate_runner=pass_gate)
    check("new source registration is included in rehearsed manifest diff", hist_reh["publishReady"] and any(r["path"] == "data/source/official_source_manifest.json" for r in hist_reh["fileChanges"]), hist_reh["fileChanges"])

    # Current overlays require explicit precedence and explicit supersession metadata.
    expect_raises("new current overlay without precedence is rejected", lambda: ua.create_transaction(tr, {"candidates": [{
        "kind": "official_snapshot", "sourceId": "m16-bad-current-overlay", "file": str(changed2),
        "registration": {
            "type": "official_faq", "status": "current_overlay",
            "url": "https://playriftbound.com/en-us/news/rules-and-releases/m16-bad-overlay/",
            "authorityScope": ["gameplay_rules"], "supersedesSourceId": "vendetta-faq-2026-08-14"
        }
    }]}, "m16-bad-overlay"), "precedence")
    manifest_for_reg = json.loads((tr / "data/source/official_source_manifest.json").read_text(encoding="utf-8"))
    old_overlay = next(x for x in manifest_for_reg["sources"] if x.get("id") == "vendetta-faq-2026-08-14")
    good_overlay = ua.create_transaction(tr, {"candidates": [{
        "kind": "official_snapshot", "sourceId": "m16-new-current-overlay", "file": str(changed2),
        "registration": {
            "type": "official_faq", "status": "current_overlay",
            "url": "https://playriftbound.com/en-us/news/rules-and-releases/m16-new-overlay/",
            "published": "2099-02-01", "effectiveFrom": "2099-02-01",
            "authorityScope": old_overlay.get("authorityScope") or ["gameplay_rules"],
            "precedence": old_overlay.get("precedence") or {"onlyWhereDifferent": True},
            "exhaustive": False, "supersedesSourceId": "vendetta-faq-2026-08-14"
        }
    }]}, "m16-good-overlay")
    ov_plan = ua.stage_transaction(tr, "m16-good-overlay")
    check("reviewed current-overlay registration stages without invented authority", ov_plan["status"] == "review_required" and ov_plan["candidates"][0].get("newSourceRegistration") is True, ov_plan)
    ua.approve_transaction(tr, "m16-good-overlay", "M16 Test Judge")
    ov_reh = ua.rehearse_transaction(tr, "m16-good-overlay", gate_runner=pass_gate)
    check("new current overlay rehearsal carries manifest and snapshot changes", ov_reh["publishReady"] and any(r["path"] == "data/source/official_source_manifest.json" for r in ov_reh["fileChanges"]), ov_reh["fileChanges"])

    # Sealed transaction documents cannot be edited between phases. Candidate bytes
    # are not enough: request routing, staged plans, human review, and rehearsal
    # approval state are all part of the security boundary.
    tamper_req = ua.create_transaction(tr, {"candidates": [{"kind": "official_snapshot", "sourceId": "vendetta-faq-2026-08-14", "file": str(changed2)}]}, "m16-tamper-request")
    req_path = tr / "data/update_transactions/m16-tamper-request/request.json"
    req_doc = json.loads(req_path.read_text(encoding="utf-8")); req_doc["note"] = "tampered after sealing"
    req_path.write_text(json.dumps(req_doc, indent=2), encoding="utf-8")
    expect_raises("tampered sealed request blocks staging", lambda: ua.stage_transaction(tr, "m16-tamper-request"), "hash mismatch: request.json")

    ua.create_transaction(tr, {"candidates": [{"kind": "official_snapshot", "sourceId": "vendetta-faq-2026-08-14", "file": str(changed2)}]}, "m16-tamper-plan")
    ua.stage_transaction(tr, "m16-tamper-plan")
    plan_path = tr / "data/update_transactions/m16-tamper-plan/plan.json"
    plan_doc = json.loads(plan_path.read_text(encoding="utf-8")); plan_doc["reviewRequired"] = False
    plan_path.write_text(json.dumps(plan_doc, indent=2), encoding="utf-8")
    expect_raises("tampered sealed plan blocks approval", lambda: ua.approve_transaction(tr, "m16-tamper-plan", "M16 Test Judge"), "hash mismatch: plan.json")

    ua.create_transaction(tr, {"candidates": [{"kind": "official_snapshot", "sourceId": "vendetta-faq-2026-08-14", "file": str(changed2)}]}, "m16-tamper-review")
    ua.stage_transaction(tr, "m16-tamper-review"); ua.approve_transaction(tr, "m16-tamper-review", "M16 Test Judge")
    review_path = tr / "data/update_transactions/m16-tamper-review/review.json"
    review_doc = json.loads(review_path.read_text(encoding="utf-8")); review_doc["reviewer"] = "forged reviewer"
    review_path.write_text(json.dumps(review_doc, indent=2), encoding="utf-8")
    expect_raises("tampered sealed review blocks rehearsal", lambda: ua.rehearse_transaction(tr, "m16-tamper-review", gate_runner=pass_gate), "review approval")

    ua.create_transaction(tr, {"candidates": [{"kind": "official_snapshot", "sourceId": "vendetta-faq-2026-08-14", "file": str(changed2)}]}, "m16-tamper-rehearsal")
    ua.stage_transaction(tr, "m16-tamper-rehearsal"); ua.approve_transaction(tr, "m16-tamper-rehearsal", "M16 Test Judge"); ua.rehearse_transaction(tr, "m16-tamper-rehearsal", gate_runner=pass_gate)
    rehearsal_path = tr / "data/update_transactions/m16-tamper-rehearsal/rehearsal.json"
    rehearsal_doc = json.loads(rehearsal_path.read_text(encoding="utf-8")); rehearsal_doc["publishReady"] = True; rehearsal_doc["publishBundleSha256"] = "0" * 64
    rehearsal_path.write_text(json.dumps(rehearsal_doc, indent=2), encoding="utf-8")
    expect_raises("tampered sealed rehearsal blocks publish", lambda: ua.publish_transaction(tr, "m16-tamper-rehearsal", gate_runner=pass_gate), "hash mismatch: rehearsal.json")

    # Poll host allowlist is checked before fetcher invocation.
    manifest_path = tr / "data/source/official_source_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    vendetta = next(x for x in manifest["sources"] if x.get("id") == "vendetta-faq-2026-08-14")
    vendetta["url"] = "https://evil.example.invalid/faq"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    called = {"value": False}
    def bad_fetcher(url, timeout): called["value"] = True; return raw, "text/plain"
    expect_raises("poll rejects non-official host before network call", lambda: ua.poll_registered_source(tr, "vendetta-faq-2026-08-14", fetcher=bad_fetcher, transaction_id="m16-evil"), "unapproved")
    check("rejected host never invokes fetcher", called["value"] is False, called)

# T164 — CLI surface and release gate completeness live in the real project.
help_run = subprocess.run([sys.executable, str(ROOT / "update_automation.py"), "--help"], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
check("Update Automation CLI help works", help_run.returncode == 0 and all(x in help_run.stdout for x in ("create", "stage", "approve", "rehearse", "publish", "status", "poll")), help_run.stdout)
check("release gate contains every certified Stable 1.0 test suite", len(TEST_SCRIPTS) == 19 and "tests/run_definition_lookup_tests.py" in TEST_SCRIPTS and "tests/run_ui_integration_tests.py" in TEST_SCRIPTS and "tests/run_update_tests.py" in TEST_SCRIPTS and "tests/run_update_automation_tests.py" in TEST_SCRIPTS and "tests/run_production_hardening_tests.py" in TEST_SCRIPTS and "tests/run_release_candidate_audit_tests.py" in TEST_SCRIPTS and "tests/run_stable_release_tests.py" in TEST_SCRIPTS, TEST_SCRIPTS)
check("release gate ends with validation and audit", FINAL_SCRIPTS == ("validate_all.py", "audit_project.py"), FINAL_SCRIPTS)
check("transaction workspace is not created in certified root during tests", not (ROOT / "data/update_transactions").exists(), ROOT / "data/update_transactions")

report = {
    "passed": not failures,
    "checkCount": checks,
    "failureCount": len(failures),
    "failures": failures,
    "metrics": {
        "schemaVersion": 1,
        "supportedCandidateKinds": sorted(ua.SUPPORTED_KINDS),
        "explicitHumanReviewForMaterialChanges": True,
        "isolatedRehearsal": True,
        "hashBoundPublishBundle": True,
        "staleBaselineProtection": True,
        "postPublishReleaseGate": True,
        "rollbackOnGateFailure": True,
        "registeredOfficialHostAllowlist": True,
        "sealedTransactionDocuments": True,
        "certifiedReleaseTestCount": len(TEST_SCRIPTS),
    },
}
out = ROOT / "data/validation/update_automation_test_report.json"
out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["passed"] else 1)
