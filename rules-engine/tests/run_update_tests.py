#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from riftkeep_rules.authority import load_authority_status
from riftkeep_rules.engine import RulesEngine
from riftkeep_rules.official_sources import import_official_snapshot, compile_supplemental_sources
from riftkeep_rules.source_integrity import validate_current_overlays
from riftkeep_rules.parser import parse_numbered_pdf, validate_pdf_parse
from riftkeep_rules.retrieval import build_index
from riftkeep_rules.versioning import compare_rule_versions
from riftkeep_rules.rule_updates import stage_rules_update, promote_staged_update
import riftkeep_rules.rule_updates as rule_updates_module
from riftkeep_rules.version_integrity import ensure_version_ledgers, validate_rule_version_integrity, sha256_file

failures: list[dict] = []
checks = 0

def check(name: str, ok: bool, detail="") -> None:
    global checks
    checks += 1
    if not ok:
        failures.append({"name": name, "detail": str(detail)})

core = json.loads((ROOT / "data/canonical/core_rules.json").read_text(encoding="utf-8"))

# Future-PDF pipeline: current PDF used as a deterministic no-change fixture.
future = parse_numbered_pdf(ROOT / "data/source/core_rules.pdf", "core-rules-future-self-test", "RK-CR", "Riftbound Core Rules")
parsed = validate_pdf_parse(ROOT / "data/source/core_rules.pdf", future)
check("future PDF parse validates", parsed["passed"], parsed)
self_diff = compare_rule_versions(core, future)
check("future PDF unchanged baseline matches all rules", self_diff["changeCounts"] == {"UNCHANGED": 2381}, self_diff["changeCounts"])
check("unchanged future PDF can auto-promote", self_diff["safeToAutoPromote"], self_diff.get("reviewRequired"))

# Same visible rule ID with unrelated content must never silently inherit identity.
repurpose = copy.deepcopy(core)
r = next(x for x in repurpose["rules"] if x["ruleId"] == "355.2.a")
r["normativeText"] = "This rule number has been intentionally repurposed to an unrelated synthetic test statement."
r["normalizedText"] = r["normativeText"].lower()
repurpose_diff = compare_rule_versions(core, repurpose)
check("same-number repurpose requires review", repurpose_diff["reviewRequiredCount"] >= 1 and not repurpose_diff["safeToAutoPromote"], repurpose_diff["reviewRequired"][:4])

# Addition/removal cannot auto-promote without review.
shape_change = copy.deepcopy(core)
removed = shape_change["rules"].pop(100)
new_rule = copy.deepcopy(shape_change["rules"][100])
new_rule["ruleId"] = "999.99.synthetic"
new_rule["internalRuleId"] = "TEMP"
new_rule["normativeText"] = "Synthetic newly added rule for update-regression coverage."
new_rule["normalizedText"] = new_rule["normativeText"].lower()
shape_change["rules"].append(new_rule)
shape_diff = compare_rule_versions(core, shape_change)
check("add/remove shape change cannot auto-promote", not shape_diff["safeToAutoPromote"], shape_diff["changeCounts"])
check("removed rule is surfaced", shape_diff["unmatchedOldCount"] >= 1, shape_diff["changeCounts"])
check("added rule is surfaced", shape_diff["unmatchedNewCount"] >= 1, shape_diff["changeCounts"])

# Current FAQ overlay: searchable, precedence-carrying, immutable, and fail-closed.
with tempfile.TemporaryDirectory() as td:
    tr = Path(td)
    (tr / "data/source").mkdir(parents=True)
    (tr / "data/canonical").mkdir(parents=True)
    (tr / "data/index").mkdir(parents=True)
    for name in ("core_rules.json", "cards.json", "semantic_ir.json"):
        shutil.copyfile(ROOT / "data/canonical" / name, tr / "data/canonical" / name)
    shutil.copyfile(ROOT / "data/source/riftbound_cards.json", tr / "data/source/riftbound_cards.json")
    # Authority checks existence/hash provenance separately from parser contents here.
    shutil.copyfile(ROOT / "data/source/core_rules.pdf", tr / "data/source/core_rules.pdf")
    manifest = {
        "schemaVersion": 1,
        "sources": [
            {"id":"core-current","type":"core_rules_pdf","status":"current","localSnapshot":"core_rules.pdf","authorityScope":["game_rules"]},
            {"id":"faq-current","type":"official_faq","status":"current_overlay","url":"https://playriftbound.com/en-us/news/rules-and-releases/synthetic-current-faq/","published":"2026-08-20","effectiveFrom":"2026-08-20","authorityScope":["official_rulings"],"precedence":{"over":["core-current"],"onlyWhereDifferent":True,"expiresWhen":"next_core_rules_document_released"}},
        ]
    }
    (tr / "data/source/official_source_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    faq1 = tr / "faq1.html"
    faq1.write_text("<html><body><h1>Synthetic Current FAQ</h1><h2>Playing Units</h2><p>Can Alpha be played to a special battlefield?</p><p>For this synthetic regression, Alpha may be played there. See CR 355.2.</p></body></html>", encoding="utf-8")
    s1 = import_official_snapshot(tr, "faq-current", faq1)
    check("current FAQ validates", s1["validation"]["passed"], s1["validation"])
    check("current FAQ carries precedence metadata", (s1.get("authority") or {}).get("precedence", {}).get("onlyWhereDifferent") is True, s1.get("authority"))
    auth = load_authority_status(tr)
    check("current gameplay authority becomes complete after overlay ingest", auth["coverage"]["gameplayRulesCurrent"]["complete"], auth)

    supplemental = compile_supplemental_sources(tr)
    cards = json.loads((tr / "data/canonical/cards.json").read_text(encoding="utf-8"))
    build_index(tr / "data/index/rules.sqlite", core, cards, supplemental)
    e = RulesEngine(tr, require_current_authority=True)
    result = e.ask("Can Alpha be played to a special battlefield?")
    issue = result["issues"][0]
    official = issue["retrieval"].get("officialEvidence") or []
    check("current FAQ evidence is searchable", any(x.get("sourceId") == "faq-current" for x in official), official)
    check("relevant current overlay blocks Core-only verdict", issue["ruling"]["status"] == "insufficient" and bool(issue["ruling"].get("officialOverlayEvidenceIds")), issue["ruling"])

    # Edit in place: old snapshot remains and section diff records the change.
    faq2 = tr / "faq2.html"
    faq2.write_text("<html><body><h1>Synthetic Current FAQ</h1><h2>Playing Units</h2><p>Can Alpha be played to a special battlefield?</p><p>For this synthetic regression, Alpha may NOT be played there. See CR 355.2.</p><p>Can Beta be played there?</p><p>Beta may be played there.</p></body></html>", encoding="utf-8")
    s2 = import_official_snapshot(tr, "faq-current", faq2)
    check("edited FAQ preserves previous hash", s2.get("previousSha256") == s1.get("sha256"), (s1.get("sha256"), s2.get("previousSha256")))
    cc = (s2.get("diffFromPrevious") or {}).get("changeCounts") or {}
    check("edited FAQ produces section-level change record", cc.get("TEXT_CHANGED", 0) + cc.get("ADDED", 0) >= 1, cc)


# Current packaged authority overlay is complete, hashed, classified, and strict-mode usable.
current_integrity = validate_current_overlays(ROOT)
check("current Vendetta overlay integrity passes", current_integrity.get("passed") is True and current_integrity.get("activeOverlayCount") == 1, current_integrity)
current_source = next((x for x in current_integrity.get("sources", []) if x.get("sourceId") == "vendetta-faq-2026-08-14"), {})
check("current Vendetta overlay contains 35 contiguous sections", current_source.get("sectionCount") == 35 and current_source.get("checks", {}).get("evidenceIdsContiguous") is True, current_source)
current_catalog = json.loads((ROOT / "data/source/official_ruling_catalog.json").read_text(encoding="utf-8")).get("sections", {})
check("all current FAQ sections have authority roles", len(current_catalog) == 35 and all((v or {}).get("role") and (v or {}).get("compilerFamily") for v in current_catalog.values()), str(len(current_catalog)))
check("Might and linked-instruction sections are explicit overrides", current_catalog.get("O:vendetta-faq-2026-08-14:0030", {}).get("role") == "override" and current_catalog.get("O:vendetta-faq-2026-08-14:0035", {}).get("role") == "override", str({k: current_catalog.get(k) for k in ("O:vendetta-faq-2026-08-14:0030","O:vendetta-faq-2026-08-14:0035")}))
overrides = json.loads((ROOT / "data/canonical/effective_rule_overrides.json").read_text(encoding="utf-8"))
check("effective Might override artifact is valid", overrides.get("valid") is True and any(r.get("overrideId") == "vendetta-2026-might-copyable" and r.get("value") == "Might" for r in overrides.get("overrides", [])), overrides)
strict_current = RulesEngine(ROOT, require_current_authority=True)
strict_might = strict_current.ask("Is Might a copyable trait?")
check("strict current authority decides Might override", strict_might["issues"][0]["ruling"].get("status") == "decided" and (strict_might["issues"][0]["ruling"].get("effectiveVerdict") or {}).get("verdict") == "might_is_copyable_current", strict_might.get("answer", ""))
strict_deflect = strict_current.ask("What does Deflect mean?")
check("full FAQ overlay does not block unrelated definition lookup", strict_deflect["issues"][0]["ruling"].get("status") == "decided", strict_deflect.get("answer", ""))

# A locally archived but superseded FAQ must remain historical and never become an active override.
with tempfile.TemporaryDirectory() as td:
    tr = Path(td)
    (tr / "data/source").mkdir(parents=True)
    (tr / "data/canonical").mkdir(parents=True)
    (tr / "data/index").mkdir(parents=True)
    for name in ("core_rules.json", "cards.json", "semantic_ir.json"):
        shutil.copyfile(ROOT / "data/canonical" / name, tr / "data/canonical" / name)
    shutil.copyfile(ROOT / "data/source/riftbound_cards.json", tr / "data/source/riftbound_cards.json")
    shutil.copyfile(ROOT / "data/source/core_rules.pdf", tr / "data/source/core_rules.pdf")
    old_manifest = {"schemaVersion":1,"sources":[
        {"id":"core-current","type":"core_rules_pdf","status":"current","localSnapshot":"core_rules.pdf","authorityScope":["game_rules"]},
        {"id":"faq-old","type":"official_faq","status":"superseded_history","url":"https://playriftbound.com/en-us/news/rules-and-releases/synthetic-old-faq/","published":"2026-01-01","authorityScope":["official_rulings"],"precedence":{"over":["core-current"],"onlyWhereDifferent":True}}
    ]}
    (tr / "data/source/official_source_manifest.json").write_text(json.dumps(old_manifest), encoding="utf-8")
    old_html = tr / "old.html"
    old_html.write_text("<html><body><h1>Old FAQ</h1><p>Can an old FAQ override this?</p><p>For the synthetic fixture, yes.</p></body></html>", encoding="utf-8")
    import_official_snapshot(tr, "faq-old", old_html)
    old_auth = load_authority_status(tr)
    check("superseded FAQ is excluded from active overlays", not old_auth.get("activeOverlays") and old_auth.get("currentRulesComplete") is True, old_auth)


# The stage/promote tests below exercise update orchestration, not PDF extraction itself.
# Parser extraction is already independently tested above, so reuse canonical parses here
# to keep the update suite fast while still verifying hashes, identity, history, and gates.
_real_stage_parse = rule_updates_module.parse_numbered_pdf
_real_stage_validate = rule_updates_module.validate_pdf_parse
def _fixture_stage_parse(path, source_id, stable_prefix, title):
    fixture_name = "core_rules.json" if stable_prefix == "RK-CR" else "tournament_rules.json"
    doc = copy.deepcopy(json.loads((ROOT / "data/canonical" / fixture_name).read_text(encoding="utf-8")))
    doc["metadata"]["sourceId"] = source_id
    doc["metadata"]["sourceSha256"] = sha256_file(Path(path))
    doc["metadata"]["sourceFile"] = Path(path).name
    for row in doc.get("rules", []):
        row["sourceId"] = source_id
    return doc
def _fixture_stage_validate(path, parsed):
    return {"passed": True, "ruleCount": len(parsed.get("rules", [])), "fixture": True}
rule_updates_module.parse_numbered_pdf = _fixture_stage_parse
rule_updates_module.validate_pdf_parse = _fixture_stage_validate

# Post-Milestone-5 audit recovery: immutable version ledgers and gated promotion.
version_integrity = validate_rule_version_integrity(ROOT)
check("rule-version ledgers protect both current PDFs", version_integrity.get("passed") is True and set((version_integrity.get("families") or {}).keys()) == {"core", "tournament"}, version_integrity)

# Silent current-PDF replacement must be detected before any future build can trust it.
with tempfile.TemporaryDirectory() as td:
    tr = Path(td)
    (tr / "data/source").mkdir(parents=True)
    (tr / "data/canonical").mkdir(parents=True)
    shutil.copyfile(ROOT / "data/source/core_rules.pdf", tr / "data/source/core_rules.pdf")
    shutil.copyfile(ROOT / "data/source/tournament_rules.pdf", tr / "data/source/tournament_rules.pdf")
    shutil.copyfile(ROOT / "data/source/official_source_manifest.json", tr / "data/source/official_source_manifest.json")
    shutil.copyfile(ROOT / "data/canonical/core_rules.json", tr / "data/canonical/core_rules.json")
    shutil.copyfile(ROOT / "data/canonical/tournament_rules.json", tr / "data/canonical/tournament_rules.json")
    ensure_version_ledgers(tr)
    with (tr / "data/source/core_rules.pdf").open("ab") as f:
        f.write(b"\nRIFTKEEP_SYNTHETIC_TAMPER\n")
    tampered = validate_rule_version_integrity(tr)
    check("silent current Core PDF replacement is detected", tampered.get("passed") is False and any("livePdfHashMatchesLedger" in x for x in tampered.get("errors", [])), tampered)

# Core stage -> review gate -> promote preserves history/identity and does not mutate live authority during staging.
with tempfile.TemporaryDirectory() as td:
    tr = Path(td)
    (tr / "data/source").mkdir(parents=True)
    (tr / "data/canonical").mkdir(parents=True)
    for name in ("core_rules.pdf", "tournament_rules.pdf", "official_source_manifest.json"):
        shutil.copyfile(ROOT / "data/source" / name, tr / "data/source" / name)
    for name in ("core_rules.json", "tournament_rules.json"):
        shutil.copyfile(ROOT / "data/canonical" / name, tr / "data/canonical" / name)
    ensure_version_ledgers(tr)
    before_sha = sha256_file(tr / "data/source/core_rules.pdf")
    stage = stage_rules_update(tr, "core", tr / "data/source/core_rules.pdf", "core-rules-synthetic-next", "2099-01-01")
    after_stage_sha = sha256_file(tr / "data/source/core_rules.pdf")
    hist_before = json.loads((tr / "data/source/rule_versions/core/history.json").read_text(encoding="utf-8"))
    check("Core staging is non-destructive", before_sha == after_stage_sha and hist_before.get("currentSourceId") == "core-rules-2026-07-16", {"stage": stage, "history": hist_before})
    check("unchanged staged Core PDF is safe for promotion", stage.get("status") == "ready_for_promotion" and stage.get("diff", {}).get("safeToAutoPromote") is True and stage.get("diff", {}).get("changeCounts") == {"UNCHANGED": 2381}, stage)

    # Flip only the stage gate metadata to prove an unsafe/review-required stage cannot promote without explicit approval.
    stage_path = tr / "data/source/rule_versions/core/staged/core-rules-synthetic-next/stage.json"
    stage_doc = json.loads(stage_path.read_text(encoding="utf-8"))
    stage_doc["diff"]["safeToAutoPromote"] = False
    stage_path.write_text(json.dumps(stage_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    refused = False
    try:
        promote_staged_update(tr, "core", "core-rules-synthetic-next", approve_review=False)
    except RuntimeError:
        refused = True
    check("review-required promotion refuses implicit approval", refused, stage_doc)
    stage_doc["diff"]["safeToAutoPromote"] = True
    stage_path.write_text(json.dumps(stage_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    promoted = promote_staged_update(tr, "core", "core-rules-synthetic-next")
    hist_after = json.loads((tr / "data/source/rule_versions/core/history.json").read_text(encoding="utf-8"))
    manifest_after = json.loads((tr / "data/source/official_source_manifest.json").read_text(encoding="utf-8"))
    promoted_doc = json.loads((tr / "data/source/rule_versions/core/core-rules-synthetic-next/parsed_rules.json").read_text(encoding="utf-8"))
    old_doc = json.loads((ROOT / "data/canonical/core_rules.json").read_text(encoding="utf-8"))
    old_internal = {r["ruleId"]: r["internalRuleId"] for r in old_doc["rules"]}
    new_internal = {r["ruleId"]: r["internalRuleId"] for r in promoted_doc["rules"]}
    current_core_sources = [x for x in manifest_after.get("sources", []) if x.get("type") == "core_rules_pdf" and x.get("status") == "current"]
    expired = next((x for x in manifest_after.get("sources", []) if x.get("id") == "vendetta-faq-2026-08-14"), {})
    check("Core promotion archives old version and preserves stable identities", promoted.get("status") == "promoted" and hist_after.get("currentSourceId") == "core-rules-synthetic-next" and len(hist_after.get("versions", [])) == 2 and len(current_core_sources) == 1 and current_core_sources[0].get("id") == "core-rules-synthetic-next" and old_internal == new_internal and expired.get("status") == "superseded_history", {"promotion": promoted, "history": hist_after, "expiredOverlay": expired})

# Tournament uses the same immutable stage/promote lifecycle and one-current-version invariant.
with tempfile.TemporaryDirectory() as td:
    tr = Path(td)
    (tr / "data/source").mkdir(parents=True)
    (tr / "data/canonical").mkdir(parents=True)
    for name in ("core_rules.pdf", "tournament_rules.pdf", "official_source_manifest.json"):
        shutil.copyfile(ROOT / "data/source" / name, tr / "data/source" / name)
    for name in ("core_rules.json", "tournament_rules.json"):
        shutil.copyfile(ROOT / "data/canonical" / name, tr / "data/canonical" / name)
    ensure_version_ledgers(tr)
    tstage = stage_rules_update(tr, "tournament", tr / "data/source/tournament_rules.pdf", "tournament-rules-synthetic-next", "2099-01-01")
    tpromote = promote_staged_update(tr, "tournament", "tournament-rules-synthetic-next")
    tintegrity = validate_rule_version_integrity(tr)
    check("Tournament stage/promote workflow preserves version integrity", tstage.get("diff", {}).get("changeCounts") == {"UNCHANGED": 935} and tpromote.get("status") == "promoted" and tintegrity.get("passed") is True and tintegrity.get("families", {}).get("tournament", {}).get("currentSourceId") == "tournament-rules-synthetic-next", {"stage": tstage, "promotion": tpromote, "integrity": tintegrity})

rule_updates_module.parse_numbered_pdf = _real_stage_parse
rule_updates_module.validate_pdf_parse = _real_stage_validate

out = {"passed": not failures, "checkCount": checks, "failureCount": len(failures), "failures": failures}
(ROOT / "data/validation/update_test_report.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=2))
raise SystemExit(0 if not failures else 1)
