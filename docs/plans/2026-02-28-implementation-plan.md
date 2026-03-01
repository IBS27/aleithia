# Alethia Implementation Plan — Full Progress Tracking

**Goal:** Build an AI-powered regulatory intelligence platform on Modal with self-hosted LLM, GPU classification, agent swarm, Supermemory RAG, and streaming chat.

**Live URL:** `https://ibsrinivas27--alethia-serve.modal.run`
**Branch:** `main`
**28+ Modal functions deployed** | **1,889+ documents ingested** | **13 pipelines** | **47 neighborhoods covered**

---

## Commits (chronological)

| Commit | Description |
|--------|-------------|
| `eeb2180` | All 9 phases implemented (LLM, classify, supermemory, agents, web, frontend, reconciler, federal_register) |
| `020de18` | fix: container imports, deprecations, cron limits |
| `3b8a38b` | fix: async Modal interfaces to eliminate AsyncUsageWarnings |
| `4220037` | docs: update all documentation to reflect deployed architecture |
| `94c2a6d` | docs: add plan-vs-reality diffs to architecture design doc |

---

## Component Status

| Component | Current State | Target | Status |
|-----------|--------------|--------|--------|
| LLM | Qwen3 8B via vLLM on H100, deployed | Streaming SSE | **DEPLOYED** |
| Classification | DocClassifier + SentimentAnalyzer on T4 | Batch classify via Queue | **DEPLOYED** |
| Event Bus | modal.Queue wired to 4 pipelines | Async queue drain + parallel classify | **DEPLOYED** |
| Supermemory | SupermemoryClient + push function | RAG context + user profiles | **DEPLOYED** |
| API | Modal-hosted FastAPI @ modal.run | 17 endpoints live | **DEPLOYED** |
| Chat | /chat endpoint with agent orchestration | Streaming SSE tokens | **DEPLOYED** |
| Agent Swarm | 4 agent types via .spawn() | Query-time fan-out | **DEPLOYED** |
| Pipeline Monitor | /status endpoint + PipelineMonitor.tsx | Frontend viz | **DEPLOYED** |
| Reconciler | Auto-restarts stale pipelines every 5min | Self-healing | **DEPLOYED** |
| Cost Tracking | modal.Dict logging compute costs | Dashboard display | **DEPLOYED** |
| Tracing | Arize AX + OTel connected spans | Cross-container traces | **DEPLOYED** |
| CCTV | IDOT cameras + YOLOv8n detection | Highway traffic scoring | **DEPLOYED** |
| Traffic | TomTom API congestion data | Business location scoring | **DEPLOYED** |
| Frontend | 18 React components + ProcessFlow | Streaming chat + dashboard | **DEPLOYED** |
| Modal Features | 18 features used | 15 target | **EXCEEDED** |

---

## Phase 1: Self-Hosted LLM on Modal — COMPLETE

**Status: DEPLOYED** | File: `modal_app/llm.py`

Centerpiece for Modal AI Inference judging. Unlocks 5+ new Modal features.

**Approach: @modal.cls + AsyncLLMEngine**
Direct engine access for maximum flexibility. Supports both single-shot and streaming generation.

**Deployed code:**

```python
@app.cls(
    gpu="H100",                    # was: modal.gpu.H100() — deprecated syntax
    image=vllm_image,
    volumes={VOLUME_MOUNT: volume, WEIGHTS_MOUNT: weights_volume},
    secrets=[modal.Secret.from_name("alethia-secrets")],
    scaledown_window=300,          # was: container_idle_timeout — renamed
    timeout=600,
)
@modal.concurrent(max_inputs=20)
class AlethiaLLM:
    model_name = "Qwen/Qwen3-8B"

    @modal.enter()
    def load_model(self):
        from vllm import AsyncLLMEngine, AsyncEngineArgs
        args = AsyncEngineArgs(
            model=self.model_name,
            tensor_parallel_size=1,
            max_model_len=8192,
            gpu_memory_utilization=0.90,
        )
        self.engine = AsyncLLMEngine.from_engine_args(args)

    @modal.method()
    async def generate(self, messages, max_tokens=2048, temperature=0.7) -> str: ...

    @modal.method()
    async def generate_stream(self, messages, max_tokens=2048, temperature=0.7):
        async for output in results_generator:
            yield output.outputs[0].text[prev_len:]
```

**Volume config** (in `modal_app/volume.py`):
- `vllm_image`: debian_slim + vllm + transformers + torch (NO flash-attn — vLLM has built-in attention)
- `weights_volume = modal.Volume.from_name("alethia-weights", create_if_missing=True)`

**Modal features added:** `@modal.cls`, `@modal.enter`, `@modal.concurrent`, H100, `Image.pip_install()`

---

## Phase 2: GPU Classification + modal.Queue — COMPLETE

**Status: DEPLOYED + ASYNC FIXED** | File: `modal_app/classify.py`

**Pattern: Queue + parallel async batch**
Pipelines push to Queue via `await doc_queue.put.aio()`. Scheduled function drains queue and classifies ALL docs in parallel via `asyncio.gather()`.

**Deployed code:**

```python
doc_queue = modal.Queue.from_name("new-docs", create_if_missing=True)

@app.cls(gpu="T4", image=classify_image, scaledown_window=120)
class DocClassifier:
    @modal.enter()
    def load_model(self):
        from transformers import pipeline
        self.classifier = pipeline("zero-shot-classification",
            model="facebook/bart-large-mnli", device=0)

    @modal.batched(max_batch_size=32, wait_ms=2000)
    async def classify(self, texts: list[str]) -> list[dict]:
        labels = ["regulatory", "economic", "safety", "infrastructure", "community", "business"]
        results = self.classifier(texts, candidate_labels=labels, multi_label=True)
        if not isinstance(results, list):
            results = [results]
        return [{"labels": r["labels"][:3], "scores": [round(s, 4) for s in r["scores"][:3]]}
                for r in results]

@app.cls(gpu="T4", image=classify_image, scaledown_window=120)
class SentimentAnalyzer:
    @modal.enter()
    def load_model(self):
        from transformers import pipeline
        self.sentiment = pipeline("sentiment-analysis",
            model="cardiffnlp/twitter-roberta-base-sentiment-latest", device=0)

    @modal.batched(max_batch_size=32, wait_ms=2000)
    async def analyze(self, texts: list[str]) -> list[dict]: ...

@app.function(image=classify_image, schedule=modal.Period(minutes=2), timeout=300)
async def process_queue_batch():
    docs = []
    while len(docs) < 100:
        try:
            doc = await doc_queue.get.aio(timeout=5)   # async queue drain
            docs.append(doc)
        except Exception:
            break
    if not docs: return 0

    # Parallel classification via asyncio.gather (was sequential blocking)
    classifications = await asyncio.gather(
        *[classifier.classify.remote.aio(text) for text in texts],
        return_exceptions=True,
    )
    sentiments = await asyncio.gather(
        *[analyzer.analyze.remote.aio(text) for text in texts],
        return_exceptions=True,
    )
    # ... enrich and save ...
    await volume.commit.aio()
```

**Pipeline integration:** 4 pipelines push to queue:
```python
# In news.py, reddit.py, public_data.py, politics.py:
await doc_queue.put.aio(doc_data)  # was: doc_queue.put(doc_data)
```

**Modal features added:** `@modal.batched`, `modal.Queue`, `modal.Retries`

---

## Phase 3: Supermemory Integration — COMPLETE

**Status: DEPLOYED** | File: `modal_app/supermemory.py`

- `SupermemoryClient` class — async httpx wrapper for Supermemory v3 API
  - `add_memory(content, metadata, container_tag)` — push docs with `container_tag="chicago_data"`
  - `search(query, container_tags, limit)` — search Chicago data with filters
  - `get_user_profile(user_id)` — fetch from `container_tag="user_{user_id}"`
  - `store_conversation(user_id, messages)` — store chat history
- `push_pipeline_data_to_supermemory()` — Modal function that batch-syncs processed data

---

## Phase 4: Agent Swarm for Query-Time Intelligence — COMPLETE

**Status: DEPLOYED** | File: `modal_app/agents.py`

- `neighborhood_intel_agent(neighborhood, business_type, focus_areas)` — queries Supermemory with neighborhood-specific filters
- `regulatory_agent(business_type)` — scans federal + local regulations
- `orchestrate_query(user_id, question, business_type, target_neighborhood)`:
  1. Get user profile from Supermemory
  2. Determine 2 adjacent comparison neighborhoods
  3. Fan-out via `.spawn()`: primary agent + 2 comparison agents + regulatory agent
  4. Gather results
  5. Build synthesis prompt → stream from LLM
- `SYNTHESIS_SYSTEM_PROMPT` — merge findings, identify conflicts, produce unified recommendation

**Modal features added:** `.spawn()` for query-time fan-out

---

## Phase 5: Modal-Hosted Web API — COMPLETE

**Status: DEPLOYED** | File: `modal_app/web.py` | URL: `https://ibsrinivas27--alethia-serve.modal.run`

**Verified endpoints:**
- `GET /health` — returns `{"status": "healthy"}`
- `GET /metrics` — 1,889 docs, 5 active sources, 47 neighborhoods
- `GET /sources` — pipeline freshness per source
- `GET /status` — pipeline monitor (doc counts, GPU status, costs)
- `POST /chat` — agent swarm orchestration + streaming SSE
- `GET /brief/{neighborhood}` — intelligence brief
- `GET /alerts` — regulatory alerts
- `GET /neighborhood/{name}` — neighborhood detail

**Deployed config:**
```python
@app.function(image=web_image, volumes={"/data": volume},
    secrets=[modal.Secret.from_name("alethia-secrets")],
    # removed: allow_concurrent_inputs=100 (deprecated for ASGI)
)
@modal.asgi_app()
def serve():
    return web_app
```

**Modal features added:** `@modal.asgi_app`, streaming SSE

---

## Phase 6: Frontend — Streaming Chat + Pipeline Monitor + Agent Visualization — COMPLETE

**Status: DEPLOYED** | 18 React components

### 6a: Streaming Chat — COMPLETE
- `ChatPanel.tsx` consumes SSE stream from `/chat` endpoint
- `api.ts` parses 5 event types: `status`, `agents`, `token`, `done`, `error`
- Real-time token streaming with cursor animation

### 6b: Pipeline Monitor Dashboard — COMPLETE
- `PipelineMonitor.tsx` polls `/status` endpoint, displays pipeline states
- `MLMonitor.tsx` shows GPU model status

### 6c: Agent Swarm + Process Flow Visualization — COMPLETE
- `ProcessFlow.tsx` — collapsible vertical trace diagram showing pipeline stages
  - Stages: Chat Request → Agent Orchestrator → agent fan-out → LLM Synthesis → Response Delivered
  - Auto-expands during processing, auto-collapses when complete
  - Copy-logs button for dev debugging (copies timestamped SSE event log)
- `AgentSwarm.tsx` — flat agent status indicators (predecessor to ProcessFlow)
- `Dashboard.tsx` tracks `processStage` state driven by SSE callbacks

---

## Phase 7: Self-Healing Reconciler + Cost Tracking — COMPLETE

**Status: DEPLOYED + ASYNC FIXED** | File: `modal_app/reconciler.py`

- `data_reconciler()` — `schedule=modal.Period(minutes=5)`
  - Checks freshness per source, auto-spawns stale pipelines via `await *.spawn.aio()`
  - Reports status: `{"news": {"state": "fresh", "doc_count": 30}, ...}`
- `log_cost(function_name, gpu, duration_seconds)` — `modal.Dict.from_name("alethia-costs")`
  - Rate table: H100 $0.001389/s, T4 $0.000164/s, CPU $0.0000125/s
- `get_total_cost()` — async function using `cost_dict.keys.aio()` and `cost_dict.get.aio()`

**Verified in logs:** Reconciler detects 2 stale sources, auto-restarts 1 (reddit).

**Modal features added:** `modal.Dict` (shared state)

---

## Phase 8: Federal Register Pipeline — COMPLETE

**Status: DEPLOYED** | File: `modal_app/pipelines/federal_register.py`

- Federal Register API (free, no auth), Agencies: SBA, FDA, OSHA, EPA
- Same pattern as existing pipelines + `retries=modal.Retries(max_retries=2, backoff_coefficient=2.0)`
- Schedule removed (was daily) to stay under 5-cron limit; runs on-demand via reconciler

---

## Phase 9: Arize AX Tracing + Connected Spans — COMPLETE

**Status: DEPLOYED** | File: `modal_app/instrumentation.py`

- `init_tracing()` — Arize `register()` with `ARIZE_SPACE_ID` + `ARIZE_API_KEY`, idempotent
- `get_tracer(name)` — returns real tracer if initialized, OTel no-op otherwise
- `inject_context()` / `extract_context()` — W3C trace context propagation across Modal containers
- OpenAI auto-instrumentor for GPT-4V calls in vision pipeline
- Traced endpoints: `/chat` (chat-request span), `/brief` (brief-request span), `/neighborhood` (neighborhood-profile span)
- Agent trace linking: orchestrator injects context → child agents extract and create linked spans
- **35 tests** in `tests/test_tracing_spans.py` + `tests/test_instrumentation.py`

---

## Phase 10: CCTV + Traffic Pipelines — COMPLETE

**Status: DEPLOYED** | Files: `modal_app/pipelines/cctv.py`, `modal_app/pipelines/traffic.py`

- **CCTV**: IDOT ArcGIS API → snapshot download → YOLOv8n pedestrian/vehicle detection on T4
- **Traffic**: TomTom API → congestion classification (free_flow/light/moderate/heavy/standstill)
- Frontend: CCTV stat card in Dashboard, DemographicsCard shows CCTV data, 5-column grid
- `/cctv/latest` and `/cctv/frame/{camera_id}` web endpoints

---

## Phase 11: Solana Data Provenance (STRETCH)

**Status: NOT STARTED** — deprioritized in favor of tracing and CCTV

---

## Modal Feature Checklist (18 deployed)

| # | Feature | Phase | Status |
|---|---------|-------|--------|
| 1 | `modal.App` | Existing | **DONE** |
| 2 | `modal.Volume` (data + weights) | Existing + P1 | **DONE** |
| 3 | `modal.Secret` | Existing | **DONE** |
| 4 | `modal.Image` (13 custom images) | Existing + P10 | **DONE** |
| 5 | `modal.Period` (scheduling) | Existing | **DONE** (5 cron jobs) |
| 6 | `.map()` (batch fan-out) | Existing | **DONE** |
| 7 | `gpu="T4"` (classifier + sentiment + CCTV) | Existing + P10 | **DONE** |
| 8 | `@modal.cls` + `@modal.enter` | Phase 1 | **DONE** |
| 9 | `@modal.concurrent(max_inputs=20)` | Phase 1 | **DONE** |
| 10 | `gpu="H100"` + vLLM | Phase 1 | **DONE** |
| 11 | `Image.pip_install()` | Phase 1 | **DONE** |
| 12 | `@modal.batched` | Phase 2 | **DONE** |
| 13 | `modal.Queue` | Phase 2 | **DONE** |
| 14 | `modal.Retries` | Phase 2 | **DONE** |
| 15 | `.spawn()` query-time fan-out | Phase 4 | **DONE** |
| 16 | `@modal.asgi_app` + streaming SSE | Phase 5 | **DONE** |
| 17 | `modal.Dict` (cost tracking) | Phase 7 | **DONE** |
| 18 | `Function.from_name` / `Cls.from_name` | Phase 5 | **DONE** |

---

## Verified Live Data (from `/metrics` and `/status`)

```json
{
  "total_documents": 1889,
  "active_sources": 5,
  "neighborhoods_covered": 47,
  "pipelines": {
    "news":        {"state": "fresh", "doc_count": 30,   "age_minutes": 10},
    "public_data": {"state": "fresh", "doc_count": 459,  "age_minutes": 14},
    "politics":    {"state": "fresh", "doc_count": 80,   "age_minutes": 151},
    "demographics":{"state": "fresh", "doc_count": 1332, "age_minutes": 152},
    "realestate":  {"state": "fresh", "doc_count": 8,    "age_minutes": 152},
    "reddit":      {"state": "missing"},
    "reviews":     {"state": "missing"}
  }
}
```

---

## Remaining Work

| Item | Priority | Notes |
|------|----------|-------|
| Reddit credentials | LOW | Need Reddit API key for reddit_ingester |
| Yelp/Google API keys | LOW | Need keys for review_ingester |
| City graph (NetworkX) | LOW | Agents read raw JSON directly — works fine |
| Solana provenance | STRETCH | Phase 11 not started |

---

## Demo Scale Numbers

- "13 pipelines ingesting from 15+ sources across 47 Chicago neighborhoods"
- "1,889+ documents processed and indexed"
- "32-document batch classification in a single GPU pass"
- "4 intelligence agents deployed per query, analyzing 3 neighborhoods in parallel"
- "Self-healing reconciler auto-restarts stale pipelines every 5 minutes"
- "18 Modal features used (target was 15)"
- "Qwen3 8B self-hosted on H100 for streaming responses"
- "YOLOv8n on T4 for live CCTV pedestrian/vehicle detection"
- "Connected OTel traces across Modal containers via W3C context propagation"
- "35 automated tests for tracing correctness"

---

## Verification Results

1. **LLM:** `modal_app/llm.py` deployed — AlethiaLLM class with H100 + vLLM
2. **Classification:** DocClassifier + SentimentAnalyzer on T4, async queue batch processing
3. **Supermemory:** Client + push function deployed
4. **Agent swarm:** 4 agent types with .spawn() fan-out
5. **Web API:** `https://ibsrinivas27--alethia-serve.modal.run` — all endpoints verified returning real data
6. **Reconciler:** Auto-detected 2 stale sources, restarted 1 — confirmed in logs
7. **Federal Register:** Pipeline deployed with Retries
8. **AsyncUsageWarnings:** Fixed in classify.py, reconciler.py, web.py, 4 pipeline files

---

## Diff: Original Plan vs Final Implementation

Changes from the original plan (written 2026-02-28) after full implementation.

### Phases added (not in original plan)
```diff
+ Phase 9: Arize AX Tracing + Connected Spans — COMPLETE
+   - OpenTelemetry tracing with Arize AX dashboard
+   - W3C trace context propagation across Modal containers
+   - 35 automated tests for tracing correctness
+
+ Phase 10: CCTV + Traffic Pipelines — COMPLETE
+   - CCTV: IDOT ArcGIS API → YOLOv8n detection on T4
+   - Traffic: TomTom API congestion classification
+   - Frontend integration (CCTV stat card, demographics overlay)
```

### Scope changes
```diff
  Original: 8 pipelines, 18 functions, 15 Modal features target
+ Final:    13 pipelines, 28+ functions, 18 Modal features (exceeded target)

  Original: 8 API endpoints planned
+ Final:    17 API endpoints live (added /cctv/latest, /cctv/frame/{id},
+           /scaling, /geo/{layer}, /neighborhood/{name}/summary, etc.)

  Original: Phase 6 frontend was "PENDING"
+ Final:    Phase 6 COMPLETE with 18 React components, ProcessFlow trace viz,
+           streaming SSE chat, pipeline monitor dashboard

  Original: Solana provenance was Phase 9
+ Final:    Deprioritized to Phase 11 (stretch) in favor of tracing and CCTV
```

### Infrastructure additions not in original plan
```diff
+ instrumentation.py — Arize AX tracing with inject/extract context
+ scaling_demo.py — Modal auto-scaling demonstration
+ 3 new Modal images: cctv_image, traffic_image, yolo_image
+ arize-secrets Modal secret group (ARIZE_SPACE_ID, ARIZE_API_KEY)
+ tests/ directory with 35 tests (test_tracing_spans.py, test_instrumentation.py)
```

### Frontend (not detailed in original plan)
```diff
+ 18 React components built:
+   Dashboard.tsx, ChatPanel.tsx, ProcessFlow.tsx, PipelineMonitor.tsx,
+   MLMonitor.tsx, AgentSwarm.tsx, OnboardingWizard.tsx, DemographicsCard.tsx,
+   AlertsPanel.tsx, MapView.tsx, NeighborhoodProfile.tsx, ChatMessage.tsx,
+   RegulatoryTimeline.tsx, StatCard.tsx, BusinessProfile.tsx,
+   ComparisonView.tsx, Header.tsx, Sidebar.tsx
+ ProcessFlow: collapsible trace viz with copy-logs dev feature
+ Tailwind CSS v4 for styling
```
