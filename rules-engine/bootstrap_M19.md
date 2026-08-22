# RiftKeep Rules Engine — Stable 1.0 / Milestone 19 Recovery Bootstrap

## Certified checkpoint

- Product: RiftKeep Rules Engine 1.0.0
- Milestone: ground-zero-milestone-19
- Release status: released
- Tasks complete through: T205
- Product API: v1
- SQLite index schema: v1
- Retained milestone releases: M18 + M19 only

## Recovery verification

1. Extract `RiftKeepRules_Engine_Milestone19.zip`.
2. Run `PYTHONPATH=src python -m riftkeep_rules.build`.
3. Run `python riftkeep.py self-check --compact`; it must return `ok: true`, version 1.0.0, manifest PASS, runtime PASS, and `networkRequired: false`.
4. Run all 19 scripts in `src/riftkeep_rules/release_gate.py`.
5. Run `python validate_all.py` and `python audit_project.py`.
6. Expected audit: 0 critical / 2 known historical archive warnings.
7. Verify the release ZIP with the external `.sha256` sidecar.

## Stable 1.0 acceptance baseline

164 core, 120 definition, 99 rulings, 42 player-language, 43 scenario-language, 58 Scenario Model, 42 compiler, 72 proof, 84 LLM interpretation, 80 LLM explanation, 34 Gold over 1,846 cases, 74 card interactions, 132 Product API, 148 UI, 29 update/version, 70 Update Automation, 74 Production Hardening, 48 M18 audit, and 191 Stable acceptance checks.

## Known non-blocking limitations

- 18 Gold-C forward card-interaction fixtures remain report-only.
- Four historical patch-note bodies are not locally mirrored.
- Three superseded historical FAQ bodies are not locally mirrored.
- None of those historical/report-only limitations affects current gameplay authority.
