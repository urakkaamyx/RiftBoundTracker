# Ask Rules local model — training workflow

How the model bundled at `src/RiftBoundTracker.App/Models/*.gguf` (used by
`LocalLlmExplanationProvider`) was built, and how to retrain it later — e.g. after a rules sync
picks up new keywords/cards, or to fix a behavior found in testing.

Base model: `Qwen/Qwen2.5-1.5B-Instruct`, LoRA fine-tuned on synthetic examples generated from the
**real synced Riftbound rules corpus** (not hand-written), then merged and quantized to GGUF
(Q4_K_M) for `LLamaSharp`/llama.cpp.

## 1. Generate the training dataset

Requires the app running locally with a synced Rules library (`POST /api/rules/sync`), since two
categories are *self-distilled* — real answers captured from the already-working RAG pipeline,
used as fine-tuning targets to make that same grounded behavior more reliable.

```
dotnet run --project src/RiftBoundTracker.App -- --headless
# in another shell, once it's up:
curl -X POST http://localhost:5080/api/rules/local-ai/configure -d '{"enabled":true}' -H "Content-Type: application/json"

pip install -r scripts/training/requirements.txt
python scripts/training/generate_dataset.py
```

Writes `scripts/training/output/dataset.jsonl`. Read the script's own comments before changing the
category mix — in particular, never remove the "insufficient evidence" refusal examples (category
6) or fine-tuning can erode the model's willingness to say "I don't know" instead of guessing.

## 2. Train

Needs a CUDA GPU (~8GB VRAM is enough for this model size at this LoRA rank).

```
python scripts/training/train.py
```

Saves a LoRA adapter to `scripts/training/output/lora-adapter/`.

## 3. Merge + convert to GGUF + quantize

```
python scripts/training/merge.py
```

Then convert with llama.cpp's own conversion script (not vendored here — clone or download it
from https://github.com/ggml-org/llama.cpp, matching the release used for `llama-quantize`):

```
python convert_hf_to_gguf.py scripts/training/output/merged --outfile scripts/training/output/riftkeep-ask-rules-f16.gguf --outtype f16
llama-quantize.exe scripts/training/output/riftkeep-ask-rules-f16.gguf scripts/training/output/riftkeep-ask-rules-Q4_K_M.gguf Q4_K_M
```

## 4. Verify before shipping

Copy the new `.gguf` into `src/RiftBoundTracker.App/Models/` (replacing the old one), run the app,
enable local AI, and re-ask the same test questions used during development — in particular:
a rule-number lookup, a keyword question, a multi-fact card legality question (a card banned in
more than one format), an errata question, and an off-topic question (must still refuse). Compare
against the previous model's answers, not just "does it not crash."

## 5. Host and wire into the release

The GGUF is **not** committed to git (a ~1GB binary would bloat the repo's history forever). It's
hosted as a GitHub release asset under the dedicated tag `ask-rules-model-v1` (not an app version
release):

```
gh release upload ask-rules-model-v1 scripts/training/output/riftkeep-ask-rules-Q4_K_M.gguf --clobber
```

Then update `scripts/release.ps1`'s `$expectedBytes` to the new file's exact size (the script
verifies the download against this before shipping it, so a corrupt/truncated download aborts the
release rather than shipping a broken model) — `$modelUrl` and `$modelFile` don't need to change
unless you're renaming the file.
