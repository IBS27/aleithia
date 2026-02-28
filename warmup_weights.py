"""
Pre-download Qwen3 8B FP8 weights to Modal volume.
Run: modal run warmup_weights.py
"""
import modal

app = modal.App("alethia-warmup")
weights_vol = modal.Volume.from_name("alethia-weights", create_if_missing=True)

image = modal.Image.debian_slim(python_version="3.12").pip_install(
    "huggingface_hub[hf_transfer]"
).env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})


@app.function(image=image, volumes={"/models": weights_vol}, timeout=1800)
def download_weights():
    from huggingface_hub import snapshot_download

    snapshot_download("Qwen/Qwen3-8B-FP8", local_dir="/models/Qwen3-8B-FP8")
    weights_vol.commit()
    print("Weights downloaded and cached.")


@app.local_entrypoint()
def main():
    download_weights.remote()
