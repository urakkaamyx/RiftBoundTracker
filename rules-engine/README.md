# RiftKeep Rules Engine — Ground-Zero Milestone

## Canonical roadmap

The user-approved M1–M19 development plan is frozen in [`ROADMAP.md`](ROADMAP.md). Milestone 16 is the latest certified released/recovery-tested checkpoint through T168; Milestone 17 Production Hardening is the current development milestone and is not released yet. Milestone scope must not be silently redefined.

A correctness-first Riftbound rules engine built from the current Core Rules, Tournament Rules, the RiftKeep card corpus, official card errata history, Rules Hub legality, and versioned official-source overlays.

## Safety model

The default CLI is **fail closed** for current gameplay rulings. The Milestone 6 release corpus includes the active Vendetta FAQ as a validated 35-section, immutable authority overlay, so current gameplay authority is complete at this snapshot. If a future manifest declares a newer active overlay that has not been mirrored locally, the engine returns `insufficient` instead of pretending older sources are current authority.

The deterministic engine does not let an LLM invent rule IDs, rule text, card text, citations, or unknown scenario facts. The optional LLM boundary is schema-validated and receives a sealed evidence catalog only.

## Quick start

Requires Python 3.11+ and PyMuPDF.

```bash
python -m pip install -e .
PYTHONPATH=src python -m riftkeep_rules.build
python tests/run_core_tests.py
python tests/run_regressions.py
python tests/run_language_tests.py
python tests/run_scenario_language_tests.py
python tests/run_scenario_model_tests.py
python tests/run_compiler_tests.py
python tests/run_proof_engine_tests.py
python tests/run_llm_interpretation_tests.py
python tests/run_llm_explanation_tests.py
python tests/run_gold_corpus_tests.py
python tests/run_card_interaction_tests.py
python tests/run_product_api_tests.py
python tests/run_update_tests.py
python validate_all.py
python cli.py --status
python cli.py "What does Ganking mean?"
```

If a future update makes current authority incomplete, sync official sources in a networked environment:

```bash
python sync_official_sources.py fetch-all
python tests/run_core_tests.py
python tests/run_regressions.py
python tests/run_language_tests.py
python tests/run_scenario_language_tests.py
python tests/run_scenario_model_tests.py
python tests/run_compiler_tests.py
python tests/run_proof_engine_tests.py
python tests/run_llm_interpretation_tests.py
python tests/run_llm_explanation_tests.py
python tests/run_gold_corpus_tests.py
python tests/run_card_interaction_tests.py
python tests/run_product_api_tests.py
python tests/run_update_tests.py
python validate_all.py
```

For developer/regression work only, an incomplete-authority mode remains available for diagnosing a future unsynced overlay:

```bash
python cli.py --allow-incomplete-authority "By default, can I play a unit to my base?"
```

Do not use that flag to present a ruling as the complete current official answer.

## Current Vendetta FAQ snapshot

The complete substantive FAQ ruling body is compiled into **35 first-class evidence sections** and archived/versioned under `data/source/snapshots/vendetta-faq-2026-08-14/`. The local artifact is a normalized transcription of the official article crawl, not a byte-for-byte HTML mirror. `data/validation/current_overlay_integrity.json` verifies the archive hash, section sequence, required anchors, authority metadata, and ruling-catalog coverage.

The current FAQ clarification that **Might is a copyable trait** is additionally compiled into `data/canonical/effective_rule_overrides.json`, linked back to its exact FAQ evidence section.

## Updating the Core Rules

Never overwrite the live PDF. Stage first, review the generated diff, then promote the exact staged source:

```bash
python update_core_rules.py stage PATH/TO/NEW_CORE_RULES.pdf \
  --source-id core-rules-YYYY-MM-DD \
  --effective-from YYYY-MM-DD

python update_core_rules.py promote --source-id core-rules-YYYY-MM-DD
# If the staged diff contains review-required changes, promotion additionally requires:
# python update_core_rules.py promote --source-id core-rules-YYYY-MM-DD --approve-review
```

The same stage -> review -> promote lifecycle exists in `update_tournament_rules.py`. The live current PDF is hash-bound to its version ledger, so manually swapping it causes build/integrity failure instead of silently changing authority. Stable internal identities are inherited only for safe deterministic matches; additions/removals/ambiguous rewrites/splits/merges remain review-required.

See `docs/OPERATIONS.md` for the complete workflow.


### Additional deterministic interaction coverage

The current compiler includes regression-tested paths for Ready/Exhaust/Stun state repetition, Exhaust costs, Counter consequences, target illegality/mistarget resolution, Untargetable timing, target-vs-permission distinctions, linked-instruction semantics under the current Vendetta FAQ, Replacement Effect ordering, combat-damage replacement timing, Play/Finalize/Resolve checks, trigger-condition snapshots, copy/layer fundamentals, Recall-vs-Move semantics, Conquer/Hold scoring gates, Unit play locations, Contested entry, Hidden/Cleanup lifecycle, damage prevention, Replace-vs-Play, and selected card-text precedence. Rules outside compiled paths remain evidence-only/UNKNOWN rather than guessed.


Current certified M16 baseline: **164/164 core checks, 99/99 ruling regressions, 42/42 player-language checks, 43/43 scenario-language checks, 58/58 generalized Scenario Model checks, 42/42 Rule Compiler checks, 72/72 Proof Engine checks, 84/84 M10 LLM-interpretation checks, 80/80 M11 LLM-explanation checks, 34/34 Gold-corpus checks, 74/74 card-interaction checks, 132/132 Product API checks, 148/148 UI checks, 29/29 update/authority checks, and 70/70 Update Automation checks**. Project audit: **0 critical / 2 known non-blocking historical-archive warnings**.

The current authority layer includes **35 Vendetta FAQ sections** with stable evidence IDs. `data/canonical/effective_rule_overrides.json` currently contains one explicit override: the Vendetta FAQ clarification that **Might is a copyable trait**, sourced to FAQ evidence `O:vendetta-faq-2026-08-14:0030` and linked to Core Rule `477.1.b.1.a`.


### Player-language interpretation

The deterministic pre-LLM interpretation layer transparently maps a narrow set of common TCG terms to Riftbound vocabulary for retrieval/fact extraction only: tap/tapped -> Exhaust/Exhausted, untap/untapped -> Ready, cast/summon -> Play, and graveyard/discard pile -> Trash. Every transformation is returned in `questionInterpretation`; the original question is preserved. Ambiguous terms such as `battle` are surfaced and are deliberately not mapped to Battlefield, Combat, or Showdown. Multipart questions preserve follow-up verbs and carry antecedent game concepts into retrieval context without rewriting the issue itself. Conditional compiled rulings can emit deterministic clarification questions tied to the exact missing predicates.


### Structured scenario language

The deterministic scenario layer extracts players, game-object entities, explicit controller/owner relations, pronoun/demonstrative references, events, and explicit temporal relations. English possessives such as `my unit` are **discourse references only** and do not become game-rule control/ownership facts. Ambiguous references are left unresolved and generate clarification questions; nearest-noun guessing is disabled. `before`, `after`, `while`, and `then` are represented only when explicitly stated, and plain `and` does not invent event order. Named cards resolve to canonical gameplay identities while retaining every matching printing ID for provenance. The scenario assumption ledger is currently always empty by policy: unstated game-state facts are never fabricated.

Run `python tests/run_scenario_language_tests.py` to verify this boundary. The engine exposes the result as `scenarioLanguage`, and the constrained LLM pipeline receives that structure downstream without authority to change it.


### Milestone 6 release gate

The release archive must be reproducible from its bundled sources. Milestone 6 was cleanly extracted, rebuilt, and passed **164/164 core, 99/99 ruling, 42/42 player-language, 43/43 scenario-language, and 29/29 update/authority checks**, plus consolidated validation and project audit (**0 critical / 2 known non-blocking historical-archive warnings**).


### Generalized Scenario Model

Milestone 7 adds `scenarioModel`, a versioned non-adjudicative representation of players, game objects, official zones, Base/Battlefield locations, explicit states, owner/controller relations, pronoun/reference resolution, events, explicit temporal edges, typed unknowns, clarifications, and assumptions. Named cards preserve canonical gameplay identity plus every printing ID. Current-location statements (`unit in Base`) are kept distinct from event destinations (`move unit to Base`). Player-relative zones with no uniquely stated player stay unknown. The model consumes normalized player language but retains the original text and does not apply game rules or advance game state.

Run `python tests/run_scenario_model_tests.py` for the M7 structural safety suite.


### Milestone 7 release gate

Milestone 7 was cleanly packaged/extracted, rebuilt from bundled sources, and passed **164/164 core, 99/99 ruling, 42/42 player-language, 43/43 scenario-language, 58/58 Scenario Model, and 29/29 update/authority checks**, plus consolidated validation and project audit (**0 critical / 2 known non-blocking historical-archive warnings**).


## Generalized Rule Compiler

Milestone 8 adds `data/canonical/compiled_rule_catalog.json`, a structural semantic compilation of all 2,381 Core Rules. Entries include source identity/hash, textual conditions, modalities, effect types, explicit rule dependencies, and compiler confidence, but remain non-executable by default.

Regression-proven semantics may be promoted into guarded declarative Rule Programs in `data/canonical/rule_programs.json`. Each program declares its proof obligation, exact governing rules, required facts, outcomes, applicability rule, and source-text drift guards. If a future Core Rules PDF changes guarded text, the program is disabled rather than silently executing stale logic.

Initial migrated families are Discard→Trash, Replace-not-Play, Ready, Exhaust, Stun, target-vs-permission, combat-damage replacement timing, and trigger-condition snapshot semantics. `data/validation/rule_compiler_metrics.json` tracks structural and executable coverage.


## Proof Engine

Milestone 9 adds a `proofTrace` to each normal issue result. It is a deterministic post-adjudication audit trail, not another answer generator. The trace records accepted/rejected evidence, applicability decisions, authority/precedence, explicit conflict handling, ordered rule/procedure chains, state transitions, dependencies, Rule Program provenance, completeness, and a verification result.

Verification is fail-closed. A decided or conditional ruling must have a selected effective verdict, resolvable basis evidence, complete evidence for known proof obligations, and no unresolved explicit conflict. The verifier never changes or invents a verdict; the engine withholds the answer as `insufficient` if verification fails.

Run `python tests/run_proof_engine_tests.py` for the adversarial M9 suite (72 checks).


### Milestone 9 release gate

Milestone 9 adds deterministic proof verification on top of adjudication. The release baseline is **164 core / 99 rulings / 42 player-language / 43 scenario-language / 58 Scenario Model / 42 Rule Compiler / 72 Proof Engine / 29 update-authority**, with consolidated validation PASS and project audit **0 critical / 2 known historical warnings**.


## M10 Constrained LLM Interpretation

Milestone 10 activates only a sealed interpretation/decomposition capability. The optional model sees the player's question plus transparent deterministic language metadata and may return source-traceable issue spans, non-authoritative paraphrases, search concepts, ambiguity notices, and clarification questions. It does **not** receive rule/card text, rule/evidence IDs, authority state, facts, Scenario Model, proof traces, rulings, or verdicts.

`llmInterpretation` is advisory metadata only in M10. Accepted, rejected, absent, and provider-failure paths are regression-tested to produce identical deterministic facts, Scenario Model, rulings, proof traces, and rendered answers. Legacy LLM evidence-completion, adjudication, and answer-writing entry points are disabled and do not call the provider.

`OpenAICompatibleLocalProvider` is loopback-only (`localhost`, `127.0.0.1`, `::1`), rejects redirects/non-loopback endpoints, bounds response size, and fails closed to deterministic interpretation fallback. See `contracts/LLM_BOUNDARY.md` and `contracts/LLM_PIPELINE.md`.


## M11 Constrained LLM Explanation

Milestone 11 adds an optional post-proof explanation writer. It can run only after M9 proof verification passes. The model receives fixed issue verdicts, deterministic support claims, and per-issue citation allowlists/required citation IDs; it does **not** receive authoritative rule/card/FAQ text.

The validator requires exact issue coverage and verdict equality, enforces required and per-issue citations, and rejects rule-number/evidence-ID text, quotations, authoritative-source claims, prompt-injection output, omitted/duplicated issues, and definitive prose for unresolved issues. Provider absence/error/rejection preserves the existing deterministic answer.

When accepted, the backend prepends the fixed direct conclusion and resolves citation IDs to exact canonical text. Model prose is never used as an authoritative quotation source. The deterministic answer remains available separately as `deterministicAnswer`. See `contracts/LLM_BOUNDARY.md` and `contracts/LLM_PIPELINE.md`.


## Milestone 12 gold corpus

`data/gold/gold_corpus.json` is a frozen 1,846-case corpus. `data/gold/gold_manifest.json` records source hashes and the no-regeneration policy. `generate_gold_corpus.py` is an explicit re-certification tool only; normal validation never invokes it. `tests/run_gold_corpus_tests.py` executes one full adjudication for each of 99 independently expected Gold-A semantic groups, mechanically validates three audited wrapper surfaces per group, directly verifies all Gold-B authority/card/FAQ/errata/version/update cases, and source-validates Gold-C forward fixtures without treating them as current engine claims.


## Milestone 13 card interaction engine

M13 adds `data/canonical/card_interaction_catalog.json`, a structural compilation of all **1,304 card printings** into **937 gameplay identities** and **1,795 typed effective-text clauses**. The structural catalog never adjudicates by itself. It preserves effective-text SHA-256, official errata event provenance, clause spans/hashes, Game Action/keyword references, effect tags, and unresolved deictic/reference terms.

`data/canonical/card_interaction_programs.json` contains **16 human-reviewed executable interaction programs**. A program may affect a ruling only when all of its guards pass: the exact current Core source ID, exact current FAQ-answer hash, every involved gameplay identity's effective-text hash set, required Core Rule IDs, required card-clause semantic tags, a sufficiently strong FAQ interaction match, and complete coverage of every decomposed issue. Any source drift disables the program instead of silently reusing stale semantics.

The 16 promoted interactions are recorded separately in `data/gold/gold_c_promotions.json`. The original M12 `gold_corpus.json` remains frozen and is not rewritten to fit M13. **16/34** Gold-C fixtures are now release-gating; the remaining **18** remain authority-backed/report-only until independently reviewed executors exist.

M13 proof traces preserve `cardInteractionPrograms` including the reviewed program ID, FAQ evidence ID, exact card-clause hashes, source guards, and accepted Core/card/FAQ evidence. Exact quotations are still rendered from backend evidence; the interaction executor never becomes a source of authoritative wording.

Current M13 implementation gate: **164/164 core, 99/99 rulings, 42/42 player language, 43/43 scenario language, 58/58 Scenario Model, 42/42 Rule Compiler, 72/72 Proof Engine, 84/84 LLM interpretation, 80/80 LLM explanation, 34/34 gold-corpus checks over 1,846 cases, 74/74 card-interaction checks, 132/132 Product API checks, and 29/29 update/authority checks**.


## M14 Product API

Milestone 14 adds a stable product-facing service boundary in `src/riftkeep_rules/product_api.py` and a zero-extra-dependency HTTP adapter in `src/riftkeep_rules/api_http.py`. The transport contains no adjudication logic: `RulesEngine` remains authoritative. The API contract is frozen in `contracts/product_api_contract.json`.

Start the local API with:

```bash
python serve_api.py
```

It binds to `127.0.0.1:8765` by default. A non-loopback bind requires the explicit `--allow-remote` flag. Current v1 routes are `/v1/status`, `/v1/search`, `/v1/rules/{family}/{ruleId}`, `/v1/cards/{id-or-exact-name}`, `POST /v1/ask`, `/v1/evidence/{evidenceId}`, `/v1/sources`, and `/v1/changes`. Ask responses expose fixed issue conclusions, clarification prompts, proof-verification status and citation IDs without dumping internal retrieval/predicate state. Exact authoritative evidence is resolved separately by citation ID.

Card lookup is exact-only: a printing ID or exact card name is required; M14 does not introduce fuzzy card identity. Core/Tournament rule IDs that overlap require an explicit family. Request bodies/query parameters are bounded, HTTP errors are stable JSON, and product responses do not expose local filesystem paths. Run `python tests/run_product_api_tests.py` for the 132-check service/HTTP boundary suite.


## RiftKeep UI (M15)

Run `python serve_api.py` and open `http://127.0.0.1:8765/`. The self-contained interface serves from the same loopback origin as Product API v1 and needs no external assets or JavaScript packages. Ask Rules, Search, evidence expansion, exact card/rule detail, authority history, and What Changed views all consume backend API responses; the browser contains no adjudication or evidence-selection logic.


## M16 Update Automation

M16 orchestrates the already validated source-update mechanisms instead of replacing them. Every change is an immutable transaction under `data/update_transactions/<transactionId>/`: candidate bytes are copied and hashed, the live project baseline is fingerprinted, staging/diff happens in an isolated clone, material authority changes require explicit human review, and rehearsal must pass the same complete release gate used for milestone packaging.

A successful rehearsal produces a hash-bound `publish_bundle.zip` containing the **exact bytes that passed**. Publish refuses a stale project baseline, applies only those exact bytes, reruns the full release gate on live, and restores a rollback bundle if the post-publish gate fails. Request/plan/review/rehearsal/publish records are SHA-sealed so transaction routing or approval scope cannot be edited between phases.

Supported candidate kinds are `core_rules_pdf`, `tournament_rules_pdf`, `official_snapshot`, and allowlisted JSON `reviewed_file` companions. New official sources require explicit registration metadata; current overlays additionally require explicit authority scope, precedence, and supersession metadata. The system does not invent authority metadata. Registered-source polling validates the official HTTPS host before any network fetch.

Use the stable CLI:

```bash
python update_automation.py create --spec update.json
python update_automation.py stage --transaction <id>
python update_automation.py approve --transaction <id> --reviewer "Judge Name"
python update_automation.py rehearse --transaction <id>
python update_automation.py publish --transaction <id>
python update_automation.py status --transaction <id>
python update_automation.py poll --source-id <registered-source-id>
```

`rehearse` and `publish` are intentionally expensive in production because each runs the full certified release gate. Run `python tests/run_update_automation_tests.py` for the M16 transaction/adversarial suite.


## Stable 1.0 checkpoint

Stable 1.0 is the certified final M19 checkpoint. Use `python riftkeep.py self-check` for the offline runtime/manifest check and `python riftkeep.py serve` for the UI/API. Product API compatibility remains v1.
