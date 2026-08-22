#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from riftkeep_rules.card_interactions import build_card_interaction_context, match_faq_interaction
from riftkeep_rules.card_interaction_executor import compile_interaction_executor_programs, EXECUTOR_SPECS
from riftkeep_rules.engine import RulesEngine
from riftkeep_rules.errata import canonical_card_identity
from riftkeep_rules.scenario import detect_named_cards
from riftkeep_rules.scenario_language import analyze_scenario_language
from riftkeep_rules.scenario_model import build_scenario_model

catalog = json.loads((ROOT / "data/canonical/card_interaction_catalog.json").read_text(encoding="utf-8"))
cards = json.loads((ROOT / "data/canonical/cards.json").read_text(encoding="utf-8"))
supplemental = json.loads((ROOT / "data/canonical/supplemental_sources.json").read_text(encoding="utf-8"))
gold = json.loads((ROOT / "data/gold/gold_corpus.json").read_text(encoding="utf-8"))
schema = json.loads((ROOT / "contracts/card_interaction_catalog.schema.json").read_text(encoding="utf-8"))
executor_programs = json.loads((ROOT / "data/canonical/card_interaction_programs.json").read_text(encoding="utf-8"))
executor_schema = json.loads((ROOT / "contracts/card_interaction_programs.schema.json").read_text(encoding="utf-8"))
promotions = json.loads((ROOT / "data/gold/gold_c_promotions.json").read_text(encoding="utf-8"))
core = json.loads((ROOT / "data/canonical/core_rules.json").read_text(encoding="utf-8"))

checks = 0
failures: list[dict[str, str]] = []


def check(name: str, ok: bool, detail: object = "") -> None:
    global checks
    checks += 1
    if not ok:
        failures.append({"check": name, "detail": str(detail)[:4000]})


def sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


# T122/T123 — contract, completeness, source provenance and immutable text guards.
errors = sorted(Draft202012Validator(schema).iter_errors(catalog), key=lambda e: list(e.path))
check("card interaction catalog validates against schema", not errors, [e.message for e in errors[:10]])
check("all 1304 card printings compiled", catalog.get("printingCount") == 1304 and len(catalog.get("printings", [])) == 1304, catalog.get("printingCount"))
check("compiled card IDs are unique", len({p["cardId"] for p in catalog["printings"]}) == 1304)
check("identity groups are non-empty", catalog.get("identityCount") == len(catalog.get("identities", [])) and all(x.get("identityKey") for x in catalog["identities"]), catalog.get("identityCount"))
check("all printings belong to exactly one identity group", sum(x.get("printingCount", 0) for x in catalog["identities"]) == 1304)
check("clause count agrees with printings", catalog.get("clauseCount") == sum(len(p.get("clauses", [])) for p in catalog["printings"]), catalog.get("clauseCount"))
check("structural compiler is explicitly non-adjudicative", catalog["policy"].get("clauseClassificationIsStructuralNotAdjudicative") is True, catalog["policy"])
check("unresolved references are never guessed", catalog["policy"].get("unresolvedReferencesAreNotGuessed") is True, catalog["policy"])

by_card = {c["id"]: c for c in cards["cards"]}
compiled_by_card = {p["cardId"]: p for p in catalog["printings"]}
text_mismatches = []
errata_mismatches = []
clause_span_errors = []
for cid, card in by_card.items():
    row = compiled_by_card.get(cid)
    if not row or row.get("effectiveText") != (card.get("effectiveText") or "") or row.get("effectiveTextSha256") != sha(card.get("effectiveText") or ""):
        text_mismatches.append(cid)
        continue
    expected_errata = [x.get("entryId") for x in card.get("officialErrataTimeline") or [] if x.get("entryId")]
    if row.get("officialErrataEventIds") != expected_errata:
        errata_mismatches.append((cid, expected_errata, row.get("officialErrataEventIds")))
    text = row["effectiveText"]
    for clause in row.get("clauses", []):
        a, b = clause["span"]
        if not (0 <= a <= b <= len(text) and text[a:b] == clause["text"] and sha(clause["text"]) == clause["textSha256"]):
            clause_span_errors.append(clause["clauseId"])
check("every compiled effective-text hash matches canonical card data", not text_mismatches, text_mismatches[:20])
check("official errata event provenance survives compilation", not errata_mismatches, errata_mismatches[:10])
check("all clause spans and clause hashes round-trip exactly", not clause_span_errors, clause_span_errors[:20])
check("all 91 errata-affected printings retain an errata event", sum(bool(p.get("officialErrataEventIds")) for p in catalog["printings"]) == 91, sum(bool(p.get("officialErrataEventIds")) for p in catalog["printings"]))

# Representative structural classification checks.
def named_printing(name: str) -> dict:
    return next(p for p in catalog["printings"] if p.get("name") == name)

shady = named_printing("Shady Spectacles")
check("Shady Spectacles splits Equip from copy-continuous clause", len(shady["clauses"]) == 2, shady["clauses"])
check("Shady Spectacles copy clause carries attach/copy/choose tags", {"attach", "copy", "choose"} <= set(shady["clauses"][1]["effectTags"]), shady["clauses"][1])
check("Shady Spectacles copy clause retains unresolved references", {"this", "unit"} - set(shady["clauses"][1].get("unresolvedReferenceTerms", [])) != {"this", "unit"}, shady["clauses"][1].get("unresolvedReferenceTerms"))
# The reference lexicon intentionally tracks pronouns/deictics, not generic nouns.
check("Shady Spectacles tracks deictic this/it references", {"this", "it"} <= set(shady["clauses"][1].get("unresolvedReferenceTerms", [])), shady["clauses"][1])

dform = named_printing("Dragon Form")
check("Dragon Form base-Might clause tagged Might", "might" in dform["clauses"][0]["effectTags"], dform["clauses"])
ride = named_printing("Ride The Wind")
check("Ride The Wind clause exposes Move and Ready", {"move", "ready"} <= set(ride["clauses"][0]["effectTags"]), ride["clauses"])
lair = named_printing("Vilemaw's Lair")
check("Vilemaw's Lair exposes movement restriction text", "move" in lair["clauses"][0]["effectTags"] and "can't move" in lair["clauses"][0]["text"].casefold(), lair["clauses"])
star_crossed = named_printing("Star-Crossed")
check("Star-Crossed return-to-hand is not mislabeled Recall", "return_to_hand" in star_crossed["clauses"][0]["effectTags"] and "recall" not in star_crossed["clauses"][0]["effectTags"], star_crossed["clauses"])
mel = named_printing("Mel, Newly Awakened")
check("Mel interaction clauses retain Empowered/counter/Might concepts", any({"counter", "might"} <= set(c["effectTags"]) for c in mel["clauses"]), mel["clauses"])
gangplank = named_printing("Gangplank, Naval")
check("Gangplank card-specific replacement is classified replacement", any(c["abilityKind"] == "replacement" and "replace" in c["effectTags"] for c in gangplank["clauses"]), gangplank["clauses"])

# T124/T125 — all current substantive FAQ interactions compile and exact-match themselves.
faq_docs = {d["evidenceId"]: d for d in supplemental["documents"] if d.get("question")}
programs = catalog.get("faqPrograms", [])
check("34 substantive FAQ interaction programs compiled", catalog.get("faqProgramCount") == 34 and len(programs) == 34, len(programs))
check("FAQ program evidence IDs are unique", len({p["evidenceId"] for p in programs}) == 34)
check("FAQ program IDs are unique", len({p["programId"] for p in programs}) == 34)
check("FAQ programs cover evidence 0002 through 0035", {p["evidenceId"].rsplit(":",1)[-1] for p in programs} == {f"{i:04d}" for i in range(2,36)})
answer_hash_bad = []
exact_match_bad = []
identity_bad = []
for p in programs:
    doc = faq_docs[p["evidenceId"]]
    text = str(doc.get("text") or "")
    question = str(doc.get("question") or "").strip()
    answer = text[len(question):].lstrip("\n ") if question and text.startswith(question) else text
    if p.get("officialAnswerSha256") != sha(answer):
        answer_hash_bad.append(p["evidenceId"])
    named = detect_named_cards(question, cards)
    identities = {canonical_card_identity(x.get("name")) for x in named if canonical_card_identity(x.get("name"))}
    if not set(p.get("requiredCardIdentityKeys") or []).issubset(identities):
        identity_bad.append((p["evidenceId"], p.get("requiredCardIdentityKeys"), sorted(identities)))
    match = match_faq_interaction(question, named, catalog)
    if not match or match.get("evidenceId") != p["evidenceId"] or not match.get("exactQuestionMatch"):
        exact_match_bad.append((p["evidenceId"], match))
check("all FAQ answer hashes are bound to current supplemental authority", not answer_hash_bad, answer_hash_bad)
check("all FAQ required card identities are present in their exact question", not identity_bad, identity_bad[:10])
check("all 34 exact FAQ questions match only their own program", not exact_match_bad, exact_match_bad[:10])

# M12 Gold-C fixture continuity.
gold_c = [x for x in gold["cases"] if x.get("category") == "future_card_interaction"]
check("all 34 M12 Gold-C fixtures remain present", len(gold_c) == 34, len(gold_c))
check("Gold-C authority IDs exactly equal compiled FAQ program IDs", {x["authorityEvidenceId"] for x in gold_c} == {p["evidenceId"] for p in programs})

# Conservative paraphrase boundaries.
paraphrases = {
    "What happens if I play Abandon on a spell that was played for its Flow cost?": "O:vendetta-faq-2026-08-14:0002",
    "If Ride the Wind tries to move my unit from Vilemaw's Lair to base, what happens?": "O:vendetta-faq-2026-08-14:0035",
}
for question, evid in paraphrases.items():
    m = match_faq_interaction(question, detect_named_cards(question, cards), catalog)
    check(f"high-confidence paraphrase matches {evid[-4:]}", bool(m) and m.get("evidenceId") == evid and m.get("exactQuestionMatch") is False, m)
for question in ["What happens with Flow?", "What happens when I play a card?", "Can I use a discount?", "What happens at a battlefield?"]:
    m = match_faq_interaction(question, detect_named_cards(question, cards), catalog)
    check(f"generic query stays unmatched: {question}", m is None, m)

# T127 — possessives and contained-name safety.
q = "Does Astral Heron’s discount apply here?"
check("curly possessive card name is recognized", [x["name"] for x in detect_named_cards(q, cards)] == ["Astral Heron"], [x["name"] for x in detect_named_cards(q, cards)])
q = "Does Astral Heron's discount apply here?"
check("ASCII possessive card name is recognized", [x["name"] for x in detect_named_cards(q, cards)] == ["Astral Heron"], [x["name"] for x in detect_named_cards(q, cards)])
q = "Does Astral Herron's discount apply here?"
check("possessive typo remains unmatched", detect_named_cards(q, cards) == [], detect_named_cards(q, cards))
check("full Vilemaw's Lair suppresses contained Vilemaw identity", [canonical_card_identity(x["name"]) for x in detect_named_cards("Vilemaw's Lair", cards)] == ["vilemaw's lair"], detect_named_cards("Vilemaw's Lair", cards))
check("separately written Vilemaw and Vilemaw's Lair both survive", {canonical_card_identity(x["name"]) for x in detect_named_cards("Vilemaw and Vilemaw's Lair", cards)} == {"vilemaw", "vilemaw's lair"})
sl = analyze_scenario_language("Astral Heron’s discount applies.", cards)
check("scenario-language entity parser recognizes possessive card", any(x.get("canonicalName") == "Astral Heron" for x in sl.get("entities", [])), sl.get("entities"))

# T126/T128 — structural context remains non-adjudicative unless a reviewed executor is invoked.
engine = RulesEngine(ROOT, require_current_authority=False)
structural_question = "Can I equip Shady Spectacles to my unit?"
structural = engine.ask(structural_question)
structural_ctx = structural.get("cardInteractionContext") or {}
check("engine exposes cardInteractionContext", structural_ctx.get("schemaVersion") == 1, structural_ctx)
check("unmatched structural context does not apply game rules", structural_ctx.get("appliesGameRules") is False and structural_ctx.get("changesVerdict") is False, structural_ctx)
check("engine policy keeps unmatched structural context non-adjudicative", structural.get("enginePolicy", {}).get("cardInteractionContextAppliesGameRules") is False, structural.get("enginePolicy"))
check("structural card context binds Shady Spectacles identity", {x.get("identityKey") for x in structural_ctx.get("namedCards", [])} == {"shady spectacles"}, structural_ctx.get("namedCards"))
check("interaction binding does not add Scenario Model assumptions", structural.get("scenarioModel", {}).get("assumptions") == [], structural.get("scenarioModel", {}).get("assumptions"))

engine_without = RulesEngine(ROOT, require_current_authority=False)
engine_without.card_interaction_catalog = {"printings": [], "identities": [], "faqPrograms": []}
engine_without.card_interaction_programs = {"programs": []}
base = engine_without.ask(structural_question)
for field in ["facts", "scenarioLanguage", "scenarioModel", "clarifyingQuestions", "issues", "deterministicAnswer", "answer"]:
    check(f"unmatched structural context leaves {field} unchanged", structural.get(field) == base.get(field), {"with": structural.get(field), "without": base.get(field)} if field in {"deterministicAnswer","answer"} else "mismatch")

# Legality routing exposes context but never executes card-interaction adjudication.
legal_q = "Is Astral Heron legal in Standard format?"
legal = engine.ask(legal_q)
check("legality result exposes card interaction context", "cardInteractionContext" in legal, legal.keys())
check("legality path keeps card interaction executor non-adjudicative", legal.get("enginePolicy", {}).get("cardInteractionContextAppliesGameRules") is False, legal.get("enginePolicy"))

# T129/T130 — reviewed executor artifact, source guards, exact authority execution and proof provenance.
executor_errors = sorted(Draft202012Validator(executor_schema).iter_errors(executor_programs), key=lambda e: list(e.path))
check("card interaction executor artifact validates against schema", not executor_errors, [e.message for e in executor_errors[:10]])
check("16 reviewed executor programs compiled", executor_programs.get("programCount") == 16 and len(executor_programs.get("programs", [])) == 16, executor_programs.get("programCount"))
check("all 16 reviewed executor programs pass source guards", executor_programs.get("validProgramCount") == 16 and all(x.get("valid") and x.get("executable") for x in executor_programs.get("programs", [])), [(x.get("programId"), x.get("validationErrors")) for x in executor_programs.get("programs", []) if not x.get("valid")])
check("executor program IDs are unique", len({x.get("programId") for x in executor_programs.get("programs", [])}) == 16)
check("executor authority IDs are unique", len({x.get("evidenceId") for x in executor_programs.get("programs", [])}) == 16)
check("promotion manifest is frozen and not engine-derived", promotions.get("frozen") is True and promotions.get("derivedExpectationsFromEngine") is False and all(x.get("derivedFromEngine") is False for x in promotions.get("promotions", [])), promotions)
check("promotion manifest contains 16 of 34 Gold-C fixtures", promotions.get("promotionCount") == 16 and promotions.get("remainingReportOnlyCount") == 18 and len(promotions.get("promotions", [])) == 16, promotions)
check("promotion IDs map to source-guarded executor programs", {x.get("programId") for x in promotions.get("promotions", [])} == {x.get("programId") for x in executor_programs.get("programs", [])}, promotions.get("promotions"))

promotion_by_eid = {x["authorityEvidenceId"]: x for x in promotions.get("promotions", [])}
execution_failures = []
proof_failures = []
for spec in EXECUTOR_SPECS:
    eid = spec["evidenceId"]
    promo = promotion_by_eid[eid]
    result = engine.ask(promo["question"])
    execution = (result.get("cardInteractionContext") or {}).get("execution") or {}
    actual_verdicts = [(i.get("ruling", {}).get("effectiveVerdict") or {}).get("verdict") for i in result.get("issues", [])]
    expected_verdicts = list(promo.get("expectedIssueVerdicts") or [])
    if not (execution.get("supported") and execution.get("fullyCoversQuestion") and execution.get("programId") == spec["programId"] and actual_verdicts == expected_verdicts and result.get("enginePolicy", {}).get("cardInteractionContextAppliesGameRules") is True):
        execution_failures.append({"programId": spec["programId"], "execution": execution, "expected": expected_verdicts, "actual": actual_verdicts})
    for issue in result.get("issues", []):
        trace = issue.get("proofTrace") or {}
        rows = trace.get("cardInteractionPrograms") or []
        if not ((trace.get("verification") or {}).get("passed") and any(x.get("programId") == spec["programId"] and x.get("evidenceId") == eid for x in rows)):
            proof_failures.append({"programId": spec["programId"], "issue": issue.get("issue"), "tracePrograms": rows, "verification": trace.get("verification")})
check("all 16 promoted exact FAQ interactions execute expected issue verdicts", not execution_failures, execution_failures[:5])
check("all promoted issue proofs preserve M13 program provenance and verify", not proof_failures, proof_failures[:5])

# A source-guarded exact interaction is authoritative for its reviewed FAQ section; adjacent lexical FAQ hits may not block it.
for eid in ["O:vendetta-faq-2026-08-14:0009", "O:vendetta-faq-2026-08-14:0031"]:
    promo = promotion_by_eid[eid]
    rr = engine.ask(promo["question"])
    check(f"reviewed executor avoids adjacent-overlay false blocker {eid[-4:]}", all(i.get("ruling", {}).get("status") == "decided" for i in rr.get("issues", [])), [(i.get("ruling", {}).get("status"), i.get("ruling", {}).get("reason")) for i in rr.get("issues", [])])

# Source drift must disable—not silently continue—reviewed execution.
drift_catalog = copy.deepcopy(catalog)
faq_eid = EXECUTOR_SPECS[0]["evidenceId"]
next(x for x in drift_catalog["faqPrograms"] if x.get("evidenceId") == faq_eid)["officialAnswerSha256"] = "0" * 64
drift = compile_interaction_executor_programs(drift_catalog, core)
check("FAQ answer drift disables its reviewed executor", next(x for x in drift["programs"] if x.get("evidenceId") == faq_eid).get("valid") is False and "faq_answer_source_drift" in next(x for x in drift["programs"] if x.get("evidenceId") == faq_eid).get("validationErrors", []), next(x for x in drift["programs"] if x.get("evidenceId") == faq_eid))

card_drift_catalog = copy.deepcopy(catalog)
identity = EXECUTOR_SPECS[1]["expectedIdentityTextHashes"]
identity_key = next(iter(identity))
next(x for x in card_drift_catalog["identities"] if x.get("identityKey") == identity_key)["effectiveTextHashes"] = ["f" * 64]
card_drift = compile_interaction_executor_programs(card_drift_catalog, core)
row = next(x for x in card_drift["programs"] if x.get("programId") == EXECUTOR_SPECS[1]["programId"])
check("card effective-text drift disables reviewed executor", row.get("valid") is False and any(str(e).startswith("card_text_source_drift:") for e in row.get("validationErrors", [])), row)

core_drift = copy.deepcopy(core)
core_drift.setdefault("metadata", {})["sourceId"] = "core-rules-future-test"
core_guard = compile_interaction_executor_programs(catalog, core_drift)
check("Core source drift disables all reviewed executors", core_guard.get("validProgramCount") == 0 and all(any(str(e).startswith("core_source_drift:") for e in p.get("validationErrors", [])) for p in core_guard.get("programs", [])), core_guard.get("validProgramCount"))

tag_drift_catalog = copy.deepcopy(catalog)
for pr in tag_drift_catalog["printings"]:
    if pr.get("name") == "Star-Crossed":
        for clause in pr.get("clauses", []):
            clause["effectTags"] = [x for x in clause.get("effectTags", []) if x != "return_to_hand"]
tag_guard = compile_interaction_executor_programs(tag_drift_catalog, core)
row = next(x for x in tag_guard["programs"] if x.get("programId") == "CARDI:0018")
check("missing return-to-hand semantic disables Akali/Star-Crossed executor", row.get("valid") is False and "missing_clause_tags:star crossed:return_to_hand" in row.get("validationErrors", []), row)

# High-confidence matched FAQ without a reviewed executor remains non-adjudicative at M13.
unpromoted = next(x for x in gold_c if x.get("authorityEvidenceId") == "O:vendetta-faq-2026-08-14:0002")
unpromoted_result = engine.ask(unpromoted["question"])
unpromoted_exec = (unpromoted_result.get("cardInteractionContext") or {}).get("execution") or {}
check("unpromoted Gold-C FAQ does not invoke a card executor", unpromoted_exec.get("supported") is False and unpromoted_result.get("enginePolicy", {}).get("cardInteractionContextAppliesGameRules") is False, unpromoted_exec)

metrics = {
    "schemaVersion": 2,
    "printingCount": catalog.get("printingCount"),
    "identityCount": catalog.get("identityCount"),
    "clauseCount": catalog.get("clauseCount"),
    "faqProgramCount": catalog.get("faqProgramCount"),
    "errataAffectedPrintings": sum(bool(p.get("officialErrataEventIds")) for p in catalog.get("printings", [])),
    "goldCFixtureCount": len(gold_c),
    "goldCPromotedExecutable": promotions.get("promotionCount"),
    "goldCRemainingReportOnly": promotions.get("remainingReportOnlyCount"),
    "executableProgramCount": executor_programs.get("programCount"),
    "validExecutableProgramCount": executor_programs.get("validProgramCount"),
    "structuralContextAloneAppliesGameRules": False,
    "guardedExecutorCanApplyGameRules": True,
    "abilityKindCounts": catalog.get("abilityKindCounts"),
    "effectTagCounts": catalog.get("effectTagCounts"),
}
(ROOT / "data/validation/card_interaction_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
report = {"schemaVersion": 1, "passed": not failures, "checkCount": checks, "failureCount": len(failures), "failures": failures, "metrics": metrics}
(ROOT / "data/validation/card_interaction_test_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"passed": report["passed"], "checkCount": checks, "failureCount": len(failures), "failures": failures[:10], "metrics": metrics}, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["passed"] else 1)
