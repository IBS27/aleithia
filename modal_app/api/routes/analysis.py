"""GPU, sandbox analysis, and impact-brief routes."""
from __future__ import annotations

import asyncio
import base64
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

import modal
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.shared_data import (
    SharedDataPath,
    count_files,
    get_processed_data_dir,
    get_raw_data_dir,
    iter_files,
    load_json_file,
    read_file_bytes,
)
from modal_app.common import safe_volume_reload
from modal_app.runtime import ENABLE_CCTV_ANALYSIS, get_modal_cls, get_modal_function
from modal_app.volume import app, sandbox_image, volume

router = APIRouter()

PROCESSED_DATA_PATH = None

ANALYSIS_EXEC_TIMEOUT_SECONDS = 90
ANALYSIS_SANDBOX_LIFETIME_SECONDS = ANALYSIS_EXEC_TIMEOUT_SECONDS + 60

CODEGEN_SYSTEM_PROMPT = """You are a data analyst. Write a self-contained Python script that answers the user's question using real data files.

Rules:
- Read the prepared JSON files from /data/raw/{source}/ and /data/processed/enriched/
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
- Read the prepared JSON files from /data/raw/{source}/ and /data/processed/enriched/
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


@dataclass(frozen=True)
class AnalysisInputArtifact:
    source_path: Path | SharedDataPath
    sandbox_path: str


def _relative_artifact_path(path, root) -> str:
    try:
        relative = path.relative_to(root)
    except Exception:
        relative = PurePosixPath(path.name)
    return relative.as_posix() if hasattr(relative, "as_posix") else str(relative).replace("\\", "/")


def _analysis_artifact(path, root, sandbox_root: str) -> AnalysisInputArtifact:
    relative = _relative_artifact_path(path, root)
    return AnalysisInputArtifact(source_path=path, sandbox_path=f"{sandbox_root.rstrip('/')}/{relative}")


def discover_data_files(neighborhood: str | None = None) -> dict:
    del neighborhood
    sources = {}
    raw = get_raw_data_dir()

    for source_dir in sorted(raw.iterdir()):
        if not source_dir.is_dir():
            continue
        json_files = iter_files(source_dir, recursive=True, pattern="*.json")[:20]
        if not json_files:
            continue
        schema_keys = []
        try:
            sample = load_json_file(json_files[0], default=None)
            if isinstance(sample, dict):
                schema_keys = list(sample.keys())[:10]
        except Exception:
            pass
        sources[source_dir.name] = {
            "count": count_files(source_dir, pattern="*.json"),
            "sample_path": str(json_files[0]),
            "schema_keys": schema_keys,
            "_artifacts": [
                _analysis_artifact(path, source_dir, f"/data/raw/{source_dir.name}")
                for path in json_files
            ],
        }

    enriched = _processed_data_dir() / "enriched"
    json_files = iter_files(enriched, recursive=True, pattern="*.json")[:20]
    if json_files:
        schema_keys = []
        try:
            sample = load_json_file(json_files[0], default=None)
            if isinstance(sample, dict):
                schema_keys = list(sample.keys())[:10]
        except Exception:
            pass
        sources["enriched"] = {
            "count": count_files(enriched, pattern="*.json"),
            "sample_path": str(json_files[0]),
            "schema_keys": schema_keys,
            "_artifacts": [
                _analysis_artifact(path, enriched, "/data/processed/enriched")
                for path in json_files
            ],
        }
    return sources


def _processed_data_dir():
    if PROCESSED_DATA_PATH is not None:
        return Path(PROCESSED_DATA_PATH)
    return get_processed_data_dir()


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

Available data prepared inside the sandbox:
{source_listing}

The listed files are materialized under /data before your script runs.
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


@dataclass
class SandboxAnalysisResult:
    stdout: str
    stderr: str
    returncode: int | None
    result: dict | None
    chart_b64: str | None


class AnalysisSandboxTimeout(Exception):
    pass


def _analysis_input_artifacts(available_sources: dict) -> list[AnalysisInputArtifact]:
    artifacts: list[AnalysisInputArtifact] = []
    for info in available_sources.values():
        if not isinstance(info, dict):
            continue
        source_artifacts = info.get("_artifacts", [])
        if isinstance(source_artifacts, list):
            artifacts.extend(
                artifact
                for artifact in source_artifacts
                if isinstance(artifact, AnalysisInputArtifact)
            )
    return artifacts


async def _modal_call(method, *args, **kwargs):
    aio = getattr(method, "aio", None)
    if callable(aio):
        return await aio(*args, **kwargs)
    return await asyncio.to_thread(method, *args, **kwargs)


async def _read_stream(stream) -> str:
    data = await _modal_call(stream.read)
    return data if isinstance(data, str) else data.decode("utf-8", errors="replace")


async def _sandbox_read_file(sb, path: str, mode: str):
    filesystem = getattr(sb, "filesystem", None)
    if filesystem is not None:
        if "b" in mode:
            read_bytes = getattr(filesystem, "read_bytes", None)
            if read_bytes is not None:
                return await _modal_call(read_bytes, path)
        else:
            read_text = getattr(filesystem, "read_text", None)
            if read_text is not None:
                return await _modal_call(read_text, path)

    file_obj = await _modal_call(sb.open, path, mode)
    try:
        return await _modal_call(file_obj.read)
    finally:
        await _modal_call(file_obj.close)


async def _sandbox_mkdir(sb, directory: str) -> None:
    if directory in {"", ".", "/"}:
        return
    process = await _modal_call(
        sb.exec,
        "python",
        "-c",
        f"import os; os.makedirs({directory!r}, exist_ok=True)",
        timeout=15,
    )
    await _modal_call(process.wait)


async def _sandbox_write_file(sb, path: str, data: bytes) -> None:
    await _sandbox_mkdir(sb, str(PurePosixPath(path).parent))

    filesystem = getattr(sb, "filesystem", None)
    if filesystem is not None:
        write_bytes = getattr(filesystem, "write_bytes", None)
        if write_bytes is not None:
            await _modal_call(write_bytes, path, data)
            return

    file_obj = await _modal_call(sb.open, path, "wb")
    try:
        await _modal_call(file_obj.write, data)
    finally:
        await _modal_call(file_obj.close)


async def _materialize_analysis_inputs(sb, artifacts: list[AnalysisInputArtifact]) -> None:
    for artifact in artifacts:
        raw = read_file_bytes(artifact.source_path, default=None)
        if raw is None:
            continue
        await _sandbox_write_file(sb, artifact.sandbox_path, raw)


async def _terminate_sandbox(sb) -> None:
    try:
        await _modal_call(sb.terminate, wait=True)
    except TypeError:
        await _modal_call(sb.terminate)
    except Exception:
        pass


async def execute_generated_analysis(
    code: str,
    input_artifacts: list[AnalysisInputArtifact] | None = None,
) -> SandboxAnalysisResult:
    sb = None
    try:
        # Keep the Sandbox container alive while the generated script runs as a
        # child process. Modal file access is unavailable after the container's
        # main process exits, so outputs must be read before cleanup.
        sb = await _modal_call(
            modal.Sandbox.create,
            "sleep",
            str(ANALYSIS_SANDBOX_LIFETIME_SECONDS),
            image=sandbox_image,
            volumes={"/data": volume},
            timeout=ANALYSIS_SANDBOX_LIFETIME_SECONDS,
            app=app,
        )
        if input_artifacts:
            await _materialize_analysis_inputs(sb, input_artifacts)
        process = await _modal_call(
            sb.exec,
            "python",
            "-c",
            code,
            timeout=ANALYSIS_EXEC_TIMEOUT_SECONDS,
        )

        try:
            stdout_text, stderr_text, returncode = await asyncio.gather(
                _read_stream(process.stdout),
                _read_stream(process.stderr),
                _modal_call(process.wait),
            )
        except Exception as exc:
            exec_timeout_error = getattr(modal.exception, "ExecTimeoutError", None)
            if exec_timeout_error is not None and isinstance(exc, exec_timeout_error):
                raise AnalysisSandboxTimeout(
                    f"Generated analysis timed out after {ANALYSIS_EXEC_TIMEOUT_SECONDS}s"
                ) from exc
            raise

        if returncode == -1:
            raise AnalysisSandboxTimeout(
                f"Generated analysis timed out after {ANALYSIS_EXEC_TIMEOUT_SECONDS}s"
            )

        result_data = None
        chart_b64 = None
        try:
            result_text = await _sandbox_read_file(sb, "/output/result.json", "r")
            result_data = json.loads(result_text)
        except Exception:
            result_data = None

        try:
            chart_bytes = await _sandbox_read_file(sb, "/output/chart.png", "rb")
            chart_b64 = base64.b64encode(chart_bytes).decode("utf-8")
        except Exception:
            chart_b64 = None

        return SandboxAnalysisResult(
            stdout=stdout_text,
            stderr=stderr_text,
            returncode=returncode,
            result=result_data,
            chart_b64=chart_b64,
        )
    finally:
        if sb is not None:
            await _terminate_sandbox(sb)


@router.get("/gpu-metrics")
async def gpu_metrics(probe_h100: bool = False):
    del probe_h100
    results = {
        "h100_llm": {"status": "disabled"},
        "t4_classifier": {"status": "cold"},
        "t4_sentiment": {"status": "cold"},
        "t4_cctv": {"status": "cold"} if ENABLE_CCTV_ANALYSIS else {"status": "disabled"},
    }

    gpu_classes = [("TrafficAnalyzer", "t4_cctv")] if ENABLE_CCTV_ANALYSIS else []

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
        enriched_files = iter_files(_processed_data_dir() / "enriched", pattern="*.json")
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

        sandbox_result = await execute_generated_analysis(code, _analysis_input_artifacts(available))
        stderr_text = sandbox_result.stderr
        stdout_text = sandbox_result.stdout
        result_data = sandbox_result.result
        chart_b64 = sandbox_result.chart_b64

        if sandbox_result.returncode not in (0, None) and result_data is None:
            return JSONResponse(
                {
                    "error": "Generated analysis script failed",
                    "stderr": stderr_text[:2000] if stderr_text else None,
                    "stdout": stdout_text[:2000] if stdout_text else None,
                    "returncode": sandbox_result.returncode,
                },
                status_code=500,
            )

        if result_data is None and stdout_text.strip():
            result_data = {"title": "Analysis Result", "summary": stdout_text.strip()[:2000], "stats": {}}

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
    except AnalysisSandboxTimeout as exc:
        if span:
            span.set_attribute("error", str(exc))
        return JSONResponse({"error": str(exc)}, status_code=504)
    except Exception as exc:
        if span:
            span.set_attribute("error", str(exc))
        return JSONResponse({"error": str(exc)}, status_code=500)
    finally:
        if span_ctx:
            span_ctx.__exit__(None, None, None)


@router.get("/impact-briefs")
async def list_impact_briefs(limit: int = 20, min_score: float = 0.0):
    await safe_volume_reload(volume, "impact_briefs")
    briefs_dir = _processed_data_dir() / "impact_briefs"

    briefs = []
    for json_file in iter_files(briefs_dir, pattern="*.json")[:limit]:
        try:
            brief = load_json_file(json_file, default=None)
            if not isinstance(brief, dict):
                continue
            if brief.get("impact_score", 0) >= min_score:
                briefs.append(brief)
        except Exception:
            continue
    return {"briefs": briefs, "count": len(briefs)}


@router.get("/impact-briefs/{brief_id}")
async def get_impact_brief(brief_id: str):
    await safe_volume_reload(volume, "impact_brief")
    briefs_dir = _processed_data_dir() / "impact_briefs"

    for json_file in iter_files(briefs_dir, pattern="*.json"):
        try:
            brief = load_json_file(json_file, default=None)
            if not isinstance(brief, dict):
                continue
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
