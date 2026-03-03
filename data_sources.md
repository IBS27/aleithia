# Data Ingestion Pipelines

Chicago-focused data source collectors, each running as Modal functions. All output is normalized into the common `Document` schema before writing to Modal Volume. Pipelines push documents to `modal.Queue` for GPU classification.

**Live stats:** 1,889+ documents | 47 neighborhoods | 5 cron sources | 11 on-demand sources | 14 pipelines total

---

## 1. Local News — `news_ingester`

**File:** `modal_app/pipelines/news.py`
**Schedule:** Every 30 minutes (cron)
**Pattern:** async + FallbackChain (NewsAPI → RSS → cache)

**Sources:**
- Block Club Chicago (RSS)
- Chicago Tribune (RSS)
- Chicago Sun-Times (RSS)
- Crain's Chicago Business (RSS)
- Patch.com Chicago neighborhoods (RSS)
- NewsAPI for broader coverage

**What we collect:**
- Article headline, body text, publication date
- Author, source outlet
- Geo-tags via `detect_neighborhood()` (neighborhood mentions, addresses)
- Article category/section

**Pipeline integration:** Pushes to `doc_queue` via `await doc_queue.put.aio(doc_data)` for GPU classification.

---

## 2. Local Politics — `politics_ingester`

**File:** `modal_app/pipelines/politics.py`
**Schedule:** On-demand (reconciler triggers when stale)
**Pattern:** async + FallbackChain + PDF parsing (pymupdf/pdfplumber)

**Sources:**
- Chicago Legistar API (council meetings, legislation, voting records)
- Zoning Board of Appeals meeting agendas and minutes (PDF)
- Plan Commission hearing transcripts (PDF)
- Chicago City Clerk ordinance filings

**What we collect:**
- Meeting date, committee/body, agenda items
- Legislation text, sponsors, status
- Zoning change applications
- Hearing transcripts (raw text extracted from PDFs via `_extract_pdf_text()`)

**Pipeline integration:** Pushes to `doc_queue` for classification. Uses `modal.Retries(max_retries=2, backoff_coefficient=2.0)`.

---

## 3. Social Media & Reviews

### 3a. Reddit — `reddit_ingester`

**File:** `modal_app/pipelines/reddit.py`
**Schedule:** Every 1 hour (cron)
**Pattern:** Hybrid retrieval + FallbackChain (asyncpraw listings/search → RSS search/hot → cache)

**Sources:**
- r/chicago, r/AskChicago, r/chicagofood, r/chicagofitness
- r/ChicagoNWside, r/SouthSideChicago, r/chicagoapartments
- r/ChicagoSuburbs, r/westloop, r/chicagojobs

**What we collect:**
- Post title, body, score, comment count, created timestamp
- Subreddit, flair/tags, retrieval metadata
- Query-time fallback hits are persisted into normal `/raw/reddit/...` flow and enqueued for classification

**Note:** Reddit API credentials (`REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`) improve reliability and search quality. Without creds, RSS fallback is used and may rate-limit (HTTP 429) under burst traffic.

### 3b. Review Platforms — `review_ingester`

**File:** `modal_app/pipelines/reviews.py`
**Schedule:** On-demand
**Pattern:** async + FallbackChain + `gather_with_limit` + review velocity computation

**Sources:**
- Yelp Fusion API (business search across 8 neighborhoods, 9 categories)
- Google Places API (business search)

**What we collect:**
- Business name, category, location (lat/lng, neighborhood)
- Rating, review count, price level
- Review velocity annotation (`high` / `medium` / `low`)

**Neighborhoods searched:** Lincoln Park, Wicker Park, Logan Square, West Loop, Pilsen, Hyde Park, Andersonville, Chinatown

### 3c. TikTok — `tiktok_ingester`

**File:** `modal_app/pipelines/tiktok.py`
**Schedule:** On-demand
**Pattern:** Kernel cloud browser + Playwright automation + Whisper transcription

**Sources:**
- TikTok search for Chicago-related trending content via Kernel cloud browsers
- Audio transcription via OpenAI Whisper (A10G GPU)

**What we collect:**
- Video metadata (title, creator, views, likes)
- Audio transcription text
- Trend analysis and aggregation across neighborhoods

**Functions:** `fetch_tiktok_videos`, `transcribe_tiktok_audio`, `analyze_tiktok_trends`, `aggregate_trending_data`

---

## 4. Public Data (Chicago Data Portal & Government APIs)

### 4a. Public Data Portal — `public_data_ingester`

**File:** `modal_app/pipelines/public_data.py`
**Schedule:** Daily (cron)
**Pattern:** async + FallbackChain (Socrata API → direct HTTP → cache)

**Sources (via data.cityofchicago.org Socrata API):**
- Business license applications and renewals
- Building permits (new construction, renovation, demolition)
- Food establishment inspections
- CTA L-station ridership data (`t2rn-p8d7`) — used for Walk-In Potential transit scoring
- CTA bus ridership data (`jyb9-n7fm`)

**Transit scoring:** CTA L-station ridership + station locations (`8pix-ypme`) are used by the web API to compute a Walk-In Potential score per neighborhood. Stations within 3km of the neighborhood centroid are matched, and average weekday ridership is normalized to a 0–100 transit score, weighted by business type.

**Live count:** 459 documents

### 4b. Demographics — `demographics_ingester`

**File:** `modal_app/pipelines/demographics.py`
**Schedule:** On-demand
**Pattern:** async + FallbackChain (Census API with key → Census API without key → cache)

**Sources:**
- U.S. Census Bureau ACS 5-year estimates (API)
- Population, income, housing data per Chicago community area

**Live count:** 1,332 documents (77 community areas × multiple variables)

### 4c. Real Estate — `realestate_ingester`

**File:** `modal_app/pipelines/realestate.py`
**Schedule:** On-demand
**Pattern:** async + FallbackChain (LoopNet API → placeholder listings → cache)

**Sources:**
- LoopNet commercial property search (8 Chicago areas)
- Placeholder listings for demo (retail, restaurant, office across neighborhoods)

**Live count:** 8 documents (placeholder data — LoopNet requires CoStar API for production)

---

## 5. Federal Regulations — `federal_register_ingester`

**File:** `modal_app/pipelines/federal_register.py`
**Schedule:** On-demand
**Pattern:** async + FallbackChain + `modal.Retries`

**Sources:**
- Federal Register API (free, no auth required)
- Agencies: SBA, FDA, OSHA, EPA

**What we collect:**
- Regulation title, abstract, document number
- Agency, document type, action
- Filtered for business-relevant keywords (small business, restaurant, food service, etc.)

---

## 6. Traffic Flow — `traffic_ingester`

**File:** `modal_app/pipelines/traffic.py`
**Schedule:** On-demand
**Pattern:** async + FallbackChain (TomTom API → cache)

**Sources:**
- TomTom Traffic Flow API (free tier available)

**What we collect:**
- Real-time traffic flow speed, free-flow speed, confidence
- Congestion classification (free_flow / light / moderate / heavy / standstill)
- Coverage across key Chicago corridors

**Note:** Requires `TOMTOM_API_KEY`. Classifies congestion into density tiers for business location scoring.

---

## 7. Highway Traffic (IDOT CCTV) — `cctv_ingester`

**File:** `modal_app/pipelines/cctv.py`
**Schedule:** On-demand (was 5min cron, removed to stay under cron limit)
**Pattern:** IDOT ArcGIS API → snapshot download → YOLOv8n GPU detection

**Sources:**
- Illinois Department of Transportation (IDOT) ArcGIS REST API (public, no auth)
- Highway camera snapshots around Chicago metro area (I-90/94, expressway ramps, etc.)

**What we collect:**
- Camera locations (lat/lng, description)
- JPEG snapshots from live feeds
- YOLOv8n detection: vehicle count, pedestrian count per frame
- Highway traffic density classification (high / medium / low)

**Important:** These are expressway cameras, not street-level. Vehicle counts are the primary useful metric. Pedestrian counts are near-zero on highways and should not be used for walk-in potential scoring. Walk-in potential is instead sourced from CTA L-station ridership data (see Section 4a, `cta_ridership_L` dataset).

**GPU:** T4 via `CCTVDetector` class (YOLOv8n inference)
**Functions:** `cctv_ingester`, `analyze_cctv_batch`, `CCTVDetector`

---

## 8. Neighborhood Vision — `vision` pipeline

**File:** `modal_app/pipelines/vision.py`
**Schedule:** On-demand
**Pattern:** YouTube download → frame extraction → GPT-4V labeling → YOLO training → inference → persist per-neighborhood

**Sources:**
- YouTube walking tour videos of Chicago neighborhoods

**What we collect:**
- Video frames extracted at configurable intervals
- GPT-4V labels (8 classes: person, vehicle, storefront_open, storefront_closed, for_lease_sign, construction, restaurant_signage, outdoor_dining)
- Custom-trained YOLOv8n detector for neighborhood analysis
- Per-neighborhood analysis results persisted to `/data/processed/vision/analysis/{neighborhood}_{timestamp}.json`

**Neighborhood filtering:** `analyze_neighborhood()` accepts a `neighborhood` parameter and saves results with neighborhood metadata. The `/vision/streetscape/{neighborhood}` API endpoint filters results by neighborhood (filename prefix or JSON field match), returning only data for the requested area.

**GPU:** T4 (training + inference), GPT-4V via OpenAI API (labeling)
**Functions:** `extract_frames`, `label_all_frames`, `train_detector`, `analyze_neighborhood`

---

## 9. Satellite Parking Detection — `parking_ingester`

**File:** `modal_app/pipelines/parking.py`
**Schedule:** On-demand
**Pattern:** Mapbox satellite tile download → SegFormer-b5 semantic segmentation → YOLOv8m + SAHI vehicle detection → occupancy estimation

**Sources:**
- Mapbox Satellite API (requires `MAPBOX_TOKEN`)
- Slippy map tiles at zoom level 19 (~0.3m/pixel resolution)

**What we collect:**
- 3x3 tile grid (768x768 composite) per neighborhood centroid
- Parking lot detection via SegFormer-b5 Cityscapes segmentation (road + terrain surfaces)
- Vehicle detection via YOLOv8m with SAHI slicing (640px tiles, 0.2 overlap) for car, motorcycle, bus, truck
- Per-lot metrics: center lat/lng, area (sqm), estimated capacity (15 sqm/stall), vehicles detected, occupancy rate
- Overall metrics: total lots, total capacity, total vehicles, overall occupancy, coverage area
- Annotated satellite overlay JPEG with green lot contours + red vehicle bounding boxes

**Processing pipeline:**
1. CPU ingester downloads 3x3 Mapbox satellite tiles per neighborhood
2. GPU analyzer (T4) stitches tiles into composite image
3. SegFormer-b5 generates semantic segmentation mask (parking surfaces)
4. Morphological cleanup → contour detection with filters (aspect ratio, solidity, area)
5. YOLOv8m + SAHI detects vehicles, NMS deduplication
6. Vehicles assigned to lot regions via mask lookup
7. Results saved as JSON analysis + annotated JPEG overlay

**Volume paths:**
- Raw tiles: `/data/raw/parking/{neighborhood}_{timestamp}/`
- Analysis JSON: `/data/processed/parking/analysis/{slug}_{timestamp}.json`
- Annotated images: `/data/processed/parking/annotated/{slug}.jpg`

**GPU:** T4 via `ParkingAnalyzer` class (SegFormer-b5 + YOLOv8m, `@modal.enter(snap=True)`)
**Functions:** `parking_ingester`, `analyze_parking_batch`, `ParkingAnalyzer`

---

## 10. Population Demographics — `worldpop_ingester`

**File:** `modal_app/pipelines/worldpop.py`
**Schedule:** On-demand
**Pattern:** Google Earth Engine API

**Sources:**
- WorldPop dataset via Google Earth Engine (age/sex-stratified population estimates)

**What we collect:**
- Population density per neighborhood
- Age and sex demographic breakdowns

**Note:** Requires Google Earth Engine authentication via `ee_image`.

---

## 11. VectorAI DB — Semantic Search Layer

**File:** `modal_app/vectordb.py`
**Schedule:** Always-on (`min_containers=1`, `scaledown_window=300`)
**Pattern:** Actian VectorAI DB (HNSW-indexed) + sentence-transformer embeddings

**Docker Image:** `williamimoh/actian-vectorai-db:1.0b`
**Python Client:** `actiancortex` (CortexClient, gRPC on port 50051)

**Embedding Model:** `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions, cosine similarity)

**Collections:** 15 total — one per data source (`news`, `politics`, `reddit`, `reviews`, `realestate`, `federal_register`, `tiktok`, `demographics`, `public_data`, `traffic`, `cctv`, `vision`, `parking`, `worldpop`) + `enriched` (unified cross-source collection)

**How it works:**
1. Documents are embedded at ingestion time in `classify.py` after enrichment
2. `build_embed_text()` concatenates title + first 1,000 chars of content
3. `build_payload()` creates metadata (doc_id, source, neighborhood, category, sentiment)
4. `batch_upsert_docs()` writes vectors + payloads to the `enriched` collection
5. At query time, `neighborhood_intel_agent` calls `search_neighborhood()` for semantic retrieval filtered by neighborhood
6. Query embedding is pre-computed once in `orchestrate_query()` and shared across all agent spawns

**VectorDBService methods:**
- `embed_text(text)` — Single text → 384-dim vector
- `embed_batch(texts)` — Batch embed (batch_size=32)
- `upsert_doc(doc_id, embedding, payload, collection)` — Single upsert
- `batch_upsert_docs(doc_ids, embeddings, payloads, collection)` — Batch upsert + flush
- `search(query_embedding, collection, top_k, filter_dict)` — Semantic search with optional payload filters
- `search_neighborhood(query_embedding, neighborhood, top_k)` — Convenience: search enriched collection filtered by neighborhood
- `health_check()` — Returns status + per-collection document counts

**Graceful degradation:** All VectorDB operations are guarded by `vectordb_available()` (returns `False` when `VECTORDB_DISABLED=1` env var is set) and wrapped in try/except. The platform operates normally without VectorDB — agents fall back to raw JSON file reads.

**Backfill:** `backfill_vectordb()` reads all existing enriched docs from volume and indexes them. Run manually: `modal run -m modal_app modal_app.vectordb::backfill_vectordb`

**Health monitoring:** The reconciler checks VectorDB health every 5 min via `check_vectordb_health()`. Status is exposed on `/status` and `/health` API endpoints.

---

## GPU Classification Pipeline

### DocClassifier + SentimentAnalyzer — `process_queue_batch`

**File:** `modal_app/classify.py`
**Schedule:** Every 2 minutes (cron)
**GPU:** T4 (2 instances — one per model)

**Models:**
- `facebook/bart-large-mnli` (406M params) — zero-shot classification into: regulatory, economic, safety, infrastructure, community, business
- `cardiffnlp/twitter-roberta-base-sentiment-latest` — sentiment analysis (positive/negative/neutral)

**Pattern:** Drains `modal.Queue`, classifies up to 100 docs per batch via `asyncio.gather()` (parallel), saves enriched docs to `/data/processed/enriched/`.

---

## Pipeline Schedule Summary

| Pipeline | Schedule | Source Count | Status |
|----------|----------|-------------|--------|
| `news_ingester` | 30 min cron | 30 docs | Active |
| `reddit_ingester` | 1 hr cron | — | Needs API keys |
| `public_data_ingester` | Daily cron | 459 docs | Active |
| `process_queue_batch` | 2 min cron | — | Active (GPU classifier) |
| `data_reconciler` | 5 min cron | — | Active (self-healing) |
| `politics_ingester` | On-demand | 80 docs | Active |
| `demographics_ingester` | On-demand | 1,332 docs | Active |
| `review_ingester` | On-demand | — | Needs API keys |
| `realestate_ingester` | On-demand | 8 docs | Active (placeholders) |
| `federal_register_ingester` | On-demand | — | Active |
| `tiktok` (4 functions) | On-demand | — | Active (needs Kernel) |
| `traffic_ingester` | On-demand | — | Active (needs TOMTOM_API_KEY) |
| `cctv_ingester` + `CCTVDetector` | On-demand | — | Active (public IDOT API) |
| `vision` (5 functions) | On-demand | — | Active (needs OPENAI_API_KEY) |
| `parking` (3 functions) | On-demand | — | Active (needs MAPBOX_TOKEN) |
| `worldpop_ingester` | On-demand | — | Active (needs Earth Engine auth) |
| `VectorDBService` | Always-on | — | Active (HNSW semantic search) |
