# RiftKeep 1.0.1 — Tournament Context Must Be Explicit
## Core-First Authority Routing & Question-Intent Patch Design

## Purpose

This document defines the routing policy RiftKeep should use for distinguishing:

- normal gameplay questions
- Core Rules deck-construction questions
- definition questions
- format-legality questions
- Tournament Rules questions
- mixed Core + Tournament questions

The key design decision is:

```text
Tournament context is opt-in.

RiftKeep must not infer tournament intent from generic card-game language.
```

The default authority context is:

```text
Core Rules / normal Riftbound gameplay
```

Tournament Rules and format-legality logic should only become active when the user explicitly establishes tournament or format context.

This patch is intended to prevent failures such as:

```text
Can I play more than one Legend in my deck?
```

being incorrectly routed into tournament/format-legality handling.

---

# 1. Core Routing Principle

The routing model should be:

```text
DEFAULT
───────
Normal Core Rules / gameplay context

TOURNAMENT
──────────
Activated only when the player explicitly signals:
- tournament
- tournament rules
- sanctioned
- Constructed
- 2v2 Constructed
- format
- banned
- ban list
- tournament legal
- illegal in tournament play
```

Do not infer tournament intent from:

```text
deck
legal
allowed
can I play
can I use
can I run
can I include
```

Those phrases are common in normal gameplay and deck-construction questions.

---

# 2. Examples That Must Stay Core-Only

These questions should not activate Tournament Rules or banned-list logic:

```text
Can I play more than one Legend in my deck?
How many cards can my deck have?
Can I run four copies of this card?
Can I use 13 runes?
How many Signature cards can I include?
Can I play this unit now?
Can I use this ability again?
Can I move this unit?
Can I choose this unit as the target?
Can I play a Reaction here?
```

These are normal Core Rules questions.

They should route to the relevant deterministic Core subsystem:

```text
Deck Construction
Definition Lookup
Gameplay Legality
General Gameplay
Card Interaction
```

---

# 3. Examples That Explicitly Activate Tournament Context

These questions should activate Tournament Rules and/or format legality:

```text
Is Called Shot banned?
Is Called Shot legal in Constructed?
Can I use Called Shot in a tournament?
Is this card legal at a sanctioned event?
Can I play this deck in Constructed?
What are the tournament rules for deck registration?
At a tournament, can I change my deck between rounds?
Is this legal in 2v2 Constructed?
What happens if I am late to a tournament round?
```

These contain explicit tournament or format context.

---

# 4. "Banned" Is a Strong Tournament/Format Signal

The word:

```text
banned
```

is inherently format-legality language.

Example:

```text
Is Called Shot banned?
```

This should route to:

```text
format_legality
```

without requiring the user to also say:

```text
tournament
```

because "banned" is itself an explicit format-legality concept.

Similarly:

```text
ban list
Constructed legality
format legality
sanctioned
```

are strong signals.

---

# 5. "Legal" Alone Is Not Enough

The word:

```text
legal
```

is ambiguous in card-game questions.

Examples:

```text
Is this a legal target?
Is this move legal?
Is my deck legal?
Is this card legal?
```

These may mean very different things.

Therefore:

```text
"legal"
```

must not automatically mean:

```text
Tournament Rules
```

Routing must use context.

---

# 6. Ambiguous "Is My Deck Legal?" Questions

Question:

```text
Is my deck legal?
```

This does not specify whether the player means:

```text
normal deck-construction rules
```

or:

```text
tournament / format legality
```

RiftKeep should not guess.

Preferred clarification:

```text
Are you asking whether the deck follows normal Riftbound deck-construction rules,
or whether it is legal for a specific tournament format?
```

Then route based on the answer.

This is preferable to silently assuming:

```text
Constructed tournament legality
```

---

# 7. Core Rules Are the Default Authority

If no explicit tournament context exists:

```text
Core Rules own the question.
```

Examples:

```text
Can I have two Champion Legends?
Can my deck have 39 cards?
Can I run four copies?
Can I use 13 runes?
What does Ganking mean?
Can this unit move between battlefields?
```

The engine should answer from:

```text
Core Rules
Cards
FAQ
Errata
Current gameplay authority
```

as appropriate.

Tournament Rules should not be injected merely because the question contains deck-building terminology.

---

# 8. Tournament Context Adds Authority — It Does Not Replace Core Rules

This distinction is critical.

If the user says:

```text
At a tournament, can I move my Ganking unit from one battlefield to another?
```

the question contains tournament context.

However, the gameplay mechanic is still governed by Core Rules.

The correct authority model is:

```text
Core Rules
    +
Tournament Rules if tournament-specific policy/procedure applies
```

not:

```text
Tournament Rules instead of Core Rules
```

The engine should accumulate obligations rather than replace one authority family with another.

---

# 9. Mixed Core + Tournament Questions

Some questions legitimately require both authority families.

Example:

```text
At a tournament, can I play Called Shot in my deck?
```

Possible obligations:

```text
format_legality
deck_construction
```

Possible authority:

```text
Tournament / format source
+
Core Rule 103 deck-construction rules
```

Another example:

```text
At a tournament, what happens if I reveal my Hidden card incorrectly?
```

This may involve:

```text
Core Rules:
what Hidden/reveal does

Tournament Rules:
procedure, penalty, correction, judge handling
```

RiftKeep must be capable of combining both.

---

# 10. Do Not Use Exclusive Early-Return Routing

Avoid architecture like:

```python
if is_tournament_question(question):
    return adjudicate_tournament(question)
```

This is dangerous because tournament context can coexist with Core gameplay obligations.

Preferred model:

```json
{
  "obligations": [
    "core_gameplay",
    "tournament_procedure"
  ]
}
```

or:

```json
{
  "authorityFamilies": [
    "core",
    "tournament"
  ]
}
```

The engine should resolve all applicable obligations.

---

# 11. Recommended Question-Intent Model

Introduce or extend a deterministic intent/obligation layer.

Suggested intents:

```text
definition
deck_construction
format_legality
tournament_procedure
gameplay_legality
general_gameplay
card_interaction
source_history
```

Example:

```text
Can I play more than one Legend in my deck?
```

should become:

```json
{
  "intents": [
    "deck_construction"
  ],
  "authorityFamilies": [
    "core"
  ],
  "tournamentContext": false
}
```

---

# 12. Explicit Tournament Example

Question:

```text
Can I play two Champion Legends in a tournament deck?
```

Expected intent:

```json
{
  "intents": [
    "deck_construction"
  ],
  "authorityFamilies": [
    "core"
  ],
  "tournamentContext": true
}
```

Why?

Because the actual quantity rule is Core Rules.

Tournament context is known, but unless Tournament Rules modify that deck-construction requirement, the Core rule still decides it.

---

# 13. Explicit Format-Legality Example

Question:

```text
Is Called Shot legal in Constructed?
```

Expected:

```json
{
  "intents": [
    "format_legality"
  ],
  "authorityFamilies": [
    "tournament_or_format_authority"
  ],
  "tournamentContext": true
}
```

If other deck-building requirements matter, additional Core obligations may also be attached.

---

# 14. Explicit Tournament Procedure Example

Question:

```text
At a tournament, can I change my deck between rounds?
```

Expected:

```json
{
  "intents": [
    "tournament_procedure"
  ],
  "authorityFamilies": [
    "tournament"
  ],
  "tournamentContext": true
}
```

Core Rules may not be needed if this is purely tournament procedure.

---

# 15. Gameplay "Legal" Example

Question:

```text
Is this a legal target?
```

Expected:

```json
{
  "intents": [
    "gameplay_legality"
  ],
  "authorityFamilies": [
    "core"
  ],
  "tournamentContext": false
}
```

Do not route this to banned-list logic.

---

# 16. Strong Tournament/Format Signals

Recommended explicit signals:

```text
tournament
tournament rules
tournament legal
tournament legality
sanctioned
sanctioned event
constructed
2v2 constructed
format
format legal
format legality
banned
ban list
restricted
tournament deck
tournament play
event policy
match procedure
round
judge call
deck registration
deck list
penalty
game loss
match loss
disqualification
```

Not every word must always imply tournament procedure by itself.

Use context.

---

# 17. Weak Signals That Must Not Activate Tournament Context Alone

These should not be sufficient:

```text
deck
legal
illegal
allowed
can I play
can I use
can I run
can I include
valid
permitted
```

They need additional context.

---

# 18. Recommended Tournament-Context Detector

Implement something conceptually like:

```python
def detect_tournament_context(question: str) -> TournamentContext:
    ...
```

Output:

```json
{
  "explicit": true,
  "signals": [
    "constructed"
  ],
  "format": "constructed"
}
```

or:

```json
{
  "explicit": false,
  "signals": [],
  "format": null
}
```

This should be deterministic.

An AI interpretation layer may offer advisory suggestions, but it must not be the sole authority for activating Tournament Rules.

---

# 19. Keep Tournament Detection Separate From Format-Legality Detection

These concepts overlap but are not identical.

Example:

```text
At a tournament, what happens if I arrive late?
```

This is:

```text
tournament_context = true
format_legality = false
```

Example:

```text
Is Called Shot banned?
```

This is:

```text
tournament_context = true
format_legality = true
```

Example:

```text
Can I run four copies of this card?
```

This is:

```text
tournament_context = false
format_legality = false
deck_construction = true
```

---

# 20. Deck Construction Must Be Core by Default

The Deck Construction subsystem should own questions such as:

```text
How many Champion Legends?
How many cards?
How many runes?
How many copies?
How many Signature cards?
Domain Identity requirements?
Battlefield requirements?
```

These are Core Rule 103 questions unless the player explicitly asks about an additional format restriction.

---

# 21. Tournament Rules May Add Restrictions

If a tournament/format rule modifies normal deck construction, then the answer should combine both.

Conceptually:

```text
Core Rule:
maximum 3 copies

Tournament Format Rule:
Card X is banned

Question:
Can I run 3 copies of Card X in Constructed?
```

Result:

```text
Core Rules:
Three copies would normally satisfy the copy-count rule.

Format legality:
Card X is banned in this format.

Final answer:
No.
```

This demonstrates why obligation accumulation is better than exclusive routing.

---

# 22. Authority Precedence Must Remain Explicit

When both Core and Tournament authorities apply:

```text
do not merge text heuristically
```

Each finding should retain provenance.

Example:

```json
{
  "obligations": [
    {
      "type": "copy_limit",
      "authorityFamily": "core",
      "evidence": ["R:103.2.b"]
    },
    {
      "type": "format_legality",
      "authorityFamily": "tournament",
      "evidence": ["T:..."]
    }
  ]
}
```

The proof engine should reconcile the final result.

---

# 23. Update `is_legality_question()`

Current format-legality routing should no longer treat:

```text
deck + can I play
```

as enough evidence.

Preferred behavior:

```text
explicit format signal
OR
explicit ban/restriction signal
```

should be required.

Generic deck construction should not trigger it.

---

# 24. Update `engine.ask()`

Current exclusive early returns for legality should be removed or constrained.

Preferred pipeline:

```text
Question
   │
   ▼
Intent / obligation extraction
   │
   ├─ deck construction
   ├─ format legality
   ├─ tournament procedure
   ├─ gameplay legality
   └─ general gameplay
   │
   ▼
All applicable deterministic adjudicators
   │
   ▼
Proof aggregation
   │
   ▼
Final verdict
```

---

# 25. Ambiguity Policy

If tournament context is not explicit and the question is ambiguous, clarify rather than guess.

Example:

```text
Is this deck legal?
```

Clarify:

```text
Do you mean legal under normal Riftbound deck-construction rules,
or legal for a specific tournament format?
```

Example:

```text
Can I use this card?
```

Possible clarification:

```text
Do you mean whether you can play/use it in the current game state,
or whether it is legal in a tournament format?
```

Only ask when the ambiguity materially changes the authority path.

---

# 26. Do Not Over-Clarify Obvious Core Questions

Question:

```text
Can I play more than one Legend in my deck?
```

Do not ask:

```text
Are you asking about tournament play?
```

There is no explicit tournament context.

Default to Core Deck Construction and answer.

The point of this policy is not to force a clarification every time the word "deck" appears.

---

# 27. Do Not Over-Clarify Obvious Tournament Questions

Question:

```text
Is Called Shot banned?
```

Do not ask:

```text
Are you asking about tournament play?
```

"Banned" is already a strong format-legality signal.

Proceed with format legality.

---

# 28. Add Tournament Context to Structured Scenario/Issue Metadata

Recommended fields:

```json
{
  "tournamentContext": {
    "explicit": false,
    "format": null,
    "signals": []
  }
}
```

When explicit:

```json
{
  "tournamentContext": {
    "explicit": true,
    "format": "constructed",
    "signals": [
      "constructed"
    ]
  }
}
```

This gives downstream adjudicators a deterministic, inspectable context.

---

# 29. AI Interpretation Layer Must Preserve This Rule

M10-style AI interpretation may help recognize phrases, but the deterministic system should verify tournament context.

AI may suggest:

```json
{
  "suggestedTournamentContext": true,
  "phrase": "at my local tournament"
}
```

But the backend should validate the actual phrase against deterministic rules.

AI must not silently upgrade a normal question into Tournament Rules authority.

---

# 30. AI Must Not Use Its Own Tournament Knowledge

If Claude/OpenAI/etc. knows something about tournament formats from training data, ignore that knowledge unless RiftKeep supplies current deterministic authority.

The AI layer should not say:

```text
"This sounds like tournament legality."
```

and adjudicate from memory.

Correct behavior:

```text
AI interprets wording
RiftKeep determines applicable authority
RiftKeep adjudicates
AI explains
```

---

# 31. Product API Should Expose Authority Context

For debugging and UI transparency, `/v1/ask` may expose something like:

```json
{
  "authorityContext": {
    "core": true,
    "tournament": false,
    "formatLegality": false
  }
}
```

For a mixed question:

```json
{
  "authorityContext": {
    "core": true,
    "tournament": true,
    "formatLegality": true
  }
}
```

This makes misrouting obvious during development.

---

# 32. Add Routing Diagnostics

Internally record:

```text
detected intents
tournament-context signals
authority families selected
why each family was selected
```

Example:

```json
{
  "routing": {
    "intents": ["deck_construction"],
    "authorityFamilies": ["core"],
    "tournamentContext": false,
    "signals": []
  }
}
```

This will make future routing bugs much easier to identify.

---

# 33. Required Regression Matrix — Core Deck Construction

These must all remain Core-only:

```text
Can I play more than one Legend in my deck?
Can I have two Champion Legends?
Can my deck have multiple Legends?
How many Champion Legends can I use?
Can I run four copies?
Can I use 13 runes?
Can I use 39 cards?
How many Signature cards can I have?
Can I use two copies of the same Battlefield?
```

Assertions:

```text
tournamentContext == false
formatLegality == false
core authority selected
deck_construction intent selected
non-empty answer
proof verified when decidable
```

---

# 34. Required Regression Matrix — Gameplay Core

These must remain Core-only:

```text
Can I play this unit now?
Can I play a Reaction here?
Can I move this unit?
Can I use this ability twice?
Is this a legal target?
Can I reveal this Hidden card?
```

Assertions:

```text
tournamentContext == false
formatLegality == false
core authority selected
```

---

# 35. Required Regression Matrix — Tournament / Format

These must activate tournament/format handling:

```text
Is Called Shot banned?
Is Called Shot legal in Constructed?
Can I use Called Shot in a tournament?
Is this card legal at a sanctioned event?
Can I play this deck in 2v2 Constructed?
What does the tournament rules document say about this?
```

Assertions:

```text
tournamentContext == true
appropriate tournament/format authority selected
```

---

# 36. Required Regression Matrix — Tournament Procedure

These should activate Tournament Rules but not necessarily format legality:

```text
What happens if I am late to a tournament round?
Can I change my deck between tournament rounds?
How do I report a match result?
What happens if I accidentally draw an extra card at a tournament?
When should I call a judge?
```

Assertions:

```text
tournamentContext == true
tournament_procedure intent selected
formatLegality only if relevant
```

---

# 37. Required Regression Matrix — Ambiguous

These should clarify:

```text
Is my deck legal?
Is this legal?
Can I use this card?
Can I play this?
```

Only when there is insufficient context to distinguish:

```text
gameplay legality
deck construction
format legality
```

The clarification should be narrow and actionable.

---

# 38. Required Regression Matrix — Mixed Core + Tournament

Examples:

```text
Can I run 3 copies of Called Shot in Constructed?
At a tournament, can I have two Champion Legends?
At a tournament, can I use a Reaction during this showdown?
Is this deck valid under normal rules and legal for Constructed?
```

Assertions:

```text
multiple obligations allowed
Core Rules not discarded
Tournament Rules not discarded
final proof aggregates both when applicable
```

---

# 39. No Blank Answers

This routing patch must retain the separate non-blank Ask invariant.

Every successful `/v1/ask` response must have:

```text
non-empty answer
non-empty deterministicAnswer
```

If routing fails internally:

```text
return explicit insufficient/clarification/error
```

Never:

```json
{
  "answer": ""
}
```

---

# 40. Recommended Files to Modify

Likely implementation surface:

```text
src/riftkeep_rules/legality.py
src/riftkeep_rules/engine.py
src/riftkeep_rules/player_language.py
src/riftkeep_rules/scenario_language.py
src/riftkeep_rules/product_api.py
src/riftkeep_rules/writer.py
```

Recommended new or expanded modules:

```text
src/riftkeep_rules/question_intent.py
src/riftkeep_rules/deck_construction.py
```

Tests:

```text
tests/run_regressions.py
tests/run_product_api_tests.py
tests/run_ui_integration_tests.py
tests/run_stable_release_tests.py
```

Potential dedicated suite:

```text
tests/run_question_routing_tests.py
```

If a new certified suite is added:

```text
update the release-gate suite count intentionally
re-certify the release
```

---

# 41. Suggested Routing Data Structure

Example:

```json
{
  "questionIntent": {
    "intents": [
      "deck_construction"
    ],
    "tournamentContext": {
      "explicit": false,
      "format": null,
      "signals": []
    },
    "authorityFamilies": [
      "core"
    ]
  }
}
```

Mixed example:

```json
{
  "questionIntent": {
    "intents": [
      "deck_construction",
      "format_legality"
    ],
    "tournamentContext": {
      "explicit": true,
      "format": "constructed",
      "signals": [
        "constructed"
      ]
    },
    "authorityFamilies": [
      "core",
      "tournament"
    ]
  }
}
```

---

# 42. Recommended Decision Logic

Conceptually:

```text
detect definition intent

detect deck-construction intent

detect gameplay intent

detect explicit tournament context

detect explicit format-legality context

accumulate all applicable obligations

select authority families per obligation

run deterministic adjudicators

aggregate proof

render non-empty answer
```

Avoid:

```text
first keyword match wins
```

---

# 43. Important Semantic Rule

This should become a permanent design rule:

```text
"Tournament" is context.

It is not the default.
```

And:

```text
Core Rules are always the baseline rules of the game.

Tournament Rules are additional authority only when tournament context is explicit
or a clearly tournament-specific concept such as "banned" is used.
```

---

# 44. Acceptance Criteria

The patch is complete only when all of the following are true.

## Core default

```text
Can I play more than one Legend in my deck?
```

routes to:

```text
Core Rules
Deck Construction
```

and not tournament legality.

---

## Explicit tournament

```text
Can I play more than one Legend in a tournament deck?
```

recognizes tournament context but still uses Core Rule 103 for the quantity rule.

---

## Format legality

```text
Is Called Shot banned?
```

activates format-legality handling.

---

## Gameplay legality

```text
Is this a legal target?
```

remains Core gameplay.

---

## Ambiguous legality

```text
Is my deck legal?
```

asks whether the player means:

```text
normal deck-construction legality
or
specific tournament format legality
```

rather than guessing.

---

## Mixed authority

A question that genuinely requires both Core and Tournament authority can produce both obligations and combine them in one proof.

---

## No blank output

No successful Ask response can render blank.

---

# 45. Recommended Release Scope

This should be included in the same patch line as the Deck Construction routing fix.

Suggested release:

```text
RiftKeep Rules Engine 1.0.1
```

Suggested release title:

```text
Core-First Question Routing, Deck Construction & Tournament Context Hotfix
```

This remains compatible with:

```text
Product API v1
```

No breaking API version is necessary if new routing metadata is additive.

---

# 46. Final Design Principle for Claude

Claude should implement this patch according to the following permanent rules:

```text
1. Core Rules are the default authority.

2. Tournament Rules are opt-in context.

3. Generic words such as "deck", "legal", "allowed", "can I play",
   and "can I use" must not activate tournament routing by themselves.

4. Strong tournament/format signals such as "tournament",
   "Constructed", "sanctioned", "banned", and "ban list"
   may activate tournament/format context.

5. Tournament context adds applicable tournament authority;
   it does not remove Core Rules from gameplay questions.

6. Questions may have multiple obligations.

7. Do not use exclusive "first router wins" early-return logic.

8. Ambiguous questions should clarify rather than silently assume tournament intent.

9. Deck construction is a Core Rules question family by default.

10. Every successful Ask response must contain visible deterministic output.

11. AI may interpret player language, but AI does not decide which rules are true.

12. All routing decisions must remain deterministic, inspectable, testable,
    and backed by regression coverage.
```

The fundamental goal is:

```text
RiftKeep should answer the question the player actually asked,
without silently inventing tournament context that was never supplied.
```
