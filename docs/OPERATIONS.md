# Aleithia Operations Guide

This is the canonical setup and operations reference for this repo.

## 1) Prerequisites

- Python 3.12 recommended
- Node.js 18+ (for frontend)
- Optional: Modal CLI (`pip install modal`)
- Optional: Docker + Docker Compose

## 2) Python Environment

Use a repo-root virtualenv at `/.venv` for local Python work. This keeps `backend/`, `modal_app/`, and root `tests/` on the same local dependency surface.

Bootstrap it with:

```bash
make setup-python
```

Manual equivalent:

```bash
python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements-dev.txt
```

Do not treat Docker container dependencies as the source of truth for local pytest. The root `requirements-dev.txt` is the local test/dev entrypoint.

## 3) Environments and Secrets

The app uses a split runtime model:
- Local backend runs FastAPI (`backend/`).
- Modal provides rich AI/pipeline endpoints (`modal_app/`).
- Frontend can call Modal directly via `VITE_MODAL_URL` or fallback to local proxy `/api/data`.

Use environment variables described in:
- Root `.env.example`
- `frontend/.env.example`

Backend shared-data reads now require Modal credentials because the canonical runtime dataset lives in the Modal Volume `alethia-data`.

Recommended backend runtime setup:
- `modal setup` or an equivalent authenticated Modal profile
- optional `ALEITHIA_MODAL_VOLUME_NAME` if you are not using `alethia-data`
- optional `ALEITHIA_MODAL_ENVIRONMENT` if your workspace uses multiple Modal environments
- optional `MODAL_ENVIRONMENT` if you prefer Modal's standard environment selection mechanism

For optional paid services, set secrets only when needed (keys improve quality/rate limits).

## 4) Environments and Secrets

Canonical backend runtime data source:
- Modal Volume `alethia-data`
- logical paths inside the Volume:
  - `raw/`
  - `processed/`
  - `cache/`

Demo fixtures are under `fixtures/demo_data/` and are not read automatically. Seed local runtime when needed:

```bash
.venv/bin/python scripts/bootstrap/bootstrap_demo_data.py
```

Use `--force` to overwrite existing runtime files.

## 5) Local Runtime Data

Run backend locally from `backend/`:

```bash
cd backend
uvicorn main:app --reload
```

Default backend route prefix:
- `/api/data` (local data/user routes)

Keep doing that even when you use the root `/.venv`, because `backend/database.py` defaults to `sqlite:///./test.db`.

Important:
- backend route handlers read the canonical shared dataset from the Modal Volume through `backend/shared_data.py`
- repo-local `data/` is no longer the normal runtime source for backend shared reads
- keep `data/` only for explicit bootstrap or test workflows that intentionally use local files

## 6) Frontend

Run frontend dev server:

```bash
cd frontend
npm install
npm run dev
```

Default local frontend URL:
- `http://localhost:5173`

Set `VITE_MODAL_URL` in `frontend/.env` for direct Modal API calls. If unset, frontend falls back to `/api/data`.

## 7) Modal (Optional)

Deploy and run Modal app:

```bash
modal deploy modal_app/__init__.py
```

Run selected pipelines:

```bash
modal run -m modal_app.pipelines.news::news_ingester
modal run -m modal_app.pipelines.politics::politics_ingester
modal run -m modal_app.pipelines.traffic::traffic_ingester
```

## 8) Docker

Run local stack:

```bash
docker-compose up --build
```

Compose services:
- `backend` on port `8000`
- `frontend` on port `5173`

## 9) Scripts

- Use `scripts/README.md` for what each script is for and safety notes.
- Prefer `make bootstrap-demo-data` and `make pipeline-smoke` for common workflows (see Makefile).

## 10) Documentation Boundaries

Current operational docs:
- [README](/Users/srinivasib/Developer/aleithia/README.md)
- [AGENTS](/Users/srinivasib/Developer/aleithia/AGENTS.md)
- [frontend/.env.example](/Users/srinivasib/Developer/aleithia/frontend/.env.example)

Archived references are kept in `docs/archive/`.
