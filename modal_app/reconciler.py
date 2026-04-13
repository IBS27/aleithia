"""Self-healing reconciler + cost tracking.

Monitors pipeline freshness and auto-restarts stale pipelines.
Tracks compute costs via modal.Dict.

Modal features: modal.Dict, modal.Period (scheduling)
"""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import modal

from modal_app.costs import cost_dict, track_cost
from modal_app.volume import app, volume, base_image, RAW_DATA_PATH

# Expected freshness per source (in minutes)
FRESHNESS_THRESHOLDS = {
    "news": 60,          # Every 30 min, alert after 60
    "reddit": 120,       # Every 1 hour, alert after 2 hours
    "public_data": 1500, # Daily, alert after 25 hours
    "politics": 1500,    # Daily
    "demographics": 44640, # Monthly
    "reviews": 1500,     # Daily
    "realestate": 10800, # Weekly
    "tiktok": 1500,      # Daily, alert after 25 hours
    "traffic": 180,      # Every 1 hour, alert after 3 hours
    "cctv": 360,         # Refresh a few times per day, alert after 6 hours
    "federal_register": 1500, # Daily
}
restart_dict = modal.Dict.from_name("alethia-restarts", create_if_missing=True)


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
@track_cost("data_reconciler", "CPU")
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

    # Auto-restart stale pipelines (with backoff: max 3 restarts per source per hour)
    hour_key = now.strftime("%Y-%m-%d-%H")
    restarted = []
    skipped = []
    for source in stale_sources:
        # Check restart backoff
        backoff_key = f"{source}_{hour_key}"
        try:
            restart_count = restart_dict[backoff_key]
        except KeyError:
            restart_count = 0
        if restart_count >= 3:
            skipped.append(source)
            print(f"Reconciler: skipping {source} — restarted {restart_count}x this hour")
            continue

        try:
            if source == "news":
                from modal_app.pipelines.news import news_ingester
                await news_ingester.spawn.aio()
            elif source == "reddit":
                from modal_app.pipelines.reddit import reddit_ingester
                await reddit_ingester.spawn.aio()
            elif source == "public_data":
                from modal_app.pipelines.public_data import public_data_ingester
                await public_data_ingester.spawn.aio()
            elif source == "politics":
                from modal_app.pipelines.politics import politics_ingester
                await politics_ingester.spawn.aio()
            elif source == "demographics":
                from modal_app.pipelines.demographics import demographics_ingester
                await demographics_ingester.spawn.aio()
            elif source == "reviews":
                from modal_app.pipelines.reviews import review_ingester
                await review_ingester.spawn.aio()
            elif source == "realestate":
                from modal_app.pipelines.realestate import realestate_ingester
                await realestate_ingester.spawn.aio()
            elif source == "tiktok":
                from modal_app.pipelines.tiktok import ingest_tiktok
                ingest_tiktok.spawn()
            elif source == "federal_register":
                from modal_app.pipelines.federal_register import federal_register_ingester
                await federal_register_ingester.spawn.aio()
            elif source == "traffic":
                from modal_app.pipelines.traffic import traffic_ingester
                await traffic_ingester.spawn.aio()
            elif source == "cctv":
                from modal_app.pipelines.cctv import cctv_ingester
                await cctv_ingester.spawn.aio()
            else:
                continue
            restarted.append(source)
            restart_dict[backoff_key] = restart_count + 1
        except Exception as e:
            print(f"Failed to restart {source}: {e}")

    print(f"Reconciler: {len(stale_sources)} stale, {len(restarted)} restarted, {len(skipped)} skipped (backoff)")

    print(f"Status: {json.dumps(status_report, indent=2, default=str)}")

    return {
        "stale_sources": stale_sources,
        "restarted": restarted,
        "status": status_report,
        "costs": await get_total_cost(),
    }
