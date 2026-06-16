from __future__ import annotations

from tests.backend_test_helpers import write_json

from modal_app.compress import (
    _build_public_data_neighborhood_index_from_paths,
    _public_data_dataset_paths,
    _record_neighborhood,
)
from modal_app.common import NEIGHBORHOOD_CENTROIDS


def test_public_data_index_paths_are_dataset_scoped_and_newest_first(tmp_path) -> None:
    raw_public_dir = tmp_path / "raw" / "public_data"
    write_json(
        raw_public_dir / "2026-06-08" / "public-food_inspections-0.json",
        '{"metadata":{"raw_record":{"community_area":"32"}}}',
    )
    write_json(
        raw_public_dir / "2026-06-10" / "public-food_inspections-1.json",
        '{"metadata":{"raw_record":{"community_area":"32"}}}',
    )
    write_json(
        raw_public_dir / "2026-06-10" / "public-building_permits-0.json",
        '{"metadata":{"raw_record":{"community_area":"32"}}}',
    )

    paths = _public_data_dataset_paths(raw_public_dir, "food_inspections", max_files=2)

    assert [path.parent.name for path in paths] == ["2026-06-10", "2026-06-08"]
    assert [path.name for path in paths] == ["public-food_inspections-1.json", "public-food_inspections-0.json"]


def test_public_data_index_from_paths_uses_requested_dataset_key(tmp_path) -> None:
    food_path = tmp_path / "public-food_inspections-0.json"
    write_json(
        food_path,
        (
            '{"source":"public_data",'
            '"metadata":{"dataset":"legacy_name","raw_record":{"community_area":"32"}},'
            '"geo":{}}'
        ),
    )

    index = _build_public_data_neighborhood_index_from_paths(
        {"food_inspections": [food_path]},
        per_dataset_limit=5,
    )

    assert index["counts"]["Loop"] == {"food_inspections": 1}
    assert len(index["neighborhoods"]["Loop"]["food_inspections"]) == 1


def test_public_data_index_deduplicates_records_across_partitions(tmp_path) -> None:
    first_path = tmp_path / "2026-06-08" / "public-food_inspections-6.json"
    second_path = tmp_path / "2026-06-10" / "public-food_inspections-6.json"
    payload = (
        '{"id":"public-food_inspections-6",'
        '"source":"public_data",'
        '"metadata":{"dataset":"food_inspections","raw_record":{"inspection_id":"2638411","community_area":"32"}},'
        '"geo":{}}'
    )
    write_json(first_path, payload)
    write_json(second_path, payload)

    index = _build_public_data_neighborhood_index_from_paths(
        {"food_inspections": [first_path, second_path]},
        per_dataset_limit=5,
    )

    assert index["counts"]["Loop"] == {"food_inspections": 1}
    assert [doc["id"] for doc in index["neighborhoods"]["Loop"]["food_inspections"]] == ["public-food_inspections-6"]


def test_public_data_index_detects_neighborhood_from_coordinates() -> None:
    lat, lng = NEIGHBORHOOD_CENTROIDS["Loop"]

    assert _record_neighborhood({
        "geo": {"lat": str(lat), "lng": str(lng), "neighborhood": "", "community_area": ""},
        "metadata": {"raw_record": {"address": "UNKNOWN"}},
    }) == "Loop"
