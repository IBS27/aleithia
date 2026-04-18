# UI Refactor Brief

This document defines the Aleithia dashboard refactor based on the generated concept images:

- `/Users/srinivasib/.codex/generated_images/019d9a56-e623-72e0-adc7-27c937b72fb2/ig_0b644a9404553f3c0169e1e1eab920819a8531886ec21615f6.png`
- `/Users/srinivasib/.codex/generated_images/019d9a56-e623-72e0-adc7-27c937b72fb2/ig_0b644a9404553f3c0169e1e2305934819a84102ffd9e4efc05.png`

The goal is not to redesign Aleithia into a different product. The goal is to evolve the current frontend into a clearer, denser, more polished control-room interface while keeping all existing data sources, route ownership, and response contracts valid.

## Refactor Goal

The current dashboard already has the right ingredients:

- dark technical aesthetic
- persistent intelligence brief rail
- map, risk, regulatory, market, community, and vision surfaces
- tabbed navigation by signal type

What it does not yet do well enough is organize those signals into a strong visual hierarchy. Important information is present, but it is spread across separate cards, long vertical flows, and inconsistent density levels. The refactor should make the UI feel more intentional, more scan-friendly, and more obviously built for decision-making.

The concept images suggest three primary upgrades:

1. Merge related information into fewer, stronger command panels.
2. Turn the main dashboard into a tactical workspace instead of a loose collection of cards.
3. Preserve the current black-glass, HUD-style brand language while improving readability and information hierarchy.

## Design Direction To Preserve

The refactor should keep the following visual qualities from the current frontend and the generated concepts:

- near-black background with subtle navy depth, not a flat charcoal screen
- thin hairline borders and panel outlines
- small monospaced uppercase labels for metadata and section headers
- restrained accent colors for semantic meaning:
  - cyan/blue for active system state
  - green for positive signal / healthy status
  - amber for caution / mixed signal
  - red for risk / negative signal
- technical, surveillance-adjacent interface language without becoming noisy
- clean typography hierarchy with larger summary numbers and quieter supporting text
- persistent right-side intelligence rail as a signature Aleithia element

The UI should feel sharper and more premium, but still unmistakably Aleithia.

## Global Layout Changes

### 1. Strengthen the top shell

The top bar should become more informative and more structured.

Change:

- keep `ALEITHIA` brand mark on the far left
- keep the current business type and neighborhood breadcrumb
- keep the elapsed analysis timer
- keep `Refresh`, `Profile`, and `New Search`
- add stronger visual grouping so the top bar reads as:
  - identity
  - context
  - session status
  - user actions

Why:

- the current top bar is present but visually weak
- the concept image shows the shell acting like a mission-control header
- users should immediately know what is being analyzed, how long the run has taken, and what actions are available

### 2. Make the pipeline monitor a real dashboard strip

The pipeline monitor should remain near the top, but it should become a compact status strip rather than a mostly passive banner.

Change:

- keep live pipeline state visible at all times
- summarize source readiness, metadata readiness, and runtime status in one row
- show source failures as non-blocking warnings, not layout-breaking messages
- preserve expandable detail, but improve the collapsed state so it is useful on its own

Why:

- the current `PipelineMonitor` has useful data, but in practice it often reads like a disconnected banner
- the concept image treats this as a continuous system status layer
- source timeouts should be visibly important without visually dominating the entire page

### 3. Preserve the persistent intelligence brief rail

The right sidebar should stay. It is one of the strongest parts of the current product.

Change:

- keep the rail sticky and independent from the left workspace
- keep the intelligence brief grouped into stacked sections
- make each section more compact, more skimmable, and more visually distinct
- keep the `Download PDF` action in the rail header

Why:

- the current brief is already a strong product signature
- the concept images confirm this should remain the permanent decision summary surface
- the rail should summarize, not compete with, the left workspace

## Overview Tab Changes

The overview tab should become the primary decision cockpit.

### 1. Replace the loose two-card hero with a command layout

Current state:

- the map and risk/opportunity content sit side by side
- risk information and insights are split across `RiskCard` and `InsightsCard`
- the result is correct but fragmented

Change:

- keep a two-column hero
- on the left, keep the map as the main spatial context module
- on the right, combine risk and opportunity into one stronger panel
- that panel should include:
  - risk score
  - opportunity score
  - confidence
  - overall verdict
  - category bars
  - top positives
  - top concerns
  - quick-jump chips into downstream tabs

Why:

- the concepts make it clear that this information should be treated as one command module
- the current `RiskCard` and `InsightsCard` separation forces the user to mentally combine related information
- this should feel like a single decision engine, not two adjacent widgets

### 2. Keep the map, but give it a more tactical frame

Current state:

- `MapView` is useful, but the surrounding layout does not emphasize its role as the geographic command surface

Change:

- keep the existing regulatory/commercial/sentiment layer model
- make the layer toggles feel like a dedicated map control row
- visually frame the map as a heatmap console
- keep hover/click neighborhood detail behavior
- improve the legend and active-state clarity

Why:

- the concept image shows the map as the spatial anchor of the dashboard
- the current map is good data-wise, but the presentation can feel like a standalone embed instead of a core control surface

### 3. Turn demographics into a tactical stats ribbon

Current state:

- `DemographicsCard` is useful but visually secondary and somewhat separate from the rest of the flow

Change:

- convert the horizontal version into a tighter stats ribbon beneath the hero
- surface the most decision-relevant values first:
  - population
  - income
  - rent
  - permits
  - reviews
  - transit
  - sentiment
- preserve secondary values, but avoid a long unstructured strip

Why:

- the concept image shows these as quick reference indicators, not a full card competing with the hero
- these values are strongest when they support the main analysis rather than interrupt it

### 4. Add a structured preview row for downstream evidence

Change:

- add a lower row with compact preview panels for:
  - local news alerts
  - community chatter
  - market snapshot
- each panel should show only a few high-signal entries and link into the full tab

Why:

- overview should feel comprehensive without forcing full-tab context switching
- the concept image demonstrates a better “preview then drill down” model

## Regulatory Tab Changes

The regulatory tab should feel like a high-trust evidence workspace, not just a list switcher.

### 1. Preserve the sub-tab structure, but strengthen hierarchy

Keep:

- `Inspections`
- `Permits`
- `Licenses`

Change:

- elevate the sub-tab header into a more obvious segmented control
- add summary counts and state labels above the content region
- make empty states more descriptive and less visually dead

Why:

- the current data is valid, but the layout can feel sparse, especially when one sub-tab has no records

### 2. Improve permit and license record readability

Change:

- maintain the existing record data, fields, and statuses
- restructure each item so the eye can immediately parse:
  - record type
  - address / entity
  - status
  - short description
  - permit type / license type
  - amount if available
  - date
- use clearer row rhythm and metadata grouping

Why:

- the current record cards are data-rich but hard to scan quickly
- this tab should support rapid review of civic and compliance signals

### 3. Keep regulatory data trustworthy

Do not change:

- how inspection pass/fail outcomes are derived
- permit count logic
- license count logic
- federal alert inclusion logic in the brief rail

This refactor should only improve structure and presentation.

## News & Policy Tab Changes

The news and policy tab should feel more like an intelligence feed and less like a flat stack of cards.

### 1. Separate signal types more clearly

Keep:

- Local News
- City Council / politics items

Change:

- present them as two clearly distinct feed groups with consistent row design
- standardize headline, snippet, tag, source, and timestamp placement
- improve the visual difference between article source tags and policy matter tags

Why:

- this tab currently works, but articles and policy items feel stylistically too similar
- the evidence explorer concept shows that source type should be visually legible at a glance

### 2. Add stronger feed metadata

Change:

- display impact or relevance badges where available from existing computed UI logic
- keep timestamps and direct links visible
- make truncation more disciplined so each entry occupies predictable height

Why:

- this makes the feed easier to skim without changing the actual data source or content

## Community Tab Changes

The community tab should become a better “social pulse” workspace.

### 1. Preserve Reddit and TikTok as separate source groups

Keep:

- Reddit discussion feed
- TikTok feed when available

Change:

- improve creator/subreddit badges
- give each source its own rhythm and metadata treatment
- make engagement cues like comments, score, views, and hashtags more visually useful

Why:

- the current data is present, but the layout still reads like generic cards
- the concepts point toward a more operational, evidence-led presentation

### 2. Support trend synthesis without replacing source evidence

Change:

- keep raw source entries visible
- make it easier to connect them to the “Social Media Trends” synthesis in the right rail

Why:

- the synthesized brief is valuable only if the user can still inspect the underlying evidence

## Market Tab Changes

The market tab should move from a generic feed to a clearer commercial intelligence view.

### 1. Make business reviews easier to compare

Change:

- keep title, rating, review count, price level, categories, and velocity
- restructure review rows so ratings and velocity become a true comparison layer
- reduce visual repetition when multiple listings appear similar

Why:

- the current market tab is valid, but comparison is harder than it should be
- users need to quickly identify strong incumbents, weak incumbents, and saturation signals

### 2. Make commercial listings feel like opportunity inventory

Change:

- keep property type, square footage, price, listing type, and outbound links
- improve hierarchy so space availability reads as market opportunity, not just another content card

Why:

- this tab should support site selection thinking, not just browsing

## Vision Tab Changes

The vision tab is visually one of the most distinctive parts of the product. It should be kept and tightened, not softened.

### 1. Keep the surveillance/HUD aesthetic

Keep:

- CCTV wall
- camera status indicators
- monospaced overlays
- green / amber / blue status accents

Change:

- make the layout more deliberate and modular
- give the selected camera state a clearer detail surface
- improve the visual relationship between summary stats, charting, and the camera wall

Why:

- the concept image confirms this tab is strongest when it leans into the control-room language

### 2. Make streetscape and parking analysis feel first-class

Change:

- elevate `StreetscapeCard` and parking occupancy into top-of-tab intelligence modules
- group them with clear visual hierarchy:
  - street analysis
  - AI assessment
  - parking occupancy
- keep annotated imagery and model framing visible, but avoid overwhelming the user with low-value decoration

Why:

- these are important differentiators and should not feel buried underneath summary cards

### 3. Improve the detection summary + timeseries flow

Change:

- keep summary stat tiles for cameras, pedestrians, vehicles, bicycles, and density
- keep the 24h traffic activity chart
- visually connect the chart to the selected camera grid and the broader vision narrative

Why:

- the current pieces are useful, but the flow is more vertical than analytical

## Evidence Explorer Addition

The generated concept introduces a consolidated evidence workspace. This should be added as a new surface or a structured mode within the existing left workspace.

### Purpose

Create one place where the user can inspect all underlying signals across:

- news
- policy
- community
- market
- regulatory

### Required behavior

- filter by source family
- filter by relevance / impact if available from existing UI logic
- search within visible evidence
- sort by recency or importance
- show source-specific metadata without flattening everything into the same card

### Why it matters

- the current tab system is useful for category browsing
- the proposed evidence explorer is useful for cross-source investigation
- both should coexist

This addition should not invent new backend aggregation requirements unless the existing frontend already has enough local data to assemble the view.

## Intelligence Brief Rail Changes

The right rail should remain structurally similar, but it needs stronger grouping and compression.

### Keep these sections

- score banner
- verdict
- advantages
- risks
- social trends
- competitive landscape
- regulatory checklist
- key metrics
- source count summary

### Change how they are presented

- reduce vertical drift by tightening spacing
- make each section feel like a deliberate module
- keep tinted containers for semantic groups:
  - green-tinted opportunities
  - amber/red-tinted risks
  - cyan-tinted social trends
- improve scannability of long text blocks
- make the sidebar feel editorial, not just stacked cards

### Important guardrail

The brief rail must continue to summarize existing data. It should not become a new independent source of truth.

## Interaction Changes

### 1. Improve drill-down behavior

Users should be able to move from summary to evidence without losing context.

Add or improve:

- quick-jump chips from overview summary modules into downstream tabs
- “view all” patterns from category summaries into evidence lists
- preserved state when navigating between tabs

### 2. Improve empty and degraded states

Current degraded states like source metadata timeouts or missing inspection data are valid conditions. The UI should present them more gracefully.

Change:

- use structured warning rows
- explain what is missing
- keep the rest of the page functional
- avoid a blank-feeling panel where possible

### 3. Improve density without reducing legibility

This refactor should increase information density, but not by shrinking everything.

Do:

- group related information
- reduce duplicate headings
- align metadata placement
- standardize row/card heights

Do not:

- compress text until the dashboard feels like a wireframe
- replace readable prose with unexplained abbreviations

## Data Validity And Contract Safety

This refactor must keep the current data sources valid.

### Frontend contract rules

Do not change response shapes unless absolutely required. If any shape changes are proposed later, they must be coordinated across:

- `frontend/src/types`
- `frontend/src/api.ts`
- the owning backend route

### Route ownership rules

Preserve existing route ownership:

- Modal-owned analysis and vision flows remain Modal-owned
- backend-owned read-only routes remain backend-owned
- do not move route ownership as part of the UI refactor

### Existing sources to preserve in the UI

The UI should continue to present data sourced from the current neighborhood payload and related calls, including:

- inspections
- permits
- licenses
- news
- politics
- reddit
- tiktok
- reviews
- real estate
- traffic
- transit
- demographics
- metrics
- cctv
- parking
- streetscape
- social trends
- pipeline status

### Presentation rules

The refactor may:

- reorder sections
- combine panels
- improve copy hierarchy
- add local filtering and search on already-fetched data
- add stronger empty states

The refactor may not:

- invent new values without a real source
- imply confidence or freshness that the backend does not provide
- merge distinct source families into a misleading “single score” without traceability
- hide degraded data states in a way that makes incomplete data look complete

## Recommended Implementation Order

### Phase 1: Shell and overview

- strengthen top bar
- refactor pipeline monitor presentation
- merge risk and opportunity into one command panel
- convert demographics into a tactical stats ribbon
- preserve current right rail with improved grouping

### Phase 2: Evidence surfaces

- refactor regulatory tab
- refactor news/policy tab
- refactor community tab
- refactor market tab
- add preview-to-detail pathways from overview

### Phase 3: Vision polish

- elevate streetscape + parking + AI assessment structure
- tighten detection summary
- improve CCTV wall and selected camera state

### Phase 4: Unified evidence explorer

- add cross-source evidence workspace
- make it complementary to, not a replacement for, the existing tab model

## Success Criteria

The refactor is successful if:

- the dashboard still feels like Aleithia
- the left side feels like a high-signal workspace instead of a long stack of unrelated cards
- the right rail remains the stable decision summary
- vision remains a standout differentiator
- source outages and partial data are clearer, not more hidden
- no backend contracts are silently broken
- all displayed signals remain traceable to current valid data sources
