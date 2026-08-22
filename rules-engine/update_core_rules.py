#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from riftkeep_rules.rule_updates import promote_staged_update, stage_rules_update


def main() -> int:
    ap = argparse.ArgumentParser(description="Stage or promote a Core Rules PDF without destroying history.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("stage", help="Parse, independently validate, diff, and stage a future PDF. Never changes live authority.")
    st.add_argument("pdf", type=Path)
    st.add_argument("--source-id", required=True, help="e.g. core-rules-2026-11-01")
    st.add_argument("--effective-from")
    pr = sub.add_parser("promote", help="Promote an already staged source through the version/history gate.")
    pr.add_argument("--source-id", required=True)
    pr.add_argument("--approve-review", action="store_true", help="Required when add/remove/ambiguous changes need human review.")
    args = ap.parse_args()
    if args.cmd == "stage":
        result = stage_rules_update(ROOT, "core", args.pdf, args.source_id, args.effective_from)
    else:
        result = promote_staged_update(ROOT, "core", args.source_id, args.approve_review)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
