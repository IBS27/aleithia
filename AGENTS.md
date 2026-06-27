# AGENTS.md

## Architecture rules that matter

- This repo effectively has two backends:
  - `backend/main.py` serves the local FastAPI app.
  - `modal_app/web.py` serves the richer Modal-hosted API used by much of the frontend.
- `frontend/src/api.ts` uses `VITE_MODAL_URL` when set, and otherwise falls back to `/api/data`.
- The app currently runs in local, unauthenticated mode. Frontend profile/history calls attach an `x-user-id` header from localStorage, and `backend/auth.py` falls back to `ALEITHIA_DEFAULT_USER_ID` when no header is provided.
- Many frontend endpoints are implemented only in `modal_app/web.py` and its route modules, not in `backend/`. This includes `/analyze`, `/gpu-metrics`, `/trends/*`, `/vision/*`, `/parking/*`, `/social-trends/*`, `/graph/full`, `/graph/neighborhood/*`, `/command/synthesis`, and impact-brief routes.
- CCTV/vision frontend flows should be treated as Modal-owned unless you verify otherwise. The local backend has a `/cctv/timeseries/{neighborhood}` fallback, but Modal owns current CCTV frame/latest, vision, and parking routes. When `ENABLE_CCTV_ANALYSIS=false`, Modal serves synthetic CCTV analytics for counts/timeseries and skips GPU analysis; do not assume those synthetic analytics correspond to a real analyzed frame.
- Simple read-only routes such as `/sources`, `/summary`, `/geo`, `/news`, `/politics`, `/inspections`, `/permits`, `/licenses`, `/reddit`, `/reviews`, `/realestate`, and `/tiktok` now belong in `backend/`, not `modal_app/`.
- Status split rule: document/source freshness belongs in `backend/` (`/status`, `/metrics`), while Modal keeps runtime-only status such as GPU/cost reporting (`/status`, `/gpu-metrics`).
- Actian VectorAI DB is no longer part of the supported `modal_app` architecture. Do not add new `vectordb` wiring, health fields, image config, or Modal discovery imports unless the task explicitly restores that integration.
- `modal_app/agents.py::regulatory_agent` should be understood as a live-fetch plus cache fallback flow: fetch Legistar and Federal Register inline, deduplicate against raw volume data under `politics/` and `federal_register/`, then optionally write fresh live results back to the volume.
- Do not add or modify a route in `backend/` if the frontend call is supposed to hit the deployed Modal API. Verify the real owner first.
- New Modal functions and endpoints must remain discoverable from `modal_app/__init__.py`. If a new module is not imported there, `modal deploy modal_app/__init__.py` may not pick it up.
- Data-root invariants:
  - The canonical shared runtime dataset for backend reads lives in the Modal Volume `alethia-data`.
  - Backend shared dataset reads must go through `backend/shared_data.py`, not direct filesystem traversal under repo `data/`.
  - Do not reintroduce `backend/data/...`, repo-root `raw/` or `processed/`, or filesystem auto-detection fallbacks as supported runtime sources.
  - Runtime code must not silently read from `fixtures/demo_data/`; if demo data is needed locally, use `scripts/bootstrap/bootstrap_demo_data.py`.
  - Do not commit generated runtime files under `data/`.
- Local Python setup:
  - Use a repo-root `/.venv`, not `backend/.venv`.
  - Use Python 3.12 for the local venv because the current dependency set is validated there.
  - Install local test/dev dependencies from `requirements-dev.txt`.
- Shared read-helper rule:
  - Normal shared read/filter/metric helpers now live in `backend/shared_data.py`, `backend/read_helpers.py`, and `backend/metric_helpers.py`. Reuse those from `modal_app/` instead of recreating duplicate helper logic there.
  - For disabled CCTV-analysis mode, prefer `processed/cctv/synthetic_analytics.json` from the shared Modal volume; do not add runtime reads that depend directly on `fixtures/demo_data/`.

## Known repo hazards

- The real Modal app object is `modal.App("alethia")` in `modal_app/volume.py`, but some legacy code still references other app names. In particular, `backend/routes/modal_routes.py` defaults `MODAL_APP_NAME` to `hackillinois2026` and still mentions `modal/app.py` in an error message. Verify `modal.Function.from_name(...)` usage before changing deployment-related code; the current deploy entrypoint is `modal_app/__init__.py`.
- Auth was removed from the app, but several database columns, Pydantic models, and frontend types still use the name `clerk_user_id`. Preserve those field names unless the task explicitly includes a contract/schema migration.
- Product-facing frontend pages and old planning docs may still mention VectorAI DB or VectorDB health/status. Treat live code paths as source of truth and update copy narrowly when it would otherwise become false.
- Some older docs, scripts, or comments may still mention repo-local runtime data roots. Treat `backend/shared_data.py`, `modal_app/volume.py`, and `tests/test_backend_shared_data.py` as the current source of truth.
- `backend/database.py` defaults to `sqlite:///./test.db`. Run backend commands from `backend/` or set `DATABASE_URL` explicitly, otherwise SQLite may be created in an unexpected directory.

## Frontend guidance

- Preserve the existing product flow and visual language unless the task is explicitly a redesign.

## Backend and Modal guidance

- Preserve JSON key names unless the task explicitly changes the contract.
- Keep local user resolution compatible with the current unauthenticated flow in `backend/auth.py`: optional `x-user-id` override plus `ALEITHIA_DEFAULT_USER_ID` fallback.
- User profile/settings/query ownership now lives in `backend/`; do not reintroduce Modal-owned `/user/settings` routes or separate Modal settings storage.
- If you touch `modal_app/api/routes/core.py`, verify the real emitted contract before adding status fields. `/status` should reflect active pipeline/GPU/cost reporting, not removed VectorDB health metadata.
- `ENABLE_CCTV_ANALYSIS` is controlled through the Modal secret `alethia-secrets`. If you add or change CCTV env-gated behavior in Modal functions/classes, verify those functions/classes mount that secret before assuming the flag is available everywhere.
- If you touch `modal_app/agents.py::regulatory_agent`, preserve the non-VectorDB path: concurrent live API fetches, dedup against cached volume docs, cached-freshness reporting, and live-result write-back.
- When adding or renaming source/document fields, update downstream readers, ranking logic, and tests in the same change.

## Instructions for writing HTML documents when asked by the user

- When I ask for an HTML document, create or edit a `.html` file, usually in `docs/` unless I specify another path.
- Treat the HTML file as a readable document, similar to a Markdown brief, but with better layout and navigation.
- Keep the writing plain and concrete. Avoid vague language, hype, filler, and generic AI-sounding phrasing.
- Prefer short sections, direct headings, bullets, tables, and examples over long paragraphs.
- Make the document self-contained: inline CSS, no unnecessary JavaScript, no external assets unless requested.
- Use semantic HTML and make it responsive enough to read on desktop and mobile.
