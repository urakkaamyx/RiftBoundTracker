from __future__ import annotations

from typing import Any


def _label(verdict: str | None) -> str:
    return {
        "yes": "Yes",
        "no": "No",
        "conditional": "It depends",
        "remove_to_trash": "Remove it to its owner's Trash",
        "no_damage_dealt": "No - that damage was not dealt",
        "damage_dealt": "Yes - damage was still dealt",
        "restricted_to_base": "No - the restriction applies",
        "restriction_inactive": "The restriction is inactive",
        "definition": "Official rules",
        "no_on_this_sequence": "No on that sequence",
        "no_on_this_rule": "No under that rule",
        "resolves_no_effect": "It resolves, but that instruction has no effect",
        "partial_resolution": "It resolves on the remaining legal targets",
        "yes_by_effect_permission": "Yes",
        "cannot_target": "No - it is not a legal target",
        "mistargets_on_resolution": "It mistargets on resolution",
        "later_ignored": "No - the later linked instruction is ignored",
        "later_executes": "Yes - the later linked instruction still executes",
        "later_does_not_execute": "No - the dependent linked instruction does not execute",
        "controller_orders": "The affected object's controller chooses the order",
        "affected_player_orders": "The affected player chooses the order",
        "current_turn_player_orders": "The Current Turn Player chooses the order",
        "separate_events": "They are treated as separate events",
        "apply_during_assignment": "Apply it during combat damage assignment",
        "no_trigger": "No - the played-card trigger does not trigger",
        "counts_for_nontriggered_check": "Yes - it counts for the non-triggered check",
        "trigger_condition_satisfied": "Yes - the played-card trigger condition is satisfied",
        "snapshot_at_trigger": "Use the information from when the trigger condition was fulfilled",
        "temporary_mod_not_copied": "No - temporary status/modifications are not copied",
        "receiver_mod_remains": "Yes - the receiving object's existing temporary modification remains",
        "no_intermediate_trigger_window": "No - there is no intermediate trigger window",
        "might_is_copyable_current": "Yes - Might is currently a copyable trait",
        "flow_spell_banished": "It is banished",
        "only_qualifying_chosen_event_replaced": "Only the qualifying chosen-object event is replaced",
        "replacement_inherits_modifiers": "Yes - the replacement inherits the modification",
        "no_replacement_without_qualifying_event": "No - there is no qualifying event to replace",
        "unchanged_choices_must_be_legal": "No - unchanged choices must be legal when choices are remade",
        "may_keep_all_existing_choices": "Yes - if no new choices are made",
        "may_remake_any_number_of_choices": "You may remake any number of targets or modes",
        "attach_then_copy_not_simultaneous": "Attach happens first, then the copy/text event",
        "copied_ability_is_new_instance": "Yes - the copied ability is a new instance",
        "all_applicable_reflexive_triggers_created": "Create every applicable Reflexive Trigger",
        "cannot_name_nonexistent_object": "No - that object cannot be named",
        "unique_description_allowed": "Yes - an unambiguous unique description is allowed",
        "ambiguous_name_not_valid": "No - the description is ambiguous",
        "naming_rules": "Use the official naming rules",
        "remove_one_empowered_stack": "Remove one Empowered status",
        "ability_may_activate_but_no_additional_empower": "Yes - it may be activated, but no additional Empower happens",
        "kayle_empowered_stacks_to_three": "Kayle may have up to three Empowered statuses",
        "resolution_control_differs_from_finalizer": "Resolution control and Finalization ownership are checked separately",
        "swap_creates_independent_increase_and_decrease": "Swap creates separate increase and decrease effects",
        "no_stun_event_to_replace": "No - no Stun event was created to replace",
        "no_might_decrease_event_to_replace": "No - no Might-decrease event was created to replace",
        "inactive_dependent_ability_can_be_referenced": "Yes - the inactive Dependent Ability can still be referenced",
        "choose_one_positive_play_requirement": "Choose one mandatory positive play requirement",
        "restriction_beats_play_location_permission": "No - the restriction beats the permission",
        "yes_control_own_legend": "Yes - you control your own Legend",
        "cannot_play_to_other_players_base": "No - a Unit cannot be played to another player's Base",
        "requires_transition_into_state": "It must transition into that state",
        "deflect_ignored_only_for_specified_action": "Deflect is ignored only for the specified action",
        "kill_attribution_propagates_to_generating_spell": "Yes - the Kill attribution can propagate to the generating spell",
        "exactly_one_required": "Exactly 1 Champion Legend is required",
        "at_least_forty_required": "At least 40 cards is the Main Deck minimum",
        "chosen_champion_counts_toward_limit": "Yes",
        "up_to_three_allowed": "Up to 3 copies of the same named card is the limit",
        "up_to_three_total_required": "Up to 3 total Signature cards is the limit",
        "must_match_domain_identity": "Rune Cards must match your Champion Legend's Domain Identity",
        "exactly_twelve_required": "Exactly 12 Rune Cards is required",
    }.get(verdict or "", (verdict or "Undetermined").replace("_", " ").capitalize())


def _dedupe_evidence(outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    out = []
    for o in outcomes:
        card = o.get("cardEvidence")
        if card and card.get("evidenceId") not in seen:
            seen.add(card["evidenceId"])
            out.append({"kind": "card", **card})
        source = o.get("sourceEvidence")
        if source and source.get("evidenceId") not in seen:
            seen.add(source["evidenceId"])
            out.append({"kind": "official_source", **source})
        for source in o.get("additionalSourceEvidence", []) or []:
            if source and source.get("evidenceId") not in seen:
                seen.add(source["evidenceId"])
                out.append({"kind": "official_source", **source})
        for e in o.get("evidence", []):
            eid = e.get("evidenceId")
            if eid and eid not in seen:
                seen.add(eid)
                out.append({"kind": "rule", **e})
    return out


def render_answer(result: dict[str, Any], include_quotes: bool = True) -> str:
    """Render a ruling without allowing prose generation to alter the verdict.

    Rule/card quotations come directly from the canonical evidence objects.
    """
    lines: list[str] = []
    issues = result.get("issues", [])
    for idx, item in enumerate(issues, 1):
        ruling = item.get("ruling", {})
        outcomes = ruling.get("outcomes", [])
        prefix = f"{idx}. " if len(issues) > 1 else ""
        eff = ruling.get("effectiveVerdict")
        if eff:
            lines.append(f"{prefix}{_label(eff.get('verdict'))}. {eff.get('reason', '')}".strip())
        elif ruling.get("status") == "insufficient":
            lines.append(f"{prefix}I can't determine this from the currently compiled deterministic rules. {ruling.get('reason','')}".strip())
        elif outcomes:
            o = outcomes[0]
            lines.append(f"{prefix}{_label(o.get('verdict'))}. {o.get('claim','')}".strip())

        # Include additional independent propositions, but don't repeat a default proposition
        # that is explicitly superseded in the scenario.
        if not eff and len(outcomes) > 1:
            for o in outcomes[1:]:
                lines.append(f"   - {_label(o.get('verdict'))}: {o.get('claim','')}")
        elif eff and len(outcomes) > 1:
            for o in outcomes:
                if o.get("effectStatus") == "superseded_in_scenario":
                    lines.append(f"   The default rule would normally allow it: {o.get('claim','')}")

        clarifications = item.get("clarifyingQuestions") or []
        if clarifications:
            lines.append("   To decide this completely, I need:")
            for cq in clarifications:
                lines.append(f"   - {cq.get('question')}")

        if include_quotes and outcomes:
            ev = _dedupe_evidence(outcomes)
            for e in ev:
                if e["kind"] == "rule":
                    lines.append(f"   Rule {e['ruleId']}: \"{e['text']}\"")
                elif e["kind"] == "card":
                    lines.append(f"   {e['name']}: \"{e['text']}\"")
                else:
                    source_date = e.get("published") or e.get("effectiveFrom") or e.get("lastUpdated") or "unknown"
                    heading = f" — {e.get('heading')}" if e.get("heading") else ""
                    lines.append(f"   {e.get('title','Official source')}{heading} ({source_date}): {e.get('text','')}")
        if idx < len(issues):
            lines.append("")
    return "\n".join(lines).strip()


def verdict_label(verdict: str | None) -> str:
    """Public stable label used by backend-only explanation rendering."""
    return _label(verdict)


def _render_catalog_evidence(e: dict[str, Any]) -> str:
    kind = e.get("kind")
    if kind == "core_rule":
        return f"   Rule {e.get('ruleId')}: \"{e.get('text','')}\""
    if kind == "card_text":
        return f"   {e.get('name','Card')}: \"{e.get('text','')}\""
    source_date = e.get("published") or e.get("effectiveFrom") or "unknown"
    heading = f" — {e.get('heading')}" if e.get("heading") else ""
    return f"   {e.get('title','Official source')}{heading} ({source_date}): {e.get('text','')}"


def render_explanation_answer(result: dict[str, Any], payload: dict[str, Any]) -> str:
    """Render validated M11 prose while keeping conclusions/citations backend-owned."""
    parts = {str(x.get("issueId")): x for x in payload.get("parts", [])}
    issues = result.get("issues", [])
    lines: list[str] = []
    for idx, issue in enumerate(issues, 1):
        iid = f"I{idx}"
        part = parts.get(iid, {})
        ruling = issue.get("ruling", {}) or {}
        effective = ruling.get("effectiveVerdict") or {}
        verdict = effective.get("verdict")
        if verdict is not None:
            label = _label(verdict)
        elif ruling.get("status") == "insufficient":
            label = "I can't determine this from the verified evidence"
        else:
            label = _label(None)
        prefix = f"{idx}. " if len(issues) > 1 else ""
        explanation = str(part.get("explanation") or "").strip()
        lines.append(f"{prefix}{label}. {explanation}".strip())

        catalog = {str(e.get("evidenceId")): e for e in issue.get("evidenceCatalog", []) or [] if e.get("evidenceId")}
        seen: set[str] = set()
        for eid in part.get("citationIds", []) or []:
            eid = str(eid)
            if eid in seen or eid not in catalog:
                continue
            seen.add(eid)
            lines.append(_render_catalog_evidence(catalog[eid]))

        clarifications = issue.get("clarifyingQuestions") or []
        if clarifications:
            lines.append("   To decide this completely, I need:")
            for cq in clarifications:
                lines.append(f"   - {cq.get('question')}")
        if idx < len(issues):
            lines.append("")
    return "\n".join(lines).strip()
