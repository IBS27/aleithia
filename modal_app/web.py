"""Modal-hosted FastAPI web API — composed from route modules."""
from __future__ import annotations

import modal
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from modal_app.api.routes.analysis import router as analysis_router
from modal_app.api.routes.core import router as core_router
from modal_app.api.routes.graph import router as graph_router
from modal_app.api.routes.legacy import router as legacy_router
from modal_app.api.routes.neighborhoods import router as neighborhoods_router
from modal_app.api.routes.vision import router as vision_router
from modal_app.api.services.metrics import (
    compute_metrics as _compute_metrics,
    compute_risk_wlc as _compute_risk_wlc,
    logistic as _logistic,
)
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
):
    web_app.include_router(router)


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
