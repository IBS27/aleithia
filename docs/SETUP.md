# Alethia Setup Guide

## Prerequisites

- Python 3.11+
- [Modal CLI](https://modal.com/docs/guide) (`pip install modal`)
- Modal account with credits (redeem code: `VVN-YQS-E55` at modal.com/credits)

## 1. Modal Authentication

```bash
modal token set --token-id <your-id> --token-secret <your-secret>
```

## 2. Create Modal Secrets

All API keys are stored as a single Modal secret group:

```bash
modal secret create alethia-secrets \
  NEWSAPI_KEY=your_key \
  REDDIT_CLIENT_ID=your_id \
  REDDIT_CLIENT_SECRET=your_secret \
  YELP_API_KEY=your_key \
  GOOGLE_PLACES_API_KEY=your_key \
  SOCRATA_APP_TOKEN=your_token \
  CENSUS_API_KEY=your_key \
  SUPERMEMORY_API_KEY=your_key \
  OPENAI_API_KEY=your_key \
  TOMTOM_API_KEY=your_key

# Arize tracing (separate secret group)
modal secret create arize-secrets \
  ARIZE_SPACE_ID=your_space_id \
  ARIZE_API_KEY=your_api_key
```

Create TikTok scraper secrets separately (used by `modal_app/pipelines/tiktok.py`):

```bash
modal secret create tiktok-scraper-secrets \
  KERNEL_API_KEY=your_kernel_key \
  TIKTOK_COOKIE_HEADER='sessionid=...; sid_tt=...'
```

`TIKTOK_COOKIE_HEADER` is optional but recommended when TikTok serves an auth gate on search pages.

**Note:** Most pipelines work without API keys (using public endpoints or fallback data), but keys improve rate limits and data quality. Arize secrets are optional — tracing is disabled gracefully without them.

## 3. API Key Sources

| Key | Where to get it | Required? |
|-----|----------------|-----------|
| `NEWSAPI_KEY` | [newsapi.org](https://newsapi.org) | Optional — RSS feeds work without it |
| `REDDIT_CLIENT_ID` / `SECRET` | [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps/) | Optional — improves reliability; otherwise RSS fallback is used |
| `YELP_API_KEY` | [yelp.com/developers](https://www.yelp.com/developers) | Optional |
| `GOOGLE_PLACES_API_KEY` | [Google Cloud Console](https://console.cloud.google.com/) | Optional |
| `SOCRATA_APP_TOKEN` | [data.cityofchicago.org](https://data.cityofchicago.org/profile/edit/developer_settings) | Optional — public access works |
| `CENSUS_API_KEY` | [census.gov/developers](https://api.census.gov/data/key_signup.html) | Optional — works without key |
| `SUPERMEMORY_API_KEY` | [supermemory.ai](https://supermemory.ai) | Optional — for RAG + user profiles |
| `TOMTOM_API_KEY` | [developer.tomtom.com](https://developer.tomtom.com) | Optional — traffic monitoring; free tier available |
| `ARIZE_SPACE_ID` | [arize.com](https://app.arize.com) | Optional — OTel tracing dashboard |
| `ARIZE_API_KEY` | [arize.com](https://app.arize.com) | Optional — OTel tracing dashboard |

## 4. Deploy Everything

```bash
# Deploy all 28+ functions at once (recommended)
modal deploy -m modal_app

# This deploys:
# - 5 cron jobs: news (30min), reddit (1hr), public_data (daily),
#                process_queue_batch (2min), data_reconciler (5min)
# - 10 on-demand pipelines: politics, demographics, reviews, realestate,
#                            federal_register, tiktok, traffic, cctv, vision, worldpop
# - GPU inference: AlethiaLLM (H100), DocClassifier (T4), SentimentAnalyzer (T4), CCTVDetector (T4)
# - Agent swarm: neighborhood_intel_agent, regulatory_agent, orchestrate_query
# - Web API: https://ibsrinivas27--alethia-serve.modal.run (17 endpoints)
# - Utilities: compress, supermemory sync, model download, scaling_demo
# - Tracing: Arize AX via OpenTelemetry (if arize-secrets configured)
```

## 5. Run Individual Pipelines

```bash
# Test individual pipelines
modal run -m modal_app.pipelines.news::news_ingester
modal run -m modal_app.pipelines.politics::politics_ingester
modal run -m modal_app.pipelines.reddit::reddit_ingester
modal run -m modal_app.pipelines.reviews::review_ingester
modal run -m modal_app.pipelines.public_data::public_data_ingester
modal run -m modal_app.pipelines.demographics::demographics_ingester
modal run -m modal_app.pipelines.realestate::realestate_ingester
modal run -m modal_app.pipelines.federal_register::federal_register_ingester
modal run -m modal_app.pipelines.traffic::traffic_ingester
modal run -m modal_app.pipelines.cctv::cctv_ingester
modal run -m modal_app.pipelines.vision::extract_frames
modal run -m modal_app.pipelines.worldpop::ingest_worldpop

# Run data compression
modal run -m modal_app.compress::compress_raw_data

# Run GPU classifier manually
modal run -m modal_app.classify::process_queue_batch
```

## 6. Verify Deployment

```bash
# Check API health
curl https://ibsrinivas27--alethia-serve.modal.run/health

# Check metrics (doc counts, sources, neighborhoods)
curl https://ibsrinivas27--alethia-serve.modal.run/metrics

# Check pipeline status (freshness, GPU status, costs)
curl https://ibsrinivas27--alethia-serve.modal.run/status

# Check data sources
curl https://ibsrinivas27--alethia-serve.modal.run/sources

# Check volume contents
modal volume ls alethia-data /raw/
modal volume ls alethia-data /processed/
```

## 7. Verify Data

```bash
# Check raw data per source
modal volume ls alethia-data /raw/news/
modal volume ls alethia-data /raw/public_data/
modal volume ls alethia-data /raw/politics/
modal volume ls alethia-data /raw/demographics/

# Check enriched (classified) documents
modal volume ls alethia-data /processed/enriched/

# Check compressed summaries
modal volume ls alethia-data /processed/summaries/

# Check GeoJSON output
modal volume ls alethia-data /processed/geo/
```

## 8. Local Frontend Development

```bash
cd frontend
npm install
npm run dev
# Runs at http://localhost:5173
# Point API calls to: https://ibsrinivas27--alethia-serve.modal.run
```

## Architecture Overview

```
                    Modal Compute Layer (28+ functions)
┌──────────────────────────────────────────────────────────┐
│                                                          │
│  DATA PIPELINES (13)           GPU INFERENCE              │
│  ├─ news (30min cron)          ├─ Qwen3 8B (H100)        │
│  ├─ reddit (1hr cron)          ├─ DocClassifier (T4)      │
│  ├─ public_data (daily)        ├─ SentimentAnalyzer (T4)  │
│  ├─ politics (on-demand)       └─ CCTVDetector (T4)       │
│  ├─ demographics (on-demand)                              │
│  ├─ reviews (on-demand)        AGENT SWARM                │
│  ├─ realestate (on-demand)     ├─ neighborhood_intel      │
│  ├─ federal_register           ├─ regulatory_agent        │
│  ├─ tiktok (on-demand)         └─ orchestrate_query       │
│  ├─ traffic (on-demand)                                   │
│  ├─ cctv (on-demand)           OBSERVABILITY              │
│  ├─ vision (on-demand)         └─ Arize AX (OTel spans)   │
│  └─ worldpop (on-demand)                                  │
│                                                          │
│  INFRASTRUCTURE                WEB API                    │
│  ├─ modal.Queue (event bus)    └─ FastAPI @asgi_app       │
│  ├─ modal.Dict (cost track)       17 endpoints live       │
│  ├─ reconciler (5min cron)                                │
│  └─ Supermemory sync                                      │
│                                                          │
│  STORAGE                                                  │
│  ├─ alethia-data (Volume)                                 │
│  └─ alethia-weights (Volume, model weights)               │
└──────────────────────────────────────────────────────────┘
```
