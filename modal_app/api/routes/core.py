"""Core runtime status and health routes."""
from __future__ import annotations

from datetime import datetime, timezone

import modal
from fastapi import APIRouter

from modal_app.runtime import ENABLE_CCTV_ANALYSIS

router = APIRouter()


@router.get("/status")
async def status():
    """Runtime status for Modal-owned GPU and worker infrastructure."""
    costs = {}
    try:
        cost_dict = modal.Dict.from_name("alethia-costs", create_if_missing=True)
        async for key in cost_dict.keys.aio():
            costs[key] = await cost_dict.get.aio(key)
    except Exception:
        pass

    return {
        "gpu_status": {
            "h100_llm": "disabled",
            "t4_classifier": "available",
            "t4_sentiment": "available",
            "t4_cctv": "available" if ENABLE_CCTV_ANALYSIS else "disabled",
        },
        "costs": costs,
    }


@router.get("/traffic")
async def traffic_list(neighborhood: str = ""):
    del neighborhood
    return []


@router.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
