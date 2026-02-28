"""Public data ingester — pulls structured data from Chicago Data Portal (Socrata API).

Cadence: Daily
Sources: data.cityofchicago.org — business licenses, food inspections,
         building permits, crimes, CTA ridership
Pattern: async + FallbackChain (with token → without token → cache) + gather_with_limit
"""
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx
import modal

from modal_app.common import (
    Document, SourceType, SOCRATA_DATASETS, COMMUNITY_AREA_MAP,
    detect_neighborhood, gather_with_limit,
)
from modal_app.fallback import FallbackChain
from modal_app.volume import app, volume, data_image, RAW_DATA_PATH

SOCRATA_BASE = "https://data.cityofchicago.org/resource"

# Dataset-specific date fields for filtering recent records
DATE_FIELDS = {
    "business_licenses": "date_issued",
    "food_inspections": "inspection_date",
    "building_permits": "issue_date",
    "crimes": "date",
    "cta_ridership_L": "service_date",
    "cta_ridership_bus": "date",
}


async def _fetch_dataset(
    dataset_id: str,
    dataset_name: str,
    date_field: str | None = None,
    since_days: int = 7,
    limit: int = 200,
    app_token: str = "",
) -> list[dict]:
    """Fetch records from a single Socrata dataset."""
    docs = []
    url = f"{SOCRATA_BASE}/{dataset_id}.json"

    params: dict = {"$limit": limit, "$order": ":id DESC"}
    headers = {}

    if app_token:
        headers["X-App-Token"] = app_token

    if date_field:
        since = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%Y-%m-%dT%H:%M:%S")
        params["$where"] = f"{date_field} > '{since}'"

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params, headers=headers)
        if resp.status_code != 200:
            print(f"Socrata [{dataset_name}] error: {resp.status_code} — {resp.text[:200]}")
            return docs

        records = resp.json()
        for i, record in enumerate(records):
            content_parts = []
            for key, value in record.items():
                if value and not key.startswith(":") and not key.startswith("@"):
                    content_parts.append(f"{key}: {value}")

            # Map community area number to canonical name
            community_area = record.get("community_area", "")
            neighborhood = ""
            try:
                area_num = int(community_area)
                neighborhood = COMMUNITY_AREA_MAP.get(area_num, "")
            except (ValueError, TypeError):
                neighborhood = detect_neighborhood(str(record.get("address", "")))

            docs.append({
                "id": f"public-{dataset_name}-{record.get(':id', i)}",
                "source": SourceType.PUBLIC_DATA.value,
                "title": f"{dataset_name.replace('_', ' ').title()} Record",
                "content": "\n".join(content_parts[:20]),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metadata": {
                    "dataset": dataset_name,
                    "dataset_id": dataset_id,
                    "raw_record": {k: v for k, v in list(record.items())[:15]},
                },
                "geo": {
                    "lat": record.get("latitude"),
                    "lng": record.get("longitude"),
                    "neighborhood": neighborhood,
                    "ward": record.get("ward", ""),
                    "community_area": community_area,
                },
            })

    return docs


async def _fetch_all_with_token(app_token: str) -> list[dict]:
    """Fetch all datasets in parallel with Socrata app token."""
    coros = [
        _fetch_dataset(
            dataset_id=dataset_id,
            dataset_name=name,
            date_field=DATE_FIELDS.get(name),
            since_days=7,
            limit=100,
            app_token=app_token,
        )
        for name, dataset_id in SOCRATA_DATASETS.items()
    ]
    results = await gather_with_limit(coros, max_concurrent=5)
    docs = []
    for result in results:
        if result:
            docs.extend(result)
    return docs


async def _fetch_all_without_token() -> list[dict]:
    """Fallback: fetch all datasets without app token (lower rate limits)."""
    return await _fetch_all_with_token("")


@app.function(
    image=data_image,
    volumes={"/data": volume},
    secrets=[modal.Secret.from_name("alethia-secrets")],
    schedule=modal.Period(days=1),
    timeout=300,
)
async def public_data_ingester():
    """Ingest public data from Chicago Data Portal via Socrata API."""
    app_token = os.environ.get("SOCRATA_APP_TOKEN", "")

    # FallbackChain: with token → without token → cache
    chain = FallbackChain("public_data", "all_datasets")
    all_docs = await chain.execute([
        lambda: _fetch_all_with_token(app_token),
        _fetch_all_without_token,
    ])

    if not all_docs:
        print("Public data ingester: no data from any source")
        return 0

    # Log per-dataset counts
    dataset_counts: dict[str, int] = {}
    for doc in all_docs:
        ds = doc.get("metadata", {}).get("dataset", "unknown")
        dataset_counts[ds] = dataset_counts.get(ds, 0) + 1
    for ds, count in dataset_counts.items():
        print(f"Socrata [{ds}]: {count} records")

    # Save to volume
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = Path(RAW_DATA_PATH) / "public_data" / date_str
    out_dir.mkdir(parents=True, exist_ok=True)

    for doc_data in all_docs:
        doc = Document(**{k: v for k, v in doc_data.items() if k != "timestamp"})
        fpath = out_dir / f"{doc.id}.json"
        fpath.write_text(doc.model_dump_json(indent=2))

    volume.commit()
    print(f"Public data ingester complete: {len(all_docs)} documents saved to {out_dir}")
    return len(all_docs)
