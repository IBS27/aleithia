"""Run vision pipeline from a video already uploaded to the Modal volume.

Uses pretrained YOLOv8n (COCO) for detection — no OpenAI API key needed.
Maps COCO classes → custom neighborhood classes (person, vehicle, etc.).

Frames were already extracted in a previous run (782 frames on volume).
Usage: modal run run_vision_from_volume.py::vision_from_volume --neighborhood "Loop"
"""
import modal

from modal_app.volume import app, volume, video_image, yolo_image, RAW_DATA_PATH, PROCESSED_DATA_PATH
from modal_app.pipelines.vision import VISION_CLASSES

# COCO class IDs → our custom class mapping
COCO_TO_CUSTOM = {
    0: "person",         # person
    1: "vehicle",        # bicycle
    2: "vehicle",        # car
    3: "vehicle",        # motorcycle
    5: "vehicle",        # bus
    7: "vehicle",        # truck
}


@app.function(image=video_image, volumes={"/data": volume}, timeout=300)
def extract_frames_from_volume(sample_rate: int = 5) -> str:
    """Extract frames from a video already on the volume."""
    import subprocess
    from pathlib import Path

    video_path = f"{RAW_DATA_PATH}/vision/tour.mp4"
    frames_dir = f"{RAW_DATA_PATH}/vision/frames"

    # Skip if frames already extracted
    existing = list(Path(frames_dir).glob("*.jpg")) if Path(frames_dir).exists() else []
    if existing:
        print(f"Frames already exist: {len(existing)} frames, skipping extraction")
        return frames_dir

    Path(frames_dir).mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-i", video_path, "-vf", f"fps=1/{sample_rate}", f"{frames_dir}/frame_%04d.jpg"],
        check=True, capture_output=True, text=True,
    )
    volume.commit()
    frame_count = len(list(Path(frames_dir).glob("*.jpg")))
    print(f"Extracted {frame_count} frames")
    return frames_dir


@app.function(image=yolo_image, gpu="T4", volumes={"/data": volume}, timeout=600)
def batch_analyze_pretrained(frames_dir: str, neighborhood: str = "", max_frames: int = 50) -> dict:
    """Run pretrained YOLOv8n on sampled frames, aggregate results.

    Uses COCO model — maps person/vehicle classes to our schema.
    Processes up to max_frames evenly sampled from the full set.
    """
    import json
    from datetime import datetime, timezone
    from pathlib import Path
    from ultralytics import YOLO

    model = YOLO("yolov8n.pt")

    all_frames = sorted(Path(frames_dir).glob("*.jpg"))
    total = len(all_frames)
    step = max(1, total // max_frames)
    sampled = all_frames[::step][:max_frames]
    print(f"Analyzing {len(sampled)} of {total} frames with pretrained YOLOv8n...")

    # Aggregate counts across all sampled frames
    agg_counts = {name: 0 for name in VISION_CLASSES}
    frame_results = []

    for i, frame_path in enumerate(sampled):
        results = model(str(frame_path), verbose=False)
        frame_counts = {name: 0 for name in VISION_CLASSES}

        for box in results[0].boxes:
            coco_id = int(box.cls)
            custom_class = COCO_TO_CUSTOM.get(coco_id)
            if custom_class:
                frame_counts[custom_class] += 1
                agg_counts[custom_class] += 1

        frame_results.append({
            "frame": frame_path.name,
            "person": frame_counts["person"],
            "vehicle": frame_counts["vehicle"],
        })

        if (i + 1) % 10 == 0:
            print(f"  Processed {i + 1}/{len(sampled)} frames...")

    # Compute averages per frame
    n = len(sampled)
    avg_persons = agg_counts["person"] / n if n else 0
    avg_vehicles = agg_counts["vehicle"] / n if n else 0

    foot_traffic = "high" if avg_persons > 15 else "medium" if avg_persons > 5 else "low"

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    result = {
        "counts": agg_counts,
        "frames_analyzed": n,
        "total_frames": total,
        "avg_persons_per_frame": round(avg_persons, 1),
        "avg_vehicles_per_frame": round(avg_vehicles, 1),
        "foot_traffic_density": foot_traffic,
        "vacancy_indicators": 0,
        "business_activity_score": 0,
        "development_activity": 0,
        "dining_scene": 0,
        "neighborhood": neighborhood,
        "timestamp": ts,
        "model": "yolov8n-coco-pretrained",
        "top_frames": sorted(frame_results, key=lambda x: x["person"], reverse=True)[:5],
    }

    # Persist analysis result
    analysis_dir = Path(PROCESSED_DATA_PATH) / "vision" / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    slug = neighborhood.lower().replace(" ", "_") if neighborhood else "unknown"
    out_path = analysis_dir / f"{slug}_{ts}.json"
    out_path.write_text(json.dumps(result, indent=2))
    volume.commit()
    print(f"Analysis saved to {out_path}")

    return result


@app.local_entrypoint(name="vision_from_volume")
def vision_from_volume(neighborhood: str = "Loop"):
    import json

    print("=" * 60)
    print(f"Vision Pipeline (pretrained YOLO) — {neighborhood}")
    print("=" * 60)

    print("\nStep 1: Checking frames on volume...")
    frames_dir = extract_frames_from_volume.remote()
    print(f"  Frames at: {frames_dir}")

    print(f"\nStep 2: Running YOLOv8n inference for {neighborhood}...")
    result = batch_analyze_pretrained.remote(frames_dir, neighborhood, max_frames=50)

    print(f"\n  Frames analyzed: {result['frames_analyzed']} / {result['total_frames']}")
    print(f"  Avg persons/frame: {result['avg_persons_per_frame']}")
    print(f"  Avg vehicles/frame: {result['avg_vehicles_per_frame']}")
    print(f"  Foot traffic density: {result['foot_traffic_density']}")
    print(f"  Total persons detected: {result['counts']['person']}")
    print(f"  Total vehicles detected: {result['counts']['vehicle']}")

    print(f"\n  Full result:\n{json.dumps(result, indent=2)}")

    print("\n" + "=" * 60)
    print("Done! Results persisted to /data/processed/vision/analysis/")
    print("=" * 60)
