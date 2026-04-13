"""Sensor, parking, and vision read routes."""
from __future__ import annotations

import base64
import json
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response

from modal_app.api.services.cctv import (
    aggregate_timeseries_for_neighborhood,
    analysis_timestamp_epoch,
    load_cctv_for_neighborhood,
    load_cctv_latest_index,
    load_parking_for_neighborhood,
)
from modal_app.runtime import ENABLE_CCTV_ANALYSIS
from modal_app.volume import PROCESSED_DATA_PATH, RAW_DATA_PATH, volume

router = APIRouter()


@router.get("/cctv/latest")
async def cctv_latest():
    latest_by_cam = await load_cctv_latest_index()
    if not latest_by_cam:
        return {"cameras": [], "count": 0}

    cameras = sorted(
        latest_by_cam.values(),
        key=lambda data: analysis_timestamp_epoch(data, fallback_mtime=0.0),
        reverse=True,
    )
    return {"cameras": cameras, "count": len(cameras)}


@router.get("/cctv/frame/{camera_id}")
async def cctv_frame(camera_id: str):
    volume.reload()
    frame_dirs: list[tuple[Path, str]] = []
    if ENABLE_CCTV_ANALYSIS:
        frame_dirs.append((Path(PROCESSED_DATA_PATH) / "cctv" / "annotated", "annotated"))
    frame_dirs.append((Path(RAW_DATA_PATH) / "cctv" / "frames", "raw"))

    for frame_dir, frame_type in frame_dirs:
        if not frame_dir.exists():
            continue
        frames = sorted(frame_dir.glob(f"{camera_id}_*.jpg"), reverse=True)
        if frames:
            return Response(content=frames[0].read_bytes(), media_type="image/jpeg")
        print("cctv_frame_lookup_miss", {"camera_id": camera_id, "frame_type": frame_type})

    return JSONResponse({"error": f"no frames for camera {camera_id}"}, status_code=404)


@router.get("/cctv/timeseries/{neighborhood}")
async def cctv_timeseries(neighborhood: str):
    cctv = await load_cctv_for_neighborhood(neighborhood)
    cam_ids = [camera["camera_id"] for camera in cctv.get("cameras", [])]
    return await aggregate_timeseries_for_neighborhood(neighborhood, camera_ids=cam_ids)


@router.get("/vision/streetscape/{neighborhood}")
async def vision_streetscape(neighborhood: str):
    volume.reload()
    analysis_dir = Path(PROCESSED_DATA_PATH) / "vision" / "analysis"
    if not analysis_dir.exists():
        return {"counts": None, "indicators": None, "analysis_count": 0}

    totals = {
        "person": 0,
        "vehicle": 0,
        "storefront_open": 0,
        "storefront_closed": 0,
        "for_lease_sign": 0,
        "construction": 0,
        "restaurant_signage": 0,
        "outdoor_dining": 0,
    }
    analysis_count = 0
    slug = neighborhood.lower().replace(" ", "_")

    for jf in analysis_dir.glob("*.json"):
        try:
            data = json.loads(jf.read_text())
            counts = data.get("counts")
            if not counts:
                continue
            file_match = jf.name.startswith(f"{slug}_")
            field_match = data.get("neighborhood", "").lower().replace(" ", "_") == slug
            if not file_match and not field_match:
                continue
            for key in totals:
                totals[key] += counts.get(key, 0)
            analysis_count += 1
        except Exception:
            continue

    if analysis_count == 0:
        return {"counts": None, "indicators": None, "analysis_count": 0}

    total_storefronts = totals["storefront_open"] + totals["storefront_closed"] + totals["for_lease_sign"]
    if total_storefronts > 0:
        vacancy_pct = (totals["for_lease_sign"] + totals["storefront_closed"]) / total_storefronts
        vacancy_signal = "high" if vacancy_pct > 0.4 else "moderate" if vacancy_pct > 0.15 else "low"
    else:
        vacancy_signal = "low"

    dining_total = totals["restaurant_signage"] + totals["outdoor_dining"]
    dining_saturation = "high" if dining_total > 10 else "moderate" if dining_total > 3 else "low"
    growth_signal = "active" if totals["construction"] > 0 else "stable"

    return {
        "counts": totals,
        "indicators": {
            "vacancy_signal": vacancy_signal,
            "dining_saturation": dining_saturation,
            "growth_signal": growth_signal,
        },
        "analysis_count": analysis_count,
    }


@router.get("/parking/latest")
async def parking_latest():
    volume.reload()
    analysis_dir = Path(PROCESSED_DATA_PATH) / "parking" / "analysis"
    if not analysis_dir.exists():
        return {"neighborhoods": [], "count": 0}

    latest_by_nb: dict[str, dict] = {}
    for jf in sorted(analysis_dir.glob("*.json"), reverse=True)[:500]:
        try:
            data = json.loads(jf.read_text())
            nb = data.get("neighborhood", "")
            if nb and nb not in latest_by_nb:
                latest_by_nb[nb] = data
        except Exception:
            continue

    neighborhoods = list(latest_by_nb.values())
    return {"neighborhoods": neighborhoods, "count": len(neighborhoods)}


@router.get("/parking/{neighborhood}")
async def parking_neighborhood(neighborhood: str):
    data = load_parking_for_neighborhood(neighborhood)
    if not data:
        return JSONResponse({"error": f"No parking data for {neighborhood}"}, status_code=404)
    return data


@router.get("/parking/annotated/{neighborhood}")
async def parking_annotated(neighborhood: str):
    volume.reload()
    slug = neighborhood.lower().replace(" ", "_")
    ann_path = Path(PROCESSED_DATA_PATH) / "parking" / "annotated" / f"{slug}.jpg"
    if not ann_path.exists():
        return JSONResponse({"error": f"No annotated image for {neighborhood}"}, status_code=404)
    return Response(content=ann_path.read_bytes(), media_type="image/jpeg")


@router.get("/vision/assess/{neighborhood}")
async def vision_assess(neighborhood: str):
    from modal_app.openai_utils import build_chat_kwargs, get_openai_client, get_vision_assess_model, openai_available

    if not openai_available():
        return JSONResponse(
            {"error": "Vision assessment requires OpenAI API key", "fallback": "Use /vision/streetscape for YOLO-based analysis"},
            status_code=503,
        )

    volume.reload()
    slug = neighborhood.lower().replace(" ", "_")
    frame_paths: list[Path] = []

    cctv_dir = Path(PROCESSED_DATA_PATH) / "cctv" / "annotated"
    if cctv_dir.exists():
        for fp in sorted(cctv_dir.glob("*.jpg"), reverse=True)[:5]:
            frame_paths.append(fp)

    vision_dir = Path(RAW_DATA_PATH) / "vision" / "frames"
    if vision_dir.exists():
        for fp in sorted(vision_dir.glob(f"{slug}*.jpg"), reverse=True)[:5]:
            frame_paths.append(fp)
        if len(frame_paths) < 3:
            for fp in sorted(vision_dir.glob("*.jpg"), reverse=True)[:5]:
                if fp not in frame_paths:
                    frame_paths.append(fp)

    frame_paths = frame_paths[:3]
    if not frame_paths:
        return JSONResponse({"error": f"No frames available for {neighborhood}", "frame_count": 0}, status_code=404)

    image_content = []
    for fp in frame_paths:
        try:
            b64 = base64.b64encode(fp.read_bytes()).decode("utf-8")
            image_content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "low"}})
        except Exception:
            continue

    if not image_content:
        return JSONResponse({"error": "Failed to read frame images"}, status_code=500)

    model_name = get_vision_assess_model()
    vision_messages = [
        {
            "role": "system",
            "content": (
                "You are an urban commercial real estate analyst. Analyze street-level images and provide a structured assessment. "
                "Return JSON with this schema: {\"storefront_viability\": {\"score\": 1-10, \"available_spaces\": str, \"condition\": str}, "
                "\"competitor_presence\": {\"restaurants\": str, \"retail\": str, \"notable_businesses\": [str]}, "
                "\"pedestrian_activity\": {\"level\": \"high\"|\"medium\"|\"low\", \"demographics\": str, \"peak_indicators\": str}, "
                "\"infrastructure\": {\"transit_access\": str, \"parking\": str, \"road_condition\": str}, "
                "\"overall_recommendation\": str (2-3 sentences)}"
            ),
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": f"Assess this area in {neighborhood}, Chicago for small business viability. Analyze the street scenes:"},
                *image_content,
            ],
        },
    ]

    try:
        client = get_openai_client()
        create_kwargs = build_chat_kwargs(
            model_name,
            vision_messages,
            max_completion_tokens=600,
            gpt5_max_completion_tokens=2048,
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        resp = await client.chat.completions.create(**create_kwargs)
        raw_content = resp.choices[0].message.content or "{}"
        choice = resp.choices[0]
        finish = getattr(choice, "finish_reason", None)
        usage = getattr(resp, "usage", None)
        print(f"[vision-assess] model={model_name} finish_reason={finish} usage={usage} raw_preview={raw_content[:200]!r}")
        assessment = json.loads(raw_content)
        return {
            "assessment": assessment,
            "frame_count": len(image_content),
            "neighborhood": neighborhood,
            "model": model_name,
        }
    except Exception as exc:
        print(f"[vision-assess] failed: {exc!r}")
        return JSONResponse({"error": f"Vision assessment failed: {exc}"}, status_code=500)
