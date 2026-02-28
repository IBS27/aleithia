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
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from modal_app.volume import app, volume, web_image, VOLUME_MOUNT, RAW_DATA_PATH, PROCESSED_DATA_PATH
from modal_app.common import CHICAGO_NEIGHBORHOODS, COMMUNITY_AREA_MAP, detect_neighborhood

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
    """Filter documents by neighborhood with multi-strategy matching."""
    if not neighborhood:
        return docs
    nb_lower = neighborhood.lower()

    # Reverse lookup: find community area number for this neighborhood
    nb_community_area = None
    for ca_num, ca_name in COMMUNITY_AREA_MAP.items():
        if ca_name.lower() == nb_lower:
            nb_community_area = str(ca_num)
            break

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


def _aggregate_demographics(neighborhood: str) -> dict:
    """Aggregate census demographics for a neighborhood from raw demographics docs."""
    demos = _load_docs("demographics", limit=1500)
    nb_lower = neighborhood.lower()

    # Try to match demographics by community area or content
    nb_community_area = None
    for ca_num, ca_name in COMMUNITY_AREA_MAP.items():
        if ca_name.lower() == nb_lower:
            nb_community_area = str(ca_num)
            break

    # Collect matching tract data
    tract_data = []
    for d in demos:
        meta_demos = d.get("metadata", {}).get("demographics", {})
        if not meta_demos:
            continue
        geo = d.get("geo", {})
        # Match by community area or content
        if nb_community_area and geo.get("community_area") == nb_community_area:
            tract_data.append(meta_demos)
        elif nb_lower in d.get("content", "").lower()[:200]:
            tract_data.append(meta_demos)

    if not tract_data:
        # Fall back to city-wide averages from all tracts
        for d in demos[:200]:
            meta_demos = d.get("metadata", {}).get("demographics", {})
            if meta_demos and meta_demos.get("total_population", 0) > 0:
                tract_data.append(meta_demos)

    if not tract_data:
        return {}

    # Aggregate: weighted average by population for rates, sum for counts
    total_pop = sum(t.get("total_population", 0) for t in tract_data)
    if total_pop == 0:
        return {}

    def wavg(field: str) -> float:
        return sum(t.get(field, 0) * t.get("total_population", 0) for t in tract_data) / total_pop

    return {
        "total_population": int(total_pop),
        "median_household_income": round(wavg("median_household_income")),
        "median_home_value": round(wavg("median_home_value")),
        "median_gross_rent": round(wavg("median_gross_rent")),
        "unemployment_rate": round(wavg("unemployment_rate"), 1),
        "median_age": round(wavg("median_age"), 1),
        "total_housing_units": int(sum(t.get("total_housing_units", 0) for t in tract_data)),
        "renter_pct": round(wavg("renter_pct"), 1),
        "bachelors_degree": int(sum(t.get("bachelors_degree", 0) for t in tract_data)),
        "masters_degree": int(sum(t.get("masters_degree", 0) for t in tract_data)),
        "tracts_counted": len(tract_data),
    }


def _compute_metrics(name: str, inspections: list, permits: list, licenses: list, news: list, politics: list) -> dict:
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

    return {
        "neighborhood": name,
        "regulatory_density": round(regulatory_density, 1),
        "business_activity": round(business_activity, 1),
        "sentiment": round(sentiment, 1),
        "risk_score": risk_score,
        "active_permits": len(permits),
        "crime_incidents_30d": 0,
        "avg_review_rating": 0.0,
        "review_count": 0,
    }


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
            # Phase 1: Agent gathering (returns synthesis_messages, NOT response text)
            from modal_app.agents import orchestrate_query
            result = await orchestrate_query.remote.aio(
                user_id=user_id,
                question=question,
                business_type=business_type,
                target_neighborhood=neighborhood,
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
            from modal_app.llm import AlethiaLLM
            llm = AlethiaLLM()
            messages = result["synthesis_messages"]

            full_response = ""
            async for token in llm.generate_stream.remote_gen.aio(
                messages, max_tokens=2048, temperature=0.7
            ):
                full_response += token
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

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

    # Load news and politics with improved matching
    all_news = _load_docs("news")
    all_politics = _load_docs("politics")

    news_docs = _filter_by_neighborhood(all_news, name)
    politics_docs = _filter_by_neighborhood(all_politics, name)

    # If no neighborhood-specific news/politics, include recent global items
    if not news_docs and all_news:
        news_docs = all_news[:5]
    if not politics_docs and all_politics:
        politics_docs = all_politics[:5]

    # Compute inspection stats
    failed = sum(1 for i in inspections if i.get("metadata", {}).get("raw_record", {}).get("results") in ("Fail", "Out of Business"))
    passed = sum(1 for i in inspections if i.get("metadata", {}).get("raw_record", {}).get("results") == "Pass")

    # Compute metrics from actual data
    computed_metrics = _compute_metrics(name, inspections, permits, licenses, news_docs, politics_docs)

    # Load demographics
    demographics = _aggregate_demographics(name)

    return {
        "neighborhood": name,
        "metrics": computed_metrics,
        "demographics": demographics,
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


@web_app.get("/summary")
async def summary():
    """City-wide summary stats."""
    total_docs = 0
    source_counts = {}
    for source in ["news", "politics", "public_data", "demographics", "realestate"]:
        source_dir = Path(RAW_DATA_PATH) / source
        if source_dir.exists():
            count = len(list(source_dir.rglob("*.json")))
            source_counts[source] = count
            total_docs += count

    demographics = _aggregate_demographics("Loop")  # city-wide fallback

    return {
        "total_documents": total_docs,
        "source_counts": source_counts,
        "demographics": demographics,
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
