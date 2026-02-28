"""Traffic ingester — monitors Chicago traffic flow using TomTom API.

Cadence: Every 1 hour
Sources: TomTom Traffic Flow API
Pattern: async + FallbackChain + gather_with_limit + congestion classification
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
import modal

from modal_app.common import (
    Document,
    SourceType,
    CHICAGO_NEIGHBORHOODS,
    NEIGHBORHOOD_CENTROIDS,
    gather_with_limit,
    safe_volume_commit,
)
from modal_app.fallback import FallbackChain
from modal_app.volume import app, volume, base_image, RAW_DATA_PATH


def _classify_congestion(current_speed: float, free_flow_speed: float) -> str:
    """Classify congestion level based on speed ratio.
    
    Congestion levels:
    - "free": >80% of free flow speed
    - "moderate": 50-80% of free flow speed
    - "heavy": 20-50% of free flow speed
    - "blocked": <20% of free flow speed
    """
    if free_flow_speed <= 0:
        return "unknown"
    
    ratio = current_speed / free_flow_speed
    
    if ratio > 0.8:
        return "free"
    elif ratio > 0.5:
        return "moderate"
    elif ratio > 0.2:
        return "heavy"
    else:
        return "blocked"


async def _fetch_traffic_point(api_key: str, neighborhood: str, lat: float, lng: float) -> dict | None:
    """Fetch traffic flow data for a single point (neighborhood centroid).
    
    Uses zoom level 14, which provides fine-grained street detail suitable for Chicago neighborhoods.
    
    TomTom zoom levels and tile sizes:
    - Zoom 12: 38.22 m/tile
    - Zoom 13: 19.109 m/tile (4891.97 m world - too large for Chicago neighborhoods)
    - Zoom 14: 9.555 m/tile (OPTIMAL for Chicago neighborhood-scale traffic analysis)
    - Zoom 15: 4.777 m/tile (very detailed street level)
    - Zoom 16+: <3 m/tile (address/building level)
    
    Returns a dict with traffic metrics or None if request fails.
    """
    if not api_key:
        return None
    
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            # TomTom Flow Segment Data API requires zoom level in path (0-22)
            # Zoom 14 provides fine-grained street-level traffic visibility
            resp = await client.get(
                f"https://api.tomtom.com/traffic/services/4/flowSegmentData/relative/14/json",
                params={
                    "key": api_key,
                    "point": f"{lat},{lng}",
                    "unit": "mph",
                },
            )
            
            if resp.status_code != 200:
                print(f"TomTom [{neighborhood}]: HTTP {resp.status_code}")
                return None
            
            data = resp.json()
            flow = data.get("flowSegmentData", {})
            
            if not flow:
                print(f"TomTom [{neighborhood}]: Empty response")
                return None
            
            current_speed = flow.get("currentSpeed", 0)
            free_flow_speed = flow.get("freeFlowSpeed", 0)
            congestion_level = _classify_congestion(current_speed, free_flow_speed)
            
            return {
                "neighborhood": neighborhood,
                "lat": lat,
                "lng": lng,
                "current_speed": current_speed,
                "free_flow_speed": free_flow_speed,
                "congestion_level": congestion_level,
                "current_travel_time": flow.get("currentTravelTime", 0),
                "free_flow_travel_time": flow.get("freeFlowTravelTime", 0),
                "confidence": flow.get("confidence", 0),
                "road_closure": flow.get("roadClosure", False),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        
        except Exception as e:
            print(f"TomTom request error [{neighborhood}]: {e}")
            return None


async def _fetch_all_traffic(api_key: str) -> list[dict]:
    """Fetch traffic data for all Chicago neighborhoods in parallel."""
    if not api_key:
        print("TOMTOM_API_KEY not set, skipping traffic")
        return []
    
    coros = [
        _fetch_traffic_point(api_key, neighborhood, lat, lng)
        for neighborhood, (lat, lng) in NEIGHBORHOOD_CENTROIDS.items()
    ]
    
    results = await gather_with_limit(coros, max_concurrent=10)
    
    # Filter out None results from failed requests
    return [r for r in results if r is not None]


def _detect_flow_anomalies(docs: list[dict]) -> None:
    """Annotate docs with congestion anomaly flags.
    
    Anomalies are defined as:
    - blocked roads (congestion_level == "blocked")
    - road closures
    - confidence < 0.5
    """
    for doc in docs:
        is_anomaly = (
            doc.get("congestion_level") == "blocked"
            or doc.get("road_closure") is True
            or doc.get("confidence", 1.0) < 0.5
        )
        doc["is_anomaly"] = is_anomaly
        doc["severity"] = (
            "critical" if doc.get("congestion_level") == "blocked"
            else "warning" if doc.get("road_closure") is True
            else "info" if is_anomaly
            else "normal"
        )


def _convert_to_documents(traffic_data: list[dict]) -> list[Document]:
    """Convert raw traffic API responses to unified Document schema."""
    documents = []
    
    for data in traffic_data:
        neighborhood = data.get("neighborhood", "Unknown")
        doc_id = f"traffic-{neighborhood.lower().replace(' ', '-')}-{data.get('timestamp', '')}"
        
        # Create readable summary
        congestion = data.get("congestion_level", "unknown")
        speed = data.get("current_speed", 0)
        free_speed = data.get("free_flow_speed", 0)
        
        content = (
            f"Traffic flow in {neighborhood}: "
            f"{congestion.upper()} | "
            f"Current: {speed} mph (free flow: {free_speed} mph) | "
            f"Confidence: {data.get('confidence', 0):.1%}"
        )
        
        if data.get("road_closure"):
            content += " | ⚠️ ROAD CLOSURE"
        
        doc = Document(
            id=doc_id,
            source=SourceType.TRAFFIC,
            title=f"{neighborhood} Traffic Flow",
            content=content,
            url="",  # Traffic API doesn't have a public URL
            timestamp=datetime.fromisoformat(data.get("timestamp", datetime.now(timezone.utc).isoformat())),
            metadata={
                "neighborhood": neighborhood,
                "current_speed": data.get("current_speed"),
                "free_flow_speed": data.get("free_flow_speed"),
                "congestion_level": data.get("congestion_level"),
                "current_travel_time": data.get("current_travel_time"),
                "free_flow_travel_time": data.get("free_flow_travel_time"),
                "confidence": data.get("confidence"),
                "road_closure": data.get("road_closure"),
                "is_anomaly": data.get("is_anomaly", False),
                "severity": data.get("severity", "normal"),
            },
            geo={
                "lat": data.get("lat"),
                "lng": data.get("lng"),
                "neighborhood": neighborhood,
            },
        )
        documents.append(doc)
    
    return documents


@app.function(
    image=base_image,
    volumes={"/data": volume},
    secrets=[modal.Secret.from_name("alethia-secrets")],
    timeout=120,
)
async def traffic_ingester():
    """Ingest traffic flow data from TomTom API for all Chicago neighborhoods."""
    all_raw_data: list[dict] = []
    
    tomtom_key = os.environ.get("TOMTOM_API_KEY", "")
    
    # Fetch traffic with fallback chain
    traffic_chain = FallbackChain("traffic", "tomtom", cache_ttl_hours=6)
    traffic_data = await traffic_chain.execute([
        lambda: _fetch_all_traffic(tomtom_key),
    ])
    
    if traffic_data:
        all_raw_data.extend(traffic_data)
        print(f"TomTom: {len(traffic_data)} neighborhoods processed")
    else:
        print("TomTom: No data retrieved (fallback used or API unavailable)")
        return 0
    
    # Detect anomalies
    _detect_flow_anomalies(all_raw_data)
    
    # Save raw data to volume
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    hour_str = datetime.now(timezone.utc).strftime("%H")
    
    raw_dir = Path(RAW_DATA_PATH) / "traffic" / date_str
    raw_dir.mkdir(parents=True, exist_ok=True)
    
    # Save each neighborhood's traffic snapshot
    for data in all_raw_data:
        neighborhood = data.get("neighborhood", "unknown").lower().replace(" ", "_")
        fpath = raw_dir / f"{neighborhood}_{hour_str}.json"
        fpath.write_text(json.dumps(data, indent=2))
    
    # Convert to documents and save processed version
    documents = _convert_to_documents(all_raw_data)
    
    processed_dir = Path(RAW_DATA_PATH) / "processed" / "traffic" / date_str
    processed_dir.mkdir(parents=True, exist_ok=True)
    
    anomalies = []
    for doc in documents:
        fpath = processed_dir / f"{doc.id}.json"
        fpath.write_text(doc.model_dump_json(indent=2))
        
        if doc.metadata.get("is_anomaly"):
            anomalies.append({
                "neighborhood": doc.metadata.get("neighborhood"),
                "severity": doc.metadata.get("severity"),
                "congestion_level": doc.metadata.get("congestion_level"),
                "timestamp": doc.timestamp.isoformat(),
            })
    
    # Save anomaly summary
    if anomalies:
        anomaly_path = processed_dir / "anomalies.json"
        anomaly_path.write_text(json.dumps(anomalies, indent=2))
        print(f"Traffic anomalies detected: {len(anomalies)}")
    
    await safe_volume_commit(volume, "traffic")
    print(f"Traffic ingester complete: {len(documents)} documents saved to {processed_dir}")
    
    return len(documents)
