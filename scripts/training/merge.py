"""Merges the trained LoRA adapter into the base model weights, ready for GGUF conversion."""
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

BASE_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
HERE = Path(__file__).resolve().parent
ADAPTER_DIR = HERE / "output" / "lora-adapter"
MERGED_DIR = HERE / "output" / "merged"

print("Loading base model...")
base = AutoModelForCausalLM.from_pretrained(BASE_MODEL, torch_dtype=torch.bfloat16, device_map="cuda:0")
tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)

print("Loading and merging LoRA adapter...")
model = PeftModel.from_pretrained(base, str(ADAPTER_DIR))
model = model.merge_and_unload()

print(f"Saving merged model to {MERGED_DIR}...")
model.save_pretrained(str(MERGED_DIR), safe_serialization=True)
tokenizer.save_pretrained(str(MERGED_DIR))
print("Done.")
