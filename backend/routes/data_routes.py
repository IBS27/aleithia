"""
Routes that serve ingested Chicago data from local JSON files.
Data was downloaded from Modal Volume after pipeline runs.
"""

import json
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter()

DATA_DIR = Path(__file__).parent.parent / "data"
SETTINGS_FILE = Path(__file__).parent.parent / "user_settings.json"


class UserSettings(BaseModel):
    location_type: str = Field(..., min_length=1)
    neighborhood: str = Field(..., min_length=1)


class UserSettingsResponse(UserSettings):
    user_id: str


def _read_settings_store() -> dict[str, dict[str, str]]:
    if not SETTINGS_FILE.exists():
        return {}
    try:
        with open(SETTINGS_FILE) as fh:
            payload = json.load(fh)
            if isinstance(payload, dict):
                return payload
            return {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_settings_store(data: dict[str, dict[str, str]]) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, "w") as fh:
        json.dump(data, fh, indent=2)


def _require_user_id(x_user_id: Optional[str]) -> str:
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing x-user-id header")
    return x_user_id


def _load_all(source: str) -> list[dict]:
    """Load all valid JSON files from a source directory."""
    source_dir = DATA_DIR / source
    if not source_dir.exists():
        return []
    docs = []
    for f in sorted(source_dir.iterdir()):
        if f.suffix != ".json":
            continue
        try:
            with open(f) as fh:
                doc = json.load(fh)
                docs.append(doc)
        except (json.JSONDecodeError, OSError):
            continue
    return docs


def _filter_by_neighborhood(docs: list[dict], neighborhood: str) -> list[dict]:
    """Filter documents that match a neighborhood (case-insensitive).
    Checks geo fields, content, metadata, and address info."""
    nb = neighborhood.lower()
    results = []
    for doc in docs:
        geo = doc.get("geo", {})
        doc_nb = (geo.get("neighborhood") or "").lower()
        doc_ca = (geo.get("community_area_name") or "").lower()
        content = (doc.get("content") or "").lower()
        # Also check raw_record for address fields
        raw = doc.get("metadata", {}).get("raw_record", {})
        address = (raw.get("address") or "").lower()
        title = (doc.get("title") or "").lower()
        community = (raw.get("community_area_name") or "").lower()
        if nb in doc_nb or nb in doc_ca or nb in content or nb in address or nb in title or nb in community:
            results.append(doc)
    return results


def _filter_by_type(docs: list[dict], dataset: str) -> list[dict]:
    """Filter public_data docs by dataset type (e.g. food_inspections)."""
    return [
        d for d in docs
        if d.get("metadata", {}).get("dataset") == dataset
    ]


@router.get("/user/settings", response_model=UserSettingsResponse)
async def get_user_settings(x_user_id: Optional[str] = Header(default=None)):
    """Get saved query settings for a user."""
    user_id = _require_user_id(x_user_id)
    store = _read_settings_store()
    entry = store.get(user_id)
    if not entry:
        raise HTTPException(status_code=404, detail="No settings found for user")
    return {
        "user_id": user_id,
        "location_type": entry.get("location_type", ""),
        "neighborhood": entry.get("neighborhood", ""),
    }


@router.put("/user/settings", response_model=UserSettingsResponse)
async def put_user_settings(payload: UserSettings, x_user_id: Optional[str] = Header(default=None)):
    """Save last queried settings for a user."""
    user_id = _require_user_id(x_user_id)
    store = _read_settings_store()
    store[user_id] = {
        "location_type": payload.location_type,
        "neighborhood": payload.neighborhood,
    }
    _write_settings_store(store)
    return {
        "user_id": user_id,
        "location_type": payload.location_type,
        "neighborhood": payload.neighborhood,
    }


@router.get("/sources")
async def get_sources():
    """Return available data sources with counts."""
    sources = {}
    for name in ["public_data", "demographics", "politics", "news", "realestate"]:
        d = DATA_DIR / name
        if d.exists():
            count = sum(1 for f in d.iterdir() if f.suffix == ".json")
            sources[name] = {"count": count, "active": count > 0}
        else:
            sources[name] = {"count": 0, "active": False}

    # Add sources we don't have data for yet
    for name in ["reddit", "reviews"]:
        sources[name] = {"count": 0, "active": False}

    return sources


@router.get("/geo")
async def get_geo():
    """Return GeoJSON FeatureCollection for map visualization."""
    geo_path = DATA_DIR / "processed" / "geo" / "neighborhood_metrics.json"
    if geo_path.exists():
        with open(geo_path) as f:
            return json.load(f)
    return {"type": "FeatureCollection", "features": []}


@router.get("/summary")
async def get_summary():
    """Return compressed data summaries."""
    summaries = {}
    summary_dir = DATA_DIR / "processed" / "summaries"
    if summary_dir.exists():
        for f in summary_dir.iterdir():
            if f.suffix == ".json":
                with open(f) as fh:
                    key = f.stem.replace("_summary", "")
                    summaries[key] = json.load(fh)
    return summaries


@router.get("/inspections")
async def get_inspections(
    neighborhood: Optional[str] = Query(None),
    result: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
):
    """Return food inspection records."""
    docs = _filter_by_type(_load_all("public_data"), "food_inspections")
    if neighborhood:
        docs = _filter_by_neighborhood(docs, neighborhood)
    if result:
        docs = [
            d for d in docs
            if d.get("metadata", {}).get("raw_record", {}).get("results", "").lower() == result.lower()
        ]
    return docs[:limit]


@router.get("/permits")
async def get_permits(
    neighborhood: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
):
    """Return building permit records."""
    docs = _filter_by_type(_load_all("public_data"), "building_permits")
    if neighborhood:
        docs = _filter_by_neighborhood(docs, neighborhood)
    return docs[:limit]


@router.get("/licenses")
async def get_licenses(
    neighborhood: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
):
    """Return business license records."""
    docs = _filter_by_type(_load_all("public_data"), "business_licenses")
    if neighborhood:
        docs = _filter_by_neighborhood(docs, neighborhood)
    return docs[:limit]


@router.get("/demographics")
async def get_demographics(limit: int = Query(50, le=200)):
    """Return Census demographics data."""
    return _load_all("demographics")[:limit]


@router.get("/news")
async def get_news(limit: int = Query(20, le=100)):
    """Return news articles."""
    docs = _load_all("news")
    # Sort by timestamp descending
    docs.sort(key=lambda d: d.get("timestamp", ""), reverse=True)
    return docs[:limit]


@router.get("/politics")
async def get_politics(limit: int = Query(50, le=200)):
    """Return political/legislative records."""
    docs = _load_all("politics")
    docs.sort(key=lambda d: d.get("timestamp", ""), reverse=True)
    return docs[:limit]


@router.get("/neighborhood/{name}")
async def get_neighborhood(name: str):
    """Return all data for a specific neighborhood."""
    all_public = _load_all("public_data")

    all_inspections = _filter_by_type(all_public, "food_inspections")
    inspections = _filter_by_neighborhood(all_inspections, name)
    # If no neighborhood-specific inspections, show all (data lacks geo tags)
    if not inspections:
        inspections = all_inspections

    all_permits = _filter_by_type(all_public, "building_permits")
    permits = _filter_by_neighborhood(all_permits, name)
    if not permits:
        permits = all_permits

    all_licenses = _filter_by_type(all_public, "business_licenses")
    licenses = _filter_by_neighborhood(all_licenses, name)
    if not licenses:
        licenses = all_licenses

    all_news = _load_all("news")
    news = _filter_by_neighborhood(all_news, name)
    if not news:
        news = all_news

    all_politics = _load_all("politics")
    politics = _filter_by_neighborhood(all_politics, name)
    if not politics:
        politics = all_politics

    # Get demographics from GeoJSON
    demo = {}
    geo_path = DATA_DIR / "processed" / "geo" / "neighborhood_metrics.json"
    if geo_path.exists():
        with open(geo_path) as f:
            geojson = json.load(f)
            for feature in geojson.get("features", []):
                props = feature.get("properties", {})
                if props.get("neighborhood", "").lower() == name.lower():
                    demo = props
                    break

    return {
        "neighborhood": name,
        "metrics": demo,
        "inspections": inspections[:20],
        "permits": permits[:20],
        "licenses": licenses[:20],
        "news": news[:10],
        "politics": politics[:10],
        "inspection_stats": {
            "total": len(inspections),
            "failed": sum(
                1 for d in inspections
                if d.get("metadata", {}).get("raw_record", {}).get("results") == "Fail"
            ),
            "passed": sum(
                1 for d in inspections
                if d.get("metadata", {}).get("raw_record", {}).get("results") == "Pass"
            ),
        },
        "permit_count": len(permits),
        "license_count": len(licenses),
    }
