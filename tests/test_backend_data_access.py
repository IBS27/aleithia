from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import shared_data
from routes.data_routes import router as data_router


def _write_json(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload)


def _make_client(monkeypatch, data_root: Path) -> TestClient:
    monkeypatch.setenv("ALEITHIA_DATA_ROOT", str(data_root))
    monkeypatch.delenv("ALEITHIA_RAW_DATA_DIR", raising=False)
    monkeypatch.delenv("ALEITHIA_PROCESSED_DATA_DIR", raising=False)
    shared_data._LAST_LOGGED_LAYOUT = None

    app = FastAPI()
    app.include_router(data_router, prefix="/api/data")
    return TestClient(app)


def test_shared_data_resolution_prefers_env_over_detected_layout(tmp_path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    backend_root = repo_root / "backend"
    canonical_raw = repo_root / "data" / "raw"
    canonical_processed = repo_root / "data" / "processed"
    explicit_raw = tmp_path / "external" / "raw"
    explicit_processed = tmp_path / "external" / "processed"

    canonical_raw.mkdir(parents=True)
    canonical_processed.mkdir(parents=True)
    explicit_raw.mkdir(parents=True)
    explicit_processed.mkdir(parents=True)

    monkeypatch.setattr(shared_data, "REPO_ROOT", repo_root)
    monkeypatch.setattr(shared_data, "BACKEND_ROOT", backend_root)
    monkeypatch.setenv("ALEITHIA_RAW_DATA_DIR", str(explicit_raw))
    monkeypatch.setenv("ALEITHIA_PROCESSED_DATA_DIR", str(explicit_processed))
    monkeypatch.delenv("ALEITHIA_DATA_ROOT", raising=False)
    shared_data._LAST_LOGGED_LAYOUT = None

    assert shared_data.get_raw_data_dir() == explicit_raw.resolve()
    assert shared_data.get_processed_data_dir() == explicit_processed.resolve()


def test_shared_data_default_resolution_uses_repo_data_root(tmp_path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    backend_root = repo_root / "backend"
    canonical_raw = repo_root / "data" / "raw"
    canonical_processed = repo_root / "data" / "processed"
    legacy_backend_raw = backend_root / "data" / "raw"
    legacy_backend_processed = backend_root / "data" / "processed"

    canonical_raw.mkdir(parents=True)
    canonical_processed.mkdir(parents=True)
    legacy_backend_raw.mkdir(parents=True)
    legacy_backend_processed.mkdir(parents=True)

    monkeypatch.setattr(shared_data, "REPO_ROOT", repo_root)
    monkeypatch.setattr(shared_data, "BACKEND_ROOT", backend_root)
    monkeypatch.delenv("ALEITHIA_DATA_ROOT", raising=False)
    monkeypatch.delenv("ALEITHIA_RAW_DATA_DIR", raising=False)
    monkeypatch.delenv("ALEITHIA_PROCESSED_DATA_DIR", raising=False)
    shared_data._LAST_LOGGED_LAYOUT = None

    assert shared_data.get_raw_data_dir() == canonical_raw.resolve()
    assert shared_data.get_processed_data_dir() == canonical_processed.resolve()


def test_load_raw_docs_recurses_and_skips_invalid_payloads(tmp_path, monkeypatch) -> None:
    data_root = tmp_path / "shared"
    monkeypatch.setenv("ALEITHIA_DATA_ROOT", str(data_root))
    monkeypatch.delenv("ALEITHIA_RAW_DATA_DIR", raising=False)
    monkeypatch.delenv("ALEITHIA_PROCESSED_DATA_DIR", raising=False)
    shared_data._LAST_LOGGED_LAYOUT = None

    _write_json(
        data_root / "raw" / "news" / "2026-03-17" / "latest.json",
        '{"id":"latest","title":"Latest","timestamp":"2026-03-17T12:00:00+00:00"}',
    )
    _write_json(
        data_root / "raw" / "news" / "2026-03-16" / "older.json",
        '{"id":"older","title":"Older","timestamp":"2026-03-16T12:00:00+00:00"}',
    )
    _write_json(data_root / "raw" / "news" / "2026-03-16" / "broken.json", '{"id":')
    _write_json(data_root / "raw" / "news" / "2026-03-16" / "list.json", '["not", "a", "dict"]')

    assert shared_data.count_raw_json_files("news") == 4
    docs = shared_data.load_raw_docs("news")

    assert [doc["id"] for doc in docs] == ["latest", "older"]


def test_backend_routes_read_shared_raw_and_processed_data(tmp_path, monkeypatch) -> None:
    data_root = tmp_path / "shared"
    client = _make_client(monkeypatch, data_root)

    _write_json(
        data_root / "raw" / "news" / "2026-03-17" / "news.json",
        """
        {
          "id": "news-1",
          "title": "Loop storefront demand rises",
          "content": "Loop businesses are seeing more foot traffic.",
          "timestamp": "2026-03-17T12:00:00+00:00",
          "geo": {"neighborhood": "Loop"}
        }
        """.strip(),
    )
    _write_json(
        data_root / "raw" / "politics" / "2026-03-17" / "policy.json",
        """
        {
          "id": "pol-1",
          "title": "Loop zoning update",
          "content": "New permit requirements affect Loop corridors.",
          "timestamp": "2026-03-17T08:00:00+00:00",
          "geo": {"neighborhood": "Loop"}
        }
        """.strip(),
    )
    _write_json(
        data_root / "raw" / "public_data" / "2026-03-17" / "inspection.json",
        """
        {
          "id": "insp-1",
          "title": "Cafe inspection",
          "content": "Inspection in Loop",
          "metadata": {
            "dataset": "food_inspections",
            "raw_record": {
              "results": "Fail",
              "address": "123 Loop Ave",
              "community_area_name": "Loop"
            }
          },
          "geo": {"neighborhood": "Loop"}
        }
        """.strip(),
    )
    _write_json(
        data_root / "raw" / "reddit" / "2026-03-17" / "post.json",
        """
        {
          "id": "reddit-1",
          "title": "Loop coffee shops",
          "content": "People want more late-night cafes.",
          "geo": {"neighborhood": "Loop"}
        }
        """.strip(),
    )
    _write_json(
        data_root / "processed" / "geo" / "neighborhood_metrics.json",
        """
        {
          "type": "FeatureCollection",
          "features": [
            {
              "type": "Feature",
              "properties": {
                "neighborhood": "Loop",
                "population": 5000
              }
            }
          ]
        }
        """.strip(),
    )
    _write_json(
        data_root / "processed" / "summaries" / "news_summary.json",
        '{"headline_count": 1}',
    )
    _write_json(
        data_root / "processed" / "cctv" / "synthetic_analytics.json",
        """
        {
          "Loop": {
            "cameras": {"active_cameras": 3},
            "timeseries": {
              "peak_hour": 17,
              "peak_pedestrians": 120,
              "hours": []
            }
          }
        }
        """.strip(),
    )

    sources = client.get("/api/data/sources")
    assert sources.status_code == 200
    assert sources.json()["news"] == {"count": 1, "active": True}
    assert sources.json()["reddit"] == {"count": 1, "active": True}

    news = client.get("/api/data/news")
    assert news.status_code == 200
    assert [doc["id"] for doc in news.json()] == ["news-1"]

    summary = client.get("/api/data/summary")
    assert summary.status_code == 200
    assert summary.json() == {"news": {"headline_count": 1}}

    geo = client.get("/api/data/geo")
    assert geo.status_code == 200
    assert geo.json()["features"][0]["properties"]["neighborhood"] == "Loop"

    cctv = client.get("/api/data/cctv/timeseries/Loop")
    assert cctv.status_code == 200
    assert cctv.json()["peak_hour"] == 17

    neighborhood = client.get("/api/data/neighborhood/Loop")
    assert neighborhood.status_code == 200
    payload = neighborhood.json()
    assert payload["metrics"]["population"] == 5000
    assert payload["inspection_stats"]["failed"] == 1
    assert payload["news"][0]["id"] == "news-1"
    assert payload["politics"][0]["id"] == "pol-1"
    assert payload["cctv"]["peak_hour"] == 17


def test_backend_routes_do_not_read_fixture_tree(tmp_path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    backend_root = repo_root / "backend"
    fixture_root = repo_root / "fixtures" / "demo_data"

    _write_json(
        fixture_root / "processed" / "geo" / "neighborhood_metrics.json",
        '{"type":"FeatureCollection","features":[{"type":"Feature","properties":{"neighborhood":"Fixture Loop"}}]}',
    )
    _write_json(
        fixture_root / "processed" / "summaries" / "news_summary.json",
        '{"headline_count": 99}',
    )

    monkeypatch.setattr(shared_data, "REPO_ROOT", repo_root)
    monkeypatch.setattr(shared_data, "BACKEND_ROOT", backend_root)
    monkeypatch.delenv("ALEITHIA_DATA_ROOT", raising=False)
    monkeypatch.delenv("ALEITHIA_RAW_DATA_DIR", raising=False)
    monkeypatch.delenv("ALEITHIA_PROCESSED_DATA_DIR", raising=False)
    shared_data._LAST_LOGGED_LAYOUT = None

    app = FastAPI()
    app.include_router(data_router, prefix="/api/data")
    client = TestClient(app)

    geo = client.get("/api/data/geo")
    assert geo.status_code == 200
    assert geo.json() == {"type": "FeatureCollection", "features": []}

    summary = client.get("/api/data/summary")
    assert summary.status_code == 200
    assert summary.json() == {}
