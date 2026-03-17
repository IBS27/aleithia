# AGENTS.md

Instructions for coding agents working in this repository. Keep this file practical: prefer repo-specific constraints, exact commands, and architecture notes over generic coding advice.

## Core workflow

- First decide which surface you are changing: `frontend/`, `backend/`, or `modal_app/`.
- Read the nearby implementation before editing. Do not assume endpoint ownership, data shapes, or file locations from names alone.
- Prefer narrow changes over broad refactors. Large components and pipeline modules already carry a lot of local context.
- Validate the smallest relevant surface for your change, then report exactly what you ran and what remains unverified.

## Repository map

- `frontend/`: React 19 + TypeScript + Vite UI.
- `frontend/src/api.ts`: primary client API contract. Check this before changing routes or response shapes.
- `frontend/.env.example`: only documents `VITE_MODAL_URL`; Clerk frontend env vars were removed.
- `backend/`: local FastAPI service for health checks, user profile/history, and some JSON-backed local data endpoints.
- `modal_app/`: the main Modal application and the production-facing API in `modal_app/web.py`.
- `data/`: local runtime data root for shared raw/processed outputs. Treat it as ephemeral.
- `fixtures/demo_data/`: checked-in demo/sample data. Only copy from here into `data/` explicitly.
- `scripts/`: maintenance utilities and a local pipeline harness.
- `tests/`: pytest coverage for ranking, retrieval, tracing, Modal web contracts, and risk scoring.

## Architecture rules that matter

- This repo effectively has two backends:
  - `backend/main.py` serves the local FastAPI app.
  - `modal_app/web.py` serves the richer Modal-hosted API used by much of the frontend.
- `frontend/src/api.ts` uses `VITE_MODAL_URL` when set, and otherwise falls back to `/api/data`.
- The app currently runs in local, unauthenticated mode. Frontend profile/history calls attach an `x-user-id` header from localStorage, and `backend/auth.py` falls back to `ALEITHIA_DEFAULT_USER_ID` when no header is provided.
- Many frontend endpoints are implemented only in `modal_app/web.py`, not in `backend/`. This includes `/analyze`, `/status`, `/metrics`, `/gpu-metrics`, `/trends/*`, `/vision/*`, `/parking/*`, `/social-trends/*`, and `/graph/full`.
- Actian VectorAI DB is no longer part of the supported `modal_app` architecture. Do not add new `vectordb` wiring, health fields, image config, or Modal discovery imports unless the task explicitly restores that integration.
- `modal_app/agents.py::regulatory_agent` should be understood as a live-fetch plus cache fallback flow: fetch Legistar and Federal Register inline, deduplicate against raw volume data under `politics/` and `federal_register/`, then optionally write fresh live results back to the volume.
- Do not add or modify a route in `backend/` if the frontend call is supposed to hit the deployed Modal API. Verify the real owner first.
- New Modal functions and endpoints must remain discoverable from `modal_app/__init__.py`. If a new module is not imported there, `modal deploy modal_app/__init__.py` may not pick it up.
- Data-root invariants:
  - The canonical local runtime layout is `data/raw/` and `data/processed/`.
  - Do not reintroduce `backend/data/...`, repo-root `raw/` or `processed/`, or filesystem auto-detection fallbacks as supported runtime sources.
  - Use `ALEITHIA_DATA_ROOT`, `ALEITHIA_RAW_DATA_DIR`, and `ALEITHIA_PROCESSED_DATA_DIR` only as explicit overrides.
  - Runtime code must not silently read from `fixtures/demo_data/`; if demo data is needed locally, use `scripts/bootstrap_demo_data.py`.
  - Do not commit generated runtime files under `data/`.

## Known repo hazards

- The real Modal app object is `modal.App("alethia")` in `modal_app/volume.py`, but some legacy code still references other app names. Verify `modal.Function.from_name(...)` usage before changing deployment-related code.
- `backend/routes/modal_routes.py` still mentions `modal/app.py` in an error message. The current deploy entrypoint is `modal_app/__init__.py`.
- Auth was removed from the app, but several database columns, Pydantic models, and frontend types still use the name `clerk_user_id`. Preserve those field names unless the task explicitly includes a contract/schema migration.
- Product-facing frontend pages and old planning docs may still mention VectorAI DB or VectorDB health/status. Treat live code paths as source of truth and update copy narrowly when it would otherwise become false.
- Some older docs, scripts, or comments may still mention `backend/data` or checked-in `data/processed` content. Treat `backend/shared_data.py`, `fixtures/demo_data/`, and `tests/test_backend_data_access.py` as the current source of truth.
- `backend/database.py` defaults to `sqlite:///./test.db`. Run backend commands from `backend/` or set `DATABASE_URL` explicitly, otherwise SQLite may be created in an unexpected directory.
- `backend/test.db` is checked in. Do not delete or rewrite local DB/data artifacts unless the task explicitly requires it.

## Commands

- Frontend dev: `cd frontend && npm run dev`
- Frontend lint: `cd frontend && npm run lint`
- Frontend build: `cd frontend && npm run build`
- Local backend dev: `cd backend && uvicorn main:app --reload`
- Full local stack: `docker-compose up --build`
- Modal deploy: `modal deploy modal_app/__init__.py`
- Local pipeline harness: `python scripts/test_pipelines.py`
- Python tests: `pytest -q`
- Targeted Python tests: `pytest tests/test_risk_scoring.py -q`

## Validation expectations

- Run targeted validation for the code you touched.
- Do not claim repo-wide success unless you actually ran repo-wide checks.
- For API-contract changes, validate both sides: the server route and the frontend caller.
- Expect baseline validation debt:
  - frontend lint/build may fail on pre-existing issues unrelated to your task;
  - Python tests depend on packages from both `backend/requirements.txt` and `modal_app/requirements-modal.txt`, plus pytest-related tooling not declared in one unified manifest.
- If a check fails for unrelated baseline reasons, say so clearly and separate it from your change-specific verification.

## External services and cost controls

- Many pipelines and scripts call paid, rate-limited, or slow services when credentials are present: Modal GPU jobs, OpenAI, NewsAPI, Reddit, Yelp, Google Places, TomTom, Supermemory, Mapbox, Google Earth Engine, and TikTok scraping infrastructure.
- Prefer mocks, fixtures, local JSON, or `scripts/test_pipelines.py` before invoking remote services.
- Do not trigger broad pipeline runs, deploys, or long GPU jobs unless the task requires them.
- Never commit secrets or real `.env` values. Use `.env.example` files only as interface references.

## Frontend guidance

- Preserve the existing product flow and visual language unless the task is explicitly a redesign.
- Keep TypeScript types explicit. Avoid introducing new `any` usage.
- Do not reintroduce Clerk assumptions in the UI or API client. The frontend no longer uses `ClerkProvider`, auth buttons, or `VITE_CLERK_PUBLISHABLE_KEY`.
- Search for the server implementation before changing frontend API assumptions. Several endpoint families are documented in the UI but are backed only by the Modal API.
- For user-scoped requests, check `frontend/src/api.ts` before editing components: it is responsible for generating/storing the local user id and attaching the `x-user-id` header.
- When changing response shapes, update `frontend/src/types`, `frontend/src/api.ts`, and affected components together.

## Backend and Modal guidance

- Preserve JSON key names unless the task explicitly changes the contract.
- Keep local user resolution compatible with the current unauthenticated flow in `backend/auth.py`: optional `x-user-id` override plus `ALEITHIA_DEFAULT_USER_ID` fallback.
- If you touch legacy Modal user settings routes, note that `modal_app/api/routes/legacy.py` still requires an explicit `x-user-id` header instead of using the backend fallback helper.
- If you touch `modal_app/api/routes/core.py`, verify the real emitted contract before adding status fields. `/status` should reflect active pipeline/GPU/cost reporting, not removed VectorDB health metadata.
- If you touch `modal_app/agents.py::regulatory_agent`, preserve the non-VectorDB path: concurrent live API fetches, dedup against cached volume docs, cached-freshness reporting, and live-result write-back.
- When adding or renaming source/document fields, update downstream readers, ranking logic, and tests in the same change.
- Avoid silent architectural cleanup outside scope. If you discover dead paths, stale messages, or inconsistencies, note them in your final response unless the task asked you to fix them.

## Agent behavior

- Make minimal, reversible edits.
- Prefer targeted tests over broad reruns.
- Do not “fix” unrelated lint or typing debt just because you touched a nearby file.
- If local reality conflicts with comments or docs, trust the code and filesystem after verifying them.
