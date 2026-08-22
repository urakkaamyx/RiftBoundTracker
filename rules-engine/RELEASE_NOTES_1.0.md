# RiftKeep Rules Engine 1.0

RiftKeep Rules Engine 1.0 is the first stable release of the deterministic Riftbound rules reference, adjudication, proof, update, Product API, and RiftKeep UI system built across milestones M1–M19.

## Stable interfaces

- Product API remains `v1` with eight service methods and the existing deterministic error envelope.
- SQLite search-index schema remains `user_version=1` and is read-only/query-only at runtime.
- Normal Ask/Search/UI/self-check operation is offline and requires no network.
- Current Core/Tournament/FAQ/card/errata authority remains source-hash and provenance bound.
- Definition Lookup is proof-verified and covers current keywords, Game Actions, named rule concepts, morphology, and dual-meaning concepts.
- Source updates remain review-gated transactions with isolated rehearsal, exact publish bundles, stale-baseline protection, post-publish gates, and rollback.

## Stable launcher

Use:

```bash
python riftkeep.py self-check
python riftkeep.py status
python riftkeep.py serve
```

The stable UI is then available from the loopback server root, with Product API routes under `/v1/*`.

## Release quality baseline

1.0 inherits the complete M18 conformance gate: current authority COMPLETE; zero Critical/High release blockers; full deterministic regression, proof, Definition Lookup, Product API/UI, update, production-hardening, and adversarial audit coverage. The known non-blocking limitations are documented separately in `KNOWN_LIMITATIONS_1.0.md`.

## Compatibility and updates

Semantic-versioning policy is machine-readable in `data/canonical/stable_release_contract.json`. Official rules/card/FAQ changes use the transactional update system and do not automatically imply a software major version. Breaking API/proof/persisted-schema changes require a major release.
