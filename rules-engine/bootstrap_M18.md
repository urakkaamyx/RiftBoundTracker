# RiftKeep Rules Engine — Milestone 18 Recovery Bootstrap

Milestone 18 is the certified Release Candidate / Full Audit checkpoint.

## Release identity
- Milestone: `ground-zero-milestone-18`
- Release status: `released`
- Tasks complete through: `T194`
- Retained certified releases: M17 + M18

## Certified gate
18 suites: Core 164, Definition Lookup 120, rulings 99, player language 42, scenario language 43, Scenario Model 58, compiler 42, proof 72, LLM interpretation 84, LLM explanation 80, Gold 34 over 1,846 cases, card interactions 74, Product API 132, UI 148, update/version 29, Update Automation 70, Production Hardening 74, M18 adversarial audit 48. Consolidated validation PASS. Audit 0 critical / 2 known historical warnings.

## M18 audit outcome
0 Critical / 0 High blockers. The sole Medium/non-blocking finding is 18 Gold-C fixtures still report-only. Clean rebuild is substantively deterministic; only `generatedAt` fields in two generated artifacts are byte-unstable.

## Recovery
1. Verify `RiftKeepRules_Engine_Milestone18.zip` against `RiftKeepRules_Engine_Milestone18.zip.sha256`.
2. Extract M18 and rebuild with `PYTHONPATH=src python -m riftkeep_rules.build`.
3. Run all 18 scripts in `src/riftkeep_rules/release_gate.py`, then `python validate_all.py` and `python audit_project.py`.
4. Confirm M18 / released / T194 and current gameplay authority COMPLETE.
5. Retain M17 + M18 only until M19 is certified.
