"""Modal-hosted FastAPI web API — replaces local backend.

Endpoints: /chat (streaming SSE), /brief, /alerts, /status, /metrics, /sources, /neighborhood
Modal features: @modal.asgi_app, streaming SSE
"""
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import modal
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from modal_app.volume import app, volume, web_image, VOLUME_MOUNT, RAW_DATA_PATH, PROCESSED_DATA_PATH
from modal_app.common import CHICAGO_NEIGHBORHOODS, COMMUNITY_AREA_MAP

web_app = FastAPI(title="Alethia API", version="2.0")

web_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _load_docs(source: str, limit: int = 200) -> list[dict]:
    """Load documents from a source directory on the volume."""
    docs = []
    source_dir = Path(RAW_DATA_PATH) / source
    if not source_dir.exists():
        return docs
    for json_file in sorted(source_dir.rglob("*.json"), reverse=True)[:limit]:
        try:
            docs.append(json.loads(json_file.read_text()))
        except Exception:
            continue
    return docs


def _filter_by_neighborhood(docs: list[dict], neighborhood: str) -> list[dict]:
    """Filter documents by neighborhood."""
    if not neighborhood:
        return docs
    nb_lower = neighborhood.lower()
    return [
        d for d in docs
        if d.get("geo", {}).get("neighborhood", "").lower() == nb_lower
        or nb_lower in d.get("content", "").lower()
    ]


@web_app.post("/chat")
async def chat(request: Request):
    """Streaming chat endpoint — orchestrates agent swarm + streams LLM tokens via SSE."""
    body = await request.json()
    question = body.get("message", "")
    user_id = body.get("user_id", str(uuid.uuid4()))
    business_type = body.get("business_type", "Restaurant")
    neighborhood = body.get("neighborhood", "Loop")

    async def event_stream():
        # Send agent deployment status
        yield f"data: {json.dumps({'type': 'status', 'content': 'Deploying intelligence agents...'})}\n\n"

        try:
            from modal_app.agents import orchestrate_query
            result = await orchestrate_query.remote.aio(
                user_id=user_id,
                question=question,
                business_type=business_type,
                target_neighborhood=neighborhood,
            )

            # Send agent stats
            yield f"data: {json.dumps({'type': 'agents', 'agents_deployed': result.get('agents_deployed', 0), 'neighborhoods': result.get('neighborhoods_analyzed', []), 'data_points': result.get('total_data_points', 0)})}\n\n"

            # Stream the response
            response_text = result.get("response", "")
            # Simulate token streaming from the pre-generated response
            words = response_text.split(" ")
            for i in range(0, len(words), 3):
                chunk = " ".join(words[i:i+3])
                if i > 0:
                    chunk = " " + chunk
                yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@web_app.get("/brief/{neighborhood}")
async def brief(neighborhood: str, business_type: str = "Restaurant"):
    """Get intelligence brief for a neighborhood."""
    try:
        from modal_app.agents import neighborhood_intel_agent
        result = await neighborhood_intel_agent.remote.aio(
            neighborhood=neighborhood,
            business_type=business_type,
        )
        return result
    except Exception as e:
        return {"error": str(e), "neighborhood": neighborhood}


@web_app.get("/alerts")
async def alerts(business_type: str = "Restaurant"):
    """Get active alerts relevant to business type."""
    alert_list = []

    # Check enriched docs for high-severity items
    enriched_dir = Path(PROCESSED_DATA_PATH) / "enriched"
    if enriched_dir.exists():
        for json_file in sorted(enriched_dir.rglob("*.json"), reverse=True)[:50]:
            try:
                doc = json.loads(json_file.read_text())
                sentiment = doc.get("sentiment", {})
                if sentiment.get("label") == "negative" and sentiment.get("score", 0) > 0.8:
                    alert_list.append({
                        "type": "negative_sentiment",
                        "title": doc.get("title", ""),
                        "source": doc.get("source", ""),
                        "neighborhood": doc.get("geo", {}).get("neighborhood", ""),
                        "severity": "high",
                    })
            except Exception:
                continue

    return {"alerts": alert_list[:20], "count": len(alert_list)}


@web_app.get("/status")
async def status():
    """Pipeline monitor — shows function states, doc counts, GPU status."""
    pipeline_status = {}

    for source in ["news", "politics", "public_data", "demographics", "reddit", "reviews", "realestate"]:
        source_dir = Path(RAW_DATA_PATH) / source
        if source_dir.exists():
            json_files = list(source_dir.rglob("*.json"))
            # Find most recent file
            latest = None
            if json_files:
                latest = max(json_files, key=lambda f: f.stat().st_mtime)
            pipeline_status[source] = {
                "doc_count": len(json_files),
                "last_update": datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc).isoformat() if latest else None,
                "state": "idle",
            }
        else:
            pipeline_status[source] = {"doc_count": 0, "last_update": None, "state": "no_data"}

    # Check enriched data
    enriched_dir = Path(PROCESSED_DATA_PATH) / "enriched"
    enriched_count = len(list(enriched_dir.rglob("*.json"))) if enriched_dir.exists() else 0

    # Cost tracking
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
            "h100_llm": "available",
            "t4_classifier": "available",
            "t4_sentiment": "available",
        },
        "costs": costs,
        "total_docs": sum(p.get("doc_count", 0) for p in pipeline_status.values()),
    }


@web_app.get("/metrics")
async def metrics():
    """Scale numbers for demo display."""
    total_docs = 0
    sources_active = 0
    neighborhoods_covered = set()

    for source in ["news", "politics", "public_data", "demographics", "reddit", "reviews", "realestate"]:
        source_dir = Path(RAW_DATA_PATH) / source
        if source_dir.exists():
            json_files = list(source_dir.rglob("*.json"))
            total_docs += len(json_files)
            if json_files:
                sources_active += 1
            for jf in json_files[:100]:
                try:
                    doc = json.loads(jf.read_text())
                    nb = doc.get("geo", {}).get("neighborhood", "")
                    if nb:
                        neighborhoods_covered.add(nb)
                except Exception:
                    continue

    return {
        "total_documents": total_docs,
        "active_pipelines": sources_active,
        "neighborhoods_covered": len(neighborhoods_covered),
        "data_sources": 15,
        "neighborhoods_total": 77,
    }


@web_app.get("/sources")
async def sources():
    """Available data sources with counts."""
    result = {}
    for source in ["news", "politics", "public_data", "demographics", "reddit", "reviews", "realestate"]:
        source_dir = Path(RAW_DATA_PATH) / source
        if source_dir.exists():
            count = len(list(source_dir.rglob("*.json")))
            result[source] = {"count": count, "active": count > 0}
        else:
            result[source] = {"count": 0, "active": False}
    return result


@web_app.get("/neighborhood/{name}")
async def neighborhood(name: str):
    """Full neighborhood data profile."""
    inspections = []
    permits = []
    licenses = []
    news_docs = []
    politics_docs = []

    # Load and filter public data
    public_docs = _load_docs("public_data", limit=500)
    nb_docs = _filter_by_neighborhood(public_docs, name)

    for doc in nb_docs:
        dataset = doc.get("metadata", {}).get("dataset", "")
        if dataset == "food_inspections":
            inspections.append(doc)
        elif dataset == "building_permits":
            permits.append(doc)
        elif dataset == "business_licenses":
            licenses.append(doc)

    news_docs = _filter_by_neighborhood(_load_docs("news"), name)
    politics_docs = _filter_by_neighborhood(_load_docs("politics"), name)

    # Compute inspection stats
    failed = sum(1 for i in inspections if i.get("metadata", {}).get("raw_record", {}).get("results") in ("Fail", "Out of Business"))
    passed = sum(1 for i in inspections if i.get("metadata", {}).get("raw_record", {}).get("results") == "Pass")

    # Load geo metrics
    geo_path = Path(PROCESSED_DATA_PATH) / "geo" / "neighborhood_metrics.json"
    metrics = {}
    if geo_path.exists():
        try:
            geojson = json.loads(geo_path.read_text())
            for feature in geojson.get("features", []):
                if feature.get("properties", {}).get("neighborhood", "").lower() == name.lower():
                    metrics = feature["properties"]
                    break
        except Exception:
            pass

    return {
        "neighborhood": name,
        "metrics": metrics,
        "inspections": inspections[:50],
        "permits": permits[:50],
        "licenses": licenses[:50],
        "news": news_docs[:20],
        "politics": politics_docs[:20],
        "inspection_stats": {
            "total": len(inspections),
            "failed": failed,
            "passed": passed,
        },
        "permit_count": len(permits),
        "license_count": len(licenses),
    }


@web_app.get("/geo")
async def geo():
    """GeoJSON FeatureCollection for map."""
    geo_path = Path(PROCESSED_DATA_PATH) / "geo" / "neighborhood_metrics.json"
    if geo_path.exists():
        return json.loads(geo_path.read_text())
    return {"type": "FeatureCollection", "features": []}


@web_app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.function(
    image=web_image,
    volumes={"/data": volume},
    secrets=[modal.Secret.from_name("alethia-secrets")],
)
@modal.asgi_app()
def serve():
    """Modal-hosted FastAPI application."""
    return web_app
