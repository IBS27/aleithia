"""Routes that serve Aleithia data from shared raw/processed JSON files."""

import os
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict, Field

from database import get_db
from models import UserProfile, QueryResult
from auth import extract_user_id
from read_helpers import (
    filter_docs_by_neighborhood,
    filter_public_data_by_dataset,
    transform_doc_for_graph,
)
from shared_data import (
    get_raw_data_dir,
    get_raw_source_stats,
    load_json_docs_from_directory,
    load_processed_json,
)

router = APIRouter()


class UserProfileSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    business_type: Optional[str] = None
    neighborhood: Optional[str] = None
    risk_tolerance: Optional[str] = None


class UserProfileResponse(UserProfileSchema):
    clerk_user_id: str
    created_at: str
    updated_at: str


class UserQueryCreateSchema(BaseModel):
    query_text: str = Field(..., min_length=1, max_length=1000)
    business_type: str = Field(..., min_length=1, max_length=255)
    neighborhood: str = Field(..., min_length=1, max_length=255)


class UserQueryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    clerk_user_id: str
    query_text: str
    business_type: str
    neighborhood: str
    created_at: str


STEP4_SOURCE_NAMES = [
    "news",
    "politics",
    "federal_register",
    "public_data",
    "demographics",
    "reddit",
    "reviews",
    "realestate",
    "tiktok",
]

_TIKTOK_CREATOR_RE = re.compile(r"tiktok\.com/@([^/?#]+)/video/", re.IGNORECASE)


def _load_source_docs(source: str, limit: int | None = None) -> list[dict]:
    """Load raw JSON documents using the same directory traversal shape as Modal."""
    return load_json_docs_from_directory(
        get_raw_data_dir() / source,
        limit=limit,
        on_error=lambda json_file, exc: print(
            f"_load_source_docs [{source}]: corrupted JSON {json_file.name}: {exc}"
        ),
    )


def _load_all(source: str) -> list[dict]:
    return _load_source_docs(source)


def _load_city_demographics_summary() -> dict:
    summary = load_processed_json("demographics_summary.json", default=None)
    if not isinstance(summary, dict):
        summary = load_processed_json("summaries", "demographics_summary.json", default={})
    return summary.get("city_wide", {}) if isinstance(summary, dict) else {}


def _is_count_only_text(value: str) -> bool:
    text = (value or "").strip()
    return bool(text) and bool(re.fullmatch(r"\d[\d,.\s]*[KMBkmb]?", text))


def _extract_tiktok_creator_from_url(video_url: str) -> str:
    match = _TIKTOK_CREATOR_RE.search(video_url or "")
    if not match:
        return ""
    return match.group(1).strip().lstrip("@")


def _extract_transcript_headline(content: str, max_len: int = 120) -> str:
    text = (content or "").strip()
    if not text:
        return ""
    if "[Transcript]" in text:
        text = text.split("[Transcript]", 1)[1].strip()
    text = re.sub(r"^\d[\d,.\s]*[KMBkmb]?\s*[:\-]?\s*", "", text)
    text = re.sub(r"\s+", " ", text)
    for sep in (". ", "! ", "? "):
        if sep in text:
            text = text.split(sep, 1)[0].strip()
            break
    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0]
    return text.strip(" -:;,.")


def _normalize_tiktok_content(content: str) -> str:
    text = (content or "").strip()
    if not text:
        return ""
    if "\n[Transcript]" in text:
        first_line, remainder = text.split("\n", 1)
        if _is_count_only_text(first_line):
            text = remainder.strip()
    if _is_count_only_text(text):
        return ""
    return text


def _parse_view_count(value: str) -> int:
    text = (value or "").strip().replace(",", "").upper()
    if not text:
        return 0
    match = re.match(r"^(\d+(?:\.\d+)?)\s*([KMB])?$", text)
    if not match:
        return 0
    num = float(match.group(1))
    suffix = match.group(2) or ""
    if suffix == "K":
        num *= 1_000
    elif suffix == "M":
        num *= 1_000_000
    elif suffix == "B":
        num *= 1_000_000_000
    return int(round(num))


def _normalize_tiktok_doc(doc: dict) -> dict:
    normalized = dict(doc)
    metadata = dict(normalized.get("metadata") or {})
    normalized["metadata"] = metadata

    content = _normalize_tiktok_content(normalized.get("content", ""))
    normalized["content"] = content

    creator = str(metadata.get("creator", "") or "").strip().lstrip("@")
    if not creator:
        creator = _extract_tiktok_creator_from_url(normalized.get("url", ""))
    if creator:
        metadata["creator"] = creator

    search_query = str(metadata.get("search_query", "") or "").strip()
    if not search_query:
        query_match = re.search(r"TikTok video related to:\s*(.+)$", content, re.IGNORECASE)
        if query_match:
            search_query = query_match.group(1).strip()
    if search_query:
        metadata["search_query"] = search_query

    views_normalized = _parse_view_count(str(metadata.get("views_normalized", "") or ""))
    if views_normalized <= 0:
        views_normalized = _parse_view_count(str(metadata.get("views", "") or ""))
    metadata["views_normalized"] = views_normalized

    query_scope = str(metadata.get("query_scope", "") or "").strip().lower()
    if query_scope in ("city", "local"):
        metadata["query_scope"] = query_scope

    title = str(normalized.get("title", "") or "").strip()
    if not title or _is_count_only_text(title) or title.lower() == "tiktok video":
        transcript_title = _extract_transcript_headline(content)
        if transcript_title:
            title = transcript_title
        elif creator:
            title = f"@{creator}"
        elif search_query:
            title = f"TikTok: {search_query}"
        else:
            title = "TikTok video"
    normalized["title"] = title

    return normalized


def _is_low_quality_tiktok_doc(doc: dict) -> bool:
    title = (doc.get("title", "") or "").strip()
    content = (doc.get("content", "") or "").strip()
    meta = doc.get("metadata", {}) or {}
    creator = str(meta.get("creator", "") or "").strip()
    hashtags = meta.get("hashtags", []) or []
    transcript_present = "[Transcript]" in content
    meaningful_content = bool(content) and not _is_count_only_text(content)
    return bool(
        _is_count_only_text(title)
        and not meaningful_content
        and not creator
        and not hashtags
        and not transcript_present
    )


@router.get("/user/profile", response_model=UserProfileResponse)
async def get_user_profile(
    db: Session = Depends(get_db),
    user_id: str = Depends(extract_user_id),
):
    """Get user's saved profile settings."""
    profile = db.query(UserProfile).filter(UserProfile.clerk_user_id == user_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="No profile found for user")
    return {
        "clerk_user_id": profile.clerk_user_id,
        "business_type": profile.business_type,
        "neighborhood": profile.neighborhood,
        "risk_tolerance": profile.risk_tolerance,
        "created_at": profile.created_at.isoformat(),
        "updated_at": profile.updated_at.isoformat(),
    }


@router.put("/user/profile", response_model=UserProfileResponse)
async def update_user_profile(
    payload: UserProfileSchema,
    db: Session = Depends(get_db),
    user_id: str = Depends(extract_user_id),
):
    """Save or update user's profile settings."""
    profile = db.query(UserProfile).filter(UserProfile.clerk_user_id == user_id).first()
    if not profile:
        profile = UserProfile(clerk_user_id=user_id)
        db.add(profile)
    
    if payload.business_type is not None:
        profile.business_type = payload.business_type
    if payload.neighborhood is not None:
        profile.neighborhood = payload.neighborhood
    if payload.risk_tolerance is not None:
        profile.risk_tolerance = payload.risk_tolerance
    
    db.commit()
    db.refresh(profile)
    
    return {
        "clerk_user_id": profile.clerk_user_id,
        "business_type": profile.business_type,
        "neighborhood": profile.neighborhood,
        "risk_tolerance": profile.risk_tolerance,
        "created_at": profile.created_at.isoformat(),
        "updated_at": profile.updated_at.isoformat(),
    }


@router.post("/user/queries", response_model=UserQueryResponse)
async def create_user_query(
    payload: UserQueryCreateSchema,
    db: Session = Depends(get_db),
    user_id: str = Depends(extract_user_id),
):
    """Persist a user's query to query history."""
    query = QueryResult(
        clerk_user_id=user_id,
        query_text=payload.query_text,
        business_type=payload.business_type,
        neighborhood=payload.neighborhood,
        result_summary=None,
    )
    db.add(query)
    db.commit()
    db.refresh(query)

    return {
        "id": query.id,
        "clerk_user_id": query.clerk_user_id,
        "query_text": query.query_text,
        "business_type": query.business_type,
        "neighborhood": query.neighborhood,
        "created_at": query.created_at.isoformat(),
    }


@router.get("/user/queries", response_model=list[UserQueryResponse])
async def get_user_queries(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    user_id: str = Depends(extract_user_id),
):
    """Get most recent queries for a user."""
    queries = (
        db.query(QueryResult)
        .filter(QueryResult.clerk_user_id == user_id)
        .order_by(QueryResult.created_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "id": query.id,
            "clerk_user_id": query.clerk_user_id,
            "query_text": query.query_text,
            "business_type": query.business_type,
            "neighborhood": query.neighborhood,
            "created_at": query.created_at.isoformat(),
        }
        for query in queries
    ]


# Legacy endpoints for backward compatibility
@router.get("/user/settings", response_model=UserProfileResponse)
async def get_user_settings(
    db: Session = Depends(get_db),
    user_id: str = Depends(extract_user_id),
):
    """Get saved query settings for a user (legacy, use /user/profile)."""
    return await get_user_profile(db, user_id)


@router.put("/user/settings", response_model=UserProfileResponse)
async def put_user_settings(
    payload: UserProfileSchema,
    db: Session = Depends(get_db),
    user_id: str = Depends(extract_user_id),
):
    """Save last queried settings for a user (legacy, use /user/profile)."""
    return await update_user_profile(payload, db, user_id)


@router.get("/sources")
async def get_sources():
    """Return available data sources with counts."""
    source_stats = get_raw_source_stats(STEP4_SOURCE_NAMES)
    return {
        source: {"count": data["doc_count"], "active": data["active"]}
        for source, data in source_stats.items()
    }


@router.get("/geo")
async def get_geo():
    """Return GeoJSON FeatureCollection for map visualization."""
    return load_processed_json(
        "geo",
        "neighborhood_metrics.json",
        default={"type": "FeatureCollection", "features": []},
    )


def _empty_graph_response():
    return {"documents": [], "pagination": {"currentPage": 1, "totalPages": 0}}


@router.get("/graph")
async def get_graph(page: int = Query(1, ge=1), limit: int = Query(500, ge=1, le=500)):
    """Proxy to Supermemory for Memory Graph. Tries graph/viewport first, then documents/list."""
    api_key = os.environ.get("SUPERMEMORY_API_KEY", "")
    key_preview = f"{api_key[:6]}...{api_key[-4:]}" if len(api_key) > 10 else "(empty)"
    print(f"[graph] SUPERMEMORY_API_KEY: {key_preview} (len={len(api_key)})")
    if not api_key:
        print("[graph] No API key, returning empty")
        return _empty_graph_response()

    import httpx
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    async with httpx.AsyncClient(timeout=15) as client:
        # 1. Graph viewport
        url1 = "https://api.supermemory.ai/v3/graph/viewport"
        try:
            print(f"[graph] Trying {url1}")
            resp = await client.post(
                url1,
                headers=headers,
                json={
                    "viewport": {"minX": 0, "maxX": 1000000, "minY": 0, "maxY": 1000000},
                    "limit": min(limit, 500),
                },
            )
            print(f"[graph] {url1} -> status={resp.status_code}, body_len={len(resp.text)}")
            if resp.status_code != 200:
                print(f"[graph] {url1} response: {resp.text[:500]}")
            if resp.status_code == 200:
                data = resp.json()
                raw_docs = data.get("documents", [])
                docs = [transform_doc_for_graph(d) for d in raw_docs]
                total = data.get("totalCount", len(docs))
                print(f"[graph] SUCCESS viewport: {len(docs)} docs, totalCount={total}")
                return {
                    "documents": docs,
                    "pagination": {"currentPage": 1, "totalPages": max(1, (total + limit - 1) // limit)},
                }
        except Exception as e:
            print(f"[graph] {url1} exception: {type(e).__name__}: {e}")

        # 2. Documents list - fallback
        payload = {"page": page, "limit": limit, "sort": "createdAt", "order": "desc"}
        for url in [
            "https://api.supermemory.ai/v3/documents/list",
            "https://api.supermemory.ai/v3/documents/documents",
        ]:
            try:
                print(f"[graph] Trying {url}")
                resp = await client.post(url, headers=headers, json=payload)
                print(f"[graph] {url} -> status={resp.status_code}, body_len={len(resp.text)}")
                if resp.status_code in (401, 403):
                    print(f"[graph] {url} auth error: {resp.text[:300]}")
                    continue
                resp.raise_for_status()
                data = resp.json()
                raw_docs = data.get("documents") or data.get("memories") or []
                docs = [transform_doc_for_graph(d) for d in raw_docs]
                pagination = data.get("pagination", {})
                print(f"[graph] SUCCESS {url}: {len(docs)} docs")
                return {"documents": docs, "pagination": pagination}
            except Exception as e:
                print(f"[graph] {url} exception: {type(e).__name__}: {e}")
                continue
    print("[graph] All endpoints failed, returning empty")
    return _empty_graph_response()


@router.get("/summary")
async def get_summary():
    """Return aggregate source counts and citywide demographics."""
    source_stats = get_raw_source_stats(STEP4_SOURCE_NAMES)
    source_counts = {source: data["doc_count"] for source, data in source_stats.items()}
    return {
        "total_documents": sum(source_counts.values()),
        "source_counts": source_counts,
        "demographics": _load_city_demographics_summary(),
    }


@router.get("/inspections")
async def get_inspections(
    neighborhood: str = "",
    result: str = "",
    limit: int = Query(100, ge=1, le=200),
):
    """Return food inspection records."""
    docs = filter_public_data_by_dataset(_load_source_docs("public_data", limit=500), "food_inspections")
    if neighborhood:
        docs = filter_docs_by_neighborhood(docs, neighborhood)
    if result:
        docs = [
            d for d in docs
            if d.get("metadata", {}).get("raw_record", {}).get("results", "").lower() == result.lower()
        ]
    return docs[:limit]


@router.get("/permits")
async def get_permits(
    neighborhood: str = "",
    limit: int = Query(100, ge=1, le=200),
):
    """Return building permit records."""
    docs = filter_public_data_by_dataset(_load_source_docs("public_data", limit=500), "building_permits")
    if neighborhood:
        docs = filter_docs_by_neighborhood(docs, neighborhood)
    return docs[:limit]


@router.get("/licenses")
async def get_licenses(
    neighborhood: str = "",
    limit: int = Query(100, ge=1, le=200),
):
    """Return business license records."""
    docs = filter_public_data_by_dataset(_load_source_docs("public_data", limit=500), "business_licenses")
    if neighborhood:
        docs = filter_docs_by_neighborhood(docs, neighborhood)
    return docs[:limit]


@router.get("/demographics")
async def get_demographics(limit: int = Query(50, le=200)):
    """Return Census demographics data."""
    return _load_all("demographics")[:limit]


@router.get("/news")
async def get_news(limit: int = Query(50, ge=1, le=100)):
    """Return news articles."""
    return _load_source_docs("news", limit=limit)


@router.get("/politics")
async def get_politics(limit: int = Query(50, ge=1, le=100)):
    """Return political/legislative records."""
    return _load_source_docs("politics", limit=limit)


@router.get("/reddit")
async def get_reddit(neighborhood: str = "", limit: int = Query(100, ge=1, le=200)):
    """Return Reddit documents."""
    docs = _load_source_docs("reddit", limit=100)
    if neighborhood:
        docs = filter_docs_by_neighborhood(docs, neighborhood)
    return docs[:limit]


@router.get("/reviews")
async def get_reviews(neighborhood: str = "", limit: int = Query(100, ge=1, le=200)):
    """Return review documents."""
    docs = _load_source_docs("reviews", limit=100)
    if neighborhood:
        docs = filter_docs_by_neighborhood(docs, neighborhood)
    return docs[:limit]


@router.get("/realestate")
async def get_realestate(neighborhood: str = "", limit: int = Query(50, ge=1, le=100)):
    """Return real estate documents."""
    docs = _load_source_docs("realestate", limit=50)
    if neighborhood:
        docs = filter_docs_by_neighborhood(docs, neighborhood)
    return docs[:limit]


@router.get("/tiktok")
async def get_tiktok(neighborhood: str = "", limit: int = Query(50, ge=1, le=100)):
    """Return normalized TikTok documents."""
    docs = [_normalize_tiktok_doc(doc) for doc in _load_source_docs("tiktok", limit=50)]
    docs = [doc for doc in docs if not _is_low_quality_tiktok_doc(doc)]
    if neighborhood:
        docs = filter_docs_by_neighborhood(docs, neighborhood)
    return docs[:limit]


@router.get("/cctv/timeseries/{neighborhood}")
async def get_cctv_timeseries(neighborhood: str):
    """Return 24h CCTV traffic timeseries for a neighborhood."""
    entry = load_processed_json("cctv", "synthetic_analytics.json", default={}).get(neighborhood)
    if not entry:
        raise HTTPException(status_code=404, detail=f"No CCTV data for {neighborhood}")
    return entry["timeseries"]


@router.get("/neighborhood/{name}")
async def get_neighborhood(name: str):
    """Return all data for a specific neighborhood."""
    all_public = _load_all("public_data")

    all_inspections = filter_public_data_by_dataset(all_public, "food_inspections")
    inspections = filter_docs_by_neighborhood(all_inspections, name)
    # If no neighborhood-specific inspections, show all (data lacks geo tags)
    if not inspections:
        inspections = all_inspections

    all_permits = filter_public_data_by_dataset(all_public, "building_permits")
    permits = filter_docs_by_neighborhood(all_permits, name)
    if not permits:
        permits = all_permits

    all_licenses = filter_public_data_by_dataset(all_public, "business_licenses")
    licenses = filter_docs_by_neighborhood(all_licenses, name)
    if not licenses:
        licenses = all_licenses

    all_news = _load_all("news")
    news = filter_docs_by_neighborhood(all_news, name)
    if not news:
        news = all_news

    all_politics = _load_all("politics")
    politics = filter_docs_by_neighborhood(all_politics, name)
    if not politics:
        politics = all_politics

    # Get demographics from GeoJSON
    demo = {}
    geojson = load_processed_json("geo", "neighborhood_metrics.json", default={"features": []})
    for feature in geojson.get("features", []):
        props = feature.get("properties", {})
        if props.get("neighborhood", "").lower() == name.lower():
            demo = props
            break

    # CCTV synthetic analytics
    cctv_entry = load_processed_json("cctv", "synthetic_analytics.json", default={}).get(name, {})
    cctv_data = cctv_entry.get("cameras")
    if cctv_data:
        # Enrich with peak_hour/peak_pedestrians from timeseries
        ts = cctv_entry.get("timeseries", {})
        cctv_data["peak_hour"] = ts.get("peak_hour")
        cctv_data["peak_pedestrians"] = ts.get("peak_pedestrians")

    return {
        "neighborhood": name,
        "metrics": demo,
        "inspections": inspections[:20],
        "permits": permits[:20],
        "licenses": licenses[:20],
        "news": news[:10],
        "politics": politics[:10],
        "inspection_stats": {
            "total": len(inspections),
            "failed": sum(
                1 for d in inspections
                if d.get("metadata", {}).get("raw_record", {}).get("results") == "Fail"
            ),
            "passed": sum(
                1 for d in inspections
                if d.get("metadata", {}).get("raw_record", {}).get("results") == "Pass"
            ),
        },
        "permit_count": len(permits),
        "license_count": len(licenses),
        "cctv": cctv_data,
    }
