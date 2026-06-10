"""Data compression — compresses raw Socrata/demographics/review JSON into
neighborhood-level summaries (~32:1 ratio).

Produces GeoJSON at /data/processed/geo/neighborhood_metrics.json for frontend Mapbox GL.
"""
from collections import defaultdict
from datetime import datetime, timezone

import modal

from backend.shared_data import get_processed_data_dir, get_raw_data_dir, iter_files, load_json_file, write_json_file
from modal_app.common import (
    CHICAGO_NEIGHBORHOODS,
    COMMUNITY_AREA_MAP,
    NEIGHBORHOOD_CENTROIDS,
    NeighborhoodGeoMetrics,
)
from modal_app.volume import app, volume, data_image


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

    # Aggregate from enriched documents — classification + sentiment
    # Per-neighborhood accumulators for averaging
    sentiment_totals: dict[str, list[float]] = defaultdict(list)
    regulatory_counts: dict[str, int] = defaultdict(int)
    business_counts: dict[str, int] = defaultdict(int)
    safety_counts: dict[str, int] = defaultdict(int)
    enriched_count = 0

    enriched_dir = get_processed_data_dir() / "enriched"
    for jf in iter_files(enriched_dir, pattern="*.json"):
        try:
            doc = load_json_file(jf, default=None)
            if not isinstance(doc, dict):
                continue
        except Exception:
            continue

        hood = doc.get("geo", {}).get("neighborhood", "")
        if not hood:
            continue
        # Normalize community area numbers to names
        try:
            area_num = int(hood)
            hood = COMMUNITY_AREA_MAP.get(area_num, str(area_num))
        except (ValueError, TypeError):
            pass

        enriched_count += 1

        # Classification — count by top label
        classification = doc.get("classification", {})
        labels = classification.get("labels", [])
        if labels:
            top_label = labels[0].lower()
            if top_label == "regulatory":
                regulatory_counts[hood] += 1
            elif top_label in ("economic", "business"):
                business_counts[hood] += 1
            elif top_label == "safety":
                safety_counts[hood] += 1

        # Sentiment — accumulate for averaging
        sentiment = doc.get("sentiment", {})
        slabel = sentiment.get("label", "").lower()
        sscore = sentiment.get("score", 0.0)
        if slabel == "positive":
            sentiment_totals[hood].append(sscore)
        elif slabel == "negative":
            sentiment_totals[hood].append(-sscore)
        elif slabel == "neutral":
            sentiment_totals[hood].append(0.0)

    # Fallback: if no enriched docs, classify raw docs via keyword heuristics
    if enriched_count == 0:
        print("Compress [enriched]: no enriched docs found, using keyword heuristic fallback")
        _REGULATORY_KW = {"permit", "license", "zoning", "regulation", "inspection", "ordinance", "violation", "compliance", "code", "fine"}
        _BUSINESS_KW = {"restaurant", "store", "shop", "cafe", "bar", "business", "opening", "closing", "lease", "rent", "revenue", "commerce"}
        _SAFETY_KW = {"crime", "theft", "shooting", "fire", "accident", "hazard", "unsafe", "emergency", "arrest", "robbery"}
        _POSITIVE_KW = {"great", "excellent", "love", "amazing", "best", "wonderful", "fantastic", "recommend", "impressed", "perfect"}
        _NEGATIVE_KW = {"terrible", "worst", "awful", "horrible", "disgusting", "avoid", "bad", "poor", "dirty", "rude", "complaint", "fail"}

        for source in ["public_data", "news", "reddit", "reviews", "politics", "federal_register"]:
            raw_dir = get_raw_data_dir() / source
            for jf in iter_files(raw_dir, pattern="*.json"):
                try:
                    doc = load_json_file(jf, default=None)
                    if not isinstance(doc, dict):
                        continue
                except Exception:
                    continue
                hood = doc.get("geo", {}).get("neighborhood", "")
                if not hood:
                    continue
                try:
                    area_num = int(hood)
                    hood = COMMUNITY_AREA_MAP.get(area_num, str(area_num))
                except (ValueError, TypeError):
                    pass

                text = (doc.get("title", "") + " " + doc.get("content", "")[:500]).lower()
                words = set(text.split())

                if words & _REGULATORY_KW:
                    regulatory_counts[hood] += 1
                if words & _BUSINESS_KW:
                    business_counts[hood] += 1
                if words & _SAFETY_KW:
                    safety_counts[hood] += 1

                pos = len(words & _POSITIVE_KW)
                neg = len(words & _NEGATIVE_KW)
                if pos > neg:
                    sentiment_totals[hood].append(0.6)
                elif neg > pos:
                    sentiment_totals[hood].append(-0.6)
                elif pos > 0 or neg > 0:
                    sentiment_totals[hood].append(0.0)

    # Apply classification + sentiment metrics to neighborhood data
    for hood in set(regulatory_counts) | set(business_counts) | set(sentiment_totals) | set(safety_counts):
        props = neighborhood_data[hood]

        # regulatory_density: normalized count of regulatory-classified docs
        if hood in regulatory_counts:
            props["regulatory_density"] = min(regulatory_counts[hood] * 3.0, 100.0)

        # business_activity: supplement with economic/business-classified docs
        if hood in business_counts:
            props["business_activity"] = min(
                props["business_activity"] + business_counts[hood] * 2.0, 100.0
            )

        # avg_review_rating: average sentiment mapped to 0-5 scale
        if hood in sentiment_totals and sentiment_totals[hood]:
            avg_sentiment = sum(sentiment_totals[hood]) / len(sentiment_totals[hood])
            props["avg_review_rating"] = round((avg_sentiment + 1.0) * 2.5, 2)
            props["sentiment"] = round(avg_sentiment, 4)

        # risk_score: weighted combination of regulatory + safety + negative sentiment
        reg = regulatory_counts.get(hood, 0)
        safe = safety_counts.get(hood, 0)
        neg_sent = sum(1 for s in sentiment_totals.get(hood, []) if s < -0.5)
        props["risk_score"] = min((reg * 2.0 + safe * 3.0 + neg_sent * 2.5), 100.0)

    print(f"Compress [enriched]: processed docs across {len(sentiment_totals)} neighborhoods (enriched: {enriched_count})")

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
        for jf in json_files:
            try:
                record = load_json_file(jf, default=None)
                if not isinstance(record, dict):
                    continue
                summary.add_record(record)
            except Exception as e:
                print(f"Compress [{source}]: error reading {jf.name}: {e}")

        summaries[source] = summary
        print(f"Compress [{source}]: {summary.total_records} records → 1 summary ({summary.to_dict()['compression_ratio']})")

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
