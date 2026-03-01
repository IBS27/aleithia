"""Modal-hosted FastAPI web API — replaces local backend.

Endpoints: /chat (streaming SSE), /brief, /alerts, /status, /metrics, /sources, /neighborhood
           /news, /politics, /inspections, /permits, /licenses, /summary
Modal features: @modal.asgi_app, streaming SSE
"""
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import modal
from fastapi import FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from modal_app.volume import app, volume, web_image, VOLUME_MOUNT, RAW_DATA_PATH, PROCESSED_DATA_PATH
from modal_app.common import CHICAGO_NEIGHBORHOODS, COMMUNITY_AREA_MAP, detect_neighborhood, neighborhood_to_ca

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
            parsed = json.loads(json_file.read_text())
            if isinstance(parsed, dict):
                docs.append(parsed)
        except Exception as e:
            print(f"_load_docs [{source}]: corrupted JSON {json_file.name}: {e}")
            continue
    return docs


def _filter_by_neighborhood(docs: list[dict], neighborhood: str) -> list[dict]:
    """Filter documents by neighborhood with multi-strategy matching."""
    if not neighborhood:
        return docs
    nb_lower = neighborhood.lower()

    nb_community_area = neighborhood_to_ca(neighborhood)

    matched = []
    for d in docs:
        geo = d.get("geo", {})
        # Match by geo.neighborhood field
        if geo.get("neighborhood", "").lower() == nb_lower:
            matched.append(d)
            continue
        # Match by community_area number
        if nb_community_area and geo.get("community_area") == nb_community_area:
            matched.append(d)
            continue
        # Match by content text (check title first, then content)
        title = d.get("title", "").lower()
        if nb_lower in title:
            matched.append(d)
            continue
        # Content match — only for multi-word neighborhoods to avoid false positives
        if len(nb_lower) > 4 and nb_lower in d.get("content", "").lower()[:500]:
            matched.append(d)
            continue
    return matched


def _load_demographics_summary() -> dict:
    """Load pre-aggregated demographics summary (one file instead of 1300+ individual reads)."""
    summary_path = Path(PROCESSED_DATA_PATH) / "demographics_summary.json"
    if summary_path.exists():
        try:
            return json.loads(summary_path.read_text())
        except Exception as e:
            print(f"Failed to load demographics summary: {e}")
    return {}


def _aggregate_demographics(neighborhood: str) -> dict:
    """Look up pre-aggregated census demographics for a neighborhood."""
    summary = _load_demographics_summary()
    if not summary:
        return {}

    nb_community_area = neighborhood_to_ca(neighborhood)
    if nb_community_area and nb_community_area in summary.get("by_community_area", {}):
        return summary["by_community_area"][nb_community_area]

    return {}


def _compute_metrics(name: str, inspections: list, permits: list, licenses: list, news: list, politics: list, reviews: list | None = None) -> dict:
    """Compute neighborhood metrics from actual data instead of relying on pre-computed geo file."""
    total_inspections = len(inspections)
    failed = sum(1 for i in inspections if i.get("metadata", {}).get("raw_record", {}).get("results") in ("Fail", "Out of Business"))

    # Regulatory density: normalized inspection volume (0-100 scale)
    regulatory_density = min(100, total_inspections * 5) if total_inspections > 0 else 0

    # Business activity: normalized license count (0-100 scale)
    business_activity = min(100, len(licenses) * 8) if licenses else 0

    # Risk score: based on inspection fail rate
    fail_rate = (failed / total_inspections) if total_inspections > 0 else 0
    risk_score = round(min(10, 2 + fail_rate * 6 + (len(licenses) > 10) + (len(politics) > 3)), 1)

    # Sentiment: placeholder based on news volume (more news = more activity = higher)
    sentiment = min(100, len(news) * 10) if news else 0

    # Review rating from actual review docs
    ratings = [r.get("metadata", {}).get("rating", 0) for r in (reviews or []) if r.get("metadata", {}).get("rating")]
    avg_review_rating = round(sum(ratings) / len(ratings), 1) if ratings else 0.0

    return {
        "neighborhood": name,
        "regulatory_density": round(regulatory_density, 1),
        "business_activity": round(business_activity, 1),
        "sentiment": round(sentiment, 1),
        "risk_score": risk_score,
        "active_permits": len(permits),
        "crime_incidents_30d": 0,
        "avg_review_rating": avg_review_rating,
        "review_count": len(ratings),
    }


@web_app.post("/chat")
async def chat(request: Request):
    """Streaming chat endpoint — orchestrates agent swarm + streams LLM tokens via SSE."""
    from modal_app.instrumentation import get_tracer
    tracer = get_tracer("alethia.web")

    body = await request.json()
    question = body.get("message", "")

    if not question or not question.strip():
        return JSONResponse({"error": "message is required"}, status_code=400)
    if len(question) > 5000:
        return JSONResponse({"error": "message exceeds 5000 character limit"}, status_code=400)

    user_id = body.get("user_id", str(uuid.uuid4()))
    business_type = body.get("business_type", "Restaurant")
    neighborhood = body.get("neighborhood", "Loop")

    async def event_stream():
        # Send agent deployment status
        yield f"data: {json.dumps({'type': 'status', 'content': 'Deploying intelligence agents...'})}\n\n"

        span_ctx = tracer.start_as_current_span("chat-request") if tracer else None
        span = span_ctx.__enter__() if span_ctx else None
        try:
            if span:
                span.set_attribute("openinference.span.kind", "CHAIN")
                span.set_attribute("input.value", question)
                span.set_attribute("chat.business_type", business_type)
                span.set_attribute("chat.neighborhood", neighborhood)
            # Phase 1: Agent gathering (returns synthesis_messages, NOT response text)
            from modal_app.instrumentation import inject_context
            orchestrate_query = modal.Function.from_name("alethia", "orchestrate_query")
            result = await orchestrate_query.remote.aio(
                user_id=user_id,
                question=question,
                business_type=business_type,
                target_neighborhood=neighborhood,
                trace_context=inject_context(),
            )

            # Build per-agent summaries for frontend
            agent_summaries = []
            agent_results = result.get("context", {}).get("agent_results", {})
            for key, agent_result in agent_results.items():
                if isinstance(agent_result, dict) and "error" not in agent_result:
                    summary = {
                        "name": key,
                        "data_points": agent_result.get("data_points", 0),
                    }
                    if "findings" in agent_result:
                        summary["sources"] = list(agent_result["findings"].keys())
                    if "regulations" in agent_result:
                        summary["regulation_count"] = len(agent_result["regulations"])
                    agent_summaries.append(summary)
                else:
                    agent_summaries.append({"name": key, "data_points": 0, "error": True})

            # Send agent stats with per-agent breakdown
            yield f"data: {json.dumps({'type': 'agents', 'agents_deployed': result.get('agents_deployed', 0), 'neighborhoods': result.get('neighborhoods_analyzed', []), 'data_points': result.get('total_data_points', 0), 'agent_summaries': agent_summaries})}\n\n"

            # Status bridge between agents and LLM streaming
            yield f"data: {json.dumps({'type': 'status', 'content': 'Synthesizing intelligence report...'})}\n\n"

            # Phase 2: Real LLM streaming
            llm_cls = modal.Cls.from_name("alethia", "AlethiaLLM")
            llm = llm_cls()
            messages = result["synthesis_messages"]

            full_response = ""
            async for token in llm.generate_stream.remote_gen.aio(
                messages, max_tokens=2048, temperature=0.7
            ):
                full_response += token
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

            if span:
                span.set_attribute("output.value", full_response[:2000])
                span.set_attribute("chat.agents_deployed", result.get("agents_deployed", 0))
                span.set_attribute("chat.data_points", result.get("total_data_points", 0))

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

            # Store conversation in Supermemory (fire-and-forget)
            api_key = os.environ.get("SUPERMEMORY_API_KEY", "")
            if api_key:
                try:
                    from modal_app.supermemory import SupermemoryClient
                    sm = SupermemoryClient(api_key)
                    await sm.store_conversation(user_id, [
                        {"role": "user", "content": question},
                        {"role": "assistant", "content": full_response},
                    ])
                except Exception:
                    pass

        except Exception as e:
            if span:
                span.set_attribute("error", str(e))
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
        finally:
            if span_ctx:
                span_ctx.__exit__(None, None, None)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@web_app.get("/brief/{neighborhood}")
async def brief(neighborhood: str, business_type: str = "Restaurant"):
    """Get intelligence brief for a neighborhood."""
    from modal_app.instrumentation import get_tracer
    tracer = get_tracer("alethia.web")

    span_ctx = tracer.start_as_current_span("brief-request") if tracer else None
    span = span_ctx.__enter__() if span_ctx else None
    try:
        if span:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("input.value", f"{business_type} in {neighborhood}")
            span.set_attribute("brief.neighborhood", neighborhood)
            span.set_attribute("brief.business_type", business_type)

        from modal_app.instrumentation import inject_context
        neighborhood_intel_agent = modal.Function.from_name("alethia", "neighborhood_intel_agent")
        result = await neighborhood_intel_agent.remote.aio(
            neighborhood=neighborhood,
            business_type=business_type,
            trace_context=inject_context(),
        )

        if span:
            span.set_attribute("output.value", json.dumps({"data_points": result.get("data_points", 0)}))
        return result
    except Exception as e:
        if span:
            span.set_attribute("error", str(e))
        return {"error": str(e), "neighborhood": neighborhood}
    finally:
        if span_ctx:
            span_ctx.__exit__(None, None, None)


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

    for source in ["news", "politics", "public_data", "demographics", "reddit", "reviews", "realestate", "tiktok", "traffic", "cctv"]:
        source_dir = Path(RAW_DATA_PATH) / source
        if not source_dir.exists() and source == "traffic":
            # Traffic processed docs live under processed/traffic
            source_dir = Path(RAW_DATA_PATH) / "processed" / "traffic"
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
            "t4_cctv": "available",
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

    for source in ["news", "politics", "public_data", "demographics", "reddit", "reviews", "realestate", "tiktok", "traffic", "cctv"]:
        source_dir = Path(RAW_DATA_PATH) / source
        if not source_dir.exists() and source == "traffic":
            source_dir = Path(RAW_DATA_PATH) / "processed" / "traffic"
        if source_dir.exists():
            json_files = list(source_dir.rglob("*.json"))
            total_docs += len(json_files)
            if json_files:
                sources_active += 1
            for jf in json_files[:100]:
                try:
                    doc = json.loads(jf.read_text())
                    if not isinstance(doc, dict):
                        continue
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
    for source in ["news", "politics", "public_data", "demographics", "reddit", "reviews", "realestate", "tiktok", "traffic", "cctv"]:
        source_dir = Path(RAW_DATA_PATH) / source
        if not source_dir.exists() and source == "traffic":
            source_dir = Path(RAW_DATA_PATH) / "processed" / "traffic"
        if source_dir.exists():
            count = len(list(source_dir.rglob("*.json")))
            result[source] = {"count": count, "active": count > 0}
        else:
            result[source] = {"count": 0, "active": False}
    return result


def _load_cctv_for_neighborhood(name: str) -> dict:
    """Load latest CCTV analysis for cameras near a neighborhood."""
    from modal_app.common import NEIGHBORHOOD_CENTROIDS
    import math

    analysis_dir = Path(PROCESSED_DATA_PATH) / "cctv" / "analysis"
    if not analysis_dir.exists():
        return {"cameras": [], "avg_pedestrians": 0, "avg_vehicles": 0, "density": "unknown"}

    centroid = NEIGHBORHOOD_CENTROIDS.get(name)
    if not centroid:
        return {"cameras": [], "avg_pedestrians": 0, "avg_vehicles": 0, "density": "unknown"}

    clat, clng = centroid
    cameras = []

    # Group by camera_id, keep latest per camera
    latest_by_cam: dict[str, dict] = {}
    for jf in sorted(analysis_dir.glob("*.json"), reverse=True)[:200]:
        try:
            data = json.loads(jf.read_text())
            cam_id = data.get("camera_id", "")
            if cam_id in latest_by_cam:
                continue
            latest_by_cam[cam_id] = data
        except Exception:
            continue

    # Filter by distance (< 5km from neighborhood centroid)
    for cam_id, data in latest_by_cam.items():
        # Get lat/lng from raw metadata
        meta_dir = Path(RAW_DATA_PATH) / "cctv"
        lat, lng = 0.0, 0.0
        for date_dir in sorted(meta_dir.iterdir(), reverse=True) if meta_dir.exists() else []:
            if not date_dir.is_dir() or date_dir.name == "frames":
                continue
            for mf in date_dir.glob(f"{cam_id}_*.json"):
                try:
                    meta = json.loads(mf.read_text())
                    lat = meta.get("lat", 0)
                    lng = meta.get("lng", 0)
                    break
                except Exception:
                    continue
            if lat:
                break

        if not lat:
            continue

        # Haversine approximation
        R = 6371
        dlat = math.radians(lat - clat)
        dlon = math.radians(lng - clng)
        a = (math.sin(dlat / 2) ** 2
             + math.cos(math.radians(clat)) * math.cos(math.radians(lat))
             * math.sin(dlon / 2) ** 2)
        dist = R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        if dist < 5:
            cameras.append({
                "camera_id": cam_id,
                "lat": lat,
                "lng": lng,
                "distance_km": round(dist, 2),
                "pedestrians": data.get("pedestrians", 0),
                "vehicles": data.get("vehicles", 0),
                "bicycles": data.get("bicycles", 0),
                "density_level": data.get("density_level", "unknown"),
                "timestamp": data.get("timestamp", ""),
            })

    if not cameras:
        return {"cameras": [], "avg_pedestrians": 0, "avg_vehicles": 0, "density": "unknown"}

    avg_p = sum(c["pedestrians"] for c in cameras) / len(cameras)
    avg_v = sum(c["vehicles"] for c in cameras) / len(cameras)
    density = "high" if avg_p > 20 else "medium" if avg_p > 5 else "low"

    return {
        "cameras": cameras[:10],
        "avg_pedestrians": round(avg_p, 1),
        "avg_vehicles": round(avg_v, 1),
        "density": density,
    }


@web_app.get("/neighborhood/{name}")
async def neighborhood(name: str):
    """Full neighborhood data profile."""
    from modal_app.instrumentation import get_tracer
    tracer = get_tracer("alethia.web")

    span_ctx = tracer.start_as_current_span("neighborhood-profile") if tracer else None
    span = span_ctx.__enter__() if span_ctx else None
    try:
        if span:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("input.value", name)
            span.set_attribute("neighborhood.name", name)

        # Also check COMMUNITY_AREA_MAP values for broader coverage
        valid_names = set(n.lower() for n in CHICAGO_NEIGHBORHOODS) | set(n.lower() for n in COMMUNITY_AREA_MAP.values())
        if name.lower() not in valid_names:
            if span:
                span.set_attribute("error", f"Unknown neighborhood: {name}")
            return JSONResponse({"error": f"Unknown neighborhood: {name}"}, status_code=404)

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

        # Load news and politics with improved matching
        all_news = _load_docs("news")
        all_politics = _load_docs("politics")

        news_docs = _filter_by_neighborhood(all_news, name)
        politics_docs = _filter_by_neighborhood(all_politics, name)

        # Load additional data sources
        all_reddit = _load_docs("reddit")
        all_reviews = _load_docs("reviews")
        all_realestate = _load_docs("realestate")
        all_tiktok = _load_docs("tiktok")
        all_traffic = _load_docs("processed/traffic")

        reddit_docs = _filter_by_neighborhood(all_reddit, name)
        reviews_docs = _filter_by_neighborhood(all_reviews, name)
        realestate_docs = _filter_by_neighborhood(all_realestate, name)
        tiktok_docs = _filter_by_neighborhood(all_tiktok, name)
        traffic_docs = _filter_by_neighborhood(all_traffic, name)

        # Fallback: show some global data if no neighborhood-specific matches
        if not reddit_docs and all_reddit:
            reddit_docs = all_reddit[:5]
        if not reviews_docs and all_reviews:
            reviews_docs = all_reviews[:5]
        if not realestate_docs and all_realestate:
            realestate_docs = all_realestate[:5]

        # If no neighborhood-specific news/politics, include recent global items
        if not news_docs and all_news:
            news_docs = all_news[:5]
        if not politics_docs and all_politics:
            politics_docs = all_politics[:5]

        # Compute inspection stats
        failed = sum(1 for i in inspections if i.get("metadata", {}).get("raw_record", {}).get("results") in ("Fail", "Out of Business"))
        passed = sum(1 for i in inspections if i.get("metadata", {}).get("raw_record", {}).get("results") == "Pass")

        # Compute metrics from actual data
        computed_metrics = _compute_metrics(name, inspections, permits, licenses, news_docs, politics_docs, reviews_docs)

        # Load demographics
        demographics = _aggregate_demographics(name)

        # Load CCTV analysis
        cctv_analysis = _load_cctv_for_neighborhood(name)

        if span:
            span.set_attribute("output.value", json.dumps({
                "inspections": len(inspections), "permits": len(permits),
                "licenses": len(licenses), "news": len(news_docs),
            }))
            span.set_attribute("neighborhood.inspections", len(inspections))
            span.set_attribute("neighborhood.permits", len(permits))
            span.set_attribute("neighborhood.licenses", len(licenses))

        return {
            "neighborhood": name,
            "metrics": computed_metrics,
            "demographics": demographics,
            "inspections": inspections[:50],
            "permits": permits[:50],
            "licenses": licenses[:50],
            "news": news_docs[:20],
            "politics": politics_docs[:20],
            "reddit": reddit_docs[:20],
            "reviews": reviews_docs[:20],
            "realestate": realestate_docs[:10],
            "tiktok": tiktok_docs[:10],
            "traffic": traffic_docs[:10],
            "cctv": cctv_analysis,
            "inspection_stats": {
                "total": len(inspections),
                "failed": failed,
                "passed": passed,
            },
            "permit_count": len(permits),
            "license_count": len(licenses),
        }
    except Exception as e:
        if span:
            span.set_attribute("error", str(e))
        raise
    finally:
        if span_ctx:
            span_ctx.__exit__(None, None, None)


# ── User settings ─────────────────────────────────────────────────────────────

SETTINGS_PATH = Path(PROCESSED_DATA_PATH) / "user_settings.json"


class _UserSettingsPayload(BaseModel):
    location_type: str = Field(..., min_length=1)
    neighborhood: str = Field(..., min_length=1)


def _read_settings_store() -> dict:
    if SETTINGS_PATH.exists():
        try:
            return json.loads(SETTINGS_PATH.read_text())
        except Exception:
            pass
    return {}


def _write_settings_store(store: dict) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(store, indent=2))
    volume.commit()


@web_app.get("/user/settings")
async def get_user_settings(x_user_id: str = Header(default="")):
    if not x_user_id:
        return JSONResponse({"error": "Missing x-user-id header"}, status_code=401)
    store = _read_settings_store()
    entry = store.get(x_user_id)
    if not entry:
        return JSONResponse({"error": "No settings found"}, status_code=404)
    return {"user_id": x_user_id, "location_type": entry.get("location_type", ""), "neighborhood": entry.get("neighborhood", "")}


@web_app.put("/user/settings")
async def put_user_settings(payload: _UserSettingsPayload, x_user_id: str = Header(default="")):
    if not x_user_id:
        return JSONResponse({"error": "Missing x-user-id header"}, status_code=401)
    store = _read_settings_store()
    store[x_user_id] = {"location_type": payload.location_type, "neighborhood": payload.neighborhood}
    _write_settings_store(store)
    return {"user_id": x_user_id, "location_type": payload.location_type, "neighborhood": payload.neighborhood}


# ── Standalone data endpoints (used by api.ts) ──────────────────────────────

@web_app.get("/news")
async def news_list():
    """All recent news articles."""
    docs = _load_docs("news", limit=50)
    return docs


@web_app.get("/politics")
async def politics_list():
    """All recent politics/council items."""
    docs = _load_docs("politics", limit=50)
    return docs


@web_app.get("/inspections")
async def inspections_list(neighborhood: str = "", result: str = ""):
    """Food inspection records, optionally filtered."""
    public_docs = _load_docs("public_data", limit=500)
    inspections = [d for d in public_docs if d.get("metadata", {}).get("dataset") == "food_inspections"]
    if neighborhood:
        inspections = _filter_by_neighborhood(inspections, neighborhood)
    if result:
        inspections = [i for i in inspections if i.get("metadata", {}).get("raw_record", {}).get("results", "").lower() == result.lower()]
    return inspections[:100]


@web_app.get("/permits")
async def permits_list(neighborhood: str = ""):
    """Building permit records, optionally filtered."""
    public_docs = _load_docs("public_data", limit=500)
    permits = [d for d in public_docs if d.get("metadata", {}).get("dataset") == "building_permits"]
    if neighborhood:
        permits = _filter_by_neighborhood(permits, neighborhood)
    return permits[:100]


@web_app.get("/licenses")
async def licenses_list(neighborhood: str = ""):
    """Business license records, optionally filtered."""
    public_docs = _load_docs("public_data", limit=500)
    licenses = [d for d in public_docs if d.get("metadata", {}).get("dataset") == "business_licenses"]
    if neighborhood:
        licenses = _filter_by_neighborhood(licenses, neighborhood)
    return licenses[:100]


@web_app.get("/reddit")
async def reddit_list(neighborhood: str = ""):
    """Reddit posts, optionally filtered by neighborhood."""
    docs = _load_docs("reddit", limit=100)
    if neighborhood:
        docs = _filter_by_neighborhood(docs, neighborhood)
    return docs[:100]


@web_app.get("/reviews")
async def reviews_list(neighborhood: str = ""):
    """Business reviews (Yelp + Google Places), optionally filtered."""
    docs = _load_docs("reviews", limit=100)
    if neighborhood:
        docs = _filter_by_neighborhood(docs, neighborhood)
    return docs[:100]


@web_app.get("/realestate")
async def realestate_list(neighborhood: str = ""):
    """Commercial real estate listings, optionally filtered."""
    docs = _load_docs("realestate", limit=50)
    if neighborhood:
        docs = _filter_by_neighborhood(docs, neighborhood)
    return docs[:50]


@web_app.get("/tiktok")
async def tiktok_list(neighborhood: str = ""):
    """TikTok videos with transcriptions, optionally filtered."""
    docs = _load_docs("tiktok", limit=50)
    if neighborhood:
        docs = _filter_by_neighborhood(docs, neighborhood)
    return docs[:50]


@web_app.get("/traffic")
async def traffic_list(neighborhood: str = ""):
    """Traffic flow data (processed Documents), optionally filtered."""
    docs = _load_docs("processed/traffic", limit=100)
    if neighborhood:
        docs = _filter_by_neighborhood(docs, neighborhood)
    return docs[:100]


def _aggregate_city_demographics() -> dict:
    """Look up pre-aggregated city-wide demographics."""
    summary = _load_demographics_summary()
    return summary.get("city_wide", {})


@web_app.get("/summary")
async def summary():
    """City-wide summary stats."""
    total_docs = 0
    source_counts = {}
    for source in ["news", "politics", "public_data", "demographics", "realestate", "traffic", "cctv"]:
        source_dir = Path(RAW_DATA_PATH) / source
        if source_dir.exists():
            count = len(list(source_dir.rglob("*.json")))
            source_counts[source] = count
            total_docs += count

    demographics = _aggregate_city_demographics()

    return {
        "total_documents": total_docs,
        "source_counts": source_counts,
        "demographics": demographics,
    }


@web_app.get("/cctv/latest")
async def cctv_latest():
    """Latest CCTV analysis per camera: counts, density, location."""
    analysis_dir = Path(PROCESSED_DATA_PATH) / "cctv" / "analysis"
    if not analysis_dir.exists():
        return {"cameras": [], "count": 0}

    latest_by_cam: dict[str, dict] = {}
    for jf in sorted(analysis_dir.glob("*.json"), reverse=True)[:500]:
        try:
            data = json.loads(jf.read_text())
            cam_id = data.get("camera_id", "")
            if cam_id not in latest_by_cam:
                latest_by_cam[cam_id] = data
        except Exception:
            continue

    cameras = list(latest_by_cam.values())
    return {"cameras": cameras, "count": len(cameras)}


@web_app.get("/cctv/frame/{camera_id}")
async def cctv_frame(camera_id: str):
    """Serve latest annotated JPEG for a camera."""
    from fastapi.responses import Response

    ann_dir = Path(PROCESSED_DATA_PATH) / "cctv" / "annotated"
    if not ann_dir.exists():
        return JSONResponse({"error": "no annotated frames"}, status_code=404)

    # Find latest annotated frame for this camera
    frames = sorted(ann_dir.glob(f"{camera_id}_*.jpg"), reverse=True)
    if not frames:
        return JSONResponse({"error": f"no frames for camera {camera_id}"}, status_code=404)

    frame_bytes = frames[0].read_bytes()
    return Response(content=frame_bytes, media_type="image/jpeg")


@web_app.get("/geo")
async def geo():
    """GeoJSON FeatureCollection for map."""
    geo_path = Path(PROCESSED_DATA_PATH) / "geo" / "neighborhood_metrics.json"
    if geo_path.exists():
        return json.loads(geo_path.read_text())
    return {"type": "FeatureCollection", "features": []}


@web_app.get("/graph")
async def graph(page: int = 1, limit: int = 200):
    """Proxy to Supermemory list documents for Memory Graph visualization."""
    empty = {"documents": [], "pagination": {"currentPage": 1, "totalPages": 0}}
    api_key = os.environ.get("SUPERMEMORY_API_KEY", "")
    if not api_key:
        return JSONResponse(empty, status_code=200)
    import httpx
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.supermemory.ai/v3/documents/documents",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                json={
                    "page": page,
                    "limit": min(limit, 200),  # Supermemory max is 200
                    "sort": "createdAt",
                    "order": "desc",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            # Memory Graph expects 'documents'; Supermemory list returns 'memories'
            if "memories" in data and "documents" not in data:
                data["documents"] = data["memories"]
            return data
    except Exception as e:
        print(f"Supermemory /graph error: {e}")
        return JSONResponse(empty, status_code=200)


@web_app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@web_app.post("/demo/scale")
async def demo_scale(request: Request):
    """Trigger scaling demo — fans out parallel agents + classification to generate traces."""
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    num_agents = body.get("num_agents", 15)
    num_queries = body.get("num_queries", 5)
    run_classify = body.get("run_classify", True)

    demo_fn = modal.Function.from_name("alethia", "scaling_demo")
    result = await demo_fn.remote.aio(
        num_agents=num_agents,
        num_queries=num_queries,
        run_classify=run_classify,
    )
    return result


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
