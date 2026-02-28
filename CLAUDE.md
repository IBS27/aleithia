# Alethia — Chicago Business Intelligence Platform

An AI-powered regulatory intelligence platform that aggregates live Chicago-area data (news, politics, social, public records, reviews, real estate, federal regulations), analyzes it on Modal GPUs (Qwen3 8B on H100, bart-large-mnli + roberta on T4), and delivers actionable insights to small business owners through a streaming chat + dashboard interface.

## Tech Stack

- **Frontend:** React 19 + TypeScript + Vite
- **Backend:** Modal-hosted FastAPI via `@modal.asgi_app()` (no separate backend server)
- **LLM:** Qwen3 8B self-hosted via vLLM on H100
- **Classification:** bart-large-mnli (zero-shot) + roberta (sentiment) on T4 GPUs
- **Compute:** Modal (18 serverless functions — pipelines, GPU inference, web API, reconciler)
- **Memory:** Supermemory (RAG context, user profiles, doc sync)
- **Data:** 10 pipelines ingesting 1,889+ documents across 47 Chicago neighborhoods

## Architecture

1. **Ingestion layer** — 10 Modal cron/on-demand functions scrape/poll heterogeneous sources (RSS, Chicago Data Portal, Reddit, Yelp/Google, Legistar, Federal Register, LoopNet, Census, TikTok) and normalize into a common `Document` schema. See `data_sources.md` for full catalog.
2. **Event bus** — `modal.Queue` connects pipelines to GPU classifiers. Pipelines push via `await doc_queue.put.aio()`.
3. **Enrichment layer** — `DocClassifier` (bart-large-mnli) + `SentimentAnalyzer` (roberta) on T4 GPUs classify documents into categories (regulatory, economic, safety, etc.) with sentiment scores. Batch processing via `@modal.batched` + `asyncio.gather()`.
4. **LLM layer** — Qwen3 8B via vLLM on H100 for streaming chat responses and intelligence briefs. 20 concurrent inputs via `@modal.concurrent`.
5. **Agent swarm** — 4 agent types (neighborhood intel, regulatory, comparison, synthesis) fan out via `.spawn()` for query-time parallel intelligence gathering.
6. **Self-healing** — Reconciler runs every 5 min, checks pipeline freshness, auto-restarts stale ingesters. Cost tracking via `modal.Dict`.
7. **Web API** — Modal-hosted FastAPI with 8 endpoints: `/chat`, `/brief/{neighborhood}`, `/alerts`, `/status`, `/metrics`, `/sources`, `/neighborhood/{name}`, `/health`.

## Project Structure

```
modal_app/              — Modal functions (all compute runs here)
  __init__.py           — Function discovery (guarded by MODAL_IS_REMOTE)
  volume.py             — App, volumes, 10 custom images (THE entrypoint: `modal deploy modal_app/volume.py`)
  common.py             — Document schema, SourceType enum, CHICAGO_NEIGHBORHOODS, detect_neighborhood()
  fallback.py           — FallbackChain pattern for resilient data fetching
  dedup.py              — SeenSet: persistent JSON-backed dedup (10k cap per source)
  compress.py           — Raw data compression → neighborhood summaries + GeoJSON for Mapbox
  llm.py                — AlethiaLLM class (Qwen3 8B on H100 via vLLM)
  classify.py           — DocClassifier + SentimentAnalyzer on T4, Queue drain every 2min
  agents.py             — Agent swarm (neighborhood, regulatory, orchestrator)
  web.py                — FastAPI web app served via @modal.asgi_app()
  reconciler.py         — Self-healing pipeline monitor + cost tracking
  supermemory.py        — Supermemory client + data sync
  pipelines/
    news.py             — RSS + NewsAPI (30min cron)
    reddit.py           — asyncpraw + JSON fallback (1hr cron)
    public_data.py      — Chicago Data Portal via Socrata (daily cron)
    politics.py         — Legistar + PDF parsing (on-demand)
    demographics.py     — Census/ACS data (on-demand)
    reviews.py          — Yelp + Google Places (on-demand)
    realestate.py       — LoopNet + placeholders (on-demand)
    federal_register.py — SBA/FDA/OSHA/EPA regulations (on-demand)
    tiktok.py           — Playwright + Kernel + Whisper transcription (daily)
    vision.py           — YouTube → YOLO frame analysis (on-demand)
frontend/               — React 19 + TypeScript + Vite
backend/                — Local FastAPI proxy for dev (submits/polls Modal jobs, serves pre-downloaded data)
test_pipelines.py       — Local test harness: mocks Modal, calls _fetch_* directly, prints report
tiktok_scraper/         — TikTok scraper package (CLI, config, analysis)
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

## Implementation Status

- **Done**: Ingestion (all 10 pipelines), enrichment (classify.py), reasoning (agents.py + llm.py), compression, reconciler, Supermemory integration, both APIs.
- **Not deployed**: Main `alethia` app needs `modal deploy modal_app/volume.py` to activate cron schedules.
- **Not built**: City graph (NetworkX multigraph described in architecture.md — agents currently read raw/enriched JSON directly). Trend/anomaly detection.

## Secrets (Modal dashboard → `alethia-secrets`)

Required: `SUPERMEMORY_API_KEY`. Optional: `NEWSAPI_KEY`, `YELP_API_KEY`, `GOOGLE_PLACES_API_KEY`, `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`. Pipelines skip gracefully when keys are missing.

## Commands

```bash
python3 test_pipelines.py          # Local test: runs all _fetch_* functions, prints report
modal deploy modal_app/volume.py   # Deploy app + activate all cron schedules
modal serve modal_app/volume.py    # Dev mode: hot-reload, no cron activation
```

## Deployment

- **Live API:** `https://ibsrinivas27--alethia-serve.modal.run`
- **Deploy command:** `modal deploy -m modal_app`
- **18 Modal functions** deployed, **17 Modal features** used
- **5 cron jobs** (news 30min, reddit 1hr, public_data daily, classifier 2min, reconciler 5min)
- **5 on-demand pipelines** (politics, demographics, reviews, realestate, federal_register)

## Modal Features Used (17)

`modal.App`, `modal.Volume` (data + weights), `modal.Secret`, `modal.Image` (10 custom), `modal.Period`, `.map()`, `gpu="T4"`, `@modal.cls` + `@modal.enter`, `@modal.concurrent`, `gpu="H100"`, `@modal.batched`, `modal.Queue`, `modal.Retries`, `.spawn()`, `@modal.asgi_app`, `modal.Dict`
