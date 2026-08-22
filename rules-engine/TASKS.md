# RiftKeep Rules Engine — Ground-Zero Execution Checklist

This build pass is complete. A task is marked complete only where the implementation exists and its regression/validation coverage passes.

- [x] **T01 — Freeze and verify current parser/card/graph baseline.** Core Rules: 2,381 numbered rules; Tournament Rules: 935; independent parser validation passes.
- [x] **T02 — Finalize contextual card-text markup classification.** Same-name Keyword/Game Action cases such as Empower are resolved by bracket context while alternate meanings remain auditable; current card corpus has no unknown bracket tokens.
- [x] **T03 — Harden official-source synchronization, immutable snapshot versioning, and authority metadata.** HTTPS + official-host allowlist, size/content validation, quarantine, immutable hash snapshots, in-place diffs, and source authority metadata are implemented/tested.
- [x] **T04 — Parse/apply official card errata without destroying history.** Four official errata releases compile to 63 events, 63 matched identities, 91 affected printings, 0 unresolved; complete old/new/provenance history is retained.
- [x] **T05 — Treat current official FAQ overlays as first-class searchable evidence with explicit precedence.** Search/index/evidence/precedence/fail-closed behavior is implemented and regression tested. This earlier milestone began with the Vendetta FAQ unavailable locally; T31–T40 subsequently ingest and validate the complete current ruling body as a versioned normalized snapshot.
- [x] **T06 — Expand scenario vocabulary/facts and deterministic applicability while preserving TRUE/FALSE/UNKNOWN.** Added Base-vs-Battlefield Unit-play destination, explicit special play-location permission, default-only scope, already-Contested handling, and safe Replace-vs-Play adjudication. Unknown facts remain UNKNOWN.
- [x] **T07 — Expand regression rulings beyond the original 15 cases.** Suite now has 28 passing cases spanning definitions, card restrictions, play locations, Contested/control, prevention, Cleanup/Hidden, Replace-vs-Play, permissions, and timing.
- [x] **T08 — Add update regressions for future Core Rules PDFs and in-place official web edits.** 14 update/authority checks cover no-change PDF baseline, repurposed rule-number review, add/remove review, current FAQ precedence/search, immutable history, and section-level diffs.
- [x] **T09 — Rebuild all canonical data and indexes from source inputs.** Final rebuild passes with parser and errata validation OK.
- [x] **T10 — Run parser/core/regression/update/integrity validation and generate one consolidated report.** `data/validation/validation_summary.json` is green for the engine; current-authority coverage is reported independently.
- [x] **T11 — Add operator documentation.** `README.md` and `docs/OPERATIONS.md` cover install, rebuild, ask, source sync, future-PDF diff, errata, FAQ precedence, tests, and failure/review behavior.
- [x] **T12 — Produce a clean runnable project package after all checks pass.** Milestone package is generated only after the final validation and extraction smoke test.

## Final validation baseline

- Core parser: PASS — 2,381 rules
- Tournament parser: PASS — 935 rules
- Cards: 1,304 records
- Official errata: 63 events / 63 identities / 91 affected printings / 0 unresolved
- Core checks: 164 / 164 PASS
- Ruling regressions: 92 / 92 PASS
- Update/authority checks: 22 / 22 PASS
- Current gameplay authority coverage: **COMPLETE** — the active Vendetta FAQ is locally versioned as a validated 35-section authority overlay. Historical FAQs and patch-note archives remain independently tracked context and do not block current gameplay authority.


## Continuation build — deterministic adjudication expansion

- [x] **T13 — Produce and extraction-smoke-test the runnable milestone ZIP.** The exact packaged tree validates after clean extraction.
- [x] **T14 — Fix gameplay-vs-format legality routing.** Target legality/mistarget questions containing “legal/illegal” no longer route to sanctioned-format ban-list adjudication.
- [x] **T15 — Compile Ready / Exhaust / Stun state interactions.** Already-Ready, already-Exhausted, Exhaust-as-cost, and already-Stunned cases are deterministic and cite the governing Game Action rules.
- [x] **T16 — Compile Counter and mistarget resolution interactions.** Countered items, play-trigger consequences, non-refunded costs, all-target mistargets, and partial mistargets are deterministic.
- [x] **T17 — Compile Recall-vs-Move semantics.** Recall is distinguished from Move for triggers and movement restrictions.
- [x] **T18 — Compile Conquer / Hold scoring gates.** Once-per-Battlefield-per-turn scoring and the defining Conquer/Hold conditions are evaluated with TRUE/FALSE/UNKNOWN facts.
- [x] **T19 — Expand deterministic ruling regressions from 28 to 42.** All 42 pass after the new compiler paths.
- [x] **T20 — Rebuild canonical artifacts, re-run all parser/core/ruling/update validation, and repackage.** That milestone validated the fail-closed source-coverage behavior; T31–T40 subsequently closed the current FAQ authority gap.

## Continuation build 2 — hard interaction families

- [x] **T21 — Compile targeting vs permission/restriction and Untargetable legality.** Distinguish targets from locations used only as action permissions/restrictions; handle Untargetable both before finalization and after a target has already been chosen.
- [x] **T22 — Compile current linked-instruction semantics.** Preserve the Core Rules linkage model while applying the current Vendetta FAQ distinction between mistargeted/ignored instructions and prevented/replaced/impossible (negated) instructions.
- [x] **T23 — Compile replacement-effect ordering and simultaneous-event handling.** Evaluate who orders multiple replacement effects and treat simultaneous replaceable events separately per the Core Rules.
- [x] **T24 — Compile combat-damage replacement timing.** Replacement effects that would apply to resulting combat damage are applied during combat damage assignment.
- [x] **T25 — Compile Play/Finalize/Resolve meaning differences.** Distinguish triggered “when played” checks from non-triggered checks that reference Finalized cards, including the effect of Countering.
- [x] **T26 — Compile triggered-information snapshot semantics.** Information referenced from a trigger condition is checked when the trigger condition is fulfilled, not re-read on resolution unless a rule says otherwise.
- [x] **T27 — Compile copy/layer fundamentals and no-intermediate-state behavior where authority supports it.** Separate copyable traits from temporary state/modifications and preserve current FAQ-only clarifications as overlay-dependent evidence.
- [x] **T28 — Expand ruling regressions from 42 to at least 58 cases.** Completed at 64 cases, including positive, negative, UNKNOWN/conditional, and current-FAQ-backed cases across T21–T27.
- [x] **T29 — Rebuild canonical artifacts and run all parser/core/ruling/update validation.** No milestone is accepted with a regression or integrity failure.
- [x] **T30 — Update milestone docs and produce/extraction-test the next runnable ZIP.** Package only the validated tree; keep current-authority completeness separate from engine validation.

## Continuation build 3 — complete current authority + FAQ compiler

- [x] **T31 — Ingest the complete current Vendetta FAQ as an immutable versioned official-source snapshot.** Validate source identity, publication metadata, article completeness, stable section extraction, and authority precedence before marking the overlay complete.
- [x] **T32 — Recompute current authority coverage and make strict/default gameplay adjudication usable only if every active overlay is locally complete.** Keep fail-closed behavior for any missing or corrupt authority source.
- [x] **T33 — Audit the full Copy / Might / layer rule family against the current FAQ.** Correct any earlier incomplete interpretation of `477.*` and add regressions around copyable traits versus temporary modifications.
- [x] **T34 — Compile the remaining high-value Vendetta FAQ ruling families.** Cover Flow/Abandon, replacement event existence/inheritance, Rebuttal choice remaking, Attach sequencing, multi-type reflexive triggers, naming, Empower stacking, controller-at-resolution/finalization, state-transition triggers, Deflect, delayed attribution, and play-location finalization legality.
- [x] **T35 — Make full FAQ sections first-class evidence and remove dependence on curated paraphrase snippets wherever the complete source supports the ruling.** Preserve curated records only as migration/history fixtures.
- [x] **T36 — Expand deterministic regression coverage substantially and include contradictory/UNKNOWN cases.** Every newly compiled FAQ family must have positive plus boundary coverage.
- [x] **T37 — Add source-integrity and authority tests for the complete Vendetta FAQ.** Test snapshot hashing, section count/anchors, precedence, strict-mode completeness, stale/superseded behavior, and edited-in-place diff behavior.
- [x] **T38 — Rebuild every canonical artifact and index from source.** No hand-edited generated artifacts may be required for a clean build.
- [x] **T39 — Run the complete parser/core/ruling/update/authority validation suite.** Fix all regressions before packaging.
- [x] **T40 — Update documentation/milestone metadata and package/extraction-test the exact validated project tree.**

## Continuation build 3 result

- Current Vendetta FAQ: 35 / 35 versioned searchable sections with immutable source hash and evidence IDs.
- Current gameplay authority: COMPLETE.
- Declarative effective overrides: 1 (`vendetta-2026-might-copyable`, sourced to FAQ section `0030`, affecting Core Rule `477.1.b.1.a`).
- Compiled applicability registry: 28 predicates.
- Core/system checks: 164 / 164 PASS.
- Deterministic ruling regressions: 92 / 92 PASS.
- Update/authority checks: 22 / 22 PASS.
- Milestone 4 must pass the same suite after clean ZIP extraction before release.

## Continuation build 3 completion baseline

- Current Vendetta FAQ: 35 / 35 classified searchable sections, immutable snapshot hash validated
- Effective current FAQ overrides: 1 machine-readable override (`Might` added to current copyable traits, overriding the conflicting Core Rules list where applicable)
- Core/system checks: 164 / 164 PASS
- Ruling regressions: 92 / 92 PASS
- Update/authority checks: 22 / 22 PASS
- Current gameplay authority: COMPLETE
- Tasks completed through: T40

## Continuation build 4 — player-language interpretation without an LLM

- [x] **T41 — Add transparent player-language normalization.** Common non-Riftbound TCG phrasing may map to official vocabulary for interpretation/retrieval, but every transformation must be reported and the original question must remain intact.
- [x] **T42 — Use normalized interpretation text consistently for facts, proof obligations, retrieval aliases, and Game Action detection without changing authoritative evidence.**
- [x] **T43 — Improve deterministic multi-issue decomposition while preserving antecedent context.** Add safe follow-up conjunctions and regression-test multipart player questions.
- [x] **T44 — Add deterministic clarification requests for conditional rulings.** Ask for a concrete missing game-state fact instead of leaving a generic UNKNOWN explanation where a known predicate can identify what is missing.
- [x] **T45 — Expand regressions with colloquial/player-style questions and ambiguity boundaries.** Include cast/summon, tap/untap, graveyard/trash wording, multipart questions, and an unmapped ambiguous term that must not be silently reinterpreted.
- [x] **T46 — Rebuild, run all validation, update milestone metadata, and package/extraction-test Milestone 5.**


## Milestone 5 validation baseline

- Core parser: PASS — 2,381 rules
- Tournament parser: PASS — 935 rules
- Cards: 1,304 records
- Official errata: 63 events / 91 affected printings / 0 unresolved
- Current Vendetta FAQ: 35 / 35 searchable sections; integrity PASS
- Core/system checks: 164 / 164 PASS
- Deterministic ruling regressions: 99 / 99 PASS
- Player-language / ambiguity checks: 42 / 42 PASS
- Update/authority checks: 22 / 22 PASS
- Current gameplay authority: COMPLETE
- Tasks completed through: T46

## Recovery audit checkpoint — post-Milestone-5 layer restored

- [x] Restored immutable Core/Tournament rule-version ledgers.
- [x] Restored live-current PDF hash protection.
- [x] Restored Core and Tournament stage -> diff -> review -> promote workflows.
- [x] Restored dynamic current-source IDs in the build pipeline.
- [x] Restored project audit tooling and rule-version integrity validation.
- [x] Restored update/authority regression baseline from 22 to 29 checks.
- [x] Full recovered baseline: 164 core / 99 ruling / 42 language / 29 update PASS; project audit 0 critical / 2 known history warnings.

## Continuation build 5 — structured scenario language

- [x] **T47 — Add dedicated scenario-language unit/regression tests.** Test entity extraction, explicit control/ownership, pronouns, ambiguity, multiple antecedents, named-card entities, and the no-assumption policy.
- [x] **T48 — Integrate scenario-language output into normal question analysis / engine results.** Preserve original text and existing player-language normalization output.
- [x] **T49 — Harden temporal sequencing.** Cover before/after/while/then, multiple events, clause boundaries, and refuse unsafe inferred ordering.
- [x] **T50 — Add multi-player/controller/owner/opponent relationship handling.** English possessives such as “my unit” are discourse references only; they must not silently become game-rule control/ownership facts.
- [x] **T51 — Add unresolved-reference clarification generation.** Ambiguous `it` / `that card` / `they` references ask for clarification instead of binding to the nearest noun blindly.
- [x] **T52 — Propagate an explicit assumption ledger.** The deterministic scenario layer reports zero assumptions unless a separately audited policy intentionally creates one.
- [x] **T53 — Add multi-card question tests using the real card database.** Resolve canonical gameplay identities while retaining all matching printing IDs/provenance.
- [x] **T54 — Run every existing suite plus the scenario-language suite.** Preserve at least 164 core / 99 ruling / 42 language / 29 update checks and project-audit cleanliness.
- [x] **T55 — Update milestone docs and build/extract/retest Milestone 6.** Do not release until the exact ZIP passes rebuild, all suites, consolidated validation, and project audit.


## Milestone 6 release gate

- Exact candidate ZIP clean extraction: PASS
- Rebuild from bundled sources: PASS
- Core/system checks: 164 / 164 PASS
- Deterministic ruling regressions: 99 / 99 PASS
- Player-language checks: 42 / 42 PASS
- Structured scenario-language checks: 43 / 43 PASS
- Update/authority checks: 29 / 29 PASS
- Consolidated validation: PASS
- Rule-version integrity: PASS
- Project audit: 0 critical / 2 known non-blocking historical-archive warnings
- Tasks completed through: T55

## Milestone 7 — Generalized Scenario Model

- [x] **T56 — Freeze the canonical M1–M19 roadmap.** Store the user-approved milestone purposes/statuses in `ROADMAP.md`; future scope changes must be explicit rather than silently drifting.
- [x] **T57 — Define the generalized Scenario Model contract.** Add a versioned schema for players, objects, zones, locations, states, relations, references, events, temporal edges, unknowns, clarifications, provenance, and assumptions.
- [x] **T58 — Normalize scenario-language entities into stable scenario objects.** Preserve named-card gameplay identity and every printing ID while assigning stable per-scenario object IDs and object kinds.
- [x] **T59 — Model official Riftbound zones and locations.** Represent Board/Non-Board zones, player-relative zones, Bases/Battlefields as locations, current-location statements, and event destination/source locations without conflating them.
- [x] **T60 — Model explicit object states without inference.** Capture stated Ready/Exhausted/Stunned/Hidden/Empowered/Contested/Temporary/attacker/defender states with source spans and never infer unstated status.
- [x] **T61 — Normalize owner/controller/player relations.** Carry only explicit game-control/game-ownership relations into the Scenario Model; keep English possessives as discourse provenance unless the wording explicitly establishes a game relation.
- [x] **T62 — Normalize references and temporal sequencing into the Scenario Model.** Preserve resolved/ambiguous/unresolved pronouns and explicit before/after/while/then edges; never create temporal order from plain conjunction.
- [x] **T63 — Add explicit unknown/assumption provenance.** Unresolved references and model slots become typed unknowns/clarifications; assumption ledger remains empty unless a separately audited policy adds an assumption.
- [x] **T64 — Integrate `scenarioModel` into normal engine results without changing rulings yet.** M7 structures game state for later M8/M9 consumption; it must not silently change adjudication semantics during this milestone.
- [x] **T65 — Build an adversarial Scenario Model regression suite.** Cover multiple players/cards, zones, locations, status states, controller changes, event destinations, pronouns, temporal chains, and no-assumption boundaries using real card identities.
- [x] **T66 — Run full M7 regression/rebuild/audit gate.** Preserve all M6 baselines plus the new Scenario Model suite; consolidated validation and project audit must stay clean.
- [x] **T67 — Package/extract/rebuild/retest Milestone 7.** Release only if the exact archive reconstructs from bundled sources and passes every suite/audit.


## Milestone 7 release gate

- Exact candidate ZIP clean extraction: PASS
- Rebuild from bundled sources: PASS
- Core/system checks: 164 / 164 PASS
- Deterministic ruling regressions: 99 / 99 PASS
- Player-language checks: 42 / 42 PASS
- Scenario-language checks: 43 / 43 PASS
- Generalized Scenario Model checks: 58 / 58 PASS
- Update/authority checks: 29 / 29 PASS
- Consolidated validation: PASS
- Rule-version integrity: PASS
- Project audit: 0 critical / 2 known non-blocking historical-archive warnings
- Tasks completed through: T67


## Milestone 8 — Generalized Rule Compiler

- [x] **T68 — Define the generalized compiler contract.** Compile every Core rule into source-bound structural semantics while preserving a safe non-executable default.
- [x] **T69 — Harden conditions and modalities.** Distinguish permissions, prohibitions, requirements, restrictions, replacements, triggers, targeting, movement, costs, and state/status effects without `can`/`can't` ambiguity.
- [x] **T70 — Compile all Core Rules into the semantic catalog.** Preserve source identity/hash, rule dependencies, confidence, conditions, and effect classifications for all 2,381 rules.
- [x] **T71 — Add source-guarded executable Rule Programs.** Programs execute only when exact governing source rules still match their frozen source guards.
- [x] **T72 — Add the declarative Rule Program evaluator and runtime drift shutdown.** Source drift disables stale executable semantics rather than guessing.
- [x] **T73 — Migrate proven adjudication families to Rule Programs.** Move selected simple families out of handwritten adjudicator branches while preserving verdict parity.
- [x] **T74 — Remove migrated legacy branches.** Ensure the migrated families have a single declarative implementation rather than duplicate code paths.
- [x] **T75 — Add compiler metrics and adversarial compiler tests.** Validate structural coverage, program guards, evaluator behavior, and drift rejection.
- [x] **T76 — Run full M8 regression/rebuild/audit gate.** Preserve all M7 suites plus the compiler suite and project-audit cleanliness.
- [x] **T77 — Package/extract/rebuild/retest Milestone 8.** Release only after the exact archive passes every suite/audit.

## Milestone 9 — Proof Engine / Complete Adjudication

- [x] **T78 — Define the versioned Proof Trace contract.** Record accepted/rejected evidence, applicability, precedence, conflicts, ordering, transitions, dependencies, and verification state.
- [x] **T79 — Build deterministic evidence accounting.** Explain why evidence was accepted or rejected rather than returning only a rule-ID list.
- [x] **T80 — Add applicability matrix tracing.** Preserve TRUE/FALSE/UNKNOWN applicability decisions and their predicates/reasons.
- [x] **T81 — Add precedence/conflict tracing.** Make Core/FAQ/card/competition authority decisions explicit and auditable.
- [x] **T82 — Trace current FAQ and card-text precedence.** Ensure effective conclusions show which authority displaced or supplemented another.
- [x] **T83 — Trace ordered procedures and derived state transitions.** Later proof steps must evaluate against post-step state where required.
- [x] **T84 — Add deterministic proof verification and fail-closed behavior.** Unsupported/tampered decided answers become insufficient rather than being silently repaired.
- [x] **T85 — Preserve Rule Program provenance in proofs.** A proof records the guarded executable program that produced a program-backed outcome.
- [x] **T86 — Build adversarial proof-engine tests.** Cover tampered basis IDs, unresolved conflicts, unknown applicability, precedence, ordered Cleanup/replacement chains, and provenance.
- [x] **T87 — Run full M9 regression/rebuild/audit gate.** Preserve every M8 suite plus the proof-engine suite.
- [x] **T88 — Package/retest/recovery-certify Milestone 9.** Exact final archive and recovery restore must pass before M10.

## Milestone 10 — LLM Interpretation Layer

- [x] **T89 — Lock the interpretation-only LLM boundary.** Disable legacy LLM adjudication, evidence completion, and answer writing for M10.
- [x] **T90 — Define the sealed interpretation input contract.** The model receives player language only, not rules, card text, proof, authority, facts, or verdicts.
- [x] **T91 — Define the constrained interpretation output contract.** Permit issue spans/paraphrases/search concepts/ambiguity/clarification hints only.
- [x] **T92 — Add strict output validation and whole-output rejection.** Reject invented facts, bindings, citations, rule IDs, verdicts, assumptions, unsafe temporal/controller/owner claims, and prompt-injection payloads.
- [x] **T93 — Add loopback-only provider execution and deterministic fallback.** Provider failure or invalid output cannot affect deterministic behavior.
- [x] **T94 — Integrate `llmInterpretation` without adjudication authority.** Normal results expose validated hints while `llmUsedForAdjudication` remains false.
- [x] **T95 — Prove deterministic state/ruling/proof immutability across accepted/rejected/provider-failure paths.**
- [x] **T96 — Build the adversarial M10 safety suite.** Verify sealed packets, endpoint restrictions, legacy-stage shutdown, injection rejection, and fallback behavior.
- [x] **T97 — Run full M10 regression/rebuild/audit gate.** Preserve all M9 suites plus the interpretation safety suite.
- [x] **T98 — Package/retest/recovery-certify Milestone 10.** Exact final archive and full recovery restore must pass before M11.

## Milestone 11 — LLM Explanation Layer

- [x] **T99 — Lock the post-proof explanation boundary.** Explanations may run only after deterministic proof verification succeeds.
- [x] **T100 — Define the sealed explanation input packet.** Provide fixed verdicts, deterministic support claims, and citation allowlists without authoritative source text.
- [x] **T101 — Enforce verdict immutability and per-issue citation boundaries.**
- [x] **T102 — Require decisive citations and backend-owned exact quote rendering.** The model cannot invent or quote authoritative text.
- [x] **T103 — Reject rule-number/quote smuggling, foreign citations, missing required citations, and unverified-proof input.**
- [x] **T104 — Preserve deterministic facts/evidence/proofs/rulings byte-equivalently when explanation prose changes.**
- [x] **T105 — Add deterministic explanation fallback.** Provider absence/failure cannot remove the backend answer.
- [x] **T106 — Build the adversarial M11 explanation suite.**
- [x] **T107 — Run full M11 regression/rebuild/audit gate.** Preserve all M10 suites plus explanation safety.
- [x] **T108 — Package/retest/recovery-certify Milestone 11.**

## Milestone 12 — Large Gold Test Corpus

- [x] **T109 — Define the versioned gold-case schema and provenance model.** Expectations must be independently specified and never derived from current engine output.
- [x] **T110 — Establish Gold A release-gating adjudication cases.** Preserve locked expected verdict/evidence across 99 semantic groups and controlled surface forms.
- [x] **T111 — Establish Gold B authority/integrity cases.** Cover current FAQ sections, all real card records, official errata, rule versions, and update fixtures.
- [x] **T112 — Establish Gold C forward card-interaction fixtures.** Authority-backed future interactions remain report-only until explicitly promoted.
- [x] **T113 — Freeze anti-self-fulfilling source hashes.** Source drift requires deliberate review/re-certification.
- [x] **T114 — Add globally unique authoritative case IDs.** Prevent lossy ID sanitization/collisions across cards/FAQ/errata/version/update fixtures.
- [x] **T115 — Optimize the gold runner without weakening semantic coverage.** Run one full adjudication per semantic group and verify audited wrapper equivalence.
- [x] **T116 — Add gold coverage metrics and minimum thresholds.**
- [x] **T117 — Make the frozen gold corpus mandatory in consolidated validation/project audit.**
- [x] **T118 — Verify Gold-A/Gold-B release gates and Gold-C report-only behavior.**
- [x] **T119 — Run full M12 implementation regression/rebuild/audit gate.**
- [x] **T120 — Build/extract/retest the M12 candidate archive.**
- [x] **T121 — Release/retest/recovery-certify M12 and rotate retention to the latest two certified milestones.**

## Milestone 13 — Card Interaction Engine

- [x] **T122 — Define the card-interaction catalog contract and effective-text provenance.**
- [x] **T123 — Compile all effective card printings into gameplay identities and typed interaction clauses.**
- [x] **T124 — Compile all substantive current FAQ card interactions into source-bound programs.**
- [x] **T125 — Bind exact FAQ questions to their authority programs while rejecting generic/ambiguous false matches.**
- [x] **T126 — Integrate structural `cardInteractionContext` as non-adjudicative context.**
- [x] **T127 — Harden card identity matching for possessives and contained/overlapping names without fuzzy invention.**
- [x] **T128 — Build structural/adversarial card-interaction tests and preserve non-adjudicative safety.**
- [x] **T129 — Add reviewed source-guarded interaction executors.** Freeze Core/FAQ/card-text/rule/clause guards and distinguish Return-to-Hand from Recall.
- [x] **T130 — Integrate fully covering executors into adjudication and M9 proof provenance with source-drift shutdown.**
- [x] **T131 — Promote only fully proven Gold-C interactions to release-gating status.** Keep unpromoted interactions report-only.
- [x] **T132 — Expand M13 executor/adversarial tests and Gold promotion verification.**
- [x] **T133 — Run full M13 regression/rebuild/audit gate and repair durable milestone/task history.**
- [x] **T134 — Package/retest/recovery-certify Milestone 13 and rotate retention.**

## Milestone 14 — Search / Ask-Rules Product API

- [x] **T135 — Define the stable Product API contract/error model.** Keep internal engine implementation details out of public responses.
- [x] **T136 — Add status/current-authority/source summary.**
- [x] **T137 — Add unified bounded search over the existing canonical index.**
- [x] **T138 — Add exact family-aware rule lookup.** Overlapping Core/Tournament IDs require explicit family selection.
- [x] **T139 — Add exact card lookup with gameplay identity, printing variants, effective text, and provenance.**
- [x] **T140 — Add Ask-Rules API responses with verified fixed verdicts, clarifications, proof state, and citation IDs.**
- [x] **T141 — Add evidence resolution, immutable source/version history, and What Changed APIs.**
- [x] **T142 — Add a zero-extra-dependency loopback HTTP adapter with bounded bodies and stable JSON errors.**
- [x] **T143 — Build adversarial service/real-HTTP Product API tests.**
- [x] **T144 — Run full M14 regression/rebuild/audit gate.**
- [x] **T145 — Package/retest/recovery-certify Milestone 14 and rotate retention to M13 + M14.**

## Milestone 15 — RiftKeep UI Integration

- [x] **T146 — Freeze the UI/API boundary.** The browser renders Product API data only and contains no adjudication/evidence-selection/rule-semantics logic.
- [x] **T147 — Build the accessible offline application shell.** Same-origin assets, landmarks, keyboard/focus behavior, labels, live regions, and responsive layout.
- [x] **T148 — Implement Ask Rules surface.** Render multipart conclusions, proof state, deterministic clarification prompts, and expandable backend evidence.
- [x] **T149 — Implement unified Search surface.** Browse rules/cards/current rulings/errata/sources through the M14 API.
- [x] **T150 — Implement exact Card and Rule detail views.** Preserve printing variants, provenance, and Core/Tournament family selection.
- [x] **T151 — Implement Sources, version history, and What Changed views.**
- [x] **T152 — Complete responsive/accessibility interaction behavior and recent-question convenience.**
- [x] **T153 — Harden static serving/security.** Exact route allowlist, same-origin policy, CSP/security headers, no external runtime dependencies, no dynamic HTML injection, no filesystem exposure.
- [x] **T154 — Build adversarial UI integration tests against real served assets and live same-origin API routes.**
- [x] **T155 — Run full M15 implementation regression/rebuild/audit gate.** Preserve all M14 gates plus the UI suite.
- [x] **T156 — Package/extract/rebuild/retest/recovery-certify Milestone 15 and rotate retention to M14 + M15.**

## Milestone 16 — Update Automation

- [x] **T157 — Define the immutable update-transaction contract and baseline fingerprint.** Transactions copy candidate inputs, record hashes/provenance, and become stale if the project changes after rehearsal.
- [x] **T158 — Add registered official-source detection/capture.** Support local candidate files and safe optional polling of allowlisted official HTTPS sources without advancing live snapshot pointers.
- [x] **T159 — Stage/diff every supported source in an isolated worktree.** Core/Tournament PDFs use the existing stable-ID diff engine; Rules Hub/FAQ/patch/errata sources use immutable official-snapshot comparison and validation.
- [x] **T160 — Enforce explicit review policy for material authority/card-text changes.** No changed Core/Tournament/current FAQ/Rules Hub/errata source may publish without a durable human approval record.
- [x] **T161 — Rehearse the complete update in isolation.** Apply/promote approved candidates, rebuild canonical/index outputs, compile authority/errata/card interactions, and run the full certified release gate.
- [x] **T162 — Add stale-transaction detection, publish diff, and rollback-safe live promotion.** Refuse publish if the live baseline differs from the rehearsed baseline; preserve rollback material and verify copied file hashes.
- [x] **T163 — Add post-publish validation and machine-readable publish manifests.** A publish is successful only if live validation/audit remain green; otherwise rollback.
- [x] **T164 — Add a stable Update Automation CLI.** Create/status/stage/approve/rehearse/publish/poll operations must return bounded JSON and never require direct file surgery.
- [x] **T165 — Add adversarial M16 automation tests.** Cover no-op inputs, parser/source validation failures, review-required changes, source drift, stale baselines, failed rehearsal, rollback, official-source host restrictions, and successful synthetic promotion.
- [x] **T166 — Make Update Automation artifacts/tests mandatory in consolidated validation and project audit.**
- [x] **T167 — Run the full M16 implementation regression/rebuild/audit gate.** Preserve every M15 suite plus the M16 automation suite.
- [x] **T168 — Package/extract/rebuild/retest/recovery-certify Milestone 16 and rotate retention to M15 + M16.**

## Milestone 17 — Production Hardening

- [x] **T169 — Define the production-runtime hardening contract and baseline diagnostics.** Freeze required runtime artifacts, index schema version, fail-closed policies, cache bounds, offline-serving policy, and measurable runtime health fields.
- [x] **T170 — Make canonical/update writes and search-index replacement crash-safe.** Use same-directory atomic replace with fsync where supported; build/validate SQLite in a temporary file before replacing the live index.
- [x] **T171 — Add startup/runtime integrity guards.** Validate required JSON/schema artifacts, Core/Tournament source-version integrity, current overlay integrity, SQLite quick-check/user-version, and fail startup on corruption.
- [x] **T172 — Harden read concurrency and caching.** Use read-only/query-only SQLite connections, bounded thread-safe LRU caches, immutable result copies, and deterministic cache diagnostics without caching adjudication/LLM results.
- [x] **T173 — Add runtime drift fail-closed behavior.** Detect on-disk authority/canonical/index changes after service startup; status reports degraded state while search/lookup/ask refuse mixed old/new snapshots until restart/reload.
- [x] **T174 — Add HTTP runtime diagnostics.** Per-request IDs, bounded thread-safe request/error/concurrency counters, sanitized server behavior, and no filesystem/secret leakage.
- [x] **T175 — Enforce offline serving and explicit-network boundaries.** Normal Ask/Search/UI/runtime integrity must require no network; only explicit LLM provider calls and M16 polling/update actions may open sockets.
- [x] **T176 — Add migration/index-schema and corruption recovery tests.** Unknown index schema, corrupt SQLite, partial JSON, interrupted index rebuild, and runtime drift must fail closed while preserving the last good live artifact.
- [x] **T177 — Build adversarial M17 performance/concurrency/hardening suite.** Cover cache bounds/hits/evictions, concurrent search/ask reads, read-only DB enforcement, atomic-write failure safety, startup corruption, drift detection, offline serving, HTTP request IDs, and deterministic responses.
- [x] **T178 — Make Production Hardening artifacts/tests mandatory in consolidated validation and project audit.**
- [x] **T179 — Run the full M17 implementation regression/rebuild/audit gate.** Preserve every M16 suite plus the M17 hardening suite.
- [x] **T180 — Package/extract/rebuild/retest/recovery-certify Milestone 17 and rotate retention to M16 + M17.**


## Pre-M18 Definition Lookup Hotfix

- [x] **P17-D1** Recognize exact-concept `What does X do?` definition phrasing without hijacking scenario questions.
- [x] **P17-D2** Add conservative singular/plural concept aliases such as `Recall` → Core heading `Recalls`.
- [x] **P17-D3** Seal full definition rule-family evidence into M9 proof catalogs before verification.
- [x] **P17-D4** Add a 120-check Definition Lookup suite covering all current keywords, Game Actions, ordinary named rule concepts, morphology, parameterized keywords, dual-meaning Empower, and false-positive boundaries.
- [x] **P17-D5** Promote Definition Lookup to the certified release gate; M16+ automated update rehearsals must pass 17 suites.


## Milestone 18 — Release Candidate / Full Audit

- [x] **T181 — Freeze the M18 audit charter and architecture-promise matrix.** Map every M1–M17 promise plus the pre-M18 Definition Lookup hotfix to required artifacts, tests, authority evidence, and release criteria; classify blocking vs non-blocking findings.
- [x] **T182 — Run a complete source-authority and provenance audit.** Verify current Core/Tournament/card/FAQ/errata hashes, precedence, effective overlays, historical retention declarations, source IDs, and fail-closed authority completeness.
- [x] **T183 — Run a clean corpus/reproducibility audit.** Reparse/rebuild in isolation, prove counts/stable IDs/source hashes/index schema, compare canonical output hashes, and identify every intentionally non-byte-stable artifact.
- [x] **T184 — Audit adjudication/proof/definition coverage against the complete regression and Gold corpus.** Map rule families, definitions, FAQ sections, card interactions, negative/conditional cases, ambiguity, and the 18 remaining report-only Gold-C fixtures.
- [x] **T185 — Execute the full update-lifecycle simulation matrix.** Core, Tournament, FAQ/article, reviewed metadata, no-op, material change, invalid source, stale baseline, failed rehearsal, successful publish, and rollback.
- [x] **T186 — Execute clean-install/offline rebuild and startup audit.** Fresh extraction with no caches/network; rebuild, startup integrity, API/UI serving, read-only SQLite, definition lookup, and runtime snapshot guarantees.
- [x] **T187 — Build end-to-end adversarial release-candidate tests.** Cross-layer tampering, corrupted artifacts, stale reports, source drift, runtime drift, malformed API/UI input, concurrency, definition false positives, and LLM boundary attacks.
- [x] **T188 — Audit product/API/UI contract parity end-to-end.** Every user-visible conclusion/definition/citation/source/change view must trace to Product API/backend authority with no browser-side rule logic.
- [x] **T189 — Audit recovery/retention and disaster-recovery promises.** Latest-two milestone retention, no recursive backups/candidates, bootstrap completeness, exact ZIP restore hash, and green recovered active tree.
- [x] **T190 — Produce a machine-readable M18 conformance report.** Aggregate all promise checks/findings with severity, evidence pointers, waivers, and explicit release blockers.
- [x] **T191 — Resolve every Critical/High M18 finding or explicitly block release.** No Critical/High finding may be waived silently.
- [x] **T192 — Make the M18 release-candidate audit suite mandatory in validation, project audit, and the automated update release gate.**
- [x] **T193 — Run the complete M18 implementation gate.** Preserve all 17 recovered M17 Revision 2 suites plus the M18 release-candidate audit suite, consolidated validation, and project audit.
- [x] **T194 — Package/extract/rebuild/retest/recovery-certify Milestone 18 and rotate retention to M17 + M18.**

## Milestone 19 — Stable RiftKeep Rules Engine 1.0

- [x] **T195 — Freeze the Stable 1.0 release/compatibility contract.** Product version 1.0.0, Product API v1, SQLite index schema v1, update/runtime schemas, offline-serving guarantees, support boundaries, and semantic-versioning policy become explicit machine-readable promises.
- [x] **T196 — Add a deterministic Stable 1.0 distribution manifest and critical-artifact hash inventory.** Bind the release to current Core/Tournament/card/FAQ authority, corpus counts, stable contracts, key executable surfaces, and known non-blocking limitations without self-referential hashes.
- [x] **T197 — Add the stable `riftkeep.py` launcher and offline self-check.** `self-check`, `status`, and `serve` must use the same validated runtime boundary, return deterministic exit codes, and require no network for normal operation.
- [x] **T198 — Expose stable product identity through Package/API/UI surfaces.** Package `__version__`, `/v1/status`, and the UI release label must consistently identify RiftKeep Rules Engine 1.0 while preserving Product API v1 compatibility.
- [x] **T199 — Freeze 1.0 release notes, known limitations, migration/update, and rollback documentation.** Explicitly document the 18 report-only Gold-C fixtures and historical-body warnings as non-current-authority limitations.
- [x] **T200 — Build the Stable 1.0 acceptance suite.** Verify version identity, manifest/hash integrity, source authority, compatibility promises, launcher/self-check, API/UI identity, no candidate/development leakage, known limitations, and M18 conformance inheritance.
- [x] **T201 — Execute a clean-install Stable 1.0 distribution rehearsal.** Fresh extraction, offline self-check, rebuild, API/UI startup, definition lookup, deterministic Ask, read-only index, and release-manifest validation.
- [x] **T202 — Promote Stable 1.0 acceptance into validation, project audit, and Update Automation.** Future authority updates must pass the Stable 1.0 contract as part of a 19-suite certified gate.
- [x] **T203 — Run the complete M19 implementation gate.** Preserve all 18 M18 suites plus the Stable 1.0 acceptance suite, consolidated validation, and project audit.
- [x] **T204 — Package and surface an M19/1.0 recovery candidate.** Clean-extract/rebuild/retest the candidate and publish it in chat as the latest recovery snapshot before final promotion.
- [x] **T205 — Finalize, clean-extract/retest, recovery-certify RiftKeep Rules Engine 1.0 and rotate retention to M18 + M19.**
