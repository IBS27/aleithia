# Alethia Architecture Design

**Date:** 2026-02-27 (updated 2026-02-28)
**Project:** Alethia — Regulatory Intelligence for Small Businesses
**Event:** HackIllinois 2026
**Status:** DEPLOYED — `https://gt12889--alethia-serve.modal.run`
**Scale:** 28+ Modal functions | 13 pipelines | 13 custom images | 18 Modal features | 17 API endpoints

## Goal

Build an AI-powered regulatory intelligence platform that aggregates live Chicago-area data (news, politics, social, public records, reviews, real estate, federal regulations, traffic, CCTV, vision), analyzes it on Modal GPUs (Qwen3 8B on H100, bart-large-mnli + roberta + YOLOv8n on T4), and delivers actionable insights to small business owners through a streaming chat + dashboard interface with OpenTelemetry tracing.

## Prize Strategy

| Category | Prize | Value |
|----------|-------|-------|
| Path | Best Voyager Hack | $5,000 team |
| Opt-in | Best Social Impact | MARSHALL Speakers + charity each |
| Opt-in | Best UI/UX Design | FUJIFILM Camera each |
| Sponsor | Supermemory | Meta RayBans each |
| Sponsor | OpenAI | $5K API credits each |
| Sponsor | Cloudflare | $5K credits each |
| Sponsor (stretch) | Solana | Blockchain verification of data provenance |
| MLH | .Tech Domain | Desktop mic + 10yr domain each |

**Constraints:** 1 path + 2 opt-in + 3 sponsor + unlimited MLH. Solana is stretch goal if time permits.

---

## System Architecture (Deployed)

```
┌─────────────────────── MODAL COMPUTE LAYER ──────────────────────────────┐
│                                                                          │
│  ┌───────────────── DATA PIPELINES (13 pipelines) ────────────────────┐ │
│  │                                                                     │ │
│  │  news_ingester     reddit_ingester    public_data_ingester          │ │
│  │  (30min cron)      (1hr cron)         (daily cron)                  │ │
│  │  - NewsAPI         - asyncpraw        - Socrata API                 │ │
│  │  - RSS feeds       - JSON fallback    - Permits, crime, transit     │ │
│  │                                                                     │ │
│  │  politics_ingester  demographics_ingester  reviews_ingester         │ │
│  │  (on-demand)        (on-demand)            (on-demand)              │ │
│  │  - Legistar API     - Census/ACS API       - Yelp Fusion           │ │
│  │  - PDF parse        - 77 community areas   - Google Places          │ │
│  │                                                                     │ │
│  │  realestate_ingester    federal_register_ingester                   │ │
│  │  (on-demand)            (on-demand)                                 │ │
│  │  - LoopNet              - SBA, FDA, OSHA, EPA                      │ │
│  │                                                                     │ │
│  │  traffic_ingester   cctv_ingester     tiktok (4 functions)         │ │
│  │  (on-demand)        (on-demand)       (on-demand)                   │ │
│  │  - TomTom API       - IDOT ArcGIS     - Kernel + Playwright        │ │
│  │                     - YOLOv8n (T4)    - Whisper transcription       │ │
│  │                                                                     │ │
│  │  vision (5 funcs)   worldpop_ingester                              │ │
│  │  (on-demand)        (on-demand)                                     │ │
│  │  - YouTube → YOLO   - Google Earth Engine                           │ │
│  └──────────────┬──────────────────────────────────────────────────────┘ │
│                 │ await doc_queue.put.aio()                              │
│                 ▼                                                        │
│  ┌──── modal.Queue ("new-docs") ────┐                                   │
│  └──────────────┬───────────────────┘                                   │
│                 │ process_queue_batch (2min cron)                        │
│                 ▼                                                        │
│  ┌───────────────── GPU INFERENCE (4 model classes) ─────────────────┐  │
│  │                                                                    │  │
│  │  DocClassifier (T4)          SentimentAnalyzer (T4)               │  │
│  │  bart-large-mnli (406M)      roberta-sentiment                    │  │
│  │  @modal.batched(32)          @modal.batched(32)                   │  │
│  │  asyncio.gather() parallel   asyncio.gather() parallel            │  │
│  │                                                                    │  │
│  │  AlethiaLLM (H100)           CCTVDetector (T4)                    │  │
│  │  Qwen3 8B via vLLM           YOLOv8n pedestrian/vehicle          │  │
│  │  @modal.concurrent(20)       detection on IDOT camera frames      │  │
│  │  Streaming token generation                                       │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌───────────────── AGENT SWARM (.spawn() fan-out) ──────────────────┐  │
│  │  neighborhood_intel_agent — per-neighborhood analysis              │  │
│  │  regulatory_agent — federal + local regulation scan                │  │
│  │  orchestrate_query — fan out 4 agents, synthesize via LLM         │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌───────────────── INFRASTRUCTURE ──────────────────────────────────┐  │
│  │  data_reconciler (5min cron) — auto-restart stale pipelines       │  │
│  │  modal.Dict ("alethia-costs") — compute cost tracking             │  │
│  │  compress_raw_data — volume optimization                          │  │
│  │  Supermemory sync — RAG context + user profiles                   │  │
│  │  instrumentation.py — Arize AX tracing (OTel connected spans)     │  │
│  │  scaling_demo.py — Modal auto-scaling demonstration               │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌───────────────── STORAGE ─────────────────────────────────────────┐  │
│  │  alethia-data (Volume) — raw docs, enriched docs, summaries, geo  │  │
│  │  alethia-weights (Volume) — Qwen3 8B model weights (16GB)         │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌───────────────── WEB API (@modal.asgi_app) ───────────────────────┐  │
│  │  FastAPI → https://gt12889--alethia-serve.modal.run               │  │
│  │  POST /chat        — agent swarm + streaming SSE                  │  │
│  │  GET  /brief/{n}   — neighborhood intelligence brief              │  │
│  │  GET  /alerts      — regulatory alerts by business type           │  │
│  │  GET  /status      — pipeline monitor (states, GPU, costs)        │  │
│  │  GET  /metrics     — scale numbers (docs, sources, neighborhoods) │  │
│  │  GET  /sources     — per-source freshness                         │  │
│  │  GET  /neighborhood/{n} — neighborhood detail                     │  │
│  │  GET  /health      — healthcheck                                  │  │
│  │  GET  /cctv/latest — latest CCTV detection results                │  │
│  │  GET  /cctv/frame/{id} — camera frame image                      │  │
│  │  + 9 more endpoints (scaling, geo, summaries, etc.)               │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
         │                              │
         │ Search + Retrieve            │ Store user context
         ▼                              ▼
┌──────────────────┐          ┌──────────────────┐
│   Supermemory    │          │  modal.Dict       │
│   - User Profiles│          │  - Cost tracking  │
│   - RAG context  │          │  - Pipeline state  │
│   - Doc sync     │          └──────────────────┘
│   - Conversations│
└──────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────┐
│          FRONTEND (React 19 + TypeScript + Vite)  │
│  ┌──────────┐ ┌──────────────┐ ┌──────────────┐ │
│  │ Onboard  │ │ Chat Panel   │ │ Dashboard    │ │
│  │ (biz     │ │ (streaming   │ │ (live data   │ │
│  │  profile)│ │  SSE tokens) │ │  cards, map) │ │
│  └──────────┘ └──────────────┘ └──────────────┘ │
└──────────────────────────────────────────────────┘
```

## Approach (Updated)

**All-Modal architecture.** No separate backend server — FastAPI runs directly on Modal via `@modal.asgi_app()`. All compute (pipelines, GPU inference, web serving, agent orchestration) runs on Modal. Supermemory for user context and RAG. Frontend is a standalone SPA.

**Key change from original plan:** Replaced "Llama 3.1 8B on A10G" with "Qwen3 8B on H100" for better throughput. Replaced "OpenAI for chat generation" with self-hosted LLM on Modal (more impressive for judges, no external API dependency for chat).

## Data Sources

| Source | API/Method | Cadence | Modal Function | Live Docs |
|--------|-----------|---------|---------------|-----------|
| Local News | NewsAPI + RSS feeds | 30 min (cron) | `news_ingester` | 30 |
| City Council | Chicago Legistar API + PDF parse | On-demand | `politics_ingester` | 80 |
| Reddit | asyncpraw + JSON fallback | 1 hr (cron) | `reddit_ingester` | — (needs keys) |
| Yelp/Google | Yelp Fusion + Google Places | On-demand | `review_ingester` | — (needs keys) |
| City Data Portal | Socrata API | Daily (cron) | `public_data_ingester` | 459 |
| Census/ACS | Census API | On-demand | `demographics_ingester` | 1,332 |
| Real Estate | LoopNet + placeholders | On-demand | `realestate_ingester` | 8 |
| Federal Register | Federal Register API | On-demand | `federal_register_ingester` | — |
| TikTok | Kernel cloud browser + Whisper | On-demand | `tiktok` (4 functions) | — |
| Traffic | TomTom Traffic Flow API | On-demand | `traffic_ingester` | — |
| CCTV | IDOT ArcGIS + YOLOv8n | On-demand | `cctv_ingester` + `CCTVDetector` | — |
| Vision | YouTube → GPT-4V → YOLO | On-demand | `vision` (5 functions) | — |
| WorldPop | Google Earth Engine | On-demand | `worldpop_ingester` | — |

**Total live:** 1,889+ documents across 47 neighborhoods (13 pipelines)

## Processing Pipeline (Deployed)

Every ingested document goes through:

1. **Raw storage** → Modal Volume `/raw/{source}/{date}/{id}.json`
2. **Queue push** → `await doc_queue.put.aio(doc_data)` to `modal.Queue`
3. **GPU classification** → `DocClassifier` (bart-large-mnli) categorizes into 6 labels
4. **GPU sentiment** → `SentimentAnalyzer` (roberta) scores positive/negative/neutral
5. **Enriched storage** → Modal Volume `/processed/enriched/{id}.json`
6. **Compression** → Summaries + GeoJSON in `/processed/summaries/` and `/processed/geo/`

## AI Inference (Modal) — Deployed

Three GPU models running on Modal:

- **DocClassifier** (`facebook/bart-large-mnli`, 406M params, T4): Zero-shot classification into regulatory/economic/safety/infrastructure/community/business. Batch size 32 via `@modal.batched`.
- **SentimentAnalyzer** (`cardiffnlp/twitter-roberta-base-sentiment-latest`, T4): Sentiment scoring. Batch size 32 via `@modal.batched`.
- **AlethiaLLM** (Qwen3 8B via vLLM, H100): Streaming chat responses, intelligence briefs, agent synthesis. 20 concurrent inputs via `@modal.concurrent`.
- **CCTVDetector** (YOLOv8n, T4): Pedestrian and vehicle detection on IDOT highway camera snapshots. Foot traffic density classification (high/medium/low).

## Supermemory Integration

| Supermemory API | Use in Alethia |
|-----------------|---------------|
| **User Profiles** | Business type, location (neighborhood), industry, size, regulatory concerns |
| **Memory** | Past queries, analysis results, recommendations per user |
| **Retrieval** | Augment RAG — pull user-relevant context alongside Modal volume data |
| **Doc Sync** | Pipeline data pushed to Supermemory for searchable RAG context |

**Flow:** User onboards → profile in Supermemory → every query enriched with profile + memory → agent swarm retrieves from Supermemory + volume → LLM synthesizes → recommendations personalize over time.

## Modal Features Used (18)

| # | Feature | Where Used |
|---|---------|------------|
| 1 | `modal.App` | `volume.py` — single app for all functions |
| 2 | `modal.Volume` | `volume.py` — `alethia-data` + `alethia-weights` |
| 3 | `modal.Secret` | All pipeline + web functions |
| 4 | `modal.Image` | `volume.py` — 13 custom images (base, reddit, politics, data, vllm, classify, web, video, label, yolo, cctv, traffic, tiktok) |
| 5 | `modal.Period` | 5 cron schedules (news, reddit, public_data, classifier, reconciler) |
| 6 | `.map()` | Batch fan-out in pipelines |
| 7 | `gpu="T4"` | `classify.py` (DocClassifier + SentimentAnalyzer), `cctv.py` (CCTVDetector) |
| 8 | `@modal.cls` + `@modal.enter` | `llm.py`, `classify.py`, `cctv.py` — model loading |
| 9 | `@modal.concurrent` | `llm.py` — 20 concurrent LLM inputs |
| 10 | `gpu="H100"` | `llm.py` — Qwen3 8B via vLLM |
| 11 | `Image.pip_install()` | All custom images |
| 12 | `@modal.batched` | `classify.py` — batch GPU inference (32 docs) |
| 13 | `modal.Queue` | `classify.py` — event bus between pipelines and classifier |
| 14 | `modal.Retries` | `politics.py`, `federal_register.py` — auto-retry on failure |
| 15 | `.spawn()` | `agents.py` — query-time fan-out of 4 agents |
| 16 | `@modal.asgi_app` | `web.py` — FastAPI hosted on Modal |
| 17 | `modal.Dict` | `reconciler.py` — shared cost tracking state |
| 18 | `Function.from_name` / `Cls.from_name` | `web.py` — cross-module function lookups |

## Deployment (Actual)

| Component | Platform | Status |
|-----------|----------|--------|
| All compute | Modal (28+ functions) | **DEPLOYED** |
| Web API | Modal `@modal.asgi_app` | **LIVE** at `https://gt12889--alethia-serve.modal.run` (17 endpoints) |
| LLM | Modal H100 (Qwen3 8B) | **DEPLOYED** |
| Classification | Modal T4 (2 models) | **DEPLOYED** |
| CCTV Detection | Modal T4 (YOLOv8n) | **DEPLOYED** |
| Tracing | Arize AX (OTel) | **DEPLOYED** |
| User Memory | Supermemory | **DEPLOYED** |
| Frontend | Local dev (Vite) | **RUNNING** (18 React components) |
| Domain | TBD | Not yet configured |

## Key Technical Decisions (Updated)

| Decision | Rationale |
|----------|-----------|
| All-Modal over separate backend | Single platform = simpler deployment, more Modal features for judges |
| Qwen3 8B over Llama 3.1 8B | Better instruction following, fits H100 well |
| H100 over A10G | Higher throughput for streaming, impressive for judges |
| Self-hosted LLM over OpenAI | No external dependency for chat, more ambitious for Modal track |
| `asyncio.gather()` over sequential | Parallel GPU calls — 100 docs in ~10s instead of ~250s |
| 5 cron + 5 on-demand | Modal free tier limits to 5 cron jobs |
| `MODAL_IS_REMOTE` guard | Prevents cross-image import failures in containers |
| `add_local_python_source(copy=True)` | Ensures source is baked into image, not mounted |
| `scaledown_window` over `container_idle_timeout` | API renamed in Modal SDK |

---

## Plan vs Reality — Key Diffs

Changes discovered during implementation that diverged from the original design.

### 1. GPU specification syntax (deprecated object → string)
```diff
- gpu=modal.gpu.H100(),
+ gpu="H100",
```

### 2. Container idle timeout renamed
```diff
- container_idle_timeout=300,
+ scaledown_window=300,
```

### 3. flash-attn removed from vLLM image
```diff
  vllm_image = (
      modal.Image.debian_slim(python_version="3.11")
      .pip_install("vllm>=0.8.0", "transformers>=4.45.0", "torch>=2.4.0")
-     .run_commands("pip install flash-attn --no-build-isolation")
+     # flash-attn removed: requires CUDA dev tools not in debian_slim
+     # vLLM includes its own optimized attention kernels
  )
```

### 4. `add_local_python_source` requires `copy=True`
```diff
- .add_local_python_source("modal_app")
+ .add_local_python_source("modal_app", copy=True)
```
Without `copy=True`, containers couldn't find the `modal_app` package at runtime.

### 5. `__init__.py` guarded with `MODAL_IS_REMOTE`
```diff
+ if not _os.environ.get("MODAL_IS_REMOTE"):
+     from modal_app import compress  # noqa: F401
+     from modal_app import classify  # noqa: F401
+     ...
```
Without this guard, every container tried to import ALL modules (including fastapi, vllm, etc.), causing `ModuleNotFoundError` in images that don't have those packages.

### 6. Cron schedules reduced from 10 to 5 (Modal free tier limit)
```diff
  # Kept (5 cron jobs):
  news_ingester:          schedule=modal.Period(minutes=30)
  reddit_ingester:        schedule=modal.Period(hours=1)
  public_data_ingester:   schedule=modal.Period(days=1)
  process_queue_batch:    schedule=modal.Period(minutes=2)
  data_reconciler:        schedule=modal.Period(minutes=5)

  # Removed schedules (run on-demand via reconciler):
- politics_ingester:      schedule=modal.Period(days=1)
- demographics_ingester:  schedule=modal.Period(days=30)
- review_ingester:        schedule=modal.Period(days=1)
- realestate_ingester:    schedule=modal.Period(days=7)
- federal_register:       schedule=modal.Period(days=1)
```

### 7. `allow_concurrent_inputs` removed from ASGI app
```diff
  @app.function(image=web_image, volumes={"/data": volume},
      secrets=[modal.Secret.from_name("alethia-secrets")],
-     allow_concurrent_inputs=100,
  )
  @modal.asgi_app()
  def serve():
```
Deprecated for ASGI apps — Modal handles concurrency automatically.

### 8. Queue drain + classification: blocking → async parallel
```diff
  # Queue drain
- doc = doc_queue.get(timeout=5)
+ doc = await doc_queue.get.aio(timeout=5)

  # Classification: sequential blocking → parallel async
- for text in texts:
-     classifications.append(classifier.classify.remote(text))
-     sentiments.append(analyzer.analyze.remote(text))
+ classifications = await asyncio.gather(
+     *[classifier.classify.remote.aio(text) for text in texts],
+     return_exceptions=True,
+ )
+ sentiments = await asyncio.gather(
+     *[analyzer.analyze.remote.aio(text) for text in texts],
+     return_exceptions=True,
+ )
```
Sequential blocking caused 300s timeout on 100 docs. Parallel async completes in ~10s.

### 9. Pipeline queue push: blocking → async
```diff
  # In news.py, reddit.py, public_data.py, politics.py:
- doc_queue.put(doc_data)
+ await doc_queue.put.aio(doc_data)
```

### 10. Data sources expanded from 8 to 13 pipelines
```diff
  # Original 8 pipelines:
  news, reddit, public_data, politics, demographics, reviews, realestate, federal_register

+ # Added 5 pipelines:
+ traffic_ingester    — TomTom Traffic Flow API congestion data
+ cctv_ingester       — IDOT ArcGIS camera snapshots + YOLOv8n detection (T4)
+ tiktok (4 functions) — Kernel cloud browser + Playwright + Whisper transcription
+ vision (5 functions) — YouTube → GPT-4V labeling → YOLOv8n training → inference
+ worldpop_ingester   — Google Earth Engine population demographics
```

### 11. GPU models expanded from 3 to 4
```diff
  DocClassifier (T4)      — bart-large-mnli zero-shot classification
  SentimentAnalyzer (T4)  — roberta sentiment analysis
  AlethiaLLM (H100)       — Qwen3 8B via vLLM streaming
+ CCTVDetector (T4)       — YOLOv8n pedestrian/vehicle detection on IDOT frames
```

### 12. Modal images expanded from 10 to 13
```diff
  Existing: base, reddit, politics, data, vllm, classify, web, video, label, yolo
+ Added:    cctv_image, traffic_image, tiktok_image
```

### 13. Arize AX tracing added (not in original plan)
```diff
+ instrumentation.py — init_tracing(), get_tracer(), inject_context(), extract_context()
+ W3C trace context propagation across Modal containers
+ arize-secrets Modal secret group (ARIZE_SPACE_ID, ARIZE_API_KEY)
+ Connected spans: web.py → agents.py → llm.py
+ 35 automated tests in tests/test_tracing_spans.py + tests/test_instrumentation.py
```

### 14. API endpoints expanded from 8 to 17
```diff
  Original 8: /health, /metrics, /sources, /status, /chat, /brief/{n}, /alerts, /neighborhood/{n}
+ Added: /cctv/latest, /cctv/frame/{id}, /scaling, /geo/{layer},
+        /neighborhood/{n}/summary, /docs, /openapi.json, /compare, /trends
```

### 15. Frontend built (not detailed in original architecture)
```diff
+ 18 React components with Tailwind CSS v4
+ ProcessFlow.tsx — collapsible trace visualization with copy-logs
+ Streaming SSE chat via api.ts event parser
+ PipelineMonitor.tsx + MLMonitor.tsx for ops dashboard
```

### 16. Reconciler spawn + cost dict: blocking → async (from original diff #10)
```diff
- news_ingester.spawn()
+ await news_ingester.spawn.aio()

- for key in cost_dict.keys():
-     entry = cost_dict[key]
+ async for key in cost_dict.keys.aio():
+     entry = await cost_dict.get.aio(key)
```
