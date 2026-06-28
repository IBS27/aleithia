# AGENTS.md

## Architecture

- The repo has two API surfaces:
  - `backend/main.py` serves local `/api/data` routes.
  - `modal_app/web.py` serves the Modal-hosted API.
- Check `frontend/src/api.ts` before moving or adding routes. Do not put a route in `backend/` when the frontend is meant to call Modal.
- New Modal functions/endpoints must be imported from `modal_app/__init__.py` so `modal deploy modal_app/__init__.py` discovers them.
- Modal `/status` is runtime/GPU/cost status. Backend `/status` and `/metrics` are document/source freshness.

## Data

- Backend shared dataset reads must go through `backend/shared_data.py`.
- The canonical runtime dataset is the Modal Volume `alethia-data`.
- Do not add runtime fallbacks to repo `data/`, `backend/data/`, or `fixtures/demo_data/`.
- Generated runtime files must not be committed under `data/`.

## CCTV

- Treat CCTV/vision flows as Modal-owned unless current code proves otherwise.
- When `ENABLE_CCTV_ANALYSIS=false`, Modal may serve synthetic CCTV analytics; do not assume they correspond to a real analyzed frame.
- `ENABLE_CCTV_ANALYSIS` comes from the Modal secret `alethia-secrets`; env-gated Modal functions/classes need that secret mounted.

## Local User State

- The app is unauthenticated locally. Frontend calls attach `x-user-id`; `backend/auth.py` falls back to `ALEITHIA_DEFAULT_USER_ID`.

## Local Dev

- Use repo-root `.venv` with Python 3.12 and `requirements-dev.txt`.
- Run backend commands from `backend/` or set `DATABASE_URL`; SQLite defaults to `sqlite:///./test.db`.

## Instructions for writing HTML documents when asked by the user

- When I ask for an HTML document, create or edit a `.html` file, usually in `docs/` unless I specify another path.
- Treat the HTML file as a readable document, similar to a Markdown brief, but with better layout and navigation.
- Keep the writing plain and concrete. Avoid vague language, hype, filler, and generic AI-sounding phrasing.
- Prefer short sections, direct headings, bullets, tables, and examples over long paragraphs.
- Make the document self-contained: inline CSS, no unnecessary JavaScript, no external assets unless requested.
- Use semantic HTML and make it responsive enough to read on desktop and mobile.
