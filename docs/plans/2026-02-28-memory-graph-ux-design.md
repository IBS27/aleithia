# Memory Graph UX Improvements Design

**Date:** 2026-02-28
**Status:** Approved

## Overview

Enhance the `@supermemory/memory-graph` (v0.1.8) integration in both `LandingPage.tsx` (embedded preview) and `MemoryGraphPage.tsx` (full-page experience) by enabling the many unused props the component already supports.

## Changes

### LandingPage.tsx (embedded preview)

Minimal additions to keep the landing page fast and clean:

- `maxNodes={50}` — cap visible nodes to prevent visual overload
- `showSpacesSelector={true}` — let visitors filter by data source

### MemoryGraphPage.tsx (full-page experience)

Full treatment with toolbar, pagination, search, and slideshow:

| Feature | Props Used | Implementation |
|---------|-----------|----------------|
| Node limit | `maxNodes={80}` | Prevents clutter |
| Space filter | `showSpacesSelector={true}`, `selectedSpace`, `onSpaceChange` | Controlled filter by container tag |
| Pagination | `hasMore`, `loadMoreDocuments`, `autoLoadOnViewport={true}`, `isLoadingMore`, `totalLoaded` | Fetch `/graph?page=N&limit=50`, append to docs array |
| Search + highlight | `highlightDocumentIds`, `highlightsVisible` | Custom search bar, client-side filter on title/content, highlights matching doc IDs |
| Slideshow | `isSlideshowActive`, `onSlideshowNodeChange`, `onSlideshowStop` | Toggle button in toolbar |

### UI Layout (MemoryGraphPage)

```
┌─────────────────────────────────────────────┐
│ nav: [Alethia]                       [Back] │
├─────────────────────────────────────────────┤
│ toolbar: [🔍 Search...] [▶ Slideshow] [Stats]│
├─────────────────────────────────────────────┤
│                                             │
│            MemoryGraph (flex-1)             │
│                                             │
└─────────────────────────────────────────────┘
```

### Architecture

- All state local to each component (useState/useEffect)
- No new files, no shared hooks, no abstractions
- Pagination: page-by-page from `/graph?page=N&limit=50`, append to existing docs
- Search: client-side filter against doc title/content, pass matching IDs to `highlightDocumentIds`
- Slideshow: boolean toggle, callbacks for node change and stop

### Files Modified

1. `frontend/src/components/MemoryGraphPage.tsx` — full enhancement
2. `frontend/src/components/LandingPage.tsx` — maxNodes + spacesSelector only
