#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from riftkeep_rules.engine import RulesEngine
from riftkeep_rules.versioning import compare_rule_versions
from riftkeep_rules.llm_contract import validate_evidence_request, validate_adjudication, validate_answer_draft
from riftkeep_rules.official_sources import import_official_snapshot, compile_supplemental_sources, validate_official_url
from riftkeep_rules.authority import load_authority_status
from riftkeep_rules.retrieval import build_index, search, retrieve_issue
from riftkeep_rules.llm_pipeline import GroundedLlmPipeline, make_adjudication_packet
from riftkeep_rules.errata import compile_official_errata, apply_official_errata, normalize_card_identity

failures = []
checks = 0

def check(name: str, condition: bool, detail: str = ""):
    global checks
    checks += 1
    if not condition:
        failures.append({"name": name, "detail": detail})

core = json.loads((ROOT / "data/canonical/core_rules.json").read_text(encoding="utf-8"))
validation = json.loads((ROOT / "data/validation/parser_validation.json").read_text(encoding="utf-8"))
check("core parser independent validation", validation["core"]["passed"], str(validation["core"]))
check("tournament parser independent validation", validation["tournament"]["passed"], str(validation["tournament"]))
by_id = {r["ruleId"]: r for r in core["rules"]}
check("347.1.b body preserved", by_id["347.1.b"]["normativeText"] == "When that Chain closes, Focus passes to the next Player in Turn Order.", by_id["347.1.b"]["normativeText"])

# Versioning: identical baseline.
self_diff = compare_rule_versions(core, copy.deepcopy(core))
check("version self diff safe", self_diff["safeToAutoPromote"], str(self_diff["reviewRequired"][:3]))
check("version self diff all unchanged", self_diff["changeCounts"] == {"UNCHANGED": 2381}, str(self_diff["changeCounts"]))

# Versioning: same-ID wording change preserves identity.
mut = copy.deepcopy(core)
r = next(x for x in mut["rules"] if x["ruleId"] == "355.2.a")
r["normativeText"] = r["normativeText"] + " Test clarification."
r["normalizedText"] = r["normalizedText"] + " test clarification."
diff = compare_rule_versions(core, mut)
c = next(x for x in diff["changes"] if x.get("oldRuleId") == "355.2.a")
check("same id text change detected", c["changeType"] == "TEXT_CHANGED", str(c))
check("same id text change stable identity", c["internalRuleId"] == by_id["355.2.a"]["internalRuleId"], str(c))

# Versioning: exact text moved to new visible number.
mut = copy.deepcopy(core)
r = next(x for x in mut["rules"] if x["ruleId"] == "355.2.a")
r["ruleId"] = "355.20.a"
r["parentRuleId"] = "355.20"
diff = compare_rule_versions(core, mut)
c = next(x for x in diff["changes"] if x.get("oldRuleId") == "355.2.a" and x.get("newRuleId") == "355.20.a")
check("renumber detected", c["changeType"] in {"RENUMBERED", "MOVED"}, str(c))

engine = RulesEngine(ROOT, require_current_authority=False)
# Keyword lookup is deterministic.
g = engine.ask("What does Ganking do?")
check("ganking concept matched", any(c["ruleId"] == "810" for c in g["matchedConcepts"]), str(g["matchedConcepts"]))
scenario_do = engine.ask("What does my unit do after I play it?")
scenario_do_is_definition = any(o.get("verdict") == "definition" for o in scenario_do["issues"][0]["ruling"].get("outcomes", []))
check("ganking definition decided and scenario do-question not hijacked", g["issues"][0]["ruling"]["status"] == "decided" and not scenario_do_is_definition, {"ganking": g["issues"][0]["ruling"]["status"], "scenario": scenario_do["issues"][0]["ruling"]})
check("ganking includes definition rule", "810.1.b" in g["issues"][0]["retrieval"]["evidenceRuleIds"] or "810.1.b" in [e["ruleId"] for e in g["issues"][0]["ruling"]["outcomes"][0]["evidence"]], "")

m = engine.ask("What does Mighty mean?")
ev = [e["ruleId"] for e in m["issues"][0]["ruling"]["outcomes"][0]["evidence"]]
check("mighty family spans sibling rules", all(x in ev for x in ["707", "708", "709", "710", "711"]), str(ev))

# LLM boundary rejects guessed rule numbers in evidence-search requests.
errs = validate_evidence_request({"complete": False, "requests": [{"issueId": "I1", "query": "find rule 355.2.a", "whyNeeded": "play location"}]})
check("LLM completion cannot guess rule IDs", bool(errs), str(errs))

# Grounded adjudication validator.
allowed = {"R:355.2.a", "R:190.3.a.1"}
valid_adj = {
    "issues": [{
        "issueId": "I1", "status": "decided", "verdict": "yes",
        "reasoningSteps": [{"claim": "controlled battlefield is valid", "evidenceIds": ["R:355.2.a"]}],
        "appliedEvidence": ["R:355.2.a"], "rejectedEvidence": [], "assumptions": [], "missingFacts": []
    }]
}
check("valid adjudication contract passes", validate_adjudication(valid_adj, allowed, {"I1"}) == [], str(validate_adjudication(valid_adj, allowed, {"I1"})))
invalid_adj = copy.deepcopy(valid_adj)
invalid_adj["issues"][0]["reasoningSteps"][0]["evidenceIds"] = ["R:999.9"]
check("invented evidence rejected", bool(validate_adjudication(invalid_adj, allowed, {"I1"})), "")

valid_draft = {"parts": [{"issueId": "I1", "declaredVerdict": "yes", "prose": "Yes, because the destination is valid.", "citationIds": ["R:355.2.a"]}]}
check("answer draft cannot change verdict - valid", validate_answer_draft(valid_draft, valid_adj, allowed) == [], str(validate_answer_draft(valid_draft, valid_adj, allowed)))
invalid_draft = copy.deepcopy(valid_draft)
invalid_draft["parts"][0]["declaredVerdict"] = "no"
check("answer draft verdict mutation rejected", bool(validate_answer_draft(invalid_draft, valid_adj, allowed)), "")


# End-to-end LLM boundary is fail-closed around the sealed evidence catalog.
class FakeJsonProvider:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []
    def complete_json(self, **kwargs):
        self.calls.append(kwargs)
        return self.payloads.pop(0)

base_result = engine.ask("By default, can I play a unit directly to a battlefield I don't control?")
sealed_packet = make_adjudication_packet(base_result)
sealed_ids = {e["evidenceId"] for e in sealed_packet["evidenceCatalog"]}
check("sealed evidence catalog contains retrieved rule IDs", "R:355.2.a" in sealed_ids, str(sorted(sealed_ids)[:20]))

good_model_adj = {"issues": [{
    "issueId": "I1", "status": "decided", "verdict": "no",
    "reasoningSteps": [{"claim": "The default location rule requires control of the battlefield.", "evidenceIds": ["R:355.2.a"]}],
    "appliedEvidence": ["R:355.2.a"], "rejectedEvidence": [], "assumptions": [], "missingFacts": []
}]}
legacy_adj_provider = FakeJsonProvider([good_model_adj])
good_pipe = GroundedLlmPipeline(legacy_adj_provider)
good_stage = good_pipe.adjudicate(sealed_packet)
check("M10 LLM adjudication stage is disabled", not good_stage.accepted and bool(good_stage.errors), str(good_stage.errors))
check("disabled M10 adjudication does not call provider", len(legacy_adj_provider.calls) == 0, str(legacy_adj_provider.calls))

good_answer = {"parts": [{"issueId": "I1", "declaredVerdict": "no", "prose": "No. The default destination condition is not satisfied.", "citationIds": ["R:355.2.a"]}]}
legacy_answer_provider = FakeJsonProvider([good_answer])
answer_pipe = GroundedLlmPipeline(legacy_answer_provider)
answer_stage = answer_pipe.draft_answer(good_model_adj, sealed_packet["evidenceCatalog"])
check("M10 LLM answer-writing stage is disabled", not answer_stage.accepted and bool(answer_stage.errors), str(answer_stage.errors))
check("disabled M10 answer writer does not call provider", len(legacy_answer_provider.calls) == 0, str(legacy_answer_provider.calls))

# Official-source sync: archive, parse, authority completeness, retrieval, and in-place change history.
with tempfile.TemporaryDirectory() as td:
    tr = Path(td)
    (tr / "data/source").mkdir(parents=True)
    (tr / "data/source/core_rules.pdf").write_bytes(b"test-core")
    manifest = {
        "schemaVersion": 1,
        "sources": [
            {"id": "core-test", "type": "core_rules_pdf", "status": "current", "localSnapshot": "core_rules.pdf"},
            {"id": "faq-test", "type": "official_faq", "status": "current_overlay", "url": "https://playriftbound.com/en-us/news/rules-and-releases/synthetic-faq/",
             "authorityScope": ["official_rulings"], "precedence": {"over": ["core-test"], "onlyWhereDifferent": True}},
        ],
    }
    (tr / "data/source/official_source_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    html1 = tr / "faq1.html"
    html1.write_text("<html><body><h1>Test FAQ</h1><p>What happens to Alpha?</p><p>Alpha is returned to hand. See CR 355.2.</p><h2>Other</h2><p>Beta stays.</p></body></html>", encoding="utf-8")
    snap1 = import_official_snapshot(tr, "faq-test", html1, published="2026-08-01")
    check("official snapshot sections parsed", snap1["sectionCount"] >= 2, str(snap1.get("sections")))
    check("official snapshot rule refs extracted", any("355.2" in x.get("explicitRuleReferences", []) for x in snap1["sections"]), str(snap1["sections"]))
    check("active overlay becomes complete only after body ingest", load_authority_status(tr)["currentRulesComplete"], str(load_authority_status(tr)))
    sup = compile_supplemental_sources(tr)
    tempdb = tr / "rules.sqlite"
    build_index(tempdb, {"rules": []}, {"cards": []}, sup)
    hits = search(tempdb, "Alpha returned hand", limit=5, kinds=("official_ruling",))
    check("official ruling is searchable", bool(hits) and hits[0].kind == "official_ruling", str([(h.kind,h.title) for h in hits]))
    # An official ruling's explicit Core Rules references are authoritative dependencies.
    # Retrieval must seed evidence closure with them instead of relying on lexical similarity.
    tempdb_with_core = tr / "rules-with-core.sqlite"
    build_index(tempdb_with_core, core, {"cards": []}, sup)
    faq_packet = retrieve_issue(tempdb_with_core, core, "What happens to Alpha?", top_k=10, closure_limit=30)
    check("FAQ explicit refs seed Core closure", "355.2" in faq_packet.get("officialReferencedRuleIds", []), str(faq_packet.get("officialReferencedRuleIds")))
    check("FAQ referenced Core rule enters evidence", any(r.get("ruleId") == "355.2" for r in faq_packet.get("evidenceRules", [])), str([r.get("ruleId") for r in faq_packet.get("evidenceRules", [])]))

    html2 = tr / "faq2.html"
    html2.write_text("<html><body><h1>Test FAQ</h1><p>What happens to Alpha?</p><p>Alpha is banished instead. See CR 355.2.</p><h2>Other</h2><p>Beta stays.</p><p>What happens to Gamma?</p><p>Gamma is readied.</p></body></html>", encoding="utf-8")
    snap2 = import_official_snapshot(tr, "faq-test", html2, published="2026-08-02")
    counts = snap2["diffFromPrevious"]["changeCounts"]
    check("official snapshot detects changed section", counts.get("TEXT_CHANGED", 0) >= 1, str(counts))
    check("official snapshot preserves previous version", bool(snap2.get("previousSha256")) and snap2["previousSha256"] == snap1["sha256"], str(snap2.get("previousSha256")))


# Official-source hardening and errata compilation.
try:
    validate_official_url("https://playriftbound.com/en-us/rules-hub/")
    good_url = True
except Exception:
    good_url = False
check("official source allowlist accepts playriftbound", good_url, "")
try:
    validate_official_url("https://example.com/fake-rules")
    rejected_bad_url = False
except ValueError:
    rejected_bad_url = True
check("official source allowlist rejects arbitrary hosts", rejected_bad_url, "")

with tempfile.TemporaryDirectory() as td:
    tr = Path(td)
    (tr / "data/source").mkdir(parents=True)
    manifest = {
        "schemaVersion": 1,
        "sources": [
            {"id":"errata-test","type":"card_errata","status":"active_history","url":"https://playriftbound.com/en-us/news/rules-and-releases/test-errata/","published":"2026-08-01","effectiveFrom":"2026-08-01"},
            {"id":"bad-faq","type":"official_faq","status":"current_overlay","url":"https://playriftbound.com/en-us/news/rules-and-releases/test-faq/"},
        ],
    }
    (tr / "data/source/official_source_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    errata_html = tr / "errata.html"
    errata_html.write_text("""<html><body><h1>Test Errata</h1><h2>Spiritforged Cards</h2><h2>Draven, Vanquisher</h2><h5>[NEW TEXT]</h5><p>When I attack, draw 2.</p><h4>▲</h4><h5>[OLD TEXT]</h5><p>When I attack, draw 1.</p><hr/><h2>Falling Star</h2><h5>[NEW TEXT]</h5><p>Deal 3 to a unit.</p><p>Deal 3 to a unit.</p><h5>[OLD TEXT]</h5><p>Do this twice: Deal 3 to a unit.</p></body></html>""", encoding="utf-8")
    esnap = import_official_snapshot(tr, "errata-test", errata_html)
    check("errata snapshot validates", esnap["validation"]["passed"], str(esnap["validation"]))
    ebundle = compile_official_errata(tr)
    check("errata compiler extracts two records", ebundle["validRecordCount"] == 2, str(ebundle))
    sample_cards = {"metadata":{}, "cards":[
        {"id":"sfd-x","name":"Draven - Vanquisher (Alternate Art)","effectiveText":"old","knownPrintedText":None,"textSource":"databaseText"},
        {"id":"ogn-y","name":"Falling Star","effectiveText":"old2","knownPrintedText":None,"textSource":"databaseText"},
    ]}
    sample_cards, ereport = apply_official_errata(sample_cards, ebundle)
    d = next(c for c in sample_cards["cards"] if c["id"] == "sfd-x")
    f = next(c for c in sample_cards["cards"] if c["id"] == "ogn-y")
    check("errata name normalization bridges comma/hyphen/variant", d["effectiveText"] == "When I attack, draw 2.", str(d))
    check("errata preserves proven old text", d["knownPrintedText"] == "When I attack, draw 1.", str(d))
    check("errata applies multi-paragraph new text", f["effectiveText"] == "Deal 3 to a unit. Deal 3 to a unit.", str(f))
    check("errata provenance stored", d["textSource"] == "official_errata:errata-test" and len(d["officialErrataHistory"]) == 1, str(d))

    bad_html = tr / "badfaq.html"
    bad_html.write_text("<html><body><h1>FAQ</h1><p>This page accidentally contains no questions.</p></body></html>", encoding="utf-8")
    bsnap = import_official_snapshot(tr, "bad-faq", bad_html)
    check("invalid FAQ snapshot quarantined", not bsnap["validation"]["passed"] and bsnap.get("quarantined") is True, str(bsnap.get("validation")))
    check("invalid FAQ does not advance latest pointer", not (tr / "data/source/snapshots/bad-faq/latest.json").exists(), "")

# Current authoritative errata corpus is complete and applied to effective card text.
current_errata = json.loads((ROOT / "data/canonical/official_errata.json").read_text(encoding="utf-8"))
current_errata_report = json.loads((ROOT / "data/validation/errata_application.json").read_text(encoding="utf-8"))
current_cards = json.loads((ROOT / "data/canonical/cards.json").read_text(encoding="utf-8"))
check("official errata corpus has 63 validated events", current_errata.get("recordCount") == 63 and current_errata.get("validRecordCount") == 63 and current_errata.get("invalidRecordCount") == 0, str({k: current_errata.get(k) for k in ("recordCount","validRecordCount","invalidRecordCount")}))
check("official errata applies without unresolved identities", current_errata_report.get("passed") is True and current_errata_report.get("cardsAffected") == 91 and current_errata_report.get("unresolvedIdentityCount") == 0, str(current_errata_report))
ava = next(c for c in current_cards["cards"] if normalize_card_identity(c.get("name")) == normalize_card_identity("Ava, Achiever"))
check("Ava Achiever uses official corrected text", "If it's a unit, play it here." in (ava.get("effectiveText") or "") and ava.get("textSource") == "official_errata:origins-errata", str({k:ava.get(k) for k in ("name","effectiveText","textSource")}))
dais = next(c for c in current_cards["cards"] if c.get("name") == "Emperor's Dais")
check("Emperor's Dais receives Vendetta errata", dais.get("textSource") == "official_errata:vendetta-errata" and bool(dais.get("officialErrataHistory")), str({k:dais.get(k) for k in ("effectiveText","textSource","officialErrataHistory")}))
falling = next(c for c in current_cards["cards"] if c.get("name") == "Falling Star")
check("Falling Star preserves historical old text provenance", "Do this twice" in (falling.get("knownPrintedText") or "") and falling.get("textSource") == "official_errata:spiritforged-errata", str({k:falling.get(k) for k in ("knownPrintedText","effectiveText","textSource")}))
coverage = engine.authority_status.get("coverage") or {}
check("official errata authority coverage complete", (coverage.get("officialCardErrataHistory") or {}).get("complete") is True, str(coverage.get("officialCardErrataHistory")))

# Production/default mode becomes usable only after the complete current overlay is ingested.
strict_engine = RulesEngine(ROOT)
strict_gameplay = strict_engine.ask("What does Ganking mean?")
strict_ruling = strict_gameplay["issues"][0]["ruling"]
strict_coverage = strict_gameplay.get("authorityStatus", {}).get("coverage", {})
check("strict gameplay mode works with complete current overlay", strict_ruling.get("status") == "decided" and strict_gameplay.get("authorityStatus", {}).get("currentRulesComplete") is True and (strict_coverage.get("gameplayRulesCurrent") or {}).get("complete") is True, str({"ruling": strict_ruling, "authority": strict_gameplay.get("authorityStatus")}))
strict_legality = strict_engine.ask("Is Called Shot banned in Constructed?")
check("strict legality remains independently decidable", strict_legality["issues"][0]["ruling"].get("status") == "decided" and strict_legality["issues"][0]["ruling"]["effectiveVerdict"]["verdict"] == "banned", strict_legality.get("answer", ""))

# Rules Hub structured transform and deterministic legality path.
with tempfile.TemporaryDirectory() as td:
    tr = Path(td)
    (tr / "data/source").mkdir(parents=True)
    hub_manifest = {"schemaVersion": 1, "sources": [{"id":"rules-hub-current","type":"rules_hub","status":"current_index","url":"https://playriftbound.com/en-us/rules-hub/","localStructuredSnapshot":"rules_hub_metadata.json"}]}
    (tr / "data/source/official_source_manifest.json").write_text(json.dumps(hub_manifest), encoding="utf-8")
    hub_html = tr / "hub.html"
    hub_html.write_text("""<html><body><h1>Rules Hub</h1><h3>Constructed Format Legality</h3><p>Last updated: July 16, 2026</p><h4>Cards</h4><ul><li>Called Shot</li></ul><h4>Battlefields</h4><ul><li>Dreaming Tree</li></ul><h3>2v2 Constructed Legality</h3><p>Last updated: July 16, 2026</p><h4>Legends</h4><ul><li>Master Yi, Wuju Bladesman</li></ul><h4>Cards</h4><ul><li>Called Shot</li></ul><h4>Battlefields</h4><ul><li>Dreaming Tree</li></ul><h3>Core Rules</h3></body></html>""", encoding="utf-8")
    import_official_snapshot(tr, "rules-hub-current", hub_html)
    derived = json.loads((tr / "data/source/rules_hub_metadata.json").read_text(encoding="utf-8"))
    check("rules hub transform captures constructed ban", "Called Shot" in derived["constructed"]["banned"]["cards"], str(derived))
    check("rules hub transform captures 2v2 legend ban", "Master Yi, Wuju Bladesman" in derived["twoVsTwoConstructed"]["banned"]["legends"], str(derived))

# Current project legality is directly queryable without an LLM.
leg = engine.ask("Is Called Shot banned in Constructed?")
check("constructed ban query decided", leg["issues"][0]["ruling"]["effectiveVerdict"]["verdict"] == "banned", leg["answer"])
leg2 = engine.ask("Is Master Yi, Wuju Bladesman banned in 2v2?")
check("2v2 ban query decided", leg2["issues"][0]["ruling"]["effectiveVerdict"]["verdict"] == "banned", leg2["answer"])

# Gameplay target legality must never be routed to sanctioned-format legality.
target_leg = engine.ask("If every target of a spell is illegal when it resolves, does the spell still resolve?")
check("target illegality stays in gameplay adjudication", "mistarget_resolution" in target_leg["issues"][0]["proof"]["obligations"] and "format_legality" not in target_leg["issues"][0]["proof"]["obligations"], str(target_leg["issues"][0]["proof"]))
check("all-target mistarget resolves deterministically", (target_leg["issues"][0]["ruling"].get("effectiveVerdict") or {}).get("verdict") == "resolves_no_effect", target_leg.get("answer", ""))

ready_case = engine.ask("If an effect tells me to Ready a unit that is already Ready, does it Ready again?")
check("already-ready interaction compiled", (ready_case["issues"][0]["ruling"].get("effectiveVerdict") or {}).get("verdict") == "no", ready_case.get("answer", ""))
recall_case = engine.ask("If my unit is Recalled, does that count as a Move for a move trigger?")
check("recall-vs-move interaction compiled", (recall_case["issues"][0]["ruling"].get("effectiveVerdict") or {}).get("verdict") == "no", recall_case.get("answer", ""))

# Every current keyword root must be reachable by a plain-English definition query.
keyword_concepts = []
for c in engine.semantic_ir["conceptCatalog"]["concepts"]:
    try:
        n = int(c.get("ruleId", ""))
    except ValueError:
        continue
    if 805 <= n <= 829 and c.get("category") == "keyword":
        keyword_concepts.append(c)
for c in keyword_concepts:
    res = engine.ask(f"What does {c['name']} do?")
    ev = [e.get("ruleId") for o in res["issues"][0]["ruling"].get("outcomes", []) for e in o.get("evidence", [])]
    check(f"keyword lookup {c['ruleId']} {c['name']}", c["ruleId"] in ev, str(ev[:20]))


# Every current Game Action root must also be directly reachable as a definition query.
game_action_concepts = []
for c in engine.semantic_ir["conceptCatalog"]["concepts"]:
    try:
        n = int(c.get("ruleId", ""))
    except ValueError:
        continue
    if 413 <= n <= 444 and c.get("category") == "game_action":
        game_action_concepts.append(c)
for c in game_action_concepts:
    res = engine.ask(f"What does {c['name']} do?")
    ev = [e.get("ruleId") for o in res["issues"][0]["ruling"].get("outcomes", []) for e in o.get("evidence", [])]
    check(f"game action lookup {c['ruleId']} {c['name']}", c["ruleId"] in ev, str(ev[:20]))

emp = engine.ask("What does Empower mean?")
emp_ev = [e.get("ruleId") for o in emp["issues"][0]["ruling"].get("outcomes", []) for e in o.get("evidence", [])]
check("Empower disambiguates game action and keyword", "441" in emp_ev and "827" in emp_ev, str(emp_ev))



# Player language and retrieval share one official Game Action vocabulary.
action_q = engine.ask("When my unit takes damage and then dies, what rules are involved?")
action_map = {(x["name"], x["ruleId"]) for x in action_q.get("mentionedGameActions", [])}
check("take damage normalizes to Deal", ("Deal", "417") in action_map, str(action_map))
check("dies normalizes to Kill", ("Kill", "428") in action_map, str(action_map))
exp_terms = set(action_q["issues"][0]["retrieval"]["queryExpansion"].get("terms", []))
check("retrieval expansion includes official Deal action", "deal" in exp_terms and "game action deal" in exp_terms, str(sorted(exp_terms)))

# Contextual card-markup resolution: [Empower] is Keyword 827 in bracket markup,
# while the same-name Game Action 441 remains an auditable candidate/related concept.
cards_canon = json.loads((ROOT / "data/canonical/cards.json").read_text(encoding="utf-8"))
emp_tokens = [
    t for card in cards_canon["cards"] for t in card.get("textMarkup", [])
    if t.get("baseTerm") == "Empower"
]
check("all bracket Empower tokens resolved", len(emp_tokens) == 51, str(len(emp_tokens)))
check("bracket Empower resolves to keyword", all(t.get("classification") == "keyword" and any(r.get("ruleId") == "827" for r in t.get("conceptRefs", [])) for t in emp_tokens), str(emp_tokens[:2]))
check("bracket Empower preserves action candidate", all(any(r.get("ruleId") == "441" for r in t.get("candidateConceptRefs", [])) for t in emp_tokens), str(emp_tokens[:2]))
check("card markup has no unknown tokens", not cards_canon.get("metadata", {}).get("textAnnotation", {}).get("unknownMarkup"), str(cards_canon.get("metadata", {}).get("textAnnotation", {}).get("unknownMarkup")))

graph_canon = json.loads((ROOT / "data/canonical/knowledge_graph.json").read_text(encoding="utf-8"))
emp_action_edges = [e for e in graph_canon["edges"] if e.get("type") == "KEYWORD_PERFORMS_GAME_ACTION" and e.get("from") == "keyword:empower" and e.get("to") == "action:empower"]
check("Empower keyword explicitly links to Empower action", len(emp_action_edges) == 1 and emp_action_edges[0].get("evidence") == "rule:827.2", str(emp_action_edges))

# Hard-interaction compiler coverage added in continuation build 2.
target_dest = engine.ask("Does playing a unit to a battlefield target that battlefield?")
check("play destination is not automatically a target", (target_dest["issues"][0]["ruling"].get("effectiveVerdict") or {}).get("verdict") == "no", target_dest.get("answer", ""))
untarget_initial = engine.ask("Can I choose a unit that is already Untargetable as the target of my spell?")
check("Untargetable blocks initial target choice", (untarget_initial["issues"][0]["ruling"].get("effectiveVerdict") or {}).get("verdict") == "cannot_target", untarget_initial.get("answer", ""))
untarget_late = engine.ask("If I legally target a unit and it becomes Untargetable after I target it but before the spell resolves, what happens?")
check("late Untargetable causes mistarget", (untarget_late["issues"][0]["ruling"].get("effectiveVerdict") or {}).get("verdict") == "mistargets_on_resolution", untarget_late.get("answer", ""))
linked = engine.ask("If a linked instruction tries to kill a unit that cannot be killed, does the later linked instruction still execute?")
linked_official = {x.get("evidenceId") for x in linked["issues"][0]["retrieval"].get("officialEvidence", [])}
check("linked instruction closes exact FAQ evidence", "O:vendetta-faq-2026-08-14:0035" in linked_official, str(linked_official))
check("compiled linked FAQ ruling is interpreted instead of blanket-blocked", (linked["issues"][0]["ruling"].get("effectiveVerdict") or {}).get("verdict") == "later_executes", linked.get("answer", ""))
replacement = engine.ask("If two replacement effects apply to the same event affecting my unit, who chooses their order?")
check("unrelated curated replacement snippet does not false-block core replacement order", (replacement["issues"][0]["ruling"].get("effectiveVerdict") or {}).get("verdict") == "controller_orders", replacement.get("answer", ""))
copy_case = engine.ask("If I copy an empowered unit, does the copy become empowered too?")
check("copy temporary status uses compiled current FAQ overlay", (copy_case["issues"][0]["ruling"].get("effectiveVerdict") or {}).get("verdict") == "temporary_mod_not_copied", copy_case.get("answer", ""))
layer_case = engine.ask("Can a unit trigger from an intermediate Might value while layers are recalculated?")
check("layer intermediate state uses compiled current FAQ overlay", (layer_case["issues"][0]["ruling"].get("effectiveVerdict") or {}).get("verdict") == "no_intermediate_trigger_window", layer_case.get("answer", ""))
pred_registry = json.loads((ROOT / "data/canonical/predicate_registry.json").read_text(encoding="utf-8"))
check("predicate registry expanded for hard interactions", pred_registry.get("compiledRuleCount", 0) >= 28, str(pred_registry.get("compiledRuleCount")))


# Complete current Vendetta FAQ integrity and effective-override coverage.
overlay_integrity = json.loads((ROOT / "data/validation/current_overlay_integrity.json").read_text(encoding="utf-8"))
check("current overlay integrity passes", overlay_integrity.get("passed") is True and overlay_integrity.get("activeOverlayCount") == 1, str(overlay_integrity))
vendetta_overlay = next((x for x in overlay_integrity.get("sources", []) if x.get("sourceId") == "vendetta-faq-2026-08-14"), {})
check("Vendetta FAQ has all 35 validated sections", vendetta_overlay.get("passed") is True and vendetta_overlay.get("sectionCount") == 35, str(vendetta_overlay))
supplemental_now = json.loads((ROOT / "data/canonical/supplemental_sources.json").read_text(encoding="utf-8"))
vendetta_docs = [x for x in supplemental_now.get("documents", []) if x.get("sourceId") == "vendetta-faq-2026-08-14"]
check("full Vendetta FAQ sections are first-class evidence", len(vendetta_docs) == 35 and all(not x.get("partialSelection") for x in vendetta_docs), str(len(vendetta_docs)))
check("compiled proof obligations no longer require curated FAQ IDs", all("curated-" not in eid for spec in __import__("riftkeep_rules.proof", fromlist=["OBLIGATION_FAMILIES"]).OBLIGATION_FAMILIES.values() for eid in spec.get("officialEvidenceIds", [])), "curated evidence ID remains in proof obligations")
effective_overrides = json.loads((ROOT / "data/canonical/effective_rule_overrides.json").read_text(encoding="utf-8"))
might_override = next((x for x in effective_overrides.get("overrides", []) if x.get("overrideId") == "vendetta-2026-might-copyable"), None)
check("current FAQ compiles explicit Might copyable override", effective_overrides.get("valid") is True and might_override is not None and might_override.get("value") == "Might" and "477.1.b.1.a" in might_override.get("overriddenRuleIds", []), str(effective_overrides))
format_boundary = engine.ask("Can I use Shady Spectacles' copied ability again after reattaching it?")
check("generic can-I-use card ability question is not format legality", "format_legality" not in format_boundary["issues"][0]["proof"].get("obligations", []), str(format_boundary["issues"][0]["proof"]))
deflect_definition = engine.ask("What does Deflect mean?")
check("full FAQ does not false-block generic Deflect definition", deflect_definition["issues"][0]["ruling"].get("status") == "decided", deflect_definition.get("answer", ""))


# Complete current Vendetta FAQ integrity and authority overlay checks (T37).
faq_source_id = "vendetta-faq-2026-08-14"
faq_dir = ROOT / "data/source/snapshots" / faq_source_id
faq_ptr = json.loads((faq_dir / "latest.json").read_text(encoding="utf-8"))
faq_archive = ROOT / faq_ptr["archivePath"]
faq_record_path = ROOT / faq_ptr["snapshotRecord"]
faq_record = json.loads(faq_record_path.read_text(encoding="utf-8"))
faq_archive_sha = hashlib.sha256(faq_archive.read_bytes()).hexdigest()
check("current FAQ archive hash matches pointer", faq_archive_sha == faq_ptr.get("sha256"), str({"archive": faq_archive_sha, "pointer": faq_ptr.get("sha256")}))
check("current FAQ snapshot hash matches pointer", faq_record.get("sha256") == faq_ptr.get("sha256"), str({"record": faq_record.get("sha256"), "pointer": faq_ptr.get("sha256")}))
check("current FAQ snapshot validation passes", bool((faq_record.get("validation") or {}).get("passed")), str(faq_record.get("validation")))
faq_sections = faq_record.get("sections", [])
faq_ids = [x.get("evidenceId") for x in faq_sections]
expected_faq_ids = [f"O:{faq_source_id}:{i:04d}" for i in range(1, 36)]
check("current FAQ has exactly 35 sections", faq_record.get("sectionCount") == 35 and len(faq_sections) == 35, str({"record": faq_record.get("sectionCount"), "actual": len(faq_sections)}))
check("current FAQ evidence IDs are complete and stable", faq_ids == expected_faq_ids and len(set(faq_ids)) == 35, str(faq_ids))
faq_text = "\n".join(x.get("text", "") for x in faq_sections)
for label, anchor in [
    ("authority precedence", "The FAQ is a collection of official rulings."),
    ("Flow/Abandon", "What happens when you play Abandon on a spell that was played for its Flow cost?"),
    ("copy empowered", "What happens if I choose to copy an empowered unit"),
    ("Might copyable", "Might is one of the traits that is managed in the Trait-Altering layer"),
    ("linked instructions", "If I play Ride the Wind targeting my unit at Vilemaw’s Lair"),
    ("negated linkage", "A negated instruction will not cause any linked instructions to be ignored"),
]:
    check(f"current FAQ anchor present - {label}", anchor.casefold() in faq_text.casefold(), anchor)

faq_catalog = json.loads((ROOT / "data/source/official_ruling_catalog.json").read_text(encoding="utf-8"))
faq_catalog_sections = faq_catalog.get("sections", {})
allowed_roles = {"meta", "supplement", "clarification", "card_specific", "errata_note", "override"}
check("FAQ catalog exactly covers current snapshot", set(faq_catalog_sections) == set(faq_ids), str({"catalog": len(faq_catalog_sections), "snapshot": len(faq_ids), "missingCatalog": sorted(set(faq_ids) - set(faq_catalog_sections)), "extraCatalog": sorted(set(faq_catalog_sections) - set(faq_ids))}))
check("FAQ catalog roles are controlled vocabulary", all((v.get("role") in allowed_roles) for v in faq_catalog_sections.values()), str(sorted({v.get("role") for v in faq_catalog_sections.values()})))
check("Might copyability section is explicit override", faq_catalog_sections["O:vendetta-faq-2026-08-14:0030"].get("role") == "override", str(faq_catalog_sections["O:vendetta-faq-2026-08-14:0030"]))
check("linked-instruction section is explicit override", faq_catalog_sections["O:vendetta-faq-2026-08-14:0035"].get("role") == "override", str(faq_catalog_sections["O:vendetta-faq-2026-08-14:0035"]))

supp_current = json.loads((ROOT / "data/canonical/supplemental_sources.json").read_text(encoding="utf-8"))
check("full FAQ snapshot suppresses curated current snippets", supp_current.get("snapshotCount") == 1 and supp_current.get("curatedDocumentCount") == 0 and supp_current.get("documentCount") == 35, str({k: supp_current.get(k) for k in ("snapshotCount", "curatedDocumentCount", "documentCount")}))
check("full FAQ supplemental IDs match snapshot", {x.get("evidenceId") for x in supp_current.get("documents", [])} == set(faq_ids), "supplemental evidence ID mismatch")

authority_current = load_authority_status(ROOT)
check("current gameplay authority is complete", authority_current.get("currentRulesComplete") is True and (authority_current.get("coverage", {}).get("gameplayRulesCurrent") or {}).get("complete") is True, str(authority_current))
check("Vendetta FAQ is the active ingested overlay", authority_current.get("activeOverlays") == [faq_source_id] and authority_current.get("ingestedOverlays") == [faq_source_id], str({"active": authority_current.get("activeOverlays"), "ingested": authority_current.get("ingestedOverlays")}))
manifest_current = json.loads((ROOT / "data/source/official_source_manifest.json").read_text(encoding="utf-8"))
historical_faq_ids = {x.get("id") for x in manifest_current.get("sources", []) if x.get("type") == "official_faq" and x.get("status") == "superseded_history"}
check("historical FAQs are not active overlays", historical_faq_ids.isdisjoint(set(authority_current.get("activeOverlays", []))) and len(historical_faq_ids) >= 3, str({"historical": sorted(historical_faq_ids), "active": authority_current.get("activeOverlays")}))

# Effective current-rule overrides must be declarative, source-linked, and auditable.
effective_overrides = json.loads((ROOT / "data/canonical/effective_rule_overrides.json").read_text(encoding="utf-8"))
check("effective rule override artifact validates", effective_overrides.get("valid") is True and effective_overrides.get("recordCount") == 1 and not effective_overrides.get("errors"), str(effective_overrides))
ovr = next((x for x in effective_overrides.get("overrides", []) if x.get("overrideId") == "vendetta-2026-might-copyable"), None)
check("Might copyability override exists", ovr is not None, str(effective_overrides.get("overrides")))
if ovr is not None:
    check("Might override targets copyable traits", ovr.get("target") == "copyable_traits" and ovr.get("value") == "Might" and ovr.get("kind") == "add_list_member", str(ovr))
    check("Might override cites exact FAQ evidence", ovr.get("sourceEvidenceId") == "O:vendetta-faq-2026-08-14:0030" and ovr.get("sourceSnapshotSha256") == faq_ptr.get("sha256"), str(ovr))
    check("Might override identifies differing Core rule", ovr.get("overriddenRuleIds") == ["477.1.b.1.a"] and "477.1.b.1.a" in by_id, str(ovr))
    section30 = next(x for x in faq_sections if x.get("evidenceId") == "O:vendetta-faq-2026-08-14:0030")
    check("Might override content hash is source section hash", ovr.get("sourceContentHash") == section30.get("contentHash"), str({"override": ovr.get("sourceContentHash"), "section": section30.get("contentHash")}))

out = {"passed": not failures, "checkCount": checks, "failureCount": len(failures), "failures": failures}
(ROOT / "data/validation/core_test_report.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
print(json.dumps(out, indent=2))
raise SystemExit(0 if not failures else 1)
