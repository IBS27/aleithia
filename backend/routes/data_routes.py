"""
Routes that serve ingested Chicago data from local JSON files.
Data was downloaded from Modal Volume after pipeline runs.
"""

import json
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from database import get_db
from models import UserProfile, QueryResult
from auth import extract_user_id

router = APIRouter()

DATA_DIR = Path(__file__).parent.parent / "data"


class UserProfileSchema(BaseModel):
    business_type: Optional[str] = None
    neighborhood: Optional[str] = None
    risk_tolerance: Optional[str] = None

    class Config:
        from_attributes = True


class UserProfileResponse(UserProfileSchema):
    clerk_user_id: str
    created_at: str
    updated_at: str


class UserQueryCreateSchema(BaseModel):
    query_text: str = Field(..., min_length=1, max_length=1000)
    business_type: str = Field(..., min_length=1, max_length=255)
    neighborhood: str = Field(..., min_length=1, max_length=255)


class UserQueryResponse(BaseModel):
    id: int
    clerk_user_id: str
    query_text: str
    business_type: str
    neighborhood: str
    created_at: str

    class Config:
        from_attributes = True


def _load_all(source: str) -> list[dict]:
    """Load all valid JSON files from a source directory."""
    source_dir = DATA_DIR / source
    if not source_dir.exists():
        return []
    docs = []
    for f in sorted(source_dir.iterdir()):
        if f.suffix != ".json":
            continue
        try:
            with open(f) as fh:
                doc = json.load(fh)
                docs.append(doc)
        except (json.JSONDecodeError, OSError):
            continue
    return docs


def _filter_by_neighborhood(docs: list[dict], neighborhood: str) -> list[dict]:
    """Filter documents that match a neighborhood (case-insensitive).
    Checks geo fields, content, metadata, and address info."""
    nb = neighborhood.lower()
    results = []
    for doc in docs:
        geo = doc.get("geo", {})
        doc_nb = (geo.get("neighborhood") or "").lower()
        doc_ca = (geo.get("community_area_name") or "").lower()
        content = (doc.get("content") or "").lower()
        # Also check raw_record for address fields
        raw = doc.get("metadata", {}).get("raw_record", {})
        address = (raw.get("address") or "").lower()
        title = (doc.get("title") or "").lower()
        community = (raw.get("community_area_name") or "").lower()
        if nb in doc_nb or nb in doc_ca or nb in content or nb in address or nb in title or nb in community:
            results.append(doc)
    return results


def _filter_by_type(docs: list[dict], dataset: str) -> list[dict]:
    """Filter public_data docs by dataset type (e.g. food_inspections)."""
    return [
        d for d in docs
        if d.get("metadata", {}).get("dataset") == dataset
    ]


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
    sources = {}
    for name in ["public_data", "demographics", "politics", "news", "realestate"]:
        d = DATA_DIR / name
        if d.exists():
            count = sum(1 for f in d.iterdir() if f.suffix == ".json")
            sources[name] = {"count": count, "active": count > 0}
        else:
            sources[name] = {"count": 0, "active": False}

    # Add sources we don't have data for yet
    for name in ["reddit", "reviews"]:
        sources[name] = {"count": 0, "active": False}

    return sources


@router.get("/geo")
async def get_geo():
    """Return GeoJSON FeatureCollection for map visualization."""
    geo_path = DATA_DIR / "processed" / "geo" / "neighborhood_metrics.json"
    if geo_path.exists():
        with open(geo_path) as f:
            return json.load(f)
    return {"type": "FeatureCollection", "features": []}


def _empty_graph_response():
    return {"documents": [], "pagination": {"currentPage": 1, "totalPages": 0}}


def _transform_doc_for_graph(doc: dict) -> dict:
    """Transform Supermemory API doc to DocumentWithMemories format. Preserves all fields for graph viz."""
    memories = doc.get("memories", doc.get("memoryEntries", []))
    memory_entries = []
    for m in memories:
        rels = m.get("memoryRelations")
        if isinstance(rels, dict):
            rels = [{"targetMemoryId": k, "relationType": v} for k, v in rels.items() if v in ("updates", "extends", "derives")]
        entry = {
            "id": m.get("id", ""),
            "documentId": doc.get("id", ""),
            "content": m.get("memory", m.get("content")),
            "summary": m.get("summary"),
            "title": m.get("title"),
            "createdAt": m.get("createdAt", m.get("created_at")),
            "updatedAt": m.get("updatedAt", m.get("updated_at")),
            "isLatest": m.get("isLatest", True),
            "isForgotten": m.get("isForgotten"),
            "forgetAfter": m.get("forgetAfter"),
            "relation": m.get("relation") or m.get("changeType"),
            "memoryRelations": rels if isinstance(rels, list) else m.get("memoryRelations"),
            "updatesMemoryId": m.get("updatesMemoryId"),
            "nextVersionId": m.get("nextVersionId"),
            "parentMemoryId": m.get("parentMemoryId"),
            "rootMemoryId": m.get("rootMemoryId"),
            "metadata": m.get("metadata"),
            "spaceId": m.get("spaceId"),
            "spaceContainerTag": m.get("spaceContainerTag"),
        }
        memory_entries.append(entry)
    out = {
        "id": doc.get("id", ""),
        "customId": doc.get("customId"),
        "title": doc.get("title"),
        "content": doc.get("content"),
        "summary": doc.get("summary"),
        "url": doc.get("url"),
        "source": doc.get("source"),
        "type": doc.get("type", doc.get("documentType")),
        "status": doc.get("status", "done"),
        "metadata": doc.get("metadata"),
        "createdAt": doc.get("createdAt", doc.get("created_at")),
        "updatedAt": doc.get("updatedAt", doc.get("updated_at")),
        "memoryEntries": memory_entries,
    }
    if doc.get("x") is not None:
        out["x"] = doc["x"]
    if doc.get("y") is not None:
        out["y"] = doc["y"]
    if doc.get("summaryEmbedding") is not None:
        out["summaryEmbedding"] = doc["summaryEmbedding"]
    return out


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
                docs = [_transform_doc_for_graph(d) for d in raw_docs]
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
                docs = [_transform_doc_for_graph(d) for d in raw_docs]
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
    """Return compressed data summaries."""
    summaries = {}
    summary_dir = DATA_DIR / "processed" / "summaries"
    if summary_dir.exists():
        for f in summary_dir.iterdir():
            if f.suffix == ".json":
                with open(f) as fh:
                    key = f.stem.replace("_summary", "")
                    summaries[key] = json.load(fh)
    return summaries


@router.get("/inspections")
async def get_inspections(
    neighborhood: Optional[str] = Query(None),
    result: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
):
    """Return food inspection records."""
    docs = _filter_by_type(_load_all("public_data"), "food_inspections")
    if neighborhood:
        docs = _filter_by_neighborhood(docs, neighborhood)
    if result:
        docs = [
            d for d in docs
            if d.get("metadata", {}).get("raw_record", {}).get("results", "").lower() == result.lower()
        ]
    return docs[:limit]


@router.get("/permits")
async def get_permits(
    neighborhood: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
):
    """Return building permit records."""
    docs = _filter_by_type(_load_all("public_data"), "building_permits")
    if neighborhood:
        docs = _filter_by_neighborhood(docs, neighborhood)
    return docs[:limit]


@router.get("/licenses")
async def get_licenses(
    neighborhood: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
):
    """Return business license records."""
    docs = _filter_by_type(_load_all("public_data"), "business_licenses")
    if neighborhood:
        docs = _filter_by_neighborhood(docs, neighborhood)
    return docs[:limit]


@router.get("/demographics")
async def get_demographics(limit: int = Query(50, le=200)):
    """Return Census demographics data."""
    return _load_all("demographics")[:limit]


@router.get("/news")
async def get_news(limit: int = Query(20, le=100)):
    """Return news articles."""
    docs = _load_all("news")
    # Sort by timestamp descending
    docs.sort(key=lambda d: d.get("timestamp", ""), reverse=True)
    return docs[:limit]


@router.get("/politics")
async def get_politics(limit: int = Query(50, le=200)):
    """Return political/legislative records."""
    docs = _load_all("politics")
    docs.sort(key=lambda d: d.get("timestamp", ""), reverse=True)
    return docs[:limit]


@router.get("/neighborhood/{name}")
async def get_neighborhood(name: str):
    """Return all data for a specific neighborhood."""
    all_public = _load_all("public_data")

    all_inspections = _filter_by_type(all_public, "food_inspections")
    inspections = _filter_by_neighborhood(all_inspections, name)
    # If no neighborhood-specific inspections, show all (data lacks geo tags)
    if not inspections:
        inspections = all_inspections

    all_permits = _filter_by_type(all_public, "building_permits")
    permits = _filter_by_neighborhood(all_permits, name)
    if not permits:
        permits = all_permits

    all_licenses = _filter_by_type(all_public, "business_licenses")
    licenses = _filter_by_neighborhood(all_licenses, name)
    if not licenses:
        licenses = all_licenses

    all_news = _load_all("news")
    news = _filter_by_neighborhood(all_news, name)
    if not news:
        news = all_news

    all_politics = _load_all("politics")
    politics = _filter_by_neighborhood(all_politics, name)
    if not politics:
        politics = all_politics

    # Get demographics from GeoJSON
    demo = {}
    geo_path = DATA_DIR / "processed" / "geo" / "neighborhood_metrics.json"
    if geo_path.exists():
        with open(geo_path) as f:
            geojson = json.load(f)
            for feature in geojson.get("features", []):
                props = feature.get("properties", {})
                if props.get("neighborhood", "").lower() == name.lower():
                    demo = props
                    break

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
    }
