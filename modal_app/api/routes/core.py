"""Core read-only API routes for status, metrics, and simple data lists."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import modal
from fastapi import APIRouter

from modal_app.api.services.documents import (
    NON_SENSOR_PIPELINE_SOURCES,
    aggregate_city_demographics,
    filter_by_neighborhood,
    get_source_stats,
    load_docs,
)
from modal_app.runtime import ENABLE_ALETHIA_LLM
from modal_app.volume import PROCESSED_DATA_PATH, RAW_DATA_PATH

router = APIRouter()


@router.get("/status")
async def status():
    """Pipeline monitor — shows function states, doc counts, GPU status."""
    pipeline_status = {}
    for source, data in get_source_stats().items():
        pipeline_status[source] = {
            "doc_count": data["doc_count"],
            "last_update": data["last_update"],
            "state": "idle" if data["active"] else "no_data",
        }

    enriched_dir = Path(PROCESSED_DATA_PATH) / "enriched"
    enriched_count = len(list(enriched_dir.rglob("*.json"))) if enriched_dir.exists() else 0

    costs = {}
    try:
        cost_dict = modal.Dict.from_name("alethia-costs", create_if_missing=True)
        async for key in cost_dict.keys.aio():
            costs[key] = await cost_dict.get.aio(key)
    except Exception:
        pass

    return {
        "pipelines": pipeline_status,
        "enriched_docs": enriched_count,
        "gpu_status": {
            "h100_llm": "disabled" if not ENABLE_ALETHIA_LLM else "available",
            "t4_classifier": "available",
            "t4_sentiment": "available",
            "t4_cctv": "available",
        },
        "costs": costs,
        "total_docs": sum(item.get("doc_count", 0) for item in pipeline_status.values()),
    }


@router.get("/metrics")
async def metrics():
    """Scale numbers for demo display."""
    source_stats = get_source_stats()
    neighborhoods_covered = set()
    total_docs = 0
    sources_active = 0
    for data in source_stats.values():
        total_docs += data["doc_count"]
        if data["active"]:
            sources_active += 1
        neighborhoods_covered.update(data["neighborhoods_covered"])

    return {
        "total_documents": total_docs,
        "active_pipelines": sources_active,
        "neighborhoods_covered": len(neighborhoods_covered),
        "data_sources": len(NON_SENSOR_PIPELINE_SOURCES),
        "neighborhoods_total": 77,
    }


@router.get("/sources")
async def sources():
    """Available data sources with counts."""
    return {
        source: {"count": data["doc_count"], "active": data["active"]}
        for source, data in get_source_stats().items()
    }


@router.get("/news")
async def news_list():
    return load_docs("news", limit=50)


@router.get("/politics")
async def politics_list():
    return load_docs("politics", limit=50)


@router.get("/inspections")
async def inspections_list(neighborhood: str = "", result: str = ""):
    public_docs = load_docs("public_data", limit=500)
    inspections = [doc for doc in public_docs if doc.get("metadata", {}).get("dataset") == "food_inspections"]
    if neighborhood:
        inspections = filter_by_neighborhood(inspections, neighborhood)
    if result:
        inspections = [
            inspection
            for inspection in inspections
            if inspection.get("metadata", {}).get("raw_record", {}).get("results", "").lower() == result.lower()
        ]
    return inspections[:100]


@router.get("/permits")
async def permits_list(neighborhood: str = ""):
    public_docs = load_docs("public_data", limit=500)
    permits = [doc for doc in public_docs if doc.get("metadata", {}).get("dataset") == "building_permits"]
    if neighborhood:
        permits = filter_by_neighborhood(permits, neighborhood)
    return permits[:100]


@router.get("/licenses")
async def licenses_list(neighborhood: str = ""):
    public_docs = load_docs("public_data", limit=500)
    licenses = [doc for doc in public_docs if doc.get("metadata", {}).get("dataset") == "business_licenses"]
    if neighborhood:
        licenses = filter_by_neighborhood(licenses, neighborhood)
    return licenses[:100]


@router.get("/reddit")
async def reddit_list(neighborhood: str = ""):
    docs = load_docs("reddit", limit=100)
    if neighborhood:
        docs = filter_by_neighborhood(docs, neighborhood)
    return docs[:100]


@router.get("/reviews")
async def reviews_list(neighborhood: str = ""):
    docs = load_docs("reviews", limit=100)
    if neighborhood:
        docs = filter_by_neighborhood(docs, neighborhood)
    return docs[:100]


@router.get("/realestate")
async def realestate_list(neighborhood: str = ""):
    docs = load_docs("realestate", limit=50)
    if neighborhood:
        docs = filter_by_neighborhood(docs, neighborhood)
    return docs[:50]


@router.get("/tiktok")
async def tiktok_list(neighborhood: str = ""):
    from modal_app.api.services.tiktok import is_low_quality_tiktok_doc, normalize_tiktok_doc

    docs = [normalize_tiktok_doc(doc) for doc in load_docs("tiktok", limit=50)]
    docs = [doc for doc in docs if not is_low_quality_tiktok_doc(doc)]
    if neighborhood:
        docs = filter_by_neighborhood(docs, neighborhood)
    return docs[:50]


@router.get("/traffic")
async def traffic_list(neighborhood: str = ""):
    del neighborhood
    return []


@router.get("/summary")
async def summary():
    source_stats = get_source_stats()
    total_docs = sum(data["doc_count"] for data in source_stats.values())
    source_counts = {source: data["doc_count"] for source, data in source_stats.items()}
    return {
        "total_documents": total_docs,
        "source_counts": source_counts,
        "demographics": aggregate_city_demographics(),
    }


@router.get("/geo")
async def geo():
    geo_path = Path(PROCESSED_DATA_PATH) / "geo" / "neighborhood_metrics.json"
    if geo_path.exists():
        return json.loads(geo_path.read_text())
    return {"type": "FeatureCollection", "features": []}


@router.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
