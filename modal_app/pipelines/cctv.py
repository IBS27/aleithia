"""CCTV vision pipeline — IDOT highway camera snapshots + YOLOv8n analysis.

Polls Illinois DOT ArcGIS camera feeds, downloads snapshots, runs YOLOv8n
on Modal T4 GPUs to count pedestrians/vehicles/bicycles, annotates frames
with bounding boxes, and feeds counts into the agent swarm.

Cadence: Every 5 minutes (ingester), on-demand (batch analyzer)
Sources: IDOT Gateway ArcGIS REST API (public, no key needed)
GPU: T4 for YOLOv8n inference via @modal.cls + @modal.enter
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx
import modal

from modal_app.common import (
    Document,
    SourceType,
    NEIGHBORHOOD_CENTROIDS,
    gather_with_limit,
    parse_timestamp,
    safe_queue_push,
    safe_volume_commit,
)
from modal_app.costs import track_cost
from modal_app.fallback import FallbackChain
from modal_app.volume import app, volume, base_image, yolo_image, RAW_DATA_PATH, PROCESSED_DATA_PATH

# IDOT Gateway Traffic Cameras — ArcGIS Online (public, no key needed)
IDOT_ARCGIS_URL = (
    "https://services2.arcgis.com/aIrBD8yn1TDTEXoz/arcgis/rest/services/"
    "TrafficCamerasTM_Public/FeatureServer/0/query"
)

# Chicago metro bounding box (covers city + nearby expressways)
CHICAGO_BBOX = {
    "xmin": -88.0,
    "ymin": 41.6,
    "xmax": -87.4,
    "ymax": 42.1,
}

# COCO class IDs for counting
PERSON_ID = 0
BICYCLE_ID = 1
CAR_ID = 2
MOTORCYCLE_ID = 3
BUS_ID = 5
TRUCK_ID = 7
VEHICLE_IDS = {CAR_ID, MOTORCYCLE_ID, BUS_ID, TRUCK_ID}

CONFIDENCE_THRESHOLD = 0.3
CCTV_INDEX_DIR = Path(PROCESSED_DATA_PATH) / "cctv" / "index"
CCTV_LATEST_INDEX_PATH = CCTV_INDEX_DIR / "latest_by_camera.json"


def _classify_density(person_count: int) -> str:
    """Classify pedestrian density level."""
    if person_count <= 5:
        return "low"
    elif person_count <= 20:
        return "medium"
    else:
        return "high"


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Approximate haversine distance in km (good enough for matching)."""
    import math
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _nearest_neighborhood(lat: float, lng: float) -> str:
    """Find nearest Chicago neighborhood by centroid distance."""
    best = ""
    best_dist = float("inf")
    for name, (clat, clng) in NEIGHBORHOOD_CENTROIDS.items():
        d = _haversine_km(lat, lng, clat, clng)
        if d < best_dist:
            best_dist = d
            best = name
    return best if best_dist < 15 else ""


def _timestamp_epoch(value: object) -> float:
    parsed = parse_timestamp(str(value or ""))
    if parsed is None:
        return 0.0
    return parsed.timestamp()


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, default=str))
    tmp_path.replace(path)


def _iter_cctv_meta_dirs(max_meta_days: int | None = None) -> list[Path]:
    root = Path(RAW_DATA_PATH) / "cctv"
    if not root.exists():
        return []

    dirs = [d for d in root.iterdir() if d.is_dir() and d.name != "frames"]
    dirs.sort(key=lambda d: d.name, reverse=True)

    if not max_meta_days or max_meta_days <= 0:
        return dirs

    cutoff_date = datetime.now(timezone.utc).date() - timedelta(days=max_meta_days)
    filtered: list[Path] = []
    for d in dirs:
        try:
            dir_date = datetime.strptime(d.name, "%Y-%m-%d").date()
            if dir_date >= cutoff_date:
                filtered.append(d)
        except ValueError:
            # Keep unknown naming schemes rather than silently dropping data.
            filtered.append(d)
    return filtered


def _build_latest_camera_metadata_map(
    camera_ids: set[str] | None = None,
    max_meta_days: int | None = None,
) -> dict[str, dict]:
    """Load latest camera metadata once, optionally scoped to a camera ID set."""
    targets = None
    if camera_ids is not None:
        targets = {str(cid or "").strip() for cid in camera_ids if str(cid or "").strip()}
        if not targets:
            return {}

    meta_by_camera: dict[str, dict] = {}
    for date_dir in _iter_cctv_meta_dirs(max_meta_days=max_meta_days):
        for mf in date_dir.glob("*.json"):
            cam_id = mf.stem.split("_", 1)[0].strip()
            if not cam_id:
                continue
            if targets is not None and cam_id not in targets:
                continue
            if cam_id in meta_by_camera:
                continue
            try:
                parsed = json.loads(mf.read_text())
            except Exception:
                continue
            meta_by_camera[cam_id] = {
                "lat": _safe_float(parsed.get("lat", 0), default=0.0),
                "lng": _safe_float(parsed.get("lng", 0), default=0.0),
                "location": str(parsed.get("location", "") or ""),
                "direction": str(parsed.get("direction", "") or ""),
            }
            if targets is not None and len(meta_by_camera) >= len(targets):
                return meta_by_camera

    return meta_by_camera


def _load_latest_index_file() -> dict[str, dict]:
    if not CCTV_LATEST_INDEX_PATH.exists():
        return {}
    try:
        parsed = json.loads(CCTV_LATEST_INDEX_PATH.read_text())
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}

    normalized: dict[str, dict] = {}
    for key, payload in parsed.items():
        if not isinstance(payload, dict):
            continue
        cam_id = str(payload.get("camera_id", key) or "").strip()
        if not cam_id:
            continue
        normalized[cam_id] = payload
    return normalized


def _update_cctv_latest_index(results: list[dict], meta_by_camera: dict[str, dict]) -> dict[str, int]:
    """Merge batch results into latest-by-camera index, keeping newest timestamp."""
    latest_index = _load_latest_index_file()
    updated = 0

    for result in results:
        cam_id = str(result.get("camera_id", "") or "").strip()
        if not cam_id:
            continue

        prev = latest_index.get(cam_id, {})
        prev_ts = _timestamp_epoch(prev.get("timestamp"))
        next_ts = _timestamp_epoch(result.get("timestamp"))
        if prev and next_ts <= prev_ts:
            continue

        meta = meta_by_camera.get(cam_id, {})
        lat = _safe_float(meta.get("lat", prev.get("lat", 0)), default=0.0)
        lng = _safe_float(meta.get("lng", prev.get("lng", 0)), default=0.0)

        latest_index[cam_id] = {
            "camera_id": cam_id,
            "lat": lat,
            "lng": lng,
            "location": str(meta.get("location", prev.get("location", "")) or ""),
            "direction": str(meta.get("direction", prev.get("direction", "")) or ""),
            "pedestrians": int(result.get("pedestrians", 0) or 0),
            "vehicles": int(result.get("vehicles", 0) or 0),
            "bicycles": int(result.get("bicycles", 0) or 0),
            "density_level": str(result.get("density_level", "unknown") or "unknown"),
            "timestamp": str(result.get("timestamp", "") or ""),
            "annotated_path": str(result.get("annotated_path", "") or ""),
        }
        updated += 1

    _atomic_write_json(CCTV_LATEST_INDEX_PATH, latest_index)
    return {"updated": updated, "total": len(latest_index)}


# ── 2a. IDOT Camera Ingester ────────────────────────────────────────────────


async def _fetch_idot_cameras() -> list[dict]:
    """Query IDOT ArcGIS for camera features in the Chicago bounding box."""
    params = {
        "where": "TooOld = 'false' OR TooOld IS NULL",
        "geometry": json.dumps(CHICAGO_BBOX),
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "OBJECTID,SnapShot,CameraLocation,CameraDirection,AgeInMinutes,TooOld",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(IDOT_ARCGIS_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    features = data.get("features", [])
    cameras = []
    for feat in features:
        attrs = feat.get("attributes", {})
        geom = feat.get("geometry", {})
        snapshot_url = attrs.get("SnapShot", "")
        if not snapshot_url:
            continue
        cameras.append({
            "camera_id": str(attrs.get("OBJECTID", snapshot_url.split("/")[-1].split(".")[0])),
            "snapshot_url": snapshot_url,
            "location": attrs.get("CameraLocation", ""),
            "direction": attrs.get("CameraDirection", ""),
            "lng": geom.get("x", 0),
            "lat": geom.get("y", 0),
            "age_minutes": attrs.get("AgeInMinutes", 0),
        })

    return cameras


async def _download_snapshot(
    client: httpx.AsyncClient, camera: dict, out_dir: Path
) -> str | None:
    """Download a single camera JPEG. Returns local path or None."""
    url = camera["snapshot_url"]
    cam_id = camera["camera_id"]
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    fname = f"{cam_id}_{ts}.jpg"
    out_path = out_dir / fname

    try:
        resp = await client.get(url, timeout=15, follow_redirects=True)
        if resp.status_code != 200:
            return None
        # Basic JPEG validation
        content = resp.content
        if len(content) < 1000 or not content[:2] == b"\xff\xd8":
            return None
        out_path.write_bytes(content)
        return str(out_path)
    except Exception as e:
        print(f"CCTV snapshot download [{cam_id}]: {e}")
        return None


async def _fetch_camera_snapshots() -> list[dict]:
    """Fetch IDOT cameras and download their snapshots."""
    cameras = await _fetch_idot_cameras()
    if not cameras:
        print("CCTV: No cameras found in Chicago bbox")
        return []

    print(f"CCTV: Found {len(cameras)} active cameras")

    # Prepare frame output directory
    frame_dir = Path(RAW_DATA_PATH) / "cctv" / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)

    # Download snapshots in parallel (limit 5 concurrent)
    async with httpx.AsyncClient() as client:
        coros = [
            _download_snapshot(client, cam, frame_dir) for cam in cameras
        ]
        paths = await gather_with_limit(coros, max_concurrent=5)

    # Pair cameras with downloaded paths
    results = []
    for cam, path in zip(cameras, paths):
        if path:
            cam["local_path"] = path
            results.append(cam)

    print(f"CCTV: Downloaded {len(results)}/{len(cameras)} snapshots")
    return results


def _trim_old_frames(frame_dir: Path, max_age_hours: int = 24) -> int:
    """Remove frames older than max_age_hours. Returns count removed."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    removed = 0
    if not frame_dir.exists():
        return 0
    for f in frame_dir.glob("*.jpg"):
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                f.unlink()
                removed += 1
        except Exception:
            continue
    return removed


@app.function(
    image=base_image,
    volumes={"/data": volume},
    timeout=300,
)
@track_cost("cctv_ingester", "CPU")
async def cctv_ingester():
    """Poll IDOT cameras, download snapshots, spawn GPU analysis."""
    chain = FallbackChain("cctv", "idot", cache_ttl_hours=1)
    cameras = await chain.execute([
        lambda: _fetch_camera_snapshots(),
    ])

    if not cameras:
        print("CCTV ingester: no snapshots obtained")
        return 0

    # Save metadata
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    hour_str = datetime.now(timezone.utc).strftime("%H")
    meta_dir = Path(RAW_DATA_PATH) / "cctv" / date_str
    meta_dir.mkdir(parents=True, exist_ok=True)

    for cam in cameras:
        cam_id = cam["camera_id"]
        meta_path = meta_dir / f"{cam_id}_{hour_str}.json"
        meta_path.write_text(json.dumps(cam, indent=2, default=str))

    # Trim old frames
    frame_dir = Path(RAW_DATA_PATH) / "cctv" / "frames"
    removed = _trim_old_frames(frame_dir)
    if removed:
        print(f"CCTV: trimmed {removed} old frames")

    await safe_volume_commit(volume, "cctv")

    # Spawn GPU batch analysis
    await analyze_cctv_batch.spawn.aio()

    print(f"CCTV ingester: {len(cameras)} cameras processed, batch analysis spawned")
    return len(cameras)


# ── 2b. TrafficAnalyzer GPU Class ────────────────────────────────────────────


@app.cls(
    gpu="T4",
    image=yolo_image,
    volumes={"/data": volume},
    scaledown_window=120,
    timeout=120,
    min_containers=1,
    enable_memory_snapshot=True,
    experimental_options={"enable_gpu_snapshot": True},
)
class TrafficAnalyzer:
    """YOLOv8n inference on CCTV frames — counts persons, vehicles, bicycles."""

    @modal.enter(snap=True)
    @track_cost("TrafficAnalyzer.load_model", "T4")
    def load_model(self):
        import cv2
        from ultralytics import YOLO
        volume.reload()  # Ensure latest frames from ingester are visible
        try:
            cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_SILENT)
        except AttributeError:
            pass
        self.model = YOLO("yolov8n.pt")

    @modal.method()
    def gpu_metrics(self) -> dict:
        """Live GPU metrics via nvidia-smi."""
        import subprocess
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu,utilization.memory,memory.used,memory.total,temperature.gpu,power.draw,power.limit,name",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                return {"status": "error"}
            vals = [v.strip() for v in result.stdout.strip().split(",")]
            return {
                "status": "active",
                "gpu_utilization": int(vals[0]),
                "memory_utilization": int(vals[1]),
                "memory_used_mb": int(vals[2]),
                "memory_total_mb": int(vals[3]),
                "temperature_c": int(vals[4]),
                "power_draw_w": int(float(vals[5])),
                "power_limit_w": int(float(vals[6])),
                "gpu_name": vals[7],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @modal.method()
    @track_cost("TrafficAnalyzer.analyze_frame", "T4")
    def analyze_frame(self, snapshot_path: str, camera_id: str) -> dict:
        """Run YOLOv8n on a single frame, annotate, and return counts."""
        import cv2
        from pathlib import Path

        path = Path(snapshot_path)
        if not path.exists():
            return {"camera_id": camera_id, "error": "file not found"}
        img = cv2.imread(str(path))
        if img is None:
            return {"camera_id": camera_id, "error": "cannot read image"}

        h, w = img.shape[:2]

        # Run inference
        results = self.model(img, conf=CONFIDENCE_THRESHOLD, verbose=False)
        detections = results[0].boxes

        persons = 0
        vehicles = 0
        bicycles = 0
        det_list = []

        for box in detections:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())

            if cls_id == PERSON_ID:
                persons += 1
                color = (0, 255, 0)  # green
                label = "person"
            elif cls_id == BICYCLE_ID:
                bicycles += 1
                color = (0, 255, 255)  # yellow
                label = "bicycle"
            elif cls_id in VEHICLE_IDS:
                vehicles += 1
                color = (255, 0, 0)  # blue
                label = "vehicle"
            else:
                continue

            # Draw bounding box
            cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
            cv2.putText(
                img, f"{label} {conf:.0%}",
                (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1,
            )
            det_list.append({
                "class": label, "confidence": round(conf, 3),
                "bbox": [x1, y1, x2, y2],
            })

        # Semi-transparent top banner with counts
        overlay = img.copy()
        cv2.rectangle(overlay, (0, 0), (w, 32), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, img, 0.4, 0, img)
        banner = f"P: {persons} | V: {vehicles} | B: {bicycles}"
        cv2.putText(img, banner, (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        # Bottom overlay: camera ID + timestamp
        ts_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        cv2.putText(
            img, f"{camera_id} | {ts_str}",
            (10, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1,
        )

        # Save annotated frame
        ann_dir = Path(PROCESSED_DATA_PATH) / "cctv" / "annotated"
        ann_dir.mkdir(parents=True, exist_ok=True)
        ts_file = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        ann_path = ann_dir / f"{camera_id}_{ts_file}.jpg"
        cv2.imwrite(str(ann_path), img)

        density = _classify_density(persons)

        return {
            "camera_id": camera_id,
            "pedestrians": persons,
            "vehicles": vehicles,
            "bicycles": bicycles,
            "density_level": density,
            "detections": det_list,
            "annotated_path": str(ann_path),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# ── 2c. Batch Analyzer ──────────────────────────────────────────────────────


@app.function(
    image=base_image,
    volumes={"/data": volume},
    timeout=300,
)
@track_cost("analyze_cctv_batch", "CPU")
async def analyze_cctv_batch():
    """Analyze all unprocessed CCTV frames via TrafficAnalyzer (GPU dispatched via .remote)."""
    frame_dir = Path(RAW_DATA_PATH) / "cctv" / "frames"
    if not frame_dir.exists():
        print("CCTV batch: no frames directory")
        return 0

    # Find unprocessed frames
    analysis_dir = Path(PROCESSED_DATA_PATH) / "cctv" / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    # Get set of already-analyzed frame stems
    analyzed = set()
    if analysis_dir.exists():
        for f in analysis_dir.glob("*.json"):
            analyzed.add(f.stem)

    frames = sorted(frame_dir.glob("*.jpg"))
    unprocessed = [f for f in frames if f.stem not in analyzed]

    if not unprocessed:
        print("CCTV batch: no unprocessed frames")
        return 0

    print(f"CCTV batch: analyzing {len(unprocessed)} frames")

    # Extract camera IDs from filenames
    frame_info = []
    for frame_path in unprocessed:
        parts = frame_path.stem.rsplit("_", 2)
        camera_id = parts[0] if len(parts) >= 2 else frame_path.stem
        frame_info.append((frame_path, camera_id))

    # Dispatch GPU inference in parallel via .remote.aio()
    analyzer = TrafficAnalyzer()

    async def _analyze_one(fpath, cam_id):
        try:
            return await analyzer.analyze_frame.remote.aio(str(fpath), cam_id)
        except Exception as e:
            print(f"CCTV batch: error analyzing {fpath.name}: {e}")
            return None

    raw_results = await gather_with_limit(
        [_analyze_one(fp, cid) for fp, cid in frame_info],
        max_concurrent=10,
    )

    results = []
    for (frame_path, _), result in zip(frame_info, raw_results):
        if result and "error" not in result:
            results.append(result)
            out_path = analysis_dir / f"{frame_path.stem}.json"
            out_path.write_text(json.dumps(result, indent=2, default=str))

    # Update rolling timeseries per camera (24h window)
    ts_dir = Path(PROCESSED_DATA_PATH) / "cctv" / "timeseries"
    ts_dir.mkdir(parents=True, exist_ok=True)

    camera_groups: dict[str, list[dict]] = {}
    for r in results:
        cid = r["camera_id"]
        camera_groups.setdefault(cid, []).append(r)

    for cid, entries in camera_groups.items():
        ts_path = ts_dir / f"{cid}.json"
        existing = []
        if ts_path.exists():
            try:
                existing = json.loads(ts_path.read_text())
            except Exception:
                existing = []

        existing.extend(entries)

        # Trim to 24h
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        existing = [e for e in existing if e.get("timestamp", "") > cutoff]

        ts_path.write_text(json.dumps(existing, indent=2, default=str))

    camera_ids = {str(r.get("camera_id", "") or "").strip() for r in results if str(r.get("camera_id", "") or "").strip()}
    meta_by_camera = _build_latest_camera_metadata_map(camera_ids=camera_ids)

    # Convert to Documents and push to classification queue
    documents = []
    for r in results:
        cam_id = r["camera_id"]
        meta = meta_by_camera.get(cam_id, {})
        lat = _safe_float(meta.get("lat", 0), default=0.0)
        lng = _safe_float(meta.get("lng", 0), default=0.0)
        location = str(meta.get("location", "") or "")
        direction = str(meta.get("direction", "") or "")

        neighborhood = _nearest_neighborhood(lat, lng) if lat else ""

        doc = Document(
            id=f"cctv-{cam_id}-{r['timestamp']}",
            source=SourceType.CCTV,
            title=f"CCTV: {location or cam_id} ({direction})" if direction else f"CCTV: {location or cam_id}",
            content=(
                f"Camera {cam_id} at {location}: "
                f"{r['pedestrians']} pedestrians, {r['vehicles']} vehicles, "
                f"{r['bicycles']} bicycles. Density: {r['density_level']}."
            ),
            timestamp=datetime.fromisoformat(r["timestamp"]),
            metadata={
                "camera_id": cam_id,
                "pedestrians": r["pedestrians"],
                "vehicles": r["vehicles"],
                "bicycles": r["bicycles"],
                "density_level": r["density_level"],
                "annotated_path": r.get("annotated_path", ""),
                "detection_count": len(r.get("detections", [])),
            },
            geo={
                "lat": lat,
                "lng": lng,
                "neighborhood": neighborhood,
            },
        )
        documents.append(doc)

    # Push to classification queue
    try:
        doc_queue = modal.Queue.from_name("alethia-doc-queue", create_if_missing=True)
        doc_dicts = [d.model_dump(mode="json") for d in documents]
        await safe_queue_push(doc_queue, doc_dicts, "cctv")
    except Exception as e:
        print(f"CCTV batch: queue push failed: {e}")

    try:
        stats = _update_cctv_latest_index(results, meta_by_camera)
        print(f"CCTV batch: latest index updated {stats['updated']} cameras ({stats['total']} total)")
    except Exception as e:
        print(f"CCTV batch: latest index update failed: {e}")

    await safe_volume_commit(volume, "cctv")
    print(f"CCTV batch: analyzed {len(results)} frames, created {len(documents)} documents")
    return len(results)


@app.function(
    image=base_image,
    volumes={"/data": volume},
    timeout=900,
)
@track_cost("rebuild_cctv_latest_index", "CPU")
def rebuild_cctv_latest_index(max_analysis_files: int = 50000, max_meta_days: int = 14) -> dict:
    """One-off rebuild of latest CCTV index from historical analysis files."""
    analysis_dir = Path(PROCESSED_DATA_PATH) / "cctv" / "analysis"
    if not analysis_dir.exists():
        return {"processed_files": 0, "cameras_found": 0, "updated": 0, "total": 0}

    def _mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except Exception:
            return 0.0

    files = sorted(
        analysis_dir.glob("*.json"),
        key=_mtime,
        reverse=True,
    )[:max(0, max_analysis_files)]

    latest_by_camera: dict[str, tuple[float, dict]] = {}
    for jf in files:
        try:
            data = json.loads(jf.read_text())
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        cam_id = str(data.get("camera_id", "") or "").strip()
        if not cam_id:
            continue

        ts_epoch = _timestamp_epoch(data.get("timestamp"))
        if ts_epoch <= 0:
            ts_epoch = _mtime(jf)
        prev = latest_by_camera.get(cam_id)
        if prev is None or ts_epoch > prev[0]:
            latest_by_camera[cam_id] = (ts_epoch, data)

    results = [payload for _, payload in latest_by_camera.values()]
    meta_by_camera = _build_latest_camera_metadata_map(
        camera_ids=set(latest_by_camera.keys()),
        max_meta_days=max_meta_days,
    )
    stats = _update_cctv_latest_index(results, meta_by_camera)
    try:
        volume.commit()
    except Exception as exc:
        print(f"cctv index rebuild commit warning: {exc}")

    with_geo = sum(
        1
        for meta in meta_by_camera.values()
        if _safe_float(meta.get("lat", 0), default=0.0)
    )
    return {
        "processed_files": len(files),
        "cameras_found": len(results),
        "cameras_with_geo": with_geo,
        "updated": stats.get("updated", 0),
        "total": stats.get("total", 0),
    }
