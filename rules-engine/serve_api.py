#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from riftkeep_rules.api_http import DEFAULT_HOST, DEFAULT_PORT, serve


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the RiftKeep Rules Product API.")
    ap.add_argument("--host", default=DEFAULT_HOST, help="Bind host (default: 127.0.0.1).")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Bind port (default: {DEFAULT_PORT}).")
    ap.add_argument("--allow-remote", action="store_true", help="Explicitly allow binding to a non-loopback address.")
    args = ap.parse_args()
    serve(ROOT, host=args.host, port=args.port, allow_remote=args.allow_remote)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
