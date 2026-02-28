"""Demographics ingester — pulls Census/ACS data for Chicago neighborhoods.

Cadence: Monthly (data updates quarterly)
Sources: US Census Bureau ACS 5-Year Estimates API
Pattern: async + FallbackChain (with key → without key → cache)
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
import modal

from modal_app.common import Document, SourceType, detect_neighborhood, safe_volume_commit, tract_to_neighborhood
from modal_app.dedup import SeenSet
from modal_app.fallback import FallbackChain
from modal_app.volume import app, volume, data_image, RAW_DATA_PATH

# Chicago FIPS: State=17 (IL), County=031 (Cook)
CHICAGO_STATE_FIPS = "17"
CHICAGO_COUNTY_FIPS = "031"

# ACS variables of interest for business intelligence
ACS_VARIABLES = {
    "B01003_001E": "total_population",
    "B19013_001E": "median_household_income",
    "B25077_001E": "median_home_value",
    "B25064_001E": "median_gross_rent",
    "B23025_005E": "unemployed",
    "B23025_002E": "labor_force",
    "B15003_022E": "bachelors_degree",
    "B15003_023E": "masters_degree",
    "B01002_001E": "median_age",
    "B25003_001E": "total_housing_units",
    "B25003_002E": "owner_occupied",
    "B25003_003E": "renter_occupied",
}


async def _fetch_census(api_key: str = "") -> list[dict]:
    """Fetch Census/ACS data for Cook County tracts."""
    docs = []
    variables = ",".join(ACS_VARIABLES.keys())
    url = "https://api.census.gov/data/2022/acs/acs5"

    params = {
        "get": f"NAME,{variables}",
        "for": "tract:*",
        "in": f"state:{CHICAGO_STATE_FIPS} county:{CHICAGO_COUNTY_FIPS}",
    }
    if api_key:
        params["key"] = api_key

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params)
        if resp.status_code != 200:
            print(f"Census API error: {resp.status_code} — {resp.text[:200]}")
            return docs

        data = resp.json()
        if not data or len(data) < 2:
            print("Census API returned no data")
            return docs

        headers = data[0]
        for row in data[1:]:
            record = dict(zip(headers, row))
            tract_name = record.get("NAME", "")
            tract_id = record.get("tract", "")

            # Map raw variables to readable names
            demographics = {}
            for var_code, var_name in ACS_VARIABLES.items():
                val = record.get(var_code)
                if val and val not in ["-666666666", "-999999999", None]:
                    try:
                        demographics[var_name] = float(val)
                    except (ValueError, TypeError):
                        demographics[var_name] = val

            # Compute derived metrics
            labor_force = demographics.get("labor_force", 0)
            unemployed = demographics.get("unemployed", 0)
            if labor_force and labor_force > 0:
                demographics["unemployment_rate"] = round(unemployed / labor_force * 100, 1)

            total_housing = demographics.get("total_housing_units", 0)
            renter = demographics.get("renter_occupied", 0)
            if total_housing and total_housing > 0:
                demographics["renter_pct"] = round(renter / total_housing * 100, 1)

            content_lines = [f"{k}: {v}" for k, v in demographics.items()]
            community_area, neighborhood = tract_to_neighborhood(tract_id)
            if not neighborhood:
                neighborhood = detect_neighborhood(tract_name)  # fallback

            docs.append({
                "id": f"demographics-tract-{CHICAGO_STATE_FIPS}{CHICAGO_COUNTY_FIPS}{tract_id}",
                "source": SourceType.DEMOGRAPHICS.value,
                "title": f"Demographics: {tract_name}",
                "content": "\n".join(content_lines),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metadata": {
                    "tract_id": tract_id,
                    "state_fips": CHICAGO_STATE_FIPS,
                    "county_fips": CHICAGO_COUNTY_FIPS,
                    "demographics": demographics,
                },
                "geo": {
                    "tract": tract_id,
                    "county": "Cook",
                    "state": "IL",
                    "community_area": community_area,
                    "neighborhood": neighborhood,
                },
            })

    print(f"Census: {len(docs)} tracts")
    return docs


async def _fetch_census_no_key() -> list[dict]:
    """Fallback: fetch Census data without API key."""
    return await _fetch_census("")


@app.function(
    image=data_image,
    volumes={"/data": volume},
    secrets=[modal.Secret.from_name("alethia-secrets")],
    timeout=180,
)
async def demographics_ingester():
    """Ingest Census/ACS demographics data for Chicago area tracts."""
    census_api_key = os.environ.get("CENSUS_API_KEY", "")

    # FallbackChain: with key → without key → cache
    chain = FallbackChain("demographics", "census_acs", cache_ttl_hours=720)
    all_docs = await chain.execute([
        lambda: _fetch_census(census_api_key),
        _fetch_census_no_key,
    ])

    if not all_docs:
        print("Demographics ingester: no data from any source")
        return 0

    # Dedup: skip already-seen documents
    seen = SeenSet("demographics")
    new_docs = [d for d in all_docs if not seen.contains(d["id"])]
    print(f"Demographics: {len(all_docs)} fetched, {len(new_docs)} new (deduped {len(all_docs) - len(new_docs)})")

    if not new_docs:
        seen.save()
        await safe_volume_commit(volume, "demographics")
        print("Demographics ingester: no new documents")
        return 0

    # Save to volume
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = Path(RAW_DATA_PATH) / "demographics" / date_str
    out_dir.mkdir(parents=True, exist_ok=True)

    for doc_data in new_docs:
        doc_data["status"] = "raw"
        doc = Document(**{k: v for k, v in doc_data.items() if k != "timestamp"})
        fpath = out_dir / f"{doc.id}.json"
        fpath.write_text(doc.model_dump_json(indent=2))
        seen.add(doc_data["id"])

    seen.save()
    await safe_volume_commit(volume, "demographics")
    print(f"Demographics ingester complete: {len(new_docs)} documents saved to {out_dir}")
    return len(new_docs)
