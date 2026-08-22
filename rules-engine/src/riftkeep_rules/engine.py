from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .adjudicator import adjudicate_issue
from .proof import plan_proof, complete_known_obligation_evidence, OBLIGATION_FAMILIES
from .proof_engine import build_proof_trace
from .retrieval import decompose_question, retrieve_issue
from .scenario import detect_named_cards, extract_facts
from .scenario_language import analyze_scenario_language
from .scenario_model import build_scenario_model
from .card_interactions import build_card_interaction_context
from .card_interaction_executor import evaluate_card_interaction_execution, materialize_card_interaction_ruling
from .writer import render_answer
from .player_language import normalize_player_language
from .clarify import clarification_questions
from .concepts import find_concepts, build_definition_ruling, card_referenced_concepts, merge_concept_evidence
from .authority import load_authority_status
from .legality import adjudicate_legality
from .vocabulary import detect_game_actions
from .evidence import build_issue_evidence_catalog, rule_evidence
from .llm_interpretation import run_interpretation
from .llm_provider import JsonLlmProvider
from .llm_explanation import run_explanation


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


_OVERLAY_STOP = {
    "what", "when", "does", "do", "will", "can", "could", "would", "should",
    "the", "a", "an", "and", "or", "if", "then", "this", "that", "with", "from",
    "your", "my", "their", "they", "them", "unit", "card", "spell", "ability",
    "play", "played", "playing", "effect", "rules", "rule", "happen", "happens",
}


def _overlay_tokens(text: str) -> set[str]:
    return {
        t for t in re.findall(r"[a-z0-9][a-z0-9'’-]*", (text or "").casefold())
        if len(t) > 2 and t not in _OVERLAY_STOP
    }


def _overlay_phrase_match(issue: str, doc: dict[str, Any]) -> bool:
    """Conservative material-relevance gate for an uncompiled current overlay.

    A higher-precedence article should fail closed only when the player's situation
    actually reaches that ruling. Generic rule-number overlap is not enough.
    """
    q = " ".join((issue or "").casefold().replace("’", "'").split())
    phrases = list(doc.get("matchPhrases") or [])
    for raw in phrases:
        phrase = " ".join(str(raw).casefold().replace("’", "'").split())
        toks = [x for x in phrase.split() if x]
        if phrase and phrase in q:
            return True
        # Do not treat a short phrase as matched merely because its words occur
        # somewhere independently in the question (for example "copy Might").
        # For longer scenario anchors we retain a conservative all-token fallback.
        if len(toks) >= 3 and all(t in q for t in toks):
            return True
    # A catalogued section with explicit match phrases opted out of generic lexical
    # fallback.  This prevents adjacent FAQ examples from blocking one another.
    if phrases:
        return False
    # Future/unclassified sections get a conservative lexical anchor fallback.
    dq = _overlay_tokens(str(doc.get("question") or doc.get("heading") or ""))
    iq = _overlay_tokens(issue)
    if not dq or not iq:
        return False
    inter = dq & iq
    return len(inter) >= 3 and (len(inter) / max(1, min(len(dq), len(iq)))) >= 0.50


def _overlay_exact_question_match(issue: str, doc: dict[str, Any]) -> bool:
    def norm(text: str) -> str:
        value = (text or "").casefold().replace("’", "'")
        value = re.sub(r"[^a-z0-9' -]+", " ", value)
        return " ".join(value.split()).strip()
    dq = norm(str(doc.get("question") or ""))
    iq = norm(issue)
    return bool(dq and iq and dq == iq)


class RulesEngine:
    def __init__(self, root: Path, *, require_current_authority: bool = True, interpretation_provider: JsonLlmProvider | None = None, explanation_provider: JsonLlmProvider | None = None):
        self.root = root
        self.core = load_json(root / "data/canonical/core_rules.json")
        self.cards = load_json(root / "data/canonical/cards.json")
        self.semantic_ir = load_json(root / "data/canonical/semantic_ir.json")
        compiled_rule_catalog_path = root / "data/canonical/compiled_rule_catalog.json"
        self.compiled_rule_catalog = load_json(compiled_rule_catalog_path) if compiled_rule_catalog_path.exists() else {"rules": []}
        rule_programs_path = root / "data/canonical/rule_programs.json"
        self.rule_programs = load_json(rule_programs_path) if rule_programs_path.exists() else {"programs": []}
        supplemental_path = root / "data/canonical/supplemental_sources.json"
        self.supplemental = load_json(supplemental_path) if supplemental_path.exists() else {"documents": []}
        card_interaction_path = root / "data/canonical/card_interaction_catalog.json"
        self.card_interaction_catalog = load_json(card_interaction_path) if card_interaction_path.exists() else {"printings": [], "identities": [], "faqPrograms": []}
        card_interaction_program_path = root / "data/canonical/card_interaction_programs.json"
        self.card_interaction_programs = load_json(card_interaction_program_path) if card_interaction_program_path.exists() else {"programs": []}
        self.db = root / "data/index/rules.sqlite"
        self.authority_status = load_authority_status(root)
        self.require_current_authority = require_current_authority
        self.interpretation_provider = interpretation_provider
        self.explanation_provider = explanation_provider

    def ask(self, question: str) -> dict[str, Any]:
        llm_interpretation = run_interpretation(question, self.interpretation_provider).to_dict()
        interpretation = normalize_player_language(question)
        interpretation_text = interpretation["text"]
        issues = decompose_question(question)
        named_cards = detect_named_cards(question, self.cards)
        scenario_language = analyze_scenario_language(question, self.cards)
        scenario_model_language = scenario_language if interpretation_text == question else analyze_scenario_language(interpretation_text, self.cards)
        scenario_model = build_scenario_model(question, interpretation_text, self.cards, scenario_model_language)
        card_interaction_context = build_card_interaction_context(question, named_cards, scenario_model, self.card_interaction_catalog)
        card_interaction_execution = evaluate_card_interaction_execution(card_interaction_context, self.card_interaction_programs, self.card_interaction_catalog, len(issues))
        card_interaction_context["execution"] = card_interaction_execution
        card_interaction_context["appliesGameRules"] = bool(card_interaction_execution.get("supported") and card_interaction_execution.get("fullyCoversQuestion"))
        card_interaction_context["changesVerdict"] = bool(card_interaction_execution.get("supported") and card_interaction_execution.get("fullyCoversQuestion"))
        concepts = find_concepts(interpretation_text, self.semantic_ir)
        facts = extract_facts(interpretation_text)
        legality_ruling = adjudicate_legality(self.root, interpretation_text, named_cards)
        # A "conditional" legality ruling means a strong format keyword (e.g. "sanctioned")
        # was detected but no specific card/battlefield/legend subject could be resolved from it.
        # That is not evidence the question is actually about tournament legality - it can just as
        # easily be an ordinary Core Rules question that happens to share a word with a real
        # rules-concept name (e.g. "Explain Sanctioned Modes." shares "sanctioned" with rule 484,
        # a Core Rules concept, not a ban-list lookup). Only short-circuit into the format-legality
        # answer when it actually resolved something ("decided") or has a specific, informative
        # reason it couldn't ("insufficient" - the Rules Hub data itself is unavailable);
        # "conditional" falls through to normal Core adjudication instead of dead-ending on a
        # generic non-answer.
        if legality_ruling is not None and legality_ruling.get("status") != "conditional":
            result = {
                "question": question,
                "namedCards": [{"id": c["id"], "name": c["name"], "effectiveText": c.get("effectiveText")} for c in named_cards],
                "matchedConcepts": concepts,
                "facts": [f.to_dict() for f in facts],
                "mentionedGameActions": detect_game_actions(interpretation_text),
                "questionInterpretation": interpretation,
                "llmInterpretation": llm_interpretation,
                "scenarioLanguage": scenario_language,
                "scenarioModel": scenario_model,
                "cardInteractionContext": card_interaction_context,
                "clarifyingQuestions": ([{"source": "scenario_language", **cq} for cq in scenario_language.get("clarifyingQuestions", [])] + [{"source": "scenario_model", **cq} for cq in scenario_model.get("clarifyingQuestions", []) if cq.get("question") not in {x.get("question") for x in scenario_language.get("clarifyingQuestions", [])}]),
                "issues": [{"issue": question, "retrievalContext": question, "retrieval": {"queryExpansion": {}, "topHits": [], "evidenceRuleIds": [], "officialEvidence": []}, "evidenceCatalog": [], "proof": {"obligations": ["format_legality"], "missingRequiredEvidence": [], "evidenceCompleteForKnownObligations": True, "decisiveRuleIds": []}, "ruling": legality_ruling}],
                "enginePolicy": {"llmUsed": False, "llmUsedForAdjudication": False, "llmInterpretationProviderAttempted": llm_interpretation["providerAttempted"], "llmInterpretationAccepted": llm_interpretation["accepted"], "unknownConditionsAreGuessed": False, "scenarioAssumptionsGuessed": False, "cardInteractionContextAppliesGameRules": False, "quotesRenderedFromAuthoritativeEvidence": True},
                "authorityStatus": self.authority_status,
            }
            result["deterministicAnswer"] = render_answer(result, include_quotes=True)
            explanation_stage = run_explanation(result, self.explanation_provider).to_dict()
            result["llmExplanation"] = explanation_stage
            result["enginePolicy"]["llmUsedForExplanation"] = bool(explanation_stage.get("accepted"))
            result["enginePolicy"]["llmUsed"] = bool(explanation_stage.get("accepted"))
            result["answer"] = explanation_stage.get("renderedAnswer") or result["deterministicAnswer"]
            return result
        resolved = []
        all_clarifications: list[dict[str, Any]] = [{"source": "scenario_language", **cq} for cq in scenario_language.get("clarifyingQuestions", [])]
        known_clarification_questions = {x.get("question") for x in all_clarifications}
        for cq in scenario_model.get("clarifyingQuestions", []):
            if cq.get("question") not in known_clarification_questions:
                all_clarifications.append({"source": "scenario_model", **cq})
                known_clarification_questions.add(cq.get("question"))
        for issue_spec in issues:
            issue = issue_spec["text"]
            issue_interp = normalize_player_language(issue)
            retrieval_interp = normalize_player_language(issue_spec["retrievalQuery"])
            interpretation_issue = issue_interp["text"]
            retrieval_query = retrieval_interp["text"]
            packet = retrieve_issue(self.db, self.core, retrieval_query, top_k=30, closure_limit=90)
            issue_concepts = find_concepts(retrieval_query, self.semantic_ir)
            card_concepts = []
            for card in named_cards:
                card_concepts.extend(card_referenced_concepts(card, self.semantic_ir))
            # Dynamic evidence closure from the rulebook's compiled concept catalog.
            # This is independent of the hand-authored proof obligations below.
            concept_map = {c["conceptId"]: c for c in issue_concepts + card_concepts}
            evidence = merge_concept_evidence(self.core, packet["evidenceRules"], list(concept_map.values()))
            proof = plan_proof(interpretation_issue, evidence, named_cards)
            # Evidence completeness loop: deterministic proof obligations may request
            # exact missing dependencies from the canonical corpus, then re-plan.
            for _ in range(3):
                if not proof["missingRequiredEvidence"]:
                    break
                expanded = complete_known_obligation_evidence(self.core, evidence, proof)
                if len(expanded) == len(evidence):
                    break
                evidence = expanded
                proof = plan_proof(interpretation_issue, evidence, named_cards)
            # Deterministic proof obligations may require exact official-overlay evidence.
            # Add those known documents by stable evidence ID even when lexical BM25 did
            # not rank them highly enough; this is evidence closure, not a guessed ruling.
            official_docs = list(packet.get("officialEvidence", []))
            official_by_id = {str(d.get("evidenceId")): d for d in self.supplemental.get("documents", []) if d.get("evidenceId")}
            required_official_ids: list[str] = []
            for ob in proof.get("obligations", []):
                for eid in (OBLIGATION_FAMILIES.get(ob, {}).get("officialEvidenceIds") or []):
                    if eid not in required_official_ids:
                        required_official_ids.append(eid)
                    if eid in official_by_id and not any(x.get("evidenceId") == eid for x in official_docs):
                        official_docs.append(official_by_id[eid])
            packet["officialEvidence"] = official_docs

            interaction_outcome = None
            if card_interaction_execution.get("supported") and card_interaction_execution.get("fullyCoversQuestion"):
                interaction_outcome = next((x for x in card_interaction_execution.get("issueOutcomes", []) if int(x.get("issueIndex", -1)) == len(resolved)), None)
                if interaction_outcome is not None:
                    required_interaction_rules = {str(x) for x in interaction_outcome.get("requiredRuleIds", [])}
                    present_rule_ids = {str(x.get("ruleId")) for x in evidence}
                    for rule in self.core.get("rules", []):
                        rid = str(rule.get("ruleId"))
                        if rid in required_interaction_rules and rid not in present_rule_ids:
                            evidence.append(rule)
                            present_rule_ids.add(rid)
                    interaction_eid = str(card_interaction_execution.get("matchedEvidenceId") or "")
                    if interaction_eid in official_by_id and not any(x.get("evidenceId") == interaction_eid for x in official_docs):
                        official_docs.append(official_by_id[interaction_eid])
                    packet["officialEvidence"] = official_docs

            issue_evidence_catalog = build_issue_evidence_catalog(
                evidence, named_cards, official_docs
            )
            if interaction_outcome is not None:
                ruling = materialize_card_interaction_ruling(interpretation_issue, interaction_outcome, card_interaction_execution, issue_evidence_catalog)
            else:
                ruling = build_definition_ruling(interpretation_issue, self.core, find_concepts(interpretation_issue, self.semantic_ir)) or adjudicate_issue(interpretation_issue, proof, facts, named_cards, official_docs, self.rule_programs)
            active_overlay_ids = set(self.authority_status.get("activeOverlays") or [])
            decisive_rule_ids = {str(r.get("ruleId")) for r in proof.get("decisiveRules", []) if r.get("ruleId")}
            required_official_set = set(required_official_ids)
            relevant_overlay = []
            ruling_is_definition = any((o.get("verdict") == "definition") for o in (ruling.get("outcomes") or []))
            if ruling_is_definition:
                # Definition rulings are authoritative lookups, not inferred adjudication.
                # Their complete Core-rule basis must be present in the sealed evidence
                # catalog before M9 proof verification. Retrieval is allowed to be
                # narrower than a large definition family; proof verification is not.
                catalog_ids = {str(x.get("evidenceId")) for x in issue_evidence_catalog if x.get("evidenceId")}
                definition_rule_ids = {
                    str(ev.get("ruleId"))
                    for outcome in (ruling.get("outcomes") or [])
                    for ev in (outcome.get("evidence") or [])
                    if ev.get("ruleId")
                }
                if definition_rule_ids:
                    for core_rule in self.core.get("rules", []):
                        rid = str(core_rule.get("ruleId") or "")
                        eid = f"R:{rid}"
                        if rid in definition_rule_ids and eid not in catalog_ids:
                            issue_evidence_catalog.append(rule_evidence(core_rule))
                            catalog_ids.add(eid)
            for x in official_docs:
                if x.get("sourceId") not in active_overlay_ids:
                    continue
                eid = str(x.get("evidenceId") or "")
                if interaction_outcome is not None:
                    matched_interaction_eid = str(card_interaction_execution.get("matchedEvidenceId") or "")
                    if eid != matched_interaction_eid:
                        continue
                refs = {str(r) for r in (x.get("explicitRuleReferences") or [])}
                role = str(x.get("rulingRole") or "unclassified")
                if x.get("partialSelection"):
                    # Curated snippets are migration/fallback material only.
                    if eid in required_official_set:
                        relevant_overlay.append(x)
                    continue
                if eid in required_official_set:
                    relevant_overlay.append(x)
                    continue
                # Definition lookups remain grounded in the canonical rule family. A FAQ
                # example that merely mentions the concept does not redefine it.
                if ruling_is_definition:
                    continue
                # Clarifications and card-specific examples do not override a generic Core
                # ruling unless a compiled obligation explicitly requests them. Uncompiled
                # supplements/overrides fail closed only on strong scenario-level match.
                if role in {"override", "supplement"} and _overlay_phrase_match(interpretation_issue, x):
                    relevant_overlay.append(x)
                    continue
                # An exact official FAQ question match is material by itself. Do not
                # make fail-closed authority depend on whether retrieval surfaced a
                # parent rule ID or one of its children. Otherwise unknown future
                # sections remain conservative: require decisive-rule overlap plus
                # strong lexical anchoring.
                if role == "unclassified" and _overlay_exact_question_match(interpretation_issue, x):
                    relevant_overlay.append(x)
                    continue
                if role == "unclassified" and bool(refs & decisive_rule_ids) and _overlay_phrase_match(interpretation_issue, x):
                    relevant_overlay.append(x)
            interpreted_overlay_ids = set(ruling.get("interpretedOfficialOverlayEvidenceIds") or [])
            uninterpreted_overlay = [x for x in relevant_overlay if x.get("evidenceId") not in interpreted_overlay_ids]
            if uninterpreted_overlay:
                base_ruling = ruling
                ruling = {
                    "status": "insufficient",
                    "issue": issue,
                    "reason": "Relevant evidence from a current official rulings overlay was retrieved. The deterministic ruling is withheld until every relevant overlay item is interpreted under its precedence policy.",
                    "outcomes": [],
                    "effectiveVerdict": None,
                    "baseRulesRuling": base_ruling,
                    "officialOverlayEvidenceIds": [x.get("evidenceId") for x in uninterpreted_overlay],
                }
            gameplay_coverage = (self.authority_status.get("coverage") or {}).get("gameplayRulesCurrent") or {}
            if self.require_current_authority and not gameplay_coverage.get("complete", False):
                base_ruling = ruling.get("baseRulesRuling") if ruling.get("baseRulesRuling") else ruling
                missing = gameplay_coverage.get("missing") or []
                ruling = {
                    "status": "insufficient",
                    "issue": issue,
                    "reason": "Current gameplay authority is incomplete locally, so a definitive current ruling is withheld until every active official override source is synced.",
                    "outcomes": [],
                    "effectiveVerdict": None,
                    "baseRulesRuling": base_ruling,
                    "missingAuthoritySources": missing,
                }
            proof_trace = build_proof_trace(
                interpretation_issue, proof, ruling, facts, issue_evidence_catalog, self.compiled_rule_catalog
            )
            if ruling.get("status") in {"decided", "conditional"} and not (proof_trace.get("verification") or {}).get("passed"):
                base_ruling = ruling
                ruling = {
                    "status": "insufficient",
                    "issue": issue,
                    "reason": "The deterministic adjudication failed proof verification, so the verdict is withheld rather than repaired or guessed.",
                    "outcomes": [],
                    "effectiveVerdict": None,
                    "baseRuling": base_ruling,
                    "proofVerificationErrors": list((proof_trace.get("verification") or {}).get("errors") or []),
                }
                proof_trace["failClosedApplied"] = True
            else:
                proof_trace["failClosedApplied"] = False
            issue_clarifications = clarification_questions(interpretation_issue, ruling, proof.get("obligations", []), facts, named_cards)
            for cq in issue_clarifications:
                row = {"source": "deterministic_rule", "issue": issue, **cq}
                if row not in all_clarifications:
                    all_clarifications.append(row)
            resolved.append(
                {
                    "issue": issue,
                    "interpretedIssue": interpretation_issue,
                    "interpretationTransformations": issue_interp.get("transformations", []),
                    "retrievalContext": retrieval_query,
                    "clarifyingQuestions": issue_clarifications,
                    "retrieval": {
                        "queryExpansion": packet["queryExpansion"],
                        "topHits": packet["rankedHits"][:12],
                        "evidenceRuleIds": [r["ruleId"] for r in evidence],
                        "officialEvidence": packet.get("officialEvidence", []),
                    },
                    "evidenceCatalog": issue_evidence_catalog,
                    "proof": {
                        "obligations": proof["obligations"],
                        "missingRequiredEvidence": proof["missingRequiredEvidence"],
                        "evidenceCompleteForKnownObligations": proof["evidenceCompleteForKnownObligations"],
                        "decisiveRuleIds": [r["ruleId"] for r in proof["decisiveRules"]],
                    },
                    "proofTrace": proof_trace,
                    "ruling": ruling,
                }
            )
        result = {
            "question": question,
            "namedCards": [{"id": c["id"], "name": c["name"], "effectiveText": c.get("effectiveText")} for c in named_cards],
            "matchedConcepts": concepts,
            "facts": [f.to_dict() for f in facts],
            "mentionedGameActions": detect_game_actions(interpretation_text),
            "questionInterpretation": interpretation,
            "llmInterpretation": llm_interpretation,
            "scenarioLanguage": scenario_language,
            "scenarioModel": scenario_model,
            "cardInteractionContext": card_interaction_context,
            "clarifyingQuestions": all_clarifications,
            "issues": resolved,
            "enginePolicy": {
                "llmUsed": False,
                "llmUsedForAdjudication": False,
                "llmInterpretationProviderAttempted": llm_interpretation["providerAttempted"],
                "llmInterpretationAccepted": llm_interpretation["accepted"],
                "unknownConditionsAreGuessed": False,
                "scenarioAssumptionsGuessed": False,
                "scenarioModelAppliesGameRules": False,
                "cardInteractionContextAppliesGameRules": bool(card_interaction_execution.get("supported") and card_interaction_execution.get("fullyCoversQuestion")),
                "quotesRenderedFromAuthoritativeEvidence": True,
            },
            "authorityStatus": self.authority_status,
        }
        result["deterministicAnswer"] = render_answer(result, include_quotes=True)
        explanation_stage = run_explanation(result, self.explanation_provider).to_dict()
        result["llmExplanation"] = explanation_stage
        result["enginePolicy"]["llmUsedForExplanation"] = bool(explanation_stage.get("accepted"))
        result["enginePolicy"]["llmUsed"] = bool(explanation_stage.get("accepted"))
        result["answer"] = explanation_stage.get("renderedAnswer") or result["deterministicAnswer"]
        return result
