# RiftKeep Rules Engine — Milestone 17 Recovery Bootstrap

Milestone 17 revision 2 is the certified Production Hardening checkpoint.

## Definition Lookup hotfix

The pre-M18 hotfix adds a 120-check Definition Lookup suite and fixes natural `What does X do?` lookups, conservative singular aliases, and proof-sealed definition evidence. The certified release gate now contains 17 suites.

## Certified baseline

- Core/system: 164/164
- Rulings: 99/99
- Player language: 42/42
- Scenario language: 43/43
- Scenario Model: 58/58
- Rule Compiler: 42/42
- Proof Engine: 72/72
- LLM interpretation: 84/84
- LLM explanation: 80/80
- Gold corpus: 34/34 over 1,846 frozen cases
- Card interactions: 74/74
- Product API: 132/132
- UI integration: 148/148
- Update/version: 29/29
- Update Automation: 70/70
- Production Hardening: 74/74
- Consolidated validation: PASS
- Project audit: 0 critical / 2 known non-blocking historical archive warnings

## M17 production guarantees

Atomic durable canonical/update writes; atomic validated SQLite replacement; SQLite schema v1; read-only/query-only runtime DB access; startup integrity fail-closed; serving-snapshot drift fail-closed; bounded 256-entry thread-safe search cache; no adjudication cache; offline normal serving; sanitized request IDs and bounded metrics; corruption/interruption/concurrency recovery tests.

## Restore

Extract `RiftKeepRules_Engine_Milestone17.zip`, run `PYTHONPATH=src python -m riftkeep_rules.build`, then run the 17 certified tests in `src/riftkeep_rules/release_gate.py`, followed by `python validate_all.py` and `python audit_project.py`. Do not promote a recovery tree that is not fully green.

## Retention

Keep only the latest two certified milestone ZIPs. At M17 that is M16 + M17. Candidates, smoke/stage folders, prior full backups, and older milestone ZIPs are excluded from the next full backup.
