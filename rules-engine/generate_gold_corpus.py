#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data/gold/gold_corpus.json"
MANIFEST = ROOT / "data/gold/gold_manifest.json"


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


def source_hashes() -> dict[str, str]:
    paths = [
        "tests/regression_cases.json",
        "data/source/riftbound_cards.json",
        "data/source/official_text/vendetta_faq_2026-08-14.txt",
        "data/canonical/official_errata_history.json",
        "data/source/rule_versions/core/history.json",
        "data/source/rule_versions/tournament/history.json",
        "tests/run_update_tests.py",
    ]
    return {p: sha_file(p) for p in paths}


def gold_a() -> list[dict[str, Any]]:
    regressions = load("tests/regression_cases.json")
    rows: list[dict[str, Any]] = []
    wrappers = [
        ("BASE", "", ""),
        ("RULES", "Rules question: ", "prefix:Rules question: "),
        ("RIFTBOUND", "Riftbound rules question: ", "prefix:Riftbound rules question: "),
        ("JUDGE", "Judge question: ", "prefix:Judge question: "),
    ]
    for i, case in enumerate(regressions, 1):
        group = f"GA-{i:03d}"
        for tag, prefix, transform in wrappers:
            rows.append({
                "caseId": f"{group}-{tag}",
                "tier": "A",
                "category": "adjudication",
                "semanticGroupId": group,
                "semanticCaseIndex": i - 1,
                "name": case["name"],
                "question": prefix + case["question"],
                "canonicalQuestion": case["question"],
                "expected": case["expected"],
                "fullAdjudication": tag == "BASE",
                "surfaceTransformation": transform or "identity",
                "derivedFromEngine": False,
                "verificationMethod": "locked-regression-fixture" if tag == "BASE" else "audited-surface-wrapper",
                "expectationSource": "tests/regression_cases.json",
            })
    return rows


def gold_b_cards() -> list[dict[str, Any]]:
    source = load("data/source/riftbound_cards.json")
    cards = source["cards"] if isinstance(source, dict) and "cards" in source else source
    fields = ["id", "name", "setId", "setLabel", "collectorNumber", "collectorCode", "type", "supertype", "rarity", "domains", "textPlain", "energy", "might", "power"]
    rows = []
    for card in cards:
        expected = {k: card.get(k) for k in fields}
        cid = str(card["id"])
        rows.append({
            "caseId": f"GB-CARD-{cid}",
            "tier": "B",
            "category": "card_record",
            "sourceCardId": cid,
            "expected": expected,
            "expectedRecordHash": jhash(expected),
            "derivedFromEngine": False,
            "verificationMethod": "direct-authoritative-card-record",
            "expectationSource": "data/source/riftbound_cards.json",
        })
    return rows


def gold_b_faq() -> list[dict[str, Any]]:
    docs = load("data/canonical/supplemental_sources.json")["documents"]
    rows = []
    for doc in docs:
        eid = doc["evidenceId"]
        expected = {
            "evidenceId": eid,
            "sourceId": doc.get("sourceId"),
            "sequence": doc.get("sequence"),
            "question": doc.get("question"),
            "contentHash": doc.get("contentHash"),
            "rulingRole": doc.get("rulingRole"),
            "compilerFamily": doc.get("compilerFamily"),
            "text": doc.get("text"),
        }
        rows.append({
            "caseId": f"GB-FAQ-{eid}",
            "tier": "B",
            "category": "current_faq_section",
            "sourceEvidenceId": eid,
            "expected": expected,
            "expectedRecordHash": jhash(expected),
            "derivedFromEngine": False,
            "verificationMethod": "direct-current-faq-snapshot",
            "expectationSource": "data/canonical/supplemental_sources.json",
        })
    return rows


def gold_b_errata() -> list[dict[str, Any]]:
    history = load("data/canonical/official_errata_history.json")
    events = []
    for ident in history["identities"]:
        for event in ident.get("events", []):
            x = dict(event)
            x["resolvedIdentityKey"] = ident.get("identityKey")
            x["currentOfficialText"] = ident.get("currentOfficialText")
            events.append(x)
    by_id = {e["entryId"]: e for e in events}
    rows = []
    for eid in sorted(by_id):
        event = by_id[eid]
        expected = {
            "entryId": eid,
            "sourceId": event.get("sourceId"),
            "published": event.get("published"),
            "cardName": event.get("cardName"),
            "oldText": event.get("oldText"),
            "newText": event.get("newText"),
            "matchedCardIds": event.get("matchedCardIds", []),
            "resolvedIdentityKey": event.get("resolvedIdentityKey"),
            "currentOfficialText": event.get("currentOfficialText"),
        }
        rows.append({
            "caseId": f"GB-ERRATA-{eid}",
            "tier": "B",
            "category": "official_errata_event",
            "sourceErrataEntryId": eid,
            "expected": expected,
            "expectedRecordHash": jhash(expected),
            "derivedFromEngine": False,
            "verificationMethod": "direct-official-errata-history",
            "expectationSource": "data/canonical/official_errata_history.json",
        })
    return rows


def gold_b_versions() -> list[dict[str, Any]]:
    rows = []
    for family in ("core", "tournament"):
        rel = f"data/source/rule_versions/{family}/history.json"
        hist = load(rel)
        current = next(x for x in hist["versions"] if x["sourceId"] == hist["currentSourceId"])
        expected = {
            "family": family,
            "currentSourceId": hist["currentSourceId"],
            "sourceSha256": current["sourceSha256"],
            "ruleCount": current["ruleCount"],
            "status": current["status"],
        }
        rows.append({
            "caseId": f"GB-VERSION-{family}",
            "tier": "B",
            "category": "rule_version_record",
            "family": family,
            "expected": expected,
            "expectedRecordHash": jhash(expected),
            "derivedFromEngine": False,
            "verificationMethod": "direct-rule-version-ledger",
            "expectationSource": rel,
        })
    return rows


def gold_b_update_fixtures() -> list[dict[str, Any]]:
    fixtures = [
        ("unchanged", "synthetic_unchanged", {"changeCounts": {"UNCHANGED": 1}, "safe": True}),
        ("text-changed", "synthetic_text_changed", {"has": "TEXT_CHANGED", "safe": True}),
        ("repurpose-review", "synthetic_repurpose", {"review": True, "safe": False}),
        ("renumber", "synthetic_renumber", {"has": "RENUMBERED", "safe": True}),
        ("moved", "synthetic_moved", {"has": "MOVED", "safe": True}),
        ("added", "synthetic_added", {"has": "ADDED_OR_REVIEW_REQUIRED", "safe": False}),
        ("removed", "synthetic_removed", {"has": "REMOVED_OR_REVIEW_REQUIRED", "safe": False}),
        ("add-remove", "synthetic_add_remove", {"hasBoth": ["ADDED_OR_REVIEW_REQUIRED", "REMOVED_OR_REVIEW_REQUIRED"], "safe": False}),
        ("core-self", "current_core_self", {"changeCounts": {"UNCHANGED": 2381}, "safe": True}),
        ("tournament-self", "current_tournament_self", {"changeCounts": {"UNCHANGED": 935}, "safe": True}),
        ("stable-id-renumber", "stable_id_renumber", {"stableIdInherited": True}),
        ("new-id-added", "new_id_added", {"newIdAssigned": True}),
    ]
    return [{
        "caseId": f"GB-UPDATE-{name}",
        "tier": "B",
        "category": "update_diff_fixture",
        "fixture": fixture,
        "expected": expected,
        "derivedFromEngine": False,
        "verificationMethod": "deterministic-versioning-fixture",
        "expectationSource": "M12 curated update/versioning fixture",
    } for name, fixture, expected in fixtures]


def gold_c() -> list[dict[str, Any]]:
    docs = load("data/canonical/supplemental_sources.json")["documents"]
    rows = []
    substantive = [d for d in docs if d.get("question")]
    for i, doc in enumerate(substantive, 1):
        rows.append({
            "caseId": f"GC-FAQ-{i:03d}",
            "tier": "C",
            "category": "future_card_interaction",
            "question": doc["question"],
            "authorityEvidenceId": doc["evidenceId"],
            "officialRulingText": doc["text"],
            "officialRulingTextHash": hashlib.sha256(doc["text"].encode("utf-8")).hexdigest(),
            "rulingRole": doc.get("rulingRole"),
            "compilerFamily": doc.get("compilerFamily"),
            "releaseGating": False,
            "targetMilestone": "M13",
            "derivedFromEngine": False,
            "verificationMethod": "official-faq-authority-forward-fixture",
            "expectationSource": f"{doc['evidenceId']} in current Vendetta FAQ snapshot",
        })
    return rows


def main() -> None:
    cases = gold_a() + gold_b_cards() + gold_b_faq() + gold_b_errata() + gold_b_versions() + gold_b_update_fixtures() + gold_c()
    ids = [c["caseId"] for c in cases]
    dups = sorted({x for x in ids if ids.count(x) > 1})
    if dups:
        raise SystemExit(f"duplicate gold case IDs: {dups[:20]}")
    tiers = {t: sum(1 for c in cases if c["tier"] == t) for t in ("A", "B", "C")}
    categories: dict[str, int] = {}
    for c in cases:
        categories[c["category"]] = categories.get(c["category"], 0) + 1
    payload = {
        "schemaVersion": 1,
        "frozen": True,
        "generatedForMilestone": "M12",
        "derivedExpectationsFromEngine": False,
        "caseCount": len(cases),
        "tierCounts": tiers,
        "categoryCounts": categories,
        "cases": cases,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "schemaVersion": 1,
        "frozen": True,
        "generatedForMilestone": "M12",
        "corpusSha256": hashlib.sha256(OUT.read_bytes()).hexdigest(),
        "sourceHashes": source_hashes(),
        "expectedCounts": {"total": len(cases), "tiers": tiers, "categories": categories},
        "policy": {
            "runnerMayRegenerateExpectations": False,
            "sourceDriftRequiresExplicitRecertification": True,
            "goldAFullAdjudicationsPerSemanticGroup": 1,
            "goldCReleaseGating": False,
        },
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"caseCount": len(cases), "tiers": tiers, "categories": categories, "duplicates": len(dups)}, indent=2))


if __name__ == "__main__":
    main()
