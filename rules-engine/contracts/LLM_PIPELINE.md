# RiftKeep Constrained LLM Pipeline

```text
player question
    │
    ├─ optional M10 interpretation model
    │     sealed language-only packet
    │     strict validation / deterministic fallback
    │
    ▼
M7 Scenario Model
    ▼
M8 Rule Compiler
    ▼
deterministic adjudication
    ▼
M9 proof verification
    │
    ├─ verification failure → insufficient / deterministic output only
    │
    ▼
sealed M11 explanation packet
    │
    ├─ optional loopback explanation model
    │     fixed verdicts + support claims + citation IDs only
    │     NO authoritative source text
    │
    ▼
strict explanation validator
    │
    ├─ invalid/error → existing deterministic writer answer
    │
    ▼
backend renderer
    ├─ fixed direct conclusion
    ├─ validated model prose
    └─ exact canonical rule/card/official-ruling text by citation ID
```

### Invariants

- M10 cannot affect adjudication.
- M11 cannot run on an unverified proof.
- M11 cannot alter a verdict or decisive citation requirement.
- Model prose never supplies an exact quotation.
- Provider absence/failure/rejection preserves the deterministic answer.
- Accepted M11 output may change only player-facing prose; facts, Scenario Model, authority, evidence, proof, ruling, and verdict remain deterministic.
