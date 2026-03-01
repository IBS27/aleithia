# Demo Polish Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement three demo-polish features: (1) Evidence Attribution in InsightsCard, (2) 24-hour Trend/Anomaly Detection with mock baselines, (3) Full NetworkX City Graph with D3 visualization.

**Architecture:** Evidence Attribution is pure frontend — expand InsightsCard categories to show source documents. Trends adds a backend endpoint + mock baseline data + frontend trend arrows. City Graph adds a full NetworkX module, three API endpoints, and a D3 force-directed visualization in the Models tab.

**Tech Stack:** React 19 + TypeScript, Modal + FastAPI, NetworkX, D3.js (via react-force-graph or raw SVG)

---

## Task 1: Evidence Attribution — Add `onTabChange` prop to InsightsCard

**Files:**
- Modify: `frontend/src/components/InsightsCard.tsx`
- Modify: `frontend/src/components/Dashboard.tsx`

**Step 1: Add props and evidence data mapping**

In `InsightsCard.tsx`, update the `Props` interface and add an evidence mapping:

```typescript
// InsightsCard.tsx — update Props
interface Props {
  data: NeighborhoodData
  profile: UserProfile
  onTabChange?: (tab: string) => void
}
```

Add a constant mapping category IDs to their tab keys and evidence extraction functions:

```typescript
const CATEGORY_TAB_MAP: Record<string, string> = {
  regulatory: 'inspections',
  economic: 'permits',
  market: 'market',
  demographic: 'overview',
  safety: 'vision',
  community: 'community',
}
```

**Step 2: Add evidence rows to CategoryRow**

Update `CategoryRow` to accept `evidence` and `onViewAll` props, and render evidence documents when expanded:

```typescript
function CategoryRow({ cat, expanded, onToggle, evidence, onViewAll }: {
  cat: CategoryScore
  expanded: boolean
  onToggle: () => void
  evidence: Array<{ label: string; detail: string; date?: string }>
  onViewAll?: () => void
}) {
```

Inside the `{expanded && ...}` block, after the existing subMetrics and source line, add:

```tsx
{evidence.length > 0 && (
  <div className="mt-2 pt-2 border-t border-white/[0.04] space-y-1.5">
    <div className="text-[10px] font-mono uppercase tracking-wider text-white/20 mb-1">
      Source Documents
    </div>
    {evidence.slice(0, 5).map((ev, i) => (
      <div key={i} className="flex items-center gap-2 text-[11px]">
        <span className="text-white/10">&#9679;</span>
        <span className="text-white/40 flex-1 truncate">{ev.label}</span>
        <span className="text-white/15 font-mono text-[10px] shrink-0">{ev.detail}</span>
      </div>
    ))}
    {onViewAll && (
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); onViewAll() }}
        className="text-[10px] font-mono text-white/30 hover:text-white/60 transition-colors cursor-pointer mt-1"
      >
        View all &rarr;
      </button>
    )}
  </div>
)}
```

**Step 3: Build evidence arrays from neighborhoodData**

In `InsightsCard` component, add a `useMemo` that builds evidence per category:

```typescript
const evidenceMap = useMemo(() => {
  const map: Record<string, Array<{ label: string; detail: string; date?: string }>> = {}

  // Regulatory — food inspections
  map.regulatory = (data.inspections || []).slice(0, 5).map(i => ({
    label: i.metadata?.raw_record?.dba_name || i.title,
    detail: i.metadata?.raw_record?.results || 'Inspected',
    date: i.timestamp,
  }))

  // Economic — permits + licenses
  map.economic = [
    ...(data.permits || []).slice(0, 3).map(p => ({
      label: `${p.metadata?.raw_record?.work_type || 'Permit'} — ${p.metadata?.raw_record?.street_name || ''}`,
      detail: p.metadata?.raw_record?.permit_status || 'Active',
    })),
    ...(data.licenses || []).slice(0, 2).map(l => ({
      label: l.metadata?.raw_record?.doing_business_as_name || l.title,
      detail: l.metadata?.raw_record?.license_description || 'License',
    })),
  ]

  // Market — reviews
  map.market = (data.reviews || []).slice(0, 5).map(r => ({
    label: (r.metadata?.business_name as string) || r.title,
    detail: r.metadata?.rating ? `${r.metadata.rating}/5` : '',
  }))

  // Demographic — static
  map.demographic = data.demographics ? [{
    label: 'Census / ACS Data',
    detail: `${data.demographics.total_population?.toLocaleString() || '—'} residents`,
  }] : []

  // Traffic & Accessibility — IDOT highway cameras + traffic + CTA transit
  map.safety = [
    ...(data.cctv?.cameras || []).slice(0, 3).map(c => ({
      label: `IDOT Camera ${c.camera_id}`,
      detail: `${c.vehicles} vehicles (highway)`,
    })),
    ...(data.traffic || []).slice(0, 2).map(t => ({
      label: t.title || 'Traffic segment',
      detail: (t.metadata?.congestion_level as string) || '',
    })),
  ]

  // Community — news + reddit + tiktok
  map.community = [
    ...(data.news || []).slice(0, 3).map(n => ({
      label: n.title,
      detail: n.source,
    })),
    ...(data.reddit || []).slice(0, 2).map(r => ({
      label: r.title,
      detail: 'reddit',
    })),
  ]

  return map
}, [data])
```

**Step 4: Wire up CategoryRow with evidence and onViewAll**

In the render, update the `CategoryRow` usage:

```tsx
{insights.categories.map(cat => (
  <CategoryRow
    key={cat.id}
    cat={cat}
    expanded={expandedId === cat.id}
    onToggle={() => setExpandedId(expandedId === cat.id ? null : cat.id)}
    evidence={evidenceMap[cat.id] || []}
    onViewAll={onTabChange && CATEGORY_TAB_MAP[cat.id] ? () => onTabChange(CATEGORY_TAB_MAP[cat.id]) : undefined}
  />
))}
```

**Step 5: Pass onTabChange from Dashboard**

In `Dashboard.tsx`, update the InsightsCard usage:

```tsx
{neighborhoodData && (
  <InsightsCard data={neighborhoodData} profile={profile} onTabChange={(tab) => setActiveTab(tab as Tab)} />
)}
```

**Step 6: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 7: Commit**

```bash
git add frontend/src/components/InsightsCard.tsx frontend/src/components/Dashboard.tsx
git commit -m "feat: add evidence attribution to InsightsCard categories"
```

---

## Task 2: Trend Detection — Backend endpoint with mock baselines

**Files:**
- Modify: `modal_app/web.py` — add `/trends/{neighborhood}` endpoint
- Create: `data/processed/trends/baselines/Boystown.json` (mock data)
- Create: `data/processed/trends/baselines/Loop.json` (mock data)
- Create: `data/processed/trends/baselines/Pilsen.json` (mock data)

**Step 1: Create mock baseline data files**

Create three JSON files with 24-hour trend data. Each file has this structure:

`data/processed/trends/baselines/Boystown.json`:
```json
{
  "neighborhood": "Boystown",
  "hours": [
    {"hour": 0, "pedestrians": 2.1, "vehicles": 8.3, "congestion": 0.15},
    {"hour": 1, "pedestrians": 1.4, "vehicles": 5.1, "congestion": 0.10},
    {"hour": 2, "pedestrians": 0.8, "vehicles": 3.2, "congestion": 0.08},
    {"hour": 3, "pedestrians": 0.5, "vehicles": 2.1, "congestion": 0.05},
    {"hour": 4, "pedestrians": 0.6, "vehicles": 2.8, "congestion": 0.06},
    {"hour": 5, "pedestrians": 1.2, "vehicles": 5.5, "congestion": 0.12},
    {"hour": 6, "pedestrians": 3.5, "vehicles": 12.0, "congestion": 0.25},
    {"hour": 7, "pedestrians": 6.2, "vehicles": 18.5, "congestion": 0.40},
    {"hour": 8, "pedestrians": 8.8, "vehicles": 22.1, "congestion": 0.55},
    {"hour": 9, "pedestrians": 9.5, "vehicles": 20.3, "congestion": 0.50},
    {"hour": 10, "pedestrians": 10.2, "vehicles": 18.7, "congestion": 0.45},
    {"hour": 11, "pedestrians": 12.5, "vehicles": 19.2, "congestion": 0.48},
    {"hour": 12, "pedestrians": 14.8, "vehicles": 21.5, "congestion": 0.52},
    {"hour": 13, "pedestrians": 13.2, "vehicles": 20.8, "congestion": 0.50},
    {"hour": 14, "pedestrians": 11.5, "vehicles": 19.5, "congestion": 0.47},
    {"hour": 15, "pedestrians": 10.8, "vehicles": 20.2, "congestion": 0.49},
    {"hour": 16, "pedestrians": 12.3, "vehicles": 24.5, "congestion": 0.60},
    {"hour": 17, "pedestrians": 15.1, "vehicles": 28.3, "congestion": 0.72},
    {"hour": 18, "pedestrians": 16.5, "vehicles": 25.1, "congestion": 0.65},
    {"hour": 19, "pedestrians": 14.2, "vehicles": 20.8, "congestion": 0.52},
    {"hour": 20, "pedestrians": 11.8, "vehicles": 16.5, "congestion": 0.40},
    {"hour": 21, "pedestrians": 9.5, "vehicles": 13.2, "congestion": 0.32},
    {"hour": 22, "pedestrians": 6.8, "vehicles": 10.5, "congestion": 0.25},
    {"hour": 23, "pedestrians": 4.2, "vehicles": 9.1, "congestion": 0.20}
  ],
  "generated_at": "2026-02-28T00:00:00Z"
}
```

Loop.json — higher baseline (business district), Pilsen.json — moderate baseline. Same structure with different numbers.

**Step 2: Add `/trends/{neighborhood}` endpoint to web.py**

Add after the existing `/neighborhood/{name}` endpoint:

```python
@web_app.get("/trends/{neighborhood}")
async def get_trends(neighborhood: str):
    """24-hour trend analysis: compare last 6h vs prior 6h."""
    volume.reload()

    # Try to load baseline data
    baseline_path = Path(PROCESSED_DATA_PATH) / "trends" / "baselines" / f"{neighborhood}.json"
    if not baseline_path.exists():
        # Generate synthetic baseline from neighborhood name hash for neighborhoods without mock data
        import hashlib
        seed = int(hashlib.md5(neighborhood.encode()).hexdigest()[:8], 16)
        rng_base = (seed % 10) + 5  # 5-15 range for pedestrians
        baseline = {
            "hours": [
                {
                    "hour": h,
                    "pedestrians": round(rng_base * (0.3 + 0.7 * abs(12 - abs(h - 14)) / 12), 1),
                    "vehicles": round(rng_base * 1.8 * (0.2 + 0.8 * abs(12 - abs(h - 13)) / 12), 1),
                    "congestion": round(0.1 + 0.5 * abs(12 - abs(h - 14)) / 12, 2),
                }
                for h in range(24)
            ]
        }
    else:
        baseline = json.loads(baseline_path.read_text())

    hours = baseline["hours"]

    # Compute trend: compare last 6h (18-23) vs prior 6h (12-17)
    recent = hours[18:24]
    prior = hours[12:18]

    def avg_field(entries, field):
        vals = [e[field] for e in entries]
        return sum(vals) / len(vals) if vals else 0

    recent_peds = avg_field(recent, "pedestrians")
    prior_peds = avg_field(prior, "pedestrians")
    ped_change = round(((recent_peds - prior_peds) / max(prior_peds, 0.1)) * 100)

    recent_cong = avg_field(recent, "congestion")
    prior_cong = avg_field(prior, "congestion")
    cong_change = round(((recent_cong - prior_cong) / max(prior_cong, 0.01)) * 100)

    # News activity: count recent news docs
    news_dir = Path(RAW_DATA_PATH) / "news"
    news_count = 0
    if news_dir.exists():
        for f in news_dir.rglob("*.json"):
            try:
                doc = json.loads(f.read_text())
                geo = doc.get("geo", {})
                if geo.get("neighborhood", "").lower() == neighborhood.lower():
                    news_count += 1
            except Exception:
                continue
    news_trend = "up" if news_count > 5 else ("stable" if news_count > 2 else "down")

    # Load traffic anomalies from existing data
    anomalies = []
    traffic_dir = Path(RAW_DATA_PATH) / "traffic"
    if traffic_dir.exists():
        for date_dir in sorted(traffic_dir.iterdir(), reverse=True)[:1]:
            for f in date_dir.glob("*.json"):
                try:
                    doc = json.loads(f.read_text())
                    meta = doc.get("metadata", {})
                    if meta.get("is_anomaly") and doc.get("geo", {}).get("neighborhood", "").lower() == neighborhood.lower():
                        anomalies.append({
                            "type": meta.get("severity", "info"),
                            "description": meta.get("congestion_level", "anomaly detected"),
                            "road": doc.get("title", "Unknown road"),
                        })
                except Exception:
                    continue

    def trend_dir(change_pct):
        if change_pct > 5:
            return "up"
        elif change_pct < -5:
            return "down"
        return "stable"

    return {
        "highway_traffic": {
            "trend": trend_dir(ped_change),
            "change_pct": ped_change,
            "current_avg": round(recent_peds, 1),
            "prior_avg": round(prior_peds, 1),
        },
        "congestion": {
            "trend": trend_dir(cong_change),
            "change_pct": cong_change,
            "anomalies": anomalies[:5],
        },
        "news_activity": {
            "trend": news_trend,
            "change_pct": (news_count - 3) * 10,  # relative to baseline of ~3
        },
        "hours": hours,
    }
```

**Step 3: Verify backend**

Run: `cd /home/gt120/projects/hackillinois2026 && python -c "from modal_app.web import web_app; print('OK')"`
Expected: OK (no import errors)

**Step 4: Commit**

```bash
git add modal_app/web.py data/processed/trends/
git commit -m "feat: add /trends endpoint with 24h mock baselines"
```

---

## Task 3: Trend Detection — Frontend trend arrows and anomaly banner

**Files:**
- Modify: `frontend/src/api.ts` — add `fetchTrends` function
- Modify: `frontend/src/components/Dashboard.tsx` — fetch trends, add arrows to StatCards, add anomaly banner

**Step 1: Add trend types and API function**

In `frontend/src/api.ts`, add:

```typescript
export interface TrendData {
  highway_traffic: { trend: 'up' | 'down' | 'stable'; change_pct: number; current_avg: number; prior_avg: number }
  congestion: { trend: 'up' | 'down' | 'stable'; change_pct: number; anomalies: Array<{ type: string; description: string; road: string }> }
  news_activity: { trend: 'up' | 'down' | 'stable'; change_pct: number }
  hours: Array<{ hour: number; pedestrians: number; vehicles: number; congestion: number }>
}

export async function fetchTrends(neighborhood: string): Promise<TrendData> {
  return fetchJSON<TrendData>(`/trends/${encodeURIComponent(neighborhood)}`)
}
```

**Step 2: Add trend state and fetch in Dashboard**

In `Dashboard.tsx`, import `fetchTrends` and `TrendData`:

```typescript
import { api, fetchTrends, type TrendData } from '../api.ts'
```

Add state:

```typescript
const [trends, setTrends] = useState<TrendData | null>(null)
```

Fetch trends alongside neighborhood data in `refreshData`:

```typescript
const refreshData = async () => {
  try {
    const [nbData, srcData] = await Promise.all([
      api.neighborhood(profile.neighborhood, profile.business_type),
      api.sources(),
    ])
    setNeighborhoodData(nbData)
    setSources(srcData)
    setRiskScore(computeRiskScore(nbData, profile))
    setLoading(false)

    // Fetch trends (non-blocking)
    fetchTrends(profile.neighborhood).then(t => setTrends(t)).catch(() => {})
  } catch (err) {
    setError(err instanceof Error ? err.message : 'Failed to load data')
    setLoading(false)
  }
}
```

**Step 3: Add trend arrow to StatCard**

Update the existing `StatCard` function to accept an optional `trend` prop:

```typescript
function StatCard({ label, value, sub, severity, trend }: {
  label: string
  value: number | string
  sub?: string
  severity?: 'nominal' | 'high'
  trend?: { direction: 'up' | 'down' | 'stable'; pct: number } | null
}) {
```

Inside StatCard's render, after the value display, add:

```tsx
{trend && (
  <span className={`text-[10px] font-mono ml-1 ${
    trend.direction === 'up' ? 'text-emerald-400' :
    trend.direction === 'down' ? 'text-red-400' :
    'text-white/20'
  }`}>
    {trend.direction === 'up' ? '↑' : trend.direction === 'down' ? '↓' : '—'}
    {Math.abs(trend.pct)}%
  </span>
)}
```

**Step 4: Pass trend data to StatCards in Overview tab**

Where StatCards are rendered in the overview tab, add trend props:

```tsx
<StatCard
  label="Highway Traffic"
  value={neighborhoodData.cctv?.avg_vehicles ? `~${Math.round(neighborhoodData.cctv.avg_vehicles)}` : '—'}
  sub={neighborhoodData.cctv?.density || 'no data'}
  trend={trends ? { direction: trends.highway_traffic.trend, pct: trends.highway_traffic.change_pct } : null}
/>
```

Apply similar pattern to the traffic/congestion StatCard.

**Step 5: Add anomaly alert banner**

Before the overview tab content, add:

```tsx
{activeTab === 'overview' && trends?.congestion.anomalies && trends.congestion.anomalies.length > 0 && (
  <div className="border border-red-500/20 bg-red-500/[0.04] px-4 py-3 flex items-center gap-3">
    <span className="text-red-400 text-xs font-mono font-bold">ALERT</span>
    <span className="text-xs text-white/50">
      {trends.congestion.anomalies.length} traffic anomal{trends.congestion.anomalies.length === 1 ? 'y' : 'ies'} detected:
      {' '}{trends.congestion.anomalies.map(a => a.road).join(', ')}
    </span>
  </div>
)}
```

**Step 6: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 7: Commit**

```bash
git add frontend/src/api.ts frontend/src/components/Dashboard.tsx
git commit -m "feat: add trend arrows and anomaly alerts to overview"
```

---

## Task 4: City Graph — Backend NetworkX module

**Files:**
- Create: `modal_app/graph.py`
- Modify: `modal_app/__init__.py` — import graph module
- Modify: `modal_app/volume.py` — add graph_image with networkx

**Step 1: Add graph_image to volume.py**

In `volume.py`, add a new image after `data_image`:

```python
graph_image = (
    _base.pip_install("networkx==3.3", "pandas==2.2.0")
    .add_local_python_source("modal_app", copy=True)
)
```

**Step 2: Create `modal_app/graph.py`**

```python
"""City Knowledge Graph — NetworkX MultiDiGraph construction and serialization."""
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import modal

from modal_app.volume import app, volume, graph_image, VOLUME_MOUNT, RAW_DATA_PATH, PROCESSED_DATA_PATH
from modal_app.common import CHICAGO_NEIGHBORHOODS, NEIGHBORHOOD_CENTROIDS


GRAPH_OUTPUT_DIR = f"{PROCESSED_DATA_PATH}/graph"


@app.function(
    image=graph_image,
    volumes={VOLUME_MOUNT: volume},
    timeout=300,
)
def build_city_graph():
    """Build full city knowledge graph from enriched docs on volume."""
    import networkx as nx

    volume.reload()
    G = nx.MultiDiGraph()

    # ── 1. Neighborhood nodes ──
    for nb in CHICAGO_NEIGHBORHOODS:
        if nb in NEIGHBORHOOD_CENTROIDS:
            lat, lng = NEIGHBORHOOD_CENTROIDS[nb]
            G.add_node(f"nb:{nb}", type="neighborhood", label=nb, lat=lat, lng=lng, size=40)

    # ── 2. Scan enriched docs for entities ──
    enriched_dir = Path(PROCESSED_DATA_PATH) / "enriched"
    regulations = {}  # title -> {node_id, neighborhoods, count}
    entities = {}     # name -> {node_id, neighborhoods, sentiment_sum, count}
    business_types = {}  # type -> {node_id, neighborhoods: {nb: count}}

    if enriched_dir.exists():
        for f in enriched_dir.rglob("*.json"):
            try:
                doc = json.loads(f.read_text())
            except Exception:
                continue

            nb = doc.get("geo", {}).get("neighborhood", "")
            source = doc.get("source", "")
            title = doc.get("title", "")
            meta = doc.get("metadata", {})
            timestamp_str = doc.get("timestamp", "")

            # Age decay factor (7-day half-life)
            try:
                ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                age_days = (datetime.now(timezone.utc) - ts).total_seconds() / 86400
            except Exception:
                age_days = 30
            decay = math.exp(-age_days / 7)

            # Regulation nodes from politics + federal_register
            if source in ("politics", "federal_register") and title:
                reg_id = f"reg:{title[:50].replace(' ', '-').lower()}"
                if reg_id not in regulations:
                    regulations[reg_id] = {"label": title[:60], "neighborhoods": set(), "count": 0, "decay_sum": 0}
                regulations[reg_id]["count"] += 1
                regulations[reg_id]["decay_sum"] += decay
                if nb:
                    regulations[reg_id]["neighborhoods"].add(nb)

            # Entity nodes from reviews + news
            if source in ("news", "yelp", "google_places"):
                entity_name = meta.get("business_name") or meta.get("source_name") or ""
                if entity_name and len(entity_name) > 2:
                    ent_id = f"ent:{entity_name[:40].replace(' ', '-').lower()}"
                    if ent_id not in entities:
                        entities[ent_id] = {"label": entity_name[:40], "neighborhoods": set(), "sentiment_sum": 0, "count": 0}
                    entities[ent_id]["count"] += 1
                    sentiment = meta.get("sentiment_score", 0)
                    if isinstance(sentiment, (int, float)):
                        entities[ent_id]["sentiment_sum"] += sentiment * decay
                    if nb:
                        entities[ent_id]["neighborhoods"].add(nb)

            # Business type nodes from licenses
            if source == "public_data":
                biz_type = meta.get("raw_record", {}).get("license_description", "")
                if biz_type and len(biz_type) > 2:
                    bt_key = biz_type.strip().title()[:30]
                    bt_id = f"biz:{bt_key.replace(' ', '-').lower()}"
                    if bt_id not in business_types:
                        business_types[bt_id] = {"label": bt_key, "neighborhoods": {}}
                    if nb:
                        business_types[bt_id]["neighborhoods"][nb] = business_types[bt_id]["neighborhoods"].get(nb, 0) + 1

    # Also scan raw docs for neighborhoods without enriched data
    for source_dir_name in ("news", "politics", "federal_register"):
        source_dir = Path(RAW_DATA_PATH) / source_dir_name
        if not source_dir.exists():
            continue
        for f in sorted(source_dir.rglob("*.json"), reverse=True)[:100]:
            try:
                doc = json.loads(f.read_text())
            except Exception:
                continue
            nb = doc.get("geo", {}).get("neighborhood", "")
            source = doc.get("source", source_dir_name)
            title = doc.get("title", "")

            if source in ("politics", "federal_register") and title:
                reg_id = f"reg:{title[:50].replace(' ', '-').lower()}"
                if reg_id not in regulations:
                    regulations[reg_id] = {"label": title[:60], "neighborhoods": set(), "count": 0, "decay_sum": 0}
                regulations[reg_id]["count"] += 1
                if nb:
                    regulations[reg_id]["neighborhoods"].add(nb)

    # ── 3. Add entity/regulation/business_type nodes ──
    for reg_id, info in regulations.items():
        G.add_node(reg_id, type="regulation", label=info["label"], size=max(10, min(30, info["count"] * 3)))

    for ent_id, info in entities.items():
        if info["count"] >= 1:
            avg_sentiment = info["sentiment_sum"] / max(info["count"], 1)
            G.add_node(ent_id, type="entity", label=info["label"], sentiment=round(avg_sentiment, 2),
                       size=max(8, min(25, info["count"] * 2)))

    for bt_id, info in business_types.items():
        total = sum(info["neighborhoods"].values())
        if total >= 2:
            G.add_node(bt_id, type="business_type", label=info["label"], size=max(8, min(25, total)))

    # ── 4. Add edges ──
    for reg_id, info in regulations.items():
        for nb in info["neighborhoods"]:
            nb_id = f"nb:{nb}"
            if G.has_node(nb_id):
                weight = round(min(1.0, info["decay_sum"] / 5), 2)
                G.add_edge(reg_id, nb_id, type="regulates", weight=weight)

    for ent_id, info in entities.items():
        if ent_id not in G:
            continue
        for nb in info["neighborhoods"]:
            nb_id = f"nb:{nb}"
            if G.has_node(nb_id):
                weight = round(min(1.0, abs(info["sentiment_sum"]) / max(info["count"], 1)), 2)
                G.add_edge(ent_id, nb_id, type="sentiment", weight=max(0.1, weight))

    for bt_id, info in business_types.items():
        if bt_id not in G:
            continue
        for nb, count in info["neighborhoods"].items():
            nb_id = f"nb:{nb}"
            if G.has_node(nb_id):
                weight = round(min(1.0, count / 10), 2)
                G.add_edge(bt_id, nb_id, type="competes_in", weight=max(0.1, weight))

    # ── 5. Serialize to JSON ──
    output = {
        "nodes": [],
        "edges": [],
        "stats": {
            "total_nodes": G.number_of_nodes(),
            "total_edges": G.number_of_edges(),
            "neighborhoods": len([n for n, d in G.nodes(data=True) if d.get("type") == "neighborhood"]),
            "regulations": len([n for n, d in G.nodes(data=True) if d.get("type") == "regulation"]),
            "entities": len([n for n, d in G.nodes(data=True) if d.get("type") == "entity"]),
            "business_types": len([n for n, d in G.nodes(data=True) if d.get("type") == "business_type"]),
            "built_at": datetime.now(timezone.utc).isoformat(),
        },
    }

    for node_id, data in G.nodes(data=True):
        output["nodes"].append({"id": node_id, **{k: v for k, v in data.items()}})

    for u, v, data in G.edges(data=True):
        output["edges"].append({"source": u, "target": v, **{k: v2 for k, v2 in data.items()}})

    # Save to volume
    graph_dir = Path(GRAPH_OUTPUT_DIR)
    graph_dir.mkdir(parents=True, exist_ok=True)
    graph_path = graph_dir / "city_graph.json"
    graph_path.write_text(json.dumps(output))
    volume.commit()

    print(f"City graph built: {output['stats']}")
    return output["stats"]
```

**Step 3: Import graph module in `__init__.py`**

Add after the existing imports inside the `if not MODAL_IS_REMOTE` block:

```python
    from modal_app import graph  # noqa: F401
```

**Step 4: Verify**

Run: `cd /home/gt120/projects/hackillinois2026 && python -c "from modal_app.graph import build_city_graph; print('OK')"`
Expected: OK

**Step 5: Commit**

```bash
git add modal_app/graph.py modal_app/__init__.py modal_app/volume.py
git commit -m "feat: add NetworkX city graph builder"
```

---

## Task 5: City Graph — API endpoints in web.py

**Files:**
- Modify: `modal_app/web.py` — add 3 graph endpoints
- Modify: `modal_app/volume.py` — export `graph_image`

**Step 1: Add graph endpoints to web.py**

Add these three endpoints:

```python
def _load_city_graph() -> dict:
    """Load the pre-built city graph from volume."""
    volume.reload()
    graph_path = Path(PROCESSED_DATA_PATH) / "graph" / "city_graph.json"
    if not graph_path.exists():
        return {"nodes": [], "edges": [], "stats": {}}
    return json.loads(graph_path.read_text())


@web_app.get("/graph/full")
async def get_full_graph():
    """Full city graph as node/edge JSON for D3."""
    return _load_city_graph()


@web_app.get("/graph/neighborhood/{name}")
async def get_neighborhood_graph(name: str):
    """1-hop subgraph around a neighborhood node."""
    graph = _load_city_graph()
    nb_id = f"nb:{name}"

    # Find connected node IDs
    connected = {nb_id}
    for edge in graph["edges"]:
        if edge["source"] == nb_id or edge["target"] == nb_id:
            connected.add(edge["source"])
            connected.add(edge["target"])

    # Filter
    nodes = [n for n in graph["nodes"] if n["id"] in connected]
    edges = [e for e in graph["edges"] if e["source"] in connected and e["target"] in connected]

    return {"nodes": nodes, "edges": edges, "center": nb_id}


@web_app.get("/graph/stats")
async def get_graph_stats():
    """Graph statistics."""
    graph = _load_city_graph()
    return graph.get("stats", {})
```

**Step 2: Verify**

Run: `cd /home/gt120/projects/hackillinois2026 && python -c "from modal_app.web import web_app; print('OK')"`
Expected: OK

**Step 3: Commit**

```bash
git add modal_app/web.py
git commit -m "feat: add graph API endpoints (full, neighborhood, stats)"
```

---

## Task 6: City Graph — Frontend API + D3 Visualization

**Files:**
- Modify: `frontend/src/api.ts` — add graph API functions
- Create: `frontend/src/components/CityGraph.tsx` — D3 force-directed graph

**Step 1: Add graph API functions to api.ts**

```typescript
export interface GraphNode {
  id: string
  type: 'neighborhood' | 'regulation' | 'entity' | 'business_type'
  label: string
  size: number
  lat?: number
  lng?: number
  sentiment?: number
}

export interface GraphEdge {
  source: string
  target: string
  type: 'regulates' | 'sentiment' | 'competes_in' | 'affects' | 'trending'
  weight: number
}

export interface CityGraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
  stats?: {
    total_nodes: number
    total_edges: number
    neighborhoods: number
    regulations: number
    entities: number
    business_types: number
    built_at: string
  }
  center?: string
}

export async function fetchCityGraph(): Promise<CityGraphData> {
  return fetchJSON<CityGraphData>('/graph/full')
}

export async function fetchNeighborhoodGraph(neighborhood: string): Promise<CityGraphData> {
  return fetchJSON<CityGraphData>(`/graph/neighborhood/${encodeURIComponent(neighborhood)}`)
}

export async function fetchGraphStats(): Promise<Record<string, unknown>> {
  return fetchJSON<Record<string, unknown>>('/graph/stats')
}
```

**Step 2: Create CityGraph.tsx**

Create `frontend/src/components/CityGraph.tsx`:

```tsx
import { useState, useEffect, useRef, useCallback } from 'react'
import { fetchCityGraph, fetchNeighborhoodGraph, type CityGraphData, type GraphNode } from '../api.ts'

const NODE_COLORS: Record<string, string> = {
  neighborhood: '#3b82f6',   // blue
  regulation: '#ef4444',     // red
  entity: '#f59e0b',         // amber
  business_type: '#22c55e',  // green
}

interface Props {
  activeNeighborhood?: string
}

export default function CityGraph({ activeNeighborhood }: Props) {
  const [graphData, setGraphData] = useState<CityGraphData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<'neighborhood' | 'full'>('neighborhood')
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [filters, setFilters] = useState<Record<string, boolean>>({
    neighborhood: true,
    regulation: true,
    entity: true,
    business_type: true,
  })
  const svgRef = useRef<SVGSVGElement>(null)
  const simulationRef = useRef<ReturnType<typeof createSimulation> | null>(null)

  const loadGraph = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = viewMode === 'neighborhood' && activeNeighborhood
        ? await fetchNeighborhoodGraph(activeNeighborhood)
        : await fetchCityGraph()
      setGraphData(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load graph')
    } finally {
      setLoading(false)
    }
  }, [viewMode, activeNeighborhood])

  useEffect(() => { loadGraph() }, [loadGraph])

  // Simple force simulation (no D3 dependency — pure math)
  function createSimulation(nodes: GraphNode[], edges: { source: string; target: string; weight: number }[], width: number, height: number) {
    const positions = new Map<string, { x: number; y: number; vx: number; vy: number }>()

    // Initialize positions
    nodes.forEach((n, i) => {
      const angle = (2 * Math.PI * i) / nodes.length
      const r = Math.min(width, height) * 0.35
      positions.set(n.id, {
        x: width / 2 + r * Math.cos(angle) + (Math.random() - 0.5) * 50,
        y: height / 2 + r * Math.sin(angle) + (Math.random() - 0.5) * 50,
        vx: 0, vy: 0,
      })
    })

    const nodeMap = new Map(nodes.map(n => [n.id, n]))

    function tick() {
      const alpha = 0.3
      const repulsion = 800
      const attraction = 0.005

      // Repulsion between all nodes
      const nodeList = Array.from(positions.entries())
      for (let i = 0; i < nodeList.length; i++) {
        for (let j = i + 1; j < nodeList.length; j++) {
          const [, a] = nodeList[i]
          const [, b] = nodeList[j]
          const dx = b.x - a.x
          const dy = b.y - a.y
          const dist = Math.max(1, Math.sqrt(dx * dx + dy * dy))
          const force = repulsion / (dist * dist)
          const fx = (dx / dist) * force
          const fy = (dy / dist) * force
          a.vx -= fx * alpha
          a.vy -= fy * alpha
          b.vx += fx * alpha
          b.vy += fy * alpha
        }
      }

      // Attraction along edges
      for (const edge of edges) {
        const a = positions.get(edge.source)
        const b = positions.get(edge.target)
        if (!a || !b) continue
        const dx = b.x - a.x
        const dy = b.y - a.y
        const force = attraction * edge.weight
        a.vx += dx * force
        a.vy += dy * force
        b.vx -= dx * force
        b.vy -= dy * force
      }

      // Center gravity
      for (const [, pos] of positions) {
        pos.vx += (width / 2 - pos.x) * 0.01
        pos.vy += (height / 2 - pos.y) * 0.01
      }

      // Apply velocity with damping
      for (const [, pos] of positions) {
        pos.vx *= 0.6
        pos.vy *= 0.6
        pos.x += pos.vx
        pos.y += pos.vy
        // Clamp to bounds
        pos.x = Math.max(30, Math.min(width - 30, pos.x))
        pos.y = Math.max(30, Math.min(height - 30, pos.y))
      }
    }

    return { positions, tick, nodeMap }
  }

  // Run simulation and render
  useEffect(() => {
    if (!graphData || !svgRef.current) return

    const svg = svgRef.current
    const width = svg.clientWidth || 800
    const height = svg.clientHeight || 500

    const filteredNodes = graphData.nodes.filter(n => filters[n.type])
    const filteredNodeIds = new Set(filteredNodes.map(n => n.id))
    const filteredEdges = graphData.edges.filter(e =>
      filteredNodeIds.has(e.source) && filteredNodeIds.has(e.target)
    )

    const sim = createSimulation(filteredNodes, filteredEdges, width, height)
    simulationRef.current = sim

    // Run 80 iterations
    for (let i = 0; i < 80; i++) sim.tick()

    // Render to SVG
    while (svg.firstChild) svg.removeChild(svg.firstChild)

    // Edges
    for (const edge of filteredEdges) {
      const a = sim.positions.get(edge.source)
      const b = sim.positions.get(edge.target)
      if (!a || !b) continue
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line')
      line.setAttribute('x1', String(a.x))
      line.setAttribute('y1', String(a.y))
      line.setAttribute('x2', String(b.x))
      line.setAttribute('y2', String(b.y))
      line.setAttribute('stroke', 'rgba(255,255,255,0.08)')
      line.setAttribute('stroke-width', String(Math.max(0.5, edge.weight * 2)))
      svg.appendChild(line)
    }

    // Nodes
    for (const node of filteredNodes) {
      const pos = sim.positions.get(node.id)
      if (!pos) continue

      const g = document.createElementNS('http://www.w3.org/2000/svg', 'g')
      g.setAttribute('transform', `translate(${pos.x},${pos.y})`)
      g.style.cursor = 'pointer'
      g.addEventListener('click', () => setSelectedNode(node))

      const isActive = activeNeighborhood && node.id === `nb:${activeNeighborhood}`
      const radius = Math.max(4, (node.size || 10) / 4)

      const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle')
      circle.setAttribute('r', String(radius))
      circle.setAttribute('fill', NODE_COLORS[node.type] || '#666')
      circle.setAttribute('opacity', isActive ? '1' : '0.7')
      if (isActive) {
        circle.setAttribute('stroke', '#fff')
        circle.setAttribute('stroke-width', '2')
      }
      g.appendChild(circle)

      // Label for larger nodes
      if (node.size >= 20 || node.type === 'neighborhood') {
        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text')
        text.textContent = node.label.length > 15 ? node.label.slice(0, 15) + '…' : node.label
        text.setAttribute('x', String(radius + 4))
        text.setAttribute('y', '3')
        text.setAttribute('fill', 'rgba(255,255,255,0.4)')
        text.setAttribute('font-size', '9')
        text.setAttribute('font-family', 'monospace')
        g.appendChild(text)
      }

      svg.appendChild(g)
    }
  }, [graphData, filters, activeNeighborhood])

  return (
    <div className="border border-white/[0.06] bg-white/[0.01]">
      <div className="px-4 py-3 border-b border-white/[0.06] flex items-center justify-between">
        <h3 className="text-[10px] font-mono uppercase tracking-wider text-white/40">Knowledge Graph</h3>
        <div className="flex items-center gap-3">
          {/* View toggle */}
          <div className="flex gap-0 border border-white/[0.08] rounded overflow-hidden">
            {(['neighborhood', 'full'] as const).map(mode => (
              <button
                key={mode}
                type="button"
                onClick={() => setViewMode(mode)}
                className={`px-3 py-1 text-[10px] font-mono uppercase tracking-wider transition-colors cursor-pointer ${
                  viewMode === mode
                    ? 'bg-white/[0.06] text-white'
                    : 'text-white/30 hover:text-white/50'
                }`}
              >
                {mode === 'neighborhood' ? '1-Hop' : 'Full'}
              </button>
            ))}
          </div>
          {/* Stats */}
          {graphData?.stats && (
            <span className="text-[10px] font-mono text-white/20">
              {graphData.stats.total_nodes} nodes · {graphData.stats.total_edges} edges
            </span>
          )}
        </div>
      </div>

      {/* Filter checkboxes */}
      <div className="px-4 py-2 border-b border-white/[0.04] flex items-center gap-4">
        {Object.entries(NODE_COLORS).map(([type, color]) => (
          <label key={type} className="flex items-center gap-1.5 cursor-pointer">
            <input
              type="checkbox"
              checked={filters[type] ?? true}
              onChange={e => setFilters(prev => ({ ...prev, [type]: e.target.checked }))}
              className="sr-only"
            />
            <span
              className="w-2 h-2 rounded-full"
              style={{ backgroundColor: color, opacity: filters[type] ? 1 : 0.2 }}
            />
            <span className={`text-[10px] font-mono ${filters[type] ? 'text-white/40' : 'text-white/15'}`}>
              {type.replace('_', ' ')}
            </span>
          </label>
        ))}
      </div>

      {/* Graph canvas */}
      <div className="relative" style={{ height: 500 }}>
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="w-5 h-5 border border-white/20 border-t-white/60 rounded-full animate-spin" />
          </div>
        )}
        {error && (
          <div className="absolute inset-0 flex items-center justify-center text-xs text-red-400/60 font-mono">
            {error}
          </div>
        )}
        {!loading && graphData && graphData.nodes.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center text-xs text-white/20 font-mono">
            No graph data — run <code className="text-white/30">modal run -m modal_app.graph::build_city_graph</code>
          </div>
        )}
        <svg ref={svgRef} width="100%" height="100%" className="bg-transparent" />
      </div>

      {/* Selected node panel */}
      {selectedNode && (
        <div className="px-4 py-3 border-t border-white/[0.06] bg-white/[0.02]">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span
                className="w-2.5 h-2.5 rounded-full"
                style={{ backgroundColor: NODE_COLORS[selectedNode.type] }}
              />
              <span className="text-xs font-medium text-white/70">{selectedNode.label}</span>
              <span className="text-[10px] font-mono text-white/20 border border-white/[0.08] px-1.5 py-0.5">
                {selectedNode.type.replace('_', ' ')}
              </span>
            </div>
            <button
              type="button"
              onClick={() => setSelectedNode(null)}
              className="text-white/20 hover:text-white/50 text-xs cursor-pointer"
            >
              ✕
            </button>
          </div>
          <div className="mt-2 grid grid-cols-3 gap-4 text-[10px] font-mono">
            <div>
              <span className="text-white/20">ID</span>
              <div className="text-white/40 mt-0.5">{selectedNode.id}</div>
            </div>
            <div>
              <span className="text-white/20">Size</span>
              <div className="text-white/40 mt-0.5">{selectedNode.size}</div>
            </div>
            {selectedNode.sentiment !== undefined && (
              <div>
                <span className="text-white/20">Sentiment</span>
                <div className={`mt-0.5 ${selectedNode.sentiment > 0 ? 'text-emerald-400/60' : selectedNode.sentiment < 0 ? 'text-red-400/60' : 'text-white/40'}`}>
                  {selectedNode.sentiment.toFixed(2)}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
```

**Step 3: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 4: Commit**

```bash
git add frontend/src/api.ts frontend/src/components/CityGraph.tsx
git commit -m "feat: add CityGraph D3 visualization component"
```

---

## Task 7: City Graph — Integrate into Models tab

**Files:**
- Modify: `frontend/src/components/MLMonitor.tsx` — add CityGraph import and section
- OR Modify: `frontend/src/components/Dashboard.tsx` — add CityGraph to models tab render

**Step 1: Add CityGraph to Dashboard.tsx models tab**

The cleanest approach is adding CityGraph directly in Dashboard.tsx where the models tab is rendered. Import CityGraph:

```typescript
import CityGraph from './CityGraph.tsx'
```

In the models tab render block, add the CityGraph component above or below the MLMonitor:

```tsx
{activeTab === 'models' && (
  <div className="space-y-4">
    <CityGraph activeNeighborhood={profile.neighborhood} />
    <MLMonitor />
  </div>
)}
```

**Step 2: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 3: Commit**

```bash
git add frontend/src/components/Dashboard.tsx
git commit -m "feat: integrate CityGraph into Models tab"
```

---

## Verification Checklist

After all tasks complete:

1. `cd frontend && npx tsc --noEmit` — 0 errors
2. InsightsCard categories expand to show source documents with "View all →" links
3. Overview tab shows trend arrows (↑/↓/—) on relevant StatCards
4. Anomaly alert banner appears when traffic anomalies exist
5. Models tab shows Knowledge Graph with force-directed layout
6. Graph has node type filters, 1-hop/full toggle, and click-to-select
7. `modal run -m modal_app.graph::build_city_graph` builds the graph from volume data
8. `/trends/{neighborhood}` endpoint returns trend data with mock baselines
