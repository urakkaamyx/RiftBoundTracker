"""
LoRA fine-tune of Qwen2.5-1.5B-Instruct on the real Riftbound rules dataset (see
generate_dataset.py). Goal: reinforce the RAG-grounded answering behavior already verified to
work with correct prompting, so it's more consistent, not to memorize rule text into weights
(that would go stale the next game patch — retrieval still supplies the live evidence at
inference time either way).

Requires a CUDA GPU with ~8GB VRAM. Install deps: pip install torch transformers peft trl
datasets bitsandbytes accelerate
"""
from pathlib import Path

import torch
from datasets import Dataset
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import SFTConfig, SFTTrainer

BASE_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
HERE = Path(__file__).resolve().parent
DATASET_PATH = HERE / "output" / "dataset.jsonl"
OUTPUT_DIR = HERE / "output" / "lora-adapter"

print(f"CUDA available: {torch.cuda.is_available()}, device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu'}")

print("Loading dataset...")
dataset = Dataset.from_json(str(DATASET_PATH))
print(f"  {len(dataset)} examples")

print(f"Loading base model {BASE_MODEL}...")
tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
model = AutoModelForCausalLM.from_pretrained(BASE_MODEL, torch_dtype=torch.bfloat16, device_map="cuda:0")
model.config.use_cache = False

lora_config = LoraConfig(
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
)
model = get_peft_model(model, lora_config)
model.print_trainable_parameters()

sft_config = SFTConfig(
    output_dir=str(OUTPUT_DIR),
    num_train_epochs=3,
    per_device_train_batch_size=2,
    gradient_accumulation_steps=4,
    learning_rate=2e-4,
    logging_steps=10,
    save_strategy="epoch",
    bf16=True,
    report_to=[],
    max_length=1024,
    packing=False,
)

trainer = SFTTrainer(model=model, args=sft_config, train_dataset=dataset, processing_class=tokenizer)

print("Training...")
trainer.train()

print("Saving LoRA adapter...")
trainer.save_model(str(OUTPUT_DIR))
tokenizer.save_pretrained(str(OUTPUT_DIR))
print(f"Done. Adapter saved to {OUTPUT_DIR}")
