"""Pipeline: WorldPop demographic data via Google Earth Engine.

Pulls WorldPop GP/100m/pop_age_sex data for Chicago neighborhoods,
aggregates population by age group and sex per neighborhood,
and writes to /data/raw/demographics/.

Dataset: WorldPop/GP/100m/pop_age_sex (2020, 100m resolution)
Bands: M_0, M_1, M_5, M_10, ... M_80 (male by age group)
       F_0, F_1, F_5, F_10, ... F_80 (female by age group)
       population (total)

Requires: earthengine-api, google-auth
EE auth: use a service account key stored in Modal secrets.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
import hashlib

import modal

from modal_app.common import SourceType, build_document
from modal_app.volume import app, volume, VOLUME_MOUNT, RAW_DATA_PATH

# ---------- Image with Earth Engine SDK ----------
ee_image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "earthengine-api>=1.4",
    "google-auth>=2.0",
)

# ---------- Chicago neighborhood boundaries (centroids + approximate bboxes) ----------
# Each entry: (lat, lon, radius_m) — used to create circular ROIs for each neighborhood
# In production you'd use actual polygon boundaries from Chicago's open data
NEIGHBORHOOD_ROIS = {
    "Loop":              (41.8819, -87.6278, 1500),
    "Near North Side":   (41.8992, -87.6310, 1800),
    "Lincoln Park":      (41.9214, -87.6474, 2000),
    "Lakeview":          (41.9435, -87.6537, 1800),
    "Uptown":            (41.9681, -87.6547, 1500),
    "West Town":         (41.8973, -87.6730, 1800),
    "Wicker Park":       (41.9088, -87.6796, 1200),
    "Logan Square":      (41.9234, -87.7082, 2000),
    "Pilsen":            (41.8525, -87.6615, 1500),
    "Hyde Park":         (41.7943, -87.5914, 1800),
    "Bronzeville":       (41.8232, -87.6179, 1500),
    "Bridgeport":        (41.8366, -87.6510, 1500),
    "Chinatown":         (41.8516, -87.6340, 800),
    "South Loop":        (41.8569, -87.6248, 1200),
    "West Loop":         (41.8845, -87.6520, 1200),
    "River North":       (41.8920, -87.6350, 1000),
    "Ravenswood":        (41.9745, -87.6743, 1500),
    "Rogers Park":       (42.0090, -87.6695, 1500),
    "Andersonville":     (41.9801, -87.6685, 1000),
    "Edgewater":         (41.9839, -87.6600, 1500),
    "Humboldt Park":     (41.9020, -87.7207, 2000),
    "Avondale":          (41.9389, -87.7107, 1500),
    "Irving Park":       (41.9541, -87.7365, 2000),
    "Albany Park":        (41.9681, -87.7234, 1500),
    "Bucktown":          (41.9209, -87.6803, 1200),
    "Ukrainian Village": (41.8990, -87.6890, 1000),
    "Old Town":          (41.9103, -87.6386, 1000),
    "Gold Coast":        (41.9048, -87.6270, 800),
    "Streeterville":     (41.8925, -87.6175, 1000),
    "Kenwood":           (41.8099, -87.5930, 1200),
    "Woodlawn":          (41.7796, -87.5963, 1500),
    "South Shore":       (41.7608, -87.5753, 1800),
    "Austin":            (41.8943, -87.7649, 2500),
    "Garfield Park":     (41.8808, -87.7242, 2000),
    "Englewood":         (41.7800, -87.6449, 2000),
    "Back of the Yards":  (41.8096, -87.6577, 1500),
    "Little Village":    (41.8444, -87.7105, 1500),
    "Brighton Park":     (41.8191, -87.6977, 1500),
}

# Age bands available in WorldPop/GP/100m/pop_age_sex
AGE_BANDS = [0, 1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80]

# Grouped for business intelligence purposes
AGE_GROUPS = {
    "children_0_14":      [0, 1, 5, 10],
    "young_adults_15_29":  [15, 20, 25],
    "adults_30_44":        [30, 35, 40],
    "middle_aged_45_64":   [45, 50, 55, 60],
    "seniors_65_plus":     [65, 70, 75, 80],
}


def _init_ee():
    """Initialize Earth Engine with service account credentials."""
    import ee
    import json as _json
    import os

    # Option 1: Service account JSON in Modal secret
    sa_key = os.environ.get("GEE_SERVICE_ACCOUNT_KEY", "")
    if sa_key:
        key_data = _json.loads(sa_key)
        credentials = ee.ServiceAccountCredentials(
            key_data["client_email"],
            key_data=sa_key,
        )
        ee.Initialize(credentials=credentials, project=key_data.get("project_id"))
        return

    # Option 2: Application default credentials (for local dev)
    ee.Authenticate()
    ee.Initialize(project=os.environ.get("GEE_PROJECT", ""))


def _extract_neighborhood_demographics(neighborhood: str, lat: float, lon: float, radius: float) -> dict:
    """Query WorldPop for a single neighborhood and return demographic breakdown."""
    import ee

    # Create circular region of interest
    point = ee.Geometry.Point(lon, lat)
    roi = point.buffer(radius)

    # Load WorldPop age/sex dataset — 2020 data for USA
    worldpop = (
        ee.ImageCollection("WorldPop/GP/100m/pop_age_sex")
        .filterMetadata("country", "equals", "USA")
        .filterDate("2020-01-01", "2021-01-01")
        .first()
    )

    if worldpop is None:
        return {"error": "No WorldPop data found for USA 2020"}

    # Extract total population
    total_pop = worldpop.select("population").reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=roi,
        scale=100,
        maxPixels=1e8,
    ).getInfo()

    # Extract each age/sex band
    male_counts = {}
    female_counts = {}
    for age in AGE_BANDS:
        m_band = f"M_{age}"
        f_band = f"F_{age}"

        result = worldpop.select([m_band, f_band]).reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=roi,
            scale=100,
            maxPixels=1e8,
        ).getInfo()

        male_counts[age] = round(result.get(m_band, 0) or 0)
        female_counts[age] = round(result.get(f_band, 0) or 0)

    # Aggregate into business-relevant age groups
    age_groups = {}
    for group_name, ages in AGE_GROUPS.items():
        m_total = sum(male_counts.get(a, 0) for a in ages)
        f_total = sum(female_counts.get(a, 0) for a in ages)
        age_groups[group_name] = {
            "male": m_total,
            "female": f_total,
            "total": m_total + f_total,
        }

    total_male = sum(male_counts.values())
    total_female = sum(female_counts.values())

    return {
        "total_population": round(total_pop.get("population", 0) or 0),
        "total_male": total_male,
        "total_female": total_female,
        "sex_ratio": round(total_male / max(total_female, 1), 3),
        "age_groups": age_groups,
        "age_detail": {
            "male": {str(k): v for k, v in male_counts.items()},
            "female": {str(k): v for k, v in female_counts.items()},
        },
        # Business-relevant derived metrics
        "working_age_pct": round(
            sum(
                age_groups[g]["total"]
                for g in ["young_adults_15_29", "adults_30_44", "middle_aged_45_64"]
            )
            / max(sum(ag["total"] for ag in age_groups.values()), 1)
            * 100,
            1,
        ),
        "young_adult_pct": round(
            age_groups["young_adults_15_29"]["total"]
            / max(sum(ag["total"] for ag in age_groups.values()), 1)
            * 100,
            1,
        ),
        "median_age_bucket": _estimate_median_bucket(age_groups),
    }


def _estimate_median_bucket(age_groups: dict) -> str:
    """Rough estimate of which age group contains the median."""
    total = sum(ag["total"] for ag in age_groups.values())
    half = total / 2
    running = 0
    for group_name, data in age_groups.items():
        running += data["total"]
        if running >= half:
            return group_name
    return "unknown"


@app.function(
    image=ee_image,
    volumes={"/data": volume},
    secrets=[modal.Secret.from_name("alethia-secrets")],
    timeout=600,
)
def ingest_worldpop_demographics():
    """Pull WorldPop age/sex demographics for all Chicago neighborhoods.

    Writes one JSON file per neighborhood to /data/raw/demographics/worldpop/
    in the standard Alethia document format.
    """
    _init_ee()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = Path(RAW_DATA_PATH) / "worldpop" / today
    out_dir.mkdir(parents=True, exist_ok=True)

    results = {}
    errors = []

    for neighborhood, (lat, lon, radius) in NEIGHBORHOOD_ROIS.items():
        try:
            print(f"[WorldPop] Querying {neighborhood}...")
            demo = _extract_neighborhood_demographics(neighborhood, lat, lon, radius)

            # Build standard Alethia document format
            doc_id = hashlib.md5(f"worldpop-{neighborhood}-2020".encode()).hexdigest()[:12]
            doc = {
                "id": f"worldpop-{doc_id}",
                "title": f"WorldPop Demographics — {neighborhood}",
                "content": (
                    f"Population estimate for {neighborhood}: {demo['total_population']:,} residents. "
                    f"{demo['working_age_pct']}% working age, {demo['young_adult_pct']}% young adults (15-29). "
                    f"Sex ratio (M/F): {demo['sex_ratio']}."
                ),
                "source": SourceType.WORLDPOP.value,
                "timestamp": f"2020-01-01T00:00:00Z",
                "geo": {
                    "neighborhood": neighborhood,
                    "lat": lat,
                    "lng": lon,
                    "lon": lon,
                    "city": "Chicago",
                    "state": "IL",
                },
                "metadata": {
                    "dataset": "worldpop_age_sex",
                    "resolution": "100m",
                    "year": 2020,
                    "source_collection": "WorldPop/GP/100m/pop_age_sex",
                    "demographics": demo,
                    "ingested_at": datetime.now(timezone.utc).isoformat(),
                },
                "status": "raw",
            }

            # Write to volume
            out_path = out_dir / f"{neighborhood.lower().replace(' ', '_')}.json"
            out_path.write_text(build_document(doc).model_dump_json(indent=2))

            results[neighborhood] = {
                "population": demo["total_population"],
                "working_age_pct": demo["working_age_pct"],
            }
            print(f"[WorldPop] {neighborhood}: pop={demo['total_population']:,}, working_age={demo['working_age_pct']}%")

        except Exception as e:
            print(f"[WorldPop] ERROR {neighborhood}: {e}")
            errors.append({"neighborhood": neighborhood, "error": str(e)})

    volume.commit()

    print(f"\n[WorldPop] Complete: {len(results)} neighborhoods, {len(errors)} errors")
    return {"results": results, "errors": errors}


@app.function(
    image=ee_image,
    volumes={"/data": volume},
    secrets=[modal.Secret.from_name("alethia-secrets")],
    timeout=120,
)
def query_neighborhood_demographics(neighborhood: str) -> dict:
    """On-demand query for a single neighborhood's demographics.

    Can be called from agents or API endpoints.
    """
    _init_ee()

    roi = NEIGHBORHOOD_ROIS.get(neighborhood)
    if not roi:
        return {"error": f"Unknown neighborhood: {neighborhood}"}

    lat, lon, radius = roi
    return _extract_neighborhood_demographics(neighborhood, lat, lon, radius)
