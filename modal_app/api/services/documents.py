"""Shared document-loading and filtering helpers for the Modal API."""
from __future__ import annotations

import copy
import json
import re
import urllib.request
from pathlib import Path

from backend.read_helpers import filter_docs_by_neighborhood_match
from backend.shared_data import (
    load_first_existing_json,
    load_json_docs_from_directory,
    scan_source_directories,
)
from modal_app.api.cache import cache
from modal_app.common import (
    CHICAGO_NEIGHBORHOODS,
    COMMUNITY_AREA_MAP,
    NON_SENSOR_PIPELINE_SOURCES,
    detect_neighborhood,
    neighborhood_to_ca,
)
from modal_app.volume import PROCESSED_DATA_PATH, RAW_DATA_PATH, volume

_COUNT_ONLY_RE = re.compile(r"^\s*\d[\d,.\s]*[KMBkmb]?\s*$")


def load_docs(source: str, limit: int = 200) -> list[dict]:
    """Load documents from a source directory on the volume."""
    cache_key = f"docs:{source}:{limit}"

    def _loader() -> list[dict]:
        source_dir = Path(RAW_DATA_PATH) / source
        return load_json_docs_from_directory(
            source_dir,
            limit=limit,
            on_error=lambda json_file, exc: print(f"_load_docs [{source}]: corrupted JSON {json_file.name}: {exc}"),
        )

    return copy.deepcopy(cache.get_or_set(cache_key, 10.0, _loader))


def valid_neighborhood_names() -> set[str]:
    return set(n.lower() for n in CHICAGO_NEIGHBORHOODS) | set(
        n.lower() for n in COMMUNITY_AREA_MAP.values()
    )


def is_count_only_text(value: str) -> bool:
    text = (value or "").strip()
    return bool(text) and bool(_COUNT_ONLY_RE.match(text))


def sanitize_business_type(value: str) -> str:
    text = (value or "").lower()
    text = re.sub(r"[/_]+", " ", text)
    text = re.sub(r"[^a-z0-9\s-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def filter_by_neighborhood(docs: list[dict], neighborhood: str) -> list[dict]:
    """Filter documents by neighborhood with multi-strategy matching."""
    nb_community_area = neighborhood_to_ca(neighborhood)
    return filter_docs_by_neighborhood_match(
        docs,
        neighborhood,
        geo_substring_fields=(),
        geo_exact_field_values={
            field: value
            for field, value in {
                "neighborhood": neighborhood.lower(),
                "community_area": nb_community_area,
            }.items()
            if value is not None
        },
        raw_record_fields=(),
        include_title=True,
        include_content=True,
        content_limit=500,
        min_content_match_length=5,
    )


BUSINESS_TYPE_KEYWORDS: dict[str, list[str]] = {
    "restaurant": ["restaurant", "food", "dining", "cuisine", "eatery", "diner"],
    "coffee shop": ["coffee", "cafe", "tea", "espresso", "bakery"],
    "bar / nightlife": ["bar", "nightlife", "tavern", "pub", "lounge", "cocktail", "brewery"],
    "retail store": ["retail", "shopping", "store", "boutique", "merchandise"],
    "grocery / convenience": ["grocery", "convenience", "market", "deli", "bodega"],
    "salon / barbershop": ["salon", "barbershop", "beauty", "hair", "spa", "nail"],
    "fitness studio": ["fitness", "gym", "yoga", "pilates", "crossfit", "health club"],
    "professional services": ["professional", "consulting", "legal", "accounting", "office"],
    "food truck": ["food truck", "food", "catering", "street food", "mobile"],
    "bakery": ["bakery", "pastry", "bread", "cake", "dessert", "sweets"],
}


def filter_by_business_type(docs: list[dict], business_type: str) -> list[dict]:
    """Filter review/market documents by business type relevance."""
    if not business_type:
        return docs
    keywords = BUSINESS_TYPE_KEYWORDS.get(business_type.lower(), [business_type.lower()])
    matched = []
    for doc in docs:
        cats = doc.get("metadata", {}).get("categories", [])
        cat_text = " ".join(c.lower() if isinstance(c, str) else "" for c in cats)
        title = doc.get("title", "").lower()
        content = doc.get("content", "").lower()[:300]
        combined = f"{cat_text} {title} {content}"
        if any(kw in combined for kw in keywords):
            matched.append(doc)
    return matched


_CEREMONIAL_PATTERNS = [
    "congratulat", "honorar", "commemorate", "memorial", "tribute",
    "recognize", "recognition of", "appreciation", "in memory of",
    "retirement of", "sympathy", "condolence",
]

_ADMINISTRATIVE_PATTERNS = [
    "handicapped parking",
    "disabled parking",
    "parking permit no",
    "vehicle sticker",
    "pet license",
    "animal license",
    "residential parking",
    "driveway permit",
]


def filter_politics_relevance(docs: list[dict], business_type: str = "") -> list[dict]:
    filtered = []
    for doc in docs:
        title_lower = doc.get("title", "").lower()
        if any(pat in title_lower for pat in _CEREMONIAL_PATTERNS):
            continue
        if any(pat in title_lower for pat in _ADMINISTRATIVE_PATTERNS):
            continue
        filtered.append(doc)

    if not business_type or not filtered:
        return filtered

    keywords = BUSINESS_TYPE_KEYWORDS.get(business_type.lower(), [business_type.lower()])
    keywords += [
        "zoning", "ordinance", "inspection", "health", "safety",
        "business permit", "liquor permit", "food permit", "building permit",
        "liquor license", "food license", "special use",
    ]

    def relevance(doc: dict) -> int:
        text = f"{doc.get('title', '')} {doc.get('content', '')[:500]}".lower()
        return sum(1 for kw in keywords if kw in text)

    filtered.sort(key=relevance, reverse=True)
    return filtered


_NON_LOCAL_NEWS_PATTERNS = re.compile(
    r"(nba|nfl|mlb|nhl|sox\s+(spring|training)|cubs\s+spring|"
    r"bears\s+(draft|trade)|bulls\s+(trade|score)|blackhawks|"
    r"world\s+series|super\s+bowl|march\s+madness|"
    r"iran|ukraine|gaza|autoridades|"
    r"election\s+results|white\s+house)",
    re.IGNORECASE,
)


def is_likely_english(text: str) -> bool:
    if not text:
        return True
    ascii_count = sum(1 for c in text[:200] if ord(c) < 128)
    return (ascii_count / min(len(text), 200)) > 0.85


def filter_news_relevance(
    docs: list[dict], business_type: str = "", neighborhood: str = "",
) -> list[dict]:
    nb_names_lower = [n.lower() for n in CHICAGO_NEIGHBORHOODS]
    biz_keywords = (
        BUSINESS_TYPE_KEYWORDS.get(business_type.lower(), [business_type.lower()])
        if business_type else []
    )

    scored: list[tuple[dict, int]] = []
    for doc in docs:
        title = doc.get("title", "")
        content = doc.get("content", "")[:500]
        combined = f"{title} {content}".lower()

        if not is_likely_english(title):
            continue
        if _NON_LOCAL_NEWS_PATTERNS.search(combined):
            continue

        score = 0
        if "chicago" in combined:
            score += 3
        for nb in nb_names_lower:
            if len(nb) > 4 and nb in combined:
                score += 2
                break
        if neighborhood and neighborhood.lower() in combined:
            score += 3
        for kw in biz_keywords:
            if kw in combined:
                score += 2
                break
        for biz_word in ["business", "restaurant", "shop", "store", "zoning", "license", "regulation", "opening", "closing"]:
            if biz_word in combined:
                score += 1
                break
        feed = doc.get("metadata", {}).get("feed_name", "").lower()
        if "block club" in feed:
            score += 2
        elif "tribune" in feed or "sun-times" in feed:
            score += 1

        scored.append((doc, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    result = [doc for doc, score in scored if score > 0]
    if not result and scored:
        result = [doc for doc, _ in scored[:5]]
    return result


def load_demographics_summary() -> dict:
    candidate_paths = [
        Path(PROCESSED_DATA_PATH) / "demographics_summary.json",
        Path(PROCESSED_DATA_PATH) / "summaries" / "demographics_summary.json",
    ]

    def _loader() -> dict:
        return load_first_existing_json(candidate_paths, default={})

    return copy.deepcopy(cache.get_or_set("demographics:summary", 60.0, _loader))


def aggregate_demographics(neighborhood: str) -> dict:
    summary = load_demographics_summary()
    if not summary:
        return {}
    nb_community_area = neighborhood_to_ca(neighborhood)
    if nb_community_area and nb_community_area in summary.get("by_community_area", {}):
        return summary["by_community_area"][nb_community_area]
    return {}


def aggregate_city_demographics() -> dict:
    return load_demographics_summary().get("city_wide", {})


def load_cta_stations() -> list[dict]:
    cache_path = Path(PROCESSED_DATA_PATH) / "cache" / "cta_stations.json"

    def _loader() -> list[dict]:
        if cache_path.exists():
            try:
                return json.loads(cache_path.read_text())
            except Exception:
                pass

        try:
            url = "https://data.cityofchicago.org/resource/8pix-ypme.json?$limit=500"
            with urllib.request.urlopen(url, timeout=10) as resp:
                stations = json.loads(resp.read().decode())
            parsed = []
            for station in stations:
                try:
                    parsed.append(
                        {
                            "station_name": station.get("station_name", ""),
                            "lat": float(station.get("location", {}).get("latitude", 0) or station.get("latitude", 0)),
                            "lng": float(station.get("location", {}).get("longitude", 0) or station.get("longitude", 0)),
                        }
                    )
                except (TypeError, ValueError):
                    continue

            seen = set()
            deduped = []
            for station in parsed:
                if station["station_name"] not in seen and station["lat"] != 0:
                    seen.add(station["station_name"])
                    deduped.append(station)

            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(deduped, indent=2))
            volume.commit()
            return deduped
        except Exception as exc:
            print(f"_load_cta_stations: fetch failed: {exc}")
            return []

    return copy.deepcopy(cache.get_or_set("cta:stations", 3600.0, _loader))


def compute_transit_score(neighborhood_name: str) -> dict:
    import math

    from modal_app.common import NEIGHBORHOOD_CENTROIDS

    centroid = NEIGHBORHOOD_CENTROIDS.get(neighborhood_name)
    if not centroid:
        return {"stations_nearby": 0, "total_daily_riders": 0, "transit_score": 0, "station_names": []}

    clat, clng = centroid
    stations = load_cta_stations()
    nearby: list[dict] = []
    for station in stations:
        dlat = math.radians(station["lat"] - clat)
        dlng = math.radians(station["lng"] - clng)
        a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(clat)) * math.cos(math.radians(station["lat"])) * math.sin(dlng / 2) ** 2
        dist_km = 6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        if dist_km <= 3.0:
            nearby.append({**station, "distance_km": dist_km})

    if not nearby:
        return {"stations_nearby": 0, "total_daily_riders": 0, "transit_score": 0, "station_names": []}

    nearby_names = {station["station_name"] for station in nearby}
    ridership_docs = load_docs("public_data", limit=500)
    total_rides = 0.0
    for doc in ridership_docs:
        meta = doc.get("metadata", {})
        if meta.get("dataset") != "cta_ridership_L":
            continue
        raw = meta.get("raw_record", {})
        station = raw.get("stationame", raw.get("station_name", ""))
        if station in nearby_names:
            try:
                total_rides += float(raw.get("avg_weekday_rides", 0))
            except (TypeError, ValueError):
                continue

    transit_score = min(100, round((total_rides / 10000) * 100)) if total_rides > 0 else 0
    if transit_score == 0 and nearby:
        transit_score = min(100, len(nearby) * 20)

    return {
        "stations_nearby": len(nearby),
        "total_daily_riders": round(total_rides),
        "transit_score": transit_score,
        "station_names": sorted(nearby_names),
    }


def get_source_stats() -> dict[str, dict]:
    """Shared source scan used by status/metrics/sources/summary."""

    def _loader() -> dict[str, dict]:
        return scan_source_directories(
            {source: Path(RAW_DATA_PATH) / source for source in NON_SENSOR_PIPELINE_SOURCES}
        )

    raw_stats = cache.get_or_set("sources:stats", 15.0, _loader)
    copied: dict[str, dict] = {}
    for source, data in raw_stats.items():
        copied[source] = {
            "doc_count": data["doc_count"],
            "active": data["active"],
            "last_update": data["last_update"],
            "neighborhoods_covered": set(data["neighborhoods_covered"]),
        }
    return copied
