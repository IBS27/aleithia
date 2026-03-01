# City Graph — Architecture

## Three Pillars

**Modal = The Brain.** All data ingestion (cron functions), all AI inference (Llama 3.1 8B on A10G for entity extraction/sentiment/signals, MiniLM for embeddings), all graph construction and reasoning algorithms. Modal Volumes persist the graph and raw data. Modal Classes hold warm GPU models.

**Supermemory = The Long-Term Memory.** Every insight the system uncovers gets stored as a memory with rich metadata. When a user queries about a neighborhood, the system pulls both fresh graph data AND historical insights that have accumulated over time. `containerTag` scopes memories per-user (personalized business context) and per-neighborhood (shared city intelligence). The system gets smarter over time.

**FastAPI = The Interface.** Thin proxy. Accepts user queries, forwards to Modal for graph reasoning, enriches with Supermemory context, streams responses back. Handles user sessions and WebSocket connections.

```
User → FastAPI → Modal (graph traversal + reasoning)
                    ↓                    ↑
              Supermemory ←──────────────┘
              (insight memory)     (stores new insights)

Modal Cron → Ingest → Enrich (Llama) → Graph Update → New Insights → Supermemory
```

---

## Modal Layer — The Brain

### Data Ingestion (Modal Cron Functions)

Each ingester is a separate `@modal.function` with a `@modal.cron` schedule. All sources and cadences are defined in `data_sources.md`. Each ingester writes raw documents to a Modal Volume (`city-data-volume`) as JSON files partitioned by source and date. Every document gets a UUID, timestamp, and source tag.

Deduplication: each ingester maintains a seen-URLs set (persisted to the Volume) to avoid reprocessing. For permits/licenses, dedup on permit number.

### Enrichment Pipeline (Modal GPU Functions)

Two persistent GPU services using `@modal.cls` for warm model instances:

**EmbeddingService (MiniLM L6 v2 on T4 GPU):**
- Accepts batches of text, returns 384-dim embeddings
- Used for document embedding, query embedding, similarity computation between entities
- Warm container — first call loads the model, subsequent calls are fast

**LLMService (Llama 3.1 8B on A10G GPU via vLLM):**
- Structured output extraction via constrained decoding (not free-form generation)
- For each raw document, extracts a structured enrichment payload:

```json
{
  "entities": [
    {"name": "Logan Square", "type": "neighborhood", "confidence": 0.95},
    {"name": "Ald. Martinez", "type": "politician", "confidence": 0.88}
  ],
  "sentiment": {"score": -0.3, "target": "new development", "from": "residents"},
  "regulatory_signal": {
    "direction": "restrictive",
    "domain": "zoning",
    "strength": 0.7,
    "description": "Opposition to rezoning for mixed-use"
  },
  "geo": {"neighborhood": "Logan Square", "ward": 35, "lat": 41.923, "lng": -87.708},
  "category": "development",
  "business_relevance": 0.82
}
```

The LLM's job is structured extraction, not opinion generation. The output schema is enforced via vLLM's guided decoding, so you always get valid JSON with the right fields.

**EnrichmentPipeline (Modal function, orchestrates the above):**
- Triggered on a schedule (every 15 min) OR by ingester completion
- Reads unprocessed documents from the Volume
- Batches them through EmbeddingService and LLMService
- Writes enriched documents back to the Volume
- Marks documents as processed

### Graph Construction (Modal Function)

`build_graph` runs after enrichment and updates the city graph.

The graph is a NetworkX directed multigraph serialized to the Modal Volume as a pickle file. NetworkX is fine for hackathon scale — thousands of nodes, not millions.

**Node types:**
- `neighborhood` — 77 Chicago community areas
- `business_type` — restaurant, bar, retail, tech, etc.
- `politician` — alderpersons, mayor, committee chairs
- `regulation` — specific ordinances, zoning codes, license types
- `trend` — detected patterns (e.g., "rising permit activity in Pilsen")
- `entity` — specific businesses, developments, organizations mentioned

**Edge types with weights:**
- `regulates(politician → regulation, weight=influence_score)`
- `affects(regulation → neighborhood, weight=impact_score)`
- `sentiment(neighborhood → business_type, weight=avg_sentiment)`
- `competes_in(business_type → neighborhood, weight=density)`
- `supports / opposes(politician → regulation, weight=vote_probability)`
- `trending(trend → neighborhood, weight=signal_strength)`

**How edges get their weights:**
- Permit density → `competes_in` weight (more permits = higher competition)
- Reddit sentiment aggregation → `sentiment` weight (rolling average)
- Council vote patterns → `supports/opposes` weight (historical vote alignment)
- News frequency + regulatory signal direction → `affects` weight

Each graph update is timestamped. The graph is temporal — edges carry a `last_updated` and `decay_rate` field. Old signals fade unless refreshed by new data.

### Reasoning Engine (Modal Function)

`reason_about_decision` — the core intelligence function. This is NOT "ask the LLM what it thinks." This is a deterministic graph traversal + scoring pipeline that produces structured evidence, then hands that evidence to the LLM for narration.

**Step 1: Query Decomposition**
Given a user question like "Should I open a ramen restaurant in Logan Square?", decompose into dimensions:
- `location = "Logan Square"`
- `business_type = "restaurant" (subtype: "ramen")`
- Dimensions to score: regulatory risk, competition density, demographic fit, sentiment trajectory, political climate

**Step 2: Graph Traversal (deterministic algorithms)**

| Dimension | Algorithm | What it computes |
|-----------|-----------|-----------------|
| Regulatory risk | Weighted shortest path from `business_type` → `regulation` → `neighborhood` | How many regulations affect this business type in this area, weighted by restrictiveness |
| Competition | Node degree + edge weight on `competes_in` edges | How many similar businesses exist, weighted by permit recency |
| Sentiment | Aggregate `sentiment` edges targeting this `business_type` in this `neighborhood` | Rolling average sentiment from social/news sources |
| Political climate | PageRank on politician nodes + their `supports/opposes` edges to relevant regulations | Which politicians have influence and which direction they lean |
| Trend momentum | Time-series slope on `trending` edges | Are signals getting stronger or weaker over time |

Each dimension produces a numerical score (0-10) with a provenance list — the specific data points that contributed to that score.

**Step 3: Composite Scoring**
Weighted average across dimensions → overall viability score. Weights are adjustable but default to equal.

**Step 4: LLM Narration**
The structured scores + provenance get handed to Llama with a prompt: "Given these scores and evidence, write a structured brief. Bull case, bear case, key uncertainties, and what assumptions would change the recommendation. Do NOT invent facts — only reference the provided evidence."

The LLM narrates the math. It doesn't make up the math.

**Step 5: Insight Storage → Supermemory**
Every completed analysis gets stored as an insight in Supermemory.

---

## Supermemory — The Long-Term Memory

### Two Memory Scopes

**City-level memories (`containerTag: "city-chicago"`):**
Insights that apply to anyone asking about Chicago. These accumulate automatically as the enrichment and reasoning pipelines run:
- Trend detections ("Logan Square permit applications for restaurants up 40% in Q4 2025")
- Political patterns ("Ald. Martinez has voted against 3 of 4 liquor license expansions in Ward 35")
- Sentiment shifts ("Reddit sentiment toward new development in Pilsen shifted negative in Jan 2026")
- Anomalies ("Food inspection failure rates in Wicker Park are 2x the city average")

Each memory gets metadata for filtering:

```json
{
    "content": "Logan Square permit applications for restaurants up 40% in Q4 2025",
    "containerTag": "city-chicago",
    "metadata": {
        "type": "trend",
        "neighborhood": "Logan Square",
        "business_domain": "restaurant",
        "signal_strength": 0.85,
        "source_pipeline": "permits",
        "data_points": 47,
        "detected_at": "2026-02-28"
    }
}
```

**User-level memories (`containerTag: "user-{user_id}"`):**
Personalized context per business owner:
- Their business profile (type, neighborhood, size, concerns)
- Every query they've asked and the structured brief they received
- Which risk factors they've acknowledged vs. which are new to them
- Their specific watchlist (neighborhoods, regulations, competitors they care about)

### When Memories Get Created

**From the enrichment pipeline (automatic, city-level):**
After each enrichment cycle, a Modal function runs trend detection across the freshly enriched documents. When it detects a statistically notable pattern (permit spike, sentiment shift, regulatory trend), it writes a memory to Supermemory under `city-chicago`.

**From the reasoning engine (per-query, both scopes):**
When a user query produces a structured brief:
1. City-level: any novel insight discovered during graph traversal (e.g., "competition density for ramen specifically in Logan Square is low despite high restaurant density")
2. User-level: the full query + brief, so follow-up queries have context

**From anomaly detection (automatic, city-level):**
A scheduled Modal function compares current graph state against 7-day / 30-day baselines. When something deviates significantly, it creates a memory.

### How Memories Get Retrieved

When the reasoning engine processes a user query, it makes two Supermemory searches before graph traversal:

**City-level search:**
```
POST /v4/search
q: "ramen restaurant Logan Square regulatory risk competition"
containerTag: "city-chicago"
searchMode: "hybrid"
filters: OR [{neighborhood: "Logan Square"}, {business_domain: "restaurant"}]
limit: 10, threshold: 0.5, rerank: true
```

**User-level search:**
```
POST /v4/search
q: "ramen restaurant Logan Square"
containerTag: "user-{user_id}"
searchMode: "hybrid"
limit: 5
```

Retrieved memories get injected into the reasoning engine as prior knowledge — they augment the graph traversal, not replace it. The graph gives current state; Supermemory gives accumulated wisdom.

### The Compounding Effect

Most systems are stateless — ask a question, get an answer, done. City Graph accumulates intelligence. More data makes the graph richer, richer graphs produce better insights, better insights accumulate in Supermemory, accumulated memory makes future answers faster and more informed.

---

## Frontend — The Interface

### Query Interface (Primary View)

A user types a business decision question and gets back a structured intelligence brief, not a chat response.

**Input:** Natural language query bar. "Should I open a ramen restaurant in Logan Square?"

**Output:** A structured brief rendered as a card layout:

```
┌─────────────────────────────────────────────────────┐
│  VIABILITY SCORE: 7.2 / 10          [Logan Square]  │
│  ████████████████████░░░░░░░░                       │
│                                                      │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐   │
│  │ Regulatory   │ │ Competition │ │ Sentiment    │   │
│  │ Risk: 3/10   │ │ Density: 6  │ │ Trend: +0.4  │   │
│  │ ▼ 12 sources │ │ ▼ 8 sources │ │ ▼ 34 sources │   │
│  └─────────────┘ └─────────────┘ └─────────────┘   │
│                                                      │
│  ┌─────────────┐ ┌─────────────┐                    │
│  │ Political    │ │ Trend        │                    │
│  │ Climate: 5   │ │ Momentum: +2 │                    │
│  │ ▼ 6 sources  │ │ ▼ 15 sources │                    │
│  └─────────────┘ └─────────────┘                    │
│                                                      │
│  ── BULL CASE ──────────────────────────────────    │
│  [LLM-narrated analysis referencing evidence]        │
│                                                      │
│  ── BEAR CASE ──────────────────────────────────    │
│  [LLM-narrated analysis referencing evidence]        │
│                                                      │
│  ── KEY UNCERTAINTIES ──────────────────────────    │
│  • [List of unknowns and assumptions]                │
│                                                      │
│  ── PROVENANCE ─────────────────────────────────    │
│  75 data points across 4 sources                     │
│  Freshest signal: 2 hours ago (Reddit)               │
│  Oldest signal: 6 months ago (Census ACS)            │
└─────────────────────────────────────────────────────┘
```

Each dimension score card is expandable — click the source count to see the actual permit filings, Reddit posts, and news articles that contributed. Full provenance chain.

### Live Pipeline Dashboard (Secondary View)

Shows the system working in real time.

**Left column — Ingestion Feed:**
A live-updating list of what the system is ingesting. Each entry shows source icon, title/snippet, timestamp, and processing status (ingested → enriching → enriched → graphed).

**Right column — Graph Visualization:**
A force-directed graph (react-force-graph or d3-force) showing the neighborhood being viewed. Nodes are color-coded by type, edges show relationship strength by thickness. When new data flows in, nodes light up and edges update in real time.

**Pipeline Stats:**
Document counts per source, average enrichment latency, graph node/edge counts.

### Onboarding (Minimal)

A 3-step form that creates the user's Supermemory profile:
1. **What's your business?** — dropdown: restaurant, bar, retail, tech, service, other
2. **Where?** — neighborhood picker (autocomplete across Chicago's 77 community areas)
3. **What concerns you most?** — multi-select: zoning, competition, crime/safety, regulations, transit access, rent/costs

On submit: creates a Supermemory user profile (`containerTag: "user-{id}"`), then redirects to the query interface with a pre-populated first query based on their profile.

### Tech Choices

- React 19 + TypeScript (already scaffolded)
- Tailwind CSS for styling
- react-force-graph or @visx for graph visualization
- WebSocket connection to FastAPI for live pipeline updates
- Framer Motion for score card animations

The frontend is a structured intelligence tool that accepts natural language input. The output format (score cards, provenance chains, bull/bear cases) is fixed and deterministic. The LLM fills in the narrative sections; everything else is computed.

---

## End-to-End Data Flows

### Flow 1: Continuous Ingestion → Enrichment → Graph Update (Always Running)

```
Modal Cron triggers ingest_* functions (per cadence in data_sources.md)
│
├─ Each ingester writes raw JSON → city-data-volume/{source}/{date}/
├─ Each doc gets: UUID, timestamp, source tag, status: "raw"
├─ Dedup via seen-URLs set persisted to Volume
│
▼
Every 15 min: Modal triggers enrich_batch()
│
├─ Reads all docs with status: "raw"
├─ Batches through EmbeddingService (MiniLM on T4) → 384-dim vectors
├─ Batches through LLMService (Llama 3.1 8B on A10G) → structured extraction
│   (entities, sentiment, regulatory signals, geo, category, confidence scores)
├─ Writes enriched docs back, status: "enriched"
│
▼
After enrichment: Modal triggers build_graph()
│
├─ Loads current graph from Volume (NetworkX pickle)
├─ For each enriched doc:
│   ├─ Upsert entity nodes (deduplicate by name + type)
│   ├─ Create/update edges with new weights
│   └─ Timestamp all mutations
├─ Serializes updated graph back to Volume
├─ Marks docs as status: "graphed"
│
▼
After graph update: Modal triggers detect_trends()
│
├─ Compares current graph state vs. 7-day / 30-day baselines
├─ Detects: permit spikes, sentiment shifts, new regulations, anomalies
├─ For each notable pattern → POST to Supermemory (containerTag: "city-chicago")
│
▼
System is now smarter. Loop repeats.
```

### Flow 2: User Query → Reasoning → Brief (On Demand)

```
User types question → Frontend WebSocket → FastAPI
│
▼
FastAPI calls Modal: reason_about_decision(query, user_id)
│
▼
Step 1: DECOMPOSE
├─ LLMService extracts: location, business_type, subtype, dimensions to score
│
▼
Step 2: RETRIEVE MEMORY (parallel)
├─ Supermemory city-level search (containerTag: "city-chicago", filtered by neighborhood + business domain)
│   → Returns historical insights
├─ Supermemory user-level search (containerTag: "user-{id}")
│   → Returns past queries, profile, acknowledged risks
│
▼
Step 3: GRAPH TRAVERSAL (deterministic, per dimension)
├─ Regulatory risk → weighted shortest path → score + provenance
├─ Competition → node degree + edge weights → score + provenance
├─ Sentiment → aggregate sentiment edges → score + provenance
├─ Political climate → PageRank + supports/opposes edges → score + provenance
├─ Trend momentum → time-series slope → score + provenance
│
▼
Step 4: COMPOSITE SCORE
├─ Weighted average → overall viability score
├─ Confidence based on data point count and freshness
│
▼
Step 5: LLM NARRATION
├─ Llama receives scores + provenance + historical insights + user context
├─ Returns: bull case, bear case, key uncertainties
├─ References ONLY provided evidence
│
▼
Step 6: STORE + RESPOND (parallel)
├─ Supermemory city-level: store novel insights discovered during traversal
├─ Supermemory user-level: store query + brief for future context
├─ Stream structured brief → FastAPI WebSocket → Frontend
│
▼
Frontend renders: score cards, narrative sections, provenance chains
```

### Flow 3: Live Pipeline → Frontend (WebSocket Push)

```
Modal function completes (any ingester, enrichment, or graph update)
│
▼
Writes pipeline_event to Modal Dict:
  {event_type, doc_id, source, snippet, entities, sentiment, timestamp}
│
▼
FastAPI polls Modal Dict every 2 seconds (or Modal webhook)
│
▼
FastAPI pushes event via WebSocket to connected frontends
│
▼
Frontend updates: live feed, pipeline stats, graph visualization pulses
```

### How the Three Flows Connect

```
Flow 1 (continuous)          Flow 2 (on-demand)         Flow 3 (live)
──────────────────          ─────────────────          ──────────────
Ingest → Enrich → Graph     Query → Reason → Brief     Events → UI
        │                          │     │
        │    ┌─────────────────────┘     │
        │    │                           │
        ▼    ▼                           ▼
    ┌──────────────┐              ┌──────────────┐
    │  SUPERMEMORY  │◄────────────│  SUPERMEMORY  │
    │  city-chicago │              │  user-{id}    │
    │  (insights)   │──────┐      │  (personal)   │
    └──────────────┘      │      └──────────────┘
                          │             │
                          ▼             ▼
                    Flow 2 retrieves from BOTH
                    scopes on every query
```

Flow 1 feeds the graph and Supermemory with raw intelligence. Flow 2 reads from both to answer questions and writes new insights back. Flow 3 gives the user a window into Flow 1. The three flows create a flywheel — more data makes the graph richer, richer graphs produce better insights, better insights accumulate in Supermemory, accumulated memory makes future answers faster and more informed.
