"""Merges the trained LoRA adapter into the base model weights, ready for GGUF conversion.

RIFTKEEP_BASE_MODEL must match whatever train.py was run with — the adapter's weights are only
meaningful relative to the exact base model they were trained against. Override
RIFTKEEP_ADAPTER_DIR/RIFTKEEP_MERGED_DIR to match train.py's RIFTKEEP_OUTPUT_DIR when training a
non-default model, so this doesn't overwrite another model's merged output.
"""
import gc
import os
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

BASE_MODEL = os.environ.get("RIFTKEEP_BASE_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
HERE = Path(__file__).resolve().parent
ADAPTER_DIR = Path(os.environ.get("RIFTKEEP_ADAPTER_DIR", str(HERE / "output" / "lora-adapter")))
MERGED_DIR = Path(os.environ.get("RIFTKEEP_MERGED_DIR", str(HERE / "output" / "merged")))

print("Loading base model...")
base = AutoModelForCausalLM.from_pretrained(BASE_MODEL, torch_dtype=torch.bfloat16, device_map="cuda:0")
tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)

print("Loading and merging LoRA adapter...")
model = PeftModel.from_pretrained(base, str(ADAPTER_DIR))
model = model.merge_and_unload()

# The implicit GPU->CPU transfer inside save_pretrained() held both a GPU and a CPU copy of the
# model in memory at once — observed directly to intermittently kill the process partway through
# "Writing model shards" (repeatable across separate training runs, not a one-off). Doing the
# transfer explicitly first, then freeing the now-unused CUDA allocation before the CPU-side
# safetensors write, keeps peak memory lower at the moment that write actually happens.
print("Moving merged model to CPU...")
model = model.to("cpu")
torch.cuda.empty_cache()
gc.collect()

print(f"Saving merged model to {MERGED_DIR}...")
model.save_pretrained(str(MERGED_DIR), safe_serialization=True)
tokenizer.save_pretrained(str(MERGED_DIR))
print("Done.")
