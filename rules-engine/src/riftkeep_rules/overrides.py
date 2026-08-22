from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def compile_effective_rule_overrides(
    supplemental: dict[str, Any], core: dict[str, Any]
) -> dict[str, Any]:
    """Compile declarative current-overlay changes into an auditable artifact.

    The official text remains the authority. Catalog metadata only describes the
    machine-readable consequence of a specific evidence section. Every override
    must point at an existing source section and existing Core Rule IDs; invalid
    declarations are surfaced rather than silently applied.
    """
    core_ids = {str(r.get("ruleId")) for r in core.get("rules", [])}
    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    seen: set[str] = set()

    for doc in supplemental.get("documents", []):
        for raw in doc.get("effectiveOverrides") or []:
            oid = str(raw.get("id") or "").strip()
            if not oid:
                errors.append({"evidenceId": doc.get("evidenceId"), "reason": "missing_override_id"})
                continue
            if oid in seen:
                errors.append({"overrideId": oid, "reason": "duplicate_override_id"})
                continue
            seen.add(oid)
            missing_rules = [str(r) for r in raw.get("overriddenRuleIds") or [] if str(r) not in core_ids]
            if missing_rules:
                errors.append({"overrideId": oid, "reason": "unknown_core_rule_ids", "ruleIds": missing_rules})
                continue
            records.append({
                "overrideId": oid,
                "kind": raw.get("kind"),
                "target": raw.get("target"),
                "value": raw.get("value"),
                "statement": raw.get("statement"),
                "scope": raw.get("scope"),
                "overriddenRuleIds": [str(r) for r in raw.get("overriddenRuleIds") or []],
                "sourceEvidenceId": doc.get("evidenceId"),
                "sourceId": doc.get("sourceId"),
                "sourceContentHash": doc.get("contentHash"),
                "sourceSnapshotSha256": doc.get("snapshotSha256"),
                "sourceUrl": doc.get("sourceUrl"),
                "effectiveFrom": doc.get("effectiveFrom"),
                "authority": doc.get("authority"),
            })

    return {
        "schemaVersion": 1,
        "generatedAt": _utc_now(),
        "recordCount": len(records),
        "valid": not errors,
        "errors": errors,
        "overrides": records,
    }
