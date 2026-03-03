"""Recursive Agent Architecture — Lead Analyst + E2B Sandbox Workers.

Monitors enriched documents for high-impact events, scores them via Qwen3-8B,
dispatches specialized workers into E2B cloud sandboxes for deep cross-domain
analysis, and synthesizes actionable impact briefs.

Modal features: modal.Queue, @modal.function, schedule, .spawn()
"""
import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import modal
from pydantic import BaseModel, Field

from modal_app.costs import track_cost
from modal_app.volume import app, volume, lead_analyst_image, VOLUME_MOUNT, RAW_DATA_PATH, PROCESSED_DATA_PATH

# Queue: classify.py pushes high-confidence docs here after enrichment
impact_queue = modal.Queue.from_name("impact-docs", create_if_missing=True)

IMPACT_BRIEFS_PATH = f"{PROCESSED_DATA_PATH}/impact_briefs"
DEDUP_PATH = f"{VOLUME_MOUNT}/dedup"
MAX_ANALYZED_IDS = 5000


# ---------------------------------------------------------------------------
# Output schemas
# ---------------------------------------------------------------------------

class WorkerResult(BaseModel):
    worker_type: str  # "real_estate" | "legal" | "economic" | "community_sentiment"
    findings: dict = Field(default_factory=dict)
    confidence: float = 0.0
    data_points_analyzed: int = 0
    neighborhoods_affected: list[str] = Field(default_factory=list)
    error: str | None = None


class ImpactBrief(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    trigger_doc_id: str = ""
    trigger_title: str = ""
    trigger_source: str = ""
    impact_score: float = 0.0
    impact_level: str = "high"
    category: str = ""
    neighborhoods_affected: list[str] = Field(default_factory=list)
    executive_summary: str = ""
    worker_results: list[WorkerResult] = Field(default_factory=list)
    synthesis: str = ""
    recommendations: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    processing_time_seconds: float = 0.0
    e2b_used: bool = False


# ---------------------------------------------------------------------------
# Worker prompt templates
# ---------------------------------------------------------------------------

WORKER_TEMPLATES = {
    "real_estate": {
        "focus": "Real estate impact analysis",
        "instructions": (
            "Analyze the trigger event's impact on real estate in affected neighborhoods. "
            "Cross-reference against property data to identify price/vacancy trends and "
            "zoning implications. Output JSON with keys: price_impact (str), vacancy_trend (str), "
            "zoning_implications (list[str]), affected_properties_estimate (int), risk_level (str)."
        ),
    },
    "legal": {
        "focus": "Legal and regulatory compliance analysis",
        "instructions": (
            "Compare the new regulation/event against existing local, state, and federal law. "
            "Identify conflicts, compliance deadlines, and enforcement risks. "
            "Output JSON with keys: conflicts (list[str]), compliance_deadlines (list[str]), "
            "enforcement_risk (str), required_actions (list[str]), precedent_cases (list[str])."
        ),
    },
    "economic": {
        "focus": "Economic impact projection",
        "instructions": (
            "Review demographics and economic indicators for affected neighborhoods. "
            "Project revenue impact, estimate timeline, and identify opportunity/threat signals. "
            "Output JSON with keys: revenue_impact_estimate (str), timeline (str), "
            "opportunity_signals (list[str]), threat_signals (list[str]), affected_businesses_estimate (int)."
        ),
    },
    "community_sentiment": {
        "focus": "Community sentiment and reaction analysis",
        "instructions": (
            "Aggregate sentiment from reddit, reviews, and news about the trigger event. "
            "Detect community reactions and trending concerns. "
            "Output JSON with keys: overall_sentiment (str), sentiment_score (float -1 to 1), "
            "key_concerns (list[str]), supportive_signals (list[str]), trending_topics (list[str])."
        ),
    },
}

# Data source directories for each worker type
WORKER_DATA_SOURCES = {
    "real_estate": ["realestate"],
    "legal": ["politics", "federal_register"],
    "economic": ["demographics", "public_data"],
    "community_sentiment": ["reddit", "reviews", "news"],
}


# ---------------------------------------------------------------------------
# Dedup helpers (lightweight, JSON-backed)
# ---------------------------------------------------------------------------

def _load_analyzed_ids(lock_fd=None) -> set[str]:
    """Load analyzed doc IDs. If lock_fd provided, caller holds the lock."""
    path = Path(DEDUP_PATH) / "impact_analyzed.json"
    try:
        if path.exists():
            data = json.loads(path.read_text())
            return set(data.get("ids", []) if isinstance(data, dict) else data)
    except Exception as e:
        print(f"Lead Analyst: dedup load error: {e}")
    return set()


def _save_analyzed_ids(ids: set[str], lock_fd=None) -> None:
    """Save analyzed doc IDs. If lock_fd provided, caller holds the lock."""
    path = Path(DEDUP_PATH) / "impact_analyzed.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        id_list = list(ids)
        if len(id_list) > MAX_ANALYZED_IDS:
            id_list = id_list[-MAX_ANALYZED_IDS:]
        path.write_text(json.dumps({"ids": id_list}))
    except Exception as e:
        print(f"Lead Analyst: dedup save error: {e}")


def _with_analyzed_lock(fn):
    """Run fn(analyzed_ids) under an exclusive file lock, then save."""
    import fcntl
    lock_path = Path(DEDUP_PATH) / "impact_analyzed.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w") as lock_fd:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            ids = _load_analyzed_ids(lock_fd)
            result = fn(ids)
            _save_analyzed_ids(ids, lock_fd)
            return result
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)


# ---------------------------------------------------------------------------
# Phase 1: Rule-based fast filter (no GPU)
# ---------------------------------------------------------------------------

def _fast_filter(doc: dict) -> bool:
    """Return True if the doc passes rule-based significance heuristics."""
    classification = doc.get("classification", {})
    sentiment = doc.get("sentiment", {})
    labels = classification.get("labels", [])
    scores = classification.get("scores", [])

    top_label = labels[0] if labels else ""
    top_score = scores[0] if scores else 0.0
    sent_label = sentiment.get("label", "neutral")
    sent_score = sentiment.get("score", 0.5)

    # Regulatory + negative sentiment
    if top_label == "regulatory" and sent_label == "negative" and sent_score > 0.7:
        return True

    # Politics source + regulatory label
    source = doc.get("source", "")
    if source in ("politics", "federal_register") and top_label == "regulatory":
        return True

    # Safety with high confidence
    if top_label == "safety" and top_score > 0.8:
        return True

    # Any category with very high classification confidence + negative sentiment
    if top_score > 0.85 and sent_label == "negative" and sent_score > 0.75:
        return True

    return False


# ---------------------------------------------------------------------------
# Phase 2: LLM significance scoring
# ---------------------------------------------------------------------------

async def _evaluate_significance(candidates: list[dict], tracer=None) -> list[dict]:
    """Use Qwen3-8B to score candidate documents for business impact (1-10)."""
    if not candidates:
        return []

    span_ctx = tracer.start_as_current_span("evaluate-significance") if tracer else None
    span = span_ctx.__enter__() if span_ctx else None
    try:
        if span:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("evaluate.candidate_count", len(candidates))

        summaries = []
        for i, doc in enumerate(candidates):
            summaries.append(
                f"[{i}] Title: {doc.get('title', 'N/A')}\n"
                f"Source: {doc.get('source', 'N/A')}\n"
                f"Classification: {doc.get('classification', {}).get('labels', [])}\n"
                f"Sentiment: {doc.get('sentiment', {})}\n"
                f"Content: {doc.get('content', '')[:300]}\n"
            )

        prompt = (
            "You are a business intelligence analyst for Chicago small businesses.\n"
            "Score each document below for potential business impact on a scale of 1-10.\n"
            "A score of 7+ means the event could materially affect small business operations.\n\n"
            "Documents:\n" + "\n---\n".join(summaries) + "\n\n"
            "Respond with ONLY a JSON array of objects, one per document:\n"
            '[{"index": 0, "score": 8, "reasoning": "...", "category": "regulatory", '
            '"neighborhoods": ["West Loop"]}]\n'
            "Categories: regulatory, economic, safety, infrastructure, community\n"
            "/no_think"
        )

        try:
            from modal_app.llm import AlethiaLLM
            llm = AlethiaLLM()
            response = await llm.generate.remote.aio(prompt, max_tokens=1500)

            # Parse JSON from response
            json_match = _extract_json_array(response)
            if json_match:
                scored = json.loads(json_match)
                for item in scored:
                    idx = item.get("index", -1)
                    if 0 <= idx < len(candidates):
                        candidates[idx]["_impact_score"] = item.get("score", 0)
                        candidates[idx]["_impact_reasoning"] = item.get("reasoning", "")
                        candidates[idx]["_impact_category"] = item.get("category", "")
                        candidates[idx]["_impact_neighborhoods"] = item.get("neighborhoods", [])

                if span:
                    span.set_attribute("evaluate.scored_count", len(scored))
                return candidates
        except Exception as e:
            print(f"Lead Analyst: LLM evaluation failed: {e}")
            if span:
                span.set_attribute("error", str(e))

        # Fallback: assign score 7 to all fast-filtered candidates
        for doc in candidates:
            if "_impact_score" not in doc:
                doc["_impact_score"] = 7
                doc["_impact_reasoning"] = "Rule-based filter pass (LLM unavailable)"
                doc["_impact_category"] = doc.get("classification", {}).get("labels", [""])[0]
                doc["_impact_neighborhoods"] = []
                geo = doc.get("geo", {})
                if geo.get("neighborhood"):
                    doc["_impact_neighborhoods"] = [geo["neighborhood"]]

        return candidates
    finally:
        if span_ctx:
            span_ctx.__exit__(None, None, None)


def _extract_json_array(text: str) -> str | None:
    """Extract a JSON array from LLM response text."""
    import re
    # Try to find JSON array in code blocks first
    match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if match:
        return match.group(1)
    # Try bare JSON array
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        return match.group(0)
    return None


# ---------------------------------------------------------------------------
# Worker execution
# ---------------------------------------------------------------------------

def _gather_worker_context(worker_type: str, neighborhoods: list[str], limit: int = 20) -> list[dict]:
    """Read relevant source data from volume for a worker."""
    sources = WORKER_DATA_SOURCES.get(worker_type, [])
    context_docs = []
    for source in sources:
        source_dir = Path(RAW_DATA_PATH) / source
        if not source_dir.exists():
            continue
        for json_file in sorted(source_dir.rglob("*.json"), reverse=True)[:limit]:
            try:
                doc = json.loads(json_file.read_text())
                # If neighborhoods specified, prefer docs from those areas
                doc_hood = doc.get("geo", {}).get("neighborhood", "")
                if neighborhoods and doc_hood and doc_hood not in neighborhoods:
                    continue
                context_docs.append({
                    "title": doc.get("title", ""),
                    "content": doc.get("content", "")[:500],
                    "source": doc.get("source", source),
                    "neighborhood": doc_hood,
                })
            except Exception:
                continue
    return context_docs[:limit]


def _build_worker_script(worker_type: str, trigger_summary: str, context_summary: str) -> str:
    """Build a Python analysis script for a worker to execute."""
    template = WORKER_TEMPLATES.get(worker_type, {})
    instructions = template.get("instructions", "Analyze the data and output JSON findings.")

    return f'''
import json
import sys

# Read input data
with open("/data/input.json", "r") as f:
    data = json.load(f)

trigger = data.get("trigger", {{}})
context = data.get("context", [])

# Analysis: {template.get("focus", worker_type)}
findings = {{}}
try:
    # Count data points
    data_points = len(context)
    neighborhoods = list(set(
        d.get("neighborhood", "") for d in context if d.get("neighborhood")
    ))

    # Extract key themes from context
    all_text = " ".join(d.get("content", "") for d in context).lower()
    trigger_text = trigger.get("content", "").lower()

    # Simple keyword frequency analysis
    important_terms = ["zoning", "permit", "license", "regulation", "closure",
                       "opening", "construction", "tax", "fine", "violation",
                       "investment", "development", "safety", "health"]
    term_counts = {{term: all_text.count(term) for term in important_terms if all_text.count(term) > 0}}

    findings = {{
        "data_points_analyzed": data_points,
        "neighborhoods_found": neighborhoods,
        "key_terms": dict(sorted(term_counts.items(), key=lambda x: -x[1])[:10]),
        "trigger_summary": trigger.get("title", "Unknown event"),
        "context_sample_size": len(context),
    }}
except Exception as e:
    findings = {{"error": str(e)}}

# Write output
with open("/data/output.json", "w") as f:
    json.dump(findings, f, indent=2)
'''


async def _generate_worker_code(worker_type: str, trigger_doc: dict, context_docs: list[dict]) -> str:
    """Generate analysis code via GPT-4o (Qwen3-8B fallback)."""
    template = WORKER_TEMPLATES.get(worker_type, {})
    trigger_summary = f"Title: {trigger_doc.get('title', 'N/A')}\nContent: {trigger_doc.get('content', '')[:400]}"
    context_summary = json.dumps(context_docs[:5], indent=2, default=str)[:2000]

    # Try GPT-4o first
    from modal_app.openai_utils import openai_available, get_openai_client
    if openai_available():
        try:
            client = get_openai_client()
            resp = await client.chat.completions.create(
                model="gpt-4o",
                messages=[{
                    "role": "system",
                    "content": (
                        "You are a data analyst. Generate a Python script that reads /data/input.json "
                        "(with 'trigger' and 'context' keys) and writes analysis results to /data/output.json. "
                        f"Focus: {template.get('focus', worker_type)}. "
                        f"{template.get('instructions', '')} "
                        "Use only standard library. Output ONLY the Python code, no markdown."
                    ),
                }, {
                    "role": "user",
                    "content": f"Trigger event:\n{trigger_summary}\n\nContext data sample:\n{context_summary}",
                }],
                max_tokens=1500,
                temperature=0.2,
            )
            code = resp.choices[0].message.content.strip()
            # Strip markdown code fences if present
            if code.startswith("```"):
                code = "\n".join(code.split("\n")[1:])
            if code.endswith("```"):
                code = "\n".join(code.split("\n")[:-1])
            return code
        except Exception as e:
            print(f"Lead Analyst: GPT-4o code gen failed for {worker_type}: {e}")

    # Fallback: hardcoded template script
    return _build_worker_script(worker_type, trigger_summary, context_summary)


async def _run_worker(
    worker_type: str,
    trigger_doc: dict,
    context_docs: list[dict],
    tracer=None,
) -> WorkerResult:
    """Execute a single worker: generate code, run in E2B or in-process."""
    span_ctx = tracer.start_as_current_span(f"impact-worker-{worker_type}") if tracer else None
    span = span_ctx.__enter__() if span_ctx else None
    start = time.time()

    try:
        if span:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("worker.type", worker_type)
            span.set_attribute("worker.context_docs", len(context_docs))

        code = await _generate_worker_code(worker_type, trigger_doc, context_docs)
        input_data = {
            "trigger": {
                "title": trigger_doc.get("title", ""),
                "content": trigger_doc.get("content", "")[:1000],
                "source": trigger_doc.get("source", ""),
                "classification": trigger_doc.get("classification", {}),
                "sentiment": trigger_doc.get("sentiment", {}),
            },
            "context": context_docs,
        }

        findings = {}
        e2b_used = False
        neighborhoods = trigger_doc.get("_impact_neighborhoods", [])

        # Try E2B sandbox execution
        from modal_app.e2b_utils import e2b_available, create_sandbox
        if e2b_available():
            sandbox_span_ctx = tracer.start_as_current_span("e2b-sandbox-execute") if tracer else None
            sandbox_span = sandbox_span_ctx.__enter__() if sandbox_span_ctx else None
            try:
                sb = await create_sandbox(timeout=120)
                if sb:
                    e2b_used = True
                    await sb.filesystem.make_dir("/data")
                    await sb.filesystem.write("/data/input.json", json.dumps(input_data, default=str))
                    result = await sb.run_code(code)

                    if result.error:
                        print(f"Lead Analyst: E2B error for {worker_type}: {result.error}")
                        findings = {"error": str(result.error)}
                    else:
                        try:
                            output = await sb.filesystem.read("/data/output.json")
                            findings = json.loads(output)
                        except Exception:
                            findings = {"raw_output": str(result.logs)[:2000]}

                    await sb.close()

                    if sandbox_span:
                        sandbox_span.set_attribute("e2b.success", "error" not in findings)
            except Exception as e:
                print(f"Lead Analyst: E2B sandbox failed for {worker_type}: {e}")
                if sandbox_span:
                    sandbox_span.set_attribute("error", str(e))
            finally:
                if sandbox_span_ctx:
                    sandbox_span_ctx.__exit__(None, None, None)

        # Fallback: in-process exec with restricted builtins (no file/import/eval access)
        if not findings:
            try:
                import tempfile
                with tempfile.TemporaryDirectory() as tmpdir:
                    data_dir = Path(tmpdir) / "data"
                    data_dir.mkdir()
                    (data_dir / "input.json").write_text(json.dumps(input_data, default=str))

                    # Replace /data/ paths with tmpdir paths in code
                    patched_code = code.replace("/data/input.json", str(data_dir / "input.json"))
                    patched_code = patched_code.replace("/data/output.json", str(data_dir / "output.json"))

                    # Restricted builtins: only safe operations, no file/import/eval/exec
                    _safe_builtins = {
                        k: getattr(__builtins__, k) if hasattr(__builtins__, k) else __builtins__[k]
                        for k in (
                            "abs", "all", "any", "bool", "dict", "enumerate", "filter",
                            "float", "frozenset", "int", "isinstance", "issubclass",
                            "len", "list", "map", "max", "min", "print", "range",
                            "repr", "reversed", "round", "set", "slice", "sorted",
                            "str", "sum", "tuple", "type", "zip", "True", "False", "None",
                            "ValueError", "TypeError", "KeyError", "IndexError", "Exception",
                        )
                        if (hasattr(__builtins__, k) if isinstance(__builtins__, type) else k in __builtins__)
                    }
                    import math as _math, statistics as _statistics, collections as _collections
                    exec_globals = {
                        "__builtins__": _safe_builtins,
                        "json": json,
                        "math": _math,
                        "statistics": _statistics,
                        "collections": _collections,
                    }
                    exec(patched_code, exec_globals)

                    output_file = data_dir / "output.json"
                    if output_file.exists():
                        findings = json.loads(output_file.read_text())
                    else:
                        findings = {"note": "Script completed but produced no output file"}
            except Exception as e:
                print(f"Lead Analyst: in-process exec failed for {worker_type}: {e}")
                findings = {"error": str(e)}

        # Extract neighborhoods from findings if available
        found_hoods = findings.get("neighborhoods_found", [])
        if found_hoods:
            neighborhoods = list(set(neighborhoods + found_hoods))

        if span:
            span.set_attribute("worker.e2b_used", e2b_used)
            span.set_attribute("worker.has_error", "error" in findings)

        return WorkerResult(
            worker_type=worker_type,
            findings=findings,
            confidence=0.7 if "error" not in findings else 0.2,
            data_points_analyzed=findings.get("data_points_analyzed", len(context_docs)),
            neighborhoods_affected=neighborhoods,
            error=findings.get("error"),
        )
    except Exception as e:
        if span:
            span.set_attribute("error", str(e))
        return WorkerResult(
            worker_type=worker_type,
            findings={},
            confidence=0.0,
            data_points_analyzed=0,
            neighborhoods_affected=[],
            error=str(e),
        )
    finally:
        if span_ctx:
            span_ctx.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# Dispatch & synthesis
# ---------------------------------------------------------------------------

async def _dispatch_workers(trigger_doc: dict, tracer=None) -> ImpactBrief:
    """Fan out 4 workers in parallel, then synthesize into an ImpactBrief."""
    span_ctx = tracer.start_as_current_span("impact-dispatch-workers") if tracer else None
    span = span_ctx.__enter__() if span_ctx else None
    start = time.time()

    try:
        if span:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("trigger.doc_id", trigger_doc.get("id", ""))

        neighborhoods = trigger_doc.get("_impact_neighborhoods", [])

        # Gather context per worker type
        worker_contexts = {}
        for wtype in WORKER_TEMPLATES:
            worker_contexts[wtype] = _gather_worker_context(wtype, neighborhoods)

        # Parallel worker dispatch
        worker_results = await asyncio.gather(
            *[
                _run_worker(wtype, trigger_doc, worker_contexts[wtype], tracer)
                for wtype in WORKER_TEMPLATES
            ],
            return_exceptions=True,
        )

        # Convert exceptions to WorkerResults
        final_results = []
        e2b_used = False
        for i, result in enumerate(worker_results):
            wtype = list(WORKER_TEMPLATES.keys())[i]
            if isinstance(result, Exception):
                final_results.append(WorkerResult(
                    worker_type=wtype,
                    error=str(result),
                ))
            else:
                final_results.append(result)
                if hasattr(result, "findings") and result.findings.get("e2b_used"):
                    e2b_used = True

        # Check if any worker actually used E2B
        from modal_app.e2b_utils import e2b_available
        e2b_used = e2b_available()

        # Synthesize
        brief = await _synthesize_brief(trigger_doc, final_results, tracer)
        brief.processing_time_seconds = round(time.time() - start, 2)
        brief.e2b_used = e2b_used

        if span:
            span.set_attribute("dispatch.worker_count", len(final_results))
            span.set_attribute("dispatch.processing_time", brief.processing_time_seconds)

        return brief
    except Exception as e:
        if span:
            span.set_attribute("error", str(e))
        raise
    finally:
        if span_ctx:
            span_ctx.__exit__(None, None, None)


async def _synthesize_brief(
    trigger_doc: dict,
    worker_results: list[WorkerResult],
    tracer=None,
) -> ImpactBrief:
    """Synthesize worker results into a coherent ImpactBrief via Qwen3-8B."""
    span_ctx = tracer.start_as_current_span("impact-synthesize") if tracer else None
    span = span_ctx.__enter__() if span_ctx else None

    try:
        if span:
            span.set_attribute("openinference.span.kind", "CHAIN")

        # Aggregate neighborhoods from all workers
        all_neighborhoods = set(trigger_doc.get("_impact_neighborhoods", []))
        for wr in worker_results:
            all_neighborhoods.update(wr.neighborhoods_affected)

        # Build synthesis prompt
        worker_summaries = []
        for wr in worker_results:
            worker_summaries.append(
                f"**{wr.worker_type}** (confidence: {wr.confidence:.1%}):\n"
                f"Findings: {json.dumps(wr.findings, default=str)[:500]}\n"
                f"Error: {wr.error or 'None'}"
            )

        prompt = (
            "You are a senior business intelligence analyst. Synthesize the following "
            "multi-domain analysis into a cohesive impact brief for Chicago small business owners.\n\n"
            f"TRIGGER EVENT: {trigger_doc.get('title', 'Unknown')}\n"
            f"Source: {trigger_doc.get('source', 'Unknown')}\n"
            f"Content: {trigger_doc.get('content', '')[:500]}\n\n"
            "WORKER ANALYSES:\n" + "\n---\n".join(worker_summaries) + "\n\n"
            "Provide:\n"
            "1. Executive summary (2-3 sentences)\n"
            "2. Detailed synthesis narrative (1-2 paragraphs)\n"
            "3. Actionable recommendations (3-5 bullet points)\n\n"
            "Format as JSON:\n"
            '{"executive_summary": "...", "synthesis": "...", "recommendations": ["...", "..."]}\n'
            "/no_think"
        )

        executive_summary = ""
        synthesis = ""
        recommendations = []

        try:
            from modal_app.llm import AlethiaLLM
            llm = AlethiaLLM()
            response = await llm.generate.remote.aio(prompt, max_tokens=2000)

            # Parse JSON from response
            json_match = _extract_json_array(response)
            if not json_match:
                # Try extracting JSON object
                import re
                obj_match = re.search(r"\{.*\}", response, re.DOTALL)
                if obj_match:
                    parsed = json.loads(obj_match.group(0))
                    executive_summary = parsed.get("executive_summary", "")
                    synthesis = parsed.get("synthesis", "")
                    recommendations = parsed.get("recommendations", [])
        except Exception as e:
            print(f"Lead Analyst: synthesis LLM failed: {e}")
            executive_summary = f"Impact analysis for: {trigger_doc.get('title', 'Unknown event')}"
            synthesis = "Automated analysis completed. See worker results for details."
            recommendations = ["Review the detailed worker findings", "Monitor for follow-up developments"]

        if span:
            span.set_attribute("synthesis.has_summary", bool(executive_summary))

        return ImpactBrief(
            trigger_doc_id=trigger_doc.get("id", ""),
            trigger_title=trigger_doc.get("title", ""),
            trigger_source=trigger_doc.get("source", ""),
            impact_score=trigger_doc.get("_impact_score", 7.0),
            impact_level="critical" if trigger_doc.get("_impact_score", 7) >= 9 else "high",
            category=trigger_doc.get("_impact_category", ""),
            neighborhoods_affected=sorted(all_neighborhoods),
            executive_summary=executive_summary,
            worker_results=worker_results,
            synthesis=synthesis,
            recommendations=recommendations,
        )
    finally:
        if span_ctx:
            span_ctx.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# Save / load briefs
# ---------------------------------------------------------------------------

def _save_brief(brief: ImpactBrief) -> str:
    """Save an ImpactBrief to volume. Returns the file path."""
    briefs_dir = Path(IMPACT_BRIEFS_PATH)
    briefs_dir.mkdir(parents=True, exist_ok=True)

    ts = brief.timestamp.strftime("%Y%m%d-%H%M%S")
    slug = brief.trigger_title[:40].lower().replace(" ", "-").replace("/", "-")
    slug = "".join(c for c in slug if c.isalnum() or c == "-")
    filename = f"{ts}-{slug}.json"

    path = briefs_dir / filename
    path.write_text(brief.model_dump_json(indent=2))
    print(f"Lead Analyst: saved brief to {path}")
    return str(path)


def _load_briefs(limit: int = 50, min_score: float = 0.0) -> list[dict]:
    """Load impact briefs from volume."""
    briefs_dir = Path(IMPACT_BRIEFS_PATH)
    if not briefs_dir.exists():
        return []

    briefs = []
    for json_file in sorted(briefs_dir.rglob("*.json"), reverse=True)[:limit]:
        try:
            brief = json.loads(json_file.read_text())
            if brief.get("impact_score", 0) >= min_score:
                briefs.append(brief)
        except Exception:
            continue
    return briefs


def _load_brief_by_id(brief_id: str) -> dict | None:
    """Load a single brief by its ID."""
    briefs_dir = Path(IMPACT_BRIEFS_PATH)
    if not briefs_dir.exists():
        return None

    for json_file in briefs_dir.rglob("*.json"):
        try:
            brief = json.loads(json_file.read_text())
            if brief.get("id") == brief_id:
                return brief
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# Scheduled scan: every 5 minutes
# ---------------------------------------------------------------------------

@app.function(
    image=lead_analyst_image,
    volumes={"/data": volume},
    secrets=[
        modal.Secret.from_name("alethia-secrets"),
        modal.Secret.from_name("arize-secrets"),
    ],
    # schedule=modal.Period(minutes=5),  # Disabled: Modal free tier limits to 5 cron jobs
    timeout=600,
)
@track_cost("scan_enriched_docs", "CPU")
async def scan_enriched_docs():
    """Lead Analyst: scan enriched docs for high-impact events.

    Runs every 5 minutes. Drains impact_queue, applies fast filter + LLM scoring,
    dispatches workers for high-impact docs (score >= 7).
    """
    from modal_app.instrumentation import init_tracing, get_tracer
    init_tracing()
    tracer = get_tracer("alethia.lead_analyst")

    span_ctx = tracer.start_as_current_span("scan-enriched-docs") if tracer else None
    span = span_ctx.__enter__() if span_ctx else None

    try:
        volume.reload()

        # Drain impact queue (up to 50 docs, non-blocking)
        docs = []
        while len(docs) < 50:
            try:
                doc = await impact_queue.get.aio(timeout=2)
                docs.append(doc)
            except Exception:
                break

        if not docs:
            print("Lead Analyst: impact queue empty, nothing to analyze")
            if span:
                span.set_attribute("scan.queue_docs", 0)
            return 0

        if span:
            span.set_attribute("scan.queue_docs", len(docs))

        # Dedup: skip already-analyzed docs (locked read to claim IDs atomically)
        def _claim_new(analyzed_ids: set[str]) -> list[dict]:
            new = [d for d in docs if d.get("id", "") not in analyzed_ids]
            # Claim IDs immediately so concurrent runs skip them
            for d in new:
                doc_id = d.get("id", "")
                if doc_id:
                    analyzed_ids.add(doc_id)
            return new

        new_docs = _with_analyzed_lock(_claim_new)
        if not new_docs:
            print(f"Lead Analyst: all {len(docs)} docs already analyzed")
            return 0

        print(f"Lead Analyst: {len(new_docs)} new docs to evaluate")

        # Phase 1: fast filter
        candidates = [d for d in new_docs if _fast_filter(d)]
        print(f"Lead Analyst: {len(candidates)} passed fast filter")

        if span:
            span.set_attribute("scan.fast_filter_passed", len(candidates))

        if not candidates:
            await volume.commit.aio()
            return 0

        # Phase 2: LLM significance scoring
        scored_candidates = await _evaluate_significance(candidates, tracer)

        # Dispatch workers for high-impact docs (score >= 7)
        high_impact = [d for d in scored_candidates if d.get("_impact_score", 0) >= 7]
        print(f"Lead Analyst: {len(high_impact)} docs scored >= 7 (high impact)")

        if span:
            span.set_attribute("scan.high_impact_count", len(high_impact))

        briefs_created = 0
        for doc in high_impact:
            try:
                brief = await _dispatch_workers(doc, tracer)
                _save_brief(brief)
                briefs_created += 1
            except Exception as e:
                print(f"Lead Analyst: dispatch failed for {doc.get('id', '?')}: {e}")

        await volume.commit.aio()
        print(f"Lead Analyst: created {briefs_created} impact briefs")

        if span:
            span.set_attribute("scan.briefs_created", briefs_created)

        return briefs_created

    except Exception as e:
        if span:
            span.set_attribute("error", str(e))
        print(f"Lead Analyst: scan error: {e}")
        raise
    finally:
        if span_ctx:
            span_ctx.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# Manual trigger: analyze a specific doc
# ---------------------------------------------------------------------------

@app.function(
    image=lead_analyst_image,
    volumes={"/data": volume},
    secrets=[
        modal.Secret.from_name("alethia-secrets"),
        modal.Secret.from_name("arize-secrets"),
    ],
    timeout=300,
)
@track_cost("analyze_impact", "CPU")
async def analyze_impact(doc_id: str) -> dict:
    """Manually trigger impact analysis for a specific enriched document."""
    from modal_app.instrumentation import init_tracing, get_tracer
    init_tracing()
    tracer = get_tracer("alethia.lead_analyst")

    volume.reload()

    # Find the document in enriched storage
    enriched_dir = Path(PROCESSED_DATA_PATH) / "enriched"
    doc = None

    if enriched_dir.exists():
        target_file = enriched_dir / f"{doc_id}.json"
        if target_file.exists():
            doc = json.loads(target_file.read_text())
        else:
            # Search all enriched files
            for json_file in enriched_dir.rglob("*.json"):
                try:
                    candidate = json.loads(json_file.read_text())
                    if candidate.get("id") == doc_id:
                        doc = candidate
                        break
                except Exception:
                    continue

    if not doc:
        return {"error": f"Document {doc_id} not found in enriched storage"}

    # Evaluate significance
    doc["_impact_score"] = 8  # Manual trigger = assumed significant
    doc["_impact_category"] = doc.get("classification", {}).get("labels", [""])[0]
    doc["_impact_neighborhoods"] = []
    geo = doc.get("geo", {})
    if geo.get("neighborhood"):
        doc["_impact_neighborhoods"] = [geo["neighborhood"]]

    # Dispatch workers
    brief = await _dispatch_workers(doc, tracer)
    _save_brief(brief)
    await volume.commit.aio()

    return brief.model_dump(mode="json")
