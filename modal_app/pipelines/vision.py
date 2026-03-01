"""Neighborhood Vision Pipeline — Yolodex-inspired CV for urban business intelligence.

Full end-to-end pipeline:
  YouTube walking tour URL → frame extraction → parallel GPT-4V labeling
  → YOLO-format dataset → custom YOLOv8n training → neighborhood health detector

Custom detection classes (8):
  0: person, 1: vehicle, 2: storefront_open, 3: storefront_closed,
  4: for_lease_sign, 5: construction, 6: restaurant_signage, 7: outdoor_dining

Usage:
  modal run modal_app/pipelines/vision.py --youtube-url "https://youtube.com/watch?v=..."
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import modal

from modal_app.volume import app, volume, video_image, label_image, yolo_image, RAW_DATA_PATH, PROCESSED_DATA_PATH

VISION_CLASSES = [
    "person", "vehicle", "storefront_open", "storefront_closed",
    "for_lease_sign", "construction", "restaurant_signage", "outdoor_dining",
]


# ─── Step 1: Video Download + Frame Extraction ────────────────────────────────


@app.function(image=video_image, volumes={"/data": volume}, timeout=300)
def extract_frames(youtube_url: str, sample_rate: int = 5) -> str:
    """Download YouTube video and extract key frames.

    Args:
        youtube_url: YouTube walking tour URL
        sample_rate: Extract every Nth second (5 = one frame per 5 seconds)
    Returns:
        Path to extracted frames directory on volume
    """
    import subprocess

    video_path = "/tmp/tour.mp4"
    frames_dir = f"{RAW_DATA_PATH}/vision/frames"

    # Download with yt-dlp
    try:
        subprocess.run(
            ["yt-dlp", "-f", "best[height<=720]", "-o", video_path, youtube_url],
            check=True, capture_output=True, text=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"yt-dlp failed (exit {e.returncode}): {e.stderr[:500]}")
        raise RuntimeError(f"Video download failed for {youtube_url}") from e

    # Extract frames with FFmpeg
    Path(frames_dir).mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                "ffmpeg", "-i", video_path,
                "-vf", f"fps=1/{sample_rate}",
                f"{frames_dir}/frame_%04d.jpg",
            ],
            check=True, capture_output=True, text=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"ffmpeg failed (exit {e.returncode}): {e.stderr[:500]}")
        raise RuntimeError(f"Frame extraction failed for {video_path}") from e

    volume.commit()
    frame_count = len(list(Path(frames_dir).glob("*.jpg")))
    print(f"Extracted {frame_count} frames from {youtube_url}")
    return frames_dir


# ─── Step 2: Parallel Vision Agent Labeling ────────────────────────────────────


@app.function(
    image=label_image,
    volumes={"/data": volume},
    secrets=[modal.Secret.from_name("alethia-secrets")],
    timeout=600,
)
def label_frame(frame_path: str, classes: list[str] | None = None) -> dict:
    """Use GPT-4V to label a single frame with bounding boxes.

    Returns YOLO-format annotations: class_id x_center y_center width height
    """
    import base64
    import openai
    from PIL import Image

    from modal_app.instrumentation import init_tracing
    init_tracing()

    if classes is None:
        classes = VISION_CLASSES

    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    with open(frame_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    img = Image.open(frame_path)
    w, h = img.size

    prompt = f"""Analyze this Chicago street scene image. For each object you detect, provide bounding box coordinates.

Classes to detect: {', '.join(f'{i}: {c}' for i, c in enumerate(classes))}

Return a JSON object with a "detections" array where each element is:
{{"class_id": int, "label": str, "bbox": [x_min, y_min, x_max, y_max]}}

Coordinates should be pixel values (image is {w}x{h}).
Only include objects you're confident about (>70% confidence).
Focus on business-relevant features: storefronts, signage, people, vehicles."""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ],
        }],
        response_format={"type": "json_object"},
        max_tokens=1000,
    )

    raw = json.loads(response.choices[0].message.content)
    detections = raw.get("detections", raw if isinstance(raw, list) else [])

    # Convert to YOLO format: class_id x_center y_center width height (normalized 0-1)
    yolo_labels = []
    for det in detections:
        bbox = det.get("bbox", [])
        if len(bbox) == 4:
            x_center = ((bbox[0] + bbox[2]) / 2) / w
            y_center = ((bbox[1] + bbox[3]) / 2) / h
            box_w = (bbox[2] - bbox[0]) / w
            box_h = (bbox[3] - bbox[1]) / h
            yolo_labels.append(
                f"{det['class_id']} {x_center:.6f} {y_center:.6f} {box_w:.6f} {box_h:.6f}"
            )

    return {"frame": frame_path, "labels": yolo_labels, "count": len(yolo_labels)}


@app.function(
    image=label_image,
    volumes={"/data": volume},
    secrets=[modal.Secret.from_name("alethia-secrets")],
    timeout=900,
)
def label_all_frames(frames_dir: str) -> str:
    """Dispatch parallel labeling agents for all frames. Returns dataset path."""
    frames = sorted(Path(frames_dir).glob("*.jpg"))
    print(f"Labeling {len(frames)} frames with {len(VISION_CLASSES)} classes...")

    # Parallel labeling — Modal auto-scales workers
    results = list(label_frame.map(
        [str(f) for f in frames],
        kwargs={"classes": VISION_CLASSES},
    ))

    # Write YOLO dataset
    dataset_dir = f"{PROCESSED_DATA_PATH}/vision/dataset"
    images_dir = Path(dataset_dir) / "images" / "train"
    labels_dir = Path(dataset_dir) / "labels" / "train"
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    total_labels = 0
    for result in results:
        if result and result.get("labels"):
            frame_name = Path(result["frame"]).stem
            # Copy image to dataset directory
            src = Path(result["frame"])
            dst = images_dir / f"{frame_name}.jpg"
            if src.exists() and not dst.exists():
                import shutil
                shutil.copy2(str(src), str(dst))
            # Write label file
            (labels_dir / f"{frame_name}.txt").write_text("\n".join(result["labels"]))
            total_labels += result["count"]

    # Write dataset YAML
    yaml_content = f"""path: {dataset_dir}
train: images/train
val: images/train
names:
"""
    for i, cls_name in enumerate(VISION_CLASSES):
        yaml_content += f"  {i}: {cls_name}\n"

    (Path(dataset_dir) / "data.yaml").write_text(yaml_content)

    volume.commit()
    print(f"Dataset ready: {len(results)} images, {total_labels} total labels")
    return dataset_dir


# ─── Step 3: Custom YOLO Training ─────────────────────────────────────────────


@app.function(
    image=yolo_image,
    gpu="T4",
    volumes={"/data": volume},
    timeout=1800,  # 30 min max for training
)
def train_detector(dataset_dir: str, epochs: int = 50) -> str:
    """Train custom YOLOv8n detector on labeled neighborhood data."""
    from ultralytics import YOLO

    model = YOLO("yolov8n.pt")  # start from pretrained
    model.train(
        data=f"{dataset_dir}/data.yaml",
        epochs=epochs,
        imgsz=640,
        batch=16,
        device=0,
        project=f"{PROCESSED_DATA_PATH}/vision",
        name="neighborhood_detector",
    )

    best_model = f"{PROCESSED_DATA_PATH}/vision/neighborhood_detector/weights/best.pt"
    volume.commit()
    print(f"Training complete. Best model: {best_model}")
    return best_model


# ─── Step 4: Inference ─────────────────────────────────────────────────────────


@app.function(image=yolo_image, gpu="T4", volumes={"/data": volume}, timeout=120)
def analyze_neighborhood(image_path: str, model_path: str = "", neighborhood: str = "") -> dict:
    """Run custom detector on a neighborhood image. Returns structured analysis."""
    from ultralytics import YOLO

    if not model_path:
        model_path = f"{PROCESSED_DATA_PATH}/vision/neighborhood_detector/weights/best.pt"

    model = YOLO(model_path)
    results = model(image_path)

    counts = {name: 0 for name in VISION_CLASSES}
    for box in results[0].boxes:
        cls_id = int(box.cls)
        if cls_id < len(VISION_CLASSES):
            counts[VISION_CLASSES[cls_id]] += 1

    # Compute neighborhood health indicators
    foot_traffic = "high" if counts["person"] > 15 else "medium" if counts["person"] > 5 else "low"
    vacancy_rate = counts["for_lease_sign"] + counts["storefront_closed"]
    business_activity = counts["storefront_open"] + counts["restaurant_signage"] + counts["outdoor_dining"]

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    result = {
        "counts": counts,
        "foot_traffic_density": foot_traffic,
        "vacancy_indicators": vacancy_rate,
        "business_activity_score": business_activity,
        "development_activity": counts["construction"],
        "dining_scene": counts["restaurant_signage"] + counts["outdoor_dining"],
        "neighborhood": neighborhood,
        "timestamp": ts,
    }

    # Persist analysis result to disk
    analysis_dir = Path(PROCESSED_DATA_PATH) / "vision" / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    slug = neighborhood.lower().replace(" ", "_") if neighborhood else "unknown"
    out_path = analysis_dir / f"{slug}_{ts}.json"
    out_path.write_text(json.dumps(result, indent=2))
    volume.commit()
    print(f"Analysis saved to {out_path}")

    return result


# ─── Full Pipeline Orchestrator ────────────────────────────────────────────────


@app.local_entrypoint()
def run_vision_pipeline(youtube_url: str, neighborhood: str = ""):
    """End-to-end: YouTube URL → custom neighborhood detector.

    Usage: modal run modal_app/pipelines/vision.py --youtube-url "https://youtube.com/watch?v=..." --neighborhood "Loop"
    """
    print("=" * 60)
    print("Alethia Neighborhood Vision Pipeline")
    print("=" * 60)

    print("\nStep 1: Extracting frames from YouTube video...")
    frames_dir = extract_frames.remote(youtube_url)
    print(f"  Frames saved to: {frames_dir}")

    print("\nStep 2: Labeling with parallel vision agents (GPT-4V)...")
    dataset_dir = label_all_frames.remote(frames_dir)
    print(f"  Dataset saved to: {dataset_dir}")

    print("\nStep 3: Training custom YOLOv8n detector...")
    model_path = train_detector.remote(dataset_dir, epochs=50)
    print(f"  Model saved to: {model_path}")

    print("\n" + "=" * 60)
    print(f"Pipeline complete! Custom detector at: {model_path}")
    print(f"Run inference:")
    print(f"  modal run modal_app/pipelines/vision.py::analyze_neighborhood --image-path <path>")
    print("=" * 60)
