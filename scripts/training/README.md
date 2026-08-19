# Ask Rules local model — training workflow

How the models Ask Rules can use (`LocalAiModelCatalog.cs`, fetched on demand by
`LocalAiModelService` into `App_Data/Models/{modelId}/`) are built, and how to retrain one later —
e.g. after a rules sync picks up new keywords/cards, or to fix a behavior found in testing.

Base models: `Qwen/Qwen2.5-1.5B-Instruct` (the default/original) and `Qwen/Qwen3.5-2B` (a newer,
somewhat larger alternative — see "Training a different base model" below), each LoRA fine-tuned on
synthetic examples generated from the **real synced Riftbound rules corpus** (not hand-written),
then merged and quantized to GGUF (Q4_K_M) for `LLamaSharp`/llama.cpp.

**Keep this file, `generate_dataset.py`, and `LocalLlmExplanationProvider.cs` in sync.** The
dataset generator's evidence formatting (`build_evidence_text`/`build_user_message`, the
`PER_ITEM_CAP`/`TOTAL_BUDGET` constants, `SYSTEM_PROMPT`) is a deliberate line-for-line mirror of
`BuildUserMessage` in `LocalLlmExplanationProvider.cs`. If you change how that method builds a
prompt, update the matching constants/functions in `generate_dataset.py` in the same change —
fine-tuning against a prompt shape the model will never actually see at inference time teaches
habits that don't transfer, which is worse than not training on that behavior at all. This bit a
real training run directly: after `BuildUserMessage` switched from 220-char snippets to full rule
text with a character budget, the dataset generator still used the old format for a while, and
separately, an entire evidence shape (a card's own printed text, `CardText` authority) had no
dataset category at all — which was later traced as the direct cause of the model echoing its own
system prompt back as an "answer" for a card with no ban/errata history.

## 0. One-time environment setup

**Python version matters.** As of writing, PyTorch has no wheels for the very latest Python (3.14
locally) — use Python 3.12 specifically. A dedicated venv keeps this isolated from whatever Python
the rest of your machine uses:

```
py -3.12 -m venv scripts/training/.venv
scripts/training/.venv/Scripts/python.exe -m pip install --upgrade pip
scripts/training/.venv/Scripts/python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cu121
scripts/training/.venv/Scripts/python.exe -m pip install -r scripts/training/requirements.txt
```

Verify CUDA is actually visible before spending time on a training run that'll silently fall back
to (much slower) CPU:

```
scripts/training/.venv/Scripts/python.exe -c "import torch; print(torch.cuda.is_available())"
```

**llama.cpp toolchain**, for step 3 (GGUF conversion + quantization) — a prebuilt CPU release is
enough; quantization itself doesn't need a GPU:

```
git clone --depth 1 https://github.com/ggml-org/llama.cpp scripts/training/llama.cpp-src
gh release download <tag> -R ggml-org/llama.cpp -p "llama-*-bin-win-cpu-x64.zip" -O scripts/training/llama-cpp-bin.zip
# unzip llama-cpp-bin.zip into scripts/training/llama.cpp-bin/ — it contains llama-quantize.exe
```

(`<tag>` — use `gh release list -R ggml-org/llama.cpp -L 1` to find the current one.) None of
`.venv/`, `llama.cpp-src/`, or `llama.cpp-bin/` are committed — see `.gitignore`.

## 1. Generate the training dataset

Requires the app running locally with a synced Rules library (`POST /api/rules/sync`), since
categories 2/3/7 are partly **self-distilled** — real answers captured from the already-working RAG
pipeline, used as fine-tuning targets to make that same grounded behavior more reliable.

```
dotnet run --project src/RiftBoundTracker.App -- --headless
# in another shell, once it's up:
curl -X POST http://localhost:5080/api/rules/local-ai/configure -d '{"enabled":true}' -H "Content-Type: application/json"

scripts/training/.venv/Scripts/python.exe scripts/training/generate_dataset.py
```

**If you're testing changes to this script itself, don't point it at a real running install** —
it calls `/api/rules/local-ai/configure`, which flips a real setting. Point it at an isolated dev
instance on a different port instead:

```
Port=5199 HttpsPort=5643 dotnet run --project src/RiftBoundTracker.App -- --headless
# in another shell:
RIFTKEEP_API_PORT=5199 scripts/training/.venv/Scripts/python.exe scripts/training/generate_dataset.py
```

Writes `scripts/training/output/dataset.jsonl`. Categories, roughly 500 examples total against the
current rules/card corpus:

1. Direct rule-number lookups (templated — correct by construction)
2. Keyword "how does X work" questions (self-distilled)
3. Concept-based natural-language questions (self-distilled)
4. Errata questions (templated)
5. Legality questions, plus 5b. multi-format legality questions (templated)
6. Insufficient-evidence / off-topic refusals (templated) — **never remove this category**; without
   it, fine-tuning can erode the model's willingness to say "I don't know" instead of guessing.
7. Card ability questions — a card's own printed text as evidence (templated, not self-distilled;
   see the file's own docstring for why the answer template deliberately doesn't try to hand-parse
   and rewrite the card text into a bespoke sentence). Weighted toward the `"[Keyword] (reminder
   text)"` bracket pattern, since that's roughly 44% of the card catalog.

Read the script's own comments before changing the category mix further.

## 2. Train

```
scripts/training/.venv/Scripts/python.exe scripts/training/train.py
```

Saves a LoRA adapter to `scripts/training/output/lora-adapter/`. On an RTX 3050 (8GB VRAM) against
~500 examples / 3 epochs, expect roughly 10–20 minutes, mostly base-model download the first time
(cached under the default Hugging Face cache dir after that).

### Iterating (multiple training rounds)

If a round's output still has a gap when you test it (step 4), the fix is almost always improving
`generate_dataset.py`'s coverage for that gap — add or reweight a category, regenerate, retrain —
not just re-running training unchanged (a fixed dataset + fixed seed will just reproduce
approximately the same result). Save each round's adapter under a distinct name (e.g.
`lora-adapter-round2/`) before starting the next one so a regression is easy to compare against and
recover from. Stop when a round's test-question battery (step 4) shows no meaningful improvement
over the previous round, or when a change fixes one case but visibly regresses another — that's a
sign the dataset/prompt change needs to be more targeted, not that another blind round will help.
(A real example of the latter: a system-prompt-only tweak fixed one card's answer but made a
different card's answer worse, including fabricating a rule citation that doesn't exist — reverted
rather than shipped, and fixed properly instead by adding a dataset category, per the note at the
top of this file.)

## 3. Merge + convert to GGUF + quantize

```
scripts/training/.venv/Scripts/python.exe scripts/training/merge.py
scripts/training/.venv/Scripts/python.exe scripts/training/llama.cpp-src/convert_hf_to_gguf.py scripts/training/output/merged --outfile scripts/training/output/riftkeep-ask-rules-f16.gguf --outtype f16
scripts/training/llama.cpp-bin/llama-quantize.exe scripts/training/output/riftkeep-ask-rules-f16.gguf scripts/training/output/riftkeep-ask-rules-Q4_K_M.gguf Q4_K_M
```

## 4. Verify before shipping

Copy the new `.gguf` into `App_Data/Models/{modelId}/` for an isolated dev instance (never a real
install — see the port-isolation note in step 1), enable local AI, select that model, and re-ask a
fixed battery of test questions — comparing against the previous model's answers, not just "does it
not crash". At minimum: a rule-number lookup, a keyword question, a multi-fact card legality
question (a card banned in more than one format), an errata question, a card-ability question for a
card with no ban/errata (the `"[Keyword] (reminder text)"` case), and an off-topic question (must
still refuse).

## 5. Host and wire into the release

GGUFs are **not** committed to git (large binaries would bloat the repo's history forever). Each
model in `LocalAiModelCatalog.cs` has its own release tag it's hosted under:

```
gh release upload <ReleaseTag from the catalog entry> scripts/training/output/riftkeep-ask-rules-Q4_K_M.gguf --clobber
```

That's the whole release step — nothing in the app build needs to change. `LocalAiModelService`
fetches whatever `.gguf` asset is attached to a given model's tag straight into
`App_Data/Models/{modelId}/` (never the install directory, so it survives app self-updates), so a
new model version ships independently of app releases entirely — no `release.ps1` changes, no app
version bump required. Someone who already has a model downloaded needs to click that model's
download action again in Settings to pick up a newer version (there's no background polling for a
newer model — the status check is local-only, on purpose, so it doesn't need a network call just to
render the Rules page). Keep the filename ending in `.gguf`; it doesn't need to match exactly since
the service just picks up whatever `.gguf` file is in that model's subfolder.

## Adding a new model option

1. Add an entry to `LocalAiModelCatalog.Options` in `src/RiftBoundTracker.App/Services/Rules/Ask/LocalAiModelCatalog.cs`
   — an `Id` (used as the App_Data subfolder name — pick something stable, never reused for a
   different model later), `DisplayName`/`Description` for Settings, a dedicated `ReleaseTag`, and
   an approximate download size.
2. Run steps 1–4 above with `RIFTKEEP_BASE_MODEL=<the new base model's HF repo id>` set for both
   `train.py` and `merge.py` (must be the *same* value for both — the merge step loads the base
   model fresh and applies the adapter on top of it).
3. Confirm the target base model's architecture is actually supported by the LLamaSharp version
   this project has pinned (`RiftBoundTracker.App.csproj`) before investing time in training it —
   check that version's own release notes on https://github.com/SciSharp/LLamaSharp/releases (a
   newer LLamaSharp than what's pinned may be required for a very new model architecture).
4. Host it per step 5, using the new catalog entry's `ReleaseTag`.
