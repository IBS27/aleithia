# Data Ingestion Pipelines

Chicago-focused data source collectors, each running as Modal functions. All output is normalized into the common `Document` schema before writing to Modal Volume. Pipelines push documents to `modal.Queue` for GPU classification.

**Live stats:** 1,889+ documents | 47 neighborhoods | 5 active cron sources | 3 on-demand sources

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
**Pattern:** async + FallbackChain (asyncpraw → JSON API → cache)

**Sources:**
- r/chicago, r/chicagofood, r/ChicagoNWside, r/SouthSideChicago

**What we collect:**
- Post title, body, score, comment count, created timestamp
- Top-level comments
- Subreddit, flair/tags

**Note:** Requires Reddit API credentials (`REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`). Falls back to Reddit JSON API (may return 403).

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

### 3c. TikTok / Instagram (Deferred)

**Status:** Deferred — no reliable public API.

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
- CTA ridership data

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
