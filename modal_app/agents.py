"""Agent swarm for query-time intelligence — parallel neighborhood analysis.

Decomposes user questions into parallel agents that independently query
Supermemory, then synthesizes findings via LLM. Uses .spawn() fan-out pattern.

Modal features: .spawn(), @modal.function
"""
import asyncio
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import modal

from modal_app.common import compute_freshness, neighborhood_to_ca
from modal_app.pipelines.reddit import (
    FALLBACK_BUDGET_MS,
    merge_rank_reddit_docs,
    rank_reddit_docs,
    reddit_docs_are_weak,
    search_reddit_fallback_runtime,
)
from modal_app.volume import app, volume, base_image, RAW_DATA_PATH, PROCESSED_DATA_PATH

ADJACENT_NEIGHBORHOODS = {
    "Logan Square": ["Humboldt Park", "Avondale"],
    "Wicker Park": ["Bucktown", "Ukrainian Village"],
    "Pilsen": ["Little Village", "Bridgeport"],
    "Hyde Park": ["Kenwood", "Woodlawn"],
    "Lincoln Park": ["Lakeview", "Old Town"],
    "West Loop": ["Near West Side", "Loop"],
    "River North": ["Near North Side", "Streeterville"],
    "Lakeview": ["Lincoln Park", "Uptown"],
    "Bucktown": ["Wicker Park", "Logan Square"],
    "Andersonville": ["Edgewater", "Uptown"],
    "Chinatown": ["Bridgeport", "South Loop"],
    "South Loop": ["Loop", "Chinatown"],
    "Uptown": ["Edgewater", "Lakeview"],
    "Rogers Park": ["Edgewater", "West Ridge"],
    "Bridgeport": ["Pilsen", "Chinatown"],
}

BUSINESS_KEYWORDS = {
    "restaurant": ["food", "restaurant", "dining", "liquor", "health inspection", "food service"],
    "retail": ["retail", "storefront", "merchandise", "commercial", "shopping"],
    "bar": ["liquor", "tavern", "bar", "alcohol", "nightlife"],
    "cafe": ["coffee", "cafe", "bakery", "food service"],
    "gym": ["fitness", "gym", "health club", "recreation"],
}


async def _fetch_legistar_inline(business_type: str, limit: int = 30) -> list[dict]:
    """Fetch live Chicago City Council legislation from Legistar REST API."""
    import httpx

    keywords = BUSINESS_KEYWORDS.get(business_type.lower(), [business_type.lower()])
    keywords += ["zoning", "license", "permit", "ordinance"]

    results = []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://webapi.legistar.com/v1/chicago/matters",
                params={
                    "$top": 100,
                    "$orderby": "MatterLastModifiedUtc desc",
                    "$filter": "MatterStatusName ne 'Withdrawn'",
                },
            )
            resp.raise_for_status()
            matters = resp.json()

            for matter in matters:
                title = (matter.get("MatterTitle") or "").lower()
                body = (matter.get("MatterBodyName") or "").lower()
                text = f"{title} {body}"
                if any(kw in text for kw in keywords):
                    results.append({
                        "id": f"legistar-{matter.get('MatterId', '')}",
                        "title": matter.get("MatterTitle", ""),
                        "type": matter.get("MatterTypeName", ""),
                        "status": matter.get("MatterStatusName", ""),
                        "date": matter.get("MatterLastModifiedUtc", ""),
                        "body": matter.get("MatterBodyName", ""),
                        "source": "legistar_live",
                    })
                    if len(results) >= limit:
                        break
    except Exception as e:
        print(f"Legistar inline fetch failed: {e}")

    return results


async def _fetch_federal_register_inline(business_type: str, since_days: int = 7) -> list[dict]:
    """Fetch live federal regulations from Federal Register API for SBA/FDA/OSHA/EPA."""
    import httpx
    from datetime import timedelta

    keywords = BUSINESS_KEYWORDS.get(business_type.lower(), [business_type.lower()])
    agencies = ["small-business-administration", "food-and-drug-administration",
                "occupational-safety-and-health-administration", "environmental-protection-agency"]

    since = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%Y-%m-%d")
    results = []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://www.federalregister.gov/api/v1/documents.json",
                params={
                    "conditions[agencies][]": agencies,
                    "conditions[publication_date][gte]": since,
                    "per_page": 50,
                    "order": "newest",
                },
            )
            resp.raise_for_status()
            data = resp.json()

            for doc in data.get("results", []):
                title = (doc.get("title") or "").lower()
                abstract = (doc.get("abstract") or "").lower()
                text = f"{title} {abstract}"
                if any(kw in text for kw in keywords + ["food", "health", "safety", "labor"]):
                    results.append({
                        "id": f"fedreg-{doc.get('document_number', '')}",
                        "title": doc.get("title", ""),
                        "type": doc.get("type", ""),
                        "agency": (doc.get("agencies") or [{}])[0].get("name", ""),
                        "date": doc.get("publication_date", ""),
                        "url": doc.get("html_url", ""),
                        "source": "federal_register_live",
                    })
    except Exception as e:
        print(f"Federal Register inline fetch failed: {e}")

    return results


SYNTHESIS_SYSTEM_PROMPT = """You are synthesizing intelligence reports from multiple neighborhood agents.
Each agent independently analyzed a different Chicago neighborhood. Your job is to:

1. Merge the findings into a coherent recommendation
2. Identify conflicts between reports (e.g., one neighborhood has high foot traffic but another has lower rent)
3. Produce a clear recommendation with confidence level
4. Compare the target neighborhood against comparison neighborhoods
5. Cite specific data points from each agent's report
6. Analyze social media trends: If TikTok or Reddit data is present, extract actionable insights —
   what content creators are featuring, trending hashtags, community sentiment, viral topics,
   and what this signals about consumer demand and foot traffic patterns.
7. Incorporate review data: If business reviews are present, analyze average ratings, review velocity,
   and what customers are saying about competitors in the area.

Format your response with clear sections:
- Executive Summary (2-3 sentences)
- Target Neighborhood Analysis
- Social & Community Pulse (TikTok trends, Reddit discussions, review sentiment — skip if no data)
- Comparison Neighborhoods
- Key Risks
- Key Opportunities
- Recommendation (with confidence: high/medium/low)"""


def _aggregate_categories(vectordb_results: list[dict]) -> dict:
    """Aggregate category counts from VectorDB search results."""
    counts: dict[str, int] = {}
    for r in vectordb_results:
        cat = r.get("payload", {}).get("category", "")
        if cat:
            counts[cat] = counts.get(cat, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True)[:5])


@app.function(
    image=base_image,
    volumes={"/data": volume},
    secrets=[modal.Secret.from_name("alethia-secrets"), modal.Secret.from_name("arize-secrets")],
    timeout=120,
)
async def neighborhood_intel_agent(neighborhood: str, business_type: str, focus_areas: list[str] | None = None, trace_context: dict | None = None) -> dict:
    """Query-time intelligence agent for a single neighborhood.

    Gathers data from local volume + Supermemory to build a neighborhood brief.
    """
    from modal_app.instrumentation import init_tracing, get_tracer, extract_context
    init_tracing()
    tracer = get_tracer("alethia.agents")
    parent_ctx = extract_context(trace_context)

    if focus_areas is None:
        focus_areas = ["permits", "sentiment", "competition", "safety", "demographics"]

    report = {
        "neighborhood": neighborhood,
        "business_type": business_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "findings": {},
        "freshness": {},
        "data_points": 0,
    }

    span_ctx = tracer.start_as_current_span("neighborhood-intel-agent", context=parent_ctx) if tracer else None
    span = span_ctx.__enter__() if span_ctx else None
    try:
        if span:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("input.value", f"{business_type} in {neighborhood}")
            span.set_attribute("agent.neighborhood", neighborhood)
            span.set_attribute("agent.business_type", business_type)

        nb_community_area = neighborhood_to_ca(neighborhood)

        # --- VectorAI DB semantic retrieval (fast path) ---
        vectordb_docs = []
        try:
            from modal_app.vectordb import vectordb_available
            if vectordb_available():
                vdb_cls = modal.Cls.from_name("alethia", "VectorDBService")
                vdb = vdb_cls()

                query_text = f"{business_type} {neighborhood} {' '.join(focus_areas or [])}"
                query_embedding = vdb.embed_text.remote(query_text)
                vectordb_docs = vdb.search_neighborhood.remote(query_embedding, neighborhood, top_k=50)

                if vectordb_docs:
                    report["findings"]["vectordb"] = {
                        "count": len(vectordb_docs),
                        "avg_score": round(sum(d["score"] for d in vectordb_docs) / len(vectordb_docs), 4),
                        "top_categories": _aggregate_categories(vectordb_docs),
                    }
                    report["data_points"] += len(vectordb_docs)
                    if span:
                        span.set_attribute("agent.vectordb_results", len(vectordb_docs))
        except Exception as e:
            print(f"VectorDB query failed (falling back to file scan): {e}")

        # Read local volume data
        for source in ["public_data", "news", "politics", "federal_register", "demographics", "reddit", "reviews", "realestate", "tiktok", "cctv"]:
            source_dir = Path(RAW_DATA_PATH) / source
            if not source_dir.exists() and source != "reddit":
                continue

            docs = []
            if source_dir.exists():
                for json_file in sorted(source_dir.rglob("*.json"), reverse=True)[:100]:
                    try:
                        doc = json.loads(json_file.read_text())
                        if not isinstance(doc, dict):
                            continue
                        geo = doc.get("geo", {})
                        doc_neighborhood = geo.get("neighborhood", "")
                        doc_ca = geo.get("community_area", "")
                        if doc_neighborhood.lower() == neighborhood.lower():
                            docs.append(doc)
                        elif nb_community_area and doc_ca == nb_community_area:
                            docs.append(doc)
                    except Exception:
                        continue

            if source == "reddit":
                docs = rank_reddit_docs(
                    docs,
                    business_type=business_type or "small business",
                    neighborhood=neighborhood,
                    min_score=0,
                )
                if reddit_docs_are_weak(
                    docs,
                    business_type=business_type or "small business",
                    neighborhood=neighborhood,
                    min_count=3,
                    median_threshold=2.0,
                ):
                    start_ms = int(time.time() * 1000)
                    fallback_docs = await search_reddit_fallback_runtime(
                        business_type=business_type or "small business",
                        neighborhood=neighborhood,
                        budget_ms=FALLBACK_BUDGET_MS,
                    )
                    latency_ms = int(time.time() * 1000) - start_ms
                    print(
                        "reddit_fallback_triggered",
                        {
                            "agent": "neighborhood_intel_agent",
                            "neighborhood": neighborhood,
                            "business_type": business_type or "small business",
                            "fallback_latency_ms": latency_ms,
                            "fallback_docs_found": len(fallback_docs),
                            "adapter_used": (fallback_docs[0].get("metadata", {}) or {}).get("retrieval_method", "") if fallback_docs else "",
                        },
                    )
                    if fallback_docs:
                        try:
                            persist_fn = modal.Function.from_name("alethia", "persist_reddit_fallback_batch")
                            await persist_fn.spawn.aio(docs=fallback_docs)
                        except Exception as exc:
                            print(f"Reddit fallback persist spawn failed (agent): {exc}")
                        docs = merge_rank_reddit_docs(
                            docs,
                            fallback_docs,
                            business_type=business_type or "small business",
                            neighborhood=neighborhood,
                            min_score=0,
                        )

            if docs:
                # Compute freshness from newest doc timestamp
                newest_ts = None
                for d in docs:
                    ts = d.get("timestamp")
                    if ts and (newest_ts is None or ts > newest_ts):
                        newest_ts = ts
                source_freshness = compute_freshness(timestamp_str=newest_ts) if newest_ts else compute_freshness()

                report["findings"][source] = {
                    "count": len(docs),
                    "samples": [{"title": d.get("title", ""), "content": d.get("content", "")[:200]} for d in docs[:5]],
                    "freshness": source_freshness,
                }
                report["freshness"][source] = source_freshness
                report["data_points"] += len(docs)

        # Traffic: read from processed path (Documents, not raw API dicts)
        traffic_dir = Path(RAW_DATA_PATH) / "processed" / "traffic"
        if traffic_dir.exists():
            traffic_docs = []
            for json_file in sorted(traffic_dir.rglob("*.json"), reverse=True)[:50]:
                try:
                    doc = json.loads(json_file.read_text())
                    if not isinstance(doc, dict) or "geo" not in doc:
                        continue
                    geo = doc.get("geo", {})
                    if geo.get("neighborhood", "").lower() == neighborhood.lower():
                        traffic_docs.append(doc)
                    elif nb_community_area and geo.get("community_area") == nb_community_area:
                        traffic_docs.append(doc)
                except Exception:
                    continue
            if traffic_docs:
                newest_ts = None
                for d in traffic_docs:
                    ts = d.get("timestamp")
                    if ts and (newest_ts is None or ts > newest_ts):
                        newest_ts = ts
                traffic_freshness = compute_freshness(timestamp_str=newest_ts) if newest_ts else compute_freshness()

                report["findings"]["traffic"] = {
                    "count": len(traffic_docs),
                    "samples": [{"title": d.get("title", ""), "content": d.get("content", "")[:200]} for d in traffic_docs[:5]],
                    "freshness": traffic_freshness,
                }
                report["freshness"]["traffic"] = traffic_freshness
                report["data_points"] += len(traffic_docs)

        # Read enriched data (classified)
        enriched_dir = Path(PROCESSED_DATA_PATH) / "enriched"
        if enriched_dir.exists():
            enriched_docs = []
            for json_file in sorted(enriched_dir.rglob("*.json"), reverse=True)[:50]:
                try:
                    doc = json.loads(json_file.read_text())
                    doc_neighborhood = doc.get("geo", {}).get("neighborhood", "")
                    if doc_neighborhood.lower() == neighborhood.lower():
                        enriched_docs.append(doc)
                except Exception:
                    continue

            if enriched_docs:
                # Aggregate sentiment
                sentiments = [d.get("sentiment", {}).get("label", "neutral") for d in enriched_docs]
                positive = sentiments.count("positive")
                negative = sentiments.count("negative")
                report["findings"]["sentiment"] = {
                    "positive": positive,
                    "negative": negative,
                    "neutral": len(sentiments) - positive - negative,
                    "ratio": round(positive / max(len(sentiments), 1), 2),
                }

                # Aggregate classifications
                all_labels = []
                for d in enriched_docs:
                    all_labels.extend(d.get("classification", {}).get("labels", []))
                label_counts = {}
                for label in all_labels:
                    label_counts[label] = label_counts.get(label, 0) + 1
                report["findings"]["top_categories"] = dict(
                    sorted(label_counts.items(), key=lambda x: x[1], reverse=True)[:5]
                )

        # Extract foot traffic metrics from CCTV data
        if "cctv" in report["findings"]:
            cctv_samples = report["findings"]["cctv"].get("samples", [])
            total_peds = 0
            total_vehs = 0
            cam_count = 0
            for sample in cctv_samples:
                content = sample.get("content", "")
                ped_match = re.search(r"(\d+) pedestrians", content)
                veh_match = re.search(r"(\d+) vehicles", content)
                if ped_match:
                    total_peds += int(ped_match.group(1))
                    cam_count += 1
                if veh_match:
                    total_vehs += int(veh_match.group(1))

            if cam_count > 0:
                avg_peds = total_peds / cam_count
                report["findings"]["foot_traffic"] = {
                    "avg_pedestrians": round(avg_peds, 1),
                    "avg_vehicles": round(total_vehs / cam_count, 1),
                    "density_level": "high" if avg_peds > 20 else "medium" if avg_peds > 5 else "low",
                    "camera_count": cam_count,
                }

        # Query Supermemory for additional context
        api_key = os.environ.get("SUPERMEMORY_API_KEY", "")
        if api_key:
            try:
                from modal_app.supermemory import SupermemoryClient
                sm = SupermemoryClient(api_key)
                results = await sm.search(
                    query=f"{business_type} in {neighborhood} Chicago permits zoning competition",
                    container_tags=[
                        "chicago_data",
                        "chicago_news",
                        "chicago_public_data",
                        "chicago_demographics",
                        "chicago_reddit",
                        "chicago_reviews",
                        "chicago_realestate",
                        "chicago_tiktok",
                        "chicago_politics",
                        "chicago_federal_register",
                    ],
                    limit=10,
                )
                report["findings"]["supermemory"] = {
                    "results_count": len(results),
                    "snippets": [r.get("content", "")[:200] for r in results[:3]],
                }
                report["data_points"] += len(results)
            except Exception as e:
                report["findings"]["supermemory_error"] = str(e)

        if span:
            span.set_attribute("output.value", json.dumps({"data_points": report["data_points"], "sources": list(report["findings"].keys())}))
            span.set_attribute("agent.data_points", report["data_points"])
        return report
    except Exception as e:
        if span:
            span.set_attribute("error", str(e))
        raise
    finally:
        if span_ctx:
            span_ctx.__exit__(None, None, None)


async def _enrich_regulations_with_impact(regulations: list[dict], business_type: str, max_batch: int = 10) -> list[dict]:
    """Use GPT-4o to add impact_summary fields to top regulations.

    Runs as a plain async helper inside the regulatory_agent container — no
    separate Modal function needed (secrets are already available).
    """
    from modal_app.openai_utils import openai_available, get_openai_client

    if not openai_available() or not regulations:
        return regulations

    client = get_openai_client()
    if not client:
        return regulations

    batch = regulations[:max_batch]
    reg_summaries = [f"{i+1}. {r.get('title', 'Untitled')} (type: {r.get('type', 'N/A')}, agency: {r.get('agency', 'N/A')})" for i, r in enumerate(batch)]

    try:
        resp = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You analyze regulations for small business impact. Given a list of regulations and a business type, return a JSON object with an 'impacts' array containing a one-sentence impact summary for each regulation, in the same order. Be specific about what the business owner should do or watch for."},
                {"role": "user", "content": f"Business type: {business_type}\n\nRegulations:\n" + "\n".join(reg_summaries)},
            ],
            max_tokens=500,
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or "{}"
        impacts = json.loads(content).get("impacts", [])
        for i, impact in enumerate(impacts):
            if i < len(regulations):
                regulations[i]["impact_summary"] = impact
    except Exception as e:
        print(f"Regulatory impact enrichment failed: {e}")

    return regulations


@app.function(
    image=base_image,
    volumes={"/data": volume},
    secrets=[modal.Secret.from_name("alethia-secrets"), modal.Secret.from_name("arize-secrets")],
    timeout=120,
)
async def regulatory_agent(business_type: str, trace_context: dict | None = None) -> dict:
    """Scans live APIs + cached volume data for regulations relevant to business type.

    Fetches Legistar + Federal Register inline (~3-5s), deduplicates against
    volume cache, writes live results back to volume for dashboard freshness.
    """
    from modal_app.instrumentation import init_tracing, get_tracer, extract_context
    init_tracing()
    tracer = get_tracer("alethia.agents")
    parent_ctx = extract_context(trace_context)

    report = {
        "business_type": business_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "regulations": [],
        "freshness": {},
        "data_points": 0,
    }

    span_ctx = tracer.start_as_current_span("regulatory-agent", context=parent_ctx) if tracer else None
    span = span_ctx.__enter__() if span_ctx else None
    try:
        if span:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("input.value", business_type)
            span.set_attribute("agent.business_type", business_type)

        # 1. Fetch live data from both APIs concurrently
        live_legistar, live_federal = [], []
        try:
            live_legistar, live_federal = await asyncio.gather(
                _fetch_legistar_inline(business_type),
                _fetch_federal_register_inline(business_type),
            )
        except Exception as e:
            print(f"Live regulatory fetch failed, falling back to volume: {e}")

        live_ids = set()

        # Add live Legistar results
        for item in live_legistar:
            live_ids.add(item["id"])
            report["regulations"].append({
                "title": item["title"],
                "type": item.get("type", ""),
                "status": item.get("status", ""),
                "date": item.get("date", ""),
                "relevance": "direct",
                "freshness": "live",
            })
            report["data_points"] += 1

        # Add live Federal Register results
        for item in live_federal:
            live_ids.add(item["id"])
            report["regulations"].append({
                "title": item["title"],
                "type": item.get("type", "federal"),
                "agency": item.get("agency", ""),
                "date": item.get("date", ""),
                "url": item.get("url", ""),
                "relevance": "federal",
                "freshness": "live",
            })
            report["data_points"] += 1

        report["freshness"]["legistar"] = {
            "source": "live_api",
            "count": len(live_legistar),
            "freshness_label": "fresh" if live_legistar else "unavailable",
        }
        report["freshness"]["federal_register"] = {
            "source": "live_api",
            "count": len(live_federal),
            "freshness_label": "fresh" if live_federal else "unavailable",
        }

        # 2. Read volume data as fallback / supplement (dedup against live)
        for source_name, source_dir_name in [("politics", "politics"), ("federal", "federal_register")]:
            source_dir = Path(RAW_DATA_PATH) / source_dir_name
            if not source_dir.exists():
                continue

            newest_ts = None
            for json_file in sorted(source_dir.rglob("*.json"), reverse=True)[:50]:
                try:
                    doc = json.loads(json_file.read_text())
                    doc_id = doc.get("id", "")
                    if doc_id in live_ids:
                        continue  # Already have live version
                    content = f"{doc.get('title', '')} {doc.get('content', '')}".lower()
                    keywords = [business_type.lower(), "zoning", "license", "permit", "ordinance"]
                    if source_name == "federal":
                        keywords += ["food", "health", "safety", "labor"]
                    if any(kw in content for kw in keywords):
                        ts = doc.get("timestamp")
                        if ts and (newest_ts is None or ts > newest_ts):
                            newest_ts = ts
                        report["regulations"].append({
                            "title": doc.get("title", ""),
                            "type": doc.get("metadata", {}).get("matter_type", "") if source_name == "politics" else "federal",
                            "status": doc.get("metadata", {}).get("status", ""),
                            "agency": doc.get("metadata", {}).get("agency", "") if source_name == "federal" else "",
                            "relevance": "direct" if business_type.lower() in content else "related",
                            "freshness": "cached",
                        })
                        report["data_points"] += 1
                except Exception:
                    continue

            if newest_ts:
                cached_freshness = compute_freshness(timestamp_str=newest_ts)
                report["freshness"][f"{source_name}_cached"] = cached_freshness

        # 2b. Enrich top regulations with GPT-4o impact summaries
        report["regulations"] = await _enrich_regulations_with_impact(
            report["regulations"], business_type
        )

        # 3. Write live data back to volume (fire-and-forget, benefits dashboard)
        if live_legistar or live_federal:
            try:
                from modal_app.common import Document, SourceType
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

                for item in live_legistar:
                    doc = Document(
                        id=item["id"],
                        source=SourceType.POLITICS,
                        title=item["title"],
                        content=f"{item.get('type', '')} — {item.get('status', '')}",
                        url="",
                        metadata={"matter_type": item.get("type", ""), "status": item.get("status", ""), "source": "legistar_live"},
                    )
                    out_dir = Path(RAW_DATA_PATH) / "politics" / today
                    out_dir.mkdir(parents=True, exist_ok=True)
                    (out_dir / f"{doc.id}.json").write_text(doc.model_dump_json())

                for item in live_federal:
                    doc = Document(
                        id=item["id"],
                        source=SourceType.FEDERAL_REGISTER,
                        title=item["title"],
                        content=f"{item.get('type', '')} — {item.get('agency', '')}",
                        url=item.get("url", ""),
                        metadata={"agency": item.get("agency", ""), "source": "federal_register_live"},
                    )
                    out_dir = Path(RAW_DATA_PATH) / "federal_register" / today
                    out_dir.mkdir(parents=True, exist_ok=True)
                    (out_dir / f"{doc.id}.json").write_text(doc.model_dump_json())

                volume.commit()
            except Exception as e:
                print(f"Failed to write live regulatory data to volume: {e}")

        if span:
            span.set_attribute("output.value", json.dumps({"data_points": report["data_points"], "regulation_count": len(report["regulations"])}))
            span.set_attribute("agent.data_points", report["data_points"])
        return report
    except Exception as e:
        if span:
            span.set_attribute("error", str(e))
        raise
    finally:
        if span_ctx:
            span_ctx.__exit__(None, None, None)


@app.function(
    image=base_image,
    volumes={"/data": volume},
    secrets=[modal.Secret.from_name("alethia-secrets"), modal.Secret.from_name("arize-secrets")],
    timeout=300,
)
async def orchestrate_query(user_id: str, question: str, business_type: str, target_neighborhood: str, trace_context: dict | None = None) -> dict:
    """Orchestrate parallel agents for query-time intelligence.

    1. Get user profile from Supermemory
    2. Determine 2 adjacent comparison neighborhoods
    3. Fan-out via .spawn(): primary agent + 2 comparison agents + regulatory agent
    4. Gather results
    5. Build synthesis prompt for LLM
    """
    from modal_app.instrumentation import init_tracing, get_tracer, extract_context, inject_context
    init_tracing()
    tracer = get_tracer("alethia.agents")
    parent_ctx = extract_context(trace_context)

    span_ctx = tracer.start_as_current_span("orchestrate-query", context=parent_ctx) if tracer else None
    span = span_ctx.__enter__() if span_ctx else None
    try:
        if span:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("input.value", question)
            span.set_attribute("orchestrator.business_type", business_type)
            span.set_attribute("orchestrator.target_neighborhood", target_neighborhood)

        # Determine comparison neighborhoods
        comparisons = ADJACENT_NEIGHBORHOODS.get(target_neighborhood, [])
        if len(comparisons) < 2:
            # Default comparisons if not in adjacency map
            comparisons = ["Loop", "Lincoln Park"]
        comparisons = comparisons[:2]

        # Capture current trace context to propagate to child agents
        child_ctx = inject_context()

        # Fan-out via .spawn() — parallel agent execution
        agent_handles = []

        # Primary neighborhood agent (full analysis)
        primary_handle = neighborhood_intel_agent.spawn(
            neighborhood=target_neighborhood,
            business_type=business_type,
            focus_areas=["permits", "sentiment", "competition", "safety", "demographics"],
            trace_context=child_ctx,
        )
        agent_handles.append(("primary", target_neighborhood, primary_handle))

        # Comparison neighborhood agents
        for comp_neighborhood in comparisons:
            handle = neighborhood_intel_agent.spawn(
                neighborhood=comp_neighborhood,
                business_type=business_type,
                focus_areas=["permits", "competition", "demographics"],
                trace_context=child_ctx,
            )
            agent_handles.append(("comparison", comp_neighborhood, handle))

        # Regulatory agent
        reg_handle = regulatory_agent.spawn(business_type=business_type, trace_context=child_ctx)
        agent_handles.append(("regulatory", "all", reg_handle))

        # Gather results
        agent_results = {}
        for agent_type, name, handle in agent_handles:
            try:
                result = handle.get()
                agent_results[f"{agent_type}_{name}"] = result
            except Exception as e:
                agent_results[f"{agent_type}_{name}"] = {"error": str(e)}

        # Build context for LLM synthesis
        total_data_points = sum(
            r.get("data_points", 0) for r in agent_results.values() if isinstance(r, dict)
        )

        context = {
            "question": question,
            "user_id": user_id,
            "business_type": business_type,
            "target_neighborhood": target_neighborhood,
            "comparison_neighborhoods": comparisons,
            "agent_results": agent_results,
            "total_data_points": total_data_points,
            "agents_deployed": len(agent_handles),
        }

        # Build synthesis prompt
        synthesis_prompt = f"""User question: {question}

Business type: {business_type}
Target neighborhood: {target_neighborhood}
Comparison neighborhoods: {', '.join(comparisons)}

Agent reports:
"""
        for key, result in agent_results.items():
            synthesis_prompt += f"\n--- {key} ---\n{json.dumps(result, indent=2, default=str)[:2000]}\n"

        synthesis_prompt += f"\nTotal data points analyzed: {total_data_points}"

        # Append freshness warnings for aging/stale sources
        freshness_warnings = []
        for key, result in agent_results.items():
            if not isinstance(result, dict):
                continue
            for source, freshness in result.get("freshness", {}).items():
                if isinstance(freshness, dict):
                    label = freshness.get("freshness_label", "")
                    age = freshness.get("age_human", "")
                    if label in ("aging", "stale"):
                        freshness_warnings.append(f"WARNING: {source} data is {label} ({age})")

        if freshness_warnings:
            synthesis_prompt += "\n\nDATA FRESHNESS WARNINGS:\n" + "\n".join(freshness_warnings)
            synthesis_prompt += "\nNote any stale data in your response and lower confidence accordingly."

        # Build synthesis messages for the caller to stream via LLM
        from modal_app.llm import SYSTEM_PROMPT

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + SYNTHESIS_SYSTEM_PROMPT},
            {"role": "user", "content": synthesis_prompt},
        ]

        if span:
            span.set_attribute("output.value", json.dumps({"agents_deployed": len(agent_handles), "total_data_points": total_data_points}))
            span.set_attribute("orchestrator.agents_deployed", len(agent_handles))
            span.set_attribute("orchestrator.total_data_points", total_data_points)

        return {
            "synthesis_messages": messages,
            "agents_deployed": len(agent_handles),
            "neighborhoods_analyzed": [target_neighborhood] + comparisons,
            "total_data_points": total_data_points,
            "context": context,
        }
    except Exception as e:
        if span:
            span.set_attribute("error", str(e))
        raise
    finally:
        if span_ctx:
            span_ctx.__exit__(None, None, None)
