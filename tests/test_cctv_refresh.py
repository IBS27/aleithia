from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from modal_app.api.services import cctv as cctv_service


class _DummyReload:
    async def aio(self):
        return None


class _DummyVolume:
    reload = _DummyReload()


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
