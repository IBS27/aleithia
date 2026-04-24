from __future__ import annotations

import os

from tests.backend_test_helpers import (
    CountingAccessor,
    install_local_accessor,
    make_data_client,
    make_router_client,
    reset_shared_data_state,
    write_json,
)

import shared_data
from routes import data_routes as data_routes_module


def test_backend_routes_read_shared_raw_and_processed_data(tmp_path, monkeypatch) -> None:
    data_root = tmp_path / "shared"
    client = make_data_client(monkeypatch, data_root)

    write_json(
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
    write_json(
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
    write_json(
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
    write_json(
        data_root / "raw" / "reddit" / "2026-03-17" / "post.json",
        '{"id":"reddit-1","title":"Loop coffee shops","content":"People want more late-night cafes.","geo":{"neighborhood":"Loop"}}',
    )
    write_json(
        data_root / "raw" / "reviews" / "2026-03-17" / "review.json",
        '{"id":"review-1","title":"Loop cafe reviews","content":"Customers like the all-day coffee program.","geo":{"neighborhood":"Loop"}}',
    )
    write_json(
        data_root / "raw" / "realestate" / "2026-03-17" / "listing.json",
        '{"id":"realestate-1","title":"Loop retail lease","content":"Retail space available in the Loop.","geo":{"neighborhood":"Loop"}}',
    )
    write_json(
        data_root / "raw" / "tiktok" / "2026-03-17" / "video.json",
        """
        {
          "id": "tiktok-1",
          "title": "TikTok video",
          "content": "12K\\n[Transcript] Loop coffee shops are packed after 6pm.",
          "url": "https://www.tiktok.com/@loopcoffee/video/123",
          "metadata": {"views": "12K"},
          "geo": {"neighborhood": "Loop"}
        }
        """.strip(),
    )
    write_json(
        data_root / "processed" / "geo" / "neighborhood_metrics.json",
        '{"type":"FeatureCollection","features":[{"type":"Feature","properties":{"neighborhood":"Loop","population":5000}}]}',
    )
    write_json(data_root / "processed" / "demographics_summary.json", '{"city_wide":{"total_population":12345}}')
    write_json(
        data_root / "processed" / "cctv" / "synthetic_analytics.json",
        '{"Loop":{"cameras":{"active_cameras":3},"timeseries":{"peak_hour":17,"peak_pedestrians":120,"hours":[]}}}',
    )

    sources = client.get("/api/data/sources")
    assert sources.status_code == 200
    sources_data = sources.json()
    assert sources_data["metadata_ready"] is True
    assert sources_data["sources"]["news"] == {"count": 1, "active": True}
    assert sources_data["sources"]["reddit"] == {"count": 1, "active": True}
    assert sources_data["sources"]["tiktok"] == {"count": 1, "active": True}
    assert sources_data["sources"]["federal_register"] == {"count": 0, "active": False}

    news = client.get("/api/data/news")
    assert news.status_code == 200
    assert [doc["id"] for doc in news.json()] == ["news-1"]

    summary = client.get("/api/data/summary")
    assert summary.status_code == 200
    assert summary.json() == {
        "total_documents": 7,
        "source_counts": {
            "news": 1,
            "politics": 1,
            "federal_register": 0,
            "public_data": 1,
            "demographics": 0,
            "reddit": 1,
            "reviews": 1,
            "realestate": 1,
            "tiktok": 1,
        },
        "demographics": {"total_population": 12345},
    }

    geo = client.get("/api/data/geo")
    assert geo.status_code == 200
    assert geo.json()["features"][0]["properties"]["neighborhood"] == "Loop"

    inspections = client.get("/api/data/inspections")
    assert inspections.status_code == 200
    assert [doc["id"] for doc in inspections.json()] == ["insp-1"]

    reddit = client.get("/api/data/reddit?neighborhood=Loop")
    assert reddit.status_code == 200
    assert [doc["id"] for doc in reddit.json()] == ["reddit-1"]

    reviews = client.get("/api/data/reviews?neighborhood=Loop")
    assert reviews.status_code == 200
    assert [doc["id"] for doc in reviews.json()] == ["review-1"]

    realestate = client.get("/api/data/realestate?neighborhood=Loop")
    assert realestate.status_code == 200
    assert [doc["id"] for doc in realestate.json()] == ["realestate-1"]

    tiktok = client.get("/api/data/tiktok?neighborhood=Loop")
    assert tiktok.status_code == 200
    tiktok_payload = tiktok.json()
    assert [doc["id"] for doc in tiktok_payload] == ["tiktok-1"]
    assert tiktok_payload[0]["title"] == "Loop coffee shops are packed after 6pm"
    assert tiktok_payload[0]["metadata"]["creator"] == "loopcoffee"
    assert tiktok_payload[0]["metadata"]["views_normalized"] == 12000

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


def test_backend_route_snapshot_cache_reuses_scan_results(tmp_path, monkeypatch) -> None:
    data_root = tmp_path / "shared"
    accessor = CountingAccessor(data_root)
    monkeypatch.setattr(shared_data, "_get_accessor", lambda: accessor)
    reset_shared_data_state()

    write_json(data_root / "raw" / "news" / "2026-03-17" / "news.json", '{"id":"news-1","geo":{"neighborhood":"Loop"}}')
    write_json(data_root / "processed" / "enriched" / "doc-1.json", '{"id":"enriched-1"}')

    client = make_router_client()

    sources = client.get("/api/data/sources")
    assert sources.status_code == 200
    assert sources.json()["metadata_ready"] is True
    calls_after_first = len(accessor.list_entries_calls)
    assert calls_after_first > 0

    status = client.get("/api/data/status")
    assert status.status_code == 200
    assert len(accessor.list_entries_calls) == calls_after_first
    assert status.json()["metadata_ready"] is True
    assert status.json()["enriched_docs"] == 1


def test_modal_backed_snapshot_requests_return_cached_or_empty_without_inline_scan(tmp_path, monkeypatch) -> None:
    data_root = tmp_path / "shared"
    accessor = CountingAccessor(data_root)
    accessor._volume = object()
    monkeypatch.setattr(shared_data, "_get_accessor", lambda: accessor)
    reset_shared_data_state()

    scheduled: list[tuple[object, ...]] = []

    def _fake_schedule(cache_key, raw_dir, processed_dir, source_names):
        scheduled.append((cache_key, tuple(source_names)))

    monkeypatch.setattr(data_routes_module, "_schedule_data_snapshot_refresh", _fake_schedule)

    snapshot = data_routes_module._get_data_snapshot(["news", "reddit"])

    assert snapshot["metadata_ready"] is False
    assert snapshot["enriched_docs"] == 0
    assert snapshot["source_stats"]["news"] == {
        "doc_count": 0,
        "active": False,
        "last_update": None,
        "neighborhoods_covered": set(),
    }
    assert snapshot["source_stats"]["reddit"] == {
        "doc_count": 0,
        "active": False,
        "last_update": None,
        "neighborhoods_covered": set(),
    }
    assert scheduled
    assert accessor.list_entries_calls == []


def test_backend_routes_do_not_read_fixture_tree(tmp_path, monkeypatch) -> None:
    data_root = tmp_path / "shared"
    fixture_root = tmp_path / "fixtures" / "demo_data"

    write_json(
        fixture_root / "processed" / "geo" / "neighborhood_metrics.json",
        '{"type":"FeatureCollection","features":[{"type":"Feature","properties":{"neighborhood":"Fixture Loop"}}]}',
    )
    write_json(fixture_root / "processed" / "summaries" / "news_summary.json", '{"headline_count": 99}')

    install_local_accessor(monkeypatch, data_root)
    client = make_router_client()

    geo = client.get("/api/data/geo")
    assert geo.status_code == 200
    assert geo.json() == {"type": "FeatureCollection", "features": []}

    summary = client.get("/api/data/summary")
    assert summary.status_code == 200
    assert summary.json() == {
        "total_documents": 0,
        "source_counts": {
            "news": 0,
            "politics": 0,
            "federal_register": 0,
            "public_data": 0,
            "demographics": 0,
            "reddit": 0,
            "reviews": 0,
            "realestate": 0,
            "tiktok": 0,
        },
        "demographics": {},
    }


def test_backend_status_and_metrics_routes_own_document_freshness(tmp_path, monkeypatch) -> None:
    data_root = tmp_path / "shared"
    client = make_data_client(monkeypatch, data_root)

    write_json(data_root / "raw" / "news" / "2026-03-20" / "recent.json", '{"id":"news-1","geo":{"neighborhood":"Loop"}}')
    write_json(data_root / "raw" / "politics" / "2026-03-18" / "older.json", '{"id":"pol-1","geo":{"neighborhood":"West Loop"}}')
    write_json(data_root / "processed" / "enriched" / "doc-1.json", '{"id":"enriched-1"}')

    os.utime(data_root / "raw" / "news" / "2026-03-20" / "recent.json", (1_742_554_800, 1_742_554_800))
    os.utime(data_root / "raw" / "politics" / "2026-03-18" / "older.json", (1, 1))

    class FrozenDateTime:
        @classmethod
        def now(cls, tz=None):
            from datetime import datetime, timezone

            return datetime(2025, 3, 21, 12, 0, tzinfo=timezone.utc)

        @classmethod
        def fromisoformat(cls, value):
            from datetime import datetime

            return datetime.fromisoformat(value)

    monkeypatch.setattr(data_routes_module, "datetime", FrozenDateTime)

    status = client.get("/api/data/status")
    assert status.status_code == 200
    status_data = status.json()
    assert set(status_data) == {"metadata_ready", "pipelines", "enriched_docs", "total_docs"}
    assert status_data["metadata_ready"] is True
    assert status_data["pipelines"]["news"]["state"] == "idle"
    assert status_data["pipelines"]["politics"]["state"] == "stale"
    assert status_data["pipelines"]["reddit"]["state"] == "no_data"
    assert status_data["enriched_docs"] == 1
    assert status_data["total_docs"] == 2

    metrics = client.get("/api/data/metrics")
    assert metrics.status_code == 200
    assert metrics.json() == {
        "total_documents": 2,
        "active_pipelines": 2,
        "neighborhoods_covered": 0,
        "data_sources": 9,
        "neighborhoods_total": 77,
    }
