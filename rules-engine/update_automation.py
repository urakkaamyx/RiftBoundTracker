#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from riftkeep_rules.update_automation import (
    approve_transaction,
    create_transaction,
    poll_registered_source,
    publish_transaction,
    rehearse_transaction,
    stage_transaction,
    transaction_status,
)


def emit(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main() -> int:
    ap = argparse.ArgumentParser(description="Transactional RiftKeep official-source update automation.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create", help="Create an immutable update transaction from a JSON specification.")
    c.add_argument("--spec", required=True, type=Path); c.add_argument("--transaction-id")
    s = sub.add_parser("stage", help="Detect/validate/diff candidates in an isolated worktree."); s.add_argument("--transaction", required=True)
    a = sub.add_parser("approve", help="Record explicit human review approval."); a.add_argument("--transaction", required=True); a.add_argument("--reviewer", required=True); a.add_argument("--notes")
    r = sub.add_parser("rehearse", help="Apply candidates in isolation and run the full release gate."); r.add_argument("--transaction", required=True)
    p = sub.add_parser("publish", help="Apply the exact rehearsed bundle to live, gate it again, rollback on failure."); p.add_argument("--transaction", required=True)
    st = sub.add_parser("status", help="Show transaction state."); st.add_argument("--transaction", required=True)
    po = sub.add_parser("poll", help="Fetch one registered allowlisted official source into a new immutable transaction."); po.add_argument("--source-id", required=True); po.add_argument("--timeout", type=int, default=30); po.add_argument("--transaction-id")
    args = ap.parse_args()
    try:
        if args.cmd == "create":
            spec = json.loads(args.spec.read_text(encoding="utf-8")); out = create_transaction(ROOT, spec, args.transaction_id)
        elif args.cmd == "stage": out = stage_transaction(ROOT, args.transaction)
        elif args.cmd == "approve": out = approve_transaction(ROOT, args.transaction, args.reviewer, args.notes)
        elif args.cmd == "rehearse": out = rehearse_transaction(ROOT, args.transaction)
        elif args.cmd == "publish": out = publish_transaction(ROOT, args.transaction)
        elif args.cmd == "status": out = transaction_status(ROOT, args.transaction)
        else: out = poll_registered_source(ROOT, args.source_id, timeout=args.timeout, transaction_id=args.transaction_id)
        emit(out); return 0
    except Exception as exc:
        emit({"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}); return 2


if __name__ == "__main__":
    raise SystemExit(main())
