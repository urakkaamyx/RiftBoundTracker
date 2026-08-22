# RiftKeep Rules Engine — Canonical Milestone Roadmap

This file is the durable post-recovery development roadmap for the RiftKeep Rules Engine.

**Roadmap rule:** milestone purpose/scope must not be silently redefined. If scope changes, record the change explicitly in this file and in milestone/task history.

| Milestone | Purpose | Status |
| --- | --- | --- |
| **M1 — Authoritative Corpus Foundation** | Parse Core Rules + Tournament Rules + cards, preserve exact text/provenance, source hashes, rule IDs, errata, validation | Complete |
| **M2 — Deterministic Retrieval & Basic Adjudication** | Rule graph, concepts, keywords/Game Actions, evidence closure, applicability, basic rule resolution, first regression rulings | Complete |
| **M3 — Hard Interaction Families** | Targeting, Untargetable, replacements, triggers, Chain timing, Combat/Showdown, copy/layer semantics, broader rulings | Complete |
| **M4 — Full Current Authority Overlay** | Ingest current Vendetta FAQ, classify rulings, enforce precedence, effective overrides, expand FAQ-backed adjudication | Complete |
| **M5 — Player Language & Clarification** | Colloquial terms, multipart questions, ambiguity detection, missing-fact questions, player-language regression suite | Complete |
| **M6 — Audit, Update Lifecycle & Scenario Understanding** | Full project audit; finish version-history gaps; safe future-PDF promotion; deeper scenario extraction and state modeling | Complete |
| **M7 — Generalized Scenario Model** | Turn natural-language situations into structured game state: players, objects, controllers, owners, zones, locations, temporal order, pronouns, references, before/after/while, assumptions | Complete |
| **M8 — Generalized Rule Compiler** | Reduce reliance on hand-coded ruling families by compiling more rule semantics into conditions/effects/dependencies/replacements/permissions/prohibitions | Complete |
| **M9 — Proof Engine / Complete Adjudication** | Build ordered proofs across multiple rule families; applicability resolution, conflicts, replacement ordering, timing/state transitions, rejected evidence reasons | Complete |
| **M10 — LLM Interpretation Layer** | Add constrained LLM for messy language interpretation/decomposition only; no authority to invent rules, card text, citations, or verdicts | Complete |
| **M11 — LLM Explanation Layer** | Convert validated rulings into natural rules-judge answers with exact backend-rendered citations and direct multipart conclusions | Complete |
| **M12 — Large Gold Test Corpus** | Hundreds/thousands of verified scenarios covering rules families, real cards, edge cases, negative cases, ambiguity, FAQ overrides, errata, updates | Complete |
| **M13 — Card Interaction Engine** | Deeper card-specific reasoning across multiple cards, abilities, keywords, replacements, continuous effects, copies, triggers, layers and state changes | Complete |
| **M14 — Search / Ask-Rules Product API** | Stable service/API for keyword search, card lookup, rule lookup, natural-language adjudication, citations, source history, and “what changed?” | Complete |
| **M15 — RiftKeep UI Integration** | Actual RiftKeep Ask Rules interface: search, judge-style answers, expandable evidence, cards/rules, clarification prompts, history/change views | Complete |
| **M16 — Update Automation** | Feed it a new Core Rules PDF / FAQ / errata / Rules Hub change → detect → diff → review → promote → rebuild indexes → regression-test → publish | Complete |
| **M17 — Production Hardening** | Performance, caching, concurrency, corruption recovery, migration/version safety, logging, diagnostics, offline behavior | Complete |
| **M18 — Release Candidate / Full Audit** | End-to-end audit against architecture promises, source authority, regression corpus, update simulation, clean install/rebuild and adversarial testing | Complete |
| **M19 — Stable RiftKeep Rules Engine 1.0** | Production-ready rules engine integrated into RiftKeep | Complete |

## Current checkpoint

Milestone 16 is the latest **certified released/recovery-tested checkpoint** (`T168` complete). Milestone 17 Production Hardening is the current development milestone and is not released yet. The M16 baseline is 164 core, 99 ruling, 42 player-language, 43 scenario-language, 58 Scenario Model, 42 Rule Compiler, 72 Proof Engine, 84 LLM interpretation, 80 LLM explanation, 34 Gold, 74 card interaction, 132 Product API, 148 UI integration, 29 update/authority, and 70 Update Automation checks; consolidated validation PASS; project audit 0 critical / 2 known historical-archive warnings.

### Roadmap status history

- 2026-08-21: M1–M19 roadmap frozen with M6 as Current.
- 2026-08-21: M7 passed its release gate.
- 2026-08-22: M8 through M15 completed their release/recovery gates.
- 2026-08-22: M16 Update Automation started; live authority remains at the certified M15 checkpoint until T168 closes.
- 2026-08-22: M16 Update Automation completed its release/recovery gate; M17 Production Hardening became current.
- 2026-08-22: M17 Production Hardening released after the full 16-suite clean-extraction gate; M18 remains next.

## Dependency direction

`M6 → M7 → M8 → M9 → M10 → M11 → M12 → M13 → M14 → M15 → M16 → M17 → M18 → M19`

M10/M11 must not be pulled forward to compensate for missing deterministic M7–M9 capabilities.

- 2026-08-22: M18 Release Candidate / Full Audit became current from the recovered M17 Revision 2 checkpoint.

- 2026-08-22: M18 completed its clean candidate/final/recovery certification; M19 Stable RiftKeep Rules Engine 1.0 became current.

- 2026-08-22: M19 Stable 1.0 implementation started from the certified M18 rollback point.

- 2026-08-22: M19 Stable RiftKeep Rules Engine 1.0 released after the complete 19-suite clean-extraction/recovery gate.
