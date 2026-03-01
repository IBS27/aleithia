"""Satellite parking detection pipeline — SegFormer + YOLOv8m + SAHI.

Two-stage computer vision pipeline:
  Stage 1: SegFormer-b5 for pixel-level parking lot segmentation from satellite tiles
  Stage 2: YOLOv8m + SAHI for vehicle detection within segmented parking regions

Source: Mapbox Satellite tiles (zoom 19, ~0.3m/pixel)
GPU: T4 for SegFormer + YOLO inference via @modal.cls + @modal.enter
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import httpx
import modal

from modal_app.common import (
    Document,
    SourceType,
    NEIGHBORHOOD_CENTROIDS,
    gather_with_limit,
    safe_queue_push,
    safe_volume_commit,
)
from modal_app.volume import app, volume, base_image, parking_image, RAW_DATA_PATH, PROCESSED_DATA_PATH


# ── Tile math (slippy map) ────────────────────────────────────────────────────

TILE_SIZE = 256  # pixels per tile
TILE_ZOOM = 19   # ~0.3m/pixel at Chicago latitude
GRID_RADIUS = 1  # 3x3 grid around center tile


def _latlng_to_tile(lat: float, lng: float, zoom: int) -> tuple[int, int]:
    """Convert lat/lng to slippy map tile X/Y at given zoom."""
    n = 2 ** zoom
    x = int((lng + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def _tile_to_latlng(x: int, y: int, zoom: int) -> tuple[float, float]:
    """Convert tile X/Y to NW corner lat/lng."""
    n = 2 ** zoom
    lng = x / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat = math.degrees(lat_rad)
    return lat, lng


def _meters_per_pixel(lat: float, zoom: int) -> float:
    """Ground resolution in meters/pixel at given latitude and zoom."""
    return 156543.03392 * math.cos(math.radians(lat)) / (2 ** zoom)


# ── CPU Ingester ──────────────────────────────────────────────────────────────

def _neighborhood_slug(name: str) -> str:
    """Lowercase slug for filesystem paths."""
    return name.lower().replace(" ", "_")


async def _download_tile_grid(
    client: httpx.AsyncClient,
    lat: float,
    lng: float,
    token: str,
    out_dir: Path,
) -> list[dict]:
    """Download a 3x3 tile grid around center lat/lng. Returns tile metadata list."""
    cx, cy = _latlng_to_tile(lat, lng, TILE_ZOOM)
    tiles = []

    for dy in range(-GRID_RADIUS, GRID_RADIUS + 1):
        for dx in range(-GRID_RADIUS, GRID_RADIUS + 1):
            tx, ty = cx + dx, cy + dy
            url = f"https://api.mapbox.com/raster/v1/mapbox.satellite/{TILE_ZOOM}/{tx}/{ty}@2x?access_token={token}"
            fname = f"{TILE_ZOOM}_{tx}_{ty}.jpg"
            out_path = out_dir / fname

            try:
                resp = await client.get(url, timeout=15, follow_redirects=True)
                if resp.status_code != 200:
                    print(f"Parking tile {tx},{ty}: HTTP {resp.status_code}")
                    continue
                content = resp.content
                if len(content) < 500:
                    continue
                out_path.write_bytes(content)
                nw_lat, nw_lng = _tile_to_latlng(tx, ty, TILE_ZOOM)
                se_lat, se_lng = _tile_to_latlng(tx + 1, ty + 1, TILE_ZOOM)
                tiles.append({
                    "path": str(out_path),
                    "x": tx, "y": ty, "zoom": TILE_ZOOM,
                    "nw_lat": nw_lat, "nw_lng": nw_lng,
                    "se_lat": se_lat, "se_lng": se_lng,
                    "grid_dx": dx, "grid_dy": dy,
                })
            except Exception as e:
                print(f"Parking tile {tx},{ty}: download error: {e}")
                continue

    return tiles


@app.function(
    image=base_image,
    volumes={"/data": volume},
    secrets=[modal.Secret.from_name("alethia-secrets")],
    timeout=300,
)
async def parking_ingester(neighborhoods: list[str] | None = None):
    """Download satellite tiles for neighborhoods and spawn GPU analysis."""
    import os

    token = os.environ.get("MAPBOX_TOKEN", "")
    if not token:
        print("Parking ingester: MAPBOX_TOKEN not set, skipping")
        return 0

    targets = neighborhoods or list(NEIGHBORHOOD_CENTROIDS.keys())
    print(f"Parking ingester: processing {len(targets)} neighborhoods")

    async with httpx.AsyncClient() as client:
        for name in targets:
            centroid = NEIGHBORHOOD_CENTROIDS.get(name)
            if not centroid:
                continue

            lat, lng = centroid
            slug = _neighborhood_slug(name)
            tile_dir = Path(RAW_DATA_PATH) / "parking" / "tiles" / slug
            tile_dir.mkdir(parents=True, exist_ok=True)

            tiles = await _download_tile_grid(client, lat, lng, token, tile_dir)
            print(f"Parking: {name} — downloaded {len(tiles)} tiles")

            if tiles:
                # Save tile metadata
                meta_path = tile_dir / "tiles_meta.json"
                meta_path.write_text(json.dumps({
                    "neighborhood": name,
                    "center_lat": lat,
                    "center_lng": lng,
                    "tile_count": len(tiles),
                    "tiles": tiles,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }, indent=2))

    await safe_volume_commit(volume, "parking")

    # Spawn GPU analysis
    await analyze_parking_batch.spawn.aio(neighborhoods=targets)

    print(f"Parking ingester: {len(targets)} neighborhoods processed")
    return len(targets)


# ── ParkingAnalyzer GPU Class ─────────────────────────────────────────────────

# Cityscapes class IDs that correspond to drivable/parking surfaces
# 0=road, 1=sidewalk, 2=building, ... 8=vegetation, 9=terrain
# We look for road (0) + terrain (9) as potential parking surface
PARKING_SURFACE_IDS = {0, 9}  # road, terrain — parking lots often classified as these
MIN_LOT_AREA_PX = 500
MIN_SOLIDITY = 0.3
MAX_ASPECT_RATIO = 8.0
SQM_PER_STALL = 15.0  # average parking stall area in sqm


@app.cls(
    gpu="T4",
    image=parking_image,
    volumes={"/data": volume},
    scaledown_window=120,
    timeout=300,
    enable_memory_snapshot=True,
    experimental_options={"enable_gpu_snapshot": True},
)
class ParkingAnalyzer:
    """Two-stage parking lot detection: SegFormer segmentation + YOLO vehicle detection."""

    @modal.enter(snap=True)
    def load_models(self):
        import torch
        from transformers import SegformerForSemanticSegmentation, SegformerImageProcessor
        from ultralytics import YOLO

        volume.reload()

        # Stage 1: SegFormer-b5 for semantic segmentation
        model_name = "nvidia/segformer-b5-finetuned-cityscapes-1024-1024"
        self.seg_processor = SegformerImageProcessor.from_pretrained(model_name)
        self.seg_model = SegformerForSemanticSegmentation.from_pretrained(model_name)
        self.seg_model.eval()
        if torch.cuda.is_available():
            self.seg_model = self.seg_model.cuda()

        # Stage 2: YOLOv8m for vehicle detection
        self.yolo = YOLO("yolov8m.pt")

        self.device = "cuda" if torch.cuda.is_available() else "cpu"

    @modal.method()
    def analyze_tiles(self, tile_batch: dict) -> dict:
        """Analyze stitched satellite tiles for parking lots and vehicles.

        tile_batch: {"neighborhood": str, "tiles": [...], "center_lat": float, "center_lng": float}
        Returns: per-neighborhood parking analysis with lot details.
        """
        import cv2
        import numpy as np
        import torch
        from PIL import Image

        neighborhood = tile_batch["neighborhood"]
        tiles = tile_batch["tiles"]
        center_lat = tile_batch["center_lat"]
        center_lng = tile_batch["center_lng"]

        if not tiles:
            return {"neighborhood": neighborhood, "parking_lots": [], "error": "no tiles"}

        # 1. Stitch tiles into composite image
        grid_positions = {}
        for t in tiles:
            grid_positions[(t["grid_dx"], t["grid_dy"])] = t

        grid_size = 2 * GRID_RADIUS + 1
        # Each @2x tile is 512x512
        tile_px = TILE_SIZE * 2  # @2x retina
        composite_w = grid_size * tile_px
        composite_h = grid_size * tile_px
        composite = np.zeros((composite_h, composite_w, 3), dtype=np.uint8)

        for dy in range(-GRID_RADIUS, GRID_RADIUS + 1):
            for dx in range(-GRID_RADIUS, GRID_RADIUS + 1):
                tile = grid_positions.get((dx, dy))
                if not tile:
                    continue
                tile_path = Path(tile["path"])
                if not tile_path.exists():
                    continue
                img = cv2.imread(str(tile_path))
                if img is None:
                    continue
                # Resize to expected tile size
                img = cv2.resize(img, (tile_px, tile_px))
                px_x = (dx + GRID_RADIUS) * tile_px
                px_y = (dy + GRID_RADIUS) * tile_px
                composite[px_y:px_y + tile_px, px_x:px_x + tile_px] = img

        # Compute ground resolution
        mpp = _meters_per_pixel(center_lat, TILE_ZOOM) / 2  # @2x tiles → half the mpp
        coverage_area_sqm = (composite_w * mpp) * (composite_h * mpp)

        # 2. SegFormer semantic segmentation
        pil_img = Image.fromarray(cv2.cvtColor(composite, cv2.COLOR_BGR2RGB))
        inputs = self.seg_processor(images=pil_img, return_tensors="pt")
        if self.device == "cuda":
            inputs = {k: v.cuda() for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self.seg_model(**inputs)

        logits = outputs.logits
        # Upsample to original size
        upsampled = torch.nn.functional.interpolate(
            logits, size=(composite_h, composite_w),
            mode="bilinear", align_corners=False,
        )
        seg_map = upsampled.argmax(dim=1).squeeze().cpu().numpy().astype(np.uint8)

        # 3. Binary parking mask (road + terrain classes)
        parking_mask = np.zeros_like(seg_map, dtype=np.uint8)
        for cls_id in PARKING_SURFACE_IDS:
            parking_mask[seg_map == cls_id] = 255

        # 4. Morphological cleanup
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
        parking_mask = cv2.morphologyEx(parking_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        parking_mask = cv2.morphologyEx(parking_mask, cv2.MORPH_OPEN, kernel, iterations=1)

        # Find contours
        contours, _ = cv2.findContours(parking_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Filter contours to plausible parking lots
        lot_regions = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < MIN_LOT_AREA_PX:
                continue

            # Aspect ratio filter (remove long thin roads)
            rect = cv2.minAreaRect(cnt)
            w_rect, h_rect = rect[1]
            if min(w_rect, h_rect) == 0:
                continue
            aspect = max(w_rect, h_rect) / min(w_rect, h_rect)
            if aspect > MAX_ASPECT_RATIO:
                continue

            # Solidity filter (parking lots are roughly convex)
            hull = cv2.convexHull(cnt)
            hull_area = cv2.contourArea(hull)
            if hull_area == 0:
                continue
            solidity = area / hull_area
            if solidity < MIN_SOLIDITY:
                continue

            lot_regions.append({
                "contour": cnt,
                "area_px": area,
                "center": tuple(map(int, np.mean(cnt.reshape(-1, 2), axis=0))),
                "bbox": cv2.boundingRect(cnt),
            })

        # 5. YOLO + SAHI vehicle detection
        # Use SAHI-style slicing for better small vehicle detection
        slice_size = 640
        overlap_ratio = 0.2
        stride = int(slice_size * (1 - overlap_ratio))

        all_vehicle_detections = []
        VEHICLE_CLASS_IDS = {2, 3, 5, 7}  # car, motorcycle, bus, truck

        for y_start in range(0, composite_h - slice_size + 1, stride):
            for x_start in range(0, composite_w - slice_size + 1, stride):
                crop = composite[y_start:y_start + slice_size, x_start:x_start + slice_size]
                results = self.yolo(crop, conf=0.25, verbose=False)
                for box in results[0].boxes:
                    cls_id = int(box.cls[0])
                    if cls_id not in VEHICLE_CLASS_IDS:
                        continue
                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                    # Translate to composite coordinates
                    abs_x1 = x_start + x1
                    abs_y1 = y_start + y1
                    abs_x2 = x_start + x2
                    abs_y2 = y_start + y2
                    cx = (abs_x1 + abs_x2) // 2
                    cy = (abs_y1 + abs_y2) // 2
                    all_vehicle_detections.append({
                        "cx": cx, "cy": cy,
                        "bbox": [abs_x1, abs_y1, abs_x2, abs_y2],
                        "confidence": conf,
                    })

        # NMS-style dedup on vehicle detections (remove overlapping from SAHI slices)
        deduped_vehicles = []
        used = set()
        for i, det in enumerate(all_vehicle_detections):
            if i in used:
                continue
            deduped_vehicles.append(det)
            for j, other in enumerate(all_vehicle_detections):
                if j <= i or j in used:
                    continue
                dist = math.sqrt((det["cx"] - other["cx"]) ** 2 + (det["cy"] - other["cy"]) ** 2)
                if dist < 15:  # within ~15px = same vehicle
                    used.add(j)

        # 6. Assign vehicles to lot regions via mask lookup
        parking_lots = []
        for lot in lot_regions:
            lot_mask = np.zeros((composite_h, composite_w), dtype=np.uint8)
            cv2.drawContours(lot_mask, [lot["contour"]], -1, 255, -1)

            vehicles_in_lot = 0
            for det in deduped_vehicles:
                if lot_mask[det["cy"], det["cx"]] > 0:
                    vehicles_in_lot += 1

            area_sqm = lot["area_px"] * (mpp ** 2)
            capacity = max(1, int(area_sqm / SQM_PER_STALL))
            occupancy = min(1.0, vehicles_in_lot / capacity) if capacity > 0 else 0.0

            # Convert pixel center to lat/lng
            px_x, px_y = lot["center"]
            # Map pixel coords to geo coords
            frac_x = px_x / composite_w
            frac_y = px_y / composite_h
            # Get NW and SE corners of composite
            nw_tile = _tile_to_latlng(
                _latlng_to_tile(center_lat, center_lng, TILE_ZOOM)[0] - GRID_RADIUS,
                _latlng_to_tile(center_lat, center_lng, TILE_ZOOM)[1] - GRID_RADIUS,
                TILE_ZOOM,
            )
            se_tile = _tile_to_latlng(
                _latlng_to_tile(center_lat, center_lng, TILE_ZOOM)[0] + GRID_RADIUS + 1,
                _latlng_to_tile(center_lat, center_lng, TILE_ZOOM)[1] + GRID_RADIUS + 1,
                TILE_ZOOM,
            )
            lot_lat = nw_tile[0] + (se_tile[0] - nw_tile[0]) * frac_y
            lot_lng = nw_tile[1] + (se_tile[1] - nw_tile[1]) * frac_x

            parking_lots.append({
                "center_lat": round(lot_lat, 6),
                "center_lng": round(lot_lng, 6),
                "area_sqm": round(area_sqm, 1),
                "estimated_capacity": capacity,
                "vehicles_detected": vehicles_in_lot,
                "occupancy_rate": round(occupancy, 2),
            })

        total_capacity = sum(p["estimated_capacity"] for p in parking_lots)
        total_vehicles = sum(p["vehicles_detected"] for p in parking_lots)
        overall_occupancy = round(total_vehicles / total_capacity, 2) if total_capacity > 0 else 0.0

        # 8. Save annotated overlay
        annotated = composite.copy()
        for lot in lot_regions:
            cv2.drawContours(annotated, [lot["contour"]], -1, (0, 255, 0), 2)
        for det in deduped_vehicles:
            x1, y1, x2, y2 = det["bbox"]
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 1)

        # Banner
        h, w = annotated.shape[:2]
        overlay = annotated.copy()
        cv2.rectangle(overlay, (0, 0), (w, 36), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, annotated, 0.4, 0, annotated)
        banner = f"{neighborhood}: {len(parking_lots)} lots | {total_vehicles}/{total_capacity} vehicles | {overall_occupancy:.0%} occupancy"
        cv2.putText(annotated, banner, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        slug = _neighborhood_slug(neighborhood)
        ann_dir = Path(PROCESSED_DATA_PATH) / "parking" / "annotated"
        ann_dir.mkdir(parents=True, exist_ok=True)
        ann_path = ann_dir / f"{slug}.jpg"
        cv2.imwrite(str(ann_path), annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])

        return {
            "neighborhood": neighborhood,
            "parking_lots": parking_lots,
            "total_capacity": total_capacity,
            "total_vehicles": total_vehicles,
            "overall_occupancy": overall_occupancy,
            "coverage_area_sqm": round(coverage_area_sqm, 1),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# ── Batch Coordinator ─────────────────────────────────────────────────────────


@app.function(
    image=base_image,
    volumes={"/data": volume},
    timeout=600,
)
async def analyze_parking_batch(neighborhoods: list[str] | None = None):
    """Dispatch ParkingAnalyzer for each neighborhood. Saves JSON results + creates Documents."""
    targets = neighborhoods or list(NEIGHBORHOOD_CENTROIDS.keys())

    analysis_dir = Path(PROCESSED_DATA_PATH) / "parking" / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    analyzer = ParkingAnalyzer()

    async def _analyze_one(name: str) -> dict | None:
        centroid = NEIGHBORHOOD_CENTROIDS.get(name)
        if not centroid:
            return None

        slug = _neighborhood_slug(name)
        tile_dir = Path(RAW_DATA_PATH) / "parking" / "tiles" / slug
        meta_path = tile_dir / "tiles_meta.json"
        if not meta_path.exists():
            return None

        try:
            meta = json.loads(meta_path.read_text())
        except Exception:
            return None

        try:
            return await analyzer.analyze_tiles.remote.aio({
                "neighborhood": name,
                "tiles": meta["tiles"],
                "center_lat": centroid[0],
                "center_lng": centroid[1],
            })
        except Exception as e:
            print(f"Parking analysis error [{name}]: {e}")
            return None

    results = await gather_with_limit(
        [_analyze_one(n) for n in targets],
        max_concurrent=4,
    )

    documents = []
    for result in results:
        if not result or "error" in result:
            continue

        name = result["neighborhood"]
        slug = _neighborhood_slug(name)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")

        # Save analysis JSON
        out_path = analysis_dir / f"{slug}_{ts}.json"
        out_path.write_text(json.dumps(result, indent=2, default=str))

        # Create Document
        centroid = NEIGHBORHOOD_CENTROIDS.get(name, (0, 0))
        doc = Document(
            id=f"parking-{slug}-{ts}",
            source=SourceType.PARKING,
            title=f"Parking Analysis: {name}",
            content=(
                f"{name}: {len(result['parking_lots'])} parking lots detected. "
                f"Total capacity {result['total_capacity']}, "
                f"{result['total_vehicles']} vehicles detected, "
                f"{result['overall_occupancy']:.0%} occupancy."
            ),
            timestamp=datetime.now(timezone.utc),
            metadata={
                "lots_detected": len(result["parking_lots"]),
                "total_capacity": result["total_capacity"],
                "total_vehicles": result["total_vehicles"],
                "overall_occupancy": result["overall_occupancy"],
                "coverage_area_sqm": result["coverage_area_sqm"],
            },
            geo={
                "neighborhood": name,
                "lat": centroid[0],
                "lng": centroid[1],
            },
        )
        documents.append(doc)

    # Push to classification queue
    if documents:
        try:
            doc_queue = modal.Queue.from_name("alethia-doc-queue", create_if_missing=True)
            doc_dicts = [d.model_dump(mode="json") for d in documents]
            await safe_queue_push(doc_queue, doc_dicts, "parking")
        except Exception as e:
            print(f"Parking batch: queue push failed: {e}")

    await safe_volume_commit(volume, "parking")
    valid = [r for r in results if r and "error" not in r]
    print(f"Parking batch: analyzed {len(valid)}/{len(targets)} neighborhoods")
    return len(valid)
