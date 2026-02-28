"""Modal app definition, volume, and image configuration."""
import modal

app = modal.App("alethia")

volume = modal.Volume.from_name("alethia-data", create_if_missing=True)
weights_volume = modal.Volume.from_name("alethia-weights", create_if_missing=True)

VOLUME_MOUNT = "/data"
WEIGHTS_MOUNT = "/weights"
RAW_DATA_PATH = f"{VOLUME_MOUNT}/raw"
PROCESSED_DATA_PATH = f"{VOLUME_MOUNT}/processed"
CACHE_PATH = f"{VOLUME_MOUNT}/cache"

# Internal base (no local source — derived images add pip_install then local source last)
_base = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "httpx==0.27.0",
        "pydantic==2.9.0",
        "feedparser==6.0.11",
    )
)

# add_local_python_source must be LAST — no pip_install after it
base_image = _base.add_local_python_source("modal_app")

reddit_image = _base.pip_install("asyncpraw==7.7.1").add_local_python_source("modal_app")

politics_image = _base.pip_install(
    "pymupdf==1.24.0",
    "pdfplumber==0.11.0",
).add_local_python_source("modal_app")

data_image = _base.pip_install("pandas==2.2.0").add_local_python_source("modal_app")

# vLLM image for self-hosted LLM (Qwen3-8B on H100)
vllm_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "vllm>=0.8.0",
        "transformers>=4.45.0",
        "torch>=2.4.0",
    )
    .run_commands("pip install flash-attn --no-build-isolation")
    .add_local_python_source("modal_app")
)

# Classification image for DocClassifier + SentimentAnalyzer (T4)
classify_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "transformers>=4.45.0",
        "torch>=2.4.0",
        "httpx==0.27.0",
        "pydantic==2.9.0",
    )
    .add_local_python_source("modal_app")
)

# Web API image
web_image = (
    _base.pip_install(
        "fastapi>=0.115.0",
        "uvicorn>=0.34.0",
    )
    .add_local_python_source("modal_app")
)

# Vision pipeline images
video_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install("yt-dlp==2024.8.6")
    .add_local_python_source("modal_app")
)

label_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("openai==1.50.0", "httpx==0.27.0", "pillow==10.4.0")
    .add_local_python_source("modal_app")
)

yolo_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libgl1-mesa-glx", "libglib2.0-0")
    .pip_install("ultralytics==8.2.0", "opencv-python-headless==4.9.0.80")
    .add_local_python_source("modal_app")
)
