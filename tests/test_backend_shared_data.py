from __future__ import annotations

import os

from tests.backend_test_helpers import StrictRecursiveAccessor, install_local_accessor, write_json

import read_helpers
import shared_data


def test_shared_data_resolution_prefers_env_over_detected_layout(tmp_path, monkeypatch) -> None:
    data_root = tmp_path / "shared"
    (data_root / "raw").mkdir(parents=True)
    (data_root / "processed").mkdir(parents=True)
    install_local_accessor(monkeypatch, data_root)

    assert shared_data.get_raw_data_dir().relative_path == "raw"
    assert shared_data.get_processed_data_dir().relative_path == "processed"
    assert str(shared_data.get_raw_data_dir()).startswith("modal://")


def test_load_raw_docs_recurses_and_skips_invalid_payloads(tmp_path, monkeypatch) -> None:
    data_root = tmp_path / "shared"
    install_local_accessor(monkeypatch, data_root)

    write_json(
        data_root / "raw" / "news" / "2026-03-17" / "latest.json",
        '{"id":"latest","title":"Latest","timestamp":"2026-03-17T12:00:00+00:00"}',
    )
    write_json(
        data_root / "raw" / "news" / "2026-03-16" / "older.json",
        '{"id":"older","title":"Older","timestamp":"2026-03-16T12:00:00+00:00"}',
    )
    write_json(data_root / "raw" / "news" / "2026-03-16" / "broken.json", '{"id":')
    write_json(data_root / "raw" / "news" / "2026-03-16" / "list.json", '["not", "a", "dict"]')

    assert shared_data.count_raw_json_files("news") == 4
    docs = shared_data.load_raw_docs("news")

    assert [doc["id"] for doc in docs] == ["latest", "older"]


def test_shared_data_recursive_scans_do_not_requery_child_entries(tmp_path, monkeypatch) -> None:
    data_root = tmp_path / "shared"
    accessor = StrictRecursiveAccessor(data_root)
    monkeypatch.setattr(shared_data, "_get_accessor", lambda: accessor)
    shared_data._LAST_LOGGED_LAYOUT = None
    shared_data._VOLUME = None

    write_json(
        data_root / "raw" / "news" / "2026-03-17" / "latest.json",
        '{"id":"latest","geo":{"neighborhood":"Loop"}}',
    )
    write_json(
        data_root / "raw" / "news" / "2026-03-16" / "older.json",
        '{"id":"older","geo":{"neighborhood":"West Loop"}}',
    )

    news_dir = shared_data.get_raw_data_dir() / "news"
    files = shared_data.iter_json_files(news_dir)
    assert [path.name for path in files] == ["latest.json", "older.json"]

    stats = shared_data.scan_source_directories({"news": news_dir}, neighborhood_sample_limit=2)
    assert stats["news"]["doc_count"] == 2
    assert stats["news"]["active"] is True
    assert stats["news"]["neighborhoods_covered"] == {"Loop", "West Loop"}


def test_processed_data_helpers_load_json_directory_and_latest_file(tmp_path, monkeypatch) -> None:
    data_root = tmp_path / "shared"
    install_local_accessor(monkeypatch, data_root)

    write_json(data_root / "processed" / "geo" / "neighborhood_metrics.json", '{"features": []}')
    write_json(data_root / "processed" / "summaries" / "news_summary.json", '{"count": 1}')
    write_json(data_root / "processed" / "summaries" / "politics_summary.json", '{"count": 2}')
    write_json(data_root / "processed" / "parking" / "analysis" / "loop_old.json", '{"id":"old"}')
    write_json(data_root / "processed" / "parking" / "analysis" / "loop_new.json", '{"id":"new"}')

    older = data_root / "processed" / "parking" / "analysis" / "loop_old.json"
    newer = data_root / "processed" / "parking" / "analysis" / "loop_new.json"
    os.utime(older, (1, 1))
    os.utime(newer, (2, 2))

    assert shared_data.load_processed_json("geo", "neighborhood_metrics.json", default={}) == {"features": []}
    assert shared_data.load_processed_json_directory("summaries", stem_suffix_to_strip="_summary") == {
        "news": {"count": 1},
        "politics": {"count": 2},
    }
    latest = shared_data.find_latest_processed_json_file("parking", "analysis", pattern="loop_*.json")
    assert latest is not None
    assert latest.name == "loop_new.json"


def test_raw_source_stats_and_read_helpers(tmp_path, monkeypatch) -> None:
    data_root = tmp_path / "shared"
    install_local_accessor(monkeypatch, data_root)

    write_json(
        data_root / "raw" / "news" / "2026-03-17" / "latest.json",
        '{"id":"n1","title":"Loop update","content":"Loop storefront changes","geo":{"neighborhood":"Loop"}}',
    )
    write_json(
        data_root / "raw" / "news" / "2026-03-16" / "older.json",
        '{"id":"n2","title":"Other update","geo":{"neighborhood":"Hyde Park"}}',
    )

    stats = shared_data.get_raw_source_stats(["news", "politics"])
    assert stats["news"]["doc_count"] == 2
    assert stats["news"]["active"] is True
    assert stats["news"]["last_update"] is not None
    assert stats["politics"] == {"doc_count": 0, "active": False, "last_update": None}

    docs = [
        {
            "id": "insp-1",
            "title": "Cafe inspection",
            "content": "Inspection in Loop",
            "metadata": {"dataset": "food_inspections", "raw_record": {"address": "123 Loop Ave"}},
            "geo": {"neighborhood": "Loop"},
        },
        {
            "id": "permit-1",
            "title": "Permit issued",
            "content": "Construction permit",
            "metadata": {"dataset": "building_permits", "raw_record": {"address": "456 Ashland"}},
            "geo": {"neighborhood": "West Town"},
        },
    ]

    assert [doc["id"] for doc in read_helpers.filter_docs_by_neighborhood(docs, "loop")] == ["insp-1"]
    assert [doc["id"] for doc in read_helpers.filter_public_data_by_dataset(docs, "food_inspections")] == ["insp-1"]

    transformed = read_helpers.transform_doc_for_graph(
        {
            "id": "doc-1",
            "title": "Doc",
            "memoryEntries": [
                {
                    "id": "mem-1",
                    "content": "Memory",
                    "memoryRelations": {"mem-0": "updates", "mem-x": "ignored"},
                }
            ],
            "x": 10,
            "y": 20,
        }
    )
    assert transformed["id"] == "doc-1"
    assert transformed["x"] == 10
    assert transformed["memoryEntries"][0]["memoryRelations"] == [
        {"targetMemoryId": "mem-0", "relationType": "updates"}
    ]
