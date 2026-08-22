from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

# This is the certified release order. M16 update rehearsal/publish uses the same
# gate as milestone packaging instead of maintaining a weaker update-only suite.
TEST_SCRIPTS: tuple[str, ...] = (
    "tests/run_core_tests.py",
    "tests/run_definition_lookup_tests.py",
    "tests/run_regressions.py",
    "tests/run_language_tests.py",
    "tests/run_scenario_language_tests.py",
    "tests/run_scenario_model_tests.py",
    "tests/run_compiler_tests.py",
    "tests/run_proof_engine_tests.py",
    "tests/run_llm_interpretation_tests.py",
    "tests/run_llm_explanation_tests.py",
    "tests/run_gold_corpus_tests.py",
    "tests/run_card_interaction_tests.py",
    "tests/run_product_api_tests.py",
    "tests/run_ui_integration_tests.py",
    "tests/run_update_tests.py",
    "tests/run_update_automation_tests.py",
    "tests/run_production_hardening_tests.py",
    "tests/run_release_candidate_audit_tests.py",
    "tests/run_stable_release_tests.py",
)
FINAL_SCRIPTS: tuple[str, ...] = ("validate_all.py", "audit_project.py")
MAX_CAPTURE_CHARS = 24000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trim(text: str) -> str:
    if len(text) <= MAX_CAPTURE_CHARS:
        return text
    return text[-MAX_CAPTURE_CHARS:]


def _run(root: Path, argv: list[str], timeout: int) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    started = _now()
    try:
        proc = subprocess.run(
            argv,
            cwd=root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
        output = _trim(proc.stdout or "")
        return {
            "argv": argv,
            "startedAt": started,
            "finishedAt": _now(),
            "returnCode": proc.returncode,
            "passed": proc.returncode == 0,
            "output": output,
        }
    except subprocess.TimeoutExpired as exc:
        raw = exc.stdout or ""
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        return {
            "argv": argv,
            "startedAt": started,
            "finishedAt": _now(),
            "returnCode": None,
            "passed": False,
            "timedOut": True,
            "output": _trim(str(raw)),
        }


def run_release_gate(
    root: Path,
    *,
    include_build: bool = True,
    test_scripts: Iterable[str] | None = None,
    include_final_checks: bool = True,
    timeout_per_command: int = 240,
) -> dict[str, Any]:
    root = Path(root).resolve()
    commands: list[list[str]] = []
    if include_build:
        commands.append([sys.executable, "-m", "riftkeep_rules.build"])
    for script in tuple(test_scripts or TEST_SCRIPTS):
        commands.append([sys.executable, script])
    if include_final_checks:
        for script in FINAL_SCRIPTS:
            commands.append([sys.executable, script])

    rows: list[dict[str, Any]] = []
    passed = True
    for argv in commands:
        row = _run(root, argv, timeout_per_command)
        rows.append(row)
        if not row["passed"]:
            passed = False
            break
    result = {
        "schemaVersion": 1,
        "startedAt": rows[0]["startedAt"] if rows else _now(),
        "finishedAt": _now(),
        "passed": passed,
        "commandCount": len(commands),
        "completedCommandCount": len(rows),
        "commands": rows,
    }
    return result


def summarize_release_gate(result: dict[str, Any]) -> dict[str, Any]:
    failed = next((r for r in result.get("commands", []) if not r.get("passed")), None)
    return {
        "passed": bool(result.get("passed")),
        "commandCount": result.get("commandCount"),
        "completedCommandCount": result.get("completedCommandCount"),
        "failedCommand": (failed or {}).get("argv"),
        "failedOutput": (failed or {}).get("output"),
    }
