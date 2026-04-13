"""CCTV, parking, and related sensor-read helpers for the Modal API."""
from __future__ import annotations

import asyncio
import copy
import importlib
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import modal

from backend.shared_data import load_json_file
from modal_app.api.cache import cache
from modal_app.common import NEIGHBORHOOD_CENTROIDS, parse_timestamp
from modal_app.runtime import ENABLE_CCTV_ANALYSIS, get_modal_function
from modal_app.volume import PROCESSED_DATA_PATH, RAW_DATA_PATH, volume

CCTV_LATEST_INDEX_PATH = Path(PROCESSED_DATA_PATH) / "cctv" / "index" / "latest_by_camera.json"
SYNTHETIC_CCTV_PATH = Path(PROCESSED_DATA_PATH) / "cctv" / "synthetic_analytics.json"
LEGACY_FAKE_CCTV_PATH = Path(PROCESSED_DATA_PATH) / "cctv" / "fake_analytics.json"
CCTV_NEIGHBORHOOD_CAMERA_LIMIT = 24
CCTV_STALE_AFTER_SECONDS = 6 * 60 * 60
CCTV_REFRESH_DEBOUNCE_SECONDS = 10 * 60
CCTV_REFRESH_DICT_KEY = "latest-index"

cctv_refresh_recent_dict = modal.Dict.from_name("alethia-cctv-refresh-recent", create_if_missing=True)
_cctv_refresh_lock = asyncio.Lock()


def _generate_synthetic_cctv() -> dict:
    try:
        import backend.shared_data as shared_data

        sys.modules.setdefault("shared_data", shared_data)
        generator = importlib.import_module("backend.generate_synthetic_analytics")
        return generator.generate()
    except Exception as exc:
        print(f"cctv_synthetic_generate_failed: {exc}")
        return {}


def load_synthetic_cctv() -> dict:
    """Load synthetic CCTV analytics, preferring the shared volume copy."""
    source_path: Path | None = None
    if SYNTHETIC_CCTV_PATH.exists():
        source_path = SYNTHETIC_CCTV_PATH
    elif LEGACY_FAKE_CCTV_PATH.exists():
        source_path = LEGACY_FAKE_CCTV_PATH

    if source_path is not None:
        cache_key = f"cctv:synthetic:{source_path.name}:{int(source_path.stat().st_mtime)}"

        def _loader() -> dict:
            return load_json_file(source_path, default={})

        return copy.deepcopy(cache.get_or_set(cache_key, 15.0, _loader))

    return copy.deepcopy(cache.get_or_set("cctv:synthetic:generated:v1", 60.0, _generate_synthetic_cctv))


def empty_cctv_payload() -> dict:
    return {"cameras": [], "avg_pedestrians": 0, "avg_vehicles": 0, "density": "unknown"}


def analysis_timestamp_epoch(data: dict, fallback_mtime: float) -> float:
    parsed = parse_timestamp(data.get("timestamp"))
    if parsed is not None:
        return parsed.timestamp()
    return fallback_mtime


def camera_frame_available(camera_id: str) -> bool:
    """Return whether any recent annotated/raw JPEG exists for the camera."""
    frame_dirs = [
        Path(PROCESSED_DATA_PATH) / "cctv" / "annotated",
        Path(RAW_DATA_PATH) / "cctv" / "frames",
    ]
    for frame_dir in frame_dirs:
        if not frame_dir.exists():
            continue
        if next(frame_dir.glob(f"{camera_id}_*.jpg"), None) is not None:
            return True
    return False


async def _dict_get_float(key: str, default: float = 0.0) -> float:
    try:
        value = await cctv_refresh_recent_dict.get.aio(key)
    except Exception:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


async def _dict_put_value(key: str, value: float) -> None:
    try:
        await cctv_refresh_recent_dict.put.aio(key, value)
    except Exception:
        try:
            cctv_refresh_recent_dict[key] = value
        except Exception:
            pass


async def maybe_spawn_cctv_refresh(index_age_seconds: float) -> None:
    if index_age_seconds <= CCTV_STALE_AFTER_SECONDS:
        return

    async with _cctv_refresh_lock:
        now_epoch = time.time()
        last_trigger_epoch = await _dict_get_float(CCTV_REFRESH_DICT_KEY, default=0.0)
        if now_epoch - last_trigger_epoch < CCTV_REFRESH_DEBOUNCE_SECONDS:
            return

        await _dict_put_value(CCTV_REFRESH_DICT_KEY, now_epoch)
        try:
            cctv_fn = get_modal_function("cctv_ingester")
            spawn_aio = getattr(cctv_fn.spawn, "aio", None)
            if callable(spawn_aio):
                await spawn_aio()
            else:
                cctv_fn.spawn()
            print(
                "cctv_refresh_spawned",
                {
                    "index_age_seconds": round(index_age_seconds, 1),
                    "triggered_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception as exc:
            await _dict_put_value(CCTV_REFRESH_DICT_KEY, 0.0)
            print(f"cctv_refresh_spawn_failed: {exc}")


def synthetic_cctv_entry(name: str) -> dict | None:
    synthetic = load_synthetic_cctv()
    entry = synthetic.get(name)
    if not isinstance(entry, dict):
        return None

    cam_blob = entry.get("cameras", {})
    if not isinstance(cam_blob, dict):
        return None

    raw_cams = cam_blob.get("cameras", [])
    if not isinstance(raw_cams, list):
        raw_cams = []

    normalized: list[dict] = []
    for idx, cam in enumerate(raw_cams):
        if not isinstance(cam, dict):
            continue
        try:
            lat = float(cam.get("lat", 0) or 0)
            lng = float(cam.get("lng", 0) or 0)
            dist = float(cam.get("distance_km", 0) or 0)
            pedestrians = int(cam.get("pedestrians", 0) or 0)
            vehicles = int(cam.get("vehicles", 0) or 0)
            bicycles = int(cam.get("bicycles", 0) or 0)
        except (TypeError, ValueError):
            continue
        normalized.append(
            {
                "camera_id": str(cam.get("camera_id", f"fake-{name}-{idx}") or f"fake-{name}-{idx}"),
                "lat": lat,
                "lng": lng,
                "distance_km": round(dist, 2),
                "pedestrians": pedestrians,
                "vehicles": vehicles,
                "bicycles": bicycles,
                "density_level": str(cam.get("density_level", "unknown") or "unknown"),
                "timestamp": str(cam.get("timestamp", "") or ""),
            }
        )

    try:
        avg_p = float(cam_blob.get("avg_pedestrians", 0) or 0)
    except (TypeError, ValueError):
        avg_p = 0.0
    try:
        avg_v = float(cam_blob.get("avg_vehicles", 0) or 0)
    except (TypeError, ValueError):
        avg_v = 0.0

    return {
        "cameras": normalized[:CCTV_NEIGHBORHOOD_CAMERA_LIMIT],
        "avg_pedestrians": round(avg_p, 1),
        "avg_vehicles": round(avg_v, 1),
        "density": str(cam_blob.get("density", "unknown") or "unknown"),
        "timeseries": entry.get("timeseries"),
    }


def _build_synthetic_neighborhood_payload(entry: dict) -> dict:
    normalized_cameras: list[dict] = []

    for camera in entry.get("cameras", []):
        camera_id = camera["camera_id"]
        normalized_cameras.append(
            {
                "camera_id": camera_id,
                "lat": camera["lat"],
                "lng": camera["lng"],
                "distance_km": camera["distance_km"],
                "pedestrians": camera["pedestrians"],
                "vehicles": camera["vehicles"],
                "bicycles": camera["bicycles"],
                "density_level": camera["density_level"],
                "timestamp": camera["timestamp"],
                "frame_available": camera_frame_available(camera_id),
                "source": "synthetic",
            }
        )

    return {
        "cameras": normalized_cameras[:CCTV_NEIGHBORHOOD_CAMERA_LIMIT],
        "avg_pedestrians": entry["avg_pedestrians"],
        "avg_vehicles": entry["avg_vehicles"],
        "density": entry["density"],
    }


def _flatten_synthetic_cctv() -> dict[str, dict]:
    flattened: dict[str, dict] = {}
    for neighborhood in load_synthetic_cctv():
        entry = synthetic_cctv_entry(neighborhood)
        if entry is None:
            continue
        mapped = _build_synthetic_neighborhood_payload(entry)
        for idx, camera in enumerate(mapped["cameras"]):
            key = str(camera["camera_id"])
            if key in flattened:
                key = f"{key}:{neighborhood.lower().replace(' ', '_')}:{idx}"
            flattened[key] = camera
    return flattened


async def load_cctv_latest_index() -> dict[str, dict]:
    start = time.perf_counter()
    if not ENABLE_CCTV_ANALYSIS:
        try:
            await volume.reload.aio()
        except Exception as exc:
            print(f"cctv_disabled_reload_warning: {exc}")
        return _flatten_synthetic_cctv()

    try:
        await volume.reload.aio()
    except Exception as exc:
        print(f"cctv_index_reload_warning: {exc}")
        return {}

    if not CCTV_LATEST_INDEX_PATH.exists():
        print(f"cctv_index_missing: {CCTV_LATEST_INDEX_PATH}")
        return {}

    index_age_seconds = max(0.0, time.time() - CCTV_LATEST_INDEX_PATH.stat().st_mtime)
    await maybe_spawn_cctv_refresh(index_age_seconds)

    cache_key = f"cctv:latest_index:{int(CCTV_LATEST_INDEX_PATH.stat().st_mtime)}"

    def _loader() -> dict[str, dict]:
        parsed = load_json_file(CCTV_LATEST_INDEX_PATH, default=None)
        if parsed is None:
            print("cctv_index_corrupt: failed to parse latest index")
            return {}

        if not isinstance(parsed, dict):
            print("cctv_index_invalid: expected JSON object")
            return {}

        normalized: dict[str, dict] = {}
        bad_entries = 0
        for cam_id, payload in parsed.items():
            if not isinstance(payload, dict):
                bad_entries += 1
                continue
            cid = str(payload.get("camera_id", cam_id) or "").strip()
            if not cid:
                bad_entries += 1
                continue
            normalized[cid] = payload
        if bad_entries:
            print(f"cctv_index_bad_entries={bad_entries}")
        return normalized

    try:
        return copy.deepcopy(cache.get_or_set(cache_key, 10.0, _loader))
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        print(f"cctv_index_load_ms={elapsed_ms:.1f}")


async def load_cctv_for_neighborhood(name: str) -> dict:
    if not ENABLE_CCTV_ANALYSIS:
        try:
            await volume.reload.aio()
        except Exception as exc:
            print(f"cctv_disabled_reload_warning: {exc}")
        synthetic_entry = synthetic_cctv_entry(name)
        if synthetic_entry is None:
            return empty_cctv_payload()
        return _build_synthetic_neighborhood_payload(synthetic_entry)

    import math

    start = time.perf_counter()
    fake_entry = synthetic_cctv_entry(name)
    latest_by_cam = await load_cctv_latest_index()
    if not latest_by_cam:
        if fake_entry is not None:
            print("cctv_neighborhood_fallback", {"name": name, "source": "synthetic_only_no_index", "camera_count": len(fake_entry["cameras"])})
            return {
                "cameras": fake_entry["cameras"],
                "avg_pedestrians": fake_entry["avg_pedestrians"],
                "avg_vehicles": fake_entry["avg_vehicles"],
                "density": fake_entry["density"],
            }
        return empty_cctv_payload()

    centroid = NEIGHBORHOOD_CENTROIDS.get(name)
    if not centroid:
        return empty_cctv_payload()

    clat, clng = centroid
    cameras = []
    for cam_id, data in latest_by_cam.items():
        try:
            lat = float(data.get("lat", 0) or 0)
            lng = float(data.get("lng", 0) or 0)
        except (TypeError, ValueError):
            continue
        if not lat:
            continue

        radius = 6371
        dlat = math.radians(lat - clat)
        dlon = math.radians(lng - clng)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(clat)) * math.cos(math.radians(lat)) * math.sin(dlon / 2) ** 2
        )
        dist = radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        if dist < 10:
            cameras.append(
                {
                    "camera_id": cam_id,
                    "lat": lat,
                    "lng": lng,
                    "distance_km": round(dist, 2),
                    "pedestrians": data.get("pedestrians", 0),
                    "vehicles": data.get("vehicles", 0),
                    "bicycles": data.get("bicycles", 0),
                    "density_level": data.get("density_level", "unknown"),
                    "timestamp": data.get("timestamp", ""),
                    "_ts_epoch": analysis_timestamp_epoch(data, fallback_mtime=0.0),
                }
            )

    if not cameras:
        if fake_entry is not None:
            print("cctv_neighborhood_fallback", {"name": name, "source": "synthetic_only_no_nearby_real", "camera_count": len(fake_entry["cameras"])})
            return {
                "cameras": fake_entry["cameras"],
                "avg_pedestrians": fake_entry["avg_pedestrians"],
                "avg_vehicles": fake_entry["avg_vehicles"],
                "density": fake_entry["density"],
            }
        return empty_cctv_payload()

    cameras.sort(key=lambda cam: (cam["distance_km"], -cam.get("_ts_epoch", 0.0), cam["camera_id"]))
    selected_cameras = cameras[:CCTV_NEIGHBORHOOD_CAMERA_LIMIT]
    for cam in selected_cameras:
        cam.pop("_ts_epoch", None)

    if fake_entry is not None:
        fake_cams = fake_entry["cameras"]
        for idx, cam in enumerate(selected_cameras):
            fc = fake_cams[idx % len(fake_cams)] if fake_cams else {}
            cam["pedestrians"] = fc.get("pedestrians", cam["pedestrians"])
            cam["vehicles"] = fc.get("vehicles", cam["vehicles"])
            cam["bicycles"] = fc.get("bicycles", cam["bicycles"])
            cam["density_level"] = fc.get("density_level", cam["density_level"])

        avg_p = fake_entry["avg_pedestrians"]
        avg_v = fake_entry["avg_vehicles"]
        density = fake_entry["density"]
    else:
        avg_p = sum(cam["pedestrians"] for cam in selected_cameras) / len(selected_cameras)
        avg_v = sum(cam["vehicles"] for cam in selected_cameras) / len(selected_cameras)
        density = "high" if avg_p > 20 else "medium" if avg_p > 5 else "low"

    elapsed_ms = (time.perf_counter() - start) * 1000
    print(
        "cctv_neighborhood_select",
        {
            "name": name,
            "selected": len(selected_cameras),
            "candidate_count": len(cameras),
            "elapsed_ms": round(elapsed_ms, 1),
        },
    )

    return {
        "cameras": selected_cameras,
        "avg_pedestrians": round(avg_p, 1),
        "avg_vehicles": round(avg_v, 1),
        "density": density,
    }


async def aggregate_timeseries_for_neighborhood(name: str, camera_ids: list[str] | None = None) -> dict:
    from zoneinfo import ZoneInfo

    if not ENABLE_CCTV_ANALYSIS:
        synthetic_entry = synthetic_cctv_entry(name)
        if synthetic_entry and isinstance(synthetic_entry.get("timeseries"), dict):
            return synthetic_entry["timeseries"]
        return {"hours": [], "peak_hour": 0, "peak_pedestrians": 0, "camera_count": 0}

    fake = load_synthetic_cctv()
    if name in fake and fake[name].get("timeseries"):
        print("cctv_timeseries_source", {"name": name, "source": "fake"})
        return fake[name]["timeseries"]

    if camera_ids is None:
        volume.reload()
        cctv_data = await load_cctv_for_neighborhood(name)
        camera_ids = [camera["camera_id"] for camera in cctv_data.get("cameras", [])]
    if not camera_ids:
        return {"hours": [], "peak_hour": 0, "peak_pedestrians": 0, "camera_count": 0}

    ts_dir = Path(PROCESSED_DATA_PATH) / "cctv" / "timeseries"
    if not ts_dir.exists():
        return {"hours": [], "peak_hour": 0, "peak_pedestrians": 0, "camera_count": len(camera_ids)}

    chicago_tz = ZoneInfo("America/Chicago")
    hourly: dict[int, list[dict]] = {hour: [] for hour in range(24)}
    for cam_id in camera_ids:
        ts_path = ts_dir / f"{cam_id}.json"
        entries = load_json_file(ts_path, default=None)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            ts_str = entry.get("timestamp", "")
            if not ts_str:
                continue
            try:
                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                local_hour = dt.astimezone(chicago_tz).hour
                hourly[local_hour].append(entry)
            except Exception:
                continue

    hours = []
    for hour in range(24):
        entries = hourly[hour]
        if entries:
            avg_p = sum(entry.get("pedestrians", 0) for entry in entries) / len(entries)
            avg_v = sum(entry.get("vehicles", 0) for entry in entries) / len(entries)
            density = "high" if avg_p > 20 else "medium" if avg_p > 5 else "low"
            hours.append(
                {
                    "hour": hour,
                    "avg_pedestrians": round(avg_p, 1),
                    "avg_vehicles": round(avg_v, 1),
                    "density": density,
                    "sample_count": len(entries),
                }
            )
        else:
            hours.append(
                {
                    "hour": hour,
                    "avg_pedestrians": 0,
                    "avg_vehicles": 0,
                    "density": "low",
                    "sample_count": 0,
                }
            )

    peak = max(hours, key=lambda bucket: bucket["avg_pedestrians"])
    return {
        "hours": hours,
        "peak_hour": peak["hour"],
        "peak_pedestrians": peak["avg_pedestrians"],
        "camera_count": len(camera_ids),
    }


def load_parking_for_neighborhood(name: str) -> dict | None:
    volume.reload()
    analysis_dir = Path(PROCESSED_DATA_PATH) / "parking" / "analysis"
    if not analysis_dir.exists():
        return None

    slug = name.lower().replace(" ", "_")
    candidates = sorted(analysis_dir.glob(f"{slug}_*.json"), reverse=True)
    if not candidates:
        return None
    return load_json_file(candidates[0], default=None)
