# Backend Refactor Plan

Use this as the implementation order. If you are on a step, read the remaining steps before changing code.

## Goal

- Move normal API work to `backend/`.
- Keep Modal only for GPU work, sandbox execution, batch pipelines, and other heavy jobs.

## Current State

- Step 1 is done.
- Step 2 is done.
- Step 3 is done.
- Step 4 is done.
- Step 5 is done.
- Shared read helpers now live in:
  - `backend/shared_data.py`
  - `backend/read_helpers.py`
  - `backend/metric_helpers.py`
- `backend/` is now the only owner of user profile/settings/query data.
- Simple read-only routes now live in `backend/`.
- Document/source status now lives in `backend/`; Modal runtime status stays in Modal.
- Start the next implementation work at Step 6.
- The canonical shared runtime dataset lives in the existing Modal Volume `alethia-data`.
- Backend route migrations must reuse `backend/shared_data.py`; do not add direct Modal SDK calls in route files unless unavoidable and documented.
- Checked-in demo data lives under `fixtures/demo_data/` and must stay explicit fixtures, not runtime fallbacks.

## Do Not Do

- Do not reintroduce `backend/data/...` or repo-local `data/...` as the canonical runtime source for backend reads.
- Do not add filesystem auto-detection fallbacks for raw/processed runtime reads or fixture paths.
- Do not silently read from `fixtures/demo_data/`; use `scripts/bootstrap_demo_data.py` only for explicit local bootstrap/test workflows.
- Do not broaden this into a Modal pipeline refactor unless the task is specifically about pipeline ownership.

## Order

1. Fix backend data access.
   - Done.
   - Make `backend/` read the real shared `raw/` and `processed/` data.
   - Do not move routes yet.

2. Move shared read logic into backend-owned modules.
   - Done.
   - Consolidate duplicated loaders, filters, graph helpers, CCTV helpers, parking readers, and metric helpers.

3. Make `backend/` the only owner of user data.
   - Done.
   - Keep `/user/profile` and `/user/queries` in `backend/`.
   - Remove Modal `/user/settings`.
   - Deployment note: local dev can keep using the existing `/api/data` backend proxy, but before the next real frontend deployment, user profile/query routes must stop sharing any `/api/data` rewrite that still points at Modal.

4. Move simple read-only routes to `backend/`.
   - Done.
   - `/sources`
   - `/summary`
   - `/geo`
   - `/news`
   - `/politics`
   - `/inspections`
   - `/permits`
   - `/licenses`
   - `/reddit`
   - `/reviews`
   - `/realestate`
   - `/tiktok`

5. Split status ownership.
   - Done.
   - `backend/` owns document counts and freshness.
   - Modal owns GPU and worker state.

6. Move main neighborhood reads to `backend/`.
   - `/neighborhood/{name}`
   - `/trends/{neighborhood}`

7. Move file-backed sensor read routes to `backend/`.
   - `/cctv/latest`
   - `/cctv/frame/{camera_id}`
   - `/cctv/timeseries/{neighborhood}`
   - `/parking/latest`
   - `/parking/{neighborhood}`
   - `/parking/annotated/{neighborhood}`
   - `/vision/streetscape/{neighborhood}`

8. Move proxy and utility routes to `backend/`.
   - `/graph`
   - `/graph/full`
   - `/user/memories`
   - `/impact-briefs`
   - `/impact-briefs/{id}`

9. Move normal request-time LLM routes to `backend/`.
   - `/social-trends/{neighborhood}`
   - `/vision/assess/{neighborhood}`

10. Replace `/brief/{neighborhood}` with a backend-owned route.
    - Let `backend/` call Modal only if heavy sub-jobs are still needed.

11. Replace `backend/routes/modal_routes.py` with a small Modal bridge.
    - Keep only the remaining Modal-only operations.

12. Remove the always-on Modal web API.
    - Switch routine frontend traffic to `backend/`.

## Modal-only at the end

- `/analyze`
- `/gpu-metrics`
- `/impact-briefs/analyze`
- GPU jobs
- batch pipelines

## Simple rule

- If it mostly reads files, filters docs, computes light summaries, stores user data, proxies HTTP, or makes a normal LLM call, move it to `backend/`.
- If it needs GPU, sandboxed code, heavy parallel fan-out, queues, or scheduled pipelines, keep it in Modal.
