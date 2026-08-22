# RiftKeep LLM Boundary — Milestones 10–11

The LLM is never a rules authority or adjudicator.

## M10 — interpretation/decomposition

The optional interpretation model runs before deterministic adjudication and receives only the player's question plus non-authoritative deterministic language metadata. It may propose source-traceable issue spans, paraphrases, search concepts, ambiguity notices, and clarification questions. Its output is advisory `llmInterpretation` metadata and does not mutate facts, Scenario Model, evidence, proof, authority, ruling, verdict, or answer.

It may not receive rule/card/FAQ text, evidence catalogs, proof traces, authority decisions, or verdicts. Facts, assumptions, entity bindings, invented ownership/control/timing, rule/evidence IDs, purported source text, and prompt-injection output invalidate the whole payload.

## M11 — explanation only

The optional explanation model runs **after deterministic adjudication and M9 proof verification**. It receives:

- player issue text;
- fixed issue status/verdict;
- deterministic support claims;
- per-issue citation allowlists and required citation IDs;
- no authoritative rule/card/FAQ text.

The model may write explanatory prose and select only allowed citation IDs. It may not change a verdict, add facts/assumptions, choose source authority, perform new adjudication, omit required decisive citations, cite another issue's evidence, type rule-number-like text, provide purported quotations, or answer an unresolved issue definitively.

The backend prepends the fixed direct conclusion and resolves citation IDs to **exact canonical text**. Model prose is never an authoritative quotation source.

## Fail-closed policy

Any provider exception, malformed/unsafe output, schema violation, proof-verification failure, citation violation, verdict mutation, or prompt-injection output discards the complete model stage and uses deterministic fallback. No partial model output is salvaged.

`OpenAICompatibleLocalProvider` is loopback-only (`localhost`, `127.0.0.1`, `::1`), rejects redirects/non-loopback endpoints, and bounds response size.

## Disabled legacy capabilities

The pre-M10 `GroundedLlmPipeline.request_evidence_completion()`, `.adjudicate()`, and `.draft_answer()` entry points remain disabled compatibility shims and do not call a provider. M11 uses the separately validated `llm_explanation.py` path.
