"""Scaling demo — fans out traced operations across Modal to show Arize observability at scale.

Spawns parallel neighborhood agents, batch classification, and LLM calls
to generate a burst of traces visible in the Arize dashboard.

Modal features: .spawn(), .map(), @modal.function
"""
import json
import time
from datetime import datetime, timezone

import modal

from modal_app.volume import app, volume, base_image, RAW_DATA_PATH

DEMO_NEIGHBORHOODS = [
    "Logan Square", "Wicker Park", "Pilsen", "Hyde Park", "Lincoln Park",
    "West Loop", "River North", "Lakeview", "Bucktown", "Andersonville",
    "Chinatown", "South Loop", "Uptown", "Rogers Park", "Bridgeport",
]

DEMO_BUSINESS_TYPES = [
    "restaurant", "cafe", "bar", "retail", "grocery",
    "salon", "fitness",
]

DEMO_QUESTIONS = [
    "What permits do I need?",
    "How is foot traffic?",
    "What are the main risks?",
    "How does rent compare to nearby areas?",
    "What regulations should I know about?",
]


@app.function(
    image=base_image,
    volumes={"/data": volume},
    secrets=[modal.Secret.from_name("alethia-secrets"), modal.Secret.from_name("arize-secrets")],
    timeout=600,
)
async def scaling_demo(num_agents: int = 15, num_queries: int = 5, run_classify: bool = True):
    """Generate a burst of traced operations to demonstrate Modal + Arize at scale.

    Args:
        num_agents: Number of parallel neighborhood agents to spawn (max 15)
        num_queries: Number of full orchestrated queries to run (max 5)
        run_classify: Whether to also run batch classification
    """
    from modal_app.instrumentation import init_tracing, get_tracer
    init_tracing()
    tracer = get_tracer("alethia.demo")

    span_ctx = tracer.start_as_current_span("scaling-demo") if tracer else None
    span = span_ctx.__enter__() if span_ctx else None

    try:
        if span:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("input.value", f"scaling demo: {num_agents} agents, {num_queries} queries")
            span.set_attribute("demo.num_agents", num_agents)
            span.set_attribute("demo.num_queries", num_queries)

        results = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "agent_results": [],
            "query_results": [],
            "classify_results": None,
        }

        neighborhoods = DEMO_NEIGHBORHOODS[:num_agents]

        # ── Phase 1: Fan-out neighborhood agents in parallel ─────────────
        print(f"Phase 1: Spawning {len(neighborhoods)} neighborhood agents in parallel...")
        t0 = time.time()

        intel_fn = modal.Function.from_name("alethia", "neighborhood_intel_agent")
        agent_handles = []
        for nb in neighborhoods:
            biz = DEMO_BUSINESS_TYPES[hash(nb) % len(DEMO_BUSINESS_TYPES)]
            handle = intel_fn.spawn(neighborhood=nb, business_type=biz)
            agent_handles.append((nb, biz, handle))

        for nb, biz, handle in agent_handles:
            try:
                agent_result = handle.get()
                results["agent_results"].append({
                    "neighborhood": nb,
                    "business_type": biz,
                    "data_points": agent_result.get("data_points", 0),
                    "sources": list(agent_result.get("findings", {}).keys()),
                })
            except Exception as e:
                results["agent_results"].append({
                    "neighborhood": nb,
                    "error": str(e),
                })

        phase1_time = round(time.time() - t0, 2)
        print(f"Phase 1 complete: {len(agent_handles)} agents in {phase1_time}s")

        # ── Phase 2: Full orchestrated queries in parallel ───────────────
        print(f"Phase 2: Running {num_queries} full orchestrated queries...")
        t1 = time.time()

        orchestrate_fn = modal.Function.from_name("alethia", "orchestrate_query")
        query_handles = []
        for i in range(min(num_queries, len(DEMO_QUESTIONS))):
            nb = neighborhoods[i % len(neighborhoods)]
            biz = DEMO_BUSINESS_TYPES[i % len(DEMO_BUSINESS_TYPES)]
            question = DEMO_QUESTIONS[i]
            handle = orchestrate_fn.spawn(
                user_id=f"demo-user-{i}",
                question=question,
                business_type=biz,
                target_neighborhood=nb,
            )
            query_handles.append((nb, question, handle))

        for nb, question, handle in query_handles:
            try:
                query_result = handle.get()
                results["query_results"].append({
                    "neighborhood": nb,
                    "question": question,
                    "agents_deployed": query_result.get("agents_deployed", 0),
                    "data_points": query_result.get("total_data_points", 0),
                })
            except Exception as e:
                results["query_results"].append({
                    "neighborhood": nb,
                    "question": question,
                    "error": str(e),
                })

        phase2_time = round(time.time() - t1, 2)
        print(f"Phase 2 complete: {num_queries} queries in {phase2_time}s")

        # ── Phase 3: Batch classification burst ──────────────────────────
        phase3_time = 0
        if run_classify:
            print("Phase 3: Running batch classification burst...")
            t2 = time.time()

            classifier = modal.Cls.from_name("alethia", "DocClassifier")()
            analyzer = modal.Cls.from_name("alethia", "SentimentAnalyzer")()

            sample_texts = [
                f"New {biz} opening in {nb} faces zoning challenges"
                for nb, biz in zip(neighborhoods, DEMO_BUSINESS_TYPES * 3)
            ]

            import asyncio
            classify_results, sentiment_results = await asyncio.gather(
                asyncio.gather(*[classifier.classify.remote.aio(t) for t in sample_texts], return_exceptions=True),
                asyncio.gather(*[analyzer.analyze.remote.aio(t) for t in sample_texts], return_exceptions=True),
            )

            successes = sum(1 for r in classify_results if not isinstance(r, Exception))
            results["classify_results"] = {
                "texts_processed": len(sample_texts),
                "classification_successes": successes,
                "sentiment_successes": sum(1 for r in sentiment_results if not isinstance(r, Exception)),
            }

            phase3_time = round(time.time() - t2, 2)
            print(f"Phase 3 complete: {len(sample_texts)} docs classified in {phase3_time}s")

        # ── Summary ──────────────────────────────────────────────────────
        total_time = round(time.time() - t0, 2)
        total_spans = (
            len(agent_handles)
            + num_queries * 5  # each query spawns ~4 agents + 1 orchestrator
            + (len(sample_texts) * 2 if run_classify else 0)
            + 1  # this demo span
        )

        results["summary"] = {
            "total_time_seconds": total_time,
            "phase1_agents_seconds": phase1_time,
            "phase2_queries_seconds": phase2_time,
            "phase3_classify_seconds": phase3_time,
            "estimated_trace_spans": total_spans,
            "parallel_containers_used": len(neighborhoods) + num_queries * 4 + 2,
        }

        print(f"\nScaling demo complete!")
        print(f"  Total time: {total_time}s")
        print(f"  Estimated spans generated: {total_spans}")
        print(f"  Parallel containers: {results['summary']['parallel_containers_used']}")

        if span:
            span.set_attribute("output.value", json.dumps(results["summary"]))
            span.set_attribute("demo.total_time", total_time)
            span.set_attribute("demo.total_spans", total_spans)

        return results

    except Exception as e:
        if span:
            span.set_attribute("error", str(e))
        raise
    finally:
        if span_ctx:
            span_ctx.__exit__(None, None, None)
