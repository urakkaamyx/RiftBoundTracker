from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def build_compiler_metrics(root: Path, catalog: dict[str, Any], programs: dict[str, Any]) -> dict[str, Any]:
    adjudicator = (root / "src/riftkeep_rules/adjudicator.py").read_text(encoding="utf-8")
    hand_coded = sorted(set(re.findall(r'if\s+"([^"]+)"\s+in\s+obligations', adjudicator)))
    migrated = sorted(str(p.get("obligation")) for p in programs.get("programs", []) if p.get("valid") and p.get("executable"))
    meta = catalog.get("metadata") or {}
    return {
        "schemaVersion": 1,
        "semanticRuleCount": meta.get("ruleCount", 0),
        "conditionalRuleCount": meta.get("conditionalRuleCount", 0),
        "modalityCounts": meta.get("modalityCounts", {}),
        "effectTypeCounts": meta.get("effectTypeCounts", {}),
        "replacementTaggedRuleCount": (meta.get("effectTypeCounts") or {}).get("replacement", 0),
        "executableProgramCount": programs.get("validProgramCount", 0),
        "migratedAdjudicationFamilyCount": len(migrated),
        "migratedAdjudicationFamilies": migrated,
        "remainingHandCodedFamilyCount": len(hand_coded),
        "remainingHandCodedFamilies": hand_coded,
        "policy": "Coverage metrics distinguish structural semantic compilation from executable Rule Programs and remaining legacy adjudication families.",
    }
