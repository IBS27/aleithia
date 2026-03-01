# Demo Polish Design — Evidence Attribution, Trends, City Graph

**Date:** 2026-02-28
**Goal:** Close three feature gaps before live demo walkthrough for judges.

## Feature 1: Evidence Attribution

**Effort:** Small (frontend only)
**Where:** InsightsCard.tsx

Each InsightsCard category row (Regulatory, Economic, Market, etc.) becomes expandable. Clicking a category reveals 3–5 source documents that drove its score.

### Data mapping (already in neighborhoodData):
- `food_inspections` → `neighborhoodData.inspections` → DBA name, result, date
- `building_permits` → `neighborhoodData.permits` → work type, address, status
- `business_licenses` → `neighborhoodData.licenses` → business name, license type
- `cctv` → `neighborhoodData.cctv.cameras` → camera ID, vehicle count (IDOT highway cameras)
- `transit` → `neighborhoodData.transit` → CTA stations nearby, daily riders, transit score
- `traffic` → `neighborhoodData.traffic` → congestion level, speed
- `news` → `neighborhoodData.news` → headline, source, date
- `reviews` → `neighborhoodData.reviews` → rating, business name

### UX:
- Click category row → expand to show evidence documents inline
- Each evidence row shows key fields from metadata
- "View all →" link calls `onTabChange(tabKey)` to switch to the relevant tab
- Props change: InsightsCard receives `neighborhoodData` + `onTabChange` callback

### Files to modify:
- `frontend/src/components/InsightsCard.tsx` — add expand/collapse per category, render evidence rows
- `frontend/src/components/Dashboard.tsx` — pass `neighborhoodData` and `setActiveTab` to InsightsCard

## Feature 2: Trend / Anomaly Detection

**Effort:** Medium
**Focus:** 24-hour trends with mock baseline data for demo

### Backend:
- New endpoint `GET /trends/{neighborhood}` in `web.py`
- Reads CCTV timeseries from `/data/processed/cctv/timeseries/` (existing 24h rolling window — IDOT highway cameras, vehicle-focused)
- Reads traffic history from `/data/raw/traffic/{date}/` (existing hourly snapshots)
- Computes trend direction: up / down / stable (compare last 6h vs prior 6h)
- Returns anomalies from existing `is_anomaly` + `severity` flags in traffic docs
- Response shape:
  ```json
  {
    "highway_traffic": { "trend": "up", "change_pct": 12, "current_avg": 85, "prior_avg": 76 },
    "congestion": { "trend": "stable", "change_pct": -2, "anomalies": [...] },
    "news_activity": { "trend": "down", "change_pct": -15 }
  }
  ```

### Mock baseline data:
- Seed representative 24-hour data for demo neighborhoods (Boystown, Loop, Pilsen)
- Store in `/data/processed/trends/baselines/{neighborhood}.json`
- Use real CCTV timeseries structure so it works with real data too

### Frontend:
- Trend arrows on StatCards in Overview tab (↑12%, ↓5%, — stable)
- Anomaly alert banner at top of Overview when active anomalies exist
- Color coding: green for up highway traffic, red for congestion anomalies

### Files to modify:
- `modal_app/web.py` — add `/trends/{neighborhood}` endpoint
- `frontend/src/components/Dashboard.tsx` — fetch trends, pass to StatCards + alert banner
- `frontend/src/components/Dashboard.tsx` (StatCard) — add optional trend arrow prop

## Feature 3: City Graph (Full NetworkX)

**Effort:** Large
**Where:** New `modal_app/graph.py` + Models tab

### Node types (from architecture.md):
1. `neighborhood` — 30 Chicago neighborhoods (from NEIGHBORHOOD_CENTROIDS)
2. `business_type` — from license data + user profiles
3. `regulation` — from federal_register + politics docs
4. `entity` — businesses/organizations from news + reviews
5. `politician` — from Legistar politics data

### Edge types:
1. `regulates(regulation → neighborhood)` — weight: mention frequency in docs
2. `affects(regulation → business_type)` — weight: keyword match score
3. `sentiment(entity → neighborhood)` — weight: sentiment score from enrichment
4. `competes_in(business_type → neighborhood)` — weight: license count density
5. `trending(trend_topic → neighborhood)` — weight: news/reddit mention rate

### Backend (`modal_app/graph.py`):
- `build_city_graph()` Modal function:
  1. Read enriched docs from volume (all sources)
  2. Extract entities: neighborhoods from `geo.neighborhood`, regulations from politics/federal titles, businesses from license/review metadata
  3. Build `networkx.MultiDiGraph`
  4. Compute edge weights from doc frequency + sentiment + permit counts
  5. Apply temporal decay: `weight * exp(-age_days / 7)` (7-day half-life)
  6. Serialize to `/data/processed/graph/city_graph.json`
- Run on-demand or daily cron

### API endpoints (in web.py):
- `GET /graph/neighborhood/{name}` — 1-hop subgraph around a neighborhood
- `GET /graph/path/{from_node}/{to_node}` — shortest weighted path
- `GET /graph/full` — full graph as node/edge JSON for D3

### Graph JSON format:
```json
{
  "nodes": [
    { "id": "nb:Boystown", "type": "neighborhood", "label": "Boystown", "size": 45 },
    { "id": "reg:food-safety-2024", "type": "regulation", "label": "Food Safety Act", "size": 20 }
  ],
  "edges": [
    { "source": "reg:food-safety-2024", "target": "nb:Boystown", "type": "regulates", "weight": 0.8 }
  ]
}
```

### Frontend:
- D3 force-directed graph in Models tab (new section: "Knowledge Graph")
- Nodes colored by type (neighborhood=blue, regulation=red, business=green, entity=amber)
- Edge thickness = weight
- Click node → show metadata panel
- Filter by node type checkboxes
- Highlight active neighborhood's subgraph

### Files to create:
- `modal_app/graph.py` — graph construction + serialization
- `frontend/src/components/CityGraph.tsx` — D3 force-directed visualization

### Files to modify:
- `modal_app/__init__.py` — import graph module
- `modal_app/volume.py` — add graph image if networkx needs special deps
- `modal_app/web.py` — add `/graph/neighborhood/`, `/graph/path/`, `/graph/full` endpoints
- `frontend/src/components/MLMonitor.tsx` — add Knowledge Graph section
- `frontend/src/api.ts` — add graph API functions

## Priority Order

1. **Evidence Attribution** — smallest effort, directly addresses Cognivi comparison gap
2. **Trend/Anomaly Detection** — medium effort, uses existing infrastructure
3. **City Graph** — largest effort, most impressive for judges

## Dependencies

- Evidence Attribution: none (pure frontend)
- Trends: needs CCTV ingester to have run + mock baseline seeding (note: CCTV = highway vehicle data, not street-level foot traffic)
- City Graph: needs enriched docs on volume (already deployed), networkx in Modal image
