"""GPU, sandbox analysis, and impact-brief routes."""
from __future__ import annotations

import asyncio
import base64
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import modal
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from modal_app.runtime import get_modal_cls, get_modal_function
from modal_app.volume import PROCESSED_DATA_PATH, RAW_DATA_PATH, app, sandbox_image, volume

router = APIRouter()

CODEGEN_SYSTEM_PROMPT = """You are a data analyst. Write a self-contained Python script that answers the user's question using real data files.

Rules:
- Read data from /data/raw/{source}/ and /data/processed/enriched/ (JSON files)
- Write results to /output/result.json (required) and optionally /output/chart.png
- result.json must have: {"title": str, "summary": str, "stats": {key: value}}
- Only use: json, os, pathlib, glob, collections, datetime, pandas, numpy, matplotlib, seaborn
- matplotlib.use("Agg") must be called before any plotting
- Max 80 lines. No network calls, no subprocess, no sys.exit.
- Create /output/ directory at the start: os.makedirs("/output", exist_ok=True)
- Always wrap file reads in try/except to handle missing or malformed files gracefully
- Output only the Python code in a ```python``` fence. No explanation."""

CODEGEN_SYSTEM_PROMPT_GPT4O = """You are a senior data analyst. Write a self-contained Python script that answers the user's question using real data files.

Rules:
- Read data from /data/raw/{source}/ and /data/processed/enriched/ (JSON files)
- Write results to /output/result.json (required) and optionally /output/chart.png
- result.json must have: {"title": str, "summary": str, "stats": {key: value}}
- Only use: json, os, pathlib, glob, collections, datetime, pandas, numpy, matplotlib, seaborn
- matplotlib.use("Agg") must be called before any plotting
- Max 100 lines. No network calls, no subprocess, no sys.exit.
- Create /output/ directory at the start: os.makedirs("/output", exist_ok=True)
- Wrap ALL file reads in try/except — skip corrupted/missing files gracefully
- Compute percentile rankings where applicable (e.g. "top 25% of neighborhoods")
- Detect simple trends: compare recent vs older data when timestamps are available
- For charts: use dark theme (plt.style.use('dark_background')), proper axis labels, tight_layout
- Use seaborn color palettes for multi-series plots
- Validate result.json schema before writing: title must be str, stats must be dict
- Output only the Python code in a ```python``` fence. No explanation."""


def discover_data_files(neighborhood: str | None = None) -> dict:
    del neighborhood
    sources = {}
    raw = Path(RAW_DATA_PATH)
    if not raw.exists():
        return sources

    for source_dir in sorted(raw.iterdir()):
        if not source_dir.is_dir():
            continue
        json_files = list(source_dir.rglob("*.json"))[:20]
        if not json_files:
            continue
        schema_keys = []
        try:
            sample = json.loads(json_files[0].read_text())
            if isinstance(sample, dict):
                schema_keys = list(sample.keys())[:10]
        except Exception:
            pass
        sources[source_dir.name] = {
            "count": len(list(source_dir.rglob("*.json"))),
            "sample_path": str(json_files[0]),
            "schema_keys": schema_keys,
        }

    enriched = Path(PROCESSED_DATA_PATH) / "enriched"
    if enriched.exists():
        json_files = list(enriched.rglob("*.json"))[:20]
        if json_files:
            schema_keys = []
            try:
                sample = json.loads(json_files[0].read_text())
                if isinstance(sample, dict):
                    schema_keys = list(sample.keys())[:10]
            except Exception:
                pass
            sources["enriched"] = {
                "count": len(list(enriched.rglob("*.json"))),
                "sample_path": str(json_files[0]),
                "schema_keys": schema_keys,
            }
    return sources


def build_codegen_prompt(question: str, brief: str, neighborhood: str, business_type: str, available_sources: dict) -> str:
    source_listing = "\n".join(
        f"- /data/raw/{src}/: {info['count']} files, keys: {info['schema_keys']}"
        if src != "enriched"
        else f"- /data/processed/enriched/: {info['count']} files, keys: {info['schema_keys']}"
        for src, info in available_sources.items()
    )
    brief_truncated = brief[:3000] if brief else "(no brief provided)"
    return f"""Neighborhood: {neighborhood}
Business type: {business_type}

User question: {question}

Intelligence brief context:
{brief_truncated}

Available data on the volume:
{source_listing}

Write a Python script to analyze this data and answer the question. Include a chart if appropriate."""


def extract_python_code(response: str) -> str | None:
    match = re.search(r"```python\s*\n(.*?)```", response, re.DOTALL)
    if match:
        return match.group(1).strip()
    match = re.search(r"^((?:import |from ).*)", response, re.MULTILINE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


class AnalyzePayload(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    brief: str = Field(default="")
    neighborhood: str = Field(default="Loop")
    business_type: str = Field(default="Restaurant")


class ImpactAnalyzeRequest(BaseModel):
    doc_id: str = Field(..., description="ID of the enriched document to analyze")


@router.get("/gpu-metrics")
async def gpu_metrics(probe_h100: bool = False):
    del probe_h100
    results = {
        "h100_llm": {"status": "disabled"},
        "t4_classifier": {"status": "cold"},
        "t4_sentiment": {"status": "cold"},
        "t4_cctv": {"status": "cold"},
    }

    gpu_classes = [("TrafficAnalyzer", "t4_cctv")]

    async def _fetch(cls_name: str, key: str):
        try:
            cls = get_modal_cls(cls_name)
            instance = cls()
            metrics = await asyncio.wait_for(instance.gpu_metrics.remote.aio(), timeout=8)
            results[key] = metrics
        except Exception:
            pass

    await asyncio.gather(*[_fetch(name, key) for name, key in gpu_classes], return_exceptions=True)

    try:
        enriched_dir = Path(PROCESSED_DATA_PATH) / "enriched"
        if enriched_dir.exists():
            enriched_files = list(enriched_dir.rglob("*.json"))
            enriched_count = len(enriched_files)
            if enriched_files:
                latest = max(enriched_files, key=lambda path: path.stat().st_mtime)
                age_seconds = time.time() - latest.stat().st_mtime
                if age_seconds < 240:
                    warm_status = {"status": "active", "gpu_name": "NVIDIA T4", "inferred": True, "enriched_count": enriched_count}
                    results["t4_classifier"] = warm_status
                    results["t4_sentiment"] = warm_status
                else:
                    idle_status = {"status": "cold", "reason": "idle", "enriched_count": enriched_count, "last_run_ago_s": round(age_seconds)}
                    results["t4_classifier"] = idle_status
                    results["t4_sentiment"] = idle_status
            else:
                no_data = {"status": "cold", "reason": "no_data", "enriched_count": 0}
                results["t4_classifier"] = no_data
                results["t4_sentiment"] = no_data
        else:
            no_data = {"status": "cold", "reason": "no_data", "enriched_count": 0}
            results["t4_classifier"] = no_data
            results["t4_sentiment"] = no_data
    except Exception:
        pass

    return results


@router.post("/demo/scale")
async def demo_scale(request: Request):
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    demo_fn = get_modal_function("scaling_demo")
    return await demo_fn.remote.aio(
        num_agents=body.get("num_agents", 15),
        num_queries=body.get("num_queries", 5),
        run_classify=body.get("run_classify", True),
    )


@router.post("/analyze")
async def analyze(payload: AnalyzePayload):
    from modal_app.instrumentation import get_tracer
    from modal_app.openai_utils import get_openai_client, openai_available

    tracer = get_tracer("alethia.web")
    span_ctx = tracer.start_as_current_span("deep-dive-analyze") if tracer else None
    span = span_ctx.__enter__() if span_ctx else None
    try:
        if span:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("input.value", payload.question)
            span.set_attribute("deep_dive.neighborhood", payload.neighborhood)

        available = discover_data_files(payload.neighborhood)
        if not available:
            return JSONResponse({"error": "No data files found on volume"}, status_code=404)

        prompt = build_codegen_prompt(
            payload.question,
            payload.brief,
            payload.neighborhood,
            payload.business_type,
            available,
        )

        if not openai_available():
            return JSONResponse(
                {"error": "Deep Dive unavailable: OpenAI not configured"},
                status_code=503,
            )

        model_used = "gpt-4o"
        try:
            client = get_openai_client()
            oai_resp = await client.chat.completions.create(
                model=model_used,
                messages=[
                    {"role": "system", "content": CODEGEN_SYSTEM_PROMPT_GPT4O},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=2048,
                temperature=0.3,
            )
            response = oai_resp.choices[0].message.content or ""
        except Exception as exc:
            return JSONResponse(
                {"error": f"Deep Dive unavailable: GPT-4o failed ({exc})"},
                status_code=503,
            )

        code = extract_python_code(response)
        if not code:
            return JSONResponse({"error": "Failed to generate valid analysis code", "raw_response": response[:500]}, status_code=500)

        sb = modal.Sandbox.create(
            "python",
            "-c",
            code,
            image=sandbox_image,
            volumes={"/data": volume},
            timeout=30,
            app=app,
        )
        sb.wait()

        stderr_text = sb.stderr.read()
        stdout_text = sb.stdout.read()

        result_data = None
        chart_b64 = None
        try:
            result_file = sb.open("/output/result.json", "r")
            result_data = json.loads(result_file.read())
            result_file.close()
        except Exception:
            if stdout_text.strip():
                result_data = {"title": "Analysis Result", "summary": stdout_text.strip()[:2000], "stats": {}}

        try:
            chart_file = sb.open("/output/chart.png", "rb")
            chart_b64 = base64.b64encode(chart_file.read()).decode("utf-8")
            chart_file.close()
        except Exception:
            pass

        if span:
            span.set_attribute("deep_dive.has_chart", chart_b64 is not None)
            span.set_attribute("deep_dive.code_lines", len(code.splitlines()))
            span.set_attribute("deep_dive.model", model_used)

        return {
            "code": code,
            "result": result_data or {"title": "Analysis", "summary": "Script completed but produced no result.json", "stats": {}, "raw_output": stdout_text[:2000]},
            "chart": chart_b64,
            "stderr": stderr_text[:500] if stderr_text else None,
            "model_used": model_used,
        }
    except Exception as exc:
        if span:
            span.set_attribute("error", str(exc))
        return JSONResponse({"error": str(exc)}, status_code=500)
    finally:
        if span_ctx:
            span_ctx.__exit__(None, None, None)


@router.get("/impact-briefs")
async def list_impact_briefs(limit: int = 20, min_score: float = 0.0):
    volume.reload()
    briefs_dir = Path(PROCESSED_DATA_PATH) / "impact_briefs"
    if not briefs_dir.exists():
        return {"briefs": [], "count": 0}

    briefs = []
    for json_file in sorted(briefs_dir.rglob("*.json"), reverse=True)[:limit]:
        try:
            brief = json.loads(json_file.read_text())
            if brief.get("impact_score", 0) >= min_score:
                briefs.append(brief)
        except Exception:
            continue
    return {"briefs": briefs, "count": len(briefs)}


@router.get("/impact-briefs/{brief_id}")
async def get_impact_brief(brief_id: str):
    volume.reload()
    briefs_dir = Path(PROCESSED_DATA_PATH) / "impact_briefs"
    if not briefs_dir.exists():
        return JSONResponse({"error": "No impact briefs found"}, status_code=404)

    for json_file in briefs_dir.rglob("*.json"):
        try:
            brief = json.loads(json_file.read_text())
            if brief.get("id") == brief_id:
                return brief
        except Exception:
            continue
    return JSONResponse({"error": f"Brief {brief_id} not found"}, status_code=404)


@router.post("/impact-briefs/analyze")
async def trigger_impact_analysis(req: ImpactAnalyzeRequest):
    try:
        from modal_app.lead_analyst import analyze_impact

        return await analyze_impact.remote.aio(req.doc_id)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
