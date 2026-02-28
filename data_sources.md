# Data Ingestion Pipelines (Layer 1)

Chicago-focused data source collectors, each running as Modal functions on independent cron schedules. All output is normalized into the common event schema before writing to the store.

---

## 1. Local News

**Sources:**
- Block Club Chicago (RSS)
- Chicago Tribune (RSS)
- Chicago Sun-Times (RSS)
- Crain's Chicago Business (RSS)
- Patch.com Chicago neighborhoods (RSS)
- NewsAPI for broader coverage

**Cadence:** Every 30 minutes

**What we collect:**
- Article headline, body text, publication date
- Author, source outlet
- Geo-tags if present (neighborhood mentions, addresses)
- Article category/section (crime, development, politics, food, etc.)

**Technical notes:**
- RSS feeds are the primary mechanism — lightweight, no auth needed for most
- NewsAPI as a fallback/supplement (requires API key, free tier has limits)
- Deduplication by URL to avoid re-ingesting the same article across feeds
- Store raw HTML/text for later re-enrichment if the extraction logic improves

---

## 2. Local Politics (Policy Discussions & Hearings)

**Sources:**
- Chicago Legistar API (council meetings, legislation, voting records)
- Zoning Board of Appeals meeting agendas and minutes (PDF)
- Plan Commission hearing transcripts (PDF)
- Chicago City Clerk ordinance filings
- Cook County Board of Commissioners (Legistar)
- Illinois General Assembly legislation tracker (for state-level impacts)

**Cadence:** Daily

**What we collect:**
- Meeting date, committee/body, agenda items
- Legislation text, sponsors, status (introduced, passed, tabled, etc.)
- Voting records per alderman
- Zoning change applications (address, current/proposed zoning, applicant)
- Hearing transcripts (raw text extracted from PDFs)

**Technical notes:**
- Legistar has a structured REST API — most reliable source
- PDF transcripts require `pymupdf` or `pdfplumber` for text extraction
- Some documents are scanned images — need OCR fallback (Tesseract or an LLM vision call)
- Map each piece of legislation to the ward(s) and neighborhood(s) it affects
- Track legislation lifecycle: introduction -> committee -> vote -> outcome

---

## 3. Social Media & Reviews

### 3a. Reddit

**Sources:**
- r/chicago
- r/chicagofood
- r/ChicagoSuburbs
- Neighborhood-specific subs (r/LoganSquare, r/WickerPark, etc.)

**Cadence:** Every 1 hour

**What we collect:**
- Post title, body, score, comment count, created timestamp
- Top-level comments (up to N per post)
- Subreddit, flair/tags
- Author (anonymized — we care about volume/sentiment, not identity)

**Technical notes:**
- Reddit API via `asyncpraw` (requires app credentials, free tier is sufficient)
- Filter by minimum score threshold to reduce noise
- Track post velocity per subreddit as a signal (spike in posts about a neighborhood = something happening)

### 3b. Review Platforms (Yelp, Google)

**Sources:**
- Yelp Fusion API (business search, business details, review counts)
- Google Places API (ratings, review counts, place details)

**Cadence:** Daily

**What we collect:**
- Business name, category, location (lat/lng, neighborhood)
- Current rating, total review count
- Rating/review count delta since last pull (computed)
- Price level, hours, attributes (outdoor seating, delivery, etc.)
- New review snippets where available via API

**Technical notes:**
- Yelp Fusion API gives up to 50 results per search, 5000 calls/day on free tier
- Google Places API is pay-per-call — budget accordingly
- Primary signal is **review velocity** (rate of new reviews) and **rating trajectory**, not individual review text
- Focus on restaurant, retail, nightlife, and service categories initially
- Track openings and closures by watching businesses appear/disappear between pulls

### 3c. TikTok / Instagram (Deferred)

**Status:** Deferred — no reliable public API for local content discovery.

**Potential approaches for later:**
- Track specific known accounts (local food bloggers, neighborhood pages)
- Use trend aggregator services if they emerge
- Manual curation of a watchlist of Chicago-relevant creators

---

## 4. Public Data (Chicago Data Portal & Government APIs)

### 4a. Transit

**Sources:**
- CTA ridership data (data.cityofchicago.org, Socrata API)
- CTA bus and rail station entries (daily totals)
- Divvy bikeshare trip data (monthly dumps)
- Metra ridership reports (quarterly)

**Cadence:** Daily (ridership), weekly (Divvy), quarterly (Metra)

**What we collect:**
- Station/stop-level ridership counts by day
- Route-level totals
- Divvy station trip starts/ends (proxy for foot traffic patterns)

### 4b. Crime & Safety

**Sources:**
- Chicago Police Department CLEAR data (data.cityofchicago.org)
- CPD community area crime stats

**Cadence:** Daily

**What we collect:**
- Incident type, date, location (lat/lng, block, community area)
- Arrest made (boolean)
- Aggregated counts by neighborhood and category over time windows

### 4c. Permits & Licensing

**Sources:**
- Business license applications and renewals (data.cityofchicago.org)
- Building permits (new construction, renovation, demolition)
- Liquor license applications
- Sidewalk cafe permits
- Food establishment inspections

**Cadence:** Daily

**What we collect:**
- License/permit type, status, application date, approval date
- Business name, address, ward, community area
- For inspections: pass/fail, violation types

**Technical notes:**
- Permit filings are leading indicators — a spike in renovation permits in a neighborhood signals incoming change
- Liquor license applications directly relevant to restaurant/bar viability analysis
- Track license revocations and non-renewals as negative signals

### 4d. Demographics & Economic

**Sources:**
- U.S. Census Bureau ACS 5-year estimates (API)
- Census Bureau population estimates (annual)
- Bureau of Labor Statistics (local employment data)
- Cook County Assessor (property values, assessed valuations)
- CoStar or LoopNet (commercial lease listings — may require paid access)

**Cadence:** Monthly (employment), quarterly (property), annually (census)

**What we collect:**
- Population by community area, age distribution, income distribution
- Employment/unemployment rates
- Median property values, assessment changes
- Commercial vacancy rates, asking rents per neighborhood
- New commercial lease listings (location, size, asking price, type)

**Technical notes:**
- Census/ACS data is relatively static — ingest once, refresh on new releases
- Property and commercial data are strong signals for neighborhood trajectory
- BLS local data has significant lag (~2 months) — useful for trend confirmation, not leading indicators

---

## Priority Order for Implementation

| Priority | Source | Rationale |
|----------|--------|-----------|
| 1 | Reddit (3a) | Easiest API, richest unstructured signal, real-time pulse |
| 2 | Chicago Data Portal — permits & licensing (4c) | Structured, free, direct business relevance |
| 3 | Chicago Data Portal — transit & crime (4a, 4b) | Structured, free, complements permit data |
| 4 | Local News (1) | RSS is straightforward, good for event detection |
| 5 | Yelp/Google Reviews (3b) | Competitive landscape signal, API rate limits manageable |
| 6 | Local Politics (2) | Highest value but hardest — PDF parsing, domain knowledge |
| 7 | Demographics/Economic (4d) | Slow-moving, can backfill later |
| 8 | TikTok/Instagram (3c) | No viable API path currently |
