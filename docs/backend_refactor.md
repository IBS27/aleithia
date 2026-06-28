# Backend Refactor Status

This document records the current ownership split after the backend refactor. It is not a migration checklist.

## Current Ownership

| Owner | Responsibility |
|-------|----------------|
| `backend/` | Local FastAPI app, shared dataset reads, document/source freshness, lightweight read-only routes, user profile, and query history |
| `modal_app/` | Modal-hosted API, GPU/runtime status, heavy analysis, graph, vision, parking, social trends, command synthesis, impact briefs, and scheduled pipelines |

## Backend-Owned Routes

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
- `/status`
- `/metrics`
- `/user/profile`
- `/user/queries`

## Shared Data

- The canonical runtime dataset is the Modal Volume `alethia-data`.
- Backend shared reads go through `backend/shared_data.py`.
- Shared filter and metric logic lives in `backend/read_helpers.py` and `backend/metric_helpers.py`.
- Demo fixtures live under `fixtures/demo_data/` and are only copied into a local runtime tree by explicit bootstrap scripts.

## Local Development

- Use the repo-root `.venv`.
- Install local development dependencies from `requirements-dev.txt`.
- Run backend commands from `backend/` or set `DATABASE_URL` explicitly, because the default SQLite URL is relative to the current working directory.
- Use `scripts/bootstrap/bootstrap_demo_data.py` only when local fixture data is intentionally needed.
