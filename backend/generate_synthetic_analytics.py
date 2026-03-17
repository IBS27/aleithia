"""
Generate realistic synthetic CCTV analytics data per Chicago neighborhood.

Produces data/processed/cctv/synthetic_analytics.json with per-neighborhood
CCTVData (cameras) and CCTVTimeseries (24h hourly buckets) that match
the shapes consumed by the frontend.

Usage:
    python backend/generate_synthetic_analytics.py
"""

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone

from shared_data import get_processed_data_dir

# ---------------------------------------------------------------------------
# Neighborhood centroids (copied from modal_app/common.py to keep standalone)
# ---------------------------------------------------------------------------
NEIGHBORHOOD_CENTROIDS: dict[str, tuple[float, float]] = {
    "Albany Park": (41.9684, -87.7244),
    "Andersonville": (41.9800, -87.6685),
    "Avondale": (41.9387, -87.7112),
    "Beverly": (41.7220, -87.6753),
    "Boystown": (41.9456, -87.6498),
    "Bridgeport": (41.8381, -87.6513),
    "Bronzeville": (41.8169, -87.6185),
    "Bucktown": (41.9217, -87.6796),
    "Chatham": (41.7410, -87.6128),
    "Chinatown": (41.8517, -87.6338),
    "Douglas": (41.8353, -87.6185),
    "Edgewater": (41.9833, -87.6607),
    "Irving Park": (41.9531, -87.7244),
    "Kenwood": (41.8095, -87.5936),
    "Gold Coast": (41.9048, -87.6279),
    "Humboldt Park": (41.9025, -87.7209),
    "Hyde Park": (41.7943, -87.5907),
    "Little Italy": (41.8687, -87.6600),
    "Lakeview": (41.9434, -87.6553),
    "Lincoln Park": (41.9214, -87.6513),
    "Lincoln Square": (41.9688, -87.6891),
    "Little Village": (41.8445, -87.7134),
    "Logan Square": (41.9233, -87.7083),
    "Loop": (41.8819, -87.6278),
    "Morgan Park": (41.6906, -87.6667),
    "Near North Side": (41.9003, -87.6345),
    "Near West Side": (41.8817, -87.6655),
    "North Center": (41.9548, -87.6790),
    "North Lawndale": (41.8600, -87.7200),
    "Old Town": (41.9112, -87.6380),
    "Pilsen": (41.8525, -87.6614),
    "Pullman": (41.6943, -87.6083),
    "River North": (41.8921, -87.6349),
    "Rogers Park": (42.0087, -87.6680),
    "South Loop": (41.8569, -87.6258),
    "Streeterville": (41.8929, -87.6178),
    "Ukrainian Village": (41.8986, -87.6871),
    "Uptown": (41.9656, -87.6536),
    "West Loop": (41.8826, -87.6499),
    "West Town": (41.8960, -87.6731),
    "Wicker Park": (41.9088, -87.6796),
    "Woodlawn": (41.7800, -87.5967),
    "South Shore": (41.7615, -87.5756),
    "Englewood": (41.7800, -87.6456),
    "Roscoe Village": (41.9434, -87.6790),
    "Ravenswood": (41.9650, -87.6750),
    "Portage Park": (41.9590, -87.7652),
    "Jefferson Park": (41.9714, -87.7600),
}

# ---------------------------------------------------------------------------
# Archetype assignments
# ---------------------------------------------------------------------------
ARCHETYPE_MAP: dict[str, str] = {
    # commercial
    "Loop": "commercial",
    "River North": "commercial",
    "Streeterville": "commercial",
    "West Loop": "commercial",
    "South Loop": "commercial",
    "Near North Side": "commercial",
    # nightlife
    "Boystown": "nightlife",
    "Wicker Park": "nightlife",
    "Logan Square": "nightlife",
    "Old Town": "nightlife",
    "Bucktown": "nightlife",
    "Ukrainian Village": "nightlife",
    "West Town": "nightlife",
    # residential
    "Jefferson Park": "residential",
    "Portage Park": "residential",
    "Rogers Park": "residential",
    "Edgewater": "residential",
    # university
    "Hyde Park": "university",
    "Lincoln Park": "university",
    "Lakeview": "university",
    "Lincoln Square": "university",
    # mixed — everything else
}

# Any neighborhood not listed above defaults to "mixed"
def _get_archetype(name: str) -> str:
    return ARCHETYPE_MAP.get(name, "mixed")

# ---------------------------------------------------------------------------
# 24-hour base multiplier curves  (0.0 – 1.0)
# Index = hour (0 = midnight, 23 = 11 PM)
# ---------------------------------------------------------------------------
BASE_CURVES: dict[str, list[float]] = {
    "commercial": [
        # 0     1     2     3     4     5     6     7     8     9    10    11
        0.03, 0.02, 0.01, 0.01, 0.02, 0.05, 0.15, 0.45, 0.85, 0.75, 0.65, 0.70,
        # 12   13    14    15    16    17    18    19    20    21    22    23
        0.80, 0.75, 0.70, 0.75, 0.90, 1.00, 0.70, 0.40, 0.20, 0.12, 0.07, 0.04,
    ],
    "nightlife": [
        0.30, 0.20, 0.10, 0.05, 0.03, 0.03, 0.05, 0.10, 0.20, 0.25, 0.30, 0.35,
        0.40, 0.45, 0.40, 0.35, 0.40, 0.50, 0.60, 0.70, 0.85, 1.00, 0.95, 0.60,
    ],
    "residential": [
        0.03, 0.02, 0.01, 0.01, 0.02, 0.08, 0.35, 0.90, 0.60, 0.15, 0.10, 0.10,
        0.12, 0.10, 0.12, 0.20, 0.55, 1.00, 0.70, 0.30, 0.12, 0.06, 0.04, 0.03,
    ],
    "university": [
        0.05, 0.03, 0.02, 0.01, 0.02, 0.04, 0.10, 0.25, 0.60, 0.80, 0.90, 1.00,
        0.85, 0.90, 0.95, 0.80, 0.60, 0.45, 0.35, 0.30, 0.25, 0.15, 0.10, 0.06,
    ],
    "mixed": [
        0.05, 0.04, 0.03, 0.02, 0.03, 0.06, 0.12, 0.30, 0.50, 0.60, 0.70, 0.80,
        0.85, 0.80, 0.75, 0.70, 0.65, 0.70, 0.55, 0.40, 0.25, 0.15, 0.08, 0.06,
    ],
}

# ---------------------------------------------------------------------------
# Scale-factor ranges by archetype
# ---------------------------------------------------------------------------
SCALE_RANGES: dict[str, dict] = {
    "commercial": {
        "peak_vehicles": (300, 500),
        "peak_pedestrians": (150, 400),
        "peak_bicycles": (10, 30),
        "camera_count": (6, 10),
    },
    "nightlife": {
        "peak_vehicles": (100, 200),
        "peak_pedestrians": (100, 300),
        "peak_bicycles": (15, 40),
        "camera_count": (4, 7),
    },
    "residential": {
        "peak_vehicles": (80, 150),
        "peak_pedestrians": (10, 40),
        "peak_bicycles": (2, 8),
        "camera_count": (3, 5),
    },
    "university": {
        "peak_vehicles": (60, 120),
        "peak_pedestrians": (80, 200),
        "peak_bicycles": (30, 60),
        "camera_count": (4, 6),
    },
    "mixed": {
        "peak_vehicles": (80, 180),
        "peak_pedestrians": (40, 120),
        "peak_bicycles": (10, 25),
        "camera_count": (3, 6),
    },
}


# ---------------------------------------------------------------------------
# Deterministic seeding helpers
# ---------------------------------------------------------------------------
def _seed_float(name: str, salt: str = "") -> float:
    """Return a deterministic float in [0, 1) from a name string."""
    h = hashlib.sha256(f"{name}:{salt}".encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def _lerp(lo: float, hi: float, t: float) -> float:
    return lo + (hi - lo) * t


def _seed_int(name: str, lo: int, hi: int, salt: str = "") -> int:
    return int(_lerp(lo, hi, _seed_float(name, salt)))


# ---------------------------------------------------------------------------
# Haversine distance (km)
# ---------------------------------------------------------------------------
def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlng / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------
def generate() -> dict:
    now = datetime.now(timezone.utc)
    output: dict[str, dict] = {}

    for name, (clat, clng) in NEIGHBORHOOD_CENTROIDS.items():
        archetype = _get_archetype(name)
        curve = BASE_CURVES[archetype]
        ranges = SCALE_RANGES[archetype]

        # Per-neighborhood scale multiplier (0.6 – 1.0)
        nb_scale = 0.6 + 0.4 * _seed_float(name, "scale")

        peak_veh = _lerp(*ranges["peak_vehicles"], _seed_float(name, "veh")) * nb_scale
        peak_ped = _lerp(*ranges["peak_pedestrians"], _seed_float(name, "ped")) * nb_scale
        peak_bic = _lerp(*ranges["peak_bicycles"], _seed_float(name, "bic")) * nb_scale
        camera_count = _seed_int(name, *ranges["camera_count"], salt="cam")

        # Build 24h timeseries -------------------------------------------------
        hours = []
        for h in range(24):
            mult = curve[h]
            # Add seeded jitter ±8%
            jitter = 1.0 + 0.08 * (2 * _seed_float(name, f"jitter_{h}") - 1)
            mult *= jitter

            avg_p = round(peak_ped * mult, 1)
            avg_v = round(peak_veh * mult, 1)

            if avg_p > 20:
                density = "high"
            elif avg_p >= 5:
                density = "medium"
            else:
                density = "low"

            sample_count = _seed_int(name, 3, 8, salt=f"sc_{h}")

            hours.append({
                "hour": h,
                "avg_pedestrians": avg_p,
                "avg_vehicles": avg_v,
                "density": density,
                "sample_count": sample_count,
            })

        peak_hour = max(range(24), key=lambda h: hours[h]["avg_pedestrians"])
        peak_pedestrians = hours[peak_hour]["avg_pedestrians"]

        timeseries = {
            "hours": hours,
            "peak_hour": peak_hour,
            "peak_pedestrians": peak_pedestrians,
            "camera_count": camera_count,
        }

        # Build per-camera data ------------------------------------------------
        # Use the "current hour" bucket values as the snapshot totals
        current_hour = now.hour
        current_bucket = hours[current_hour]
        total_ped = current_bucket["avg_pedestrians"]
        total_veh = current_bucket["avg_vehicles"]
        total_bic = round(peak_bic * curve[current_hour], 1)

        cameras = []
        # Generate camera positions around centroid
        offsets = []
        for ci in range(camera_count):
            dlat = 0.005 + 0.010 * _seed_float(name, f"clat_{ci}")
            dlng = 0.005 + 0.010 * _seed_float(name, f"clng_{ci}")
            # Alternate signs for spread
            if _seed_float(name, f"csign_lat_{ci}") > 0.5:
                dlat = -dlat
            if _seed_float(name, f"csign_lng_{ci}") > 0.5:
                dlng = -dlng
            cam_lat = round(clat + dlat, 6)
            cam_lng = round(clng + dlng, 6)
            dist = _haversine(clat, clng, cam_lat, cam_lng)
            offsets.append((ci, cam_lat, cam_lng, dist))

        # Distribute totals across cameras weighted by inverse distance
        inv_dists = [1.0 / max(d, 0.01) for (_, _, _, d) in offsets]
        inv_sum = sum(inv_dists)
        weights = [w / inv_sum for w in inv_dists]

        for idx, (ci, cam_lat, cam_lng, dist) in enumerate(offsets):
            w = weights[idx]
            cam_ped = max(0, round(total_ped * w))
            cam_veh = max(0, round(total_veh * w))
            cam_bic = max(0, round(total_bic * w))

            if cam_ped > 20:
                density_level = "high"
            elif cam_ped >= 5:
                density_level = "medium"
            else:
                density_level = "low"

            # IDOT-style camera ID (4 digits, seeded)
            cam_id = str(1000 + _seed_int(name, 0, 900, salt=f"camid_{ci}"))

            # Recent timestamp (within last hour)
            minutes_ago = _seed_int(name, 1, 55, salt=f"ts_{ci}")
            ts = (now - timedelta(minutes=minutes_ago)).isoformat()

            cameras.append({
                "camera_id": cam_id,
                "lat": cam_lat,
                "lng": cam_lng,
                "distance_km": round(dist, 2),
                "pedestrians": cam_ped,
                "vehicles": cam_veh,
                "bicycles": cam_bic,
                "density_level": density_level,
                "timestamp": ts,
            })

        # Compute averages across cameras
        avg_ped = round(sum(c["pedestrians"] for c in cameras) / len(cameras), 1) if cameras else 0
        avg_veh = round(sum(c["vehicles"] for c in cameras) / len(cameras), 1) if cameras else 0

        if avg_ped > 20:
            overall_density = "high"
        elif avg_ped >= 5:
            overall_density = "medium"
        else:
            overall_density = "low"

        camera_data = {
            "cameras": cameras,
            "avg_pedestrians": avg_ped,
            "avg_vehicles": avg_veh,
            "density": overall_density,
        }

        output[name] = {
            "timeseries": timeseries,
            "cameras": camera_data,
        }

    return output


def main():
    data = generate()

    out_dir = get_processed_data_dir() / "cctv"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "synthetic_analytics.json"

    with open(out_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Wrote {len(data)} neighborhoods to {out_path}")
    # Show a sample
    sample = list(data.keys())[:3]
    for nb in sample:
        ts = data[nb]["timeseries"]
        cam = data[nb]["cameras"]
        print(
            f"  {nb}: peak_hour={ts['peak_hour']}, "
            f"peak_ped={ts['peak_pedestrians']}, "
            f"cameras={len(cam['cameras'])}, "
            f"density={cam['density']}"
        )


if __name__ == "__main__":
    main()
