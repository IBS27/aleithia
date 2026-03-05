"""Modal app definition, volume, and image configuration."""
import os
import modal

app = modal.App("alethia")

volume = modal.Volume.from_name("alethia-data", create_if_missing=True)
weights_volume = modal.Volume.from_name("alethia-weights", create_if_missing=True)

VOLUME_MOUNT = "/data"
WEIGHTS_MOUNT = "/weights"
RAW_DATA_PATH = f"{VOLUME_MOUNT}/raw"
PROCESSED_DATA_PATH = f"{VOLUME_MOUNT}/processed"
CACHE_PATH = f"{VOLUME_MOUNT}/cache"

# Arize AX tracing packages safe for all images.
_arize_core_packages = [
    "arize-otel",
    "openinference-instrumentation",
    "opentelemetry-api",
    "opentelemetry-sdk",
]

# OpenAI-specific instrumentation; only install in images that include openai.
_arize_openai_packages = [
    "openinference-instrumentation-openai",
]

# Internal base (no local source — derived images add pip_install then local source last)
_base = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "httpx==0.27.0",
        "pydantic==2.9.0",
        "feedparser==6.0.11",
        "openai>=1.69.0,<2",
        *_arize_core_packages,
        *_arize_openai_packages,
    )
)

# add_local_python_source must be LAST — no pip_install after it
base_image = _base.add_local_python_source("modal_app", copy=True)

reddit_image = _base.pip_install("asyncpraw==7.7.1").add_local_python_source("modal_app", copy=True)

politics_image = _base.pip_install(
    "pymupdf==1.24.0",
    "pdfplumber==0.11.0",
).add_local_python_source("modal_app", copy=True)

data_image = _base.pip_install("pandas==2.2.0").add_local_python_source("modal_app", copy=True)

graph_image = _base.pip_install("networkx==3.3", "pandas==2.2.0").add_local_python_source("modal_app", copy=True)

# vLLM image for self-hosted LLM (Qwen3-8B on H100)
# vLLM includes its own optimized attention kernels; flash-attn is optional
vllm_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "vllm>=0.8.0",
        "transformers>=4.45.0",
        "torch>=2.4.0",
        *_arize_core_packages,
    )
    .add_local_python_source("modal_app", copy=True)
)

# Classification image for DocClassifier + SentimentAnalyzer (T4)
classify_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "transformers>=4.45.0",
        "torch>=2.4.0",
        "httpx==0.27.0",
        "pydantic==2.9.0",
        *_arize_core_packages,
    )
    .add_local_python_source("modal_app", copy=True)
)

# Web API image
web_image = (
    _base.pip_install(
        "fastapi>=0.115.0",
        "uvicorn>=0.34.0",
    )
    .add_local_python_source("modal_app", copy=True)
)

# Sandbox image for AI-generated data analysis scripts (no local source — standalone code)
sandbox_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("pandas==2.2.0", "matplotlib==3.9.0", "numpy==1.26.0", "seaborn==0.13.0")
)

# Lead Analyst: recursive agent architecture with E2B sandbox workers
lead_analyst_image = (
    _base.pip_install("e2b-code-interpreter>=1.0.0")
    .add_local_python_source("modal_app", copy=True)
)

# Vision pipeline images
video_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install("yt-dlp==2024.8.6")
    .add_local_python_source("modal_app", copy=True)
)

label_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "openai>=1.69.0,<2",
        "httpx==0.27.0",
        "pillow==10.4.0",
        *_arize_core_packages,
        *_arize_openai_packages,
    )
    .add_local_python_source("modal_app", copy=True)
)

yolo_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libgl1-mesa-glx", "libglib2.0-0")
    .pip_install("ultralytics==8.3.40", "opencv-python-headless==4.9.0.80", "httpx==0.27.0", "pydantic==2.9.0")
    .add_local_python_source("modal_app", copy=True)
)

# Parking detection: SegFormer + YOLOv8m + SAHI for satellite imagery analysis
parking_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libgl1-mesa-glx", "libglib2.0-0")
    .pip_install(
        "transformers>=4.45.0", "torch>=2.4.0",
        "ultralytics==8.3.40", "sahi>=0.11.0",
        "opencv-python-headless==4.9.0.80", "Pillow>=10.4.0",
        "httpx==0.27.0", "pydantic==2.9.0",
    )
    .add_local_python_source("modal_app", copy=True)
)

# VectorAI DB: Actian vector database + embedding model + Python client
# VectorAI DB image: requires actiancortex (private package) + vectoraidb binary.
# The image from_registry("williamimoh/actian-vectorai-db:1.0b") provides both,
# but needs Python installed. Set VECTORDB_IMAGE=1 env var to enable this image.
# When disabled, all VectorDB code degrades gracefully via vectordb_available().
_build_vectordb = os.environ.get("VECTORDB_IMAGE", "").strip() == "1"
if _build_vectordb:
    vectordb_image = (
        modal.Image.from_registry("williamimoh/actian-vectorai-db:1.0b")
        .run_commands(
            "apt-get update -qq && apt-get install -y -qq python3 python3-pip python3-venv > /dev/null 2>&1 && ln -sf /usr/bin/python3 /usr/bin/python",
            "python3 -m pip install --break-system-packages actiancortex sentence-transformers==3.3.1 'torch>=2.4.0' 'grpcio>=1.60.0' httpx==0.27.0 pydantic==2.9.0 "
            + " ".join(_arize_core_packages),
        )
        .add_local_python_source("modal_app", copy=True)
    )
else:
    vectordb_image = None

# TikTok scraper: Playwright + Kernel cloud browser
tiktok_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "kernel>=0.1.0",
        "playwright>=1.40.0",
        "httpx==0.27.0",
        "pydantic==2.9.0",
    )
    .run_commands("playwright install chromium")
    .add_local_python_source("modal_app")
)

# TikTok transcription: yt-dlp + Whisper on GPU
transcribe_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("ffmpeg")
    .pip_install(
        "yt-dlp>=2024.1.0",
        "openai-whisper>=20231117",
        "torch>=2.1.0",
        "httpx==0.27.0",
        "pydantic==2.9.0",
    )
    .add_local_python_source("modal_app")
)
