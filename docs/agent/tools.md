# Tools

## Tech Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| Local API | FastAPI | Backend data, status, metrics, profile, and query-history routes |
| Modal API | FastAPI on Modal | GPU/runtime, analysis, graph, vision, parking, social trends, and command synthesis routes |
| Data Pipelines | Modal | Scheduled and on-demand ingestion from Chicago and federal sources |
| Shared Data | Modal Volume `alethia-data` | Canonical runtime `raw/`, `processed/`, `cache/`, and `dedup/` trees |
| Frontend | React + Vite | Aleithia UI |
| Styling | Tailwind CSS | UI styling |
| Local User State | Browser localStorage + SQLite | Unauthenticated local profile and query history |

## Project Structure

```text
aleithia/
├── backend/
│   ├── main.py              # Local FastAPI app
│   ├── shared_data.py       # Shared runtime data accessors
│   ├── read_helpers.py      # Shared document filtering/transforms
│   ├── metric_helpers.py    # Shared metric calculations
│   └── routes/
│       └── data_routes.py   # Local /api/data routes
├── modal_app/
│   ├── __init__.py          # Modal deploy entrypoint
│   ├── web.py               # Modal-hosted FastAPI app
│   ├── api/                 # Modal route modules and services
│   └── pipelines/           # Ingestion and processing functions
├── frontend/
│   └── src/
│       ├── api.ts           # Frontend API ownership map
│       └── components/      # UI components
├── fixtures/
│   └── demo_data/           # Explicit local bootstrap fixtures only
├── scripts/
│   ├── bootstrap/           # Local demo-data bootstrap scripts
│   └── maintenance/         # Maintenance and migration scripts
└── tests/
```

## Commands

### Python

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

### Backend

```bash
cd backend
uvicorn main:app --reload --port 8000
```

Run backend commands from `backend/` or set `DATABASE_URL`; the default SQLite URL is relative to the current working directory.

### Frontend

```bash
cd frontend
npm install
npm run dev
npm run build
```

### Modal

```bash
modal setup
modal deploy modal_app/__init__.py
```

Set `VITE_MODAL_URL` in `frontend/.env` when the frontend should call the deployed Modal API directly. Without it, Modal-owned frontend calls fall back through `/api/data` only where the local backend implements a fallback.

## Route Ownership

| Owner | Routes |
|-------|--------|
| Local backend | `/sources`, `/summary`, `/geo`, `/news`, `/politics`, `/inspections`, `/permits`, `/licenses`, `/reddit`, `/reviews`, `/realestate`, `/tiktok`, `/status`, `/metrics`, `/user/profile`, `/user/queries` |
| Modal API | `/analyze`, `/gpu-metrics`, `/trends/*`, `/vision/*`, `/parking/*`, `/social-trends/*`, `/graph/full`, `/graph/neighborhood/*`, `/command/synthesis`, impact-brief routes |

## Data Access

Backend shared dataset reads go through `backend/shared_data.py`. Demo fixtures are never automatic runtime fallbacks; use `scripts/bootstrap/bootstrap_demo_data.py` when local fixture data is intentionally needed.
