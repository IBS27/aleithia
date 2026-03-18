"""
Generate synthetic Q&A training pairs from existing Chicago data.
Run: modal run generate_training_data.py
Output: /data/training_pairs.jsonl on your volume
"""
import json
import modal
from pathlib import Path

app = modal.App("alethia-training-data")
volume = modal.Volume.from_name("alethia-data", create_if_missing=True)

image = modal.Image.debian_slim(python_version="3.12").pip_install(
    "vllm>=0.8.0", "transformers>=4.45.0,<4.52.0", "huggingface_hub[hf_transfer]"
).env({"HF_HUB_ENABLE_HF_TRANSFER": "1", "VLLM_USE_V1": "1"})

weights_vol = modal.Volume.from_name("alethia-weights", create_if_missing=True)


@app.function(
    image=image,
    gpu=modal.gpu.H100(),
    volumes={"/data": volume, "/models": weights_vol},
    timeout=3600,
)
def generate_pairs():
    from vllm import LLM, SamplingParams

    llm = LLM(model="Qwen/Qwen3-8B-FP8", download_dir="/models", max_model_len=4096)
    params = SamplingParams(temperature=0.7, max_tokens=512)

    # Load existing docs
    raw = Path("/data/raw")
    docs = []
    for f in raw.rglob("*.json"):
        try:
            d = json.loads(f.read_text())
            if d.get("content") and len(d["content"]) > 100:
                docs.append(d)
        except Exception:
            continue

    print(f"Found {len(docs)} docs, generating pairs from first 300...")
    docs = docs[:300]

    # Generate questions
    q_prompts = [
        f"You are a Chicago small business advisor. Given this document, generate ONE specific question a small business owner would ask.\n\nTitle: {d.get('title', '')}\nContent: {d['content'][:800]}\n\nQuestion:"
        for d in docs
    ]
    q_outputs = llm.generate(q_prompts, params)
    questions = [o.outputs[0].text.strip() for o in q_outputs]

    # Generate answers
    a_prompts = [
        f"You are Alethia, a Chicago business intelligence advisor. Answer this question using ONLY the provided context.\n\nContext: {d['content'][:1200]}\n\nQuestion: {q}\n\nAnswer:"
        for d, q in zip(docs, questions)
    ]
    a_outputs = llm.generate(a_prompts, params)
    answers = [o.outputs[0].text.strip() for o in a_outputs]

    # Save as JSONL
    out = Path("/data/training_pairs.jsonl")
    pairs = []
    for d, q, a in zip(docs, questions, answers):
        if len(q) > 10 and len(a) > 20:
            pair = {
                "instruction": q,
                "input": "",
                "output": a,
                "source": d.get("source", "unknown"),
                "neighborhood": d.get("geo", {}).get("neighborhood", ""),
            }
            pairs.append(pair)
            with out.open("a") as f:
                f.write(json.dumps(pair) + "\n")

    volume.commit()
    print(f"Generated {len(pairs)} training pairs → /data/training_pairs.jsonl")
    return len(pairs)


@app.local_entrypoint()
def main():
    count = generate_pairs.remote()
    print(f"Done: {count} pairs generated")
