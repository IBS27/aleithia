"""Shared document-loading and filtering helpers for the Modal API."""
from __future__ import annotations

import copy
import fnmatch
import json
import math
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from backend.shared_data import (
    SharedDataPath,
    get_processed_data_dir,
    get_raw_data_dir,
    load_first_existing_json,
    load_json_file,
    load_json_docs_from_directory,
    load_json_docs_from_paths,
    scan_source_directories,
    write_json_file,
)
from modal_app.api.cache import cache
from modal_app.common import (
    CHICAGO_NEIGHBORHOODS,
    COMMUNITY_AREA_MAP,
    NEIGHBORHOOD_CENTROIDS,
    NON_SENSOR_PIPELINE_SOURCES,
    SOCRATA_DATASETS,
    detect_neighborhood,
    neighborhood_to_ca,
)

_COUNT_ONLY_RE = re.compile(r"^\s*\d[\d,.\s]*[KMBkmb]?\s*$")
NEIGHBORHOOD_COORDINATE_RADIUS_KM = 2.75
SOCRATA_BASE = "https://data.cityofchicago.org/resource"
CTA_STATION_CACHE_VERSION = "v2"
CTA_TRANSIT_SCORE_CACHE_VERSION = "v2"

_LIVE_PUBLIC_DATASET_FIELDS = {
    "food_inspections": {
        "select": (
            "inspection_id,dba_name,aka_name,facility_type,risk,address,city,state,zip,"
            "inspection_date,inspection_type,results,violations,latitude,longitude,location"
        ),
        "order": "inspection_date DESC",
    },
    "building_permits": {
        "select": (
            "id,permit_,permit_type,review_type,application_start_date,issue_date,street_number,"
            "street_direction,street_name,work_description,reported_cost,total_fee,latitude,longitude,location"
        ),
        "order": "issue_date DESC",
    },
    "business_licenses": {
        "select": (
            "id,license_id,doing_business_as_name,address,city,state,zip_code,license_description,"
            "business_activity,license_status,date_issued,license_start_date,expiration_date"
        ),
        "where": "city='CHICAGO'",
        "order": "date_issued DESC",
    },
}


def load_docs(source: str, limit: int = 200) -> list[dict]:
    """Load documents from a source directory in the shared dataset."""
    raw_dir = get_raw_data_dir()
    cache_key = f"docs:{raw_dir}:{source}:{limit}"

    def _loader() -> list[dict]:
        source_dir = raw_dir / source
        return load_json_docs_from_directory(
            source_dir,
            limit=limit,
            on_error=lambda json_file, exc: print(f"_load_docs [{source}]: corrupted JSON {json_file.name}: {exc}"),
        )

    return copy.deepcopy(cache.get_or_set(cache_key, 10.0, _loader))


def _limited_source_files(
    directory: Path | SharedDataPath,
    *,
    pattern: str,
    limit: int,
) -> list[Path | SharedDataPath]:
    """Collect matching files from newest source subdirectories without a full recursive scan."""
    if limit <= 0:
        return []

    def _literal_name_prefix(glob_pattern: str) -> str:
        for idx, char in enumerate(glob_pattern):
            if char in "*?[":
                return glob_pattern[:idx]
        return glob_pattern

    if isinstance(directory, SharedDataPath):
        files: list[SharedDataPath] = []
        entries = directory.accessor.list_entries(directory.relative_path, recursive=False)
        ordered = sorted(entries, key=lambda entry: (entry.mtime, entry.path), reverse=True)
        list_with_prefix = getattr(directory.accessor, "list_entries_with_name_prefix", None)
        literal_prefix = _literal_name_prefix(pattern)

        for entry in ordered:
            if len(files) >= limit:
                break
            if entry.is_file and fnmatch.fnmatch(PurePosixPath(entry.path).name, pattern):
                files.append(SharedDataPath(directory.accessor, entry.path))
                continue
            if not entry.is_dir:
                continue

            if literal_prefix and callable(list_with_prefix):
                children = list_with_prefix(
                    entry.path,
                    name_prefix=literal_prefix,
                    recursive=False,
                    max_entries=max(limit - len(files), 1),
                )
            else:
                children = directory.accessor.list_entries(entry.path, recursive=False)
            children = sorted(children, key=lambda child: (child.mtime, child.path), reverse=True)
            for child in children:
                if len(files) >= limit:
                    break
                if child.is_file and fnmatch.fnmatch(PurePosixPath(child.path).name, pattern):
                    files.append(SharedDataPath(directory.accessor, child.path))
        return files

    if not directory.exists():
        return []

    def _mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    files: list[Path] = []
    entries = sorted(directory.iterdir(), key=lambda path: (_mtime(path), str(path)), reverse=True)
    for entry in entries:
        if len(files) >= limit:
            break
        if entry.is_file() and fnmatch.fnmatch(entry.name, pattern):
            files.append(entry)
            continue
        if not entry.is_dir():
            continue
        for child in sorted(entry.iterdir(), key=lambda path: (_mtime(path), str(path)), reverse=True):
            if len(files) >= limit:
                break
            if child.is_file() and fnmatch.fnmatch(child.name, pattern):
                files.append(child)
    return files


def load_public_dataset_docs(dataset: str, limit: int = 200) -> list[dict]:
    """Load one public_data dataset by filename prefix."""
    raw_dir = get_raw_data_dir()
    cache_key = f"docs:{raw_dir}:public_data:{dataset}:{limit}"

    def _loader() -> list[dict]:
        public_dir = raw_dir / "public_data"
        paths = _limited_source_files(
            public_dir,
            pattern=f"public-{dataset}-*.json",
            limit=limit,
        )
        return load_json_docs_from_paths(
            paths,
            limit=limit,
            on_error=lambda json_file, exc: print(
                f"_load_public_dataset_docs [{dataset}]: corrupted JSON {json_file.name}: {exc}"
            ),
        )

    return copy.deepcopy(cache.get_or_set(cache_key, 10.0, _loader))


def load_public_dataset_docs_for_neighborhood(dataset: str, neighborhood: str, limit: int = 120) -> list[dict]:
    """Load indexed real public-data docs for a neighborhood without scanning raw files."""
    processed_dir = get_processed_data_dir()
    index_path = processed_dir / "cache" / "public_data_by_neighborhood.json"
    mounted_index_path = Path("/data/processed/cache/public_data_by_neighborhood.json")
    cache_key = f"docs:{processed_dir}:public_data_index:{neighborhood}:{dataset}:{limit}"

    def _loader() -> list[dict]:
        index = None
        for candidate in (mounted_index_path, index_path):
            parsed = load_json_file(candidate, default=None)
            if isinstance(parsed, dict):
                index = parsed
                break
        if not isinstance(index, dict):
            return []
        neighborhoods = index.get("neighborhoods", {})
        if not isinstance(neighborhoods, dict):
            return []

        dataset_map = neighborhoods.get(neighborhood)
        if not isinstance(dataset_map, dict):
            normalized_target = _normalize_text(neighborhood)
            for name, candidate in neighborhoods.items():
                if _normalize_text(name) == normalized_target and isinstance(candidate, dict):
                    dataset_map = candidate
                    break
        if not isinstance(dataset_map, dict):
            return []

        docs = dataset_map.get(dataset, [])
        if not isinstance(docs, list):
            return []
        return [doc for doc in docs if isinstance(doc, dict)][:limit]

    return copy.deepcopy(cache.get_or_set(cache_key, 30.0, _loader))


def load_live_public_dataset_docs(dataset: str, neighborhood: str, limit: int = 120) -> list[dict]:
    """Load current public records for a neighborhood directly from Socrata."""
    dataset_id = SOCRATA_DATASETS.get(dataset)
    config = _LIVE_PUBLIC_DATASET_FIELDS.get(dataset)
    if not dataset_id or not config:
        raise ValueError(f"Unsupported live public dataset: {dataset}")

    centroid = NEIGHBORHOOD_CENTROIDS.get(neighborhood)
    where = config.get("where", "")
    if dataset in {"food_inspections", "building_permits"}:
        if centroid is None:
            raise ValueError(f"No centroid available for neighborhood: {neighborhood}")
        lat, lng = centroid
        where = f"within_circle(location,{lat},{lng},{int(NEIGHBORHOOD_COORDINATE_RADIUS_KM * 1000)})"

    params = {
        "$select": config["select"],
        "$order": config["order"],
        "$limit": str(limit),
    }
    if where:
        params["$where"] = where
    url = f"{SOCRATA_BASE}/{dataset_id}.json?{urllib.parse.urlencode(params)}"
    headers = {}
    app_token = os.getenv("SOCRATA_APP_TOKEN", "").strip()
    if app_token:
        headers["X-App-Token"] = app_token

    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=8) as response:
        records = json.loads(response.read().decode("utf-8"))
    if not isinstance(records, list):
        return []
    return [_socrata_record_to_doc(dataset, record) for record in records if isinstance(record, dict)]


def load_live_review_docs(neighborhood: str, business_type: str = "", limit: int = 12) -> list[dict]:
    """Load current business review summaries for a neighborhood from Google Places."""
    api_key = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
    if not api_key:
        return []

    query_subject = sanitize_business_type(business_type) or "businesses"
    params = {
        "query": f"{query_subject} in {neighborhood}, Chicago, IL",
        "key": api_key,
    }
    url = f"https://maps.googleapis.com/maps/api/place/textsearch/json?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url)
    with urllib.request.urlopen(request, timeout=8) as response:
        payload = json.loads(response.read().decode("utf-8"))

    results = payload.get("results", []) if isinstance(payload, dict) else []
    if not isinstance(results, list):
        return []

    docs: list[dict] = []
    timestamp = datetime.now(timezone.utc).isoformat()
    for place in results[:limit]:
        if not isinstance(place, dict):
            continue
        place_id = str(place.get("place_id") or "").strip()
        if not place_id:
            continue
        name = str(place.get("name") or "Business").strip()
        address = str(place.get("formatted_address") or "").strip()
        rating = place.get("rating")
        review_count = int(place.get("user_ratings_total") or 0)
        types = [str(value) for value in place.get("types", []) if isinstance(value, str)]
        location = (place.get("geometry") or {}).get("location") if isinstance(place.get("geometry"), dict) else {}
        docs.append(
            {
                "id": f"gplaces-live-{place_id}",
                "source": "google_places",
                "title": name,
                "content": (
                    f"{name} — {address}. "
                    f"Rating: {rating if rating is not None else 'N/A'}/5 ({review_count} reviews). "
                    f"Search: {query_subject} in {neighborhood}."
                ),
                "url": f"https://www.google.com/maps/place/?q=place_id:{place_id}",
                "timestamp": timestamp,
                "metadata": {
                    "rating": rating,
                    "review_count": review_count,
                    "user_ratings_total": review_count,
                    "types": types,
                    "categories": [value.replace("_", " ").title() for value in types],
                    "business_status": place.get("business_status", ""),
                    "price_level": place.get("price_level"),
                    "address": address,
                    "neighborhood": neighborhood,
                    "query": query_subject,
                    "live_fallback": True,
                },
                "geo": {
                    "lat": location.get("lat") if isinstance(location, dict) else None,
                    "lng": location.get("lng") if isinstance(location, dict) else None,
                    "neighborhood": neighborhood,
                },
            }
        )
    return docs


def _socrata_record_to_doc(dataset: str, record: dict) -> dict:
    record_id = (
        record.get("inspection_id")
        or record.get("id")
        or record.get("permit_")
        or record.get("license_id")
        or len(str(record))
    )
    timestamp = (
        record.get("inspection_date")
        or record.get("issue_date")
        or record.get("date_issued")
        or record.get("license_start_date")
        or ""
    )
    if dataset == "food_inspections":
        title = record.get("dba_name") or record.get("aka_name") or "Food Inspection"
    elif dataset == "building_permits":
        title = record.get("permit_type") or record.get("review_type") or "Building Permit"
    elif dataset == "business_licenses":
        title = record.get("doing_business_as_name") or "Business License"
    else:
        title = dataset.replace("_", " ").title()

    content_parts = []
    for key, value in record.items():
        if value and not key.startswith(":") and key != "location":
            content_parts.append(f"{key}: {value}")

    location = record.get("location") if isinstance(record.get("location"), dict) else {}
    lat = record.get("latitude") or location.get("latitude")
    lng = record.get("longitude") or location.get("longitude")
    if lng is None and isinstance(location.get("coordinates"), list) and len(location["coordinates"]) >= 2:
        lng = location["coordinates"][0]
        lat = lat or location["coordinates"][1]
    address = record.get("address") or " ".join(
        str(record.get(part, "") or "").strip()
        for part in ("street_number", "street_direction", "street_name")
    ).strip()

    return {
        "id": f"public-{dataset}-{record_id}",
        "source": "public_data",
        "title": str(title),
        "content": "\n".join(content_parts[:20]),
        "timestamp": timestamp,
        "metadata": {
            "dataset": dataset,
            "dataset_id": SOCRATA_DATASETS.get(dataset, ""),
            "raw_record": record,
        },
        "geo": {
            "lat": lat,
            "lng": lng,
            "neighborhood": detect_neighborhood(address),
            "community_area": record.get("community_area", ""),
            "ward": record.get("ward", ""),
        },
    }


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
    if not neighborhood:
        return docs

    return [doc for doc in docs if _doc_matches_neighborhood(doc, neighborhood)]


def is_placeholder_doc(doc: dict) -> bool:
    metadata = doc.get("metadata", {}) or {}
    return bool(metadata.get("is_placeholder") or metadata.get("placeholder"))


def _normalize_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _target_names(neighborhood: str) -> set[str]:
    name = _normalize_text(neighborhood)
    names = {name} if name else set()
    ca = neighborhood_to_ca(neighborhood)
    if ca:
        try:
            ca_name = COMMUNITY_AREA_MAP.get(int(ca), "")
        except (TypeError, ValueError):
            ca_name = ""
        normalized = _normalize_text(ca_name)
        if normalized:
            names.add(normalized)
    return names


def _structured_location_values(doc: dict) -> list[object]:
    metadata = doc.get("metadata", {}) or {}
    raw = metadata.get("raw_record", {}) or {}
    geo = doc.get("geo", {}) or {}
    values = []
    for source in (geo, metadata, raw):
        for key in (
            "neighborhood",
            "query_neighborhood",
            "community_area_name",
            "community_area",
            "community",
        ):
            value = source.get(key)
            if value not in (None, ""):
                values.append(value)
    return values


def _structured_value_matches(value: object, names: set[str], community_area: str) -> bool:
    normalized = _normalize_text(value)
    if not normalized:
        return False
    if normalized in names:
        return True
    if community_area and normalized == community_area:
        return True
    if community_area and normalized.isdigit() and str(int(normalized)) == community_area:
        return True
    return False


def _extract_lat_lng(doc: dict) -> tuple[float, float] | None:
    metadata = doc.get("metadata", {}) or {}
    raw = metadata.get("raw_record", {}) or {}
    geo = doc.get("geo", {}) or {}

    lat_candidates = (
        geo.get("lat"),
        geo.get("latitude"),
        doc.get("lat"),
        doc.get("latitude"),
        raw.get("latitude"),
        raw.get("lat"),
    )
    lng_candidates = (
        geo.get("lng"),
        geo.get("lon"),
        geo.get("longitude"),
        doc.get("lng"),
        doc.get("lon"),
        doc.get("longitude"),
        raw.get("longitude"),
        raw.get("lng"),
        raw.get("lon"),
    )

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


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius_km = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlng / 2) ** 2
    )
    return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def neighborhood_from_coordinates(
    lat: float,
    lng: float,
    *,
    max_distance_km: float = NEIGHBORHOOD_COORDINATE_RADIUS_KM,
) -> str:
    """Return the nearest Chicago neighborhood centroid within the accepted radius."""
    closest_name = ""
    closest_distance = float("inf")
    for neighborhood, centroid in NEIGHBORHOOD_CENTROIDS.items():
        clat, clng = centroid
        distance = _haversine_km(lat, lng, clat, clng)
        if distance < closest_distance:
            closest_name = neighborhood
            closest_distance = distance
    return closest_name if closest_distance <= max_distance_km else ""


def _coordinate_matches_neighborhood(doc: dict, neighborhood: str) -> bool:
    coords = _extract_lat_lng(doc)
    neighborhood_key = next(
        (
            name
            for name in NEIGHBORHOOD_CENTROIDS
            if name.lower() == (neighborhood or "").strip().lower()
        ),
        (neighborhood or "").strip(),
    )
    centroid = NEIGHBORHOOD_CENTROIDS.get(neighborhood_key)
    if coords is None or centroid is None:
        return False
    lat, lng = coords
    clat, clng = centroid
    return _haversine_km(lat, lng, clat, clng) <= NEIGHBORHOOD_COORDINATE_RADIUS_KM


def _text_mentions_neighborhood(doc: dict, neighborhood: str) -> bool:
    name = (neighborhood or "").strip()
    if len(name) < 5:
        return False

    text = f"{doc.get('title', '')} {str(doc.get('content', '') or '')[:500]}".lower()
    pattern = re.compile(rf"(?<![a-z0-9]){re.escape(name.lower())}(?![a-z0-9])")
    return bool(pattern.search(text))


def _doc_matches_neighborhood(doc: dict, neighborhood: str) -> bool:
    names = _target_names(neighborhood)
    community_area = neighborhood_to_ca(neighborhood)
    structured_values = _structured_location_values(doc)

    if structured_values:
        return any(_structured_value_matches(value, names, community_area) for value in structured_values)

    if _coordinate_matches_neighborhood(doc, neighborhood):
        return True

    return _text_mentions_neighborhood(doc, neighborhood)


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
    processed_dir = get_processed_data_dir()
    candidate_paths = [
        processed_dir / "demographics_summary.json",
        processed_dir / "summaries" / "demographics_summary.json",
    ]

    def _loader() -> dict:
        return load_first_existing_json(candidate_paths, default={})

    return copy.deepcopy(cache.get_or_set(f"demographics:summary:{processed_dir}", 60.0, _loader))


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
    processed_dir = get_processed_data_dir()
    cache_path = processed_dir / "cache" / "cta_stations.json"

    def _loader() -> list[dict]:
        for candidate in (Path("/data/processed/cache/cta_stations.json"), cache_path):
            cached = load_json_file(candidate, default=None)
            if isinstance(cached, list):
                return cached

        try:
            url = "https://data.cityofchicago.org/resource/8pix-ypme.json?$select=station_name,location&$limit=500"
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

            try:
                write_json_file(cache_path, deduped)
            except Exception as exc:
                print(f"_load_cta_stations: cache write failed: {exc}")
            return deduped
        except Exception as exc:
            print(f"_load_cta_stations: fetch failed: {exc}")
            return []

    cache_key = f"cta:stations:{CTA_STATION_CACHE_VERSION}:{processed_dir}"
    stations = cache.get_or_set(cache_key, 3600.0, _loader)
    if not stations:
        cache.invalidate(cache_key)
    return copy.deepcopy(stations)


def _normalize_station_name(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", _normalize_text(value))


def _coerce_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def cta_ridership_by_station_from_docs(docs: list[dict]) -> dict[str, dict]:
    """Build a latest-month CTA ridership lookup keyed by normalized station name."""
    stations: dict[str, dict] = {}

    for doc in docs:
        if not isinstance(doc, dict):
            continue
        raw = doc.get("metadata", {}).get("raw_record", {}) or {}
        if not isinstance(raw, dict):
            raw = {}

        station_name = (
            raw.get("stationame")
            or raw.get("station_name")
            or raw.get("station")
            or doc.get("title")
            or ""
        )
        station_key = _normalize_station_name(station_name)
        if not station_key:
            continue

        avg_weekday_rides = 0.0
        for key in ("avg_weekday_rides", "average_weekday_rides", "weekday_rides"):
            avg_weekday_rides = _coerce_float(raw.get(key))
            if avg_weekday_rides > 0:
                break
        if avg_weekday_rides == 0:
            avg_weekday_rides = _coerce_float(raw.get("monthtotal")) / 30
        if avg_weekday_rides <= 0:
            continue

        timestamp = str(
            raw.get("month_beginning")
            or raw.get("month")
            or doc.get("timestamp")
            or ""
        )
        existing = stations.get(station_key)
        if existing and timestamp < str(existing.get("timestamp", "")):
            continue

        stations[station_key] = {
            "station_name": str(station_name),
            "avg_weekday_rides": round(avg_weekday_rides),
            "timestamp": timestamp,
        }

    return stations


def load_cta_ridership_by_station(*, allow_raw_scan: bool = False) -> dict[str, dict]:
    processed_dir = get_processed_data_dir()
    cache_path = processed_dir / "cache" / "cta_l_ridership_by_station.json"
    mounted_cache_path = Path("/data/processed/cache/cta_l_ridership_by_station.json")

    def _loader() -> dict[str, dict]:
        for candidate in (mounted_cache_path, cache_path):
            cached = load_json_file(candidate, default=None)
            if isinstance(cached, dict):
                stations = cached.get("stations")
                if isinstance(stations, dict):
                    return {str(key): value for key, value in stations.items() if isinstance(value, dict)}
                return {str(key): value for key, value in cached.items() if isinstance(value, dict)}

        if not allow_raw_scan:
            return {}

        docs = load_public_dataset_docs("cta_ridership_L", limit=1000)
        stations = cta_ridership_by_station_from_docs(docs)
        if stations:
            try:
                write_json_file(cache_path, {"stations": stations})
            except Exception as exc:
                print(f"_load_cta_ridership_by_station: cache write failed: {exc}")
        return stations

    cache_mode = "scan" if allow_raw_scan else "cached"
    return copy.deepcopy(cache.get_or_set(f"cta:ridership:{processed_dir}:{cache_mode}", 3600.0, _loader))


def compute_transit_score(neighborhood_name: str) -> dict:
    import math

    from modal_app.common import NEIGHBORHOOD_CENTROIDS

    processed_dir = get_processed_data_dir()

    def _compute() -> dict:
        neighborhood_key = next(
            (
                name
                for name in NEIGHBORHOOD_CENTROIDS
                if name.lower() == (neighborhood_name or "").strip().lower()
            ),
            (neighborhood_name or "").strip(),
        )
        centroid = NEIGHBORHOOD_CENTROIDS.get(neighborhood_key)
        if not centroid:
            return {"stations_nearby": 0, "total_daily_riders": 0, "transit_score": 0, "station_names": []}

        clat, clng = centroid
        stations = load_cta_stations()
        nearby_by_name: dict[str, dict] = {}
        for station in stations:
            try:
                slat = float(station["lat"])
                slng = float(station["lng"])
            except (KeyError, TypeError, ValueError):
                continue
            dlat = math.radians(slat - clat)
            dlng = math.radians(slng - clng)
            a = (
                math.sin(dlat / 2) ** 2
                + math.cos(math.radians(clat))
                * math.cos(math.radians(slat))
                * math.sin(dlng / 2) ** 2
            )
            dist_km = 6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            if dist_km <= 3.0:
                name = str(station.get("station_name") or "").strip()
                key = _normalize_station_name(name)
                if key and (key not in nearby_by_name or dist_km < nearby_by_name[key]["distance_km"]):
                    nearby_by_name[key] = {**station, "station_name": name, "distance_km": dist_km}

        nearby = sorted(nearby_by_name.values(), key=lambda station: (station["distance_km"], station["station_name"]))
        if not nearby:
            return {"stations_nearby": 0, "total_daily_riders": 0, "transit_score": 0, "station_names": []}

        ridership_by_station = load_cta_ridership_by_station()
        total_rides = 0
        for station in nearby:
            ridership = ridership_by_station.get(_normalize_station_name(station["station_name"]))
            if not ridership:
                continue
            total_rides += int(_coerce_float(ridership.get("avg_weekday_rides")))

        transit_score = min(100, round((total_rides / 10000) * 100)) if total_rides > 0 else 0
        if transit_score == 0:
            transit_score = min(100, len(nearby) * 20)

        return {
            "stations_nearby": len(nearby),
            "total_daily_riders": total_rides,
            "transit_score": transit_score,
            "station_names": [station["station_name"] for station in nearby],
        }

    cache_key = f"cta:transit-score:{CTA_TRANSIT_SCORE_CACHE_VERSION}:{processed_dir}:{neighborhood_name}"
    result = cache.get_or_set(cache_key, 3600.0, _compute)
    if not result.get("stations_nearby"):
        cache.invalidate(cache_key)
    return copy.deepcopy(result)


def get_source_stats() -> dict[str, dict]:
    """Shared source scan used by status/metrics/sources/summary."""
    raw_dir = get_raw_data_dir()

    def _loader() -> dict[str, dict]:
        return scan_source_directories(
            {source: raw_dir / source for source in NON_SENSOR_PIPELINE_SOURCES}
        )

    raw_stats = cache.get_or_set(f"sources:stats:{raw_dir}", 15.0, _loader)
    copied: dict[str, dict] = {}
    for source, data in raw_stats.items():
        copied[source] = {
            "doc_count": data["doc_count"],
            "active": data["active"],
            "last_update": data["last_update"],
            "neighborhoods_covered": set(data["neighborhoods_covered"]),
        }
    return copied
