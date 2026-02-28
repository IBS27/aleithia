"""Agent swarm for query-time intelligence — parallel neighborhood analysis.

Decomposes user questions into parallel agents that independently query
Supermemory, then synthesizes findings via LLM. Uses .spawn() fan-out pattern.

Modal features: .spawn(), @modal.function
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import modal

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

SYNTHESIS_SYSTEM_PROMPT = """You are synthesizing intelligence reports from multiple neighborhood agents.
Each agent independently analyzed a different Chicago neighborhood. Your job is to:

1. Merge the findings into a coherent recommendation
2. Identify conflicts between reports (e.g., one neighborhood has high foot traffic but another has lower rent)
3. Produce a clear recommendation with confidence level
4. Compare the target neighborhood against comparison neighborhoods
5. Cite specific data points from each agent's report

Format your response with clear sections:
- Executive Summary (2-3 sentences)
- Target Neighborhood Analysis
- Comparison Neighborhoods
- Key Risks
- Key Opportunities
- Recommendation (with confidence: high/medium/low)"""


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

        # Read local volume data
        for source in ["public_data", "news", "politics", "demographics", "cctv"]:
            source_dir = Path(RAW_DATA_PATH) / source
            if not source_dir.exists():
                continue

            docs = []
            for json_file in sorted(source_dir.rglob("*.json"), reverse=True)[:100]:
                try:
                    doc = json.loads(json_file.read_text())
                    doc_neighborhood = doc.get("geo", {}).get("neighborhood", "")
                    if doc_neighborhood.lower() == neighborhood.lower():
                        docs.append(doc)
                except Exception:
                    continue

            if docs:
                report["findings"][source] = {
                    "count": len(docs),
                    "samples": [{"title": d.get("title", ""), "content": d.get("content", "")[:200]} for d in docs[:5]],
                }
                report["data_points"] += len(docs)

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
                # Parse counts from content string: "N pedestrians, M vehicles"
                import re
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
                    container_tags=["chicago_data", "chicago_news", "chicago_public_data", "chicago_reddit", "chicago_reviews", "chicago_politics", "chicago_cctv"],
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


@app.function(
    image=base_image,
    volumes={"/data": volume},
    secrets=[modal.Secret.from_name("alethia-secrets"), modal.Secret.from_name("arize-secrets")],
    timeout=120,
)
async def regulatory_agent(business_type: str, trace_context: dict | None = None) -> dict:
    """Scans local + federal regulations relevant to business type."""
    from modal_app.instrumentation import init_tracing, get_tracer, extract_context
    init_tracing()
    tracer = get_tracer("alethia.agents")
    parent_ctx = extract_context(trace_context)

    BUSINESS_KEYWORDS = {
        "restaurant": ["food", "health", "safety", "labor", "kitchen", "sanitation"],
        "retail": ["commerce", "consumer", "safety", "trade", "merchandise"],
        "bar": ["liquor", "alcohol", "safety", "noise", "entertainment"],
        "cafe": ["food", "health", "safety", "beverage", "coffee"],
        "grocery": ["food", "health", "safety", "produce", "retail"],
        "salon": ["cosmetology", "health", "safety", "beauty"],
        "fitness": ["health", "safety", "recreation", "gym"],
    }
    keywords = BUSINESS_KEYWORDS.get(business_type.lower(), ["business", "safety", "labor", "health"])
    keywords.append(business_type.lower())

    report = {
        "business_type": business_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "regulations": [],
        "data_points": 0,
    }

    span_ctx = tracer.start_as_current_span("regulatory-agent", context=parent_ctx) if tracer else None
    span = span_ctx.__enter__() if span_ctx else None
    try:
        if span:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("input.value", business_type)
            span.set_attribute("agent.business_type", business_type)

        # Scan politics data for regulatory items
        politics_dir = Path(RAW_DATA_PATH) / "politics"
        if politics_dir.exists():
            for json_file in sorted(politics_dir.rglob("*.json"), reverse=True)[:50]:
                try:
                    doc = json.loads(json_file.read_text())
                    content = f"{doc.get('title', '')} {doc.get('content', '')}".lower()
                    if any(kw in content for kw in [business_type.lower(), "zoning", "license", "permit", "ordinance"]):
                        report["regulations"].append({
                            "title": doc.get("title", ""),
                            "type": doc.get("metadata", {}).get("matter_type", ""),
                            "status": doc.get("metadata", {}).get("status", ""),
                            "relevance": "direct" if business_type.lower() in content else "related",
                        })
                        report["data_points"] += 1
                except Exception:
                    continue

        # Scan federal register data if available
        federal_dir = Path(RAW_DATA_PATH) / "federal_register"
        if federal_dir.exists():
            for json_file in sorted(federal_dir.rglob("*.json"), reverse=True)[:30]:
                try:
                    doc = json.loads(json_file.read_text())
                    content = f"{doc.get('title', '')} {doc.get('content', '')}".lower()
                    if any(kw in content for kw in keywords):
                        report["regulations"].append({
                            "title": doc.get("title", ""),
                            "type": "federal",
                            "agency": doc.get("metadata", {}).get("agency", ""),
                            "relevance": "federal",
                        })
                        report["data_points"] += 1
                except Exception:
                    continue

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
