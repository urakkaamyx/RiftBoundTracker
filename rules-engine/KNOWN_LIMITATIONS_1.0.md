# RiftKeep Rules Engine 1.0 — Known Limitations

These limitations are explicitly non-blocking for current gameplay authority and are covered by the M18/M19 release gates.

## 18 report-only Gold-C interaction fixtures

Eighteen forward-looking card-interaction fixtures remain authority-backed but report-only. They are not silently treated as executable adjudication coverage. The 16 promoted Gold-C interactions remain source-guarded and release-gating. A future minor release may promote additional fixtures only after deterministic executors and proof coverage exist.

## Historical patch-note bodies

Four superseded historical Core patch-note bodies are not locally ingested. Patch notes are non-exhaustive change context; Core PDF-to-PDF version diff remains the authoritative historical rules-change mechanism. This does not reduce current gameplay authority completeness.

## Historical FAQ bodies

Three superseded historical FAQ bodies are not locally ingested. They are historical evidence only and cannot override the current Vendetta FAQ overlay. This does not reduce current gameplay authority completeness.

## Optional LLM presentation layers

Local LLM interpretation/explanation is optional. Deterministic adjudication, proof verification, citations, Definition Lookup, Product API, and current-authority enforcement do not depend on an LLM provider. Non-loopback providers are rejected by the constrained LLM boundary.

A provider is off unless `RIFTKEEP_LLM_BASE_URL` (and optionally `RIFTKEEP_LLM_MODEL`) is explicitly set before `riftkeep.py serve` starts, pointing at a loopback OpenAI-compatible chat endpoint (e.g. a locally-run `llama-server`) the operator starts themselves — nothing here launches a model process automatically. `declaredVerdict` and every citation are still validated exactly against the deterministic result regardless of provider quality, so a bad response is rejected and falls back to the plain deterministic answer rather than being shown. That said, this has been directly tested against a small (1.5B) local instruct model and found to sometimes produce fluent, structurally-valid prose that draws on the model's own pretrained knowledge of a similarly-spelled term from unrelated games instead of the actual supplied Riftbound evidence — a failure the structural validator cannot detect, since it checks shape, not truth. Treat this capability as experimental until verified against a larger/more capable model; it is intentionally not wired into any default deployment path.
