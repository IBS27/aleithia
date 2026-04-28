# AGENTS.md

Instructions for coding agents working in this repository. Keep this file practical: prefer repo-specific constraints, exact commands, and architecture notes over generic coding advice.

## Core workflow

- First decide which surface you are changing: `frontend/`, `backend/`, or `modal_app/`.
- Read the nearby implementation before editing. Do not assume endpoint ownership, data shapes, or file locations from names alone.
- Prefer narrow changes over broad refactors. Large components and pipeline modules already carry a lot of local context.
- Validate the smallest relevant surface for your change, then report exactly what you ran and what remains unverified.
- Treat `docs/OPERATIONS.md` as the canonical human setup/runbook doc. Keep `README.md` short and practical, and use `AGENTS.md` for agent-specific repo guidance.

## Repository map

- `frontend/`: React 19 + TypeScript + Vite UI.
- `frontend/src/api.ts`: primary client API contract. Check this before changing routes or response shapes.
- `frontend/src/business/`: frontend-local mock POS and business intelligence layer for the dashboard Command screen. Keep this deterministic and derived from raw mock orders/menu/hours/inventory; do not hardcode final dashboard card values.
- `frontend/.env.example`: documents `VITE_MODAL_URL` and optional `VITE_BACKEND_URL`; Clerk frontend env vars were removed.
- `backend/`: local FastAPI service for health checks, user profile/history, and some JSON-backed local data endpoints.
- `modal_app/`: the main Modal application and the production-facing API in `modal_app/web.py`.
- `data/`: local bootstrap/test workspace only. Do not assume backend shared reads come from here.
- `fixtures/demo_data/`: checked-in demo/sample data. Only copy from here into `data/` explicitly.
- `scripts/bootstrap/`: explicit local bootstrap utilities.
- `scripts/maintenance/`: supported maintenance utilities and local pipeline harnesses.
- `scripts/experiments/`: optional compute-heavy or one-off workflows.
- `tests/`: pytest coverage for ranking, retrieval, tracing, Modal web contracts, and risk scoring.
- `requirements-dev.txt`: root local Python dependency entrypoint for `/.venv` and repo-wide pytest.

## Architecture rules that matter

- This repo effectively has two backends:
  - `backend/main.py` serves the local FastAPI app.
  - `modal_app/web.py` serves the richer Modal-hosted API used by much of the frontend.
- `frontend/src/api.ts` uses `VITE_MODAL_URL` when set, and otherwise falls back to `/api/data`.
- The app currently runs in local, unauthenticated mode. Frontend profile/history calls attach an `x-user-id` header from localStorage, and `backend/auth.py` falls back to `ALEITHIA_DEFAULT_USER_ID` when no header is provided.
- Many frontend endpoints are implemented only in `modal_app/web.py`, not in `backend/`. This includes `/analyze`, `/status`, `/metrics`, `/gpu-metrics`, `/trends/*`, `/vision/*`, `/parking/*`, `/social-trends/*`, and `/graph/full`.
- CCTV/vision frontend flows should be treated as Modal-owned unless you verify otherwise. In particular, when `ENABLE_CCTV_ANALYSIS=false`, the Modal API serves synthetic CCTV analytics for counts/timeseries and skips GPU analysis; do not assume those synthetic analytics correspond to a real frame or analyzed camera result.
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

- The real Modal app object is `modal.App("alethia")` in `modal_app/volume.py`, but some legacy code still references other app names. Verify `modal.Function.from_name(...)` usage before changing deployment-related code.
- `backend/routes/modal_routes.py` still mentions `modal/app.py` in an error message. The current deploy entrypoint is `modal_app/__init__.py`.
- Auth was removed from the app, but several database columns, Pydantic models, and frontend types still use the name `clerk_user_id`. Preserve those field names unless the task explicitly includes a contract/schema migration.
- Product-facing frontend pages and old planning docs may still mention VectorAI DB or VectorDB health/status. Treat live code paths as source of truth and update copy narrowly when it would otherwise become false.
- Some older docs, scripts, or comments may still mention repo-local runtime data roots. Treat `backend/shared_data.py`, `modal_app/volume.py`, and `tests/test_backend_data_access.py` as the current source of truth.
- `backend/database.py` defaults to `sqlite:///./test.db`. Run backend commands from `backend/` or set `DATABASE_URL` explicitly, otherwise SQLite may be created in an unexpected directory.
- `backend/test.db` is checked in. Do not delete or rewrite local DB/data artifacts unless the task explicitly requires it.

## Commands

- Frontend dev: `cd frontend && npm run dev`
- Frontend lint: `cd frontend && npm run lint`
- Frontend build: `cd frontend && npm run build`
- Python env bootstrap: `make setup-python`
- Manual Python env bootstrap: `python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`
- Run pytest from the repo-root virtualenv: `.venv/bin/pytest ...`
- Local backend dev: `cd backend && uvicorn main:app --reload`
- Full local stack: `docker-compose up --build` (set `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET` in repo-root `.env` so backend volume-backed routes like `/geo` can read `alethia-data`)
- Modal deploy: `modal deploy modal_app/__init__.py`
- Local pipeline harness: `python scripts/maintenance/test_pipelines.py`
- Python tests: `pytest -q`
- Targeted Python tests: `pytest tests/test_risk_scoring.py -q`

## Validation expectations

- Run targeted validation for the code you touched.
- Do not claim repo-wide success unless you actually ran repo-wide checks.
- For API-contract changes, validate both sides: the server route and the frontend caller.
- Expect baseline validation debt:
  - frontend lint/build may fail on pre-existing issues unrelated to your task;
  - Runtime packaging still uses both `backend/requirements.txt` and `modal_app/requirements-modal.txt`, while local repo-wide pytest should use `requirements-dev.txt`.
  - The local `/.venv` is for repo development and pytest; Docker and Modal packaging still use their own runtime-specific manifests.
- If a check fails for unrelated baseline reasons, say so clearly and separate it from your change-specific verification.

## External services and cost controls

- Many pipelines and scripts call paid, rate-limited, or slow services when credentials are present: Modal GPU jobs, OpenAI, NewsAPI, Reddit, Yelp, Google Places, TomTom, Supermemory, Mapbox, Google Earth Engine, and TikTok scraping infrastructure.
- Prefer mocks, fixtures, local JSON, or `scripts/maintenance/test_pipelines.py` before invoking remote services.
- Do not trigger broad pipeline runs, deploys, or long GPU jobs unless the task requires them.
- Never commit secrets or real `.env` values. Use `.env.example` files only as interface references.

## Frontend guidance

- Preserve the existing product flow and visual language unless the task is explicitly a redesign.
- Keep TypeScript types explicit. Avoid introducing new `any` usage.
- Do not reintroduce Clerk assumptions in the UI or API client. The frontend no longer uses `ClerkProvider`, auth buttons, or `VITE_CLERK_PUBLISHABLE_KEY`.
- Search for the server implementation before changing frontend API assumptions. Several endpoint families are documented in the UI but are backed only by the Modal API.
- For user-scoped requests, check `frontend/src/api.ts` before editing components: it is responsible for generating/storing the local user id and attaching the `x-user-id` header.
- When changing response shapes, update `frontend/src/types`, `frontend/src/api.ts`, and affected components together.
- For the Command/business screen, keep `frontend/src/business/` narrow: fixed mock coffee shop/restaurant internals plus derived neighborhood context; no backend route or POS-provider abstraction until a real integration needs it.

## Backend and Modal guidance

- Preserve JSON key names unless the task explicitly changes the contract.
- Keep local user resolution compatible with the current unauthenticated flow in `backend/auth.py`: optional `x-user-id` override plus `ALEITHIA_DEFAULT_USER_ID` fallback.
- User profile/settings/query ownership now lives in `backend/`; do not reintroduce Modal-owned `/user/settings` routes or separate Modal settings storage.
- If you touch `modal_app/api/routes/core.py`, verify the real emitted contract before adding status fields. `/status` should reflect active pipeline/GPU/cost reporting, not removed VectorDB health metadata.
- `ENABLE_CCTV_ANALYSIS` is controlled through the Modal secret `alethia-secrets`. If you add or change CCTV env-gated behavior in Modal functions/classes, verify those functions/classes mount that secret before assuming the flag is available everywhere.
- If you touch `modal_app/agents.py::regulatory_agent`, preserve the non-VectorDB path: concurrent live API fetches, dedup against cached volume docs, cached-freshness reporting, and live-result write-back.
- When adding or renaming source/document fields, update downstream readers, ranking logic, and tests in the same change.
- Avoid silent architectural cleanup outside scope. If you discover dead paths, stale messages, or inconsistencies, note them in your final response unless the task asked you to fix them.

## Agent behavior

- Make minimal, reversible edits.
- Prefer targeted tests over broad reruns.
- Do not “fix” unrelated lint or typing debt just because you touched a nearby file.
- If local reality conflicts with comments or docs, trust the code and filesystem after verifying them.
