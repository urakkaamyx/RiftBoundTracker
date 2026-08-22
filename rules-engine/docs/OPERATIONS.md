# RiftKeep Rules Engine Operations

## 1. Rebuild and validate

From the project root:

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
python tests/run_ui_integration_tests.py
python tests/run_update_tests.py
python tests/run_update_automation_tests.py
python validate_all.py
```

The build command rebuilds canonical artifacts and the SQLite search index. The five test commands regenerate their reports. `validate_all.py` then verifies parser/errata status, report freshness, source hashes, canonical artifacts, and writes `data/validation/validation_summary.json`.

A green engine validation does **not** mean every online authority source is locally mirrored. Read `operationalReadiness.currentGameplayAuthorityComplete` separately.

## 2. Ask a question

Safe/default mode:

```bash
python cli.py "Can I play a unit to a battlefield I control?"
```

Compact answer only:

```bash
python cli.py --compact "What does Hidden mean?"
```

Source coverage:

```bash
python cli.py --status
```

Developer baseline mode (never present as complete current authority):

```bash
python cli.py --allow-incomplete-authority "QUESTION"
```

## 3. Sync official web sources

The source manifest is `data/source/official_source_manifest.json`. Official HTML snapshots are immutable and hash-addressed. Invalid snapshots are quarantined and cannot advance a source's `latest.json` pointer.

```bash
python sync_official_sources.py fetch-all
```

Current sources only:

```bash
python sync_official_sources.py fetch-all --current-only
```

Import a locally saved official page:

```bash
python sync_official_sources.py import-file \
  --source-id vendetta-faq-2026-08-14 \
  --file PATH/TO/vendetta-faq.html
```

Then rebuild/validate:

```bash
python validate_all.py
```

The fetcher accepts HTTPS from the allowlisted official Riftbound domains only, enforces a size cap, validates expected page structure, and preserves previous versions. FAQs must have usable question/ruling structure; errata snapshots must contain old/new text markers; Rules Hub snapshots must expose the legality section.

## 4. New Core Rules PDF

Do not directly replace the baseline. Stage the candidate first:

```bash
python update_core_rules.py stage NEW.pdf \
  --source-id core-rules-YYYY-MM-DD \
  --effective-from YYYY-MM-DD
```

Review the staged diff and review-required records. Staging never changes live authority. Then promote only the staged source:

```bash
python update_core_rules.py promote --source-id core-rules-YYYY-MM-DD
```

If the diff contains add/remove/ambiguous changes requiring human review, promotion refuses unless the operator explicitly supplies `--approve-review`. The same workflow is available for Tournament Rules through `update_tournament_rules.py stage|promote`.

Possible classifications include `UNCHANGED`, `TEXT_CHANGED`, `RENUMBERED`, `MOVED`, `RENUMBERED_AND_TEXT_CHANGED`, `MOVED_AND_TEXT_CHANGED`, additions/removals, and review-required split/merge/repurpose candidates. Stable internal identities are preserved only for safe matches. Current PDFs are SHA-256 bound to immutable version ledgers, so out-of-band replacement fails integrity checks.

## 5. Card errata

Official errata history is compiled into:

- `data/canonical/official_errata.json`
- `data/canonical/official_errata_history.json`
- `data/validation/errata_validation.json`

The card database's source text is kept distinct from official effective text. Errata records preserve old/new official wording and provenance; they do not claim every promo/alternate printing physically contained the historical old text.

## 6. Current FAQ precedence

A source with `status: current_overlay` is current ruling authority according to its manifest precedence declaration. Its archived sections enter the same searchable evidence index as Core Rules evidence but retain `sourceId`, effective date, authority scope, source URL, and precedence metadata.

If relevant current-overlay evidence is retrieved, the deterministic Core-Rules-only ruling is withheld until that overlay is handled. If the active overlay is not locally mirrored at all, default current gameplay adjudication also fails closed.

Superseded FAQs remain historical material and cannot override current rules.

## 7. Test suites

```bash
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
python tests/run_ui_integration_tests.py
python tests/run_update_tests.py
python tests/run_update_automation_tests.py
```

Current coverage includes parser integrity, all discovered keyword and Game Action roots, sealed LLM evidence contracts, card markup, official-source validation/versioning, errata matching, legality, play-location permissions, Contested/control, prevention, Hidden/Cleanup, card restrictions/precedence, Replace-vs-Play, source edits, and future-rules update safety.

## 8. Failure policy

The system intentionally prefers `conditional`, `insufficient`, or `review required` over an unsupported ruling. Do not repair source anomalies or missing authority by inventing text. Fix the ingestion/source coverage, rebuild, and rerun validation.


## 9. Player-language interpretation

Player-language normalization is an interpretation aid, not authority. `questionInterpretation.original` is retained; `questionInterpretation.text` is the normalized form used for fact extraction, proof planning, retrieval aliases, Game Action detection, and gameplay-vs-format routing. Transformations are auditable. Current conservative aliases include tap/untap, cast/summon, graveyard/discard pile. `battle` is intentionally treated as ambiguous rather than guessed.

Multipart decomposition splits only on explicit question boundaries and safe follow-up conjunctions such as `and is`, `and can`, and `and does`; the leading verb is preserved. Retrieval context may inherit missing antecedent anchors from the first clause, but adjudication still receives the actual follow-up issue.

For compiled conditional rulings, deterministic clarification questions are generated only from explicit missing predicates already used by the proof family. The engine does not ask speculative generic questions.


## 10. Structured scenario language

`scenarioLanguage` is deterministic pre-LLM structure. It records explicit players/entities, discourse possession, explicit control/ownership statements, references, events, temporal relations, unresolved references, clarification questions, and an assumption ledger. Important policies are fail-closed: possessive English does not imply game control/ownership; ambiguous references do not bind to the nearest noun; unstated temporal order is not inferred; assumptions remain empty unless a future separately audited policy is introduced.

Named cards resolve against the real card database to canonical gameplay identities while preserving all printing IDs. Run:

```bash
python tests/run_scenario_language_tests.py
```

Full release validation should finish with both `python validate_all.py` and `python audit_project.py`. The current two audit warnings concern incomplete historical patch-note and superseded-FAQ article bodies only; they do not block current gameplay authority.


## 10. Generalized Scenario Model

`scenarioModel` is structural evidence, not a rules verdict. Its contract is `contracts/scenario_model.schema.json`. It normalizes explicit players/objects/zones/locations/statuses/relations/references/events/temporal edges while preserving provenance and an explicit unknown/assumption ledger. Do not consume `event_destination` as a current location, do not convert discourse possession into game control/ownership, and do not bind ambiguous references without clarification. M8/M9 may consume this structure only through separately tested compiler/proof policies.


## 10. Rule compiler safety

`compiled_rule_catalog.json` is structural only and cannot adjudicate by itself. `rule_programs.json` contains the much smaller set of regression-proven executable semantics. A Rule Program is valid only while every guarded governing rule matches its expected source-text hash and every required evidence rule exists in the proof packet. Compile-time or runtime drift disables execution and leaves the issue for UNKNOWN/legacy handling rather than guessing. Run `python tests/run_compiler_tests.py` after any rule-source or compiler change.


## 11. Proof Engine verification

`proofTrace` is generated after deterministic adjudication. It must not be used to invent a verdict. The verifier checks basis evidence resolution, known-obligation evidence closure, accepted-evidence support, and unresolved explicit conflicts. Procedure-dependent state changes are represented in-order; for example, Cleanup may derive loss of Battlefield control under Rule 323.6 before Rule 323.7 is evaluated.

A verification failure converts a would-be decided/conditional ruling to `insufficient` and records `proofVerificationErrors`; the original adjudication is retained under `baseRuling` for diagnostics. Run `python tests/run_proof_engine_tests.py` after any change to adjudication, proof planning, applicability, precedence, evidence catalogs, Rule Programs, or the proof engine itself.


## 10. M10 LLM interpretation provider

M10 does not require an LLM. With no provider configured, `llmInterpretation` uses deterministic fallback. When a provider is supplied programmatically to `RulesEngine(..., interpretation_provider=...)`, it must satisfy the loopback-only provider policy. Provider output is validated as interpretation metadata and never mutates deterministic adjudication. Run `python tests/run_llm_interpretation_tests.py` to verify the sealed-input, validation, legacy-stage-disable, local-only, fallback, and adjudication-equivalence invariants.


## 11. M11 LLM explanation provider

M11 is optional. Pass a validated loopback `explanation_provider` to `RulesEngine` to enable post-proof prose generation. The provider sees no authoritative source text and cannot change fixed verdicts. Invalid/unavailable output falls back to `deterministicAnswer`. Run `python tests/run_llm_explanation_tests.py` to verify proof gating, verdict/citation immutability, backend quote rendering, multipart direct conclusions, and fallback equivalence.


## Frozen gold corpus

Run `python tests/run_gold_corpus_tests.py` as part of every M12+ release gate. Do **not** run `generate_gold_corpus.py` during normal validation: generation changes the frozen expectations and is only for deliberate reviewed re-certification after authoritative source/fixture changes. A source-hash mismatch is a review event, not a reason to auto-regenerate.


## Card interaction executor safety

The card-interaction catalog is rebuilt from canonical effective card text on every build, but the human-reviewed executor guard literals in `src/riftkeep_rules/card_interaction_executor.py` are **not regenerated**. This is deliberate. If a Core Rules source ID, official FAQ answer, involved card effective text, required rule, or required semantic clause tag changes, the corresponding executor compiles as invalid/non-executable and release validation fails. Review the changed authority/card text before updating a guard.

A matched FAQ is not sufficient by itself to create an executable ruling. The program must exist in the reviewed executor set, pass every source guard, meet exact/paraphrase threshold, and fully cover the current question's issue shape. Unmatched/unpromoted card context remains structural only and follows the pre-M13 adjudication path.

Run:

```bash
python tests/run_card_interaction_tests.py
python tests/run_gold_corpus_tests.py
```

The M13 gold promotion overlay is `data/gold/gold_c_promotions.json`. Do not change expected verdicts by copying current engine output. Promotions are reviewed expectations with `derivedFromEngine: false`; the M12 frozen Gold-C source fixtures remain unchanged.


## Product API operations

Run the M14 API locally with `python serve_api.py`. The default bind is loopback-only (`127.0.0.1:8765`). Use `--host`/`--port` to change the endpoint; a non-loopback host additionally requires `--allow-remote`. The HTTP layer must remain transport-only and delegate to `ProductApiService`; do not add ruling logic to the handler.

The v1 contract is `contracts/product_api_contract.json`. Validate changes with `python tests/run_product_api_tests.py`. The API intentionally uses exact card identity, explicit Core/Tournament rule families where IDs overlap, bounded pagination/body sizes, no-store JSON responses, stable error codes, current-authority fail-closed Ask behavior, and separate evidence resolution for expandable citations.


## RiftKeep UI operation

Start the combined UI/API server with:

```bash
python serve_api.py
```

Then open `http://127.0.0.1:8765/`. Remote binding is disabled unless `--allow-remote` is explicitly supplied. The UI is offline/self-contained and consumes only same-origin `/v1/*` Product API routes. UI static files are limited to `/`, `/index.html`, `/styles.css`, and `/app.js`; arbitrary filesystem paths are never served.


## M16 Update Automation workflow

Use `update_automation.py` for end-to-end authority maintenance. It wraps the existing PDF stage/review/promote and official-source snapshot systems in a transaction; it does not bypass them.

1. `create` copies every candidate into an immutable transaction, hashes it, and records the current source/code baseline fingerprint.
2. `stage` works only in an isolated project clone. Core/Tournament PDFs are parsed/diffed through the existing rule-update engine; official snapshots are validated/versioned through the existing source importer. Live authority is untouched.
3. Material changes and every new rules document require `approve` with an explicit reviewer. New authority registrations require explicit type/status/URL/scope metadata; a new `current_overlay` additionally requires explicit precedence and `supersedesSourceId`.
4. `rehearse` applies the approved candidate only in an isolated clone and runs the **full certified release gate**. A passing rehearsal creates a hash-bound publish bundle of the exact changed bytes.
5. `publish` first refuses input drift or a stale baseline. It creates a rollback bundle, applies only the rehearsed bytes, reruns the full release gate on live, and automatically restores the rollback bundle if that gate fails.
6. `status` exposes the sealed request/plan/review/rehearsal/publish records and whether the transaction baseline is still current.
7. `poll` may capture a registered official HTTPS source into a new immutable transaction. Host validation occurs before the fetch. Polling never directly promotes authority.

Reviewed companion metadata is JSON-only and limited to `data/source/official_ruling_catalog.json`, `data/source/current_authority_overlay.json`, and `data/source/history_sync_plan.json`. Do not expand this allowlist merely to make an update convenient; project code/content changes belong in normal development, not the authority-update channel.

Transaction JSON records are SHA-sealed. Editing request routing, staged plans, human review, rehearsal results, or publish records after they are written invalidates the next phase. No-change transactions never create a publish bundle.

Production rehearsal/publish intentionally run all certified suites plus `validate_all.py` and `audit_project.py`. The M16 release itself adds `tests/run_update_automation_tests.py` to that reusable release gate, so future authority updates cannot regress the updater that is performing them.
