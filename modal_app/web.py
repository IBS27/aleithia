"""Modal-hosted FastAPI web API — composed from route modules."""
from __future__ import annotations

import json
from pathlib import Path

import modal
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from modal_app.api.routes import neighborhoods as neighborhoods_routes
from modal_app.api.routes import vision as vision_routes
from modal_app.api.routes.analysis import router as analysis_router
from modal_app.api.routes.command import command_synthesis, router as command_router
from modal_app.api.routes.core import router as core_router
from modal_app.api.routes.graph import router as graph_router
from modal_app.api.routes.legacy import router as legacy_router
from modal_app.api.routes.neighborhoods import router as neighborhoods_router
from modal_app.api.routes.vision import router as vision_router
from modal_app.api.services import cctv as cctv_service
from modal_app.api.services.metrics import (
    compute_metrics as _compute_metrics,
    compute_risk_wlc as _compute_risk_wlc,
    logistic as _logistic,
)
from modal_app.common import NEIGHBORHOOD_CENTROIDS
from modal_app.volume import app, volume, web_image

web_app = FastAPI(title="Aleithia API", version="2.0")

web_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (
    legacy_router,
    neighborhoods_router,
    core_router,
    vision_router,
    graph_router,
    analysis_router,
    command_router,
):
    web_app.include_router(router)


# Legacy module-level compatibility exports for tests and older callers.
CCTV_LATEST_INDEX_PATH = cctv_service.CCTV_LATEST_INDEX_PATH
CCTV_NEIGHBORHOOD_CAMERA_LIMIT = cctv_service.CCTV_NEIGHBORHOOD_CAMERA_LIMIT
RAW_DATA_PATH = None
PROCESSED_DATA_PATH = None

_analysis_timestamp_epoch = cctv_service.analysis_timestamp_epoch
_load_docs = neighborhoods_routes.load_docs
_rank_tiktok_docs = neighborhoods_routes.rank_tiktok_docs
_rank_social_docs_deterministic = neighborhoods_routes._rank_social_docs_deterministic
_parse_social_trends_response = neighborhoods_routes._parse_social_trends_response
_deterministic_social_fallback_trends = neighborhoods_routes._deterministic_social_fallback_trends
_score_social_doc = neighborhoods_routes._score_social_doc
_parse_view_count = neighborhoods_routes.parse_view_count
_load_fake_cctv = cctv_service.load_synthetic_cctv
_fake_cctv_entry = cctv_service.synthetic_cctv_entry
rank_reddit_docs = neighborhoods_routes.rank_reddit_docs


async def _reload_volume_compat() -> None:
    reload_attr = getattr(volume, "reload", None)
    if reload_attr is None:
        return

    aio = getattr(reload_attr, "aio", None)
    if callable(aio):
        await aio()
        return

    result = reload_attr()
    if hasattr(result, "__await__"):
        await result


async def _load_cctv_latest_index() -> dict[str, dict]:
    await _reload_volume_compat()

    if CCTV_LATEST_INDEX_PATH is None:
        return await cctv_service.load_cctv_latest_index()

    index_path = Path(CCTV_LATEST_INDEX_PATH)
    if not index_path.exists():
        return {}

    try:
        parsed = json.loads(index_path.read_text())
    except Exception:
        return {}

    if not isinstance(parsed, dict):
        return {}

    normalized: dict[str, dict] = {}
    for camera_id, payload in parsed.items():
        if not isinstance(payload, dict):
            continue
        normalized[str(payload.get("camera_id", camera_id) or camera_id)] = payload
    return normalized


async def _load_cctv_for_neighborhood(name: str) -> dict:
    original_state = (
        cctv_service.volume,
        cctv_service.CCTV_LATEST_INDEX_PATH,
        cctv_service.CCTV_NEIGHBORHOOD_CAMERA_LIMIT,
        cctv_service.load_cctv_latest_index,
        cctv_service.synthetic_cctv_entry,
    )
    try:
        cctv_service.volume = volume
        cctv_service.CCTV_LATEST_INDEX_PATH = Path(CCTV_LATEST_INDEX_PATH) if CCTV_LATEST_INDEX_PATH is not None else None
        cctv_service.CCTV_NEIGHBORHOOD_CAMERA_LIMIT = CCTV_NEIGHBORHOOD_CAMERA_LIMIT
        cctv_service.load_cctv_latest_index = _load_cctv_latest_index
        cctv_service.synthetic_cctv_entry = _fake_cctv_entry
        return await cctv_service.load_cctv_for_neighborhood(name)
    finally:
        (
            cctv_service.volume,
            cctv_service.CCTV_LATEST_INDEX_PATH,
            cctv_service.CCTV_NEIGHBORHOOD_CAMERA_LIMIT,
            cctv_service.load_cctv_latest_index,
            cctv_service.synthetic_cctv_entry,
        ) = original_state


async def _aggregate_timeseries_for_neighborhood(name: str, camera_ids: list[str] | None = None) -> dict:
    original_state = (
        cctv_service.volume,
        cctv_service.load_synthetic_cctv,
        cctv_service.synthetic_cctv_entry,
    )
    try:
        cctv_service.volume = volume
        cctv_service.load_synthetic_cctv = _load_fake_cctv
        cctv_service.synthetic_cctv_entry = _fake_cctv_entry
        return await cctv_service.aggregate_timeseries_for_neighborhood(name, camera_ids=camera_ids)
    finally:
        (
            cctv_service.volume,
            cctv_service.load_synthetic_cctv,
            cctv_service.synthetic_cctv_entry,
        ) = original_state


async def cctv_latest():
    latest_by_cam = await _load_cctv_latest_index()
    if not latest_by_cam:
        return {"cameras": [], "count": 0}

    cameras = sorted(
        latest_by_cam.values(),
        key=lambda data: _analysis_timestamp_epoch(data, fallback_mtime=0.0),
        reverse=True,
    )
    return {"cameras": cameras, "count": len(cameras)}


async def social_trends(neighborhood: str, business_type: str = ""):
    original_state = (
        neighborhoods_routes.volume,
        neighborhoods_routes.load_docs,
        neighborhoods_routes.rank_reddit_docs,
        neighborhoods_routes.rank_tiktok_docs,
        neighborhoods_routes._rank_social_docs_deterministic,
        neighborhoods_routes._parse_social_trends_response,
        neighborhoods_routes._deterministic_social_fallback_trends,
    )
    try:
        neighborhoods_routes.volume = volume
        neighborhoods_routes.load_docs = _load_docs
        neighborhoods_routes.rank_reddit_docs = rank_reddit_docs
        neighborhoods_routes.rank_tiktok_docs = _rank_tiktok_docs
        neighborhoods_routes._rank_social_docs_deterministic = _rank_social_docs_deterministic
        neighborhoods_routes._parse_social_trends_response = _parse_social_trends_response
        neighborhoods_routes._deterministic_social_fallback_trends = _deterministic_social_fallback_trends
        return await neighborhoods_routes.social_trends(neighborhood, business_type)
    finally:
        (
            neighborhoods_routes.volume,
            neighborhoods_routes.load_docs,
            neighborhoods_routes.rank_reddit_docs,
            neighborhoods_routes.rank_tiktok_docs,
            neighborhoods_routes._rank_social_docs_deterministic,
            neighborhoods_routes._parse_social_trends_response,
            neighborhoods_routes._deterministic_social_fallback_trends,
        ) = original_state


async def vision_assess(neighborhood: str):
    original_state = (
        vision_routes.volume,
        vision_routes.RAW_DATA_PATH,
        vision_routes.PROCESSED_DATA_PATH,
    )
    try:
        vision_routes.volume = volume
        if RAW_DATA_PATH is not None:
            vision_routes.RAW_DATA_PATH = RAW_DATA_PATH
        if PROCESSED_DATA_PATH is not None:
            vision_routes.PROCESSED_DATA_PATH = PROCESSED_DATA_PATH
        return await vision_routes.vision_assess(neighborhood)
    finally:
        (
            vision_routes.volume,
            vision_routes.RAW_DATA_PATH,
            vision_routes.PROCESSED_DATA_PATH,
        ) = original_state


@app.function(
    image=web_image,
    volumes={"/data": volume},
    secrets=[modal.Secret.from_name("alethia-secrets"), modal.Secret.from_name("arize-secrets")],
)
@modal.asgi_app()
def serve():
    """Modal-hosted FastAPI application."""
    from modal_app.instrumentation import init_tracing

    init_tracing()
    return web_app
