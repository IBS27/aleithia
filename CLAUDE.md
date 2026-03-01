# Alethia — Chicago Business Intelligence Platform

An AI-powered regulatory intelligence platform that aggregates live Chicago-area data (news, politics, social, public records, reviews, real estate, federal regulations, traffic, CCTV), analyzes it on Modal GPUs (Qwen3 8B on H100, bart-large-mnli + roberta on T4, YOLOv8n on T4), and delivers actionable insights to small business owners through a streaming chat + dashboard interface.

## Tech Stack

- **Frontend:** React 19 + TypeScript + Vite + Tailwind CSS v4
- **Backend:** Modal-hosted FastAPI via `@modal.asgi_app()` (no separate backend server)
- **LLM:** Qwen3 8B AWQ (INT4) self-hosted via vLLM on H100
- **Classification:** bart-large-mnli (zero-shot) + roberta (sentiment) on T4 GPUs
- **Vision:** YOLOv8n (pedestrian/vehicle detection) on T4 GPUs
- **Compute:** Modal (28+ serverless functions — pipelines, GPU inference, web API, agents, reconciler)
- **Memory:** Supermemory (RAG context, user profiles, doc sync)
- **Tracing:** Arize AX via OpenTelemetry (connected spans across Modal containers)
- **Data:** 13 pipelines ingesting 1,889+ documents across 47 Chicago neighborhoods

## Architecture

1. **Ingestion layer** — 13 Modal cron/on-demand functions scrape/poll heterogeneous sources (RSS, Chicago Data Portal, Reddit, Yelp/Google, Legistar, Federal Register, LoopNet, Census, TikTok, TomTom traffic, IDOT CCTV, YouTube, WorldPop) and normalize into a common `Document` schema. See `data_sources.md` for full catalog.
2. **Event bus** — `modal.Queue` connects pipelines to GPU classifiers. Pipelines push via `await doc_queue.put.aio()`.
3. **Enrichment layer** — `DocClassifier` (bart-large-mnli) + `SentimentAnalyzer` (roberta) on T4 GPUs classify documents into categories (regulatory, economic, safety, etc.) with sentiment scores. Batch processing via `@modal.batched` + `asyncio.gather()`.
4. **LLM layer** — Qwen3 8B AWQ (INT4) via vLLM on H100 for streaming chat responses and intelligence briefs. 20 concurrent inputs via `@modal.concurrent`. GPU memory snapshots for fast cold starts.
5. **Agent swarm** — 4 agent types (neighborhood intel, regulatory, comparison, synthesis) fan out via `.spawn()` for query-time parallel intelligence gathering. W3C trace context propagation links spans across containers.
6. **Self-healing** — Reconciler runs every 5 min, checks pipeline freshness, auto-restarts stale ingesters. Cost tracking via `modal.Dict`.
7. **Vision layer** — CCTV pipeline ingests IDOT highway camera frames, YOLOv8n detects pedestrians/vehicles for foot traffic density scoring. Vision pipeline trains custom detectors from YouTube walking tours.
8. **Observability** — Arize AX tracing with OpenTelemetry. Connected spans across web → orchestrator → agents → LLM. OpenAI auto-instrumentor for GPT-4V calls.
9. **Web API** — Modal-hosted FastAPI with 19 endpoints including `/chat`, `/brief/{neighborhood}`, `/neighborhood/{name}`, `/analyze`, `/cctv/latest`, `/cctv/frame/{camera_id}`, `/gpu-metrics`, `/status`, `/metrics`, `/health`.
10. **Deep Dive** — `/analyze` endpoint generates Python analysis scripts via LLM, runs them in `modal.Sandbox` against real pipeline data. Returns stats, charts (base64 PNG), and the generated code.

## Project Structure

```
modal_app/              — Modal functions (all compute runs here)
  __init__.py           — Function discovery (20 module imports, guarded by MODAL_IS_REMOTE)
  volume.py             — App, volumes, 14 custom images (THE entrypoint: `modal deploy -m modal_app`)
  common.py             — Document schema, SourceType enum, CHICAGO_NEIGHBORHOODS, detect_neighborhood()
  instrumentation.py    — Arize AX tracing: init_tracing(), get_tracer(), inject/extract_context()
  fallback.py           — FallbackChain pattern for resilient data fetching
  dedup.py              — SeenSet: persistent JSON-backed dedup (10k cap per source)
  compress.py           — Raw data compression → neighborhood summaries + GeoJSON for Mapbox
  llm.py                — AlethiaLLM class (Qwen3 8B AWQ on H100 via vLLM, GPU metrics)
  classify.py           — DocClassifier + SentimentAnalyzer on T4, Queue drain every 2min
  agents.py             — Agent swarm (neighborhood, regulatory, orchestrator) with trace context propagation
  web.py                — FastAPI web app served via @modal.asgi_app() (19 endpoints, incl. /analyze deep dive)
  reconciler.py         — Self-healing pipeline monitor + cost tracking
  supermemory.py        — Supermemory client + data sync
  scaling_demo.py       — Fan-out demo for generating Arize traces
  pipelines/
    news.py             — RSS + NewsAPI (30min cron)
    reddit.py           — asyncpraw + JSON fallback (1hr cron)
    public_data.py      — Chicago Data Portal via Socrata (daily cron)
    politics.py         — Legistar + PDF parsing (on-demand)
    demographics.py     — Census/ACS data (on-demand)
    reviews.py          — Yelp + Google Places (on-demand)
    realestate.py       — LoopNet + placeholders (on-demand)
    federal_register.py — SBA/FDA/OSHA/EPA regulations (on-demand)
    tiktok.py           — Playwright + Kernel + Whisper transcription (on-demand)
    traffic.py          — TomTom Traffic Flow API (on-demand)
    cctv.py             — IDOT highway cameras + YOLOv8n detection + GPU metrics (on-demand)
    vision.py           — YouTube → YOLO frame analysis + custom training (on-demand)
    worldpop.py         — Google Earth Engine population data (on-demand)
frontend/               — React 19 + TypeScript + Vite (19 components)
  src/components/
    ProcessFlow.tsx     — Collapsible trace diagram (pipeline stages + copy logs)
    AgentSwarm.tsx      — Agent status indicators
    ChatPanel.tsx       — Streaming chat with inline ProcessFlow + Deep Dive
    DeepDivePanel.tsx   — AI-generated analysis: stats grid, chart, code toggle
    Dashboard.tsx       — Main dashboard (tabs, map, risk, demographics, CCTV)
    MapView.tsx         — Mapbox neighborhood map
    PipelineMonitor.tsx — Live pipeline status polling
    MLMonitor.tsx       — ML model monitoring
    ...                 — RiskCard, InspectionTable, PermitTable, LicenseTable, etc.
backend/                — Local FastAPI proxy for dev
tests/
  conftest.py           — InMemorySpanExporter + span_capture fixture
  test_tracing_spans.py — 20 tests: LLM, agent, classify, web endpoint spans
  test_instrumentation.py — 15 tests: init_tracing, get_tracer, context propagation
test_pipelines.py       — Local test harness: mocks Modal, calls _fetch_* directly
data_sources.md         — Detailed catalog of all data sources
architecture.md         — Full architecture spec
docs/                   — Design docs, setup guide, plans
```

## Key Patterns

- **Document schema** (`common.py`): All pipelines normalize to `Document(id, source, title, content, url, timestamp, metadata, geo, status)`.
- **Ingestion flow**: `_fetch_*()` → `FallbackChain` → `SeenSet` dedup → save to volume → push to `doc_queue` → `classify.py` enriches.
- **Volume paths**: raw at `/data/raw/{source}/{date}/`, enriched at `/data/processed/enriched/`, cache at `/data/cache/`, dedup at `/data/dedup/`.
- **Two APIs**: `web.py` is the production Modal-hosted API. `backend/` is a local dev proxy.
- **Reasoning**: `orchestrate_query()` fans out 4 agents via `.spawn()`, gathers results, synthesizes with LLM.

- **Tracing**: `instrumentation.py` provides `init_tracing()` → Arize register, `get_tracer()`, `inject_context()`/`extract_context()` for W3C trace propagation across Modal containers.
- **Agent trace linking**: `orchestrate_query()` calls `inject_context()` inside its span, passes the dict to child `.spawn()` calls. Children call `extract_context()` to create linked child spans.

## Implementation Status

- **Deployed**: All 13 pipelines, enrichment (classify.py), reasoning (agents.py + llm.py), compression, reconciler, Supermemory, web API, Arize tracing with connected spans.
- **Frontend complete**: Streaming chat, pipeline monitor, agent visualization, ProcessFlow trace diagram with copy-logs, CCTV stat card, demographics card, Deep Dive analysis panel.
- **Not built**: City graph (NetworkX multigraph described in architecture.md — agents read raw/enriched JSON directly). Trend/anomaly detection.

## Secrets (Modal dashboard)

**`alethia-secrets`**: `SUPERMEMORY_API_KEY` (required). Optional: `NEWSAPI_KEY`, `YELP_API_KEY`, `GOOGLE_PLACES_API_KEY`, `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `TOMTOM_API_KEY`, `OPENAI_API_KEY`.

**`arize-secrets`**: `ARIZE_SPACE_ID`, `ARIZE_API_KEY` — for OpenTelemetry trace export to Arize AX dashboard.

Pipelines skip gracefully when keys are missing.

## Commands

```bash
python3 test_pipelines.py          # Local test: runs all _fetch_* functions, prints report
pytest tests/                      # Run tracing + instrumentation tests (35 tests)
modal deploy -m modal_app          # Deploy all functions + activate cron schedules
modal serve -m modal_app           # Dev mode: hot-reload, no cron activation
cd frontend && npm run dev         # Frontend dev server at localhost:5173
```

## Deployment

- **Live API:** `https://ibsrinivas27--alethia-serve.modal.run`
- **Deploy command:** `modal deploy -m modal_app`
- **28+ Modal functions** deployed, **21 Modal features** used
- **5 cron jobs** (news 30min, reddit 1hr, public_data daily, classifier 2min, reconciler 5min)
- **10 on-demand pipelines** (politics, demographics, reviews, realestate, federal_register, tiktok, traffic, cctv, vision, worldpop)
- **4 GPU classes** (AlethiaLLM H100, DocClassifier T4, SentimentAnalyzer T4, TrafficAnalyzer T4)
- **Warm containers** (`min_containers=1`): AlethiaLLM (H100), TrafficAnalyzer (T4), serve (CPU). Classifiers use `scaledown_window` only (incompatible with `@modal.batched`).
- **GPU memory snapshots** enabled on all 4 GPU classes for fast cold starts

## Modal Features Used (21)

`modal.App`, `modal.Volume` (data + weights), `modal.Secret`, `modal.Image` (14 custom), `modal.Period`, `.map()`, `gpu="T4"`, `gpu="H100"`, `@modal.cls` + `@modal.enter(snap=True)`, `@modal.concurrent`, `@modal.batched`, `modal.Queue`, `modal.Retries`, `.spawn()`, `@modal.asgi_app`, `modal.Dict`, `Function.from_name`, `Cls.from_name`, `min_containers`, `enable_memory_snapshot`, `modal.Sandbox`
