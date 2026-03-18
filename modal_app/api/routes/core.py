"""Core read-only API routes for status, metrics, and simple data lists."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import modal
from fastapi import APIRouter

from modal_app.api.services.documents import (
    NON_SENSOR_PIPELINE_SOURCES,
    get_source_stats,
)
from modal_app.runtime import ENABLE_ALETHIA_LLM
from modal_app.volume import PROCESSED_DATA_PATH

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


@router.get("/traffic")
async def traffic_list(neighborhood: str = ""):
    del neighborhood
    return []


@router.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
