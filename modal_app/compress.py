"""Data compression — compresses raw Socrata/demographics/review JSON into
neighborhood-level summaries (~32:1 ratio).

Produces GeoJSON at /data/processed/geo/neighborhood_metrics.json for frontend Mapbox GL.
"""
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
import tempfile
from pathlib import Path

import modal

from backend.shared_data import (
    SharedDataPath,
    get_processed_data_dir,
    get_raw_data_dir,
    iter_files,
    load_json_file,
    write_json_file,
)
from modal_app.api.services.documents import (
    cta_ridership_by_station_from_docs,
    neighborhood_from_coordinates,
)
from modal_app.common import (
    CHICAGO_NEIGHBORHOODS,
    COMMUNITY_AREA_MAP,
    NEIGHBORHOOD_CENTROIDS,
    detect_neighborhood,
)
from modal_app.volume import app, volume, data_image


PUBLIC_DATA_INDEX_DATASETS = ("food_inspections", "building_permits", "business_licenses")
DEFAULT_PUBLIC_DATA_INDEX_MAX_FILES_PER_DATASET = 1200
DEFAULT_CTA_RIDERSHIP_MAX_FILES = 1200


def _read_concurrency() -> int:
    try:
        return max(1, int(os.environ.get("COMPRESS_READ_CONCURRENCY", "32")))
    except ValueError:
        return 32


def _load_json_records(json_files: list, source: str) -> list[dict]:
    """Load source JSON concurrently because object storage reads are network-bound."""
    records: list[dict] = []

    def _load_one(jf):
        try:
            record = load_json_file(jf, default=None)
            return record if isinstance(record, dict) else None
        except Exception as e:
            print(f"Compress [{source}]: error reading {jf.name}: {e}")
            return None

    with ThreadPoolExecutor(max_workers=_read_concurrency()) as executor:
        for record in executor.map(_load_one, json_files):
            if record is not None:
                records.append(record)

    return records


def _normalize_neighborhood(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        area_num = int(raw)
        return COMMUNITY_AREA_MAP.get(area_num, str(area_num))
    except (ValueError, TypeError):
        return raw


def _record_coordinates(record: dict) -> tuple[float, float] | None:
    metadata = record.get("metadata", {}) or {}
    raw_record = metadata.get("raw_record", {}) or {}
    geo = record.get("geo", {}) or {}
    location = raw_record.get("location") or {}
    if not isinstance(location, dict):
        location = {}

    lat_candidates = (
        geo.get("lat"),
        geo.get("latitude"),
        record.get("lat"),
        record.get("latitude"),
        raw_record.get("latitude"),
        raw_record.get("lat"),
        location.get("latitude"),
    )
    lng_candidates = (
        geo.get("lng"),
        geo.get("lon"),
        geo.get("longitude"),
        record.get("lng"),
        record.get("lon"),
        record.get("longitude"),
        raw_record.get("longitude"),
        raw_record.get("lng"),
        raw_record.get("lon"),
        location.get("longitude"),
    )

    if isinstance(location.get("coordinates"), list) and len(location["coordinates"]) >= 2:
        lng_candidates = (*lng_candidates, location["coordinates"][0])
        lat_candidates = (*lat_candidates, location["coordinates"][1])

    for lat_raw in lat_candidates:
        for lng_raw in lng_candidates:
            try:
                lat = float(lat_raw)
                lng = float(lng_raw)
            except (TypeError, ValueError):
                continue
            if lat == 0 or lng == 0:
                continue
            return lat, lng
    return None


def _record_neighborhood(record: dict) -> str:
    metadata = record.get("metadata", {}) or {}
    raw_record = metadata.get("raw_record", {}) or {}
    geo = record.get("geo", {}) or {}

    for value in (
        geo.get("neighborhood"),
        geo.get("community_area"),
        raw_record.get("community_area_name"),
        raw_record.get("community_area"),
    ):
        neighborhood = _normalize_neighborhood(value)
        if neighborhood:
            return neighborhood

    coords = _record_coordinates(record)
    if coords is not None:
        neighborhood = neighborhood_from_coordinates(*coords)
        if neighborhood:
            return neighborhood

    address = str(raw_record.get("address") or "").strip()
    if address:
        return detect_neighborhood(address)
    return ""


def _record_dedupe_key(record: dict, dataset: str) -> str:
    metadata = record.get("metadata", {}) or {}
    raw_record = metadata.get("raw_record", {}) or {}
    for value in (
        record.get("id"),
        raw_record.get("inspection_id"),
        raw_record.get("id"),
        raw_record.get("permit_"),
        raw_record.get("license_id"),
    ):
        if value not in (None, ""):
            return f"{dataset}:{value}"
    return ":".join(
        str(part or "").strip().lower()
        for part in (
            dataset,
            record.get("title"),
            record.get("timestamp"),
            raw_record.get("address"),
            raw_record.get("license_description"),
        )
    )


def _build_public_data_neighborhood_index(
    records: list[dict],
    *,
    per_dataset_limit: int = 160,
) -> dict:
    """Build a compact real-document index for fast dashboard public-data reads."""
    neighborhoods: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    seen: dict[tuple[str, str], set[str]] = defaultdict(set)

    for record in records:
        metadata = record.get("metadata", {}) or {}
        dataset = str(metadata.get("dataset") or record.get("source") or "unknown")
        neighborhood = _record_neighborhood(record)
        if not neighborhood:
            continue

        seen_key = (neighborhood, dataset)
        dedupe_key = _record_dedupe_key(record, dataset)
        if dedupe_key in seen[seen_key]:
            continue
        seen[seen_key].add(dedupe_key)

        counts[neighborhood][dataset] += 1
        bucket = neighborhoods[neighborhood][dataset]
        if len(bucket) < per_dataset_limit:
            bucket.append(record)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "per_dataset_limit": per_dataset_limit,
        "neighborhoods": {
            neighborhood: {
                dataset: docs
                for dataset, docs in datasets.items()
            }
            for neighborhood, datasets in neighborhoods.items()
        },
        "counts": {
            neighborhood: dict(datasets)
            for neighborhood, datasets in counts.items()
        },
    }


def _public_data_partition_dirs(raw_public_dir: Path | SharedDataPath) -> list[Path | SharedDataPath]:
    if isinstance(raw_public_dir, SharedDataPath):
        entries = raw_public_dir.accessor.list_entries(raw_public_dir.relative_path, recursive=False)
        dirs = [
            SharedDataPath(raw_public_dir.accessor, entry.path)
            for entry in entries
            if entry.is_dir
        ]
    else:
        if not raw_public_dir.exists():
            return []
        dirs = [path for path in raw_public_dir.iterdir() if path.is_dir()]
    return sorted(dirs, key=lambda path: str(path.name), reverse=True)


def _public_data_dataset_paths(
    raw_public_dir: Path | SharedDataPath,
    dataset: str,
    *,
    max_files: int = DEFAULT_PUBLIC_DATA_INDEX_MAX_FILES_PER_DATASET,
) -> list[Path | SharedDataPath]:
    prefix = f"public-{dataset}-"
    paths: list[Path | SharedDataPath] = []

    for partition in _public_data_partition_dirs(raw_public_dir):
        remaining = max_files - len(paths)
        if remaining <= 0:
            break

        if isinstance(partition, SharedDataPath):
            list_with_prefix = getattr(partition.accessor, "list_entries_with_name_prefix", None)
            if callable(list_with_prefix):
                entries = list_with_prefix(
                    partition.relative_path,
                    name_prefix=prefix,
                    recursive=False,
                )
            else:
                entries = [
                    entry
                    for entry in partition.accessor.list_entries(partition.relative_path, recursive=False)
                    if entry.name.startswith(prefix)
                ]
            entries = [
                entry
                for entry in entries
                if entry.is_file and entry.name.startswith(prefix) and entry.name.endswith(".json")
            ]
            entries.sort(key=lambda entry: (entry.mtime, entry.path), reverse=True)
            paths.extend(SharedDataPath(partition.accessor, entry.path) for entry in entries[:remaining])
            continue

        files = [
            path
            for path in partition.glob(f"{prefix}*.json")
            if path.is_file()
        ]
        files.sort(key=lambda path: (path.stat().st_mtime, path.name), reverse=True)
        paths.extend(files[:remaining])

    return paths


def _build_public_data_neighborhood_index_from_paths(
    dataset_paths: dict[str, list[Path | SharedDataPath]],
    *,
    per_dataset_limit: int = 160,
) -> dict:
    neighborhoods: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    loaded_by_dataset: dict[str, int] = defaultdict(int)
    seen: dict[tuple[str, str], set[str]] = defaultdict(set)

    items = [
        (dataset, path)
        for dataset, paths in dataset_paths.items()
        for path in paths
    ]

    def _load_one(item: tuple[str, Path | SharedDataPath]) -> tuple[str, dict | None]:
        dataset, path = item
        try:
            record = load_json_file(path, default=None)
        except Exception as exc:
            print(f"Public data index: error reading {path}: {exc}")
            return dataset, None
        return dataset, record if isinstance(record, dict) else None

    with ThreadPoolExecutor(max_workers=_read_concurrency()) as executor:
        for dataset, record in executor.map(_load_one, items):
            if record is None:
                continue
            loaded_by_dataset[dataset] += 1

            neighborhood = _record_neighborhood(record)
            if not neighborhood:
                continue

            seen_key = (neighborhood, dataset)
            dedupe_key = _record_dedupe_key(record, dataset)
            if dedupe_key in seen[seen_key]:
                continue
            seen[seen_key].add(dedupe_key)

            counts[neighborhood][dataset] += 1
            bucket = neighborhoods[neighborhood][dataset]
            if len(bucket) < per_dataset_limit:
                bucket.append(record)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "per_dataset_limit": per_dataset_limit,
        "files_by_dataset": {
            dataset: len(paths)
            for dataset, paths in dataset_paths.items()
        },
        "loaded_by_dataset": dict(loaded_by_dataset),
        "neighborhoods": {
            neighborhood: {
                dataset: docs
                for dataset, docs in datasets.items()
            }
            for neighborhood, datasets in neighborhoods.items()
        },
        "counts": {
            neighborhood: dict(datasets)
            for neighborhood, datasets in counts.items()
        },
    }


def _load_docs_from_paths(paths: list[Path | SharedDataPath], *, source: str) -> list[dict]:
    items = list(paths)

    def _load_one(path: Path | SharedDataPath) -> dict | None:
        try:
            record = load_json_file(path, default=None)
        except Exception as exc:
            print(f"{source}: error reading {path}: {exc}")
            return None
        return record if isinstance(record, dict) else None

    records: list[dict] = []
    with ThreadPoolExecutor(max_workers=_read_concurrency()) as executor:
        for record in executor.map(_load_one, items):
            if record is not None:
                records.append(record)
    return records


class DatasetSummary:
    """Aggregates raw records into neighborhood-level counts and notable items."""

    def __init__(self, source: str):
        self.source = source
        self.counts_by_type: dict[str, int] = defaultdict(int)
        self.counts_by_status: dict[str, int] = defaultdict(int)
        self.counts_by_neighborhood: dict[str, int] = defaultdict(int)
        self.recent_items: list[dict] = []
        self.notable_items: list[dict] = []  # failed inspections, revoked licenses, etc.
        self.total_records = 0

    def add_record(self, record: dict) -> None:
        """Process a single raw record."""
        self.total_records += 1
        meta = record.get("metadata", {})
        geo = record.get("geo", {})

        # Count by type/dataset
        dataset = meta.get("dataset", record.get("source", "unknown"))
        self.counts_by_type[dataset] += 1

        # Count by status if available
        raw = meta.get("raw_record", {})
        status = raw.get("status", raw.get("results", meta.get("business_status", "")))
        if status:
            self.counts_by_status[str(status)] += 1

        # Count by neighborhood
        neighborhood = geo.get("neighborhood", "")
        if neighborhood:
            # Map community area numbers to names
            try:
                area_num = int(neighborhood)
                neighborhood = COMMUNITY_AREA_MAP.get(area_num, str(area_num))
            except (ValueError, TypeError):
                pass
            self.counts_by_neighborhood[neighborhood] += 1

        # Track recent items (keep top 5)
        if len(self.recent_items) < 5:
            self.recent_items.append({
                "title": record.get("title", ""),
                "timestamp": record.get("timestamp", ""),
                "id": record.get("id", ""),
            })

        # Track notable items
        self._check_notable(record, raw)

    def _check_notable(self, record: dict, raw: dict) -> None:
        """Identify notable items: failed inspections, revoked licenses, high-value permits."""
        # Failed food inspections
        if raw.get("results") in ("Fail", "Out of Business"):
            self.notable_items.append({
                "type": "failed_inspection",
                "title": record.get("title", ""),
                "detail": raw.get("violations", "")[:200],
            })

        # Revoked business licenses
        if raw.get("license_status") in ("REV", "AAC"):
            self.notable_items.append({
                "type": "revoked_license",
                "title": record.get("title", ""),
                "detail": raw.get("license_description", ""),
            })

        # High-value building permits (>$100K)
        try:
            cost = float(raw.get("reported_cost", 0) or 0)
            if cost > 100000:
                self.notable_items.append({
                    "type": "high_value_permit",
                    "title": record.get("title", ""),
                    "detail": f"${cost:,.0f}",
                })
        except (ValueError, TypeError):
            pass

    def to_dict(self) -> dict:
        """Export summary as dict."""
        return {
            "source": self.source,
            "total_records": self.total_records,
            "counts_by_type": dict(self.counts_by_type),
            "counts_by_status": dict(self.counts_by_status),
            "counts_by_neighborhood": dict(self.counts_by_neighborhood),
            "recent_items": self.recent_items[:5],
            "notable_items": self.notable_items[:10],
            "compression_ratio": f"{self.total_records}:1" if self.total_records > 0 else "0:1",
        }


def _build_geo_metrics(summaries: dict[str, DatasetSummary]) -> dict:
    """Build GeoJSON FeatureCollection from aggregated summaries and enriched docs."""
    neighborhood_data: dict[str, dict] = defaultdict(lambda: {
        "regulatory_density": 0.0,
        "business_activity": 0.0,
        "sentiment": 0.0,
        "risk_score": 0.0,
        "active_permits": 0,
        "crime_incidents_30d": 0,
        "avg_review_rating": 0.0,
        "review_count": 0,
    })

    # Aggregate from public_data summary
    if "public_data" in summaries:
        pd_summary = summaries["public_data"]
        for hood, count in pd_summary.counts_by_neighborhood.items():
            neighborhood_data[hood]["active_permits"] += count
            neighborhood_data[hood]["regulatory_density"] = min(count * 3.0, 100.0)

    # Aggregate from CCTV summary — foot traffic intensity
    if "cctv" in summaries:
        cctv_summary = summaries["cctv"]
        for hood, count in cctv_summary.counts_by_neighborhood.items():
            neighborhood_data[hood]["foot_traffic_intensity"] = min(count * 5.0, 100.0)

    # Aggregate from reviews summary
    if "reviews" in summaries:
        rv_summary = summaries["reviews"]
        for hood, count in rv_summary.counts_by_neighborhood.items():
            neighborhood_data[hood]["review_count"] += count
            neighborhood_data[hood]["business_activity"] += min(count * 2.0, 100.0)

    print("Compress [geo]: building metrics from source summaries")

    # Min-max normalize metrics to 0-100 for comparable heatmap rendering
    def _minmax(values: dict[str, float]) -> dict[str, float]:
        if not values:
            return {}
        lo, hi = min(values.values()), max(values.values())
        span = hi - lo if hi > lo else 1.0
        return {h: round((v - lo) / span * 100, 1) for h, v in values.items()}

    # Collect raw values only for neighborhoods that have data (> 0)
    raw_reg = {h: p["regulatory_density"] + p["active_permits"] for h, p in neighborhood_data.items()
               if p["regulatory_density"] > 0 or p["active_permits"] > 0}
    raw_biz = {h: p["business_activity"] for h, p in neighborhood_data.items() if p["business_activity"] > 0}
    raw_sent = {h: p["avg_review_rating"] for h, p in neighborhood_data.items() if p["avg_review_rating"] > 0}

    norm_reg = _minmax(raw_reg)
    norm_biz = _minmax(raw_biz)
    norm_sent = _minmax(raw_sent)

    # Apply normalized values; None for neighborhoods with no data
    for hood, props in neighborhood_data.items():
        props["norm_regulatory"] = norm_reg.get(hood)
        props["norm_business"] = norm_biz.get(hood)
        props["norm_sentiment"] = norm_sent.get(hood)

    # Build GeoJSON
    features = []
    for hood in CHICAGO_NEIGHBORHOODS:
        coords = NEIGHBORHOOD_CENTROIDS.get(hood)
        if not coords:
            continue
        props = neighborhood_data[hood]
        props["neighborhood"] = hood
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [coords[1], coords[0]],  # GeoJSON is [lng, lat]
            },
            "properties": props,
        })

    return {
        "type": "FeatureCollection",
        "features": features,
    }


@app.function(
    image=data_image,
    volumes={"/data": volume},
    secrets=[modal.Secret.from_name("alethia-secrets")],
    timeout=1200,
)
def build_public_data_index(
    per_dataset_limit: int = 160,
    max_files_per_dataset: int = DEFAULT_PUBLIC_DATA_INDEX_MAX_FILES_PER_DATASET,
):
    """Build the processed public-data neighborhood index used by dashboard routes."""
    raw_dir = get_raw_data_dir() / "public_data"
    dataset_paths = {
        dataset: _public_data_dataset_paths(
            raw_dir,
            dataset,
            max_files=max_files_per_dataset,
        )
        for dataset in PUBLIC_DATA_INDEX_DATASETS
    }
    if not any(dataset_paths.values()):
        print("Public data index: no raw public_data files found")
        return {"total_records": 0, "neighborhoods": 0}

    index = _build_public_data_neighborhood_index_from_paths(
        dataset_paths,
        per_dataset_limit=per_dataset_limit,
    )
    index_path = get_processed_data_dir() / "cache" / "public_data_by_neighborhood.json"
    raw_index = json.dumps(index, indent=2, default=str)
    write_json_file(index_path, index)

    mounted_index_path = Path("/data/processed/cache/public_data_by_neighborhood.json")
    mounted_index_path.parent.mkdir(parents=True, exist_ok=True)
    mounted_index_path.write_text(raw_index, encoding="utf-8")

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
        tmp.write(raw_index)
        upload_path = Path(tmp.name)
    try:
        with volume.batch_upload(force=True) as batch:
            batch.put_file(str(upload_path), "/processed/cache/public_data_by_neighborhood.json")
    finally:
        if upload_path.exists():
            upload_path.unlink()
    volume.commit()

    result = {
        "total_records": sum(index.get("loaded_by_dataset", {}).values()),
        "neighborhoods": len(index["neighborhoods"]),
        "files_by_dataset": index.get("files_by_dataset", {}),
        "loaded_by_dataset": index.get("loaded_by_dataset", {}),
        "generated_at": index["generated_at"],
        "index_path": str(index_path),
        "mounted_index_exists": mounted_index_path.exists(),
        "mounted_index_size": mounted_index_path.stat().st_size if mounted_index_path.exists() else 0,
    }
    print(f"Public data index complete: {result}")
    return result


@app.function(
    image=data_image,
    volumes={"/data": volume},
    secrets=[modal.Secret.from_name("alethia-secrets")],
    timeout=900,
)
def build_transit_cache(max_files: int = DEFAULT_CTA_RIDERSHIP_MAX_FILES):
    """Build the processed CTA ridership cache used by neighborhood transit scoring."""
    mounted_station_cache_path = Path("/data/processed/cache/cta_stations.json")
    station_cache = load_json_file(mounted_station_cache_path, default=None)
    station_count = len(station_cache) if isinstance(station_cache, list) else 0
    active_station_cache_path = get_processed_data_dir() / "cache" / "cta_stations.json"
    if isinstance(station_cache, list):
        write_json_file(active_station_cache_path, station_cache)
    active_station_cache = load_json_file(active_station_cache_path, default=None)
    active_station_count = len(active_station_cache) if isinstance(active_station_cache, list) else 0

    raw_public_dir = get_raw_data_dir() / "public_data"
    paths = _public_data_dataset_paths(
        raw_public_dir,
        "cta_ridership_L",
        max_files=max_files,
    )
    if not paths:
        print("Transit cache: no cta_ridership_L files found")
        empty_payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "files": 0,
            "records": 0,
            "stations": {},
        }
        cache_path = get_processed_data_dir() / "cache" / "cta_l_ridership_by_station.json"
        raw_empty_payload = json.dumps(empty_payload, indent=2, default=str)
        write_json_file(cache_path, empty_payload)
        mounted_cache_path = Path("/data/processed/cache/cta_l_ridership_by_station.json")
        mounted_cache_path.parent.mkdir(parents=True, exist_ok=True)
        mounted_cache_path.write_text(raw_empty_payload, encoding="utf-8")
        volume.commit()
        return {
            "records": 0,
            "stations": 0,
            "station_cache_records": station_count,
            "active_station_cache_records": active_station_count,
            "empty_ridership_cache_written": True,
        }

    docs = _load_docs_from_paths(paths, source="Transit cache")
    stations = cta_ridership_by_station_from_docs(docs)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "files": len(paths),
        "records": len(docs),
        "stations": stations,
    }

    cache_path = get_processed_data_dir() / "cache" / "cta_l_ridership_by_station.json"
    raw_payload = json.dumps(payload, indent=2, default=str)
    write_json_file(cache_path, payload)

    mounted_cache_path = Path("/data/processed/cache/cta_l_ridership_by_station.json")
    mounted_cache_path.parent.mkdir(parents=True, exist_ok=True)
    mounted_cache_path.write_text(raw_payload, encoding="utf-8")

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
        tmp.write(raw_payload)
        upload_path = Path(tmp.name)
    try:
        with volume.batch_upload(force=True) as batch:
            batch.put_file(str(upload_path), "/processed/cache/cta_l_ridership_by_station.json")
            if isinstance(station_cache, list):
                batch.put_file(str(mounted_station_cache_path), "/processed/cache/cta_stations.json")
    finally:
        if upload_path.exists():
            upload_path.unlink()
    volume.commit()

    result = {
        "files": len(paths),
        "records": len(docs),
        "stations": len(stations),
        "station_cache_records": station_count,
        "active_station_cache_records": active_station_count,
        "generated_at": payload["generated_at"],
        "cache_path": str(cache_path),
        "mounted_cache_exists": mounted_cache_path.exists(),
        "mounted_cache_size": mounted_cache_path.stat().st_size if mounted_cache_path.exists() else 0,
    }
    print(f"Transit cache complete: {result}")
    return result


@app.function(
    image=data_image,
    volumes={"/data": volume},
    secrets=[modal.Secret.from_name("alethia-secrets")],
    timeout=600,
)
def compress_raw_data(days: int = 7):
    """Compress raw data into neighborhood-level summaries.

    Reads /data/raw/{source}/ → writes /data/processed/summaries/ and
    /data/processed/geo/neighborhood_metrics.json

    Args:
        sources: List of sources to compress. Default: public_data, demographics, reviews
        days: How many days of data to include
    """
    sources = ["public_data", "demographics", "reviews", "cctv"]

    summaries: dict[str, DatasetSummary] = {}

    for source in sources:
        summary = DatasetSummary(source)
        raw_dir = get_raw_data_dir() / source

        # Read all JSON files in date subdirectories
        json_files = iter_files(raw_dir, pattern="*.json")
        if not json_files:
            print(f"Compress [{source}]: no raw data directory")
            continue
        records = _load_json_records(json_files, source)
        for record in records:
            summary.add_record(record)

        summaries[source] = summary
        print(f"Compress [{source}]: {summary.total_records} records → 1 summary ({summary.to_dict()['compression_ratio']})")

        if source == "public_data":
            index_path = get_processed_data_dir() / "cache" / "public_data_by_neighborhood.json"
            index = _build_public_data_neighborhood_index(records)
            write_json_file(index_path, index)
            print(
                "Compress [public_data]: wrote neighborhood index "
                f"for {len(index['neighborhoods'])} neighborhoods"
            )

    # Write summaries
    summary_dir = get_processed_data_dir() / "summaries"

    for source, summary in summaries.items():
        out_path = summary_dir / f"{source}_summary.json"
        write_json_file(out_path, summary.to_dict())

    # Write GeoJSON
    geo_path = get_processed_data_dir() / "geo" / "neighborhood_metrics.json"
    geojson = _build_geo_metrics(summaries)
    write_json_file(geo_path, geojson)

    volume.commit()

    total_in = sum(s.total_records for s in summaries.values())
    print(f"Compression complete: {total_in} records → {len(summaries)} summaries + GeoJSON")
    return {s: summaries[s].to_dict() for s in summaries}
