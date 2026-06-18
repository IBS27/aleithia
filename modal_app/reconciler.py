"""Self-healing reconciler + cost tracking.

Monitors pipeline freshness and auto-restarts stale pipelines.
Tracks compute costs via modal.Dict.

Modal features: modal.Dict, modal.Period (scheduling)
"""
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import modal

from backend.shared_data import get_source_freshness_statuses
from modal_app.costs import cost_dict, track_cost
from modal_app.volume import app, volume, base_image

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
reconciler_state = modal.Dict.from_name("alethia-reconciler-state", create_if_missing=True)

# Cooldowns are intentionally longer than the 5-minute scheduler period. The
# heartbeat files written by ingesters end cooldown early by making the source
# fresh; otherwise this acts as an in-flight lease for slow/failing jobs.
RESTART_COOLDOWN_MINUTES = {
    "news": 30,
    "reddit": 60,
    "public_data": 12 * 60,
    "politics": 12 * 60,
    "demographics": 24 * 60,
    "reviews": 12 * 60,
    "realestate": 24 * 60,
    "tiktok": 24 * 60,
    "traffic": 60,
    "cctv": 6 * 60,
    "federal_register": 12 * 60,
}

TIKTOK_RECONCILER_QUERY_SPECS = [
    {
        "query": "chicago small business",
        "limit": 1,
        "scope": "city",
        "business_type": "small business",
        "neighborhood": "",
    }
]


def _parse_iso_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


async def _dict_get(dictionary: modal.Dict, key: str, default: Any = None) -> Any:
    try:
        value = await dictionary.get.aio(key)
    except Exception:
        return default
    return default if value is None else value


async def _dict_put(dictionary: modal.Dict, key: str, value: Any) -> None:
    await dictionary.put.aio(key, value)


async def _spawn_source(source: str) -> None:
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
        await ingest_tiktok.spawn.aio(
            query_specs=TIKTOK_RECONCILER_QUERY_SPECS,
            max_videos=1,
            transcribe=False,
        )
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
        raise ValueError(f"unknown source: {source}")


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
    secrets=[modal.Secret.from_name("alethia-secrets")],
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
    source_stats = get_source_freshness_statuses(FRESHNESS_THRESHOLDS.keys())

    for source, threshold_minutes in FRESHNESS_THRESHOLDS.items():
        stats = source_stats.get(source, {})
        last_update = _parse_iso_timestamp(stats.get("last_update"))
        doc_count = int(stats.get("doc_count") or 0)
        if last_update is None:
            stale_sources.append(source)
            status_report[source] = {
                "state": "empty",
                "last_update": None,
                "doc_count": doc_count,
                "last_status": stats.get("last_status"),
            }
            continue

        age_minutes = (now - last_update).total_seconds() / 60

        if age_minutes > threshold_minutes:
            stale_sources.append(source)
            status_report[source] = {
                "state": "stale",
                "last_update": last_update.isoformat(),
                "age_minutes": round(age_minutes),
                "threshold": threshold_minutes,
                "doc_count": doc_count,
                "last_status": stats.get("last_status"),
            }
        else:
            status_report[source] = {
                "state": "fresh",
                "last_update": last_update.isoformat(),
                "age_minutes": round(age_minutes),
                "doc_count": doc_count,
                "last_status": stats.get("last_status"),
            }

    # Auto-restart stale pipelines, guarded by per-source leases/cooldowns.
    hour_key = now.strftime("%Y-%m-%d-%H")
    restarted = []
    skipped = []
    for source in stale_sources:
        state_key = f"source:{source}"
        state = await _dict_get(reconciler_state, state_key, {})
        lease_until = _parse_iso_timestamp(state.get("lease_until")) if isinstance(state, dict) else None
        if lease_until and lease_until > now:
            skipped.append({"source": source, "reason": "cooldown", "lease_until": lease_until.isoformat()})
            print(f"Reconciler: skipping {source} — lease active until {lease_until.isoformat()}")
            continue

        backoff_key = f"{source}_{hour_key}"
        restart_count = int(await _dict_get(restart_dict, backoff_key, 0) or 0)
        if restart_count >= 3:
            skipped.append({"source": source, "reason": "hourly_backoff", "restart_count": restart_count})
            print(f"Reconciler: skipping {source} — restarted {restart_count}x this hour")
            continue

        cooldown_minutes = RESTART_COOLDOWN_MINUTES.get(source, max(30, FRESHNESS_THRESHOLDS[source] // 2))
        lease_until = now + timedelta(minutes=cooldown_minutes)
        lease_payload = {
            "source": source,
            "last_started_at": now.isoformat(),
            "lease_until": lease_until.isoformat(),
            "hour_key": hour_key,
            "restart_count": restart_count + 1,
        }
        try:
            await _dict_put(reconciler_state, state_key, lease_payload)
            await _spawn_source(source)
            restarted.append(source)
            await _dict_put(restart_dict, backoff_key, restart_count + 1)
        except Exception as e:
            failure_lease_until = now + timedelta(minutes=15)
            await _dict_put(
                reconciler_state,
                state_key,
                {
                    **lease_payload,
                    "lease_until": failure_lease_until.isoformat(),
                    "last_error": str(e),
                },
            )
            print(f"Failed to restart {source}: {e}")

    print(f"Reconciler: {len(stale_sources)} stale, {len(restarted)} restarted, {len(skipped)} skipped")

    print(f"Status: {json.dumps(status_report, indent=2, default=str)}")

    return {
        "stale_sources": stale_sources,
        "restarted": restarted,
        "skipped": skipped,
        "status": status_report,
        "costs": await get_total_cost(),
    }
