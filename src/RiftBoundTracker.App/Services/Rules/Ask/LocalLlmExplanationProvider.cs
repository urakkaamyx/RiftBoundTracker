using System.Text;
using LLama;
using LLama.Common;
using LLama.Sampling;
using LLama.Transformers;

namespace RiftBoundTracker.App.Services.Rules;

/// <summary>
/// Fully local plain-language explanation layer for Ask Rules — a small instruct model (GGUF,
/// bundled with the app; see Models/ and scripts/release.ps1) run entirely in-process via
/// llama.cpp bindings. No network call, no API key, no third party: the question and the rules
/// evidence this app already retrieved locally never leave the machine. Registered as a singleton
/// so the model loads once (a couple of seconds) and stays resident for the process lifetime
/// rather than reloading per question.
///
/// A missing chat template was the actual cause of a hallucinated/rambling first attempt during
/// development (verified against the real model directly) — PromptTemplateTransformer applies the
/// GGUF's own embedded template (ChatML for Qwen), which is what actually makes the model follow
/// "answer only from the supplied evidence" instead of free-associating from the prompt text.
/// </summary>
public sealed class LocalLlmExplanationProvider(
    RulesLocalAiSettingsService settings, LocalAiModelService modelService, ILogger<LocalLlmExplanationProvider> logger)
    : IRulesExplanationProvider, IDisposable
{
    private const string SystemPrompt = """
        You are a rules-reference assistant for the Riftbound trading card game. Answer only from
        the official rules evidence supplied below. If the evidence does not clearly establish the
        answer, say so plainly instead of guessing. Never invent a ruling that isn't supported by
        the evidence. Prefer current Core Rules over Tournament Rules, errata, or historical
        material when they overlap. Clearly distinguish what a rule directly says from any
        interpretation you're making. Keep the answer concise — a few sentences, not an essay.
        A card's own printed text is valid evidence of what that card does — if it's supplied below,
        describe the card's effect directly instead of calling the evidence insufficient.
        Rules text is often a conditional built on negations ("applies if X is not Y and Z does not
        W") — before answering, work out literally which side of each "not" the actual situation in
        the question falls on. Getting a negation backwards produces the opposite of the correct
        ruling, which is worse than not answering at all.
        """;

    // Adjudication decides the ruling; it never writes player-facing prose. Citing evidence only by
    // its E<n> id (never a typed rule number) is the hard boundary RulesAdjudicationValidator
    // enforces against a hallucinated citation ever reaching the player — the model can't invent a
    // rule number here even if it wanted to, since only a known E-id passes validation. Few-shot
    // examples are baked in rather than a separate call, since the fine-tuned model has never seen
    // this structured shape during training and instructions alone are unreliable for a 1.5B model.
    private const string AdjudicationSystemPrompt = """
        You are a rules adjudicator for the Riftbound trading card game. Your ONLY job is to decide
        the correct ruling from the evidence supplied below — you are not writing the player-facing
        answer here, only the internal ruling.

        Rules:
        - Cite evidence only by its E<number> id (e.g. E1, E3). Never type a rule number and never
          invent a citation that isn't in the supplied evidence.
        - Use only the supplied evidence. Never use outside knowledge of other card games, and never
          invent a rule or mechanic that isn't in the evidence.
        - If the question asks about more than one thing, treat each as its own issue.
        - Evidence is often a conditional built on negations ("applies if X is not Y") — work out
          literally which side of each "not" the actual situation falls on before deciding ANSWER.
        - If the supplied evidence does not establish the answer, ANSWER is "Insufficient" — say so,
          do not guess.
        - You will usually be given far more evidence than any one issue needs. Most of it is
          irrelevant to any given issue — that is normal and expected. REASON cites only the 1-3
          ids that actually decide this issue. Never work through the evidence id by id, never
          summarize what every id says, and never repeat the same sentence structure for multiple
          ids — that is a mistake, not thoroughness.

        Output exactly this shape, one block per issue, nothing else — no other text:
        ISSUE: <restate the sub-question in your own words>
        ANSWER: Yes|No|Insufficient
        REASON: <ONE sentence, citing only the 1-3 E-ids that decide this issue — not a tour of the evidence>
        EVIDENCE: <comma-separated E ids used for this issue, e.g. E1, E3>
        MISSING: <only include this line if ANSWER is Insufficient>
        ---
        (repeat the ISSUE block above for each additional issue, each followed by its own ---)
        VERDICT: <one line: Yes / No / Mixed / Insufficient evidence>

        Example — simple question:
        ISSUE: Does Exhaust let a card be played from the trash?
        ANSWER: No
        REASON: E1 defines Exhaust as a cost-paying keyword and says nothing about the trash zone.
        EVIDENCE: E1
        ---
        VERDICT: No

        Example — two issues, one is a negation:
        ISSUE: Can a unit be played to a battlefield its controller already controls?
        ANSWER: Yes
        REASON: E1 lists a controlled battlefield as a valid location a unit can enter.
        EVIDENCE: E1
        ---
        ISSUE: Does that make the battlefield Contested?
        ANSWER: No
        REASON: E2 only applies Contested when the arriving unit's controller does NOT already
        control the battlefield; since they already do, that condition is false.
        EVIDENCE: E2
        ---
        VERDICT: Mixed

        Example — insufficient evidence:
        ISSUE: Can a player sacrifice a Rune to draw a card?
        ANSWER: Insufficient
        REASON: The supplied evidence describes Runes only as a payment cost; nothing supplied
        mentions sacrificing a Rune or a resulting draw effect.
        EVIDENCE: E1
        MISSING: A rule or card ability that grants a draw effect from sacrificing a Rune.
        ---
        VERDICT: Insufficient evidence

        The three examples above are for OUTPUT FORMAT ONLY. Their questions, evidence ids, and
        answers are not real and do not apply here. You will now be given a real question and a
        real, numbered evidence list in the user turn — adjudicate ONLY that question, using ONLY
        that evidence. Do not reuse or repeat any example's question or reasoning.
        """;

    // Explanation-of-an-already-decided-ruling — the counterpart to SystemPrompt above, but for the
    // second stage of the adjudicate -> validate -> explain pipeline. Deliberately does NOT say
    // "keep the answer concise — a few sentences, not an essay" (SystemPrompt's own instruction,
    // left as-is there since ExplainAsync's single-pass path still wants that): a validated,
    // possibly-multi-issue ruling needs room for a direct answer, an explanation, and a quotation
    // per issue, not a fixed brevity ceiling.
    private const string AdjudicatedExplanationSystemPrompt = """
        You are a rules-reference assistant for the Riftbound trading card game, writing the
        player-facing answer. THE RULING BELOW HAS ALREADY BEEN DETERMINED — do not re-adjudicate
        it, do not change any Yes/No/Insufficient answer given, and do not reach a different
        conclusion than the one supplied. Your only job is to communicate the already-decided ruling
        clearly and naturally, using the supplied rule text to show why it's correct.

        For each issue: give the direct answer first, explain briefly in plain language, quote the
        rule text that establishes it, and — for anything conditional or negated — explicitly
        connect the rule's condition to the player's actual situation (state what the condition
        requires, state what's actually true here, state the result). If there is more than one
        issue, address them as clearly separated points and end with a short conclusion; for a
        single issue, do not force a numbered list or an artificial conclusion section.

        If an issue's answer is "Insufficient", say plainly that the supplied evidence doesn't
        establish an answer — never guess or fill the gap with outside knowledge.

        Write flowing plain-language prose only. The ruling below is internal bookkeeping for you to
        read, not a template to echo — never repeat its "Issue:"/"Answer:"/"Reason:"/"Supporting rule
        text:"/"Overall verdict:" labels or structure in your response, and never reply with anything
        resembling "thank you for providing..." or an offer of further assistance. A player asked a
        rules question and is waiting for the answer, not a receipt.
        """;

    private readonly SemaphoreSlim _gate = new(1, 1);
    private ModelParams? _modelParams;
    private LLamaWeights? _weights;
    private string? _loadedModelPath;
    private DateTime _loadedModelWriteTimeUtc;
    // Keyed to the path that failed, not a bare bool — switching to a DIFFERENT catalog model
    // after one failed to load must not keep reporting unconfigured for a model that was never
    // actually tried.
    private string? _failedModelPath;

    public bool IsConfigured => settings.IsEnabled() && FindModelPath() is { } path && path != _failedModelPath;

    public async Task<RulesGeneratedAnswer> ExplainAsync(RulesExplanationContext context, CancellationToken ct = default)
    {
        if (!settings.IsEnabled())
            return new RulesGeneratedAnswer(null, false, "Local AI explanations are turned off.");

        var modelPath = FindModelPath();
        if (modelPath is null)
            return new RulesGeneratedAnswer(null, false, "The selected local model hasn't been downloaded yet.");

        await _gate.WaitAsync(ct);
        try
        {
            if (!EnsureWeightsLoaded(modelPath))
                return new RulesGeneratedAnswer(null, false, "Could not load the local model.");

            // A fresh context per question — only the model weights (the big, slow-to-load part)
            // stay resident. Reusing one context's KV cache across questions caused a real
            // 'llama_decode failed: InvalidInputBatch' error once the cache from an earlier
            // question left it without room for the next one; a new context has no such history.
            using var requestContext = _weights!.CreateContext(_modelParams!);
            var executor = new InteractiveExecutor(requestContext);
            var chatHistory = new ChatHistory();
            chatHistory.AddMessage(AuthorRole.System, SystemPrompt);
            var session = new ChatSession(executor, chatHistory)
                .WithHistoryTransform(new PromptTemplateTransformer(_weights!, withAssistant: true));

            var inferenceParams = new InferenceParams
            {
                MaxTokens = 350,
                AntiPrompts = ["User:", "Question:", "<|im_end|>"],
                // RepeatPenalty defaults to 1 (a no-op multiplier) even though PenaltyCount defaults
                // to a real 64-token window — confirmed directly by probing DefaultSamplingPipeline's
                // own defaults, not assumed. Leaving it unset let this model loop into the exact
                // degenerate-repetition failure this fix targets: real testing caught it verbatim
                // repeating "Rule 465.2.c... Rule 465.2.c.2... Rule 465.2.c.3..." until MaxTokens cut
                // it off, producing a wrong, unusable answer even though retrieval had the right
                // evidence. 1.1 matches llama.cpp's own CLI default — enough to break the loop
                // without over-constraining legitimate short repeated terms (e.g. "Rule 190.3.a").
                SamplingPipeline = new DefaultSamplingPipeline { Temperature = 0.2f, RepeatPenalty = 1.1f },
                // A defensive backstop, not the primary defense — BuildUserMessage's own evidence
                // budget is what's supposed to keep prompts under the context size. This just
                // means a case that budget didn't anticipate degrades to a truncated answer
                // instead of a hard ContextOverflowException and no answer at all (a real failure
                // mode hit directly during testing: a single Patch Notes article indexed as one
                // whole-section blob ran to 27,000+ characters as one piece of "evidence").
                OverflowStrategy = LLama.Common.ContextOverflowStrategy.TruncateAndReprefill,
            };

            var output = new StringBuilder();
            await foreach (var token in session.ChatAsync(new ChatHistory.Message(AuthorRole.User, BuildUserMessage(context)), inferenceParams)
                .WithCancellation(ct))
                output.Append(token);

            var answer = StripTrailingAntiPrompt(StripLeadingThinkBlock(output.ToString()), inferenceParams.AntiPrompts);
            return answer.Length == 0
                ? new RulesGeneratedAnswer(null, false, "The local model returned an empty response.")
                : new RulesGeneratedAnswer(answer, true, null);
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Local AI explanation failed");
            return new RulesGeneratedAnswer(null, false, ex.Message);
        }
        finally
        {
            _gate.Release();
        }
    }

    // Deliberately does not share inference-running code with ExplainAsync above — ExplainAsync is
    // the fallback path RulesAnswerService reaches for when adjudication fails validation, and it
    // needs to stay exactly as it already is (proven, unmodified) rather than risk a subtle change
    // from being refactored into a shared helper alongside these two newer methods.
    public async Task<RulesAdjudicationOutput> AdjudicateAsync(RulesAdjudicationContext context, CancellationToken ct = default)
    {
        if (!settings.IsEnabled())
            return new RulesAdjudicationOutput(null, false, "Local AI explanations are turned off.");

        var modelPath = FindModelPath();
        if (modelPath is null)
            return new RulesAdjudicationOutput(null, false, "The selected local model hasn't been downloaded yet.");

        await _gate.WaitAsync(ct);
        try
        {
            if (!EnsureWeightsLoaded(modelPath))
                return new RulesAdjudicationOutput(null, false, "Could not load the local model.");

            using var requestContext = _weights!.CreateContext(_modelParams!);
            var executor = new InteractiveExecutor(requestContext);
            var chatHistory = new ChatHistory();
            chatHistory.AddMessage(AuthorRole.System, AdjudicationSystemPrompt);
            var session = new ChatSession(executor, chatHistory)
                .WithHistoryTransform(new PromptTemplateTransformer(_weights!, withAssistant: true));

            var inferenceParams = new InferenceParams
            {
                // Adjudication output is compact structured lines, not prose — a few issues' worth
                // of ISSUE/ANSWER/REASON/EVIDENCE blocks fits comfortably well under 500 tokens.
                MaxTokens = 500,
                AntiPrompts = ["User:", "Question:", "<|im_end|>"],
                // See ExplainAsync's identical fix above for why RepeatPenalty must be set explicitly.
                // This is where it was caught in the first place: given ~16 E-ids, the model would
                // devolve the REASON field into "E1 states that... E2 states that... E3 states
                // that..." straight through every id instead of the one sentence the prompt asks for,
                // never reaching EVIDENCE/VERDICT — a guaranteed validation failure every time, not an
                // occasional one, confirmed across 6 of 7 real test questions before this fix.
                //
                // Grammar: real testing showed the dominant validation failure by far wasn't a wrong
                // ruling, it was output that never reached a parseable ISSUE/VERDICT shape at all —
                // instructions alone weren't reliable enough for this 1.5B model on a task it has no
                // fine-tuning exposure to. A GBNF grammar makes the invalid shape unreachable rather
                // than merely discouraged: the sampler can only choose among tokens that keep the
                // output grammatically valid, so it structurally cannot fail to reach VERDICT, and
                // cannot cite an EvidenceId outside this question's real evidence set (BuildAdjudication
                // Grammar enumerates only the ids actually present). This can't fix a wrong or
                // off-topic RULING — RulesAdjudicationValidator's IsGroundedInQuestion check still
                // catches that — but it removes the format-following failures that dominated testing
                // before this, which is what made adjudication validate on only ~1 in 14 real attempts.
                SamplingPipeline = new DefaultSamplingPipeline
                {
                    Temperature = 0.1f,
                    RepeatPenalty = 1.1f,
                    Grammar = new Grammar(BuildAdjudicationGrammar(context.Evidence), "root"),
                },
                OverflowStrategy = LLama.Common.ContextOverflowStrategy.TruncateAndReprefill,
            };

            var output = new StringBuilder();
            await foreach (var token in session.ChatAsync(new ChatHistory.Message(AuthorRole.User, BuildAdjudicationUserMessage(context)), inferenceParams)
                .WithCancellation(ct))
                output.Append(token);

            var raw = StripTrailingAntiPrompt(StripLeadingThinkBlock(output.ToString()), inferenceParams.AntiPrompts);
            return raw.Length == 0
                ? new RulesAdjudicationOutput(null, false, "The local model returned an empty response.")
                : new RulesAdjudicationOutput(raw, true, null);
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Local AI adjudication failed");
            return new RulesAdjudicationOutput(null, false, ex.Message);
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task<RulesGeneratedAnswer> ExplainAdjudicationAsync(RulesAdjudicatedExplanationContext context, CancellationToken ct = default)
    {
        if (!settings.IsEnabled())
            return new RulesGeneratedAnswer(null, false, "Local AI explanations are turned off.");

        var modelPath = FindModelPath();
        if (modelPath is null)
            return new RulesGeneratedAnswer(null, false, "The selected local model hasn't been downloaded yet.");

        await _gate.WaitAsync(ct);
        try
        {
            if (!EnsureWeightsLoaded(modelPath))
                return new RulesGeneratedAnswer(null, false, "Could not load the local model.");

            using var requestContext = _weights!.CreateContext(_modelParams!);
            var executor = new InteractiveExecutor(requestContext);
            var chatHistory = new ChatHistory();
            chatHistory.AddMessage(AuthorRole.System, AdjudicatedExplanationSystemPrompt);
            var session = new ChatSession(executor, chatHistory)
                .WithHistoryTransform(new PromptTemplateTransformer(_weights!, withAssistant: true));

            var inferenceParams = new InferenceParams
            {
                // 350 -> ~750: doc's target style (direct answer + explanation + quotation +
                // conditional walk-through per issue) genuinely needs more room than a "few
                // sentences" summary did. ContextSize=6144 already has headroom for this — the
                // explanation-stage prompt only carries evidence for the ids actually cited, not the
                // full evidence set adjudication saw.
                MaxTokens = 750,
                AntiPrompts = ["User:", "Question:", "<|im_end|>"],
                // See ExplainAsync's identical fix above. This call site produced the most severe
                // failure seen in testing: given a validated single-sentence ruling to explain, it
                // looped "A unit's Standard Move exhausts the unit as a cost." verbatim for the full
                // 750-token budget instead of stopping — an unmistakable degenerate-repetition loop,
                // not a borderline case.
                SamplingPipeline = new DefaultSamplingPipeline { Temperature = 0.2f, RepeatPenalty = 1.1f },
                OverflowStrategy = LLama.Common.ContextOverflowStrategy.TruncateAndReprefill,
            };

            var output = new StringBuilder();
            await foreach (var token in session.ChatAsync(new ChatHistory.Message(AuthorRole.User, BuildAdjudicatedExplanationUserMessage(context)), inferenceParams)
                .WithCancellation(ct))
                output.Append(token);

            var answer = StripTrailingAntiPrompt(StripLeadingThinkBlock(output.ToString()), inferenceParams.AntiPrompts);
            return answer.Length == 0
                ? new RulesGeneratedAnswer(null, false, "The local model returned an empty response.")
                : new RulesGeneratedAnswer(answer, true, null);
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Local AI explanation-of-adjudication failed");
            return new RulesGeneratedAnswer(null, false, ex.Message);
        }
        finally
        {
            _gate.Release();
        }
    }

    private bool EnsureWeightsLoaded(string modelPath)
    {
        var writeTimeUtc = File.GetLastWriteTimeUtc(modelPath);
        if (_weights is not null && _loadedModelPath == modelPath && _loadedModelWriteTimeUtc == writeTimeUtc) return true;
        // Either nothing loaded yet, the user switched which catalog model is selected
        // (RulesLocalAiSettingsService.SelectedModelId), or re-downloaded the same model to pick up
        // an improved version — the write-time check catches that last case even though the path on
        // disk is unchanged. Swap the resident weights instead of requiring an app restart.
        if (_weights is not null)
        {
            _weights.Dispose();
            _weights = null;
        }
        try
        {
            // 6144, not 4096 — raised again alongside BuildUserMessage's evidence budget (900/5500
            // -> 1400/9000 chars): a real question (Tank's interaction with spell targeting) needed
            // 11 rules to answer properly, and 5500 chars wasn't enough room to fit them all even
            // though retrieval had already found the right ones — evidence was silently dropped by
            // the budget loop, not by retrieval. The bigger context window is what makes the bigger
            // budget actually usable instead of just hitting a llama_decode overflow instead.
            _modelParams = new ModelParams(modelPath) { ContextSize = 6144, GpuLayerCount = 0 };
            _weights = LLamaWeights.LoadFromFile(_modelParams);
            _loadedModelPath = modelPath;
            _loadedModelWriteTimeUtc = writeTimeUtc;
            _failedModelPath = null;
            return true;
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Failed to load local AI model from {Path}", modelPath);
            _failedModelPath = modelPath;
            return false;
        }
    }

    // Qwen3's chat template pre-fills the assistant turn with a "<think>\n\n</think>\n\n" block
    // whenever thinking mode isn't explicitly enabled (confirmed directly in the GGUF's own
    // embedded template) — the model then continues generating its real answer after that, but
    // the literal tag text lands in the output stream same as any other token, so it leaked
    // straight into every answer during testing until this was added. Qwen2.5 has no such
    // template branch, so this is a no-op for it.
    private static string StripLeadingThinkBlock(string text)
    {
        var trimmed = text.TrimStart();
        if (!trimmed.StartsWith("<think>", StringComparison.Ordinal)) return text;
        var closeIndex = trimmed.IndexOf("</think>", StringComparison.Ordinal);
        if (closeIndex >= 0) return trimmed[(closeIndex + "</think>".Length)..].TrimStart();
        // Observed directly: the template's usual "<think>\n\n</think>\n\n" pre-fill sometimes
        // comes back with no closing tag at all before the real answer starts — generation just
        // continues past the empty think block without ever emitting "</think>". Rather than guess
        // where real content begins (there's nothing to reliably anchor on), just drop the literal
        // opening tag itself and keep everything after it.
        return trimmed["<think>".Length..].TrimStart();
    }

    // Anti-prompts stop generation once matched, but the matched text itself can still land in
    // the output stream before the stop takes effect (observed directly: "User:" trailing a real
    // answer during testing) — strip any of them (and anything after) off the end.
    private static string StripTrailingAntiPrompt(string text, IEnumerable<string> antiPrompts)
    {
        var trimmed = text;
        foreach (var antiPrompt in antiPrompts)
        {
            var index = trimmed.IndexOf(antiPrompt, StringComparison.Ordinal);
            if (index >= 0) trimmed = trimmed[..index];
        }
        return trimmed.Trim();
    }

    private static string Cap(string text, int maxChars) =>
        text.Length > maxChars ? text[..maxChars] + "…" : text;

    private static string BuildUserMessage(RulesExplanationContext context)
    {
        // Card evidence is deliberately formatted with the exact same "[Title] (Authority) Title\nText"
        // shape as regular rule evidence below (matching what the training data used, see
        // generate_dataset.py's errata/legality categories) — a differently-shaped evidence block
        // the model never saw during fine-tuning caused it to contradict its own supplied evidence
        // in testing, even though the underlying fact was correct.
        //
        // FullText, not Snippet — Snippet is a 220-char UI preview (RulesSearchService.ToHitAsync),
        // truncated for ~11.5% of rules in the corpus. A rule cut off mid-sentence there was
        // starving the model of evidence it needed to answer correctly even though the retrieval
        // step had found the right rule.
        //
        // That said, FullText is unbounded, and at least one real entry blows past it dramatically:
        // a Patch Notes article is indexed as one whole-section blob (ArticleSectionParser) and can
        // run to tens of thousands of characters — one such entry alone overflowed the model's
        // context window outright during testing, silently losing the answer entirely. PerItemCap
        // keeps any single item from doing that; TotalBudget keeps several merely-long items from
        // adding up to the same problem. Both are generous relative to the old 220-char snippet —
        // this only ever bites entries that were already far outside the normal range for one rule.
        const int perItemCap = 1400;
        const int totalBudget = 9000;
        var used = 0;
        var evidenceParts = new List<string>();
        // CardNotes FIRST, not last — a question about a specific card (its own text, legality, or
        // errata) is directly on-topic for that card no matter how much general rule evidence also
        // matched, so it must never lose the budget race to it. Before this fix, rule evidence (up
        // to 12 items, each up to perItemCap) filled the shared totalBudget first and the loop's
        // own "if (used >= totalBudget) break" could exhaust the budget before ever reaching a
        // card's own evidence, silently dropping it from the prompt entirely — the model would
        // then have no idea the card evidence even existed, however much noise it were.
        foreach (var part in context.CardNotes.Select(c => $"[{c.CardName}] ({c.Authority}) {c.CardName}\n{Cap(c.Note, perItemCap)}")
            .Concat(context.Evidence.Select(e =>
                $"[{(e.Hit.RuleNumber is not null ? $"Rule {e.Hit.RuleNumber}" : e.Hit.Title)}] " +
                $"({e.Hit.Document.Authority}{(e.Hit.Document.Current ? "" : ", historical")}) {e.Hit.Title}\n{Cap(e.Hit.FullText, perItemCap)}")))
        {
            if (used >= totalBudget) break;
            var remaining = totalBudget - used;
            var trimmed = part.Length > remaining ? Cap(part, remaining) : part;
            evidenceParts.Add(trimmed);
            used += trimmed.Length;
        }
        var evidenceText = string.Join("\n\n", evidenceParts);

        // Previously only the card's name reached the model, never its printed text — it could
        // name the card but had nothing to reason from when the question was actually about what
        // the card itself does (e.g. "does this trigger Fury?" needs the card's own text, not just
        // which rules mention Fury generically).
        var cardText = context.CardContext.Count > 0
            ? "\n\nThe question is specifically about this card:\n" + string.Join("\n\n", context.CardContext.Select(c =>
                $"[{c.Name}]" + (string.IsNullOrWhiteSpace(c.Text) ? "" : $"\n{c.Text}")))
            : "";

        return $"Question: {context.Question}{cardText}\n\nRules evidence:\n{evidenceText}";
    }

    // Forces the adjudicator's output into the exact shape RulesAdjudicationValidator expects —
    // structurally, not just by instruction. Only called with a non-empty context.Evidence (Rules
    // AnswerService gates AdjudicateAsync on having at least one evidence item), so the eid
    // alternation is never empty. EvidenceRef.Id values are always "E<n>" from EvidenceIdMapper, so
    // embedding them as literal GBNF string alternatives (not user input) is safe.
    private static string BuildAdjudicationGrammar(IReadOnlyList<EvidenceRef> evidence)
    {
        var eidAlternatives = string.Join(" | ", evidence.Select(e => $"\"{e.Id}\""));
        return $$"""
            root ::= issue+ verdict
            issue ::= "ISSUE:" " " freetext "\n" "ANSWER:" " " answer "\n" "REASON:" " " freetext "\n" "EVIDENCE:" " " eidlist "\n" missing? "---" "\n"
            answer ::= "Yes" | "No" | "Insufficient"
            missing ::= "MISSING:" " " freetext "\n"
            verdict ::= "VERDICT:" " " verdictvalue "\n"?
            verdictvalue ::= "Yes" | "No" | "Mixed" | "Insufficient evidence"
            eidlist ::= eid ("," " "? eid)*
            eid ::= {{eidAlternatives}}
            freetext ::= [^\n]+
            """;
    }

    // Same perItemCap/totalBudget as BuildUserMessage — adjudication needs the same full evidence
    // text to actually reason from, so it faces the same context pressure the single-pass path did.
    private static string BuildAdjudicationUserMessage(RulesAdjudicationContext context)
    {
        const int perItemCap = 1400;
        const int totalBudget = 9000;
        var used = 0;
        var parts = new List<string>();
        foreach (var e in context.Evidence)
        {
            var part = $"{e.Id} [{e.Label}] ({e.Authority}{(e.Current ? "" : ", historical")})\n{Cap(e.FullText, perItemCap)}";
            if (used >= totalBudget) break;
            var remaining = totalBudget - used;
            var trimmed = part.Length > remaining ? Cap(part, remaining) : part;
            parts.Add(trimmed);
            used += trimmed.Length;
        }
        var evidenceText = string.Join("\n\n", parts);

        var cardText = context.CardContext.Count > 0
            ? "\n\nThe question is specifically about this card:\n" + string.Join("\n\n", context.CardContext.Select(c =>
                $"[{c.Name}]" + (string.IsNullOrWhiteSpace(c.Text) ? "" : $"\n{c.Text}")))
            : "";

        var correctionText = string.IsNullOrWhiteSpace(context.CorrectionNote)
            ? ""
            : $"\n\nYour previous attempt was rejected: {context.CorrectionNote} Follow the exact output format and cite only the E-ids listed above.";

        // The question is stated again after the (up to 9000-char) evidence block, not just before
        // it — a real failure mode in testing was the model drifting onto a blended/hallucinated
        // question after reading through a long evidence list, sharing little or no content with the
        // real one. Restating it immediately before generation starts (a "lost in the middle"
        // mitigation — models attend most reliably to the start and end of a long context) makes it
        // the last thing the model reads before it has to decide what ISSUE to write.
        return $"Adjudicate this real question — it is not one of the system prompt's examples:\n" +
               $"Question: {context.Question}{cardText}\n\nEvidence:\n{evidenceText}{correctionText}" +
               $"\n\nReminder — the real question you must adjudicate is: {context.Question}";
    }

    // Only the EvidenceRefs the adjudicator actually cited are included here — the explanation
    // stage doesn't need the full evidence set adjudication saw, just enough to quote and connect
    // to the already-decided answer, which keeps this prompt considerably smaller.
    private static string BuildAdjudicatedExplanationUserMessage(RulesAdjudicatedExplanationContext context)
    {
        var citedIds = context.Adjudication.Issues.SelectMany(i => i.EvidenceIds).ToHashSet();
        var evidenceById = context.Evidence.Where(e => citedIds.Contains(e.Id)).ToDictionary(e => e.Id);

        var issueBlocks = context.Adjudication.Issues.Select(issue =>
        {
            var quotes = issue.EvidenceIds
                .Where(evidenceById.ContainsKey)
                .Select(id => evidenceById[id])
                .Select(e => $"[{e.Label}] ({e.Authority}{(e.Current ? "" : ", historical")})\n{e.FullText}");
            return $"Issue: {issue.Question}\nAnswer: {issue.Answer}\nReason: {issue.Reason}\n" +
                   $"Supporting rule text:\n{string.Join("\n\n", quotes)}";
        });

        var cardText = context.CardContext.Count > 0
            ? "\n\nThe question is specifically about this card:\n" + string.Join("\n\n", context.CardContext.Select(c =>
                $"[{c.Name}]" + (string.IsNullOrWhiteSpace(c.Text) ? "" : $"\n{c.Text}")))
            : "";

        return $"Question: {context.Question}{cardText}\n\n" +
               $"Ruling (already determined — explain it, do not change it):\n" +
               $"{string.Join("\n\n---\n\n", issueBlocks)}\n\nOverall verdict: {context.Adjudication.OverallVerdict}";
    }

    public string? FindModelPath() => modelService.FindModelPath(settings.GetSelectedModelId());

    public void Dispose()
    {
        _weights?.Dispose();
        _gate.Dispose();
    }
}
