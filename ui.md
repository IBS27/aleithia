# Aleithia Analysis Dashboard — UI/UX Redesign Brief

This is a briefing doc for coding agents assigned to redesign the Analysis Dashboard (`/analysis` route). The goal is to produce the best possible UI/UX for the data Aleithia already surfaces for a chosen neighborhood + business type (example: Coffee Shop / Loop), without changing how data is fetched or shaped.

## Scope and hard constraints

**In scope (frontend-only):**
- Anything under `frontend/src/components/**` that the Dashboard composes.
- `frontend/src/components/Dashboard.tsx` layout, routing of sub-tabs, and any presentational helpers it owns.
- Purely presentational utilities in `frontend/src/insights.ts` (composition / category grouping / ordering) as long as the category ids remain compatible with callers.
- `frontend/src/App.css` / `index.css` / Tailwind classes and local CSS files (e.g. `Squares.css`).

**Out of scope (do not touch):**
- `frontend/src/api.ts` fetch endpoints, request/response shapes, auth header, timeouts.
- `frontend/src/types/index.ts` type definitions (they mirror the backend contract).
- Any file under `backend/**` or `modal_app/**`.
- Which data sources power which tab. If a field is missing today (e.g. `data.cctv` is null on some neighborhoods), the redesign must still handle that case gracefully.
- URL structure (`/analysis`, `/profile`, `/start`, `/how-it-works`, `/why-us`, `/memory-graph`, `/lead-analyst`). You can change in-page tab state, but not routes.
- Onboarding / landing pages, unless the task explicitly asks.

**Explicit "do not regress" items:**
1. Every data field currently visible in the Dashboard must remain visible somewhere in the redesign (it can be grouped, collapsed, or progressively disclosed — not deleted).
2. Drag-to-resize between main content and right-hand intelligence brief must still work on desktop widths ≥ 1280 px.
3. The Overview map (heatmap + layer tabs) must retain Regulatory Activity / Commercial Activity / Public Sentiment layers.
4. The CCTV grid must still open a per-camera drawer on click (`CCTVCameraDrawer`), including the GPT-4V structured output block and OTel pipeline trace mock.
5. The `x-user-id` header and history-saving side effects driven by `App.tsx` must not break.

---

## Current architecture (read-only reference)

### Entry point

`Dashboard.tsx` is the shell. It:
1. Calls `api.neighborhood(neighborhood, businessType)` once on mount for the big `NeighborhoodData` payload.
2. Calls `api.sources()` for the header chip list (retries every 5 s until `metadata_ready`).
3. Calls `fetchTrends(neighborhood)` for congestion anomalies and the 24 h bar pattern.
4. Computes a local `RiskScore` via the inline `computeRiskScore()` function (WLC, 0–10 scale).
5. Renders `LocationReportPanel` in a resizable right sidebar (`sidebarWidth`, min 360 / default 540 / max 720).
6. Switches main content between six tabs: `overview | regulatory | intel | community | market | vision`.

### Tab content today

| Tab | Component(s) | Core data consumed |
|---|---|---|
| Overview | `MapView`, `RiskCard`, `InsightsCard`, `DemographicsCard` (horizontal) | `NeighborhoodData.metrics`, `demographics`, `insights.ts::computeInsights()`, local `RiskScore` |
| Regulatory | `RegulatorySubTabs` → `InspectionTable` / `PermitTable` / `LicenseTable` | `inspections`, `permits`, `licenses` + `inspection_stats` |
| News & Policy | `NewsFeed` | `news[]`, `politics[]` (Document shape) |
| Community | `CommunityFeed` | `reddit[]`, `tiktok[]` |
| Market | `MarketPanel` | `reviews[]`, `realestate[]` |
| Vision | `StreetscapeCard` + (optional) Parking block + Detection Summary + `FootTrafficChart` + CCTV camera grid | `cctv`, `parking`, streetscape (`api.streetscape`), CCTV timeseries (`api.cctvTimeseries`), optional AI assess |

### Sidebar ("Intelligence Brief")

`LocationReportPanel.tsx` renders, top-to-bottom:
1. Score (0–100 from `computeInsights`) + Strongest Signal + Primary Risk verdict card.
2. Advantages (≤5) — green cards.
3. Risks (≤5) — amber cards.
4. Social Media Trends (cyan cards; uses `api.socialTrends`).
5. Competitive Landscape (bulleted, uses `data.licenses` filtered by `LICENSE_MAP[business_type]`).
6. Regulatory Checklist (inspections pass rate, permits by type, federal register alerts).
7. Key Metrics grid (8 tiles).
8. "N documents analyzed across M sources" footer.

### Shared chrome

- Header: logo → `onReset`, breadcrumb `BusinessType / Neighborhood`, `Timer`, Refresh / Profile / New Search text links.
- Pipeline Monitor strip (`PipelineMonitor`) — shows doc count + enriched count + GPU dot indicators.
- Data source chips (`DataSourceBadge`) — one per active source.
- Both appear above the tab row, always.

---

## What's wrong today (observed on Coffee Shop / Loop)

1. **Three overlapping scores.** Top-center shows `4.5/10 RISK SCORE` (RiskCard). Directly under it: `58 / 100 Overall Opportunity` (InsightsCard). The sidebar repeats `58 Business Intelligence Score`. Users don't know which number is "the answer".
2. **Overview duplicates the sidebar.** Advantages, Risks, Verdict, and Key Metrics render twice — once in the inline InsightsCard / DemographicsCard, once in the sidebar `LocationReportPanel`.
3. **Raw HTML leaks into news cards.** `NewsFeed` renders the first 200 chars of `article.content`. For RSS items that contain `<figure><img …>` markup, those tags show up in the UI. Same issue on Reddit bodies in some cases.
4. **Map zoom is wrong for the selected neighborhood.** Even with `activeNeighborhood="Loop"`, the heatmap stays city-wide because the `flyTo` only fires if Loop appears in the geo features. The user expects the map to focus on their target.
5. **Vision tab leads with cold data.** The hero is "Highway Camera Detections" from IDOT expressway cameras — frequently `NO SIGNAL` tiles. The more decision-useful Streetscape / AI Assessment / Parking blocks are hidden or behind a button.
6. **Market tab repeats the same 3 businesses 5×.** The data contains duplicates but the UI does not dedupe.
7. **Competitive Landscape is noisy.** It lists any license regardless of type, so "IMC Americas", "Johnson Consulting", "Kassells Decorating" appear for a coffee-shop query.
8. **Regulatory "Inspections" shows "No food inspection data available" even though the tab badge says `26`.** The count aggregates inspections + permits + licenses, but the default sub-tab is Inspections which is empty. First impression is broken-looking.
9. **Typography sprawl.** `text-[8px]`, `text-[9px]`, `text-[10px]`, `text-[11px]`, `text-xs`, `text-sm`, `text-lg`, `text-xl`, `text-2xl`, `text-3xl`, `text-4xl` are all used within the Dashboard. There is no type scale.
10. **Colour semantics are unreliable.** Green/amber/red is used for risk, for opportunity (inverted), for permit status, for CCTV density, and for news/reddit/tiktok source badges. Users get no consistent signal.
11. **Sidebar fights the map for horizontal space.** Default is 540 px sidebar on a ~1460 px screen, leaving the map + insights column ~900 px — both end up cramped.
12. **Long initial load (45–60 s) has no progress information.** Just a spinner + "ANALYZING LOOP". The `LoadingFlow` component is not telling the user what's happening or how much longer.
13. **Refresh / Profile / New Search look like body text, not controls.** Low affordance in a high-density screen.
14. **Demographic tiles are a dumb flat strip.** Rent vs Income are the most load-bearing numbers for the score, but they're displayed identically to "Age" and "Renters %".
15. **No easy way to compare neighborhoods.** The whole dashboard is single-location. Every user I watched wants to answer "is Loop better than West Loop?"

---

## Design goals

In priority order:

1. **One score, many lenses.** Decide on a single top-line number (recommend the 0–100 `insights.overall` from `insights.ts`) and demote the 0–10 risk number to a secondary / legacy display or remove it. The sidebar and main area must agree on this number.
2. **Answer first, evidence second.** The viewport on initial load should show: score + 1-line verdict + top 3 advantages + top 3 risks. Everything else is progressive disclosure.
3. **Category-as-navigation.** Replace today's six tabs (Overview / Regulatory / News & Policy / Community / Market / Vision) with the six scoring categories from `insights.ts` (Regulatory / Development Activity / Market / Demographic / Traffic & Accessibility / Community). Each category page deep-dives into its own evidence — inspections live under Regulatory, reviews + real estate under Market, reddit/tiktok under Community, CCTV + parking + streetscape under Traffic & Accessibility, etc. The existing `allTabs`/`tabs` state can simply be renamed and re-routed.
4. **Sidebar becomes a persistent summary, not a second dashboard.** Keep score + verdict + "jump to evidence" links. Move Advantages / Risks / Social Trends / Competitive Landscape inline under the relevant category (Advantages → Overview, Social Trends → Community, Competitive Landscape → Market, etc.).
5. **Establish a type scale and a colour system.** See "Design system" below. Delete one-off pixel sizes.
6. **Sanitise every rendered document preview.** No raw HTML, no escaped entities, no "[Transcript]" prefix bleeding through.
7. **Make every empty state honest.** "No inspection data for this neighborhood" should say *why* (e.g. "Chicago's food-inspection dataset tracks restaurants only — Loop has 0 coffee-shop-category inspections") and offer a sensible next action.

Non-goals / explicitly rejected approaches:

- **Do not add a chat/ask-anything box.** There is already `LeadAnalystPage` on a separate route.
- **Do not add charts for the sake of charts.** Every visualisation must answer a concrete question the user is likely to ask.
- **Do not introduce a new CSS framework or component library.** Stay on Tailwind + existing components unless a specific control is unavoidable (and then motivate it in the PR description).

---

## Design system

### Type scale

Use exactly these and nothing else:

| Role | Tailwind | Example |
|---|---|---|
| Display | `text-4xl font-semibold tracking-tight` | Top-level score |
| Heading 1 | `text-2xl font-semibold` | Category hero |
| Heading 2 | `text-lg font-medium` | Section title |
| Body | `text-sm` | Card copy, metric labels |
| Caption | `text-xs text-white/50` | Tertiary meta |
| Mono label | `text-[11px] font-mono uppercase tracking-wider text-white/40` | Eyebrows / source tags |

Avoid everything below 11 px. Avoid `tracking-widest` unless the string is ≤ 3 words.

### Colour semantics

One rule: colour only conveys signal direction. Do not colour-code categories or sources.

| Signal | Foreground | Background/border |
|---|---|---|
| Positive / favourable | `text-emerald-300` | `bg-emerald-500/10 border-emerald-500/20` |
| Neutral | `text-amber-300` | `bg-amber-500/10 border-amber-500/20` |
| Negative / concerning | `text-rose-300` | `bg-rose-500/10 border-rose-500/20` |
| Info / inert | `text-white/70` | `bg-white/5 border-white/10` |

Source tags (reddit, tiktok, news, politics) should render with the same inert chip style (`bg-white/5 border-white/10 text-white/60`) with just the label. Any additional colour is reserved for signal.

### Spacing and density

- Baseline grid: 4 px. Default vertical rhythm between sections: 24 px (`gap-6`).
- Card padding: `p-5` for hero cards, `p-4` for list items, `p-3` for dense tables.
- Maximum content width inside the main column: 1100 px. Beyond that, pad equally.

### Motion

- Use framer-motion's `fade + translateY(4px)` for entering cards. 180 ms, ease-out.
- Avoid looping background animations (the `Squares` grid and radial gradients on the onboarding screen are OK there; do **not** bring them into Dashboard).

---

## Proposed information architecture

```
┌───────────────────────────────────────────────────────────────────────┐
│ Header: logo · BusinessType / Neighborhood · [New Search] [Profile]  │
├───────────────────────────────────────────────────────────────────────┤
│ Hero strip (always visible, collapses to a thin bar on scroll):       │
│   ┌─────────────┐ ┌──────────────────────────────────────────────┐    │
│   │ SCORE 58/100│ │ "Mixed signals for a Coffee Shop in the Loop"│    │
│   │ conservative│ │ Strongest: Community 89 · Risk: Dev Act 34   │    │
│   │ ● ● ● ● ●   │ │ [Conservative] [Growth] [Budget] profile tabs│    │
│   └─────────────┘ └──────────────────────────────────────────────┘    │
├────────────────── Category nav (sticky) ──────────────────────────────┤
│  Snapshot · Regulatory · Development · Market · Demographic · Traffic │
│  · Community                                                          │
├──────────────────────────────────────────────┬────────────────────────┤
│  MAIN CONTENT PANE                           │  EVIDENCE SIDEBAR       │
│  (swap per active category)                  │  (resizable, 320–560px) │
│                                              │                         │
│                                              │  - Top 3 advantages     │
│                                              │  - Top 3 risks          │
│                                              │  - Jump-to-evidence     │
│                                              │  - Data footer          │
└──────────────────────────────────────────────┴────────────────────────┘
```

### Active category → content

- **Snapshot (default landing):** Map (wider than today, sized to the selected neighborhood), category score strip (six compact rows), advantages/risks teaser, social trends teaser, source inventory.
- **Regulatory:** Inspection pass-rate KPI + stacked-bar by result + violation themes. Permits by type + fee heatmap. Federal register alerts. Licenses searchable table. This absorbs the current `RegulatorySubTabs`.
- **Development:** Permit timeline (use `issue_date` on permits), investment ($ fees), new-build ratio, recent projects list.
- **Market:** Yelp-style score + velocity badge, deduped review list, commercial listings in a 2-column card grid with price/sqft, **filtered** competitive landscape (only direct competitors from `LICENSE_MAP[business_type]`).
- **Demographic:** Big readable tiles for rent/income/age/unemployment/education, rent-burden bar, comparison to Chicago citywide averages (static constants are fine — no new endpoints).
- **Traffic & Accessibility:** Streetscape hero first, AI assessment inline (auto-fire request on tab open), 24h foot-traffic chart, parking block if present, CCTV camera grid last (it's the least decision-useful for most users).
- **Community:** Social trends cards on top, news feed, city council items, reddit posts, tiktok videos — each in its own collapsible section.

### Sidebar content

Keep it narrow and fixed-structure. No more than five items, total height ≤ viewport:
1. Score + verdict (sticky on scroll).
2. Advantages (top 3, green).
3. Risks (top 3, amber/rose).
4. "Jump to evidence" chip rail — clicking jumps the main pane to the relevant category.
5. Data footer: `89 documents · 9 sources · fetched <timestamp>`.

Move Competitive Landscape → Market tab. Move Regulatory Checklist → Regulatory tab. Move Key Metrics grid → Demographic tab (or inline in hero).

---

## Component-by-component direction

Use this as a punch list. Each item names the file, the intent, and a "definition of done".

### `Dashboard.tsx`
- Replace `type Tab = 'overview' | ...` with the category ids from `insights.ts` (`'snapshot' | 'regulatory' | 'economic' | 'market' | 'demographic' | 'safety' | 'community'`). `'snapshot'` maps to the new landing.
- Move `computeRiskScore()` out or delete it. The 0–10 risk score should not appear in the new hero.
- Pull `PipelineMonitor` + `DataSourceBadge` behind a toggle (keyboard shortcut `d` or a `Diagnostics` link in the header). They are developer chrome, not product UI.
- Keep the resizable sidebar but change default width to 420 and min to 320. Use `localStorage` to persist the width.
- Done when: initial viewport on a 1440×900 laptop shows hero + one card-row of Snapshot content without scrolling.

### `RiskCard.tsx`
- Demote or delete. If kept, render only as an inline chip inside the hero's verdict area showing the 0–10 legacy score in muted text. Do not make it a card.
- Done when: only the 0–100 insights score is prominent; the 0–10 score is ≤ body size.

### `InsightsCard.tsx`
- Split into two components:
  - `<ScoreHero>` — displays `overall`, profile selector, coverage count. Owns the primary number.
  - `<CategoryBreakdown>` — the six rows with score bars and expandable evidence. Lives inside the Snapshot page, not the hero.
- Keep the profile selector (`Conservative / Growth / Budget`) but move it to the hero so it's reachable from every category page.
- Done when: changing the profile updates the score everywhere on screen without scrolling required.

### `MapView.tsx`
- On mount, fit bounds to the selected neighborhood (use `api.geo()` response). Only fall back to city-wide if the feature is missing.
- Replace the three layer tabs with a segmented control in the map's bottom-left corner to free top-edge space.
- Suppress the HTML-string popup in favour of a rendered React portal so styles stay consistent with the rest of the app.
- Done when: selecting Coffee Shop / Loop lands the viewport on downtown Chicago, not Illinois.

### `DemographicsCard.tsx`
- Introduce two view modes:
  - `compact` — used only in the Snapshot hero: 3 tiles (Rent, Income, Rent Burden %).
  - `full` — used on the Demographic category page: full tile grid + rent-burden bar + "vs Chicago avg" comparisons.
- Drop the `horizontal` mode; replace with `compact`.
- Done when: hero is legible on a 320 px-wide sidebar snapshot; full grid fills the Demographic page.

### `NewsFeed.tsx`
- Sanitise `article.content` before rendering. Minimum: strip tags with a regex; better: use a lightweight library already in the bundle (no new deps). Then take the first 180 chars.
- Group by date bucket (Today / This Week / Earlier). Source tag uses the neutral chip style.
- Done when: no `<img>`, `<figure>`, `&#32;`, `&amp;` visible in any preview.

### `CommunityFeed.tsx`
- Dedupe reddit posts by `id`. Show the subreddit as a chip (`r/chicago` etc) using the inert chip style.
- For TikTok, collapse the transcript preview by default; open on click.
- Add a filter tab row: `All · Reddit · TikTok · Sentiment: all|positive|negative` (client-side filter, no new endpoints).
- Done when: no "[Transcript]" string appears before a click; duplicates across reddit are merged.

### `MarketPanel.tsx`
- Dedupe reviews by `review.title + rating + address` signature.
- Split into two sub-sections inside the Market page: "Businesses nearby" (review cards) and "Commercial listings" (2-column real-estate card grid with prominent price + sqft).
- Provide a sort control: Rating desc / Review count desc / Recent.
- Done when: "The Loop Marketing Inc" renders once, not five times, and listings have a readable 2-column grid.

### `InspectionTable.tsx` / `PermitTable.tsx` / `LicenseTable.tsx`
- Move from "cards" presentation to a table with sticky header, zebra rows (`even:bg-white/[0.015]`), and filterable columns. Keep row expansion for violation detail on inspections.
- For permits: show work type, address, issue date, status, fee. For licenses: name, DBA, license type, ward. Sortable by each column.
- Done when: a permit row is ~36 px tall; 15 permits fit on one screen without scrolling.

### `StreetscapeCard.tsx`
- Auto-fire the AI Assessment request on tab open, with its own loading row. Do not hide it behind a button click.
- Keep the grid of storefront counts, but re-order: lead with vacancy signal + dining saturation + growth signal badges, then the numeric grid below, then the AI assessment narrative.
- Done when: Traffic & Accessibility tab renders the AI recommendation without user interaction.

### `FootTrafficChart.tsx`
- Add a brushable hour range (even a simple `input[type=range]`) so users can zoom into morning / evening peaks.
- Label the y-axis (it's currently unlabeled).
- Done when: hovering a bar no longer overflows the chart container on the right edge.

### CCTV stack (`CCTVCameraCard`, `CCTVCameraDrawer`)
- Reduce the grid from 4 cols to 3 so each tile is bigger.
- Hide the NO-SIGNAL tiles by default behind a "Show offline cameras" disclosure.
- In the drawer, keep the mock OTel trace but move it to a collapsible "Developer" section so it does not dominate the panel.

### `LocationReportPanel.tsx`
- Strip down per the sidebar spec above. Extract Advantages/Risks helpers (`extractAllAdvantages`, `extractAllRisks`) into `insights.ts` so the Snapshot page and sidebar share them.
- Each advantage/risk card should be one line of copy + one line of evidence. No third paragraph.
- Done when: the sidebar fits in 420 px width at 1440×900 without horizontal scroll and without truncating any card.

### `PipelineMonitor.tsx` / `DataSourceBadge.tsx`
- Move behind a `Diagnostics` toggle in the header. Collapsed by default. Render as an inline `<details>` when expanded.
- Done when: product surface does not show GPU names or polling dots unless the user opts in.

### `LoadingFlow.tsx`
- Replace the generic spinner with a step-aware loader driven by the same `PipelineStatus` poll that `PipelineMonitor` uses. Show 5–7 named steps (Fetching neighborhood, Loading inspections, Loading permits, Scoring categories, Enriching trends, Generating brief). Fall back to spinner if status is unavailable.
- Done when: the 60-second initial wait shows progress the user can parse, not a solitary circle.

---

## Worked layout for Snapshot (ASCII mock)

```
┌── Hero ─────────────────────────────────────────────────────────────┐
│ COFFEE SHOP · LOOP                               Conservative ▾     │
│                                                                      │
│   58        Mixed signals for a Coffee Shop in the Loop.            │
│   ────      Strongest: Community (89)  ·  Primary risk: Dev (34)    │
│  of 100                                                              │
│                                                                      │
│   ●●●●●●●●○○  5/6 categories scored · 89 docs from 9 sources        │
└──────────────────────────────────────────────────────────────────────┘

┌── Map & neighborhood context ─────────────┐ ┌── Category breakdown ─┐
│                                           │ │  Regulatory     —/100 │
│     (fits Loop bounding box)              │ │  Development    34 ▓  │
│                                           │ │  Market         56 ▓▓ │
│   [Regulatory] [Commercial] [Sentiment]   │ │  Demographic    79 ▓▓▓│
│                                           │ │  Traffic        44 ▓▓ │
│                                           │ │  Community      89 ▓▓▓│
└───────────────────────────────────────────┘ └───────────────────────┘

┌── Why it looks good ──────────────┐  ┌── What could go wrong ────────┐
│ ✓ Strong transit access           │  │ ▲ Declining review activity   │
│   23 CTA stations nearby          │  │   0 of 15 reviews in 90 days  │
│ ✓ Active real estate market       │  │ ▲ Federal regulatory pressure │
│   4 commercial listings           │  │   10 recent SBA/FDA/EPA rules │
│ ✓ High review ratings             │  │ ▲ Low development activity    │
│   4.5/5 avg across 15 businesses  │  │   34/100 (concerning)          │
└───────────────────────────────────┘  └───────────────────────────────┘

┌── Zeitgeist (social media + news pulse) ───────────────────────────┐
│  Budget-friendly study spot demand   [from reddit · 3 threads]     │
│  Michigan Ave lunch/tourist surge    [from news · 7 mentions]      │
│  Summer influx, late-night upside    [from reddit + tiktok]        │
└────────────────────────────────────────────────────────────────────┘
```

---

## Acceptance criteria (verifiable)

A redesign PR is ready to ship when all of the following hold on a 1440×900 Chrome window, `/analysis` route, Coffee Shop + Loop inputs:

1. **Single hero number.** Only one score renders above the fold. It equals `computeInsights(..., selectedProfile).overall`.
2. **No duplicate sections.** No header label (Advantages, Risks, Verdict, Key Metrics) appears in both the main content and the sidebar.
3. **Clean previews.** No HTML tag (`<`, `&lt;`, `&#`) appears in any news/reddit/tiktok preview.
4. **Map is focused.** Initial map center+zoom fits the Loop feature bounding box, not the Chicago-wide default.
5. **No unstyled empty state.** If inspections/cctv/parking data is missing, the redesigned empty state explains *why* and offers a next action. No "No food inspection data available" flat row.
6. **Type scale lint.** A grep for `text-\[\d+px\]` in changed files returns zero matches, except for a single approved exception (`text-[11px]` mono label).
7. **Profile switching propagates.** Switching Conservative → Growth → Budget updates the hero number, the category breakdown, and the advantages/risks without refetching.
8. **Sidebar resize persists.** Dragging the sidebar to a new width survives a page reload (localStorage).
9. **No new runtime API calls.** `git diff frontend/src/api.ts` is empty; `git diff frontend/src/types/index.ts` is empty (or types-only tweaks).
10. **Lint + build pass.** `cd frontend && npm run lint && npm run build` succeeds.
11. **Keyboard navigable.** Tabbing through the hero reaches: profile selector, category nav, sidebar jump-to-evidence chips, in that order.
12. **Responsive.** At 1280 px the sidebar collapses to a bottom drawer; below 900 px the category nav becomes a select. No horizontal scroll at ≥ 768 px.

---

## Suggested sequencing for the implementing agent

1. **Freeze the data contract.** Read `api.ts` and `types/index.ts` end-to-end; do not modify.
2. **Add `ScoreHero` and new category nav** inside `Dashboard.tsx` behind a feature flag (`NEW_DASHBOARD` env var). Keep the existing tab tree alive until parity is reached.
3. **Port category content in this order:** Snapshot → Market → Regulatory → Community → Traffic → Development → Demographic. (Market and Regulatory are the most-read; start there so feedback is high-signal.)
4. **Retire old tabs one by one,** deleting their components only after the new page for that category passes all relevant acceptance criteria above.
5. **Only then** sweep through the sidebar cleanup in `LocationReportPanel.tsx` and tighten typography/colour.
6. **Final pass:** move `PipelineMonitor` + `DataSourceBadge` behind the Diagnostics toggle; delete unused exports.

---

## Things to flag back to the humans, not fix silently

- The backend exposes `federal_register` but `NeighborhoodData` types include it only optionally. If you need to render it in Regulatory, confirm current server behaviour rather than adding a guard that hides it.
- `computeRiskScore()` in `Dashboard.tsx` is dead-weight once the 0–10 score is demoted; confirm removal with the team because `RiskScore` is exposed on the `types` module.
- `api.visionAssess()` is a paid GPT-4V call. Auto-firing it on tab open increases cost. If the human reviewer disagrees, keep the click-to-run button but move it inline with the Streetscape hero.
- The `x-user-id` profile save on submit (`App.tsx::handleProfileSubmit`) writes to the backend. Any redesign of the profile drawer must preserve that call.
