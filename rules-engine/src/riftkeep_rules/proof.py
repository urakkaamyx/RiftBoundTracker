from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from .graph import classify_semantics
from .retrieval import expand_query


# Proof obligations are domain concepts, not hardcoded final answers.
# Each obligation identifies the authoritative rule families normally needed to establish that proposition.
OBLIGATION_FAMILIES: dict[str, dict[str, Any]] = {
    "unit_play_location": {"mustInclude": ["355.2", "355.2.a", "355.2.b"], "families": ["349", "355", "419"]},
    "contested_on_entry": {"mustInclude": ["190.3.a", "190.3.a.1"], "families": ["188", "190"]},
    "battlefield_control_loss": {"mustInclude": ["190.4.c", "323.6"], "families": ["188", "190", "318", "323"]},
    "hidden_lifecycle": {"mustInclude": ["811.1.b", "323.7"], "families": ["318", "323", "800", "811"]},
    "lethal_cleanup_death": {"mustInclude": ["323.5"], "families": ["318", "323"]},
    "deal_damage": {"mustInclude": ["417.1", "417.1.b"], "families": ["407", "417"]},
    "prevent_damage": {"mustInclude": ["437.2", "437.2.a", "437.4"], "families": ["407", "417", "437"]},
    "card_rule_precedence": {"mustInclude": ["002", "054", "054.1", "054.2"], "families": ["001", "050"]},
    "replacement_not_play": {"mustInclude": ["438", "438.1"], "families": ["407", "438"]},
    "discard_to_trash": {"mustInclude": ["422", "422.1", "422.1.a", "422.1.b"], "families": ["407", "422"]},
    "ready_state": {"mustInclude": ["415.1", "415.1.b", "415.1.c"], "families": ["407", "415"]},
    "exhaust_state": {"mustInclude": ["414.1", "414.1.b", "414.1.c", "414.4"], "families": ["407", "414"]},
    "stun_state": {"mustInclude": ["423.1", "423.1.a", "423.1.a.1"], "families": ["407", "423"]},
    "counter_resolution": {"mustInclude": ["425.1", "425.1.a", "425.1.a.1", "425.1.b", "425.1.c", "419.4.a.1"], "families": ["337", "419", "425"]},
    "mistarget_resolution": {"mustInclude": ["359.3.e.1", "359.3.e.2", "359.3.e.7", "359.3.e.8", "359.3.e.10"], "families": ["349", "355", "359"]},
    "recall_not_move": {"mustInclude": ["455", "456", "456.1", "456.3", "458.1"], "families": ["446", "454", "455", "456", "458"]},
    "conquer_scoring": {"mustInclude": ["469.1", "470", "471.2.a"], "families": ["188", "467", "469", "470", "471"]},
    "hold_scoring": {"mustInclude": ["469.2", "470", "471.2.b"], "families": ["188", "315", "467", "469", "470", "471"]},
    "targeting_permission_restriction": {"mustInclude": ["355.10", "355.10.b"], "families": ["349", "355"]},
    "untargetable_legality": {"mustInclude": ["355.8", "355.9", "355.9.b", "359.3.e.5", "757", "758", "758.1", "758.2"], "families": ["349", "355", "757", "758"]},
    "linked_instructions_current_faq": {"mustInclude": ["359.3.e.14", "359.3.e.14.a", "359.3.e.14.b"], "families": ["349", "359"], "officialEvidenceIds": ["O:vendetta-faq-2026-08-14:0035"]},
    "replacement_order": {"mustInclude": ["370.1", "372", "372.1", "372.2", "373", "373.1", "373.1.a"], "families": ["369", "370", "372", "373"]},
    "combat_replacement_assignment": {"mustInclude": ["465.2.c.1", "465.2.c.5"], "families": ["459", "465"]},
    "play_finalize_semantics": {"mustInclude": ["419.1", "419.4", "419.4.a", "419.4.a.1", "419.4.b", "425.1"], "families": ["329", "337", "349", "419", "425"]},
    "trigger_snapshot": {"mustInclude": ["359.3.f.3", "383.2", "383.2.c"], "families": ["359", "379", "383"]},
    "copy_effect_semantics": {"mustInclude": ["477", "477.1", "477.1.b", "477.1.b.1", "477.1.b.1.a", "477.1.b.1.b", "477.3"], "families": ["473", "477"], "officialEvidenceIds": ["O:vendetta-faq-2026-08-14:0009"]},
    "layer_intermediate_state": {"mustInclude": ["477", "477.1", "477.3"], "families": ["473", "477"], "officialEvidenceIds": ["O:vendetta-faq-2026-08-14:0030"]},
    "copy_might_current_faq": {"mustInclude": ["477", "477.1", "477.1.a.1", "477.1.b", "477.1.b.1", "477.1.b.1.a", "477.1.b.1.b"], "families": ["473", "477"], "officialEvidenceIds": ["O:vendetta-faq-2026-08-14:0030"]},
    "flow_leave_chain_current_faq": {"mustInclude": ["829", "829.1.b", "829.1.b.1"], "families": ["367", "389", "829"], "officialEvidenceIds": ["O:vendetta-faq-2026-08-14:0002"]},
    "replacement_chosen_event": {"mustInclude": ["370.1", "370.1.b"], "families": ["367", "370"], "officialEvidenceIds": ["O:vendetta-faq-2026-08-14:0004"]},
    "replacement_inherits_modifiers": {"mustInclude": ["375"], "families": ["367", "375"], "officialEvidenceIds": ["O:vendetta-faq-2026-08-14:0005"]},
    "replacement_missing_counter_event": {"mustInclude": ["370.1", "370.1.c", "425.1"], "families": ["367", "370", "425"], "officialEvidenceIds": ["O:vendetta-faq-2026-08-14:0006"]},
    "rebuttal_remake_choices": {"mustInclude": ["355.15"], "families": ["349", "355", "750"], "officialEvidenceIds": ["O:vendetta-faq-2026-08-14:0008"]},
    "attach_replacement_sequence": {"mustInclude": ["369.1", "370.1.a.2", "370.1.b.1", "434"], "families": ["367", "370", "434"], "officialEvidenceIds": ["O:vendetta-faq-2026-08-14:0010"]},
    "copied_ability_new_instance": {"mustInclude": ["477.1.b", "477.1.b.1"], "families": ["473", "477"], "officialEvidenceIds": ["O:vendetta-faq-2026-08-14:0011"]},
    "multi_type_reflexive_trigger": {"mustInclude": ["387.1.b"], "families": ["379", "387"], "officialEvidenceIds": ["O:vendetta-faq-2026-08-14:0013"]},
    "naming_rules": {"mustInclude": ["761", "761.1", "761.2", "762", "762.1", "762.2", "763"], "families": ["759", "761", "762", "763"], "officialEvidenceIds": ["O:vendetta-faq-2026-08-14:0015"]},
    "kayle_empowered_stacks": {"mustInclude": ["002", "441.1", "441.1.b", "441.1.c", "441.1.c.1"], "families": ["001", "441"], "officialEvidenceIds": ["O:vendetta-faq-2026-08-14:0016", "O:vendetta-faq-2026-08-14:0017"]},
    "finalize_vs_resolve_control": {"mustInclude": ["419.4", "419.4.a", "419.4.b"], "families": ["419"], "officialEvidenceIds": ["O:vendetta-faq-2026-08-14:0019"]},
    "swap_replacement_current_faq": {"mustInclude": ["370.1", "433", "433.1", "433.1.a"], "families": ["367", "370", "433"], "officialEvidenceIds": ["O:vendetta-faq-2026-08-14:0021"]},
    "replacement_missing_stun_event": {"mustInclude": ["370.1", "423.1.a.1"], "families": ["367", "370", "423"], "officialEvidenceIds": ["O:vendetta-faq-2026-08-14:0022"]},
    "replacement_missing_might_event": {"mustInclude": ["370.1", "477.3.b"], "families": ["367", "370", "477"], "officialEvidenceIds": ["O:vendetta-faq-2026-08-14:0023"]},
    "dependent_keyword_reference": {"mustInclude": ["727.1", "727.1.b", "727.1.b.1"], "families": ["725", "727"], "officialEvidenceIds": ["O:vendetta-faq-2026-08-14:0025"]},
    "competing_positive_play_requirements": {"mustInclude": ["355.2", "355.2.a", "355.2.b"], "families": ["349", "355"], "officialEvidenceIds": ["O:vendetta-faq-2026-08-14:0027"]},
    "cant_beats_can_play_location": {"mustInclude": ["054", "054.1", "054.2", "355.2.b", "369.3"], "families": ["050", "349", "355", "369"], "officialEvidenceIds": ["O:vendetta-faq-2026-08-14:0028"]},
    "legend_control_current_faq": {"mustInclude": ["188", "189"], "families": ["188"], "officialEvidenceIds": ["O:vendetta-faq-2026-08-14:0029"]},
    "invalid_other_base_play": {"mustInclude": ["355.2", "355.2.a", "359.2"], "families": ["349", "355", "359"], "officialEvidenceIds": ["O:vendetta-faq-2026-08-14:0031"]},
    "become_state_transition": {"mustInclude": ["124"], "families": ["124", "379"], "officialEvidenceIds": ["O:vendetta-faq-2026-08-14:0032"]},
    "ignore_deflect_scope": {"mustInclude": ["766", "767"], "families": ["766", "767", "809"], "officialEvidenceIds": ["O:vendetta-faq-2026-08-14:0033"]},
    "delayed_trigger_attribution": {"mustInclude": ["411.4", "411.5", "411.6", "428.5", "428.5.d"], "families": ["411", "428"], "officialEvidenceIds": ["O:vendetta-faq-2026-08-14:0034"]},
    # Deck Construction (Rule 103 family). See RiftKeep 1.0.1's Deck Construction Obligation
    # Integration Fix - promotes Rule 103 into the same executable obligation/proof system as
    # every other family here, instead of a parallel deck-answer subsystem.
    "champion_legend_count": {"mustInclude": ["103", "103.1"], "families": ["103"]},
    "main_deck_minimum": {"mustInclude": ["103.2"], "families": ["103"]},
    "same_name_copy_limit": {"mustInclude": ["103.2.b", "103.2.b.1", "103.2.b.2"], "families": ["103"]},
    "signature_limit": {"mustInclude": ["103.2.d", "103.2.d.1", "103.2.d.2", "103.2.d.3"], "families": ["103"]},
    "rune_deck_count": {"mustInclude": ["103.3", "103.3.a", "103.3.a.1"], "families": ["103"]},
    "battlefield_duplicate_limit": {"mustInclude": ["103.4", "103.4.c"], "families": ["103"]},
    "battlefield_count_requirement": {"mustInclude": ["103.4", "103.4.a"], "families": ["103"]},
    "attach_exhausted_state_legality": {"mustInclude": ["719.4", "434.2", "434.2.a"], "families": ["434", "716", "719"]},
}


def detect_obligations(issue: str, named_cards: list[dict[str, Any]] | None = None) -> list[str]:
    q = issue.lower().replace("’", "'")
    out: list[str] = []
    target_only_play_question = bool(re.search(r"\btarget(?:s|ed|ing)?\b", q) and re.search(r"\b(?:does|is|count|considered)\b", q) and not re.search(r"\b(?:can|may|valid|legal|allowed|bypass)\b", q))
    specific_other_base = bool(re.search(r"\bother player's base|opponent's base|base of (?:another|a different) player|base other than\b", q))
    specific_restriction_conflict = bool(re.search(r"\b(?:can only|can't|cannot|only be played|restriction)\b", q) and re.search(r"\b(?:override|permit|permission|allows?|can)\b", q))
    if re.search(r"\bplay(?:ing)?\b", q) and "unit" in q and ("battlefield" in q or "base" in q) and not target_only_play_question and not specific_other_base and not specific_restriction_conflict:
        out.append("unit_play_location")
    if "contested" in q:
        out.append("contested_on_entry")
    if "battlefield" in q and re.search(r"\b(?:lose|losing|lost|last unit|no units?)\b", q):
        out.append("battlefield_control_loss")
    if ("hidden" in q or "facedown" in q or "face down" in q) and ("battlefield" in q and re.search(r"\b(?:control|last unit|no units?|dies|died|cleanup|removed|stay)\b", q)):
        out.append("hidden_lifecycle")
    if re.search(r"\blethal damage\b", q):
        out.append("lethal_cleanup_death")
    if "damage" in q or re.search(r"\bdeal(?:t|ing)?\b", q):
        out.append("deal_damage")
    if ("damage" in q or "deal" in q) and re.search(r"\bprevent(?:ed|s|ing)?\b", q):
        out.append("prevent_damage")
    if named_cards and re.search(r"\b(?:can|can't|cannot|only|may|play|ready|move|target|stop|prevent|restrict|limit|allow|prohibit|forbid)\b", q):
        out.append("card_rule_precedence")
    if re.search(r"\breplac(?:e|es|ed|ing|ement)\b", q) and re.search(r"\bplay(?:ed|ing)?\b", q):
        out.append("replacement_not_play")
    if re.search(r"\bdiscard(?:ed|ing|s)?\b", q) and ("trash" in q or re.search(r"\bwhere .*discard", q)):
        out.append("discard_to_trash")
    if re.search(r"\bready|readied|readying\b", q) and re.search(r"\balready ready|ready again|becomes? ready|ready trigger|when .* ready\b", q):
        out.append("ready_state")
    if re.search(r"\bexhaust|exhausted|exhausting\b", q) and re.search(r"\balready exhausted|exhaust again|as (?:a )?cost|pay .*exhaust|\[e\]\b", q):
        out.append("exhaust_state")
    if re.search(r"\bstun|stunned|stunning\b", q) and re.search(r"\balready stunned|stun again|becomes? stunned|stun trigger|when .* stunned\b", q):
        out.append("stun_state")
    if re.search(r"\b(?:my|your|their|the|a|an) (?:spell|card|ability) (?:is|was|gets|got) countered\b|\bcounter(?:ed|ing) (?:the |a |my |your |their )?(?:spell|card|ability)\b", q):
        out.append("counter_resolution")
    linked_context = bool(re.search(r"\blinked instruction|linked ability|later linked|next linked\b", q))
    if not linked_context and "untargetable" not in q and re.search(r"\btarget|targets|targeted|mistarget\b", q) and re.search(r"\billegal|invalid|leaves? (?:the )?board|no longer|resolution|resolves?\b", q):
        out.append("mistarget_resolution")
    if re.search(r"\brecall(?:ed|ing|s)?\b", q) and re.search(r"\bmove|movement|trigger|prevent|damage|status\b", q):
        out.append("recall_not_move")
    if re.search(r"\bconquer(?:ed|ing|s)?\b|\bgain(?:ed|ing|s)? control\b", q) and "battlefield" in q and re.search(r"\bscore|scored|point|conquer\b", q):
        out.append("conquer_scoring")
    if re.search(r"\bhold|holding|held\b", q) and "battlefield" in q and re.search(r"\bscore|scored|point|hold\b", q):
        out.append("hold_scoring")
    if re.search(r"\btarget(?:s|ed|ing)?\b", q) and "battlefield" in q and re.search(r"\bplay(?:ing|ed)?\b", q) and re.search(r"\bdoes|is|count|target\b", q):
        out.append("targeting_permission_restriction")
    if re.search(r"\buntargetable\b|\bcan(?:not|'t) be chosen\b", q):
        out.append("untargetable_legality")
    if re.search(r"\blinked instruction|linked ability|controller (?:still )?draw|later instruction|next instruction\b", q):
        out.append("linked_instructions_current_faq")
    if (re.search(r"\b(?:two|multiple|more than one) replacement effects?\b|\border (?:the )?replacement effects?\b", q)
            or ("simultaneous" in q and "replacement" in q)):
        out.append("replacement_order")
    if "combat damage" in q and re.search(r"\breplacement|prevent|increase|modify|assignment\b", q):
        out.append("combat_replacement_assignment")
    if re.search(r"\bfinalized|finalization\b", q) or (re.search(r"\bcount(?:s|ed)? as played|considered played|when .*?play(?:ed)?\b", q) and re.search(r"\bcounter|trigger|non-triggered|check|resolv\b", q)):
        out.append("play_finalize_semantics")
    if re.search(r"\btrigger condition\b", q) and re.search(r"\binformation|checked|check|snapshot|changes?|resolution|resolve\b", q):
        out.append("trigger_snapshot")
    if re.search(r"\bcopy|copies|copied|copying\b", q) and (
        re.search(r"\bempowered|buff|temporary|status|modification\b", q)
        or (re.search(r"\btrait|traits\b", q) and "copyable" not in q)
        or ("might" in q and re.search(r"\btemporary|increase|decrease|[+-]\d+\b", q))
    ):
        out.append("copy_effect_semantics")
    if re.search(r"\blayer|layers\b", q) and re.search(r"\bintermediate|moment|before|trigger|might\b", q):
        out.append("layer_intermediate_state")
    if (
        re.search(r"\bcopy|copies|copied|copying\b", q) and re.search(r"\b(?:base|printed|copyable) might\b|\bmight (?:copy|copied|copyable)\b", q)
    ) or (
        "might" in q and re.search(r"\bcopyable trait|trait .*copyable|is .*copyable\b", q)
    ):
        out.append("copy_might_current_faq")
    if "flow" in q and re.search(r"\babandon|counter|leave(?:s|ing)? (?:the )?chain|return(?:ed)? to hand\b", q):
        out.append("flow_leave_chain_current_faq")
    if re.search(r"\breplacement|replaces?\b", q) and re.search(r"\bchosen (?:unit|target|object)\b", q) and re.search(r"\bother|all|multiple|several\b", q):
        out.append("replacement_chosen_event")
    if re.search(r"\breplacement|replaced|replaces\b", q) and re.search(r"\bminimum|min(?:imum)? of|inherit(?:s|ed)? .*modif|modified event\b", q):
        out.append("replacement_inherits_modifiers")
    if "abandon" in q and re.search(r"\bcan(?:not|'t) be countered|uncounterable|counter .* fail\b", q):
        out.append("replacement_missing_counter_event")
    if "rebuttal" in q and re.search(r"\bnew choices|remake|remaking|change (?:some|targets|modes)|keep .*choice|illegal choice\b", q):
        out.append("rebuttal_remake_choices")
    if re.search(r"\bshady spectacles|svellsongur\b", q) and re.search(r"\battach|attached|copy|trigger\b", q):
        out.append("attach_replacement_sequence")
    if re.search(r"\bcopied ability|copy of .*ability|ability again|new instance\b", q) and re.search(r"\bcopy|copied|shady spectacles|svellsongur\b", q):
        out.append("copied_ability_new_instance")
    if re.search(r"\bhwei|reflexive trigger|do the following\b", q) and re.search(r"\bmultiple types|two types|three types|both .*?types|both unit and gear|patched porobot|unit gear|spell unit\b", q):
        out.append("multi_type_reflexive_trigger")
    if re.search(r"\bname a card|naming a card|name a tag|naming .*tag|uniquely identif|card that doesn't exist|card that does not exist|valid card name|name of a card|description could refer to (?:two|multiple|more than one)\b", q):
        out.append("naming_rules")
    if "kayle" in q and re.search(r"\bempower|empowered|disempower\b", q):
        out.append("kayle_empowered_stacks")
    if "rebuttal" in q and re.search(r"\bgain(?:ed|ing)? control|who controlled|finalized|finalize|resolv", q) and (
        re.search(r"\blegion|battering ram|ravenbloom|played spell|finalized by\b", q)
        or re.search(r"\bdid (?:i|you|they|we) finaliz|who finaliz|count as .*finaliz", q)
    ):
        out.append("finalize_vs_resolve_control")
    if re.search(r"\bswap|switcheroo\b", q) and re.search(r"\breplacement|gangplank|might|increase|decrease\b", q):
        out.append("swap_replacement_current_faq")
    if re.search(r"\bgangplank\b", q) and re.search(r"\balready stunned|can't be stunned|cannot be stunned|stun .*replacement\b", q):
        out.append("replacement_missing_stun_event")
    if (
        re.search(r"\bgangplank\b", q) and re.search(r"\bstupefy|1 \[m\]|one might|-0|zero\b", q)
    ) or (
        re.search(r"\breplacement|replace", q) and re.search(r"\bstupefy|-0\s*(?:might|\[m\])|zero might|might-decrease event|might decrease event", q)
    ):
        out.append("replacement_missing_might_event")
    if re.search(r"\bdependent keyword|dependent ability|heimerdinger|jayce\b", q) and re.search(r"\binactive|reference|gain .*ability|empowered\b", q):
        out.append("dependent_keyword_reference")
    if re.search(r"\btemporal breach\b|\bcompeting .*play\b|\btwo (?:mandatory )?(?:positive )?.*locations\b|\bcontradictory requirements\b", q) and re.search(r"\bplay|location|base|battlefield\b", q):
        out.append("competing_positive_play_requirements")
    if re.search(r"\bperched grimwyrm|dragon roost\b", q) and re.search(r"\bcan(?:not|'t)|play|conquered|finaliz\b", q):
        out.append("cant_beats_can_play_location")
    if re.search(r"\bcontrol (?:my|your|a|the) legend|do i control .*legend|legend .*control\b", q):
        out.append("legend_control_current_faq")
    if re.search(r"\bother player's base|another player's base|opponent's base|base of (?:another|a different) player|base other than\b", q) and re.search(r"\bplay|played|unit|temporal breach\b", q):
        out.append("invalid_other_base_play")
    if re.search(r"\bbecome(?:s|ing)? \d+|become .* or more|becomes? .*state|maintain(?:s|ing)? .*state|already .* or more\b", q) and re.search(r"\btrigger|ability|renekton|become\b", q):
        out.append("become_state_transition")
    # "pay" was dropped from this trigger - the claim is specifically that ignoring Deflect for
    # one named action/spell doesn't carry over to a different one, not a general "must I pay
    # Deflect" question, but "pay" is common enough in ordinary Deflect cost questions ("do I
    # have to pay Deflect twice?", "does this make me pay Deflect?") that it fired for those too,
    # confirmed directly against real player questions where this claim's actual subject (an
    # explicit ignore-for-one-action instruction) was never mentioned at all.
    if "deflect" in q and re.search(r"\bignore|heisho\b", q):
        out.append("ignore_deflect_scope")
    # "kill" and bare "trigger" were dropped from the second clause - this claim is specifically
    # about delayed-triggered-ability Kill attribution, not "any Immortal Phoenix question that
    # mentions killing or triggering something" (which is nearly all of them, since Immortal
    # Phoenix's whole mechanic is being killed by a spell). "delayed trigger" was also dropped
    # from the second clause because it's already part of the first, so pairing it with itself
    # let any question that merely uses the phrase "delayed trigger" about a completely different
    # card match here. "attribut"/"responsib" mirror the actual claim text ("...can be
    # attributed the Kill action... Responsibility remains with the controller...").
    if re.search(r"\bimperial decree|immortal phoenix|delayed trigger(?:ed)?\b", q) and re.search(r"\battribut|responsib\b", q):
        out.append("delayed_trigger_attribution")
    if re.search(r"\battach(?:ing|ed)?\b|\bequip(?:ping|ped)?\b", q) and re.search(r"\bexhaust", q):
        out.append("attach_exhausted_state_legality")
    # Deck Construction (Rule 103 family) - kept in its own module since it needs numeric
    # quantity parsing, not just boolean keyword regexes. See RiftKeep 1.0.1's Deck Construction
    # Obligation Integration Fix.
    from .deck_construction import detect_deck_obligations
    out.extend(detect_deck_obligations(q))
    # preserve order, dedupe
    return list(dict.fromkeys(out))


def _token_set(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def select_decisive_rules(issue: str, evidence: list[dict[str, Any]], obligations: list[str], limit: int = 18) -> list[dict[str, Any]]:
    by_id = {r["ruleId"]: r for r in evidence}
    wanted: list[tuple[str, str]] = []
    for ob in obligations:
        for rid in OBLIGATION_FAMILIES.get(ob, {}).get("mustInclude", []):
            if rid in by_id:
                wanted.append((rid, f"proof_obligation:{ob}"))

    q_terms = set(expand_query(issue)["terms"])
    q_tokens = set()
    for t in q_terms:
        q_tokens |= _token_set(t)

    scored: list[tuple[float, str]] = []
    for r in evidence:
        toks = _token_set(r.get("normativeText") or "")
        overlap = len(q_tokens & toks)
        tags = classify_semantics(r.get("normativeText") or "")
        score = float(overlap)
        if "conditional" in tags:
            score += 0.5
        if "permission" in tags or "prohibition" in tags or "restriction" in tags or "requirement" in tags:
            score += 0.7
        if r.get("closureReason") == "seed":
            score += 0.6
        if r.get("exampleText") and not r.get("normativeText"):
            score -= 2.0
        scored.append((score, r["ruleId"]))
    scored.sort(key=lambda x: (-x[0], by_id[x[1]]["sequence"]))
    for score, rid in scored:
        if score <= 0:
            continue
        wanted.append((rid, "relevance"))

    out = []
    seen = set()
    for rid, reason in wanted:
        if rid in seen or rid not in by_id:
            continue
        seen.add(rid)
        x = dict(by_id[rid])
        x["selectionReason"] = reason
        x["semanticTags"] = classify_semantics(x.get("normativeText") or "")
        out.append(x)
        if len(out) >= limit:
            break
    return out


def plan_proof(issue: str, evidence: list[dict[str, Any]], named_cards: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    obligations = detect_obligations(issue, named_cards)
    decisive = select_decisive_rules(issue, evidence, obligations)
    have = {r["ruleId"] for r in evidence}
    missing = []
    for ob in obligations:
        for rid in OBLIGATION_FAMILIES[ob]["mustInclude"]:
            if rid not in have:
                missing.append({"obligation": ob, "ruleId": rid})
    return {
        "issue": issue,
        "obligations": obligations,
        "missingRequiredEvidence": missing,
        "evidenceCompleteForKnownObligations": not missing,
        "decisiveRules": decisive,
    }


def complete_known_obligation_evidence(core: dict[str, Any], evidence: list[dict[str, Any]], proof: dict[str, Any], max_rules: int = 180) -> list[dict[str, Any]]:
    """Add exact deterministic dependencies requested by known proof obligations.

    This is the first evidence-completeness loop: the proof planner can request exact
    authoritative rules that its compiled obligation definition requires. The rules
    are fetched from the canonical corpus, never invented by a model.
    """
    by_id = {r["ruleId"]: r for r in core["rules"]}
    out = [dict(r) for r in evidence]
    seen = {r["ruleId"] for r in out}
    queue: list[tuple[str, str]] = []
    for miss in proof.get("missingRequiredEvidence", []):
        rid = miss["ruleId"]
        if rid in by_id:
            queue.append((rid, f"required_by:{miss['obligation']}"))
    qi = 0
    while qi < len(queue) and len(out) < max_rules:
        rid, reason = queue[qi]
        qi += 1
        if rid in seen or rid not in by_id:
            continue
        seen.add(rid)
        r = dict(by_id[rid])
        r["closureReason"] = reason
        out.append(r)
        # Bring just the local clause bundle, not the whole major section.
        parent = r.get("parentRuleId")
        if parent and parent in by_id:
            queue.append((parent, f"parent_of_required:{rid}"))
        for sid in r.get("siblingRuleIds", []):
            if sid in by_id:
                queue.append((sid, f"sibling_of_required:{rid}"))
        for ref in r.get("resolvedCrossReferences", []):
            if ref in by_id:
                queue.append((ref, f"explicit_ref_from_required:{rid}"))
    return out
