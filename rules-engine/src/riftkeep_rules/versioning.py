from __future__ import annotations

import hashlib
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any


def sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a or "", b or "", autojunk=False).ratio()


def _norm(rule: dict[str, Any]) -> str:
    return rule.get("normalizedText") or ""


def _major(rule: dict[str, Any]) -> str | None:
    return rule.get("majorSectionTitle")


def _new_internal_id(prefix: str, used: set[str], seed: str) -> str:
    base = f"{prefix}-NEW-{hashlib.sha1(seed.encode('utf-8')).hexdigest()[:10].upper()}"
    x = base
    i = 2
    while x in used:
        x = f"{base}-{i}"
        i += 1
    used.add(x)
    return x


def compare_rule_versions(old_doc: dict[str, Any], new_doc: dict[str, Any], stable_prefix: str = "RK-CR") -> dict[str, Any]:
    old = old_doc["rules"]
    new = new_doc["rules"]
    old_by_id = {r["ruleId"]: r for r in old}
    new_by_id = {r["ruleId"]: r for r in new}
    old_idx = {r["ruleId"]: i for i, r in enumerate(old)}
    new_idx = {r["ruleId"]: i for i, r in enumerate(new)}

    matches: dict[str, dict[str, Any]] = {}  # old rid -> match record
    used_new: set[str] = set()
    review: list[dict[str, Any]] = []

    # Pass 1: exact visible ID + exact normalized text.
    for rid, o in old_by_id.items():
        n = new_by_id.get(rid)
        if n and _norm(o) == _norm(n):
            matches[rid] = {"oldRuleId": rid, "newRuleId": rid, "matchType": "same_id_exact", "confidence": 1.0}
            used_new.add(rid)

    # Pass 2: exact normalized text moved/renumbered, unique among unmatched.
    old_texts: dict[str, list[str]] = {}
    new_texts: dict[str, list[str]] = {}
    for r in old:
        if r["ruleId"] not in matches:
            old_texts.setdefault(_norm(r), []).append(r["ruleId"])
    for r in new:
        if r["ruleId"] not in used_new:
            new_texts.setdefault(_norm(r), []).append(r["ruleId"])
    for text, old_ids in old_texts.items():
        new_ids = new_texts.get(text, [])
        if text and len(old_ids) == 1 and len(new_ids) == 1:
            oid, nid = old_ids[0], new_ids[0]
            matches[oid] = {"oldRuleId": oid, "newRuleId": nid, "matchType": "exact_text_renumbered", "confidence": 0.99}
            used_new.add(nid)

    # Pass 3: same visible ID with changed wording. Auto-accept only when the text still resembles the prior rule.
    for rid, o in old_by_id.items():
        if rid in matches:
            continue
        n = new_by_id.get(rid)
        if n and rid not in used_new:
            score = sim(_norm(o), _norm(n))
            if score >= 0.58:
                matches[rid] = {"oldRuleId": rid, "newRuleId": rid, "matchType": "same_id_text_changed", "confidence": round(score, 4)}
                used_new.add(rid)
            else:
                review.append({"type": "same_id_possible_repurpose", "oldRuleId": rid, "newRuleId": rid, "similarity": round(score, 4)})

    # Pass 4: high-confidence fuzzy renumber/move. Require strong score and a clear margin over runner-up.
    unmatched_old = [r for r in old if r["ruleId"] not in matches]
    unmatched_new = [r for r in new if r["ruleId"] not in used_new]
    for o in unmatched_old:
        candidates = []
        for n in unmatched_new:
            if n["ruleId"] in used_new:
                continue
            text_score = sim(_norm(o), _norm(n))
            if text_score < 0.65:
                continue
            major_bonus = 0.08 if _major(o) and _major(o) == _major(n) else 0.0
            # positional proximity is a weak signal only; renumbering can shift many rules.
            pos_delta = abs(old_idx[o["ruleId"]] / max(1, len(old)) - new_idx[n["ruleId"]] / max(1, len(new)))
            position_bonus = max(0.0, 0.05 * (1.0 - min(1.0, pos_delta * 5)))
            score = min(1.0, text_score * 0.87 + major_bonus + position_bonus)
            candidates.append((score, text_score, n["ruleId"]))
        if not candidates:
            continue
        candidates.sort(reverse=True)
        best = candidates[0]
        runner = candidates[1][0] if len(candidates) > 1 else 0.0
        if best[0] >= 0.90 and best[0] - runner >= 0.06:
            matches[o["ruleId"]] = {
                "oldRuleId": o["ruleId"],
                "newRuleId": best[2],
                "matchType": "fuzzy_renumbered_or_moved",
                "confidence": round(best[0], 4),
                "textSimilarity": round(best[1], 4),
            }
            used_new.add(best[2])
        elif best[0] >= 0.78:
            review.append({
                "type": "ambiguous_fuzzy_match",
                "oldRuleId": o["ruleId"],
                "bestNewRuleId": best[2],
                "score": round(best[0], 4),
                "runnerUpScore": round(runner, 4),
            })

    matched_new_to_old = {m["newRuleId"]: oid for oid, m in matches.items()}
    changes: list[dict[str, Any]] = []
    for oid, m in matches.items():
        o, n = old_by_id[oid], new_by_id[m["newRuleId"]]
        same_text = _norm(o) == _norm(n)
        same_id = oid == n["ruleId"]
        moved_section = _major(o) != _major(n) and _major(o) is not None and _major(n) is not None
        if same_text and same_id and not moved_section:
            kind = "UNCHANGED"
        elif same_text and not same_id:
            kind = "MOVED" if moved_section else "RENUMBERED"
        elif not same_text and same_id:
            kind = "TEXT_CHANGED"
        elif not same_text and not same_id:
            kind = "MOVED_AND_TEXT_CHANGED" if moved_section else "RENUMBERED_AND_TEXT_CHANGED"
        else:
            kind = "REVIEW_REQUIRED"
        changes.append({
            **m,
            "changeType": kind,
            "oldText": o.get("normativeText"),
            "newText": n.get("normativeText"),
            "oldMajorSection": _major(o),
            "newMajorSection": _major(n),
            "internalRuleId": o.get("internalRuleId"),
        })

    unmatched_old_ids = [r["ruleId"] for r in old if r["ruleId"] not in matches]
    unmatched_new_ids = [r["ruleId"] for r in new if r["ruleId"] not in matched_new_to_old]

    # Split/merge diagnostics are REVIEW_REQUIRED only, never auto-identity changes.
    for oid in unmatched_old_ids:
        o = old_by_id[oid]
        best = None
        for start in range(max(0, old_idx[oid] - 4), min(len(new), old_idx[oid] + 5)):
            for width in (2, 3):
                chunk = new[start : start + width]
                if len(chunk) != width or any(r["ruleId"] in matched_new_to_old for r in chunk):
                    continue
                joined = " ".join(_norm(r) for r in chunk)
                sc = sim(_norm(o), joined)
                if best is None or sc > best[0]:
                    best = (sc, [r["ruleId"] for r in chunk])
        if best and best[0] >= 0.86:
            review.append({"type": "possible_split", "oldRuleId": oid, "newRuleIds": best[1], "similarity": round(best[0], 4)})

    used_internal = {r.get("internalRuleId") for r in old if r.get("internalRuleId")}
    promoted_new = []
    for n in new:
        oid = matched_new_to_old.get(n["ruleId"])
        x = dict(n)
        if oid:
            x["internalRuleId"] = old_by_id[oid].get("internalRuleId")
            x["identityStatus"] = "inherited"
        else:
            x["internalRuleId"] = _new_internal_id(stable_prefix, used_internal, n["ruleId"] + "|" + _norm(n))
            x["identityStatus"] = "new_pending_review" if any(r.get("bestNewRuleId") == n["ruleId"] for r in review) else "new"
        promoted_new.append(x)

    for oid in unmatched_old_ids:
        changes.append({
            "oldRuleId": oid,
            "newRuleId": None,
            "changeType": "REMOVED_OR_REVIEW_REQUIRED",
            "internalRuleId": old_by_id[oid].get("internalRuleId"),
            "oldText": old_by_id[oid].get("normativeText"),
        })
    for nid in unmatched_new_ids:
        changes.append({
            "oldRuleId": None,
            "newRuleId": nid,
            "changeType": "ADDED_OR_REVIEW_REQUIRED",
            "internalRuleId": next(r["internalRuleId"] for r in promoted_new if r["ruleId"] == nid),
            "newText": new_by_id[nid].get("normativeText"),
        })

    counts: dict[str, int] = {}
    for c in changes:
        counts[c["changeType"]] = counts.get(c["changeType"], 0) + 1
    return {
        "oldRuleCount": len(old),
        "newRuleCount": len(new),
        "matchedRuleCount": len(matches),
        "unmatchedOldCount": len(unmatched_old_ids),
        "unmatchedNewCount": len(unmatched_new_ids),
        "changeCounts": counts,
        "changes": sorted(changes, key=lambda x: ((x.get("oldRuleId") or "9999"), (x.get("newRuleId") or "9999"))),
        "reviewRequired": review,
        "reviewRequiredCount": len(review),
        "promotedNewRules": promoted_new,
        "safeToAutoPromote": not unmatched_old_ids and not unmatched_new_ids and not review,
    }
