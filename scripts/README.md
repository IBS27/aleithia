# Scripts Index

All scripts are grouped to keep repo operations explicit.

- `scripts/bootstrap/`
  - `bootstrap_demo_data.py`
  - Safe local utility
  - Uses demo fixtures to seed `data/`
  - No external services required
  - Supported for local bootstrap

- `scripts/maintenance/`
  - `fix_data_quality.py`
  - Safe local utility (data cleanup, normalization, summaries)
  - No external services required
  - Supported for maintenance workflows

  - `seed_supermemory.py`
  - Optional maintenance utility for external RAG sync
  - Requires `SUPERMEMORY_API_KEY`; optional paid service
  - Supported when Supermemory is used

  - `sync_shared_data_to_s3.py`
  - Dry-run by default; pass `--write` to copy shared runtime data from Modal Volume to S3-compatible object storage
  - Requires Modal credentials plus `ALEITHIA_OBJECT_STORAGE_*` destination settings
  - Use after changing `ALEITHIA_SHARED_DATA_BACKEND=s3` to verify/copy `raw/`, `processed/`, `cache/`, and `dedup/`

  - `test_pipelines.py`
  - Local pipeline harness with mocked Modal runtime
  - No external services required for core test path
  - Supported for local validation

- `scripts/experiments/`
  - `generate_training_data.py`
  - Requires Modal + heavy model stack
  - Optional paid/compute-heavy workflow
  - Supported for advanced use only

  - `run_vision_from_volume.py`
  - Requires Modal volume data and vision model runtime
  - Optional and high-cost workflow
  - Use when reproducing vision experiments

  - `warmup_weights.py`
  - Downloads large model weights to Modal volume
  - Optional, high-cost/large-artifact workflow
  - Use only when needed for warm model cache

## Quick commands

- `make bootstrap-demo-data`
- `make pipeline-smoke`
- `make dev-frontend`
- `make dev-backend`
- `.venv/bin/python scripts/maintenance/sync_shared_data_to_s3.py`
