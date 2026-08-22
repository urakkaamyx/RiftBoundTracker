#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from riftkeep_rules.audit import run_project_audit


def main() -> int:
    result = run_project_audit(ROOT)
    print(json.dumps({
        "passed": result["passed"],
        "criticalIssueCount": result["criticalIssueCount"],
        "warningCount": result["warningCount"],
        "warnings": result["warnings"],
        "report": str(ROOT / "data/validation/project_audit.json"),
    }, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
