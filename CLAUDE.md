# Alethia — Chicago Business Intelligence Platform

An AI-powered regulatory intelligence platform that aggregates live Chicago-area data (news, politics, social, public records, reviews, real estate, federal regulations, traffic, IDOT highway cameras, CTA ridership, satellite parking), analyzes it on Modal GPUs (Qwen3 8B on H100, GPT-4o hybrid layer, bart-large-mnli + roberta on T4, YOLOv8n on T4, SegFormer + YOLOv8m on T4, Whisper on A10G), and delivers actionable insights to small business owners through a dashboard interface with 44 interactive components.

## Tech Stack

- **Frontend:** React 19 + TypeScript + Vite + Tailwind CSS v4 + Framer Motion (44 components)
- **Backend:** Modal-hosted FastAPI via `@modal.asgi_app()` (43 endpoints, no separate backend server)
- **LLM:** Qwen3 8B AWQ (INT4) self-hosted via vLLM on H100 + GPT-4o hybrid layer (code generation, follow-up suggestions, regulatory enrichment, vision assessment)
- **Classification:** bart-large-mnli (zero-shot) + roberta (sentiment) on T4 GPUs
- **Vision:** YOLOv8n (vehicle detection on IDOT highway cameras) on T4 GPUs
- **Parking:** SegFormer-b5 (semantic segmentation) + YOLOv8m + SAHI (satellite parking lot detection) on T4 GPUs
- **Transcription:** Whisper (TikTok audio transcription) on A10G GPU
- **Vector Search:** Actian VectorAI DB (local HNSW vector search via gRPC) + all-MiniLM-L6-v2 embeddings (384d)
- **Impact Analysis:** Recursive Lead Analyst + E2B sandbox workers for proactive intelligence
- **Risk Scoring:** WLC (Weighted Linear Combination) with logistic normalization, ISO 31000-aligned MCDA
- **Compute:** Modal (47 serverless functions — 41 functions + 6 GPU/CPU classes)
- **Memory:** Supermemory (cloud RAG context, user profiles, doc sync) + VectorAI DB (local semantic search)
- **Tracing:** Arize AX via OpenTelemetry (connected spans across Modal containers, auto-instrumented OpenAI calls)
- **Auth:** Clerk (React SDK — sign-in, sign-up, user profiles)
- **Data:** 14 pipelines ingesting 1,889+ documents across 47 Chicago neighborhoods

## Architecture

1. **Ingestion layer** — 14 Modal cron/on-demand functions scrape/poll heterogeneous sources (RSS, Chicago Data Portal, Reddit, Yelp/Google, Legistar, Federal Register, LoopNet, Census, TikTok, TomTom traffic, IDOT CCTV, YouTube, WorldPop, Mapbox satellite) and normalize into a common `Document` schema. See `data_sources.md` for full catalog.
2. **Event bus** — `modal.Queue` connects pipelines to GPU classifiers. Pipelines push via `await doc_queue.put.aio()`.
3. **Enrichment layer** — `DocClassifier` (bart-large-mnli) + `SentimentAnalyzer` (roberta) on T4 GPUs classify documents into categories (regulatory, economic, safety, etc.) with sentiment scores. Batch processing via `@modal.batched` + `asyncio.gather()`. After enrichment, documents are embedded with all-MiniLM-L6-v2 and upserted to VectorAI DB for semantic retrieval.
4. **LLM layer** — Qwen3 8B AWQ (INT4) via vLLM on H100 for streaming chat responses and intelligence briefs. 20 concurrent inputs via `@modal.concurrent`. GPU memory snapshots for fast cold starts.
5. **Agent swarm** — 4 agent types (neighborhood intel, regulatory, comparison, synthesis) fan out via `.spawn()` for query-time parallel intelligence gathering. Agents query VectorAI DB for fast semantic retrieval (with fallback to JSON file scan) + Supermemory in parallel. Query embedding computed once and shared across all agent spawns. W3C trace context propagation links spans across containers. Regulatory agent enriches regulations with GPT-4o impact summaries when available.
6. **Self-healing** — Reconciler runs every 5 min, checks pipeline freshness, auto-restarts stale ingesters. Cost tracking via `modal.Dict`.
7. **Vision layer** — CCTV pipeline ingests IDOT highway camera frames, YOLOv8n detects vehicles for highway traffic density scoring (not street-level foot traffic). Vision pipeline trains custom detectors from YouTube walking tours and persists per-neighborhood analysis results to `/data/processed/vision/analysis/`. Walk-in potential is sourced from CTA L-station ridership data instead. Parking pipeline analyzes Mapbox satellite tiles via SegFormer-b5 (lot segmentation) + YOLOv8m + SAHI (vehicle detection) for parking occupancy estimation.
8. **Observability** — Arize AX tracing with OpenTelemetry. Connected spans across web → orchestrator → agents → LLM. OpenAI auto-instrumentor for all OpenAI calls (GPT-4o hybrid layer + GPT-4V vision labeling).
9. **Web API** — Modal-hosted FastAPI with 43 endpoints. Core routes: `/chat`, `/neighborhood/{name}`, `/brief/{neighborhood}`, `/analyze`, `/impact-briefs`, `/geo`, `/graph`, `/gpu-metrics`, plus per-source data endpoints (`/news`, `/politics`, `/inspections`, `/permits`, `/licenses`, `/reddit`, `/reviews`, `/realestate`, `/tiktok`, `/traffic`), vision endpoints (`/cctv/*`, `/vision/*`, `/parking/*`), and system endpoints (`/status`, `/metrics`, `/health`). Full list in Endpoints section below.
10. **Deep Dive** — `/analyze` endpoint generates Python analysis scripts via GPT-4o (with Qwen3-8B fallback), runs them in `modal.Sandbox` against real pipeline data. Returns stats, charts (base64 PNG), generated code, and `model_used` indicator.
11. **OpenAI hybrid layer** — `openai_utils.py` provides shared client factory. GPT-4o is used for 4 targeted enhancements: (a) Deep Dive code generation, (b) chat follow-up suggestions, (c) regulatory impact summaries, (d) vision-powered street assessment. All features gracefully degrade without `OPENAI_API_KEY`.
12. **Recursive Agent Architecture** — `lead_analyst.py` monitors enriched docs via `impact_queue`, scores them for business impact (rule-based fast filter + Qwen3-8B LLM scoring), dispatches 4 specialized workers (real_estate, legal, economic, community_sentiment) into E2B cloud sandboxes for deep cross-domain analysis, synthesizes findings into `ImpactBrief` documents saved to `/data/processed/impact_briefs/`. Runs every 5 min. Manual trigger via `analyze_impact()`. Degrades gracefully without E2B or OpenAI keys.
13. **Risk scoring** — Client-side WLC (Weighted Linear Combination) with logistic sigmoid normalization, ISO 31000-aligned. Six MCDA dimensions weighted for commercial site selection: regulatory (0.25), market (0.20), economic (0.20), accessibility (0.15), political (0.10), community (0.10). All displayed factors contribute to the actual 0–10 score.
14. **Interactive data** — All documents, records, and data items are clickable. Items with source URLs open in a new tab; items without URLs expand to show details or navigate to the relevant dashboard tab.

## Project Structure

```
modal_app/                — Modal functions (all compute runs here)
  __init__.py             — Function discovery (25 module imports, guarded by MODAL_IS_REMOTE)
  volume.py               — App, 2 volumes, 17 custom images (THE entrypoint: `modal deploy -m modal_app`)
  common.py               — Document schema, SourceType enum, CHICAGO_NEIGHBORHOODS (47), detect_neighborhood()
  openai_utils.py         — Shared OpenAI client factory: openai_available(), get_openai_client(), get_sync_openai_client()
  e2b_utils.py            — Shared E2B sandbox factory: e2b_available(), create_sandbox()
  instrumentation.py      — Arize AX tracing: init_tracing(), get_tracer(), inject/extract_context()
  fallback.py             — FallbackChain pattern for resilient data fetching
  dedup.py                — SeenSet: persistent JSON-backed dedup (10k cap per source)
  compress.py             — Raw data compression → neighborhood summaries + GeoJSON for Mapbox
  llm.py                  — AlethiaLLM class (Qwen3 8B AWQ on H100 via vLLM, @modal.concurrent(20), GPU metrics)
  classify.py             — DocClassifier + SentimentAnalyzer on T4 (@modal.batched), Queue drain every 2min
  agents.py               — Agent swarm (neighborhood, regulatory + GPT-4o enrichment, comparison, synthesis, orchestrator) with W3C trace propagation
  web.py                  — FastAPI web app via @modal.asgi_app() (43 endpoints)
  lead_analyst.py         — Recursive agent: impact scoring, E2B worker dispatch, synthesis (5-min cron + manual trigger)
  vectordb.py             — VectorAI DB service: embed (MiniLM-L6-v2), upsert, search, health check, backfill + vectordb_available() guard
  graph.py                — City knowledge graph construction (NetworkX multigraph)
  reconciler.py           — Self-healing pipeline monitor (5-min cron) + cost tracking via modal.Dict
  supermemory.py          — Supermemory client + data sync
  scaling_demo.py         — Fan-out demo for generating Arize traces
  pipelines/
    news.py               — RSS + NewsAPI (30min cron)
    reddit.py             — asyncpraw + JSON fallback (1hr cron)
    public_data.py        — Chicago Data Portal via Socrata (daily cron)
    politics.py           — Legistar + PDF parsing (on-demand)
    demographics.py       — Census/ACS data (on-demand)
    reviews.py            — Yelp + Google Places (on-demand)
    realestate.py         — LoopNet + placeholders (on-demand)
    federal_register.py   — SBA/FDA/OSHA/EPA regulations (on-demand)
    tiktok.py             — Playwright + Kernel + Whisper transcription on A10G (on-demand)
    traffic.py            — TomTom Traffic Flow API (on-demand)
    cctv.py               — IDOT highway cameras + YOLOv8n vehicle detection on T4 + GPU metrics (on-demand)
    vision.py             — YouTube → YOLO frame analysis on T4 + custom training + per-neighborhood persistence (on-demand)
    parking.py            — Mapbox satellite tiles → SegFormer-b5 + YOLOv8m + SAHI on T4 (on-demand)
    worldpop.py           — Google Earth Engine population data (on-demand)
frontend/                 — React 19 + TypeScript + Vite (44 components)
  src/
    api.ts                — API client: fetch wrappers, SSE streaming, type-safe endpoints
    insights.ts           — computeInsights(): 6-category WLS scoring with risk profiles
    types/index.ts        — 20+ TypeScript interfaces (Document, InspectionRecord, PermitRecord, LicenseRecord, CCTVCamera, ParkingData, etc.)
    components/
      Dashboard.tsx       — Main dashboard hub (8 tabs, WLC risk scoring, Clerk auth, tab routing, data loading)
      LoadingFlow.tsx     — Pipeline flow animation during initial data load (7-stage animated diagram)
      LandingPage.tsx     — Public landing page with hero, features, onboarding CTA
      OnboardingForm.tsx  — Business type + neighborhood selection onboarding
      ProfilePage.tsx     — User profile management (Clerk-integrated)
      Drawer.tsx          — Reusable slide-out drawer component
      MapView.tsx         — Mapbox GL neighborhood map with GeoJSON overlay
      RiskCard.tsx        — Animated risk score display (framer-motion gradients, expanding factors)
      DemographicsCard.tsx — Census data grid with animated score bars (framer-motion)
      InsightsCard.tsx    — 6-category risk insights with expandable evidence + clickable source links
      LocationReportPanel.tsx — Intelligence brief sidebar + "Investment Committee" PDF export (9 sections, html2canvas)
      ChatPanel.tsx       — Streaming chat with inline ProcessFlow + Deep Dive + follow-up suggestion chips
      DeepDivePanel.tsx   — AI-generated analysis: stats grid, base64 chart, code toggle
      ProcessFlow.tsx     — Collapsible trace diagram (pipeline stages + copy logs)
      AgentSwarm.tsx      — Agent status indicators and swarm visualization
      RecursiveAgentPanel.tsx — Autonomous Systems monitor (pipeline freshness, GPU fleet, agent deployment log, Agent Spawning Agent tree, impact briefs)
      NewsFeed.tsx        — News + City Council items (clickable cards → source URLs)
      CommunityFeed.tsx   — Reddit + TikTok posts (clickable cards → source URLs)
      MarketPanel.tsx     — Business reviews + commercial listings (clickable cards → Yelp/LoopNet URLs)
      InspectionTable.tsx — Food inspection records (clickable → Chicago Data Portal, expandable violations)
      PermitTable.tsx     — Building permits (clickable → source records)
      LicenseTable.tsx    — Business license table (clickable rows → source records)
      FootTrafficChart.tsx — CTA transit ridership time series
      TrafficCard.tsx     — Highway traffic density stats
      CCTVCameraCard.tsx  — Individual CCTV camera HUD with detection counts
      CCTVCameraDrawer.tsx — Detailed CCTV camera inspection drawer
      CCTVFeedCard.tsx    — Live CCTV frame display with fallback
      StreetscapeCard.tsx — Vision pipeline streetscape intelligence + GPT-4o AI assessment button
      CityGraph.tsx       — Knowledge graph visualization (force-directed, vis-network)
      CityGlobe.tsx       — 3D globe visualization of Chicago
      MemGraph.tsx        — Memory graph entity/relationship viewer
      MemoryGraphPage.tsx — Full-page memory graph (Supermemory)
      VaultCharts.tsx     — Recharts analytics (InspectionOutcomesChart, TopViolationsPareto, AlertHoursStackedArea)
      PipelineMonitor.tsx — Live pipeline status polling with freshness indicators
      MLMonitor.tsx       — ML model monitoring and metrics display
      DataSourceBadge.tsx — Source attribution badge
      Timer.tsx           — Elapsed time counter
      ShinyText.tsx       — Text shimmer/shine effect (CSS gradient animation)
      BlurText.tsx        — Text blur reveal animation
      Squares.tsx         — Geometric squares background animation
      LogoLoop.tsx        — Animated logo carousel
      SponsorLogos.tsx    — Sponsor logo grid
      HowItWorks.tsx      — Feature explainer section
      WhyUs.tsx           — Value proposition section
backend/                  — Local FastAPI proxy for dev
tests/
  conftest.py             — InMemorySpanExporter + span_capture fixture
  test_tracing_spans.py   — 20 tests: LLM, agent, classify, web endpoint spans
  test_instrumentation.py — 15 tests: init_tracing, get_tracer, context propagation
test_pipelines.py         — Local test harness: mocks Modal, calls _fetch_* directly
data_sources.md           — Detailed catalog of all 14 data sources
architecture.md           — Full architecture spec
docs/                     — Design docs, setup guide, plans
```

## API Endpoints (43 total)

### Chat & Intelligence
| Method | Path | Description |
|--------|------|-------------|
| POST | `/chat` | Streaming chat with GPT-4o follow-up suggestions |
| POST | `/analyze` | Deep Dive: GPT-4o code gen → modal.Sandbox execution → stats/charts |
| GET | `/brief/{neighborhood}` | Investment committee intelligence brief |
| GET | `/alerts` | Risk alerts (negative sentiment > 0.8) |

### Neighborhoods & Aggregated Data
| Method | Path | Description |
|--------|------|-------------|
| GET | `/neighborhood/{name}` | Full neighborhood data (metrics, demographics, permits, licenses, cctv, transit, parking) |
| GET | `/trends/{neighborhood}` | Trend analysis and time series with anomaly detection |
| GET | `/geo` | GeoJSON for all neighborhoods with metrics |
| GET | `/summary` | City-wide summary across all neighborhoods |

### Per-Source Data (all clickable in frontend)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/news` | News articles by neighborhood/business |
| GET | `/politics` | City Council legislative items |
| GET | `/inspections` | Food inspection records (filterable by result) |
| GET | `/permits` | Building permits |
| GET | `/licenses` | Business licenses |
| GET | `/reddit` | Reddit discussions |
| GET | `/reviews` | Yelp + Google Places reviews |
| GET | `/realestate` | Commercial real estate listings |
| GET | `/tiktok` | TikTok content by neighborhood/business |
| GET | `/traffic` | TomTom traffic flow data |
| GET | `/sources` | Data source status (count + active flag) |

### CCTV & Vision
| Method | Path | Description |
|--------|------|-------------|
| GET | `/cctv/latest` | Latest vehicle/pedestrian detections across cameras |
| GET | `/cctv/frame/{camera_id}` | Individual camera frame (JPEG proxy) |
| GET | `/cctv/timeseries/{neighborhood}` | Hourly traffic patterns by camera |
| GET | `/vision/streetscape/{neighborhood}` | Streetscape analysis counts (storefronts, dining, vacancy) |
| GET | `/vision/assess/{neighborhood}` | GPT-4o vision-powered street assessment |

### Satellite Parking
| Method | Path | Description |
|--------|------|-------------|
| GET | `/parking/latest` | All neighborhood parking summaries |
| GET | `/parking/{neighborhood}` | Detailed parking lot detection data |
| GET | `/parking/annotated/{neighborhood}` | Annotated satellite images (JPEG) |

### Knowledge Graph
| Method | Path | Description |
|--------|------|-------------|
| GET | `/graph` | Supermemory document/memory graph |
| GET | `/graph/full` | Full city knowledge graph (NetworkX JSON) |
| GET | `/graph/neighborhood/{name}` | Neighborhood-scoped subgraph |
| GET | `/graph/stats` | Graph statistics |

### Impact Briefs (Recursive Agent)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/impact-briefs` | List recent briefs (params: `limit`, `min_score`) |
| GET | `/impact-briefs/{brief_id}` | Single brief detail |
| POST | `/impact-briefs/analyze` | Manual trigger for specific doc |

### User & System
| Method | Path | Description |
|--------|------|-------------|
| GET | `/user/memories` | User conversation memory (Supermemory) |
| GET | `/user/settings` | User preferences |
| PUT | `/user/settings` | Update user settings |
| GET | `/status` | System health (pipelines, caches, uptime) |
| GET | `/metrics` | Performance metrics (API latency, queue depth) |
| GET | `/gpu-metrics` | GPU utilization across H100/T4s |
| GET | `/health` | Health check |
| POST | `/demo/scale` | Scaling demo for Arize traces |

## Key Patterns

- **Document schema** (`common.py`): All pipelines normalize to `Document(id, source, title, content, url, timestamp, metadata, geo, status)`.
- **Ingestion flow**: `_fetch_*()` → `FallbackChain` → `SeenSet` dedup → save to volume → push to `doc_queue` → `classify.py` enriches.
- **Volume paths**: raw at `/data/raw/{source}/{date}/`, enriched at `/data/processed/enriched/`, cache at `/data/cache/`, dedup at `/data/dedup/`, vision analysis at `/data/processed/vision/analysis/`, parking analysis at `/data/processed/parking/analysis/`, parking annotated images at `/data/processed/parking/annotated/`, impact briefs at `/data/processed/impact_briefs/`, vectordb at `/data/vectordb/`.
- **OpenAI hybrid**: `openai_utils.py` provides `openai_available()` guard + `get_openai_client()` factory. All GPT-4o features check availability and fall back gracefully.
- **VectorAI DB**: `vectordb.py` provides `vectordb_available()` guard + `VectorDBService` Modal class. Agents query VectorAI DB for semantic retrieval, falling back to JSON file scan if unavailable. Enrichment pipeline upserts to VectorDB after classification. `backfill_vectordb()` for one-time indexing of existing data.
- **Two APIs**: `web.py` is the production Modal-hosted API. `backend/` is a local dev proxy.
- **Reasoning**: `orchestrate_query()` fans out 4 agents via `.spawn()`, gathers results, synthesizes with LLM.
- **Tracing**: `instrumentation.py` provides `init_tracing()` → Arize register, `get_tracer()`, `inject_context()`/`extract_context()` for W3C trace propagation across Modal containers.
- **Agent trace linking**: `orchestrate_query()` calls `inject_context()` inside its span, passes the dict to child `.spawn()` calls. Children call `extract_context()` to create linked child spans.
- **Risk scoring** (`Dashboard.tsx:computeRiskScore`): Multi-Criteria Risk Assessment using Weighted Linear Combination (WLC), ISO 31000-aligned. Each input is normalized to [0,1] via logistic (sigmoid) functions with Chicago-calibrated midpoints (e.g. 22% inspection fail rate = 0.5 risk). Six MCDA dimensions weighted for commercial site selection: regulatory (0.25), market (0.20), economic (0.20), accessibility (0.15), political (0.10), community (0.10). Score = `Σ(wᵢ·rᵢ)/Σ(wᵢ)` scaled to 0–10. Confidence = 60% dimensional coverage + 40% data depth (saturates at 50 data points). All displayed factors contribute to the score.
- **Insights scoring** (`insights.ts:computeInsights`): Computes 6 category scores (regulatory, economic, market, demographic, safety/accessibility, community) from NeighborhoodData + streetscape vision data. Each category averages its sub-metrics (0–100 scale). Overall = WLS composite with profile-dependent weights: conservative (regulatory+safety heavy), growth (economic+market heavy), budget (demographic+community heavy). Signal thresholds: ≥65 FAVORABLE, 40–65 MODERATE, <40 CONCERNING.
- **Clickable data**: All document/record components (NewsFeed, CommunityFeed, MarketPanel, InspectionTable, PermitTable, LicenseTable, InsightsCard) render items as clickable cards/rows. Items with `url` fields open source in new tab; items without URLs expand details or navigate to relevant dashboard tab.

## Implementation Status

- **Deployed**: All 14 pipelines (incl. parking), enrichment (classify.py), reasoning (agents.py + llm.py), OpenAI hybrid layer (openai_utils.py), recursive agent architecture (lead_analyst.py + e2b_utils.py), VectorAI DB (vectordb.py — local semantic search), compression, reconciler, Supermemory, web API (43 endpoints), Arize tracing with connected spans.
- **Frontend complete**: 44 React components including: animated loading flow, streaming chat with follow-up chips, pipeline monitor with freshness indicators, agent visualization, ProcessFlow trace diagram with copy-logs, highway traffic stat card, CTA transit scoring, animated demographics card (framer-motion), animated risk card (framer-motion) with WLC scoring, Deep Dive analysis panel (GPT-4o enhanced), professional "Investment Committee" PDF export (9-section proposal format), streetscape intelligence with GPT-4o AI assessment, satellite parking detection display, recursive agent panel (autonomous systems, GPU fleet, agent spawning tree, impact briefs), knowledge graph + memory graph visualization, Vault analytics charts (recharts), clickable data throughout.
- **Not built**: Trend/anomaly detection (endpoint exists, frontend display pending).

## Secrets (Modal dashboard)

**`alethia-secrets`**: `SUPERMEMORY_API_KEY` (required). Optional: `NEWSAPI_KEY`, `YELP_API_KEY`, `GOOGLE_PLACES_API_KEY`, `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `TOMTOM_API_KEY`, `OPENAI_API_KEY` (enables GPT-4o hybrid: better Deep Dive, follow-up suggestions, regulatory enrichment, vision assessment), `MAPBOX_TOKEN` (satellite parking pipeline), `E2B_API_KEY` (enables E2B cloud sandbox execution for Lead Analyst workers; falls back to in-process exec without it).

**`arize-secrets`**: `ARIZE_SPACE_ID`, `ARIZE_API_KEY` — for OpenTelemetry trace export to Arize AX dashboard.

**`tiktok-scraper-secrets`**: TikTok authentication secrets for Playwright browser automation.

Pipelines skip gracefully when keys are missing.

## Commands

```bash
python3 test_pipelines.py          # Local test: runs all _fetch_* functions, prints report
pytest tests/                      # Run tracing + instrumentation tests (35 tests)
modal deploy -m modal_app          # Deploy all functions + activate cron schedules
modal serve -m modal_app           # Dev mode: hot-reload, no cron activation
cd frontend && npm run dev         # Frontend dev server at localhost:5173
cd frontend && npx vite build      # Production build
cd frontend && npx tsc --noEmit    # TypeScript type check
```

## Deployment

- **Live API:** `https://ibsrinivas27--alethia-serve.modal.run`
- **Deploy command:** `modal deploy -m modal_app`
- **47 Modal functions** deployed (41 `@app.function` + 6 `@app.cls`)
- **43 API endpoints** on FastAPI
- **44 frontend components** (React 19 + TypeScript)
- **6 cron jobs** (news 30min, reddit 1hr, public_data daily, classifier 2min, reconciler 5min, lead_analyst 5min)
- **11 on-demand pipelines** (politics, demographics, reviews, realestate, federal_register, tiktok, traffic, cctv, vision, parking, worldpop)
- **8 GPU-equipped functions** (1× H100, 6× T4, 1× A10G)
- **18 custom Docker images** (17 in volume.py + 1 ee_image in worldpop.py)
- **3 secret groups** (alethia-secrets, arize-secrets, tiktok-scraper-secrets)
- **2 persistent volumes** (alethia-data, alethia-weights)
- **Warm containers** (`min_containers=1`): AlethiaLLM (H100), TrafficAnalyzer (T4), VectorDBService (CPU), serve (CPU). Classifiers use `scaledown_window=120` only (incompatible with `@modal.batched`).
- **GPU memory snapshots** enabled on all GPU classes for fast cold starts (`enable_memory_snapshot=True` + `experimental_options={"enable_gpu_snapshot": True}`)

## GPU Fleet (8 functions across 3 GPU types)

| Class | GPU | File | Task | Config |
|-------|-----|------|------|--------|
| AlethiaLLM | H100 | llm.py | Qwen3 8B AWQ via vLLM | `@modal.concurrent(20)`, `min_containers=1`, memory snapshot |
| DocClassifier | T4 | classify.py | bart-large-mnli zero-shot | `@modal.batched`, `scaledown_window=120`, memory snapshot |
| SentimentAnalyzer | T4 | classify.py | roberta sentiment | `@modal.batched`, `scaledown_window=120`, memory snapshot |
| TrafficAnalyzer | T4 | cctv.py | YOLOv8n vehicle detection | `min_containers=1`, memory snapshot |
| ParkingAnalyzer | T4 | parking.py | SegFormer-b5 + YOLOv8m + SAHI | Memory snapshot |
| analyze_neighborhood | T4 | vision.py | YOLOv8 frame analysis | Per-invocation |
| train_detector | T4 | vision.py | YOLOv8 custom training | Per-invocation |
| transcribe | A10G | tiktok.py | Whisper audio transcription | Per-invocation |

## Modal Features Used (21)

`modal.App`, `modal.Volume` (data + weights), `modal.Secret` (3 groups), `modal.Image` (18 custom), `modal.Period` (6 schedules), `.map()`, `gpu="T4"` / `gpu="H100"` / `gpu="A10G"`, `@modal.cls` + `@modal.enter(snap=True)`, `@modal.concurrent`, `@modal.batched`, `modal.Queue` (doc_queue + impact_queue), `modal.Retries`, `.spawn()`, `@modal.asgi_app`, `modal.Dict`, `Function.from_name`, `Cls.from_name`, `min_containers`, `enable_memory_snapshot`, `scaledown_window`, `modal.Sandbox`

## Custom Docker Images (18)

| Image | Base | Key Packages | Used By |
|-------|------|-------------|---------|
| `base_image` | Python 3.11 slim | httpx, pydantic, feedparser, openai, arize | Most functions |
| `reddit_image` | base | asyncpraw | Reddit pipeline |
| `politics_image` | base | pymupdf, pdfplumber | Politics pipeline |
| `data_image` | base | pandas | Data processing |
| `graph_image` | base | networkx, pandas | Knowledge graph |
| `vllm_image` | Python 3.11 slim | vLLM, transformers, torch | AlethiaLLM (H100) |
| `classify_image` | Python 3.11 slim | transformers, torch | DocClassifier, SentimentAnalyzer (T4) |
| `web_image` | base | fastapi, uvicorn | Web API |
| `sandbox_image` | Python 3.11 slim | pandas, matplotlib, numpy, seaborn | Deep Dive sandbox |
| `lead_analyst_image` | base | e2b-code-interpreter | Lead Analyst + E2B workers |
| `video_image` | Python 3.11 slim | ffmpeg, yt-dlp | Video download |
| `label_image` | Python 3.11 slim | openai, pillow | Vision labeling (GPT-4V) |
| `yolo_image` | Python 3.11 slim | ultralytics, opencv, httpx | YOLOv8 detection (T4) |
| `parking_image` | Python 3.11 slim | transformers, torch, ultralytics, sahi, opencv, pillow | ParkingAnalyzer (T4) |
| `vectordb_image` | williamimoh/actian-vectorai-db:1.0b | actiancortex, sentence-transformers, torch | VectorDBService |
| `tiktok_image` | Python 3.12 slim | playwright, kernel | TikTok browser automation |
| `transcribe_image` | Python 3.12 slim | yt-dlp, openai-whisper, torch | Whisper transcription (A10G) |
| `ee_image` | Python 3.11 slim | earthengine-api | WorldPop / Earth Engine |
