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

from modal_app.common import SourceType, build_document, detect_neighborhood, parse_timestamp, safe_volume_commit, tract_to_neighborhood
from modal_app.dedup import SeenSet
from modal_app.fallback import FallbackChain
from modal_app.volume import app, volume, data_image, RAW_DATA_PATH, PROCESSED_DATA_PATH

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


def _safe_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_demographics_summary(docs: list[dict]) -> dict:
    """Aggregate tract-level ACS docs into community-area and city-wide summaries."""
    by_ca: dict[str, dict] = {}

    for doc in docs:
        if doc.get("source") != SourceType.DEMOGRAPHICS.value:
            continue
        geo = doc.get("geo", {})
        ca = str(geo.get("community_area", "")).strip()
        if not ca:
            continue
        demo = doc.get("metadata", {}).get("demographics", {})
        if not isinstance(demo, dict):
            continue

        stats = by_ca.setdefault(ca, {
            "_tracts": 0,
            "_population_sum": 0.0,
            "_income_weighted_sum": 0.0,
            "_rent_weighted_sum": 0.0,
            "_unemployment_weighted_sum": 0.0,
            "_renter_weighted_sum": 0.0,
            "_age_weighted_sum": 0.0,
            "total_population": 0,
            "median_household_income": 0.0,
            "median_gross_rent": 0.0,
            "unemployment_rate": 0.0,
            "renter_pct": 0.0,
            "median_age": 0.0,
            "tracts_counted": 0,
        })

        pop = _safe_float(demo.get("total_population")) or 0.0
        income = _safe_float(demo.get("median_household_income"))
        rent = _safe_float(demo.get("median_gross_rent"))
        unemployment = _safe_float(demo.get("unemployment_rate"))
        renter_pct = _safe_float(demo.get("renter_pct"))
        median_age = _safe_float(demo.get("median_age"))

        stats["_tracts"] += 1
        stats["_population_sum"] += pop
        if income is not None:
            stats["_income_weighted_sum"] += income * pop
        if rent is not None:
            stats["_rent_weighted_sum"] += rent * pop
        if unemployment is not None:
            stats["_unemployment_weighted_sum"] += unemployment * pop
        if renter_pct is not None:
            stats["_renter_weighted_sum"] += renter_pct * pop
        if median_age is not None:
            stats["_age_weighted_sum"] += median_age * pop

    for ca, stats in by_ca.items():
        pop = max(stats["_population_sum"], 1.0)
        stats["total_population"] = int(round(stats["_population_sum"]))
        stats["median_household_income"] = round(stats["_income_weighted_sum"] / pop, 1)
        stats["median_gross_rent"] = round(stats["_rent_weighted_sum"] / pop, 1)
        stats["unemployment_rate"] = round(stats["_unemployment_weighted_sum"] / pop, 1)
        stats["renter_pct"] = round(stats["_renter_weighted_sum"] / pop, 1)
        stats["median_age"] = round(stats["_age_weighted_sum"] / pop, 1)
        stats["tracts_counted"] = stats["_tracts"]

        for k in [key for key in stats.keys() if key.startswith("_")]:
            del stats[k]

    city = {
        "total_population": 0,
        "median_household_income": 0.0,
        "median_gross_rent": 0.0,
        "unemployment_rate": 0.0,
        "renter_pct": 0.0,
        "median_age": 0.0,
        "tracts_counted": 0,
    }
    if by_ca:
        city_pop = sum(v["total_population"] for v in by_ca.values())
        city_pop_safe = max(city_pop, 1)
        city["total_population"] = city_pop
        city["median_household_income"] = round(
            sum(v["median_household_income"] * v["total_population"] for v in by_ca.values()) / city_pop_safe, 1
        )
        city["median_gross_rent"] = round(
            sum(v["median_gross_rent"] * v["total_population"] for v in by_ca.values()) / city_pop_safe, 1
        )
        city["unemployment_rate"] = round(
            sum(v["unemployment_rate"] * v["total_population"] for v in by_ca.values()) / city_pop_safe, 1
        )
        city["renter_pct"] = round(
            sum(v["renter_pct"] * v["total_population"] for v in by_ca.values()) / city_pop_safe, 1
        )
        city["median_age"] = round(
            sum(v["median_age"] * v["total_population"] for v in by_ca.values()) / city_pop_safe, 1
        )
        city["tracts_counted"] = sum(v["tracts_counted"] for v in by_ca.values())

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "by_community_area": by_ca,
        "city_wide": city,
    }


def _dedupe_latest_demographics_docs(docs: list[dict]) -> list[dict]:
    """Keep one latest record per demographics document ID."""
    latest_by_id: dict[str, tuple[dict, float]] = {}

    for doc in docs:
        if doc.get("source") != SourceType.DEMOGRAPHICS.value:
            continue
        doc_id = str(doc.get("id", "")).strip()
        if not doc_id:
            continue

        metadata = doc.get("metadata", {}) or {}
        ts = (
            parse_timestamp(doc.get("timestamp"))
            or parse_timestamp(metadata.get("ingested_at"))
            or datetime.fromtimestamp(0, tz=timezone.utc)
        )
        epoch = ts.timestamp()

        existing = latest_by_id.get(doc_id)
        if existing is None or epoch > existing[1]:
            latest_by_id[doc_id] = (doc, epoch)

    return [entry[0] for entry in latest_by_id.values()]


def _write_demographics_summary() -> None:
    raw_dir = Path(RAW_DATA_PATH) / "demographics"
    docs = []
    if raw_dir.exists():
        for jf in raw_dir.rglob("*.json"):
            try:
                parsed = json.loads(jf.read_text())
                if isinstance(parsed, dict):
                    docs.append(parsed)
            except Exception:
                continue

    summary_docs = _dedupe_latest_demographics_docs(docs)
    summary = _build_demographics_summary(summary_docs)
    out_path = Path(PROCESSED_DATA_PATH) / "demographics_summary.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2))


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
    new_docs = [d for d in all_docs if not seen.contains(d["id"], max_age_hours=720)]
    print(f"Demographics: {len(all_docs)} fetched, {len(new_docs)} new (deduped {len(all_docs) - len(new_docs)})")

    if not new_docs:
        seen.save()
        _write_demographics_summary()
        await safe_volume_commit(volume, "demographics")
        print("Demographics ingester: no new documents")
        return 0

    # Save to volume
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = Path(RAW_DATA_PATH) / "demographics" / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    ingested_at = datetime.now(timezone.utc).isoformat()

    for doc_data in new_docs:
        doc_data["status"] = "raw"
        doc_data.setdefault("metadata", {})["ingested_at"] = ingested_at
        doc = build_document(doc_data)
        fpath = out_dir / f"{doc.id}.json"
        fpath.write_text(doc.model_dump_json(indent=2))
        seen.add(doc_data["id"])

    seen.save()
    _write_demographics_summary()
    await safe_volume_commit(volume, "demographics")
    print(f"Demographics ingester complete: {len(new_docs)} documents saved to {out_dir}")
    return len(new_docs)
