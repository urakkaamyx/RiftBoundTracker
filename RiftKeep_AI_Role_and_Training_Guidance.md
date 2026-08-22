# RiftKeep Rules Engine 1.0 — AI Role, Model Strategy, and Training Guidance

## Purpose

This document defines **where AI should participate in RiftKeep**, where it must not participate, whether RiftKeep requires a trained/fine-tuned model, and what future model-training work could be useful.

The central architectural rule is:

```text
AI helps understand and explain.
The deterministic RiftKeep engine decides the rules.
```

RiftKeep Rules Engine 1.0 was deliberately designed so that the correctness of a ruling does **not** depend on an LLM having memorized Riftbound rules.

---

# 1. Core AI Architecture

Recommended architecture:

```text
User Question
     │
     ▼
AI Interpretation Layer
     │
     │ Understand player language
     │ Extract entities/actions
     │ Detect ambiguity
     │ Ask for clarification when required
     ▼
Structured Scenario
     │
     ▼
DETERMINISTIC RIFTKEEP ENGINE
     │
     ├─ Core Rules
     ├─ Tournament Rules
     ├─ Cards
     ├─ FAQ
     ├─ Errata
     ├─ Scenario Model
     ├─ Rule Compiler
     ├─ Card Interaction Engine
     └─ Proof Engine
     │
     ▼
Verified Ruling + Proof + Evidence
     │
     ▼
AI Explanation Layer
     │
     │ Explain the already-fixed result
     │ Use only approved support claims
     │ Use only approved citation IDs
     ▼
User
```

The AI is therefore positioned **around** the deterministic engine rather than **inside the authority decision**.

---

# 2. The AI Must Not Be the Judge

Do not implement RiftKeep as:

```text
Question
   │
   ▼
LLM
   │
   ▼
"Here is what I think the rule says."
```

That architecture creates unacceptable risks:

- hallucinated rules
- stale rules
- invented card text
- invented citations
- incorrect precedence
- inconsistent answers
- inability to prove the result
- model-training knowledge becoming outdated after official updates

The correct architecture is:

```text
Question
   │
   ▼
LLM understands wording
   │
   ▼
RiftKeep deterministic engine adjudicates
   │
   ▼
LLM explains verified result
```

---

# 3. AI Role #1 — Player-Language Interpretation

Players rarely ask questions in formal rules terminology.

Example:

```text
"Can my dude gank over there?"
```

Possible structured interpretation:

```text
Action:
    Move

Object:
    Friendly unit

Origin:
    Battlefield

Destination:
    Different battlefield

Relevant player term:
    Ganking
```

Another example:

```text
"If I lose the field does my hidden shit go away?"
```

Possible interpretation:

```text
Event:
    Player loses control of a battlefield

Object:
    Facedown / Hidden card associated with battlefield

Question:
    What happens to the facedown card?

Timing question:
    Immediate vs Cleanup
```

The AI is useful here because human language is inconsistent, abbreviated, slang-heavy, and context-dependent.

The AI is **not** deciding the ruling.

It is converting player language into data the deterministic engine can safely process.

---

# 4. AI Role #2 — Ambiguity Detection

A major part of rules judging is recognizing when a question is missing a fact.

Example:

```text
"If my unit dies, does my hidden card disappear?"
```

Potential missing information:

```text
Does the player still control the battlefield after that unit dies?
```

A good AI interpretation layer should identify that the ruling cannot safely proceed without this information.

Desired behavior:

```text
Question
   │
   ▼
Interpretation Layer
   │
   ├─ Enough information
   │      ▼
   │   Scenario Model
   │
   └─ Missing information
          ▼
      Clarification Request
```

The AI should never guess missing scenario facts.

---

# 5. AI Role #3 — Entity and Relationship Extraction

The AI may help identify:

- players
- units
- gear
- spells
- battlefields
- cards in hidden/facedown zones
- controllers
- owners
- locations
- origins
- destinations
- current state
- previous events
- temporal order
- pronouns such as "it", "that unit", "there", "them"
- player terminology such as "field", "hidden card", "gank", etc.

The result should be converted into RiftKeep's structured Scenario Model.

Example:

```text
User:
"My opponent stole my unit and it dies. Where does it go?"
```

Interpretation might identify:

```text
Object owner:
    Player A

Object controller:
    Player B

Event:
    Unit dies

Question:
    Destination after death
```

The deterministic engine then applies ownership, zone, death, and destination rules.

---

# 6. AI Role #4 — Natural-Language Explanation

The deterministic engine may internally produce something like:

```text
Verdict:
    Hidden card remains temporarily

Reason:
    Battlefield control was lost

Timing:
    Card is removed during next Cleanup

Applicable evidence:
    Rule X
    Rule Y
    Rule Z

Proof:
    verified
```

That may not be the ideal user-facing answer.

The AI explanation layer can convert the verified result into something like:

```text
If you lose control of the battlefield, the hidden card is not removed immediately.

It is removed during the next Cleanup because a facedown card can only remain in that battlefield's facedown zone while its controller also controls the associated battlefield.
```

The important distinction is:

```text
The AI explains the verdict.
It does not choose the verdict.
```

---

# 7. AI Explanation Must Be Constrained

The AI explanation layer should receive a sealed packet containing only things it is allowed to explain.

Conceptually:

```text
Explanation Packet

✓ Fixed verdict
✓ Fixed issue status
✓ Verified support claims
✓ Required evidence IDs
✓ Allowed citation IDs
✓ Deterministic sequence of events

Not included / not editable:

✗ Ability to change verdict
✗ Ability to add facts
✗ Ability to add assumptions
✗ Ability to invent authority
✗ Ability to invent card text
✗ Ability to invent citations
```

The backend should remain responsible for rendering exact authority quotations and citations.

---

# 8. RiftKeep Already Has These AI Boundaries

Milestones 10 and 11 were specifically created for this architecture.

## M10 — LLM Interpretation Layer

The interpretation layer is advisory and upstream of deterministic adjudication.

It may help with:

- player language
- normalization
- ambiguity
- issue segmentation
- entity references

It may not create:

- verdicts
- rule IDs
- evidence
- rules
- card text
- new facts
- hidden assumptions

Invalid AI output is discarded.

---

## M11 — LLM Explanation Layer

The explanation layer runs only after:

```text
Deterministic adjudication
        +
Proof verification
```

It receives a sealed explanation packet.

It cannot:

- alter the verdict
- introduce foreign evidence
- invent citations
- create rule text
- omit mandatory evidence
- rewrite the proof

A deterministic fallback explanation remains available if the LLM output is rejected.

---

# 9. Does RiftKeep 1.0 Need a Trained Model?

## No.

RiftKeep 1.0 does **not** require custom model training or fine-tuning.

Use an existing capable instruction model initially.

Possible choices include:

```text
OpenAI model
Claude
Qwen
Llama
Mistral
other instruction-following models
```

The model does not need to have Riftbound rules memorized.

---

# 10. Why the Model Should Not Memorize the Rules

Training the rules directly into model weights creates a synchronization problem.

Example:

```text
July 2026

Model is trained on:
Core Rules V4
```

Later:

```text
Riot publishes:
Core Rules V5
New FAQ
New errata
```

Now two sources of "truth" exist:

```text
Model memory:
    old rules

RiftKeep corpus:
    current rules
```

This is exactly what RiftKeep's authority/versioning architecture was designed to prevent.

Instead:

```text
LLM
does not own rules

        │
        ▼

RiftKeep Engine
owns current authority
```

When rules change:

```text
Update authority corpus
Run update lifecycle
Run release gate
Restart engine
```

No model retraining is necessary.

---

# 11. Updating Rules Should Not Require Retraining

Desired lifecycle:

```text
New Core Rules PDF
        │
        ▼
RiftKeep Update Automation
        │
        ├─ detect
        ├─ stage
        ├─ parse
        ├─ diff
        ├─ review
        ├─ rehearse
        ├─ run certified release gate
        └─ publish
        │
        ▼
Restart Rules Engine
```

The AI continues operating against the newly updated deterministic authority.

No fine-tuning cycle should be required for ordinary rules updates.

---

# 12. What the AI Actually Needs to Know

The model mainly needs to be good at:

```text
natural language
entity extraction
relationship extraction
coreference resolution
ambiguity detection
structured-output compliance
explanation
```

It does not need deep memorized knowledge of:

```text
Riftbound Core Rules
Tournament Rules
FAQ
errata
card interactions
rule precedence
```

Those are engine responsibilities.

---

# 13. Prompting Before Training

For RiftKeep 1.0, start with strong constrained prompting.

Interpretation-system behavior should resemble:

```text
Your job is to interpret the player's wording.

You may:
- identify referenced objects
- identify actions
- identify relationships
- identify ambiguity
- identify missing information
- return the required structured schema

You may not:
- determine the ruling
- invent a rule
- invent card text
- invent facts
- assume missing facts
- provide rule IDs
- provide a verdict
```

The deterministic engine then processes the structured result.

---

# 14. Explanation Prompting

The explanation model should receive something conceptually like:

```text
You are explaining an already-decided ruling.

The verdict is fixed.

You may use only:
- supplied support claims
- supplied evidence IDs
- supplied sequence information

Do not:
- add new rules
- alter the verdict
- infer additional facts
- create citations
- quote unsupplied authority
```

The backend validates the response before showing it to the user.

---

# 15. When Custom Training Might Become Useful

Training may become useful later, but it should improve **communication**, not **rules authority**.

Potential training targets include:

1. Player-language interpretation
2. Scenario extraction
3. Clarification detection
4. Coreference resolution
5. Judge-style explanations

---

# 16. Future Training Target — Player Language

Players may say:

```text
"gank over there"
"bounce him"
"hidden dude"
"field"
"trash him"
"does that proc?"
"does that trigger twice?"
```

A fine-tuned model could become better at mapping community language into RiftKeep's canonical vocabulary.

Example:

```text
Player phrase:
"Can he gank over?"

Canonical interpretation:
Standard Move
Battlefield → Battlefield
Requires Ganking
```

This is a good future training objective.

---

# 17. Future Training Target — Scenario Model Generation

Training pairs could eventually look like:

```text
INPUT

"If my opponent steals my unit and it dies where does it go?"

OUTPUT

{
  owner: "player_a",
  controller: "player_b",
  objectType: "unit",
  event: "dies",
  issue: "zone_destination"
}
```

The deterministic engine would still decide the result.

---

# 18. Future Training Target — Clarification Detection

Training examples could focus on missing information.

Example:

```text
INPUT

"If my unit dies does the hidden card disappear?"

EXPECTED OUTPUT

Missing fact:
"Do you still control the battlefield after the unit dies?"
```

This could make RiftKeep much better at judge-style interaction.

---

# 19. Future Training Target — Explanation Style

A model could be trained to produce a consistent judge-style format:

```text
Short answer

Why

Sequence

Relevant rules
```

Example:

```text
Short answer:
No, not immediately.

Why:
The hidden card remains until Cleanup after battlefield control is lost.

Sequence:
1. Unit dies.
2. Battlefield control changes.
3. Cleanup occurs.
4. Facedown card is removed.

Authority:
Backend-provided citations.
```

Again, the model is learning how to communicate a ruling, not how to determine one.

---

# 20. RiftKeep's Gold Corpus Is Valuable Future Training Material

RiftKeep already contains a strong future dataset foundation.

Current Stable 1.0 includes:

```text
1,846 frozen Gold cases
```

The corpus includes:

- semantic rule cases
- player-language surfaces
- negative cases
- conditional cases
- FAQ cases
- errata cases
- card cases
- definition cases
- update/diff cases
- card-interaction fixtures

This could later be transformed into specialized AI datasets.

---

# 21. Possible Future Dataset — Interpretation

Dataset form:

```text
Player Question
        │
        ▼
Expected Scenario Model
```

Example:

```text
"What happens to my hidden card if I lose the battlefield?"

        ↓

{
  issue: "facedown_zone_control_loss",
  event: "battlefield_control_loss",
  object: "facedown_card"
}
```

---

# 22. Possible Future Dataset — Clarification

Dataset form:

```text
Question + Partial Scenario
        │
        ▼
Required Clarification
```

Example:

```text
"If that unit dies can I move it?"

        ↓

"What zone is the unit currently in?"
```

---

# 23. Possible Future Dataset — Explanation

Dataset form:

```text
Verified Proof Packet
        │
        ▼
Ideal Judge Explanation
```

This dataset would train communication style while preserving deterministic authority.

---

# 24. Do Not Fine-Tune Directly on Raw Rule PDFs as the Primary Strategy

Avoid:

```text
Core Rules PDF
Tournament Rules PDF
FAQ
        │
        ▼
Fine-tune LLM
        │
        ▼
Use LLM as judge
```

Problems include:

- rules become embedded in weights
- difficult to update safely
- difficult to remove superseded rules
- no deterministic provenance
- no exact version binding
- possible mixing of old/new authority
- hallucination remains possible
- difficult to audit

The authoritative corpus should remain external and versioned.

---

# 25. Collect Real Usage Before Training

Do not train prematurely.

First deploy the system and collect real examples.

After meaningful usage, the dataset may contain information such as:

```text
50,000 real rules questions

8,000 containing player slang
4,000 requiring clarification
2,000 initially misunderstood
hundreds of recurring phrasing patterns
```

That data would be considerably more valuable than a synthetic guess about how Riftbound players will speak.

---

# 26. Recommended Production Strategy for 1.0

Initial production architecture:

```text
Existing General-Purpose Model
          │
          ▼
Interpretation Layer
          │
          ▼
Scenario Model
          │
          ▼
RiftKeep Deterministic Engine
          │
          ▼
Verified Proof
          │
          ▼
Existing General-Purpose Model
          │
          ▼
Explanation Layer
```

No custom training required.

---

# 27. Model Provider Should Be Replaceable

The AI provider should be behind an abstraction.

Conceptually:

```text
IRiftKeepLanguageModel

    Interpret(...)
    Explain(...)
```

Possible implementations:

```text
OpenAI
Claude
Local Qwen
Local Llama
Local Mistral
Other provider
```

The deterministic Rules Engine should not depend on a particular model vendor.

---

# 28. AI Failure Must Not Break Rules Correctness

If the AI interpretation layer fails:

```text
invalid output
schema violation
timeout
unsupported response
```

RiftKeep should:

```text
reject AI result
        │
        ▼
use deterministic fallback / clarification path
```

If the explanation model fails:

```text
reject explanation
        │
        ▼
use deterministic explanation
```

The ruling itself must remain valid regardless of AI availability.

---

# 29. AI Can Potentially Be Optional

A strong long-term design is:

```text
AI available
    │
    ├─ Better language interpretation
    └─ Better explanation

AI unavailable
    │
    └─ Deterministic RiftKeep still works
```

This allows:

- offline operation
- privacy-sensitive deployments
- local-only deployments
- API-free modes
- graceful provider outages

---

# 30. Long-Term Local AI Option

Because the model is not responsible for rules reasoning, RiftKeep may eventually work well with a relatively small local model.

Potential future architecture:

```text
RiftKeep Desktop
       │
       ├── Deterministic Rules Engine
       │
       └── Local 3B–8B Instruction Model
                 │
                 ├─ interpretation
                 ├─ clarification
                 └─ explanation
```

Benefits:

```text
No cloud API cost
No Internet requirement
Lower latency
Better privacy
Rules remain independently updateable
```

The exact model size should be determined by evaluation rather than assumed in advance.

---

# 31. Why a Small Model Can Work

The hard reasoning has already been moved into the deterministic system.

The AI does not need to calculate:

- rule precedence
- replacement chains
- proof obligations
- card interactions
- authority versions
- exact evidence
- current errata

Its primary tasks are linguistic.

That makes small-model deployment much more realistic.

---

# 32. Rules Updates Stay Independent From AI Updates

Desired separation:

```text
RULE UPDATE
    │
    ▼
Update deterministic corpus
Run certified release gate
Restart engine

AI MODEL
    │
    └─ unchanged
```

And separately:

```text
AI MODEL UPDATE
    │
    ▼
Evaluate interpretation/explanation quality
Deploy improved model

RULE CORPUS
    │
    └─ unchanged
```

This separation is extremely valuable.

---

# 33. If Training Is Added Later

Recommended order:

```text
1. Deploy RiftKeep 1.0 with an existing model
2. Gather real user questions
3. Label interpretation failures
4. Label clarification failures
5. Build ScenarioModel training pairs
6. Build clarification training pairs
7. Build explanation-style pairs
8. Evaluate a small fine-tuned model
9. Compare against baseline model
10. Only deploy if measurable quality improves
```

Do not train merely because training is technically possible.

---

# 34. Evaluation Matters More Than Training

Any future model should be evaluated against fixed datasets.

Example:

```text
Interpretation Accuracy
Clarification Recall
False-Assumption Rate
Schema Compliance
Coreference Accuracy
Explanation Fidelity
Unsupported-Claim Rate
Citation-Allowlist Compliance
```

The most important AI metric should remain:

```text
Does the AI preserve the deterministic engine's meaning without inventing anything?
```

---

# 35. Never Allow Fine-Tuning to Bypass the Engine

Even if a future model becomes extremely good at Riftbound:

```text
Model:
"I know the answer."
```

RiftKeep should still require:

```text
Scenario
   │
   ▼
Deterministic adjudication
   │
   ▼
Proof verification
```

The model's confidence is not authority.

---

# 36. Recommended Claude Integration Principle

If Claude is used as one of RiftKeep's AI providers, Claude should receive only the constrained task appropriate to its role.

For interpretation:

```text
User language
Normalization hints
Ambiguity metadata
Strict Scenario output contract
```

Claude should not independently browse or select rules for the ruling.

For explanation:

```text
Fixed verdict
Verified claims
Allowed evidence IDs
Required evidence IDs
```

Claude should not be permitted to change the adjudication.

---

# 37. Claude Development Guidance

When implementing RiftKeep integration, Claude should preserve these architectural boundaries:

```text
AI Provider
    │
    ├─ Interpretation Adapter
    └─ Explanation Adapter

             ↓

RiftKeep Product / Rules Service

             ↓

Deterministic Engine
```

Do not merge the AI provider directly into:

- rule compiler
- proof engine
- authority selection
- evidence selection
- card interaction executor
- update promotion logic

---

# 38. Data Privacy Consideration

Before sending questions to a cloud AI provider, consider whether the application should support:

```text
Cloud AI mode
Local AI mode
No-AI deterministic mode
```

Because deterministic adjudication remains local, these modes can share the same rules backend.

---

# 39. Recommended Initial Model Strategy

For RiftKeep 1.0:

```text
Use a strong existing instruction model.

Do not fine-tune yet.

Constrain it aggressively.

Collect real usage data.

Measure errors.

Fine-tune later only if the data demonstrates a useful target.
```

---

# 40. Final Architectural Rule

The most important distinction is:

```text
AI owns language.

RiftKeep owns truth.
```

Or more explicitly:

```text
AI:
    "What is the player asking?"

RiftKeep:
    "What is legally true?"

AI:
    "How can I explain the verified result clearly?"
```

That separation is intentional and should be preserved through future development.

---

# 41. Recommended Next Step

The next practical implementation step is not model training.

It is to wire an AI-provider abstraction around the already-built M10/M11 boundaries and test it with an existing model.

Recommended sequence:

```text
1. Integrate deterministic Rules Engine into the application
2. Verify Product API integration
3. Add AI-provider abstraction
4. Implement interpretation adapter
5. Feed output into existing deterministic Scenario Model pipeline
6. Implement explanation adapter
7. Enforce existing validation/rejection boundaries
8. Add deterministic fallback
9. Start collecting real player-language examples
10. Evaluate whether future fine-tuning is actually necessary
```

This gives RiftKeep useful AI immediately without making rules correctness dependent on model training.
