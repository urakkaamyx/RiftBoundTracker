#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from riftkeep_rules.engine import RulesEngine
from riftkeep_rules.versioning import compare_rule_versions

CORPUS_PATH = ROOT / "data/gold/gold_corpus.json"
MANIFEST_PATH = ROOT / "data/gold/gold_manifest.json"
REPORT_PATH = ROOT / "data/validation/gold_corpus_report.json"
METRICS_PATH = ROOT / "data/validation/gold_corpus_metrics.json"
PROMOTIONS_PATH = ROOT / "data/gold/gold_c_promotions.json"

failures: list[dict[str, Any]] = []
checks = 0


def check(name: str, ok: bool, detail: Any = None) -> None:
    global checks
    checks += 1
    if not ok:
        failures.append({"check": name, "detail": detail})


def load(rel: str) -> Any:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def sha_file(rel: str) -> str:
    h = hashlib.sha256()
    with (ROOT / rel).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def jhash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def check_ruling(case: dict[str, Any], result: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    for exp in case["expected"]:
        idx = exp["issue"]
        if idx >= len(result.get("issues", [])):
            reasons.append(f"missing issue {idx}")
            continue
        issue = result["issues"][idx]
        ruling = issue["ruling"]
        if ruling.get("status") != exp["status"]:
            reasons.append(f"issue {idx} status {ruling.get('status')} != {exp['status']}")
        evidence = set(issue.get("retrieval", {}).get("evidenceRuleIds", []))
        missing = [rid for rid in exp.get("requiredRules", []) if rid not in evidence]
        if missing:
            reasons.append(f"issue {idx} missing rules {missing}")
        if "effectiveVerdict" in exp:
            got = (ruling.get("effectiveVerdict") or {}).get("verdict")
            if got != exp["effectiveVerdict"]:
                reasons.append(f"issue {idx} effective verdict {got} != {exp['effectiveVerdict']}")
        if "verdict" in exp:
            verdicts = [o.get("verdict") for o in ruling.get("outcomes", [])]
            if exp["verdict"] not in verdicts:
                reasons.append(f"issue {idx} verdict {exp['verdict']} not in {verdicts}")
        if "requiredCard" in exp:
            cards = {c.get("id") for c in result.get("namedCards", [])}
            if exp["requiredCard"] not in cards:
                reasons.append(f"issue {idx} card {exp['requiredCard']} not resolved")
        if "requiredOfficialEvidence" in exp:
            official_ids = {str(x.get("evidenceId")) for x in issue.get("retrieval", {}).get("officialEvidence", []) if x.get("evidenceId")}
            miss = [eid for eid in exp["requiredOfficialEvidence"] if eid not in official_ids]
            if miss:
                reasons.append(f"issue {idx} missing official evidence {miss}")
    return reasons


def rule(rule_id: str, text: str, *, internal: str, major: str = "A") -> dict[str, Any]:
    return {
        "ruleId": rule_id,
        "internalRuleId": internal,
        "normativeText": text,
        "normalizedText": " ".join(text.casefold().split()),
        "majorSectionTitle": major,
    }


def doc(*rules: dict[str, Any]) -> dict[str, Any]:
    return {"rules": list(rules)}


def run_update_fixture(name: str, core: dict[str, Any], tournament: dict[str, Any]) -> tuple[bool, Any]:
    base = rule("1", "A player may draw one card during this procedure.", internal="RK-X-1", major="A")
    if name == "synthetic_unchanged":
        d = compare_rule_versions(doc(base), doc(dict(base)), stable_prefix="RK-X")
        return d["changeCounts"] == {"UNCHANGED": 1} and d["safeToAutoPromote"], d
    if name == "synthetic_text_changed":
        changed = rule("1", "A player may draw one card during this procedure now.", internal="TEMP", major="A")
        d = compare_rule_versions(doc(base), doc(changed), stable_prefix="RK-X")
        return d["changeCounts"].get("TEXT_CHANGED") == 1 and d["safeToAutoPromote"], d
    if name == "synthetic_repurpose":
        changed = rule("1", "Destroy every permanent and restart the entire game immediately.", internal="TEMP", major="Z")
        d = compare_rule_versions(doc(base), doc(changed), stable_prefix="RK-X")
        return d["reviewRequiredCount"] >= 1 and not d["safeToAutoPromote"], d
    if name == "synthetic_renumber":
        changed = rule("2", base["normativeText"], internal="TEMP", major="A")
        d = compare_rule_versions(doc(base), doc(changed), stable_prefix="RK-X")
        return d["changeCounts"].get("RENUMBERED") == 1 and d["safeToAutoPromote"], d
    if name == "synthetic_moved":
        changed = rule("2", base["normativeText"], internal="TEMP", major="B")
        d = compare_rule_versions(doc(base), doc(changed), stable_prefix="RK-X")
        return d["changeCounts"].get("MOVED") == 1 and d["safeToAutoPromote"], d
    if name == "synthetic_added":
        added = rule("2", "A newly added independent rule.", internal="TEMP", major="A")
        d = compare_rule_versions(doc(base), doc(base, added), stable_prefix="RK-X")
        return d["changeCounts"].get("ADDED_OR_REVIEW_REQUIRED") == 1 and not d["safeToAutoPromote"], d
    if name == "synthetic_removed":
        old2 = rule("2", "A second independent rule.", internal="RK-X-2", major="A")
        d = compare_rule_versions(doc(base, old2), doc(base), stable_prefix="RK-X")
        return d["changeCounts"].get("REMOVED_OR_REVIEW_REQUIRED") == 1 and not d["safeToAutoPromote"], d
    if name == "synthetic_add_remove":
        old2 = rule("2", "A second independent old rule.", internal="RK-X-2", major="A")
        new3 = rule("3", "A wholly different newly added rule.", internal="TEMP", major="B")
        d = compare_rule_versions(doc(base, old2), doc(base, new3), stable_prefix="RK-X")
        counts = d["changeCounts"]
        return counts.get("REMOVED_OR_REVIEW_REQUIRED") == 1 and counts.get("ADDED_OR_REVIEW_REQUIRED") == 1 and not d["safeToAutoPromote"], d
    if name == "current_core_self":
        d = compare_rule_versions(core, core)
        return d["changeCounts"] == {"UNCHANGED": 2381} and d["safeToAutoPromote"], {"changeCounts": d["changeCounts"], "safe": d["safeToAutoPromote"]}
    if name == "current_tournament_self":
        d = compare_rule_versions(tournament, tournament, stable_prefix="RK-TR")
        return d["changeCounts"] == {"UNCHANGED": 935} and d["safeToAutoPromote"], {"changeCounts": d["changeCounts"], "safe": d["safeToAutoPromote"]}
    if name == "stable_id_renumber":
        changed = rule("2", base["normativeText"], internal="TEMP", major="A")
        d = compare_rule_versions(doc(base), doc(changed), stable_prefix="RK-X")
        promoted = d["promotedNewRules"][0]
        return promoted.get("internalRuleId") == "RK-X-1" and promoted.get("identityStatus") == "inherited", promoted
    if name == "new_id_added":
        added = rule("2", "A newly added independent rule.", internal="TEMP", major="A")
        d = compare_rule_versions(doc(base), doc(base, added), stable_prefix="RK-X")
        promoted = next(x for x in d["promotedNewRules"] if x["ruleId"] == "2")
        return str(promoted.get("internalRuleId", "")).startswith("RK-X-NEW-") and promoted.get("identityStatus") == "new", promoted
    return False, {"unknownFixture": name}


def main() -> int:
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    promotions = json.loads(PROMOTIONS_PATH.read_text(encoding="utf-8"))
    cases = corpus["cases"]

    # Frozen corpus integrity / anti-self-fulfilling checks.
    check("corpus marked frozen", corpus.get("frozen") is True, corpus.get("frozen"))
    check("corpus expectations not engine-derived", corpus.get("derivedExpectationsFromEngine") is False and all(c.get("derivedFromEngine") is False for c in cases))
    ids = [c.get("caseId") for c in cases]
    duplicate_ids = sorted(k for k, n in Counter(ids).items() if n > 1)
    check("gold case IDs globally unique", not duplicate_ids, duplicate_ids[:20])
    check("manifest corpus hash matches frozen data", manifest.get("corpusSha256") == hashlib.sha256(CORPUS_PATH.read_bytes()).hexdigest())
    for rel, expected_hash in manifest.get("sourceHashes", {}).items():
        actual = sha_file(rel)
        check(f"frozen source hash {rel}", actual == expected_hash, {"expected": expected_hash, "actual": actual})
    check("runner may not regenerate expectations", manifest.get("policy", {}).get("runnerMayRegenerateExpectations") is False)

    tier_counts = Counter(c["tier"] for c in cases)
    category_counts = Counter(c["category"] for c in cases)
    check("total gold corpus count 1846", len(cases) == 1846, len(cases))
    check("Gold A count 396", tier_counts["A"] == 396, dict(tier_counts))
    check("Gold B count 1416", tier_counts["B"] == 1416, dict(tier_counts))
    check("Gold C count 34", tier_counts["C"] == 34, dict(tier_counts))

    # Gold A: one real adjudication for each of 99 independently expected semantic groups.
    ga = [c for c in cases if c["tier"] == "A"]
    groups: dict[str, list[dict[str, Any]]] = {}
    for c in ga:
        groups.setdefault(c["semanticGroupId"], []).append(c)
    check("Gold A has 99 semantic groups", len(groups) == 99, len(groups))
    engine = RulesEngine(ROOT, require_current_authority=False)
    adjudicated = 0
    gold_a_failures: list[dict[str, Any]] = []
    for gid in sorted(groups):
        rows = groups[gid]
        base_rows = [x for x in rows if x.get("fullAdjudication")]
        if len(rows) != 4 or len(base_rows) != 1:
            gold_a_failures.append({"group": gid, "reason": "group must contain exactly four rows and one base"})
            continue
        base = base_rows[0]
        result = engine.ask(base["question"])
        adjudicated += 1
        reasons = check_ruling(base, result)
        if reasons:
            gold_a_failures.append({"group": gid, "caseId": base["caseId"], "reasons": reasons})
        prefixes = {
            "identity": "",
            "prefix:Rules question: ": "Rules question: ",
            "prefix:Riftbound rules question: ": "Riftbound rules question: ",
            "prefix:Judge question: ": "Judge question: ",
        }
        for row in rows:
            transform = row["surfaceTransformation"]
            prefix = prefixes.get(transform)
            if prefix is None:
                gold_a_failures.append({"group": gid, "caseId": row["caseId"], "reason": f"unknown transformation {transform}"})
                continue
            if row["question"] != prefix + base["canonicalQuestion"]:
                gold_a_failures.append({"group": gid, "caseId": row["caseId"], "reason": "surface wrapper is not the declared exact transformation"})
            if row["expected"] != base["expected"]:
                gold_a_failures.append({"group": gid, "caseId": row["caseId"], "reason": "surface wrapper expectation differs from base"})
    check("Gold A 99 semantic adjudications pass", not gold_a_failures, gold_a_failures[:20])
    check("Gold A executes exactly one full adjudication per semantic group", adjudicated == 99, adjudicated)

    # Gold B direct source integrity.
    source_cards = load("data/source/riftbound_cards.json")
    source_cards = source_cards["cards"] if isinstance(source_cards, dict) and "cards" in source_cards else source_cards
    cards_by_id = {str(c["id"]): c for c in source_cards}
    faq_by_id = {d["evidenceId"]: d for d in load("data/canonical/supplemental_sources.json")["documents"]}
    errata_by_id: dict[str, dict[str, Any]] = {}
    for ident in load("data/canonical/official_errata_history.json")["identities"]:
        for event0 in ident.get("events", []):
            event = dict(event0)
            event["resolvedIdentityKey"] = ident.get("identityKey")
            event["currentOfficialText"] = ident.get("currentOfficialText")
            errata_by_id[event["entryId"]] = event
    core_hist = load("data/source/rule_versions/core/history.json")
    tr_hist = load("data/source/rule_versions/tournament/history.json")
    core = load("data/canonical/core_rules.json")
    tournament = load("data/canonical/tournament_rules.json")

    gb_failures: list[dict[str, Any]] = []
    for c in (x for x in cases if x["tier"] == "B"):
        cat = c["category"]
        if cat == "card_record":
            actual_card = cards_by_id.get(c["sourceCardId"])
            if actual_card is None:
                gb_failures.append({"caseId": c["caseId"], "reason": "card missing"}); continue
            actual = {k: actual_card.get(k) for k in c["expected"]}
            if actual != c["expected"] or jhash(actual) != c["expectedRecordHash"]:
                gb_failures.append({"caseId": c["caseId"], "reason": "card record drift"})
        elif cat == "current_faq_section":
            d = faq_by_id.get(c["sourceEvidenceId"])
            if d is None:
                gb_failures.append({"caseId": c["caseId"], "reason": "FAQ section missing"}); continue
            actual = {k: d.get(k) for k in c["expected"]}
            if actual != c["expected"] or jhash(actual) != c["expectedRecordHash"]:
                gb_failures.append({"caseId": c["caseId"], "reason": "FAQ section drift"})
        elif cat == "official_errata_event":
            e = errata_by_id.get(c["sourceErrataEntryId"])
            if e is None:
                gb_failures.append({"caseId": c["caseId"], "reason": "errata event missing"}); continue
            actual = {k: e.get(k) for k in c["expected"]}
            if actual != c["expected"] or jhash(actual) != c["expectedRecordHash"]:
                gb_failures.append({"caseId": c["caseId"], "reason": "errata event drift"})
        elif cat == "rule_version_record":
            hist = core_hist if c["family"] == "core" else tr_hist
            cur = next((x for x in hist["versions"] if x["sourceId"] == hist["currentSourceId"]), None)
            actual = None if cur is None else {"family": c["family"], "currentSourceId": hist["currentSourceId"], "sourceSha256": cur["sourceSha256"], "ruleCount": cur["ruleCount"], "status": cur["status"]}
            if actual != c["expected"] or (actual is not None and jhash(actual) != c["expectedRecordHash"]):
                gb_failures.append({"caseId": c["caseId"], "reason": "rule version record drift", "actual": actual})
        elif cat == "update_diff_fixture":
            ok, detail = run_update_fixture(c["fixture"], core, tournament)
            if not ok:
                gb_failures.append({"caseId": c["caseId"], "reason": "update fixture failed", "detail": detail})
        else:
            gb_failures.append({"caseId": c["caseId"], "reason": f"unknown Gold B category {cat}"})
    check("all 1416 Gold B direct-authority cases pass", not gb_failures, gb_failures[:20])

    # Gold C source fixtures remain frozen exactly as M12 certified them. M13 promotion is
    # an external reviewed overlay so M12 data is never rewritten to fit the current engine.
    gc_failures = []
    gold_c_cases = [x for x in cases if x["tier"] == "C"]
    gold_c_by_id = {x["caseId"]: x for x in gold_c_cases}
    for c in gold_c_cases:
        d = faq_by_id.get(c["authorityEvidenceId"])
        if d is None:
            gc_failures.append({"caseId": c["caseId"], "reason": "authority section missing"}); continue
        actual_hash = hashlib.sha256(d["text"].encode("utf-8")).hexdigest()
        if d.get("question") != c.get("question") or d.get("text") != c.get("officialRulingText") or actual_hash != c.get("officialRulingTextHash"):
            gc_failures.append({"caseId": c["caseId"], "reason": "forward authority fixture drift"})
        if c.get("releaseGating") is not False or c.get("targetMilestone") != "M13":
            gc_failures.append({"caseId": c["caseId"], "reason": "frozen Gold C fixture metadata drift"})
    check("all 34 frozen Gold C authority fixtures remain source-valid", not gc_failures, gc_failures[:20])

    # M13 promoted Gold-C interactions are now release-gating. Expectations come from the
    # human-reviewed promotion manifest / guarded program specs, never from engine output.
    check("M13 Gold-C promotion manifest is frozen and non-engine-derived", promotions.get("frozen") is True and promotions.get("derivedExpectationsFromEngine") is False and all(x.get("derivedFromEngine") is False for x in promotions.get("promotions", [])), promotions)
    promoted_rows = promotions.get("promotions", [])
    check("M13 promotes exactly 16 Gold-C fixtures", len(promoted_rows) == promotions.get("promotionCount") == 16 and promotions.get("remainingReportOnlyCount") == 18, {"promoted": len(promoted_rows), "remaining": promotions.get("remainingReportOnlyCount")})
    promoted_failures = []
    for promo in promoted_rows:
        c = gold_c_by_id.get(promo.get("caseId"))
        if not c:
            promoted_failures.append({"caseId": promo.get("caseId"), "reason": "promoted case missing from frozen Gold C"}); continue
        qhash = hashlib.sha256(c["question"].encode("utf-8")).hexdigest()
        if promo.get("authorityEvidenceId") != c.get("authorityEvidenceId") or promo.get("question") != c.get("question") or promo.get("questionSha256") != qhash:
            promoted_failures.append({"caseId": c["caseId"], "reason": "promotion does not match frozen source fixture"}); continue
        result = engine.ask(c["question"])
        execution = (result.get("cardInteractionContext") or {}).get("execution") or {}
        actual = [(i.get("ruling", {}).get("effectiveVerdict") or {}).get("verdict") for i in result.get("issues", [])]
        expected = list(promo.get("expectedIssueVerdicts") or [])
        if not (execution.get("supported") and execution.get("fullyCoversQuestion") and execution.get("programId") == promo.get("programId") and result.get("enginePolicy", {}).get("cardInteractionContextAppliesGameRules") is True):
            promoted_failures.append({"caseId": c["caseId"], "reason": "reviewed executor did not activate", "execution": execution}); continue
        if actual != expected or len(result.get("issues", [])) != promo.get("expectedIssueCount"):
            promoted_failures.append({"caseId": c["caseId"], "reason": "promoted verdict mismatch", "expected": expected, "actual": actual}); continue
        bad_proofs = [i.get("issue") for i in result.get("issues", []) if not (i.get("proofTrace", {}).get("verification") or {}).get("passed") or not any(x.get("programId") == promo.get("programId") for x in i.get("proofTrace", {}).get("cardInteractionPrograms", []))]
        if bad_proofs:
            promoted_failures.append({"caseId": c["caseId"], "reason": "promoted proof provenance/verification failed", "issues": bad_proofs})
    check("all 16 promoted Gold-C interactions pass current deterministic execution and proof", not promoted_failures, promoted_failures[:20])

    # Coverage metrics.
    bases = [c for c in ga if c.get("fullAdjudication")]
    rule_ids = sorted({rid for c in bases for e in c["expected"] for rid in e.get("requiredRules", [])})
    official_ids = sorted({eid for c in bases for e in c["expected"] for eid in e.get("requiredOfficialEvidence", [])})
    conditional_or_insufficient = sum(1 for c in bases if any(e.get("status") in {"conditional", "insufficient"} for e in c["expected"]))
    explicit_no = sum(1 for c in bases if any(str(e.get("effectiveVerdict", e.get("verdict", ""))).casefold() == "no" for e in c["expected"]))
    nonaffirmative_groups = sum(1 for c in bases if any(
        e.get("status") in {"conditional", "insufficient"} or str(e.get("effectiveVerdict", e.get("verdict", ""))).casefold() == "no"
        for e in c["expected"]
    ))
    metrics = {
        "schemaVersion": 1,
        "passed": not failures,
        "totalCases": len(cases),
        "tierCounts": dict(tier_counts),
        "categoryCounts": dict(category_counts),
        "goldASemanticGroups": len(groups),
        "goldAFullAdjudications": adjudicated,
        "distinctRequiredRuleIds": len(rule_ids),
        "requiredRuleIds": rule_ids,
        "distinctOfficialEvidenceIds": len(official_ids),
        "officialEvidenceIds": official_ids,
        "conditionalOrInsufficientSemanticGroups": conditional_or_insufficient,
        "explicitNoSemanticGroups": explicit_no,
        "nonAffirmativeSemanticGroups": nonaffirmative_groups,
        "realCardRecordsCovered": category_counts["card_record"],
        "currentFaqSectionsCovered": category_counts["current_faq_section"],
        "officialErrataEventsCovered": category_counts["official_errata_event"],
        "ruleVersionRecordsCovered": category_counts["rule_version_record"],
        "updateDiffFixturesCovered": category_counts["update_diff_fixture"],
        "forwardCardInteractionFixtures": category_counts["future_card_interaction"],
        "goldCPromotedReleaseGating": promotions.get("promotionCount"),
        "goldCRemainingReportOnly": promotions.get("remainingReportOnlyCount"),
        "goldCReleaseGating": True,
    }
    METRICS_PATH.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # M12 minimum thresholds.
    check("coverage threshold total >= 1800", metrics["totalCases"] >= 1800, metrics["totalCases"])
    check("coverage threshold semantic groups >= 99", metrics["goldASemanticGroups"] >= 99, metrics["goldASemanticGroups"])
    check("coverage threshold distinct rule IDs >= 120", metrics["distinctRequiredRuleIds"] >= 120, metrics["distinctRequiredRuleIds"])
    check("coverage threshold official evidence IDs >= 25", metrics["distinctOfficialEvidenceIds"] >= 25, metrics["distinctOfficialEvidenceIds"])
    check("coverage threshold cards == 1304", metrics["realCardRecordsCovered"] == 1304, metrics["realCardRecordsCovered"])
    check("coverage threshold FAQ == 35", metrics["currentFaqSectionsCovered"] == 35, metrics["currentFaqSectionsCovered"])
    check("coverage threshold errata == 63", metrics["officialErrataEventsCovered"] == 63, metrics["officialErrataEventsCovered"])
    check("coverage threshold update fixtures == 12", metrics["updateDiffFixturesCovered"] == 12, metrics["updateDiffFixturesCovered"])
    check("coverage threshold forward fixtures == 34", metrics["forwardCardInteractionFixtures"] == 34, metrics["forwardCardInteractionFixtures"])
    check("coverage threshold M13 promoted Gold-C == 16", metrics["goldCPromotedReleaseGating"] == 16, metrics["goldCPromotedReleaseGating"])

    report = {
        "schemaVersion": 1,
        "passed": not failures,
        "checkCount": checks,
        "caseCount": len(cases),
        "failureCount": len(failures),
        "failures": failures,
        "metrics": metrics,
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "checkCount": checks, "caseCount": len(cases), "failureCount": len(failures), "failures": failures[:10], "metrics": {k:v for k,v in metrics.items() if not k.endswith('Ids')}}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
