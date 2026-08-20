You are working on the **RiftKeep / RiftBoundTracker Ask Rules system**.

I am providing you the CURRENT implementation. **Inspect the actual files before changing anything. Do not redesign the rules system from scratch.**

The deterministic rule retrieval system is already substantially developed and working. The problem I want you to solve is specifically the **AI adjudication and player-facing answer quality**.

# PRIMARY GOAL

I want Ask Rules to answer questions like a knowledgeable human Riftbound judge.

For example, a user may ask:

> "Can you play units to battlefields you control and bypass playing to base, and does this make the battlefield contested?"

I want a response resembling:

## Answer

### 1. Yes, you can play a unit directly to a battlefield you control

When you play a unit, you choose a valid location for it to enter.

> "For Units, choose a valid Location where that Unit will enter upon being Played."  
> Rule 355.2

By default, both your base and battlefields you control are valid choices.

> "By default, Valid Locations include the controller's Base or a Battlefield the controller controls."  
> Rule 355.3

So you can play the unit straight to a battlefield you control without first playing it to base.

### 2. No, this does not make the battlefield Contested

Contested applies when a unit controlled by a player who does **not already control that battlefield** becomes present there.

> Relevant official Contested rule

Because you already control the battlefield, that condition is false, so Contested is not applied.

## Conclusion

- Yes, you may play the unit directly to a battlefield you control.
- No, that alone does not make the battlefield Contested because you already control it.

The important characteristics are:

- Direct answer first.
- Recognize when the player asked multiple questions.
- Answer each issue separately.
- Use the actual retrieved rules.
- Quote the strongest relevant rule text.
- Explain **why** the rule answers the player's situation.
- Combine multiple rules when needed.
- Understand conditions and negations correctly.
- Do not hallucinate rules.
- End with a concise conclusion.
- Sound like an experienced player/judge, not a search engine.

---

# CURRENT IMPLEMENTATION — IMPORTANT

Inspect these files particularly carefully:

```text
Rules/Ask/RulesAnswerService.cs
Rules/Ask/RulesEvidenceService.cs
Rules/Ask/RulesQuestionService.cs
Rules/Ask/RulesQuestionAnalysis.cs
Rules/Ask/IRulesExplanationProvider.cs
Rules/Ask/LocalLlmExplanationProvider.cs
Rules/Ask/LocalAiModelCatalog.cs
Rules/RulesSearchService.cs
Rules/RulesService.cs
```

Do not assume an older architecture.

Several improvements have ALREADY been made.

## Full rule text is already used

`LocalLlmExplanationProvider.BuildUserMessage()` uses:

```csharp
e.Hit.FullText
```

rather than the old 220-character UI snippet.

Do NOT "fix" this again.

The UI snippet can remain truncated.

---

## Card text is already supplied

`RulesQuestionService` supplies the selected card's actual text through `CardSummaryDto.Text`.

`RulesEvidenceService` also produces `CardEvidence` for:

- printed card text
- legality
- errata

Do NOT redesign this from scratch.

---

## Retrieval already performs multi-hop rule traversal

`RulesEvidenceService` already traverses `RuleCrossReferences` for up to 3 hops and has logic to prevent heavily referenced hub rules from overpowering directly relevant rules.

Do NOT replace this with a generic RAG system.

Do NOT remove the weighting/ranking work that is already there.

---

## Current evidence count

`RulesAnswerService` currently calls:

```csharp
evidenceService.GatherAsync(
    analysis,
    currentOnly: true,
    limit: 16,
    ct);
```

That is intentional.

Do not arbitrarily increase evidence count unless testing proves it is required.

---

## Current evidence prompt budget

`LocalLlmExplanationProvider` currently has approximately:

```csharp
perItemCap = 1400;
totalBudget = 9000;
```

and the model context is currently:

```csharp
ContextSize = 6144;
```

These were increased because actual interaction questions required more rules.

Do not blindly change these values.

If you change them, justify it based on actual prompt/token requirements and tests.

---

# CURRENT MODEL

The current supported model is:

```text
Qwen2.5 1.5B
```

It has been fine-tuned against the Riftbound rules corpus.

There was previously a Qwen3 1.7B experiment.

It was removed because it performed **worse on actual rules reasoning**, including a reproducible question involving Might and marked damage.

Therefore:

**DO NOT replace Qwen2.5 merely because another model is newer.**

**DO NOT add a cloud AI dependency.**

**DO NOT require an external API.**

Everything must remain capable of running locally.

The current GGUF/model-management architecture should remain intact.

---

# THE ACTUAL PROBLEM

The current flow is approximately:

```text
Player Question
      ↓
RulesQuestionService
      ↓
Keyword / Concept / Rule-number detection
      ↓
RulesEvidenceService
      ↓
FTS + keyword + concept + rule graph retrieval
      ↓
Ranked evidence
      ↓
LocalLlmExplanationProvider
      ↓
Final answer
```

The problem is that the final 1.5B model is currently being asked to perform too many jobs simultaneously.

It must:

1. Understand the player's situation.
2. Determine whether the question contains multiple issues.
3. Interpret all relevant rules.
4. Resolve conditions and negations.
5. Determine which rules interact.
6. Determine the actual ruling.
7. Select which evidence proves each part.
8. Write polished prose.
9. Format the answer.
10. Avoid hallucinating citations.

That is too much responsibility for a single unrestricted generation pass.

I want the system changed so **ruling/adjudication and human explanation are distinct responsibilities.**

---

# IMPORTANT CURRENT PROMPT PROBLEM

Inspect the current `SystemPrompt` in:

```text
LocalLlmExplanationProvider.cs
```

It currently contains instructions similar to:

> "Keep the answer concise — a few sentences, not an essay."

That is directly opposed to the response style I now want.

I am NOT asking for enormous essays, but I do want enough room for:

- separate issues
- direct answers
- rule quotations
- explanations
- conclusion

Also inspect:

```csharp
MaxTokens = 350
```

This may be too restrictive for the desired answer format.

Do not simply set it to an enormous number.

Choose a reasonable output budget after evaluating the desired answer length.

Something approximately in the 600–900 token range may be appropriate, but determine that from the actual implementation and tests.

---

# TARGET ARCHITECTURE

Preserve the existing retrieval system and evolve the final portion toward:

```text
Player Question
      ↓
Existing RulesQuestionService
      ↓
Existing RulesEvidenceService
      ↓
Existing ranked evidence
      ↓
NEW: Rules Adjudication
      ↓
NEW: Adjudication Validation
      ↓
Player Explanation
      ↓
Final Human-Like Answer
```

The important boundary is:

```text
RETRIEVAL
determines what evidence is available

ADJUDICATION
determines what that evidence means for this situation

EXPLANATION
communicates the already-determined result naturally
```

---

# 1. ADD ISSUE DECOMPOSITION

The current `RulesQuestionAnalysis` identifies:

- rule numbers
- keywords
- concepts
- card context
- expanded terms

That is useful and should remain.

However, it does not formally represent the **individual questions/issues** contained in a player's sentence.

For:

> "Can I play a unit directly to a battlefield I control, and does it become Contested?"

the reasoning layer should recognize:

```text
Issue 1:
Can the unit be played directly to the controlled battlefield?

Issue 2:
Does the battlefield become Contested as a result?
```

Do NOT necessarily use another expensive standalone AI request purely for question decomposition if it is unnecessary.

A good implementation may allow the adjudication pass itself to return multiple issues.

Choose the cleanest solution for the existing architecture.

---

# 2. CREATE A STRUCTURED ADJUDICATION RESULT

I want an intermediate result that is NOT player-facing prose.

Something conceptually like:

```csharp
public sealed record RulesAdjudication(
    string OverallVerdict,
    IReadOnlyList<RulesAdjudicatedIssue> Issues,
    IReadOnlyList<string> MissingInformation);

public sealed record RulesAdjudicatedIssue(
    string Question,
    string Answer,
    string Reason,
    IReadOnlyList<string> EvidenceIds);
```

Exact naming/types are up to you.

For the example question, it should conceptually represent:

```json
{
  "overallVerdict": "Mixed",
  "issues": [
    {
      "question": "Can the unit be played directly to a battlefield the player controls?",
      "answer": "Yes",
      "reason": "A controlled battlefield is a valid location when playing a unit.",
      "evidenceIds": ["E1", "E2"]
    },
    {
      "question": "Does doing so make that battlefield Contested?",
      "answer": "No",
      "reason": "The Contested condition requires the arriving unit's controller to not already control the battlefield.",
      "evidenceIds": ["E3", "E4"]
    }
  ],
  "missingInformation": []
}
```

This is internal machine data.

The player should not see raw JSON.

---

# 3. ASSIGN STABLE EVIDENCE IDS

Do not let the model freely type rule numbers as citations.

Before adjudication, transform retrieved evidence into something like:

```text
E1 = Rule 355.2
E2 = Rule 355.3
E3 = Rule 190.3
E4 = Rule 190.3.a
```

The model should reference:

```text
E1
E2
E3
```

rather than inventing:

```text
Rule 355.2
Rule 593.8
etc.
```

The backend already knows the authoritative:

- database ID
- rule number
- title
- authority
- current/historical state
- full text

So use the backend to resolve evidence IDs back into real citations.

This creates a hard boundary against hallucinated rule numbers.

---

# 4. ADJUDICATION MODEL RESPONSIBILITY

The adjudication pass should receive:

- original player question
- detected card context
- card evidence
- retrieved rule evidence
- stable evidence IDs

Its job is ONLY to establish the ruling.

The adjudication prompt should require it to determine:

1. What exactly is the player asking?
2. Are there multiple independent issues?
3. What facts are stated in the hypothetical?
4. Which supplied rules apply?
5. What conditions must be true for those rules?
6. Are those conditions actually true in the player's scenario?
7. Are there negations such as:
   - "does not"
   - "unless"
   - "if not"
   - "only if"
8. Is an action:
   - mandatory
   - optional
   - prohibited
   - allowed
9. Does a card-specific rule modify a general rule?
10. Does an official keyword change the interaction?
11. Is there enough supplied evidence for a definitive ruling?

The model must NOT:

- use outside TCG knowledge
- assume Riftbound works like Magic/Pokémon/Yu-Gi-Oh!
- invent a missing game mechanic
- invent a rule
- invent a citation
- decide something unsupported by the supplied evidence

If evidence is insufficient:

```text
Insufficient evidence
```

is a valid result.

Guessing is not.

---

# 5. VALIDATE THE ADJUDICATION

Add a validation layer.

For example:

```text
RulesAdjudicationValidator
```

Every `EvidenceId` returned by the adjudicator must exist in the evidence packet.

If the model returns:

```text
E1
E4
E99
```

but no `E99` exists:

the result is invalid.

Do not silently render E99 as a citation.

At minimum:

- validate evidence IDs
- reject unsupported IDs
- prevent arbitrary rule numbers from entering the final answer
- log validation failures for debugging

If practical, retry the adjudication once with a corrective prompt when its structured output is malformed.

Do not create infinite retry loops.

---

# 6. DO NOT RELY ON THE LLM TO COPY OFFICIAL RULE TEXT

The backend already possesses authoritative rule text.

Use it.

The LLM should decide:

> E2 is useful here.

The backend/UI should render the quotation from:

```text
E2.FullText
```

or the appropriate exact stored rule text.

Do NOT ask a 1.5B model to manually reproduce official text from memory.

That produces unnecessary transcription errors.

Desired:

```text
AI:
Use E2.

Backend:
E2 -> Rule 355.3 -> exact database text.
```

---

# 7. PLAYER-FACING EXPLANATION PASS

Once adjudication is validated, generate the human response.

This pass should receive:

```text
Original Question
+
Validated Adjudication
+
Only supporting evidence needed for those findings
+
Relevant Card Text
```

Tell this model explicitly:

> THE RULING HAS ALREADY BEEN DETERMINED. DO NOT RE-ADJUDICATE IT.

Its responsibility is communication.

Target style:

```text
Answer

1. Yes, you can play a unit directly to a battlefield you control

[plain-language explanation]

[authoritative rule quotation]

[explain why this rule matters]

2. No, this does not make the battlefield Contested

[plain-language explanation]

[authoritative rule quotation]

[apply condition to this exact situation]

Conclusion

• ...
• ...
```

It should not mechanically force two numbered sections if there is only one issue.

Examples:

Single question:

```text
Answer

Yes. ...

Why this works:
...

Rule 123.4:
...

Conclusion:
...
```

Multi-part question:

```text
1. Yes...
2. No...
```

Use natural judgment.

---

# 8. THE EXPLANATION MUST EXPLAIN "WHY"

I do not want this:

> Rule 355.3 says controlled battlefields are valid locations. Therefore yes.

I want this:

> Yes. When a unit is played, you choose a valid location for it to enter. Rule 355.3 establishes that a battlefield you already control is one of those valid locations, so the unit does not have to enter your Base first.

The model should explicitly connect:

```text
rule condition
+
player's facts
=
result
```

Especially for conditional rules.

Example:

```text
Rule:
Contested applies if the unit's controller does not already control
the battlefield.

Player fact:
The player DOES already control it.

Therefore:
The required condition is false.

Result:
Contested is not applied.
```

This kind of reasoning is critical.

---

# 9. USE FEW-SHOT EXAMPLES

The current Qwen2.5 model is small.

Instructions alone may not reliably produce the desired formatting and reasoning behavior.

Add several carefully chosen few-shot examples to the explanation/adjudication prompts OR another maintainable mechanism that teaches the expected shape.

Use examples for:

- simple yes/no
- two-part question
- keyword interaction
- negation/conditional interaction
- card + general rule interaction
- insufficient evidence
- optional vs mandatory action

Keep examples compact enough that they do not consume the evidence context window.

Do not hardcode actual rulings into application behavior.

Examples teach the model **how to reason/answer**, not what the rules are.

If the fine-tuned model's existing training format conflicts with the new format, inspect the training pipeline and document what needs to change.

Do not immediately retrain unless necessary to complete the requested behavior.

---

# 10. CONSIDER STRUCTURED UI OUTPUT

`RulesAskResponse` currently contains primarily:

```text
Question
Answer
AnswerGenerated
Confidence
Keywords
Concepts
Sources
CardNotes
```

Evaluate whether the final response should remain one generated markdown/plain-text answer or expose structured sections.

For example:

```csharp
RulesAnswerSection
{
    Heading
    Answer
    Explanation
    SupportingRules
}
```

Structured output may make it much easier for the frontend to display:

- numbered findings
- quote blocks
- clickable Rule chips
- conclusion
- source links

However:

**Do not unnecessarily break the existing API contract.**

If the existing UI relies on `Answer`, preserve compatibility or introduce the new structure additively.

---

# 11. CONFIDENCE MUST REMAIN DETERMINISTIC

The current architecture intentionally computes confidence from retrieval evidence in:

```text
RulesAnswerService.DetermineConfidence()
```

The comments explicitly state:

> evidence quality, not AI confidence, drives the answer.

KEEP THIS PRINCIPLE.

Do not replace it with:

```text
"LLM says 97% confidence"
```

The LLM may report whether evidence is insufficient for a particular issue, but the existing retrieval-grounded confidence system should remain authoritative.

---

# 12. PRESERVE THE CURRENT LOCAL MODEL ARCHITECTURE

Do not:

- add OpenAI
- add Claude API
- add Gemini
- add a remote inference server
- require an API key
- silently switch model families
- remove Qwen2.5

The user intentionally wants local inference.

Reuse the currently resident model weights where possible.

If adjudication and explanation become separate calls, avoid loading the ~1GB model twice.

The existing singleton/resident-weight architecture should be preserved.

Each request may use separate fresh contexts, but the weights should stay loaded as they do now.

---

# PERFORMANCE

Remember this is local inference on a relatively small model.

Do not create an absurd multi-agent chain with 8 LLM calls per question.

Target something like:

```text
1 adjudication generation
+
1 explanation generation
```

where necessary.

If a simple question can safely be handled with fewer calls, you may optimize later.

Correctness is currently more important than shaving one inference call, but avoid needless architecture.

---

# TEST CASES

Add tests around the new behavior.

At minimum include scenarios equivalent to:

## Test A — controlled battlefield + Contested

Question:

> Can you play units to battlefields you control and bypass playing to base, and does this make the battlefield contested?

Expected reasoning shape:

```text
Issue 1 = YES
Issue 2 = NO
```

The second result must correctly evaluate the negated condition around already controlling the battlefield.

---

## Test B — marked damage vs Might

Use the known regression type:

> If my card has 8 Might and someone does 2 damage to it, does that make its Might 6?

Expected:

Damage being marked must not automatically be interpreted as reducing printed/current Might unless supplied rules explicitly say so.

This is an important regression because Qwen3 previously failed this interaction.

---

## Test C — insufficient evidence

Construct a question where retrieved rules genuinely do not establish the answer.

Expected:

The AI clearly states that the supplied official evidence is insufficient.

It must not invent a ruling.

---

## Test D — multi-rule condition

Use a question whose answer requires combining at least two rules.

Verify:

- both evidence IDs survive adjudication
- the final explanation connects them logically
- citations correspond to actual supplied rules

---

## Test E — card text interaction

Use a card question where the answer depends on:

```text
card printed/effective text
+
a general rule or keyword rule
```

Verify that card text remains part of the evidence and is not dropped.

---

# LOGGING / DEBUGGING

Add useful development logging around the AI path.

I want to be able to inspect:

```text
Question
Detected keywords/concepts
Retrieved evidence IDs
Evidence ranking
Evidence actually inserted into prompt
Structured adjudication
Validation result
Final explanation
```

Do not log huge model files or unnecessary sensitive data.

This should make it possible to determine whether a wrong answer came from:

```text
bad retrieval
vs
missing evidence
vs
bad adjudication
vs
bad explanation
```

That distinction is extremely important.

---

# DO NOT BREAK EXISTING FUNCTIONALITY

This is critical.

DO NOT:

- replace the rules database
- replace the existing FTS system
- remove keyword detection
- remove concepts
- remove cross-reference traversal
- remove authority weighting
- remove errata
- remove card legality
- remove card evidence
- remove current/historical filtering
- remove deterministic confidence
- change model download/release behavior unnecessarily
- rewrite unrelated rules code
- change working APIs without compatibility consideration

The current system has already gone through substantial debugging.

Make the smallest clean changes necessary to improve adjudication and explanation quality.

---

# IMPLEMENTATION APPROACH

Before editing:

1. Read the current source.
2. Trace one Ask Rules request completely from `RulesAnswerService` through inference.
3. Inspect the model/training integration.
4. Identify the minimum files that need to change.
5. Explain your proposed implementation plan.
6. Then implement it incrementally.
7. Build after each logical stage.
8. Run existing tests.
9. Add regression tests for the new behavior.
10. Do not leave the project in a partially compiling state.

Do not assume comments are stale. Many comments in these files document bugs that were already discovered through real testing.

Respect those decisions unless you have concrete evidence they are now wrong.

---

# SUCCESS CRITERIA

I should be able to ask a natural question such as:

> "Can you play units to battlefields you control and bypass playing to base, and does this make the battlefield contested?"

and receive a result similar to:

## Answer

### 1. Yes, you can play a unit directly to a battlefield you control

When playing a unit, you select a valid location for it to enter.

> Rule 355.2 — [exact official rule text]

A battlefield you already control is one of the valid locations.

> Rule 355.3 — [exact official rule text]

So the unit does not need to enter your Base first.

### 2. No, this does not make the battlefield Contested

The relevant Contested rule only applies when the arriving unit's controller does **not already control the battlefield**.

> Rule 190.3.a — [exact official rule text]

In this situation you already control the battlefield, so that requirement is false. The battlefield therefore does not become Contested merely because you played another unit there.

## Conclusion

- You can play the unit directly to your controlled battlefield.
- You do not need to play it to Base first.
- Doing so does not make your own battlefield Contested.

The exact wording does not need to be identical.

The important thing is that the system:

**finds the evidence → adjudicates it correctly → proves the conclusion → explains it naturally.**

That is the objective.