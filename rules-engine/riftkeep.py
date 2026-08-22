#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from riftkeep_rules.api_http import DEFAULT_HOST, DEFAULT_PORT, serve
from riftkeep_rules.product_api import ProductApiService
from riftkeep_rules.release_identity import PRODUCT_NAME, PRODUCT_VERSION, RELEASE_LINE, validate_stable_release_manifest
from riftkeep_rules.runtime_hardening import validate_runtime_artifacts


def run_self_check(root: Path = ROOT) -> dict:
    runtime = validate_runtime_artifacts(root)
    manifest = validate_stable_release_manifest(root)
    service_status = None
    service_error = None
    if runtime.get("passed"):
        try:
            service_status = ProductApiService(root).status()
        except Exception as exc:
            service_error = f"{type(exc).__name__}: {exc}"
    passed = bool(runtime.get("passed")) and bool(manifest.get("passed")) and service_status is not None
    return {
        "ok": passed,
        "product": {"name": PRODUCT_NAME, "version": PRODUCT_VERSION, "releaseLine": RELEASE_LINE},
        "runtime": runtime,
        "stableManifest": manifest,
        "service": service_status,
        "serviceError": service_error,
        "networkRequired": False,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=f"{PRODUCT_NAME} {PRODUCT_VERSION}")
    sub = ap.add_subparsers(dest="command", required=True)
    sc = sub.add_parser("self-check", help="Validate the offline runtime and Stable 1.0 manifest.")
    sc.add_argument("--compact", action="store_true", help="Emit compact JSON.")
    st = sub.add_parser("status", help="Print Product API status without starting an HTTP server.")
    st.add_argument("--compact", action="store_true", help="Emit compact JSON.")
    sv = sub.add_parser("serve", help="Serve the RiftKeep UI and Product API.")
    sv.add_argument("--host", default=DEFAULT_HOST)
    sv.add_argument("--port", type=int, default=DEFAULT_PORT)
    sv.add_argument("--allow-remote", action="store_true")
    args = ap.parse_args()

    if args.command == "serve":
        serve(ROOT, host=args.host, port=args.port, allow_remote=args.allow_remote)
        return 0
    if args.command == "self-check":
        payload = run_self_check(ROOT)
    else:
        try:
            payload = ProductApiService(ROOT).status()
        except Exception as exc:
            payload = {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
    print(json.dumps(payload, ensure_ascii=False, indent=None if args.compact else 2))
    return 0 if payload.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
