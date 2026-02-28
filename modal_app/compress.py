"""Data compression — compresses raw Socrata/demographics/review JSON into
neighborhood-level summaries (~32:1 ratio).

Produces GeoJSON at /data/processed/geo/neighborhood_metrics.json for frontend Mapbox GL.
"""
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import modal

from modal_app.common import (
    CHICAGO_NEIGHBORHOODS,
    COMMUNITY_AREA_MAP,
    NEIGHBORHOOD_CENTROIDS,
    NeighborhoodGeoMetrics,
)
from modal_app.volume import app, volume, data_image, RAW_DATA_PATH, PROCESSED_DATA_PATH


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
    """Build GeoJSON FeatureCollection from aggregated summaries."""
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

    # Build GeoJSON
    features = []
    for hood in CHICAGO_NEIGHBORHOODS:
        coords = NEIGHBORHOOD_CENTROIDS.get(hood)
        if not coords:
            continue
        props = neighborhood_data.get(hood, {})
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
        raw_dir = Path(RAW_DATA_PATH) / source

        if not raw_dir.exists():
            print(f"Compress [{source}]: no raw data directory")
            continue

        # Read all JSON files in date subdirectories
        json_files = list(raw_dir.rglob("*.json"))
        for jf in json_files:
            try:
                record = json.loads(jf.read_text())
                summary.add_record(record)
            except Exception as e:
                print(f"Compress [{source}]: error reading {jf.name}: {e}")

        summaries[source] = summary
        print(f"Compress [{source}]: {summary.total_records} records → 1 summary ({summary.to_dict()['compression_ratio']})")

    # Write summaries
    summary_dir = Path(PROCESSED_DATA_PATH) / "summaries"
    summary_dir.mkdir(parents=True, exist_ok=True)

    for source, summary in summaries.items():
        out_path = summary_dir / f"{source}_summary.json"
        out_path.write_text(json.dumps(summary.to_dict(), indent=2, default=str))

    # Write GeoJSON
    geo_dir = Path(PROCESSED_DATA_PATH) / "geo"
    geo_dir.mkdir(parents=True, exist_ok=True)
    geo_path = geo_dir / "neighborhood_metrics.json"
    geojson = _build_geo_metrics(summaries)
    geo_path.write_text(json.dumps(geojson, indent=2))

    volume.commit()

    total_in = sum(s.total_records for s in summaries.values())
    print(f"Compression complete: {total_in} records → {len(summaries)} summaries + GeoJSON")
    return {s: summaries[s].to_dict() for s in summaries}
