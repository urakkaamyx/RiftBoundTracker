#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from riftkeep_rules.official_sources import import_official_snapshot, fetch_official_snapshot, compile_supplemental_sources
from riftkeep_rules.authority import load_authority_status
from riftkeep_rules.build import build as rebuild_engine


def main() -> int:
    ap = argparse.ArgumentParser(description="Archive/version official Riftbound web-rule sources.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    imp = sub.add_parser("import-file", help="Ingest a locally saved official HTML/text snapshot.")
    imp.add_argument("--source-id", required=True)
    imp.add_argument("--file", required=True, type=Path)
    imp.add_argument("--type", dest="source_type")
    imp.add_argument("--url")
    imp.add_argument("--published")
    imp.add_argument("--effective-from")
    imp.add_argument("--media-type")

    fetch = sub.add_parser("fetch", help="Fetch a registered official URL (for networked production/runtime environments).")
    fetch.add_argument("--source-id", required=True)
    fetch.add_argument("--url")
    fetch.add_argument("--timeout", type=int, default=30)

    fetch_all = sub.add_parser("fetch-all", help="Fetch all registered official web sources, preserve snapshots, then rebuild indexes.")
    fetch_all.add_argument("--timeout", type=int, default=30)
    fetch_all.add_argument("--current-only", action="store_true", help="Fetch only current/index/overlay/change-record sources; skip historical archives.")
    fetch_all.add_argument("--no-rebuild", action="store_true", help="Do not rebuild canonical/index outputs after syncing.")

    hist = sub.add_parser("fetch-missing-history", help="Fetch only historical FAQ/patch bodies listed in history_sync_plan.json.")
    hist.add_argument("--timeout", type=int, default=30)
    hist.add_argument("--no-rebuild", action="store_true")

    sub.add_parser("status", help="Show ingested snapshots and current authority completeness.")

    args = ap.parse_args()
    if args.cmd == "import-file":
        snap = import_official_snapshot(
            ROOT, args.source_id, args.file, media_type=args.media_type, source_type=args.source_type,
            source_url=args.url, published=args.published, effective_from=args.effective_from,
        )
        print(json.dumps({
            "sourceId": snap["sourceId"], "title": snap["title"], "sha256": snap["sha256"],
            "sectionCount": snap["sectionCount"], "archivePath": snap["archivePath"],
        }, indent=2))
        return 0
    if args.cmd == "fetch":
        snap = fetch_official_snapshot(ROOT, args.source_id, url=args.url, timeout=args.timeout)
        print(json.dumps({"sourceId": snap["sourceId"], "sha256": snap["sha256"], "sectionCount": snap["sectionCount"]}, indent=2))
        return 0
    if args.cmd == "fetch-missing-history":
        plan_path = ROOT / "data/source/history_sync_plan.json"
        manifest_path = ROOT / "data/source/official_source_manifest.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        by_id = {s.get("id"): s for s in manifest.get("sources", [])}
        rows = []
        failures = 0
        for item in plan.get("sources", []):
            sid = item.get("sourceId")
            src = by_id.get(sid)
            if not src or not src.get("url"):
                failures += 1
                rows.append({"sourceId": sid, "status": "error", "error": "source not registered with URL"})
                continue
            latest = ROOT / "data/source/snapshots" / str(sid) / "latest.json"
            if latest.exists():
                rows.append({"sourceId": sid, "status": "already_present"})
                continue
            try:
                snap = fetch_official_snapshot(ROOT, str(sid), timeout=args.timeout)
                rows.append({"sourceId": sid, "status": "ok", "sha256": snap.get("sha256"), "sections": snap.get("sectionCount")})
            except Exception as exc:
                failures += 1
                rows.append({"sourceId": sid, "status": "error", "error": f"{type(exc).__name__}: {exc}"})
        build_result = None if args.no_rebuild else rebuild_engine(ROOT)
        print(json.dumps({"sources": rows, "failureCount": failures, "build": build_result, "authorityStatus": load_authority_status(ROOT)}, ensure_ascii=False, indent=2))
        return 0 if failures == 0 else 2
    if args.cmd == "fetch-all":
        manifest_path = ROOT / "data/source/official_source_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        web_types = {"rules_hub", "official_faq", "patch_notes", "card_errata"}
        current_statuses = {"current_index", "current", "current_overlay", "current_change_record", "active_history"}
        rows = []
        failures = 0
        for src in manifest.get("sources", []):
            if src.get("type") not in web_types or not src.get("url"):
                continue
            if args.current_only and src.get("status") not in current_statuses:
                continue
            try:
                snap = fetch_official_snapshot(ROOT, src["id"], timeout=args.timeout)
                rows.append({"sourceId": src["id"], "status": "ok", "sha256": snap["sha256"], "sections": snap["sectionCount"], "changed": (snap.get("diffFromPrevious") or {}).get("changed")})
            except Exception as exc:
                failures += 1
                rows.append({"sourceId": src.get("id"), "status": "error", "error": f"{type(exc).__name__}: {exc}"})
        build_result = None
        if not args.no_rebuild:
            build_result = rebuild_engine(ROOT)
        print(json.dumps({
            "sources": rows,
            "failureCount": failures,
            "build": build_result,
            "authorityStatus": load_authority_status(ROOT),
        }, ensure_ascii=False, indent=2))
        return 0 if failures == 0 else 2
    supplemental = compile_supplemental_sources(ROOT)
    print(json.dumps({
        "snapshots": supplemental["snapshots"],
        "authorityStatus": load_authority_status(ROOT),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
