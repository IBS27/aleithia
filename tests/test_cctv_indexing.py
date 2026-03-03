import asyncio
import json

from modal_app.common import NEIGHBORHOOD_CENTROIDS
from modal_app.pipelines import cctv
from modal_app import web


def test_update_cctv_latest_index_merges_and_keeps_newest(tmp_path, monkeypatch) -> None:
    index_path = tmp_path / "latest_by_camera.json"
    monkeypatch.setattr(cctv, "CCTV_INDEX_DIR", tmp_path)
    monkeypatch.setattr(cctv, "CCTV_LATEST_INDEX_PATH", index_path)

    existing = {
        "cam-a": {
            "camera_id": "cam-a",
            "lat": 41.88,
            "lng": -87.63,
            "timestamp": "2026-03-02T00:00:00+00:00",
            "vehicles": 10,
        },
        "cam-b": {
            "camera_id": "cam-b",
            "lat": 41.89,
            "lng": -87.64,
            "timestamp": "2026-03-02T00:00:00+00:00",
            "vehicles": 20,
        },
    }
    index_path.write_text(json.dumps(existing))

    results = [
        {
            "camera_id": "cam-a",
            "pedestrians": 2,
            "vehicles": 99,
            "bicycles": 1,
            "density_level": "medium",
            "timestamp": "2026-03-03T01:00:00+00:00",
            "annotated_path": "/tmp/a.jpg",
        },
        {
            "camera_id": "cam-c",
            "pedestrians": 1,
            "vehicles": 7,
            "bicycles": 0,
            "density_level": "low",
            "timestamp": "2026-03-03T01:05:00+00:00",
            "annotated_path": "/tmp/c.jpg",
        },
    ]
    meta_by_camera = {
        "cam-a": {"lat": 41.90, "lng": -87.60, "location": "A", "direction": "N"},
        "cam-c": {"lat": 41.91, "lng": -87.61, "location": "C", "direction": "S"},
    }

    stats = cctv._update_cctv_latest_index(results, meta_by_camera)
    merged = json.loads(index_path.read_text())

    assert stats == {"updated": 2, "total": 3}
    assert merged["cam-b"]["camera_id"] == "cam-b"
    assert merged["cam-a"]["vehicles"] == 99
    assert merged["cam-a"]["lat"] == 41.9
    assert merged["cam-c"]["location"] == "C"


def test_load_cctv_latest_index_handles_missing_and_corrupt(tmp_path, monkeypatch) -> None:
    class _DummyReload:
        async def aio(self):
            return None

    class _DummyVolume:
        reload = _DummyReload()

    monkeypatch.setattr(web, "volume", _DummyVolume())
    monkeypatch.setattr(web, "CCTV_LATEST_INDEX_PATH", tmp_path / "latest_by_camera.json")

    assert asyncio.run(web._load_cctv_latest_index()) == {}

    (tmp_path / "latest_by_camera.json").write_text("{bad json")
    assert asyncio.run(web._load_cctv_latest_index()) == {}


def test_load_cctv_for_neighborhood_is_capped_and_stable(monkeypatch) -> None:
    clat, clng = NEIGHBORHOOD_CENTROIDS["Loop"]
    index_data = {}
    for i in range(30):
        cid = f"cam{i:02d}"
        index_data[cid] = {
            "camera_id": cid,
            "lat": clat + (i * 0.001),
            "lng": clng,
            "pedestrians": i,
            "vehicles": i * 2,
            "bicycles": 0,
            "density_level": "low",
            "timestamp": f"2026-03-03T00:{i:02d}:00+00:00",
        }

    async def _fake_index():
        return index_data

    monkeypatch.setattr(web, "_load_cctv_latest_index", _fake_index)
    monkeypatch.setattr(web, "_fake_cctv_entry", lambda _: None)

    payload = asyncio.run(web._load_cctv_for_neighborhood("Loop"))
    ids = [c["camera_id"] for c in payload["cameras"]]

    assert len(ids) == web.CCTV_NEIGHBORHOOD_CAMERA_LIMIT
    assert ids == [f"cam{i:02d}" for i in range(web.CCTV_NEIGHBORHOOD_CAMERA_LIMIT)]


def test_load_cctv_for_neighborhood_real_only_uses_real_summary(monkeypatch) -> None:
    clat, clng = NEIGHBORHOOD_CENTROIDS["Loop"]
    index_data = {
        "cam-a": {
            "camera_id": "cam-a",
            "lat": clat,
            "lng": clng,
            "pedestrians": 10,
            "vehicles": 30,
            "bicycles": 1,
            "density_level": "low",
            "timestamp": "2026-03-03T00:00:00+00:00",
        },
        "cam-b": {
            "camera_id": "cam-b",
            "lat": clat + 0.001,
            "lng": clng,
            "pedestrians": 30,
            "vehicles": 50,
            "bicycles": 2,
            "density_level": "high",
            "timestamp": "2026-03-03T00:01:00+00:00",
        },
    }

    async def _fake_index():
        return index_data

    monkeypatch.setattr(web, "_load_cctv_latest_index", _fake_index)
    monkeypatch.setattr(web, "_fake_cctv_entry", lambda _: None)

    payload = asyncio.run(web._load_cctv_for_neighborhood("Loop"))

    assert [c["camera_id"] for c in payload["cameras"]] == ["cam-a", "cam-b"]
    assert payload["avg_pedestrians"] == 20.0
    assert payload["avg_vehicles"] == 40.0
    assert payload["density"] == "medium"


def test_load_cctv_for_neighborhood_fake_only_when_no_index(monkeypatch) -> None:
    fake_entry = {
        "cameras": [{
            "camera_id": "fake-loop-1",
            "lat": 41.88,
            "lng": -87.63,
            "distance_km": 0.5,
            "pedestrians": 7,
            "vehicles": 22,
            "bicycles": 1,
            "density_level": "medium",
            "timestamp": "2026-03-03T00:00:00+00:00",
        }],
        "avg_pedestrians": 7.0,
        "avg_vehicles": 22.0,
        "density": "medium",
        "has_timeseries": True,
    }

    async def _fake_index():
        return {}

    monkeypatch.setattr(web, "_load_cctv_latest_index", _fake_index)
    monkeypatch.setattr(web, "_fake_cctv_entry", lambda _: fake_entry)

    payload = asyncio.run(web._load_cctv_for_neighborhood("Loop"))

    assert payload["cameras"][0]["camera_id"] == "fake-loop-1"
    assert payload["avg_pedestrians"] == 7.0
    assert payload["avg_vehicles"] == 22.0
    assert payload["density"] == "medium"


def test_load_cctv_for_neighborhood_real_plus_fake_preserves_real_camera_ids(monkeypatch) -> None:
    clat, clng = NEIGHBORHOOD_CENTROIDS["Loop"]
    index_data = {
        "real-cam-1": {
            "camera_id": "real-cam-1",
            "lat": clat,
            "lng": clng,
            "pedestrians": 100,
            "vehicles": 100,
            "bicycles": 100,
            "density_level": "high",
            "timestamp": "2026-03-03T00:00:00+00:00",
        },
        "real-cam-2": {
            "camera_id": "real-cam-2",
            "lat": clat + 0.001,
            "lng": clng,
            "pedestrians": 100,
            "vehicles": 100,
            "bicycles": 100,
            "density_level": "high",
            "timestamp": "2026-03-03T00:01:00+00:00",
        },
    }
    fake_entry = {
        "cameras": [{
            "camera_id": "fake-loop-1",
            "lat": 41.88,
            "lng": -87.63,
            "distance_km": 0.5,
            "pedestrians": 3,
            "vehicles": 9,
            "bicycles": 1,
            "density_level": "low",
            "timestamp": "2026-03-03T00:00:00+00:00",
        }],
        "avg_pedestrians": 3.0,
        "avg_vehicles": 9.0,
        "density": "low",
        "has_timeseries": True,
    }

    async def _fake_index():
        return index_data

    monkeypatch.setattr(web, "_load_cctv_latest_index", _fake_index)
    monkeypatch.setattr(web, "_fake_cctv_entry", lambda _: fake_entry)

    payload = asyncio.run(web._load_cctv_for_neighborhood("Loop"))

    assert [c["camera_id"] for c in payload["cameras"]] == ["real-cam-1", "real-cam-2"]
    assert payload["cameras"][0]["vehicles"] == 9
    assert payload["cameras"][1]["vehicles"] == 9
    assert payload["avg_pedestrians"] == 3.0
    assert payload["avg_vehicles"] == 9.0
    assert payload["density"] == "low"


def test_load_cctv_for_neighborhood_returns_empty_when_no_real_or_fake(monkeypatch) -> None:
    async def _fake_index():
        return {}

    monkeypatch.setattr(web, "_load_cctv_latest_index", _fake_index)
    monkeypatch.setattr(web, "_fake_cctv_entry", lambda _: None)

    payload = asyncio.run(web._load_cctv_for_neighborhood("Loop"))

    assert payload == {"cameras": [], "avg_pedestrians": 0, "avg_vehicles": 0, "density": "unknown"}


def test_cctv_latest_uses_index_payload(monkeypatch) -> None:
    async def _fake_index():
        return {
            "cam1": {"camera_id": "cam1", "timestamp": "2026-03-03T01:00:00+00:00"},
            "cam2": {"camera_id": "cam2", "timestamp": "2026-03-03T02:00:00+00:00"},
        }

    monkeypatch.setattr(web, "_load_cctv_latest_index", _fake_index)
    payload = asyncio.run(web.cctv_latest())

    assert payload["count"] == 2
    assert payload["cameras"][0]["camera_id"] == "cam2"


def test_aggregate_timeseries_prefers_fake_when_available(monkeypatch) -> None:
    fake_timeseries = {
        "hours": [{"hour": 12, "avg_pedestrians": 42, "avg_vehicles": 17, "density": "high", "sample_count": 4}],
        "peak_hour": 12,
        "peak_pedestrians": 42,
        "camera_count": 4,
    }
    fake_payload = {"Loop": {"timeseries": fake_timeseries}}
    monkeypatch.setattr(web, "_load_fake_cctv", lambda: fake_payload)

    result = asyncio.run(web._aggregate_timeseries_for_neighborhood("Loop", camera_ids=["cam-a"]))

    assert result == fake_timeseries
