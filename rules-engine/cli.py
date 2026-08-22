#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from riftkeep_rules.authority import load_authority_status
from riftkeep_rules.engine import RulesEngine


def main() -> int:
    ap = argparse.ArgumentParser(description="Ask the RiftKeep deterministic Riftbound rules engine.")
    ap.add_argument("question", nargs="*", help="Rules question")
    ap.add_argument("--status", action="store_true", help="Show source-authority coverage and exit.")
    ap.add_argument(
        "--allow-incomplete-authority",
        action="store_true",
        help="Developer/testing mode: return the Core Rules baseline even if a current official overlay is not locally mirrored.",
    )
    ap.add_argument("--compact", action="store_true", help="Print only the rendered answer instead of the full JSON result.")
    args = ap.parse_args()
    if args.status:
        print(json.dumps(load_authority_status(ROOT), ensure_ascii=False, indent=2))
        return 0
    if not args.question:
        ap.error("provide a rules question or use --status")
    engine = RulesEngine(ROOT, require_current_authority=not args.allow_incomplete_authority)
    result = engine.ask(" ".join(args.question))
    if args.compact:
        print(result.get("answer") or "")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=lambda x: getattr(x, "value", str(x))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
