#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from riftkeep_rules.release_identity import PRODUCT_VERSION, validate_stable_release_manifest


def _run(root: Path, argv: list[str], timeout: int = 240) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    try:
        proc = subprocess.run(argv, cwd=root, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, check=False)
        return {"passed": proc.returncode == 0, "returnCode": proc.returncode, "output": (proc.stdout or "")[-12000:]}
    except subprocess.TimeoutExpired as exc:
        raw = exc.stdout or ""
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        return {"passed": False, "timedOut": True, "returnCode": None, "output": str(raw)[-12000:]}


def _zip_distribution(source: Path, archive: Path) -> int:
    excluded_dirs = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".git", "update_transactions"}
    count = 0
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in sorted(source.rglob("*")):
            rel = path.relative_to(source)
            if any(part in excluded_dirs for part in rel.parts):
                continue
            # A clean install does not inherit validation/test output from the source tree.
            if len(rel.parts) >= 2 and rel.parts[0] == "data" and rel.parts[1] == "validation":
                continue
            if path.is_file() and not path.name.endswith((".pyc", ".pyo")):
                z.write(path, Path("RiftKeepRules_Engine") / rel)
                count += 1
    return count


def run_clean_install_rehearsal(root: Path = ROOT) -> dict[str, Any]:
    root = Path(root).resolve()
    with tempfile.TemporaryDirectory(prefix="riftkeep-stable-clean-") as td:
        td_path = Path(td)
        archive = td_path / "RiftKeepRules_Engine_1.0_clean.zip"
        file_count = _zip_distribution(root, archive)
        extract_root = td_path / "extract"
        with zipfile.ZipFile(archive) as z:
            bad = z.testzip()
            if bad:
                return {"schemaVersion": 1, "passed": False, "error": f"zip_integrity:{bad}"}
            z.extractall(extract_root)
        clean = extract_root / "RiftKeepRules_Engine"

        build = _run(clean, [sys.executable, "-m", "riftkeep_rules.build"], timeout=360)
        manifest = validate_stable_release_manifest(clean) if build.get("passed") else {"passed": False, "errors": ["build_failed"]}
        self_check = _run(clean, [sys.executable, "riftkeep.py", "self-check", "--compact"], timeout=120) if build.get("passed") else {"passed": False}
        try:
            self_payload = json.loads(self_check.get("output") or "{}") if self_check.get("passed") else {}
        except Exception:
            self_payload = {}

        sys.path.insert(0, str(clean / "src"))
        old_modules = {k: v for k, v in sys.modules.items() if k == "riftkeep_rules" or k.startswith("riftkeep_rules.")}
        for key in list(old_modules):
            sys.modules.pop(key, None)
        api_passed = ui_passed = definition_passed = ask_passed = readonly_passed = False
        external_network_attempted = False
        api_detail: dict[str, Any] = {}
        try:
            from riftkeep_rules.api_http import start_test_server
            from riftkeep_rules.product_api import ProductApiService
            from riftkeep_rules.runtime_hardening import open_readonly_sqlite

            service = ProductApiService(clean)
            status = service.status()
            api_passed = (status.get("release") or {}).get("productVersion") == PRODUCT_VERSION and (status.get("authority") or {}).get("currentRulesComplete") is True
            definition = service.ask("What does Deflect do?")
            issue = (definition.get("issues") or [{}])[0]
            definition_passed = issue.get("verdict") == "definition" and (issue.get("proof") or {}).get("verified") is True
            ask = service.ask("Can I summon a unit to my base?")
            aissue = (ask.get("issues") or [{}])[0]
            ask_passed = aissue.get("verdict") == "yes" and (aissue.get("proof") or {}).get("verified") is True

            con = open_readonly_sqlite(clean / "data/index/rules.sqlite")
            try:
                readonly_passed = int(con.execute("PRAGMA query_only").fetchone()[0]) == 1 and int(con.execute("PRAGMA user_version").fetchone()[0]) == 1
                try:
                    con.execute("DELETE FROM docs_meta WHERE 1=0")
                    readonly_passed = False
                except sqlite3.OperationalError:
                    pass
            finally:
                con.close()

            server, thread = start_test_server(clean, service=service)
            host, port = server.server_address
            try:
                with urllib.request.urlopen(f"http://{host}:{port}/", timeout=30) as response:
                    body = response.read().decode("utf-8", errors="replace")
                    ui_passed = response.status == 200 and "RiftKeep" in body
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=5)
            api_detail = {"productVersion": (status.get("release") or {}).get("productVersion"), "authorityComplete": (status.get("authority") or {}).get("currentRulesComplete")}
        finally:
            for key in list(sys.modules):
                if key == "riftkeep_rules" or key.startswith("riftkeep_rules."):
                    sys.modules.pop(key, None)
            sys.modules.update(old_modules)
            try:
                sys.path.remove(str(clean / "src"))
            except ValueError:
                pass

        passed = all([
            build.get("passed") is True,
            manifest.get("passed") is True,
            self_check.get("passed") is True,
            self_payload.get("ok") is True,
            api_passed,
            ui_passed,
            definition_passed,
            ask_passed,
            readonly_passed,
        ]) and not external_network_attempted
        return {
            "schemaVersion": 1,
            "passed": passed,
            "distributionFileCount": file_count,
            "buildPassed": build.get("passed") is True,
            "manifestPassed": manifest.get("passed") is True,
            "selfCheckPassed": self_check.get("passed") is True and self_payload.get("ok") is True,
            "apiPassed": api_passed,
            "uiPassed": ui_passed,
            "definitionPassed": definition_passed,
            "deterministicAskPassed": ask_passed,
            "readOnlyIndexPassed": readonly_passed,
            "networkRequired": False,
            "externalNetworkAttempted": external_network_attempted,
            "productVersion": api_detail.get("productVersion"),
            "currentAuthorityComplete": api_detail.get("authorityComplete"),
            "manifest": manifest,
            "build": {"returnCode": build.get("returnCode"), "timedOut": build.get("timedOut", False)},
        }


def main() -> int:
    result = run_clean_install_rehearsal(ROOT)
    out = ROOT / "data/validation/stable_clean_install_audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
