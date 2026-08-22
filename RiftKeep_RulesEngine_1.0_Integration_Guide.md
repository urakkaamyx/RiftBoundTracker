# RiftKeep Rules Engine 1.0 — Application Integration Guide

## Purpose

RiftKeep Rules Engine 1.0 should be integrated into the main RiftKeep / RiftBoundTracker application as a **local rules backend service**.

The main application should **not** duplicate, reimplement, or directly query the rules engine's internal rule logic, canonical JSON files, SQLite database, proof engine, authority overlays, or adjudication code.

Instead, the application should communicate with the Rules Engine exclusively through the stable **Product API v1**.

This preserves the deterministic rules, proof, authority, citation, errata, FAQ, update, and validation guarantees established through Milestones 1–19.

---

# 1. Recommended Architecture

```text
MAIN RIFTKEEP APPLICATION
────────────────────────────────
Collection Manager
Deck Builder
Tournament Decks
Card Recommendations
Rules UI
Settings
Other RiftKeep Features

              │
              │ HTTP /v1/*
              ▼

RIFTKEEP RULES ENGINE 1.0
────────────────────────────────
Definition Lookup
Question Interpretation
Scenario Model
Rule Compiler
Proof Engine
Card Interaction Engine
Core Rules
Tournament Rules
Cards
FAQ
Errata
Authority Overlays
Evidence / Citations
Source History
Update Lifecycle
Production Hardening
```

The Rules Engine is the authoritative source for all rules-related behavior.

---

# 2. Install the Rules Engine

Extract the certified Milestone 19 package into a permanent location.

Example:

```text
G:\Endo\Endo_Architecture_Package\Projects\RiftKeep\
    RulesEngine\
        riftkeep.py
        serve_api.py
        src\
        data\
        contracts\
        web\
        tests\
        ...
```

The engine requires:

```text
Python 3.11+
PyMuPDF >= 1.24
```

Example environment setup:

```bat
py -3.12 -m venv .venv

.venv\Scripts\activate

python -m pip install --upgrade pip
python -m pip install "PyMuPDF>=1.24"
```

---

# 3. Verify the Installation

Run:

```bat
python riftkeep.py self-check
```

Expected result:

```json
{
  "ok": true
}
```

The self-check verifies the Stable 1.0 runtime, including:

- release identity
- runtime authority integrity
- canonical artifact integrity
- SQLite integrity
- SQLite schema version
- Stable 1.0 distribution manifest
- Product API startup
- current rules authority completeness

Normal self-check operation does not require Internet access.

---

# 4. Start the Rules Engine

Run:

```bat
python riftkeep.py serve
```

Default address:

```text
http://127.0.0.1:8765
```

The engine provides both:

```text
RiftKeep Rules UI
Product API v1
```

from the same local service.

Opening this address in a browser:

```text
http://127.0.0.1:8765
```

loads the standalone RiftKeep Rules interface.

---

# 5. Product API v1

The main RiftKeep application should communicate with the engine using the stable Product API.

Base URL:

```text
http://127.0.0.1:8765
```

## Status

```http
GET /v1/status
```

Use this to determine whether the engine is healthy and ready.

The Stable 1.0 service reports:

```text
productVersion: 1.0.0
releaseLine: stable
Product API: v1
```

---

# 6. Ask Rules

Primary endpoint:

```http
POST /v1/ask
Content-Type: application/json
```

Example request:

```json
{
  "question": "Can I move a unit from one battlefield to another if it has Ganking?"
}
```

Flow:

```text
Player question
      │
      ▼
Main RiftKeep App
      │
      ▼
POST /v1/ask
      │
      ▼
RiftKeep Rules Engine
      │
      ├─ language interpretation
      ├─ scenario model
      ├─ deterministic rule execution
      ├─ proof engine
      ├─ authority verification
      └─ evidence selection
      │
      ▼
Verified ruling
      │
      ▼
Main RiftKeep UI
```

The main application must not determine or alter the ruling.

---

# 7. Search

Example:

```http
GET /v1/search?q=Ganking
```

Additional filtering:

```http
GET /v1/search?q=Ganking&kind=rule&limit=20&offset=0
```

Use search for:

- rule keywords
- definitions
- cards
- FAQ material
- relevant authority

---

# 8. Rule Details

Core Rules:

```http
GET /v1/rules/core/{ruleId}
```

Example:

```http
GET /v1/rules/core/810
```

Tournament Rules:

```http
GET /v1/rules/tournament/{ruleId}
```

The rule family must remain explicit where rule identifiers may overlap.

---

# 9. Card Details

Cards can be retrieved using a printing identity or exact supported card identity.

```http
GET /v1/cards/{printingId-or-exact-name}
```

The application should rely on the Product API for canonical card identity rather than reading the internal card corpus directly.

---

# 10. Evidence and Citations

```http
GET /v1/evidence/{evidenceId}
```

Use this endpoint when the interface needs to show:

- exact rules evidence
- authority provenance
- supporting citations
- why a ruling was reached

The backend owns evidence selection and exact authority quoting.

The frontend must not invent or reconstruct citations.

---

# 11. Sources

```http
GET /v1/sources
```

Use this for a Rules Sources / Authority screen.

Possible information includes:

- current Core Rules source
- current Tournament Rules source
- FAQ authority
- source versions
- effective authority state
- provenance

---

# 12. What Changed

Core Rules:

```http
GET /v1/changes?family=core
```

Tournament Rules:

```http
GET /v1/changes?family=tournament
```

These routes support a user-facing **What Changed** interface without requiring the main application to understand the rules version-history storage format.

---

# 13. Definition Lookup

Stable RiftKeep 1.0 includes deterministic Definition Lookup.

Questions such as:

```text
What does Deflect do?
What does Recall do?
What does Ganking mean?
```

can be routed through the Product API.

Definition results remain backend-authoritative and proof/citation-aware.

The frontend must not maintain a separate keyword-definition table.

---

# 14. C# Client Example

A C# application only needs an HTTP client to begin integrating the engine.

```csharp
using System.Net.Http.Json;

public sealed class RiftKeepRulesClient
{
    private readonly HttpClient _http;

    public RiftKeepRulesClient()
    {
        _http = new HttpClient
        {
            BaseAddress = new Uri("http://127.0.0.1:8765/")
        };
    }

    public async Task<string> AskAsync(string question)
    {
        using var response = await _http.PostAsJsonAsync(
            "v1/ask",
            new
            {
                question
            });

        response.EnsureSuccessStatusCode();

        return await response.Content.ReadAsStringAsync();
    }
}
```

This is only the minimum integration example.

The final application should deserialize Product API responses into typed C# models.

---

# 15. Recommended Application Service Layer

Create a dedicated client/service in the main application.

Example conceptual structure:

```text
Services/
    Rules/
        RiftKeepRulesClient.cs
        RiftKeepRulesProcessManager.cs
        Models/
            AskRequest.cs
            AskResponse.cs
            SearchResponse.cs
            RuleResponse.cs
            CardResponse.cs
            EvidenceResponse.cs
            SourceResponse.cs
            ChangesResponse.cs
```

This keeps the Product API boundary explicit.

---

# 16. Automatically Manage the Python Rules Service

End users should not need to manually open a terminal and run:

```bat
python riftkeep.py serve
```

The main RiftKeep application should manage the engine process.

Recommended startup flow:

```text
RiftKeep Application Starts
          │
          ▼
Check:
GET http://127.0.0.1:8765/v1/status
          │
     ┌────┴────┐
     │         │
 Running     Not Running
     │         │
     ▼         ▼
 Use It    Start Engine
               │
               ▼
RulesEngine\.venv\Scripts\python.exe
RulesEngine\riftkeep.py serve
               │
               ▼
Wait for /v1/status
               │
               ▼
Enable Rules Features
```

The user should experience this as one application.

---

# 17. Suggested Process Manager Responsibilities

A `RiftKeepRulesProcessManager` should handle:

- locate the Rules Engine installation
- locate the correct Python environment
- detect whether the service is already running
- start the service when necessary
- wait for `/v1/status`
- detect startup failures
- capture process exit state
- expose engine availability to the UI
- restart the service after successful rules updates
- stop a child process cleanly when appropriate

Do not silently launch multiple copies of the service.

---

# 18. Startup Health Check

The application should call:

```http
GET /v1/status
```

before enabling rules functionality.

Conceptually:

```text
Engine reachable?
    │
    ├─ No
    │   └─ Attempt startup
    │
    └─ Yes
        │
        ▼
Stable 1.0?
        │
        ▼
Authority complete?
        │
        ▼
Runtime snapshot healthy?
        │
        ▼
Enable Rules UI
```

The main application should not bypass a degraded or fail-closed state.

---

# 19. Runtime Snapshot Changes

RiftKeep Rules Engine intentionally does not silently hot-reload authority files into a running service.

If serving-critical files change after startup, the engine fails closed rather than mixing old in-memory data with new on-disk authority.

After a successful rules update:

```text
Update publishes
      │
      ▼
Old service detects runtime drift
      │
      ▼
Non-status rules calls fail closed
      │
      ▼
Main app restarts Rules Engine
      │
      ▼
New authority snapshot loaded
```

This is intentional production-hardening behavior.

---

# 20. Do Not Query SQLite Directly

The main application must not access:

```text
data/index/rules.sqlite
```

directly.

Do not build application features around:

```sql
SELECT ...
FROM docs_fts
```

or any other internal table.

The SQLite index is an internal implementation detail of the Rules Engine.

Always use:

```text
/v1/search
/v1/rules/*
/v1/cards/*
```

instead.

---

# 21. Do Not Read Canonical Rule JSON Directly

The main application should not directly read files such as:

```text
data/canonical/core_rules.json
data/canonical/tournament_rules.json
data/canonical/cards.json
data/canonical/rule_programs.json
data/canonical/compiled_rule_catalog.json
data/canonical/card_interaction_programs.json
```

These are internal engine artifacts.

The Product API is the stable integration contract.

---

# 22. Do Not Duplicate Adjudication Logic

Do not implement frontend logic such as:

```text
if card has Hidden ...
if unit has Ganking ...
if rule says can't ...
if replacement effect ...
if trigger happens ...
```

Rules logic belongs entirely inside the Rules Engine.

Frontend code should only:

```text
collect user input
send request
receive deterministic response
display response
display evidence
display citations
display clarification requests
```

---

# 23. LLM Boundary

The main application should not call an LLM and treat the response as a ruling.

The Stable engine already enforces the correct architecture:

```text
LLM Interpretation
        │
        ▼
Deterministic Scenario / Rules System
        │
        ▼
Proof Engine
        │
        ▼
Verified Ruling
        │
        ▼
LLM Explanation
```

The LLM cannot invent:

- rules
- card text
- evidence
- citations
- facts
- assumptions
- verdicts

The deterministic backend remains authoritative.

---

# 24. Suggested Rules UI Integration

The main RiftKeep application can expose these sections:

## Ask Rules

Uses:

```text
POST /v1/ask
```

## Search

Uses:

```text
GET /v1/search
```

## Rule Detail

Uses:

```text
GET /v1/rules/...
```

## Card Detail

Uses:

```text
GET /v1/cards/...
```

## Evidence

Uses:

```text
GET /v1/evidence/...
```

## Sources

Uses:

```text
GET /v1/sources
```

## What Changed

Uses:

```text
GET /v1/changes
```

---

# 25. Clarifications

If the deterministic engine cannot safely adjudicate because the question is ambiguous, the application should render the clarification returned by the engine.

The frontend must not guess the missing fact.

Example conceptual interaction:

```text
User:
"If my unit dies, can I remove the hidden card?"

Engine:
"I need to know who controls the battlefield after the unit dies."

User supplies answer
        │
        ▼
Follow-up request
        │
        ▼
Deterministic ruling
```

---

# 26. Rules Updates

The application should not manually replace files in the engine.

RiftKeep includes a controlled authority-update lifecycle.

Conceptually:

```text
New Official Source
      │
      ▼
Create Update Transaction
      │
      ▼
Parse / Stage
      │
      ▼
Diff
      │
      ▼
Review if Material
      │
      ▼
Isolated Rehearsal
      │
      ▼
19-Suite Release Gate
      │
      ▼
Publish
      │
      ▼
Post-Publish Validation
      │
      ├─ PASS → New Authority
      │
      └─ FAIL → Rollback
```

The application should restart the running Rules Engine after successful publication.

---

# 27. Stable 1.0 Release Gate

RiftKeep Rules Engine 1.0 was certified using 19 mandatory suites:

```text
Core/system                 164
Definition Lookup           120
Ruling regressions           99
Player language              42
Scenario language            43
Scenario Model               58
Rule Compiler                42
Proof Engine                 72
LLM interpretation           84
LLM explanation              80
Gold corpus                  34
Card interactions            74
Product API                 132
UI integration              148
Update/version               29
Update Automation            70
Production Hardening         74
M18 adversarial audit        48
Stable 1.0 acceptance       191
```

The frozen Gold corpus contains:

```text
1,846 cases
```

The Stable release also passed:

```text
Consolidated validation: PASS
Project audit: 0 critical
```

Two known non-blocking historical archive warnings remain regarding unavailable superseded historical source bodies. They do not affect current gameplay authority.

---

# 28. Stable Release Identity

The Stable release line is:

```text
RiftKeep Rules Engine 1.0.0
```

Stable Product API:

```text
Product API v1
```

Runtime database:

```text
SQLite schema v1
```

The Product API v1 compatibility contract should remain stable across compatible 1.x releases.

Breaking API changes should require a new API version rather than silently altering `/v1/*` behavior.

---

# 29. Recommended Distribution Layout

The final RiftKeep application can distribute the engine alongside the main application.

Example:

```text
RiftKeep/
│
├─ RiftKeep.exe
│
├─ App/
│
├─ Data/
│
│
└─ RulesEngine/
   │
   ├─ riftkeep.py
   ├─ serve_api.py
   ├─ src/
   ├─ data/
   ├─ contracts/
   ├─ web/
   ├─ RELEASE_NOTES_1.0.md
   ├─ KNOWN_LIMITATIONS_1.0.md
   │
   └─ .venv/
```

The exact packaging strategy can later change, but the Product API boundary should remain the same.

---

# 30. Future C# Conversion

The current Python Stable 1.0 engine should be treated as the **reference implementation and behavioral oracle** if the Rules Engine is later ported to C#.

Recommended conversion strategy:

```text
Python Stable 1.0
      │
      │ existing 19-suite oracle
      ▼
C# Implementation
      │
      ▼
Parity Test
      │
      ├─ same inputs
      ├─ same authority
      ├─ same scenario interpretation constraints
      ├─ same verdicts
      ├─ same proof obligations
      ├─ same evidence
      └─ same API behavior
```

Do not rewrite the architecture from memory.

Port subsystem-by-subsystem while keeping the Python Stable release available as the comparison oracle.

---

# 31. Recommended Integration Order

Integrate the main RiftKeep application in this order:

```text
1. Bundle RulesEngine/
2. Create RulesEngineProcessManager
3. Add automatic /v1/status detection
4. Automatically launch the engine when unavailable
5. Create typed RiftKeepRulesClient
6. Connect Ask Rules
7. Connect Definition Lookup
8. Connect Search
9. Connect Rule Detail
10. Connect Card Detail
11. Connect Evidence / Citations
12. Connect Sources
13. Connect What Changed
14. Add clarification UI
15. Add degraded/unavailable state UI
16. Restart engine after successful authority updates
17. Add application-level integration tests
18. Package the Rules Engine with RiftKeep
```

---

# 32. Core Integration Rule

The most important architectural rule is:

```text
THE MAIN APPLICATION DOES NOT KNOW HOW RIFTBOUND RULES WORK.
```

It knows only how to communicate with:

```text
RiftKeep Product API v1
```

The Rules Engine alone owns:

```text
rules
definitions
cards
FAQ
errata
authority
scenario modeling
adjudication
proof
evidence
citations
updates
```

This separation is what allows the Stable 1.0 Rules Engine to remain independently testable, replaceable, updateable, and eventually portable to C# without destabilizing the rest of RiftKeep.
