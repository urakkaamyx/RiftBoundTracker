from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any


class Truth(str, Enum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"


@dataclass
class Fact:
    name: str
    value: Truth
    source: str
    confidence: str = "explicit"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


CARD_NAME_STRIP_RE = re.compile(r"\s+\((?:Alternate Art|Overnumbered|Signature|Metal|Showcase|Launch Exclusive|Ultimate|Promo[^)]*)\)\s*$", re.I)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower().replace("’", "'"))


def _name_search_key(s: str) -> str:
    s = _norm(s)
    s = re.sub(r"[,\-–—]+", " ", s)
    s = re.sub(r"[^a-z0-9'!]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def detect_named_cards(question: str, cards: dict[str, Any]) -> list[dict[str, Any]]:
    # Card recognition is punctuation-insensitive but not fuzzy-edit-distance matching.
    # Candidates are considered longest-name-first.  A shorter card name is suppressed
    # only when every occurrence is contained inside an already accepted longer card
    # span (for example ``Vilemaw`` inside ``Vilemaw's Lair``).  If both names are
    # actually written at separate spans, both are retained.
    q = _name_search_key(question)
    matches: list[dict[str, Any]] = []
    occupied: list[tuple[int, int]] = []
    candidates = sorted(
        cards["cards"],
        key=lambda c: len(_name_search_key(CARD_NAME_STRIP_RE.sub("", c.get("name") or ""))),
        reverse=True,
    )
    seen = set()
    for c in candidates:
        name = c.get("name") or ""
        base_name = CARD_NAME_STRIP_RE.sub("", name)
        key = _name_search_key(base_name)
        if len(key) < 3:
            continue
        pattern = re.compile(r"(?:^| )(" + re.escape(key) + r"(?:\'s)?)(?= |$)")
        spans = [m.span(1) for m in pattern.finditer(q)]
        if not spans:
            continue
        available = [sp for sp in spans if not any(sp[0] < b and a < sp[1] for a, b in occupied)]
        if not available:
            continue
        dedupe = (key, _norm(c.get("effectiveText") or ""), c.get("type"))
        if dedupe in seen:
            continue
        seen.add(dedupe)
        matches.append(c)
        # Reserve every occurrence of the accepted longest identity so contained
        # shorter identities cannot claim the same player-written text.
        occupied.extend(spans)
    return matches[:10]


def extract_facts(question: str) -> list[Fact]:
    q = _norm(question)
    facts: dict[str, Fact] = {}

    def setf(name: str, value: Truth, source: str, confidence: str = "explicit") -> None:
        old = facts.get(name)
        if old and old.value != value:
            facts[name] = Fact(name, Truth.UNKNOWN, f"conflict: {old.source}; {source}", "conflict")
        else:
            facts[name] = Fact(name, value, source, confidence)

    if re.search(r"\bby default\b|\bdefault(?:ly)?\b", q):
        setf("query_scope_default_rules_only", Truth.TRUE, "question explicitly asks for the default rule")

    # Destination type for Unit play. Keep this distinct from a named card being at a Base.
    if re.search(r"\bplay(?:ing)? (?:a |the |my |your )?unit(?: directly)? (?:to|at|into) (?:my |your |the |a )?base\b|\bplay units? to (?:my |your |the |a )?base\b", q):
        setf("unit_play_destination_is_base", Truth.TRUE, "question states the Unit-play destination is a Base")
    if re.search(r"\bplay(?:ing)? (?:a |the |my |your )?unit(?: directly)? (?:to|at|into) (?:a |the )?battlefield\b|\bplay units? to battlefields?\b", q):
        setf("unit_play_destination_is_base", Truth.FALSE, "question states the Unit-play destination is a Battlefield")

    # Explicit special permission. This is deliberately narrow: absence of this phrase
    # is UNKNOWN, not FALSE, unless the question explicitly says no effect grants it.
    if re.search(r"\b(?:an?|the) (?:card |game )?effect (?:says|lets|allows|permits|grants|gives) .*?play .*?unit .*?(?:to|at|into) .*?battlefield\b|\bpermission to play .*?unit .*?(?:normally invalid|battlefield .*?don't control|battlefield .*?do not control)\b", q):
        setf("game_effect_grants_play_location_permission", Truth.TRUE, "question explicitly states a game effect grants the play-location permission")
    if re.search(r"\bno (?:card |game )?effect (?:allows|permits|grants|lets) .*?play\b|\bwithout (?:any )?(?:card |game )?effect (?:allowing|permitting|granting)\b", q):
        setf("game_effect_grants_play_location_permission", Truth.FALSE, "question explicitly states no game effect grants special play-location permission")

    # Battlefield control.
    if re.search(r"\b(?:battlefields?|bf) (?:that )?(?:i|you|we|they) control\b|\bmy controlled battlefields?\b|\bcontrolled battlefields?\b", q):
        setf("actor_controls_battlefield", Truth.TRUE, "question states the battlefield is controlled")
        setf("unit_controller_already_controls_battlefield", Truth.TRUE, "question states the destination battlefield is controlled")
    if re.search(
        r"\b(?:do not|don't|does not|doesn't) control (?:that |the )?battlefield\b"
        r"|\bbattlefields? (?:that )?(?:i|you|we|they) (?:do not|don't|does not|doesn't) control\b"
        r"|\buncontrolled battlefield\b",
        q,
    ):
        setf("actor_controls_battlefield", Truth.FALSE, "question states the battlefield is not controlled")
        setf("unit_controller_already_controls_battlefield", Truth.FALSE, "question states destination is not controlled")

    # Unit occupancy / last unit.
    if re.search(r"\blast unit(?: there| at (?:that|the) battlefield)? (?:dies|died|is killed|gets killed)\b|\bno units? (?:left|remain|remaining|there)\b", q):
        setf("actor_has_units_at_battlefield_after_event", Truth.FALSE, "question states the last/no unit remains at the battlefield")
    if re.search(r"\bstill (?:have|has) (?:a |one or more )?units? (?:there|at (?:that|the) battlefield)\b", q):
        setf("actor_has_units_at_battlefield_after_event", Truth.TRUE, "question states a unit remains")

    # Contested state.
    if "not contested" in q or "isn't contested" in q:
        setf("battlefield_already_contested", Truth.FALSE, "question states battlefield is not contested")
    elif re.search(r"\balready contested\b|\bis contested\b", q):
        setf("battlefield_already_contested", Truth.TRUE, "question states battlefield is contested")

    # State/timing. Do not infer Open merely from absence of combat/showdown.
    if re.search(r"\bopen state\b|\bneutral open\b|\bshowdown open\b", q):
        setf("turn_is_open_state", Truth.TRUE, "question explicitly states an Open State")
    no_combat = bool(re.search(r"\bno combat\b|\bnot in combat\b|\bno combat or showdown\b|\bno showdown or combat\b", q))
    no_showdown = bool(re.search(r"\bno showdown\b|\bnot in (?:a )?showdown\b|\bno combat or showdown\b|\bno showdown or combat\b", q))
    if not no_combat and re.search(r"\bduring combat\b|\bcombat (?:is )?(?:ongoing|in progress)\b", q):
        setf("combat_ongoing_at_battlefield", Truth.TRUE, "question explicitly states ongoing combat")
        setf("turn_is_open_state", Truth.FALSE, "ongoing combat is not an Open State", "derived")
    if not no_showdown and re.search(r"\bduring (?:a )?showdown\b|\bshowdown (?:is )?(?:ongoing|in progress)\b", q):
        setf("showdown_ongoing_at_battlefield", Truth.TRUE, "question explicitly states ongoing showdown")
    if no_combat:
        setf("combat_ongoing_at_battlefield", Truth.FALSE, "question states no combat")
    if no_showdown:
        setf("showdown_ongoing_at_battlefield", Truth.FALSE, "question states no showdown")

    # Cleanup/death/damage.
    if "cleanup" in q:
        setf("cleanup_occurs", Truth.TRUE, "question explicitly references cleanup")
    if re.search(r"\b(?:dies|died|killed|kill)\b", q):
        setf("unit_death_event", Truth.TRUE, "question contains a unit death/kill event")
    if re.search(r"\blethal damage\b", q):
        setf("unit_has_lethal_damage", Truth.TRUE, "question explicitly says lethal damage")
    # Damage prevention. Partial prevention must not be collapsed into "no damage dealt".
    # When the question provides both numbers, resolve the remaining amount deterministically.
    numeric_prevent = re.search(
        r"\bprevent(?:ed|s|ing)?\s+(\d+)\s+(?:of (?:the )?)?damage\s+(?:from|of)\s+(?:a |the )?(\d+)\s+damage\b",
        q,
    )
    if not numeric_prevent:
        numeric_prevent = re.search(r"\bprevent(?:ed|s|ing)?\s+(\d+)\s+of (?:the )?(\d+)\s+damage\b", q)
    if numeric_prevent:
        prevented = int(numeric_prevent.group(1))
        incoming = int(numeric_prevent.group(2))
        if prevented >= incoming:
            setf("damage_was_dealt", Truth.FALSE, f"numeric prevention removes all damage ({prevented} of {incoming})", "derived")
        else:
            setf("damage_was_dealt", Truth.TRUE, f"numeric prevention leaves damage remaining ({incoming - prevented} of {incoming})", "derived")
    elif re.search(
        r"\b(?:all|the full|the entire) (?:of the )?damage(?:\s+[^.?!,;]{0,80})?\s+(?:is|was|gets?|got)? ?prevented\b"
        r"|\bprevent(?:ed|s|ing)? (?:all|the full|the entire) (?:of the )?damage\b"
        r"|\bfully prevent(?:ed|s|ing)? (?:the )?damage\b"
        r"|\bno damage (?:is|was) dealt\b",
        q,
    ):
        setf("damage_was_dealt", Truth.FALSE, "question states all damage was prevented/not dealt")
    if re.search(r"\b(?:takes?|took|is dealt|was dealt) \d+ damage\b", q) and "damage_was_dealt" not in facts:
        setf("damage_was_dealt", Truth.TRUE, "question explicitly states damage was taken/dealt")


    # Binary board states used by deterministic Limited Action rulings.
    if re.search(r"\balready ready\b|\bis ready\b|\bcurrently ready\b", q):
        setf("unit_already_ready", Truth.TRUE, "question states the unit/object is already Ready")
    if re.search(r"\bnot ready\b|\bis exhausted\b|\bcurrently exhausted\b", q):
        setf("unit_already_ready", Truth.FALSE, "question states the unit/object is not Ready")
    if re.search(r"\balready exhausted\b|\bis exhausted\b|\bcurrently exhausted\b", q):
        setf("object_already_exhausted", Truth.TRUE, "question states the object is already Exhausted")
    if re.search(r"\bnot exhausted\b|\bis ready\b|\bcurrently ready\b", q):
        setf("object_already_exhausted", Truth.FALSE, "question states the object is not Exhausted")
    if re.search(r"\bas (?:an? )?cost\b|\bexhaust .*? to (?:activate|pay|use)\b|\bcost (?:is|includes) exhaust", q):
        setf("exhaust_is_cost", Truth.TRUE, "question states Exhaust is being paid as a cost")
    if re.search(r"\balready stunned\b|\bis stunned\b|\bcurrently stunned\b", q):
        setf("unit_already_stunned", Truth.TRUE, "question states the unit is already Stunned")
    if re.search(r"\bnot stunned\b|\bisn't stunned\b|\bis not stunned\b", q):
        setf("unit_already_stunned", Truth.FALSE, "question states the unit is not Stunned")

    # Chain / counter facts.
    if re.search(r"\b(?:spell|card|ability) (?:is|was|gets?|got) countered\b|\bcounter(?:ed|ing) (?:the |a |my |your |their )?(?:spell|card|ability)\b", q):
        setf("chain_item_countered", Truth.TRUE, "question states a card or ability is Countered")
    if re.search(r"\bnot countered\b|\bwasn't countered\b|\bwas not countered\b", q):
        setf("chain_item_countered", Truth.FALSE, "question states the chain item was not Countered")

    # Target legality at resolution.
    if re.search(r"\b(?:all|every) (?:of )?(?:the )?targets?(?: of [^,.?!;]{1,60})? (?:are|become|becomes|became|were|is) (?:illegal|invalid)\b|\bonly target(?: of [^,.?!;]{1,60})? (?:is|becomes|became|was) (?:illegal|invalid)\b", q):
        setf("all_targets_illegal_on_resolution", Truth.TRUE, "question states every target is illegal/invalid on resolution")
        setf("some_target_illegal_on_resolution", Truth.TRUE, "all targets illegal implies at least one illegal target", "derived")
    elif re.search(r"\b(?:a|one|some) targets? (?:is|becomes|became|was|are|were) (?:illegal|invalid)\b|\btarget leaves? (?:the )?board\b|\btarget is no longer (?:legal|valid)\b", q):
        setf("some_target_illegal_on_resolution", Truth.TRUE, "question states a target becomes illegal/invalid on resolution")
    if re.search(r"\bremaining target(?:s)? (?:is|are) (?:legal|valid)\b|\bsome targets? remain (?:legal|valid)\b|\banother target remains? (?:legal|valid)\b", q):
        setf("some_targets_remain_legal_on_resolution", Truth.TRUE, "question states at least one target remains legal")

    # Recall semantics.
    if re.search(r"\brecall(?:ed|ing|s)?\b", q):
        setf("action_is_recall", Truth.TRUE, "question explicitly refers to a Recall")

    # Scoring facts. These are intentionally literal; absence remains UNKNOWN.
    if re.search(r"\bgain(?:ed|ing|s)? control of (?:a |the )?battlefield\b", q):
        setf("gains_control_of_battlefield", Truth.TRUE, "question states battlefield control is gained")
    if re.search(r"\b(?:have|has|had) not (?:yet )?scored (?:that |the )?battlefield this turn\b|\bhaven't scored (?:that |the )?battlefield this turn\b|\bhasn't scored (?:that |the )?battlefield this turn\b|\bbattlefield (?:that )?(?:i|you|we|they) haven't scored this turn\b|\bbattlefield (?:that )?(?:i|you|we|they) have not scored this turn\b", q):
        setf("battlefield_already_scored_this_turn", Truth.FALSE, "question states the battlefield has not been scored this turn")
    if re.search(r"\balready scored (?:that |the )?battlefield this turn\b|\bhave scored (?:that |the )?battlefield this turn\b|\b(?:i|you|we|they) already scored (?:it|that battlefield|the battlefield) this turn\b|\bbattlefield (?:that )?(?:i|you|we|they) already scored this turn\b", q):
        setf("battlefield_already_scored_this_turn", Truth.TRUE, "question states the battlefield was already scored this turn")
    if re.search(r"\bduring (?:my |your |the )?beginning phase\b", q):
        setf("during_beginning_phase", Truth.TRUE, "question explicitly states the Beginning Phase")
    if re.search(r"\bmaintain(?:s|ed|ing)? control of (?:a |the )?battlefield\b|\bstill control (?:a |the )?battlefield\b", q):
        setf("maintains_control_of_battlefield", Truth.TRUE, "question states control of the battlefield is maintained")

    # Card location/context.
    if re.search(r"\bhidden (?:card|spell|unit|gear)\b|\bcard (?:is )?hidden\b|\bface ?down at (?:a |the )?battlefield\b", q):
        setf("hidden_card_at_battlefield", Truth.TRUE, "question states a hidden/facedown card is at a battlefield")
    if re.search(r"\bwhile .* at (?:a |the )?battlefield\b|\bis at (?:a |the )?battlefield\b", q):
        setf("named_card_at_battlefield", Truth.TRUE, "question places the named card at a battlefield")
    if re.search(r"\b(?:is|while|sits?|stays?) (?:at|in) (?:my |your |the |a )?base\b", q):
        setf("named_card_at_battlefield", Truth.FALSE, "question places the named card at a Base rather than a battlefield")

    # Targeting / Untargetable timing. These facts distinguish legality at finalization
    # from a target becoming illegal only after it was legally chosen.
    if re.search(r"\bplay(?:ing)? (?:a |the )?unit .*?(?:to|at) (?:a |the )?battlefield\b", q) and re.search(r"\btarget(?:s|ed|ing)? (?:the |that )?battlefield\b|\bdoes .* battlefield .* target\b", q):
        setf("battlefield_mention_is_play_location_only", Truth.TRUE, "question asks whether a Battlefield used only as the destination/restriction of Play is targeted")
    if re.search(r"\b(?:already |currently )?untargetable\b|\bcan(?:not|'t) be chosen by\b", q) and not re.search(r"\bbecomes? untargetable .*after|after .*target.*untargetable", q):
        setf("target_untargetable_at_choice", Truth.TRUE, "question states the object is Untargetable when targets would be chosen")
    if re.search(r"\bafter (?:i |you |they |we )?(?:target|choose|chose|targeted).*?(?:becomes?|is made) untargetable\b|\bbecomes? untargetable after (?:being )?(?:targeted|chosen)\b|\bbecomes? untargetable after (?:i |you |they |we )?(?:target|choose|chose|targeted)\b", q):
        setf("target_became_untargetable_after_targeted", Truth.TRUE, "question states the object became Untargetable after becoming a target")

    # Linked-instruction failure modes. Current official FAQ distinguishes mistargeted
    # (ignored) instructions from prevented/replaced/impossible (negated) instructions.
    linked_context = bool(re.search(r"\blinked instruction|linked ability|controller (?:still )?draw|later instruction|next instruction\b", q))
    if linked_context and re.search(r"\btarget (?:becomes?|became|is|was) (?:illegal|invalid)|target leaves? (?:the )?board|mistarget", q):
        setf("earlier_linked_instruction_mistargeted", Truth.TRUE, "question states the earlier linked instruction mistargets")
    if linked_context and re.search(r"\bcan(?:not|'t) be killed|cannot be killed|prevent(?:ed|s|ing)?|already stunned|already ready|already exhausted|negated\b", q):
        setf("earlier_linked_instruction_negated", Truth.TRUE, "question states the earlier instruction is prevented/impossible rather than mistargeted")
    if linked_context and re.search(r"\breplac(?:e|es|ed|ing) (?:the |that )?(?:kill|stun|event|action|instruction)\b|\b(?:kill|stun)(?: action)? (?:is |was |gets? )?replaced\b|\b(?:kill|stun) .* instead\b", q):
        setf("earlier_linked_instruction_replaced", Truth.TRUE, "question states the earlier linked action/event is replaced")
        setf("earlier_linked_instruction_negated", Truth.TRUE, "replacement means the original instructed event is not performed as written", "derived")
    if linked_context and re.search(r"\blater instruction .*?(?:that |the )?(?:kill|stun|move|action)|\bnext instruction .*?that (?:kill |stun |move )?action\b|\bdirectly references? (?:that |the )?(?:kill |stun |move )?action\b|\bdirectly references? (?:the )?(?:kill|stun|move)\b", q):
        setf("later_linked_instruction_directly_references_action", Truth.TRUE, "question states the later linked instruction directly references the earlier Game Action")

    # Replacement ordering / simultaneous events.
    if re.search(r"\b(?:two|multiple|more than one) replacement effects? .*?(?:same|one) event\b|\bwhich replacement effect (?:applies|happens) first\b|\b(?:two|multiple|more than one) replacement effects? apply to .*?(?:who|which).*?order\b", q):
        setf("multiple_replacement_effects_same_event", Truth.TRUE, "question states or necessarily frames multiple Replacement Effects as competing for one event")
    if re.search(r"\b(?:my|your|their) (?:unit|gear|card|permanent|object)\b", q) and "replacement" in q:
        setf("affected_object_has_controller", Truth.TRUE, "question identifies a controlled object as the affected object")
    if re.search(r"\breplacement effects? (?:apply|applying) to (?:me|a player|the player)|\bplayer being acted on\b", q):
        setf("affected_entity_is_player", Truth.TRUE, "question states a player is the entity being acted on")
    if re.search(r"\buncontrolled battlefield\b", q) and "replacement" in q:
        setf("affected_object_uncontrolled_battlefield", Truth.TRUE, "question states the affected object is an Uncontrolled Battlefield")
    if "simultaneous" in q and "replacement" in q and re.search(r"\bevents?\b", q):
        setf("simultaneous_replaceable_events", Truth.TRUE, "question states multiple replaceable events occur simultaneously")

    # Combat damage replacement timing.
    if "combat damage" in q and re.search(r"\breplacement|prevent|increase|modify\b", q):
        setf("combat_damage_replacement_effect_applies", Truth.TRUE, "question asks about a Replacement Effect that would modify resulting combat damage")

    # Play / Finalize / Resolve terminology.
    if re.search(r"\bfinalized|finalization\b", q):
        setf("chain_item_was_finalized", Truth.TRUE, "question explicitly states the card/item was Finalized")
    non_triggered_play_check = bool(re.search(r"\bnon-triggered\b|\bnontriggered\b|\bchecks? whether .* (?:was|were|has been|have been)? ?played\b|\blegion\b", q))
    if non_triggered_play_check:
        setf("played_check_is_non_triggered", Truth.TRUE, "question refers to a non-triggered check of whether a card was played")
    if not non_triggered_play_check and re.search(r"\btriggered ability|\bwhen (?:you |i |they )?play|\btriggers? when .* played\b", q):
        setf("played_check_is_triggered", Truth.TRUE, "question refers to a triggered ability checking cards being played")
    if re.search(r"\b(?:card|spell|unit|gear) (?:resolves?|resolved)\b|\bafter .* resolves?\b", q):
        setf("card_resolved", Truth.TRUE, "question states that the card resolves")

    # Trigger-condition referents.
    if re.search(r"\btrigger condition\b", q) and re.search(r"\binformation|value|amount|which|what|refer", q):
        setf("trigger_uses_information_from_condition", Truth.TRUE, "question asks about information referenced from a trigger condition")

    # Copy/layer facts.
    if re.search(r"\bcopy|copies|copied|copying\b", q):
        setf("copy_effect_applied", Truth.TRUE, "question explicitly involves a copy effect")
    copied_object_has_temp = bool(
        re.search(r"\bcopy(?:ing)? (?:an? |the )?(?:empowered|buff(?:ed)?|temporary)\b", q)
        or re.search(r"\bcopy(?:ing)? .*?(?:unit|object).*?(?:that |which )?(?:has|with|is) .*?(?:empowered|buff(?:ed)?|temporary|[+-]\d+\s*might)\b", q)
        or re.search(r"\bsource (?:unit|object).*?(?:has|with|is) .*?(?:empowered|buff(?:ed)?|temporary|[+-]\d+\s*might)\b", q)
    )
    if copied_object_has_temp:
        setf("copy_source_has_temporary_modification", Truth.TRUE, "question identifies temporary status/modification on the copied object")
    if re.search(r"\b(?:copying|receiving|equipped|my) (?:unit|object).*?(?:already |currently )?(?:has|with) [+-]?\d+ .*might|\bhas [+-]\d+ \[?m\]? .*before .*copy\b", q):
        setf("copy_receiver_has_existing_temporary_might_mod", Truth.TRUE, "question states the receiving object already has a temporary Might modification")
    if re.search(r"\b(?:moment|intermediate|briefly) .*?might\b|\bbecome(?:s)? \d+ .*?before .*?\d+\b", q) and re.search(r"\blayer|might|dragon form|arithmetic\b", q):
        setf("question_asks_intermediate_layer_state", Truth.TRUE, "question asks whether an intermediate layered value exists as a triggerable game state")

    # Deck Construction (Rule 103 family) - numeric quantity facts live in their own module
    # since they need cardinality parsing, not just boolean keyword regexes.
    from .deck_construction import deck_construction_facts
    for name, value, source in deck_construction_facts(q):
        setf(name, Truth.TRUE if value == "true" else Truth.FALSE, source)

    return list(facts.values())


def fact_map(facts: list[Fact]) -> dict[str, Truth]:
    return {f.name: f.value for f in facts}
