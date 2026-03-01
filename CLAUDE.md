# Alethia — Chicago Business Intelligence Platform

An AI-powered regulatory intelligence platform that aggregates live Chicago-area data (news, politics, social, public records, reviews, real estate, federal regulations, traffic, IDOT highway cameras, CTA ridership, satellite parking), analyzes it on Modal GPUs (Qwen3 8B on H100, GPT-4o hybrid layer, bart-large-mnli + roberta on T4, YOLOv8n on T4, SegFormer + YOLOv8m on T4), and delivers actionable insights to small business owners through a streaming chat + dashboard interface.

## Tech Stack

- **Frontend:** React 19 + TypeScript + Vite + Tailwind CSS v4
- **Backend:** Modal-hosted FastAPI via `@modal.asgi_app()` (no separate backend server)
- **LLM:** Qwen3 8B AWQ (INT4) self-hosted via vLLM on H100 + GPT-4o hybrid layer (code generation, follow-up suggestions, regulatory enrichment, vision assessment)
- **Classification:** bart-large-mnli (zero-shot) + roberta (sentiment) on T4 GPUs
- **Vision:** YOLOv8n (pedestrian/vehicle detection) on T4 GPUs
- **Parking:** SegFormer-b5 (semantic segmentation) + YOLOv8m + SAHI (satellite parking lot detection) on T4 GPUs
- **Impact Analysis:** Recursive Lead Analyst + E2B sandbox workers for proactive intelligence
- **Compute:** Modal (33+ serverless functions — pipelines, GPU inference, web API, agents, lead analyst, reconciler)
- **Memory:** Supermemory (RAG context, user profiles, doc sync)
- **Tracing:** Arize AX via OpenTelemetry (connected spans across Modal containers, auto-instrumented OpenAI calls)
- **Data:** 14 pipelines ingesting 1,889+ documents across 47 Chicago neighborhoods

## Architecture

1. **Ingestion layer** — 14 Modal cron/on-demand functions scrape/poll heterogeneous sources (RSS, Chicago Data Portal, Reddit, Yelp/Google, Legistar, Federal Register, LoopNet, Census, TikTok, TomTom traffic, IDOT CCTV, YouTube, WorldPop, Mapbox satellite) and normalize into a common `Document` schema. See `data_sources.md` for full catalog.
2. **Event bus** — `modal.Queue` connects pipelines to GPU classifiers. Pipelines push via `await doc_queue.put.aio()`.
3. **Enrichment layer** — `DocClassifier` (bart-large-mnli) + `SentimentAnalyzer` (roberta) on T4 GPUs classify documents into categories (regulatory, economic, safety, etc.) with sentiment scores. Batch processing via `@modal.batched` + `asyncio.gather()`.
4. **LLM layer** — Qwen3 8B AWQ (INT4) via vLLM on H100 for streaming chat responses and intelligence briefs. 20 concurrent inputs via `@modal.concurrent`. GPU memory snapshots for fast cold starts.
5. **Agent swarm** — 4 agent types (neighborhood intel, regulatory, comparison, synthesis) fan out via `.spawn()` for query-time parallel intelligence gathering. W3C trace context propagation links spans across containers. Regulatory agent enriches regulations with GPT-4o impact summaries when available.
6. **Self-healing** — Reconciler runs every 5 min, checks pipeline freshness, auto-restarts stale ingesters. Cost tracking via `modal.Dict`.
7. **Vision layer** — CCTV pipeline ingests IDOT highway camera frames, YOLOv8n detects vehicles for highway traffic density scoring (not street-level foot traffic). Vision pipeline trains custom detectors from YouTube walking tours and persists per-neighborhood analysis results to `/data/processed/vision/analysis/`. Walk-in potential is sourced from CTA L-station ridership data instead. Parking pipeline analyzes Mapbox satellite tiles via SegFormer-b5 (lot segmentation) + YOLOv8m + SAHI (vehicle detection) for parking occupancy estimation.
8. **Observability** — Arize AX tracing with OpenTelemetry. Connected spans across web → orchestrator → agents → LLM. OpenAI auto-instrumentor for all OpenAI calls (GPT-4o hybrid layer + GPT-4V vision labeling).
9. **Web API** — Modal-hosted FastAPI with 25+ endpoints including `/chat` (with GPT-4o follow-up suggestions), `/brief/{neighborhood}`, `/neighborhood/{name}` (includes `transit` + `parking` fields), `/analyze`, `/cctv/latest`, `/cctv/frame/{camera_id}`, `/vision/streetscape/{neighborhood}`, `/vision/assess/{neighborhood}` (GPT-4o vision assessment), `/parking/latest`, `/parking/{neighborhood}`, `/parking/annotated/{neighborhood}`, `/impact-briefs`, `/impact-briefs/{brief_id}`, `/impact-briefs/analyze`, `/gpu-metrics`, `/status`, `/metrics`, `/health`.
10. **Deep Dive** — `/analyze` endpoint generates Python analysis scripts via GPT-4o (with Qwen3-8B fallback), runs them in `modal.Sandbox` against real pipeline data. Returns stats, charts (base64 PNG), generated code, and `model_used` indicator.
11. **OpenAI hybrid layer** — `openai_utils.py` provides shared client factory. GPT-4o is used for 4 targeted enhancements: (a) Deep Dive code generation, (b) chat follow-up suggestions, (c) regulatory impact summaries, (d) vision-powered street assessment. All features gracefully degrade without `OPENAI_API_KEY`.
12. **Recursive Agent Architecture** — `lead_analyst.py` monitors enriched docs via `impact_queue`, scores them for business impact (rule-based fast filter + Qwen3-8B LLM scoring), dispatches 4 specialized workers (real_estate, legal, economic, community_sentiment) into E2B cloud sandboxes for deep cross-domain analysis, synthesizes findings into `ImpactBrief` documents saved to `/data/processed/impact_briefs/`. Runs every 5 min. Manual trigger via `analyze_impact()`. Degrades gracefully without E2B or OpenAI keys.

## Project Structure

```
modal_app/              — Modal functions (all compute runs here)
  __init__.py           — Function discovery (21 module imports, guarded by MODAL_IS_REMOTE)
  volume.py             — App, volumes, 15 custom images (THE entrypoint: `modal deploy -m modal_app`)
  common.py             — Document schema, SourceType enum, CHICAGO_NEIGHBORHOODS, detect_neighborhood()
  openai_utils.py       — Shared OpenAI client factory: openai_available(), get_openai_client(), get_sync_openai_client()
  instrumentation.py    — Arize AX tracing: init_tracing(), get_tracer(), inject/extract_context()
  fallback.py           — FallbackChain pattern for resilient data fetching
  dedup.py              — SeenSet: persistent JSON-backed dedup (10k cap per source)
  compress.py           — Raw data compression → neighborhood summaries + GeoJSON for Mapbox
  llm.py                — AlethiaLLM class (Qwen3 8B AWQ on H100 via vLLM, GPU metrics)
  classify.py           — DocClassifier + SentimentAnalyzer on T4, Queue drain every 2min
  agents.py             — Agent swarm (neighborhood, regulatory + GPT-4o enrichment, orchestrator) with trace context propagation
  web.py                — FastAPI web app served via @modal.asgi_app() (22+ endpoints, incl. /analyze, /vision/assess, /parking/*)
  lead_analyst.py       — Recursive agent: impact scoring, E2B worker dispatch, synthesis (5-min cron + manual trigger)
  e2b_utils.py          — Shared E2B sandbox factory: e2b_available(), create_sandbox()
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
    cctv.py             — IDOT highway cameras + YOLOv8n vehicle detection + GPU metrics (on-demand)
    vision.py           — YouTube → YOLO frame analysis + custom training + per-neighborhood persistence (on-demand)
    parking.py          — Mapbox satellite tiles → SegFormer-b5 + YOLOv8m + SAHI parking detection (on-demand)
    worldpop.py         — Google Earth Engine population data (on-demand)
frontend/               — React 19 + TypeScript + Vite (21 components)
  src/components/
    ProcessFlow.tsx     — Collapsible trace diagram (pipeline stages + copy logs)
    AgentSwarm.tsx      — Agent status indicators
    ChatPanel.tsx       — Streaming chat with inline ProcessFlow + Deep Dive + follow-up suggestion chips
    DeepDivePanel.tsx   — AI-generated analysis: stats grid, chart, code toggle
    Dashboard.tsx       — Main dashboard (tabs, map, WLC risk scoring, demographics, highway traffic, parking)
    MapView.tsx         — Mapbox neighborhood map
    PipelineMonitor.tsx — Live pipeline status polling
    MLMonitor.tsx       — ML model monitoring
    LocationReportPanel.tsx — Intelligence brief sidebar + professional "Investment Committee" PDF export (9 sections)
    StreetscapeCard.tsx — Vision pipeline streetscape intelligence + GPT-4o AI assessment button
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
- **Volume paths**: raw at `/data/raw/{source}/{date}/`, enriched at `/data/processed/enriched/`, cache at `/data/cache/`, dedup at `/data/dedup/`, vision analysis at `/data/processed/vision/analysis/`, parking analysis at `/data/processed/parking/analysis/`, parking annotated images at `/data/processed/parking/annotated/`, impact briefs at `/data/processed/impact_briefs/`.
- **OpenAI hybrid**: `openai_utils.py` provides `openai_available()` guard + `get_openai_client()` factory. All GPT-4o features check availability and fall back gracefully.
- **Two APIs**: `web.py` is the production Modal-hosted API. `backend/` is a local dev proxy.
- **Reasoning**: `orchestrate_query()` fans out 4 agents via `.spawn()`, gathers results, synthesizes with LLM.

- **Tracing**: `instrumentation.py` provides `init_tracing()` → Arize register, `get_tracer()`, `inject_context()`/`extract_context()` for W3C trace propagation across Modal containers.
- **Agent trace linking**: `orchestrate_query()` calls `inject_context()` inside its span, passes the dict to child `.spawn()` calls. Children call `extract_context()` to create linked child spans.
- **Risk scoring** (`Dashboard.tsx:computeRiskScore`): Multi-Criteria Risk Assessment using Weighted Linear Combination (WLC), ISO 31000-aligned. Each input is normalized to [0,1] via logistic (sigmoid) functions with Chicago-calibrated midpoints (e.g. 22% inspection fail rate = 0.5 risk). Six MCDA dimensions weighted for commercial site selection: regulatory (0.25), market (0.20), economic (0.20), accessibility (0.15), political (0.10), community (0.10). Score = `Σ(wᵢ·rᵢ)/Σ(wᵢ)` scaled to 0–10. Confidence = 60% dimensional coverage + 40% data depth (saturates at 50 data points). All displayed factors contribute to the score.
- **Insights scoring** (`insights.ts:computeInsights`): Computes 6 category scores (regulatory, economic, market, demographic, safety/accessibility, community) from NeighborhoodData + streetscape vision data. Each category averages its sub-metrics (0–100 scale). Overall = WLS composite with profile-dependent weights: conservative (regulatory+safety heavy), growth (economic+market heavy), budget (demographic+community heavy). Signal thresholds: ≥65 FAVORABLE, 40–65 MODERATE, <40 CONCERNING.

## Implementation Status

- **Deployed**: All 14 pipelines (incl. parking), enrichment (classify.py), reasoning (agents.py + llm.py), OpenAI hybrid layer (openai_utils.py), recursive agent architecture (lead_analyst.py + e2b_utils.py), compression, reconciler, Supermemory, web API, Arize tracing with connected spans.
- **Frontend complete**: Streaming chat (with follow-up suggestion chips), pipeline monitor, agent visualization, ProcessFlow trace diagram with copy-logs, highway traffic stat card, CTA transit scoring, demographics card, Deep Dive analysis panel (GPT-4o enhanced), professional "Investment Committee" PDF export (9-section proposal format), streetscape intelligence with GPT-4o AI assessment, satellite parking detection display.
- **Not built**: City graph (NetworkX multigraph described in architecture.md — agents read raw/enriched JSON directly). Trend/anomaly detection.

## Secrets (Modal dashboard)

**`alethia-secrets`**: `SUPERMEMORY_API_KEY` (required). Optional: `NEWSAPI_KEY`, `YELP_API_KEY`, `GOOGLE_PLACES_API_KEY`, `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `TOMTOM_API_KEY`, `OPENAI_API_KEY` (enables GPT-4o hybrid: better Deep Dive, follow-up suggestions, regulatory enrichment, vision assessment), `MAPBOX_TOKEN` (satellite parking pipeline), `E2B_API_KEY` (enables E2B cloud sandbox execution for Lead Analyst workers; falls back to in-process exec without it).

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
- **33+ Modal functions** deployed, **21 Modal features** used
- **6 cron jobs** (news 30min, reddit 1hr, public_data daily, classifier 2min, reconciler 5min, lead_analyst 5min)
- **11 on-demand pipelines** (politics, demographics, reviews, realestate, federal_register, tiktok, traffic, cctv, vision, parking, worldpop)
- **5 GPU classes** (AlethiaLLM H100, DocClassifier T4, SentimentAnalyzer T4, TrafficAnalyzer T4, ParkingAnalyzer T4)
- **Warm containers** (`min_containers=1`): AlethiaLLM (H100), TrafficAnalyzer (T4), serve (CPU). Classifiers use `scaledown_window` only (incompatible with `@modal.batched`).
- **GPU memory snapshots** enabled on all 5 GPU classes for fast cold starts

## Modal Features Used (21)

`modal.App`, `modal.Volume` (data + weights), `modal.Secret`, `modal.Image` (15 custom), `modal.Period`, `.map()`, `gpu="T4"`, `gpu="H100"`, `@modal.cls` + `@modal.enter(snap=True)`, `@modal.concurrent`, `@modal.batched`, `modal.Queue`, `modal.Retries`, `.spawn()`, `@modal.asgi_app`, `modal.Dict`, `Function.from_name`, `Cls.from_name`, `min_containers`, `enable_memory_snapshot`, `modal.Sandbox`
