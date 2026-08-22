# RiftKeep 1.0.1 — Deck Construction Obligation Integration Fix
## Extend the Existing Proof/Compiler Architecture — Do Not Add a Parallel Deck Rules System

## Purpose

This document corrects and sharpens the earlier Deck Construction hotfix design.

The important architectural finding is:

```text
RiftKeep already contains the authoritative Deck Construction rules.

RiftKeep already compiles those rules into the semantic/canonical rule catalog.

RiftKeep already has a generalized proof-obligation architecture.

What is missing is promotion of Deck Construction into that existing executable obligation system.
```

Therefore the fix should **not** create an unrelated special-purpose deck-answer subsystem.

The correct patch is:

```text
Extend the existing obligation/compiler/proof architecture
to make Deck Construction rules executable.
```

This preserves the design established across the earlier milestones.

---

# 1. What Already Exists

RiftKeep Stable 1.0 already has all of the following:

```text
Authoritative Core Rules
Semantic IR
Compiled Rule Catalog
Rule Programs
Knowledge Graph / Retrieval
Scenario Model
Proof Engine
Evidence / Citation System
Product API
Stable Release Gate
```

The Core Rules already contain the Deck Construction rule family.

Examples include:

```text
103
103.1
103.2
103.3
103.4
```

with children covering:

```text
Champion Legend
Domain Identity
Main Deck
Chosen Champion
copy limits
Signature cards
Rune Deck
Battlefields
```

The compiler already knows these rules exist.

The missing piece is executable obligation coverage.

---

# 2. The Actual Gap

Current state conceptually looks like:

```text
AUTHORITATIVE RULE TEXT
        ✓

SEMANTIC IR
        ✓

COMPILED RULE CATALOG
        ✓

RETRIEVAL
        ✓

PROOF ENGINE
        ✓

DECK CONSTRUCTION OBLIGATION FAMILY
        ✗

DECK CONSTRUCTION EXECUTABLE RULE PROGRAMS
        ✗
```

That is why questions such as:

```text
Can I play more than one Legend in my deck?
```

can retrieve relevant rules but still fail to produce a deterministic verdict.

---

# 3. Existing Obligation Architecture

RiftKeep already contains executable obligation families for gameplay concepts.

Examples include obligation families such as:

```text
unit_play_location
battlefield_control_loss
hidden_lifecycle
discard_to_trash
ready_state
exhaust_state
stun_state
counter_resolution
mistarget_resolution
recall_not_move
replacement_order
targeting_permission_restriction
```

The Deck Construction patch should follow the same pattern.

Do not invent a different adjudication framework.

---

# 4. Required New Deck Obligation Families

Add Deck Construction obligations to the existing obligation registry.

Recommended initial families:

```text
deck_composition
champion_legend_count
main_deck_minimum
same_name_copy_limit
chosen_champion_requirement
signature_limit
signature_champion_tag
rune_deck_count
rune_domain_identity
card_domain_identity
battlefield_count_requirement
battlefield_duplicate_limit
```

Some of these may later be combined internally if the existing architecture prefers broader obligation names.

The important requirement is that the underlying constraints become executable.

---

# 5. Champion Legend Count Obligation

Authoritative basis:

```text
103
103.1
```

Constraint:

```text
exactly 1 Champion Legend
```

Example question:

```text
Can I play more than one Legend in my deck?
```

Normalized obligation:

```json
{
  "obligation": "champion_legend_count",
  "requestedQuantity": {
    "operator": "greater_than",
    "value": 1
  }
}
```

Compiled rule constraint:

```json
{
  "constraintType": "exact_count",
  "value": 1,
  "sourceRuleIds": [
    "103",
    "103.1"
  ]
}
```

Evaluation:

```text
required = exactly 1

requested = more than 1

result = NO
```

Proof result:

```text
decided
verified
```

---

# 6. Main Deck Minimum Obligation

Authoritative basis:

```text
103.2
```

Constraint:

```text
at least 40 cards
```

Questions:

```text
Can I use a 39-card Main Deck?
Can I have only 35 cards?
How many cards does my Main Deck need?
Can I have more than 40 cards?
```

Important distinction:

```text
minimum = 40
```

not:

```text
exactly 40
```

The deterministic program must preserve the operator.

---

# 7. Same-Named Copy Limit

Authoritative basis:

```text
103.2.b
103.2.b.1
103.2.b.2
```

Constraint:

```text
up to 3 copies of the same named card
```

Questions:

```text
Can I run four copies of the same card?
Can I use three copies plus my Chosen Champion?
Does the Chosen Champion count toward the three-copy limit?
Can I run three Yasuo, Remorseful and three Yasuo, Windrider?
```

The rule program must distinguish:

```text
same named card
```

from:

```text
same character
```

---

# 8. Chosen Champion Obligation

Authoritative basis includes:

```text
103.2.a
103.2.a.1
103.2.a.2
103.2.a.3
```

Required deterministic checks include:

```text
Chosen Champion must be a Champion Unit
Champion tag must match the Champion Legend
Chosen Champion starts in Champion Zone
same-name copies retain Chosen Champion status during play
```

This should be modeled as one or more proof obligations depending on current architecture.

---

# 9. Signature Card Obligations

Authoritative basis:

```text
103.2.d
103.2.d.1
103.2.d.2
103.2.d.3
```

Constraints include:

```text
maximum 3 total Signature cards
Signature cards must share the Champion tag of the Champion Legend
Signature cards are not Champion Units
Signature cards cannot occupy the Champion Zone
```

Example questions:

```text
Can I use four Signature cards?
Can I use Signature cards for a different Champion?
Can a Signature unit be my Chosen Champion?
```

---

# 10. Rune Deck Obligations

Authoritative basis:

```text
103.3
103.3.a
103.3.a.1
103.3.b
```

Constraints:

```text
exactly 12 Rune Cards
Runes must match Domain Identity
Rune Deck remains separate from Main Deck
Rune Deck is shuffled separately
```

Example questions:

```text
Can I use 13 runes?
Can I use 11 runes?
How many runes are required?
Can I use a Fury Rune in a deck without Fury Domain Identity?
```

---

# 11. Domain Identity Obligations

Authoritative basis includes:

```text
103.1.b
103.1.b.1
103.1.b.2
103.1.b.3
103.1.b.4
103.1.b.5
```

These rules should become executable.

Possible obligation families:

```text
card_domain_identity
rune_domain_identity
deck_domain_identity
```

Examples:

```text
Can I include this Fury card in my Calm deck?
Can a dual-domain card go in this deck?
Can an effect add a card outside my normal Domain Identity?
```

Named-card questions should use canonical card metadata.

Do not hard-code domain behavior from card names.

---

# 12. Battlefield Deck Obligations

Authoritative basis:

```text
103.4
103.4.a
103.4.b
103.4.c
```

Constraints include:

```text
Battlefield quantity depends on Mode of Play
Battlefields may be subject to Domain Identity
duplicate-name restrictions apply when multiple Battlefields are required
```

Some questions will require clarification.

Example:

```text
How many Battlefields can I have?
```

Possible required clarification:

```text
Which Mode of Play are you using?
```

Valid conditional behavior must contain a real unresolved predicate or clarification.

Never return an empty conditional result.

---

# 13. Numeric / Cardinality Parsing Must Be Deterministic

Deck questions frequently express numeric constraints in natural language.

Support:

```text
one
two
three
four
more than one
more than two
multiple
at least
at most
up to
exactly
only
less than
fewer than
more than
how many
```

Examples:

```text
two Legends
more than one Legend
4 copies
three Signature cards
39 cards
40 cards
13 runes
```

Normalize into explicit operators.

Example:

```json
{
  "operator": "greater_than",
  "value": 1
}
```

---

# 14. Generic "Legend" in Deck Context

Question:

```text
Can I play more than one Legend in my deck?
```

uses the category word:

```text
Legend
```

rather than:

```text
Champion Legend
```

Within a deck-construction question, the deck slot defined by Rule 103 is:

```text
Champion Legend
```

The deterministic language layer may normalize generic:

```text
Legend
```

to:

```text
Champion Legend
```

when deck-slot context makes that interpretation unambiguous.

Do not globally equate every Legend with Champion Legend.

Gameplay effects may involve non-Champion Legends.

---

# 15. Integrate With Existing Rule Compiler

Do not build Deck Construction rules as free-form Python conditionals disconnected from rule provenance.

Use the existing compiler/program architecture.

Recommended flow:

```text
Core Rule 103 family
        │
        ▼
Semantic IR
        │
        ▼
Deck obligation semantic tags
        │
        ▼
Compiled executable rule programs
        │
        ▼
Source-hash guards
        │
        ▼
Proof obligations
```

Deck programs should disable themselves if their source text/hash no longer matches the expected authority, just like other guarded deterministic programs.

---

# 16. Required Semantic Tags

Add or extend semantic tags in the compiled catalog.

Examples:

```text
deck.construction
deck.legend.count
deck.main.minimum
deck.copy_limit.same_name
deck.chosen_champion
deck.signature.limit
deck.signature.tag
deck.rune.count
deck.domain_identity
deck.battlefield.requirement
deck.battlefield.duplicate_limit
```

Use naming consistent with the existing compiler conventions.

---

# 17. Source Guards

Each executable Deck Construction program should retain exact provenance.

Example:

```json
{
  "programId": "deck.champion_legend_count",
  "requiredRuleIds": [
    "103",
    "103.1"
  ],
  "sourceGuards": {
    "family": "core",
    "sourceId": "current-core-source-id",
    "ruleTextHashes": {
      "103.1": "..."
    }
  }
}
```

If authority changes:

```text
source hash mismatch
        │
        ▼
program disabled
        │
        ▼
recompile / review required
```

Do not continue executing stale semantic assumptions.

---

# 18. Retrieval Should Seed the Correct Rule Family

When intent/obligation detection identifies:

```text
deck_construction
```

the retrieval/evidence layer should seed Rule 103.

Then narrow based on subject.

Example:

```text
Champion Legend
    → 103
    → 103.1
    → relevant 103.1 children

copy limit
    → 103.2.b family

Signature
    → 103.2.d family

Rune Deck
    → 103.3 family

Battlefields
    → 103.4 family
```

This prevents semantic retrieval from burying the decisive structural rule below less relevant matches.

---

# 19. Proof Engine Integration

Deck questions should go through the existing proof engine.

Example:

```text
Question:
Can I have two Champion Legends?

Detected obligation:
champion_legend_count

Rule program:
exactly 1 Champion Legend

Requested count:
2

Applicability:
TRUE

Conflict:
none

Verdict:
NO

Evidence:
103
103.1

Proof:
VERIFIED
```

The answer must not bypass proof verification.

---

# 20. Multiple Deck Obligations

A single question may produce several obligations.

Example:

```text
Can I run four copies of a Signature card from a different Champion?
```

Possible obligations:

```text
same_name_copy_limit
signature_limit
signature_champion_tag
domain_identity
```

The engine should accumulate all applicable obligations.

Do not use:

```text
first matching rule wins
```

---

# 21. Mixed Deck + Tournament Questions

Tournament context is separate from Deck Construction.

Example:

```text
Can I run three copies of Called Shot in Constructed?
```

Possible obligations:

```text
same_name_copy_limit
format_legality
```

Authority:

```text
Core Rules
+
Tournament / format authority
```

Deck Construction remains a Core obligation.

Tournament context does not replace it.

---

# 22. Tournament Context Must Remain Explicit

Permanent routing rule:

```text
Core Rules are the default.

Tournament context is opt-in.
```

Do not route generic Deck Construction questions to tournament/format legality merely because they contain:

```text
deck
legal
allowed
can I play
can I use
can I run
```

Strong tournament signals include:

```text
tournament
Constructed
2v2 Constructed
sanctioned
banned
ban list
format
tournament legal
```

This routing fix should be implemented together with Deck obligations.

---

# 23. Do Not Implement a Separate `deck_answer()` Shortcut

Avoid code such as:

```python
def answer_deck_question(question):
    if "legend" in question:
        return "No"
```

Avoid any parallel architecture like:

```text
DeckQuestionHandler
        bypasses
Compiler
Proof Engine
Evidence
```

That would undermine RiftKeep's deterministic architecture.

Deck Construction must become another first-class obligation family inside the system that already exists.

---

# 24. Do Not Hard-Code the Trigger Sentence

Never implement:

```python
if question == "Can I play more than one Legend in my deck?":
    return ...
```

The exact question is only a regression example.

The semantic rule is:

```text
Champion Legend deck slot has exact cardinality 1.
```

All paraphrases should converge on that obligation.

---

# 25. Required Trigger Regression

Permanent test:

```text
Can I play more than one Legend in my deck?
```

Expected:

```text
status = decided
verdict = no
proof = verified
answer != blank
deterministicAnswer != blank
deck_construction selected
champion_legend_count selected
format_legality NOT selected
Core authority selected
Rule 103 evidence present
Rule 103.1 evidence present
```

---

# 26. Required Champion Legend Paraphrases

Test:

```text
Can I have two Legends in my deck?
Can I run two Champion Legends?
Can my deck have multiple Legends?
Can I use more than one Champion Legend?
How many Champion Legends can my deck contain?
Can I put 2 Legends in a deck?
Is more than one Champion Legend allowed?
How many Legends do I need?
```

All should resolve through the same constraint.

---

# 27. Required Main Deck Tests

Test:

```text
Can I have a 39-card Main Deck?
Can I use only 35 cards?
Can I have more than 40 cards?
How many cards does my Main Deck need?
```

Expected semantic distinction:

```text
39 → invalid
35 → invalid
40 → valid minimum
>40 → not invalid merely because it exceeds 40
```

subject to any other rules.

---

# 28. Required Copy-Limit Tests

Test:

```text
Can I run four copies of the same card?
Can I have three copies plus my Chosen Champion?
Does my Chosen Champion count toward the copy limit?
Can I run three Yasuo, Remorseful and three Yasuo, Windrider?
```

Expected evidence:

```text
103.2.b family
```

---

# 29. Required Signature Tests

Test:

```text
Can I use four Signature cards?
Can I use Signature cards from another Champion?
Can a Signature unit be my Chosen Champion?
```

Expected evidence:

```text
103.2.d family
```

---

# 30. Required Rune Tests

Test:

```text
Can I use 13 runes?
Can I use 11 runes?
How many runes do I need?
Can my Rune Deck contain a rune outside my Domain Identity?
```

Expected evidence:

```text
103.3 family
```

---

# 31. Required Battlefield Tests

Test:

```text
How many Battlefields do I need?
Can I use two copies of the same Battlefield?
```

If Mode of Play is required:

```text
status = conditional
clarification exists
answer is non-empty
```

Never:

```text
conditional
+
no outcome
+
no clarification
```

---

# 32. No-Blank Ask Invariant

This patch should also retain the separate renderer/API safety fix.

Every successful Ask response must satisfy:

```python
answer.strip() != ""
deterministicAnswer.strip() != ""
```

If deterministic adjudication cannot decide:

```text
return visible insufficient explanation
```

If missing information is required:

```text
return visible clarification
```

Never return a blank successful response.

---

# 33. Conditional Result Invariant

A valid conditional result must have at least one of:

```text
clarifying question
unknown predicate
missing fact
condition-dependent outcome
```

This state is invalid:

```json
{
  "status": "conditional",
  "outcomes": [],
  "clarifyingQuestions": []
}
```

Convert it to:

```text
insufficient
```

or an internal contract error before Product API rendering.

---

# 34. Recommended Code Areas

Inspect and extend:

```text
src/riftkeep_rules/proof.py
src/riftkeep_rules/proof_engine.py
src/riftkeep_rules/rule_compiler.py
src/riftkeep_rules/rule_programs.py
src/riftkeep_rules/retrieval.py
src/riftkeep_rules/player_language.py
src/riftkeep_rules/scenario_language.py
src/riftkeep_rules/engine.py
src/riftkeep_rules/writer.py
src/riftkeep_rules/product_api.py
src/riftkeep_rules/legality.py
```

Exact filenames may differ slightly in the current source tree.

The implementation should follow existing patterns rather than creating isolated one-off code.

---

# 35. Recommended New Module Only If It Fits Existing Architecture

If Deck Construction logic requires a dedicated module, use something like:

```text
src/riftkeep_rules/deck_construction.py
```

But that module should provide:

```text
obligation detection
constraint extraction
compiled-program helpers
```

and feed the normal proof engine.

It must not become an alternative adjudicator bypassing the existing system.

---

# 36. Suggested Deck Obligation Registry

Conceptually:

```python
DECK_OBLIGATIONS = {
    "champion_legend_count",
    "main_deck_minimum",
    "same_name_copy_limit",
    "chosen_champion_requirement",
    "signature_limit",
    "signature_champion_tag",
    "rune_deck_count",
    "rune_domain_identity",
    "card_domain_identity",
    "battlefield_count_requirement",
    "battlefield_duplicate_limit",
}
```

Integrate this with the same registry/process used for existing proof obligations.

---

# 37. Proof Completeness

A deck-construction verdict should fail closed if its required obligation cannot be proven.

Example:

```text
Question:
Can I use this card in my deck?

Known:
card identity

Unknown:
Champion Legend / Domain Identity
```

Do not guess.

Return:

```text
conditional
```

with a clarification such as:

```text
Which Champion Legend is the deck using?
```

Then evaluate Domain Identity once supplied.

---

# 38. Deck Validation Can Reuse These Same Obligations

Once Deck Construction obligations are executable, the same programs can later power a full deck validator.

Example:

```text
Deck List
   │
   ▼
Generate obligations
   │
   ├─ Champion Legend count
   ├─ Main Deck size
   ├─ copy limits
   ├─ Signature rules
   ├─ Rune count
   ├─ Domain Identity
   ├─ Battlefield rules
   └─ format legality if explicitly requested
   │
   ▼
Proof Engine
   │
   ▼
Deck Validation Report
```

This is preferable to building a separate deck-validator rules implementation.

---

# 39. Future Full-Deck Validation Output

Conceptually:

```json
{
  "valid": false,
  "issues": [
    {
      "obligation": "champion_legend_count",
      "verdict": "fail",
      "actual": 2,
      "required": 1,
      "evidence": [
        "R:103",
        "R:103.1"
      ]
    },
    {
      "obligation": "rune_deck_count",
      "verdict": "pass",
      "actual": 12,
      "required": 12
    }
  ]
}
```

This would naturally reuse the same deterministic rule programs.

---

# 40. Why This Is the Correct Architectural Fix

The existing architecture was designed to turn rules into:

```text
authority
→ semantic meaning
→ executable obligations
→ proof
→ verdict
```

Deck Construction should follow the same path.

The bug occurred because that last promotion step was never completed for Rule 103.

The correct repair is therefore:

```text
finish the architecture
```

not:

```text
add another special-case system
```

---

# 41. Stable Release Requirements

Do not silently edit the certified M19 ZIP.

Ship as a patch revision.

Recommended release:

```text
RiftKeep Rules Engine 1.0.1
```

Suggested title:

```text
Deck Construction Obligation & Core-First Routing Hotfix
```

Product API should remain:

```text
v1
```

unless an actual breaking response-contract change is introduced.

Additive routing/debug fields are acceptable if handled compatibly.

---

# 42. Release Gate Requirements

After implementation:

```text
rebuild
```

Then run all existing certified suites.

Add permanent regressions for:

```text
Deck Construction obligations
Tournament routing boundaries
No-blank Ask output
Mixed Core + Tournament obligations
```

If a new certified suite is introduced:

```text
increment certified suite count
update Update Automation expectations
update Stable release manifest
update project audit
re-certify clean candidate
re-certify final archive
restore-test recovery backup
```

No release-gate drift is allowed.

---

# 43. Claude Implementation Rule

Claude should treat this as an extension of the existing architecture.

Permanent instruction:

```text
Do not create a parallel Deck Construction answer engine.

Promote Rule 103 and its children into the same executable
obligation/compiler/proof system already used by RiftKeep.
```

---

# 44. Final Expected Flow

Question:

```text
Can I play more than one Legend in my deck?
```

Correct flow:

```text
Player Language
      │
      ▼
Question Intent
      │
      ▼
deck_construction
      │
      ▼
Obligation Detection
      │
      ▼
champion_legend_count
      │
      ▼
Compiled Rule Program
      │
      ▼
Rule 103 / 103.1
exactly 1 Champion Legend
      │
      ▼
requested quantity > 1
      │
      ▼
NO
      │
      ▼
Proof Engine
      │
      ▼
VERIFIED
      │
      ▼
Non-empty deterministic answer
      │
      ▼
Optional constrained AI explanation
```

Tournament Rules are never involved unless the user explicitly provides tournament/format context or uses an inherently format-specific concept such as:

```text
banned
Constructed
sanctioned
format legality
```

---

# 45. Final Design Principle

The fix should preserve the core RiftKeep philosophy:

```text
Rules are not answers stored in code.

Rules become deterministic obligations.

Obligations are proven against authority.

Answers are rendered from verified proof.
```

Deck Construction should finally become a first-class participant in that same system.
