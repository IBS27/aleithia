"""Self-healing reconciler + cost tracking.

Monitors pipeline freshness and auto-restarts stale pipelines.
Tracks compute costs via modal.Dict.

Modal features: modal.Dict, modal.Period (scheduling)
"""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import modal

from modal_app.volume import app, volume, base_image, RAW_DATA_PATH

# GPU cost rates (per second)
COST_RATES = {
    "H100": 0.001389,
    "A100-80GB": 0.001042,
    "A10G": 0.000306,
    "T4": 0.000164,
    "CPU": 0.0000125,
}

# Expected freshness per source (in minutes)
FRESHNESS_THRESHOLDS = {
    "news": 60,         # Every 30 min, alert after 60
    "reddit": 120,      # Every 1 hour, alert after 2 hours
    "public_data": 1500, # Daily, alert after 25 hours
    "politics": 1500,   # Daily
    "demographics": 44640, # Monthly
    "reviews": 1500,    # Daily
    "realestate": 10800, # Weekly
}

cost_dict = modal.Dict.from_name("alethia-costs", create_if_missing=True)


def log_cost(function_name: str, gpu: str, duration_seconds: float):
    """Log compute cost for a function execution."""
    rate = COST_RATES.get(gpu, COST_RATES["CPU"])
    cost = rate * duration_seconds

    key = f"{function_name}_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    try:
        existing = cost_dict[key]
        cost_dict[key] = {
            "total_cost": existing.get("total_cost", 0) + cost,
            "total_seconds": existing.get("total_seconds", 0) + duration_seconds,
            "invocations": existing.get("invocations", 0) + 1,
            "gpu": gpu,
            "function": function_name,
        }
    except KeyError:
        cost_dict[key] = {
            "total_cost": cost,
            "total_seconds": duration_seconds,
            "invocations": 1,
            "gpu": gpu,
            "function": function_name,
        }


async def get_total_cost() -> dict:
    """Get total accumulated cost across all functions."""
    total = 0.0
    breakdown = {}
    try:
        async for key in cost_dict.keys.aio():
            entry = await cost_dict.get.aio(key)
            if entry is None:
                continue
            total += entry.get("total_cost", 0)
            fn = entry.get("function", "unknown")
            breakdown[fn] = breakdown.get(fn, 0) + entry.get("total_cost", 0)
    except Exception:
        pass

    return {
        "total_cost_usd": round(total, 4),
        "breakdown": {k: round(v, 4) for k, v in breakdown.items()},
    }


@app.function(
    image=base_image,
    volumes={"/data": volume},
    schedule=modal.Period(minutes=5),
    timeout=120,
)
async def data_reconciler():
    """Self-healing pipeline reconciler.

    Checks freshness per source, auto-spawns stale pipelines.
    """
    now = datetime.now(timezone.utc)
    stale_sources = []
    status_report = {}

    for source, threshold_minutes in FRESHNESS_THRESHOLDS.items():
        source_dir = Path(RAW_DATA_PATH) / source
        if not source_dir.exists():
            stale_sources.append(source)
            status_report[source] = {"state": "missing", "last_update": None}
            continue

        json_files = list(source_dir.rglob("*.json"))
        if not json_files:
            stale_sources.append(source)
            status_report[source] = {"state": "empty", "last_update": None}
            continue

        latest = max(json_files, key=lambda f: f.stat().st_mtime)
        last_update = datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc)
        age_minutes = (now - last_update).total_seconds() / 60

        if age_minutes > threshold_minutes:
            stale_sources.append(source)
            status_report[source] = {
                "state": "stale",
                "last_update": last_update.isoformat(),
                "age_minutes": round(age_minutes),
                "threshold": threshold_minutes,
            }
        else:
            status_report[source] = {
                "state": "fresh",
                "last_update": last_update.isoformat(),
                "age_minutes": round(age_minutes),
                "doc_count": len(json_files),
            }

    # Auto-restart stale pipelines
    restarted = []
    for source in stale_sources:
        try:
            if source == "news":
                from modal_app.pipelines.news import news_ingester
                await news_ingester.spawn.aio()
                restarted.append(source)
            elif source == "reddit":
                from modal_app.pipelines.reddit import reddit_ingester
                await reddit_ingester.spawn.aio()
                restarted.append(source)
            elif source == "public_data":
                from modal_app.pipelines.public_data import public_data_ingester
                await public_data_ingester.spawn.aio()
                restarted.append(source)
            elif source == "politics":
                from modal_app.pipelines.politics import politics_ingester
                await politics_ingester.spawn.aio()
                restarted.append(source)
        except Exception as e:
            print(f"Failed to restart {source}: {e}")

    print(f"Reconciler: {len(stale_sources)} stale, {len(restarted)} restarted")
    print(f"Status: {json.dumps(status_report, indent=2, default=str)}")

    return {
        "stale_sources": stale_sources,
        "restarted": restarted,
        "status": status_report,
        "costs": await get_total_cost(),
    }
