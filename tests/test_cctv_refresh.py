from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from modal_app.api.services import cctv as cctv_service
from modal_app.api.routes import analysis as analysis_routes
from modal_app.api.routes import core as core_routes
from modal_app.api.routes import vision as vision_routes


class _DummyReload:
    async def aio(self):
        return None


class _DummyVolume:
    reload = _DummyReload()


def _synthetic_cctv_payload(camera_id: str = "synth-loop-1") -> dict:
    return {
        "Loop": {
            "cameras": {
                "cameras": [
                    {
                        "camera_id": camera_id,
                        "lat": 41.8819,
                        "lng": -87.6278,
                        "distance_km": 0.4,
                        "pedestrians": 18,
                        "vehicles": 35,
                        "bicycles": 2,
                        "density_level": "medium",
                        "timestamp": "2026-04-13T00:00:00+00:00",
                    }
                ],
                "avg_pedestrians": 18.0,
                "avg_vehicles": 35.0,
                "density": "medium",
            },
            "timeseries": {
                "hours": [
                    {
                        "hour": 8,
                        "avg_pedestrians": 18.0,
                        "avg_vehicles": 35.0,
                        "density": "medium",
                        "sample_count": 1,
                    }
                ],
                "peak_hour": 17,
                "peak_pedestrians": 18.0,
                "camera_count": 1,
            },
        }
    }


def test_load_cctv_latest_index_triggers_refresh_when_stale(tmp_path, monkeypatch) -> None:
    index_path = tmp_path / "latest_by_camera.json"
    index_path.write_text(json.dumps({"cam-1": {"camera_id": "cam-1", "timestamp": "2026-03-03T00:00:00+00:00"}}))

    stale_now = 1_000_000.0
    stale_mtime = stale_now - cctv_service.CCTV_STALE_AFTER_SECONDS - 30

    triggered: list[float] = []

    async def _fake_refresh(age_seconds: float) -> None:
        triggered.append(age_seconds)

    monkeypatch.setattr(cctv_service, "volume", _DummyVolume())
    monkeypatch.setattr(cctv_service, "CCTV_LATEST_INDEX_PATH", index_path)
    monkeypatch.setattr(cctv_service, "maybe_spawn_cctv_refresh", _fake_refresh)
    monkeypatch.setattr(cctv_service.time, "time", lambda: stale_now)
    index_path.touch()
    import os
    os.utime(index_path, (stale_mtime, stale_mtime))

    payload = asyncio.run(cctv_service.load_cctv_latest_index())

    assert payload["cam-1"]["camera_id"] == "cam-1"
    assert len(triggered) == 1
    assert triggered[0] > cctv_service.CCTV_STALE_AFTER_SECONDS


def test_load_cctv_latest_index_skips_refresh_when_fresh(tmp_path, monkeypatch) -> None:
    index_path = tmp_path / "latest_by_camera.json"
    index_path.write_text(json.dumps({"cam-1": {"camera_id": "cam-1", "timestamp": "2026-03-03T00:00:00+00:00"}}))

    fresh_now = 2_000_000.0
    fresh_mtime = fresh_now - 60

    triggered: list[float] = []

    async def _fake_refresh(age_seconds: float) -> None:
        triggered.append(age_seconds)

    monkeypatch.setattr(cctv_service, "volume", _DummyVolume())
    monkeypatch.setattr(cctv_service, "CCTV_LATEST_INDEX_PATH", index_path)
    monkeypatch.setattr(cctv_service, "maybe_spawn_cctv_refresh", _fake_refresh)
    monkeypatch.setattr(cctv_service.time, "time", lambda: fresh_now)
    index_path.touch()
    import os
    os.utime(index_path, (fresh_mtime, fresh_mtime))

    payload = asyncio.run(cctv_service.load_cctv_latest_index())

    assert payload["cam-1"]["camera_id"] == "cam-1"
    assert triggered == [60.0]


def test_maybe_spawn_cctv_refresh_debounces(monkeypatch) -> None:
    store = {"value": 0.0}
    spawn_count = {"value": 0}
    now_values = iter([1000.0, 1005.0])

    async def _fake_get(_key: str, default: float = 0.0) -> float:
        return store["value"] if store["value"] else default

    async def _fake_put(_key: str, value: float) -> None:
        store["value"] = value

    class _FakeSpawn:
        async def aio(self):
            spawn_count["value"] += 1

    monkeypatch.setattr(cctv_service, "_dict_get_float", _fake_get)
    monkeypatch.setattr(cctv_service, "_dict_put_value", _fake_put)
    monkeypatch.setattr(cctv_service, "get_modal_function", lambda _name: SimpleNamespace(spawn=_FakeSpawn()))
    monkeypatch.setattr(cctv_service.time, "time", lambda: next(now_values))

    asyncio.run(cctv_service.maybe_spawn_cctv_refresh(cctv_service.CCTV_STALE_AFTER_SECONDS + 1))
    asyncio.run(cctv_service.maybe_spawn_cctv_refresh(cctv_service.CCTV_STALE_AFTER_SECONDS + 1))

    assert spawn_count["value"] == 1
    assert store["value"] == 1000.0


def test_aggregate_timeseries_returns_synthetic_data_when_analysis_disabled(monkeypatch) -> None:
    monkeypatch.setattr(cctv_service, "ENABLE_CCTV_ANALYSIS", False)
    monkeypatch.setattr(cctv_service, "load_synthetic_cctv", _synthetic_cctv_payload)

    payload = asyncio.run(cctv_service.aggregate_timeseries_for_neighborhood("Loop"))

    assert payload["peak_hour"] == 17
    assert payload["camera_count"] == 1


def test_cctv_synthetic_data_contract_when_analysis_disabled(monkeypatch) -> None:
    monkeypatch.setattr(cctv_service, "ENABLE_CCTV_ANALYSIS", False)
    monkeypatch.setattr(cctv_service, "volume", _DummyVolume())
    monkeypatch.setattr(cctv_service, "load_synthetic_cctv", _synthetic_cctv_payload)

    neighborhood_payload = asyncio.run(cctv_service.load_cctv_for_neighborhood("Loop"))
    latest_index = asyncio.run(cctv_service.load_cctv_latest_index())

    assert neighborhood_payload["avg_pedestrians"] == 18.0
    assert neighborhood_payload["avg_vehicles"] == 35.0
    assert neighborhood_payload["density"] == "medium"
    assert neighborhood_payload["cameras"][0]["source"] == "synthetic"
    assert latest_index["synth-loop-1"]["camera_id"] == "synth-loop-1"
    assert latest_index["synth-loop-1"]["pedestrians"] == 18
    assert latest_index["synth-loop-1"]["frame_available"] is False


def test_load_cctv_for_neighborhood_marks_synthetic_camera_frame_available_when_snapshot_exists(tmp_path, monkeypatch) -> None:
    raw_dir = tmp_path / "raw" / "cctv" / "frames"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "synth-loop-1_20260413_0100.jpg").write_bytes(b"\xff\xd8raw-frame")

    monkeypatch.setattr(cctv_service, "ENABLE_CCTV_ANALYSIS", False)
    monkeypatch.setattr(cctv_service, "volume", _DummyVolume())
    monkeypatch.setattr(cctv_service, "RAW_DATA_PATH", str(tmp_path / "raw"))
    monkeypatch.setattr(cctv_service, "PROCESSED_DATA_PATH", str(tmp_path / "processed"))
    monkeypatch.setattr(cctv_service, "load_synthetic_cctv", _synthetic_cctv_payload)

    payload = asyncio.run(cctv_service.load_cctv_for_neighborhood("Loop"))

    assert payload["cameras"][0]["frame_available"] is True
    assert payload["cameras"][0]["source"] == "synthetic"


def test_cctv_frame_falls_back_to_raw_frames_when_analysis_disabled(tmp_path, monkeypatch) -> None:
    raw_dir = tmp_path / "raw" / "cctv" / "frames"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_frame = raw_dir / "cam-1_20260413_0100.jpg"
    raw_frame.write_bytes(b"\xff\xd8raw-frame")

    monkeypatch.setattr(vision_routes, "ENABLE_CCTV_ANALYSIS", False)
    monkeypatch.setattr(vision_routes, "RAW_DATA_PATH", str(tmp_path / "raw"))
    monkeypatch.setattr(vision_routes, "PROCESSED_DATA_PATH", str(tmp_path / "processed"))
    monkeypatch.setattr(vision_routes.volume, "reload", lambda: None)

    response = asyncio.run(vision_routes.cctv_frame("cam-1"))

    assert response.status_code == 200
    assert response.media_type == "image/jpeg"
    assert response.body == b"\xff\xd8raw-frame"


def test_runtime_status_and_metrics_disable_cctv_gpu(monkeypatch) -> None:
    def _raise_modal_dict_unavailable(*args, **kwargs):
        raise RuntimeError

    monkeypatch.setattr(core_routes, "ENABLE_CCTV_ANALYSIS", False)
    monkeypatch.setattr(analysis_routes, "ENABLE_CCTV_ANALYSIS", False)
    monkeypatch.setattr(core_routes.modal.Dict, "from_name", _raise_modal_dict_unavailable)
    monkeypatch.setattr(analysis_routes, "PROCESSED_DATA_PATH", "/tmp/alethia-test-missing-processed")

    status_payload = asyncio.run(core_routes.status())
    metrics_payload = asyncio.run(analysis_routes.gpu_metrics())

    assert status_payload["gpu_status"]["t4_cctv"] == "disabled"
    assert metrics_payload["t4_cctv"]["status"] == "disabled"
