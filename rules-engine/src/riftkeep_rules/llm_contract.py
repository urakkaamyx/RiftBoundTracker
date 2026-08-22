from __future__ import annotations

import re
from typing import Any

RULE_ID_LIKE = re.compile(r"\b\d{3}(?:\.(?:\d+|[a-z]))+\b", re.I)


def evidence_catalog(engine_result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for issue in engine_result.get("issues", []):
        # Preferred source: the sealed per-issue catalog built before adjudication.
        for e in issue.get("evidenceCatalog", []) or []:
            if e.get("evidenceId"):
                out[e["evidenceId"]] = e
        # Backward-compatible fallback for older deterministic result payloads.
        for outcome in issue.get("ruling", {}).get("outcomes", []):
            card = outcome.get("cardEvidence")
            if card:
                out[card["evidenceId"]] = card
            for e in outcome.get("evidence", []):
                out[e["evidenceId"]] = e
    return out


def validate_evidence_request(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    requests = payload.get("requests")
    if not isinstance(payload.get("complete"), bool):
        errors.append("complete must be boolean")
    if not isinstance(requests, list):
        return errors + ["requests must be an array"]
    if len(requests) > 8:
        errors.append("at most 8 evidence requests are allowed per completion iteration")
    for i, req in enumerate(requests):
        if not isinstance(req, dict):
            errors.append(f"requests[{i}] must be an object")
            continue
        query = str(req.get("query", ""))
        # The completion model asks for concepts/search language; it does not get to invent exact rule IDs.
        if RULE_ID_LIKE.search(query):
            errors.append(f"requests[{i}].query contains a rule-number-like token; request evidence by concept instead")
        if not query.strip():
            errors.append(f"requests[{i}].query is empty")
    return errors


def validate_adjudication(payload: dict[str, Any], allowed_evidence_ids: set[str], expected_issue_ids: set[str]) -> list[str]:
    errors: list[str] = []
    issues = payload.get("issues")
    if not isinstance(issues, list) or not issues:
        return ["issues must be a non-empty array"]
    seen_issues = set()
    for i, issue in enumerate(issues):
        iid = issue.get("issueId")
        if iid not in expected_issue_ids:
            errors.append(f"issues[{i}].issueId is unknown: {iid}")
        seen_issues.add(iid)
        status = issue.get("status")
        if status not in {"decided", "conditional", "insufficient"}:
            errors.append(f"issues[{i}].status is invalid")
        missing = issue.get("missingFacts") or []
        if status == "decided" and missing:
            errors.append(f"issues[{i}] is decided but still declares missingFacts")
        steps = issue.get("reasoningSteps") or []
        for j, step in enumerate(steps):
            ids = step.get("evidenceIds") or []
            if not ids:
                errors.append(f"issues[{i}].reasoningSteps[{j}] has no supporting evidence")
            for eid in ids:
                if eid not in allowed_evidence_ids:
                    errors.append(f"issues[{i}].reasoningSteps[{j}] cites unavailable evidence {eid}")
        for eid in issue.get("appliedEvidence") or []:
            if eid not in allowed_evidence_ids:
                errors.append(f"issues[{i}].appliedEvidence contains unavailable evidence {eid}")
        for rej in issue.get("rejectedEvidence") or []:
            eid = rej.get("evidenceId")
            if eid not in allowed_evidence_ids:
                errors.append(f"issues[{i}].rejectedEvidence contains unavailable evidence {eid}")
    missing_issues = expected_issue_ids - seen_issues
    if missing_issues:
        errors.append(f"adjudication omitted issues: {sorted(missing_issues)}")
    return errors


def validate_answer_draft(payload: dict[str, Any], adjudication: dict[str, Any], allowed_evidence_ids: set[str]) -> list[str]:
    errors: list[str] = []
    adjudicated = {x["issueId"]: x for x in adjudication.get("issues", [])}
    parts = payload.get("parts")
    if not isinstance(parts, list):
        return ["parts must be an array"]
    for i, part in enumerate(parts):
        iid = part.get("issueId")
        if iid not in adjudicated:
            errors.append(f"parts[{i}] has unknown issueId {iid}")
            continue
        expected = adjudicated[iid].get("verdict")
        if part.get("declaredVerdict") != expected:
            errors.append(f"parts[{i}] changed the adjudicated verdict ({part.get('declaredVerdict')} != {expected})")
        for eid in part.get("citationIds") or []:
            if eid not in allowed_evidence_ids:
                errors.append(f"parts[{i}] cites unavailable evidence {eid}")
        # Quotes are backend-rendered. Discourage model-supplied quoted rule/card text.
        prose = str(part.get("prose", ""))
        if re.search(r'[“"]\s*(?:Rule\s+\d{3}|Card text|[A-Z][^”"]{10,})', prose):
            errors.append(f"parts[{i}] appears to contain a generated quotation; use citationIds and let the backend render exact text")
    return errors
