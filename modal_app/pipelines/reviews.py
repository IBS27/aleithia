"""Review ingester — pulls business reviews from Yelp Fusion and Google Places.

Cadence: Daily
Sources: Yelp Fusion API, Google Places API
Pattern: async + FallbackChain + gather_with_limit + review velocity
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
import modal

from modal_app.common import SourceType, CHICAGO_NEIGHBORHOODS, build_document, detect_neighborhood, gather_with_limit, safe_queue_push, safe_volume_commit
from modal_app.dedup import SeenSet
from modal_app.fallback import FallbackChain
from modal_app.volume import app, volume, base_image, RAW_DATA_PATH

# Business categories to monitor
YELP_CATEGORIES = [
    "restaurants", "food", "coffee", "bars", "nightlife",
    "shopping", "beautysvc", "autorepair", "professional",
]

# Search neighborhoods
SEARCH_NEIGHBORHOODS = [
    "Lincoln Park, Chicago, IL",
    "Wicker Park, Chicago, IL",
    "Logan Square, Chicago, IL",
    "West Loop, Chicago, IL",
    "Pilsen, Chicago, IL",
    "Hyde Park, Chicago, IL",
    "Andersonville, Chicago, IL",
    "Chinatown, Chicago, IL",
]


async def _fetch_yelp_location(api_key: str, location: str, category: str) -> list[dict]:
    """Fetch a single Yelp location+category combination."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            "https://api.yelp.com/v3/businesses/search",
            params={
                "location": location,
                "categories": category,
                "sort_by": "rating",
                "limit": 10,
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        if resp.status_code == 429:
            print(f"Yelp rate limited [{location}/{category}]: HTTP 429, skipping")
            return []
        if resp.status_code != 200:
            print(f"Yelp error [{location}/{category}]: {resp.status_code}")
            return []

        docs = []
        for biz in resp.json().get("businesses", []):
            neighborhood = location.split(",")[0]
            docs.append({
                "id": f"yelp-{biz.get('id', '')}",
                "source": SourceType.YELP.value,
                "title": biz.get("name", ""),
                "content": (
                    f"{biz.get('name', '')} — {', '.join(c.get('title', '') for c in biz.get('categories', []))}. "
                    f"Rating: {biz.get('rating', 'N/A')}/5 ({biz.get('review_count', 0)} reviews). "
                    f"Price: {biz.get('price', 'N/A')}."
                ),
                "url": biz.get("url", ""),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metadata": {
                    "rating": biz.get("rating"),
                    "review_count": biz.get("review_count", 0),
                    "price": biz.get("price", ""),
                    "categories": [c.get("title", "") for c in biz.get("categories", [])],
                    "address": ", ".join(biz.get("location", {}).get("display_address", [])),
                    "phone": biz.get("phone", ""),
                    "is_closed": biz.get("is_closed", False),
                    "neighborhood": neighborhood,
                },
                "geo": {
                    "lat": biz.get("coordinates", {}).get("latitude"),
                    "lng": biz.get("coordinates", {}).get("longitude"),
                    "neighborhood": neighborhood,
                },
            })
        return docs


async def _fetch_yelp(api_key: str) -> list[dict]:
    """Fetch business data from Yelp Fusion API — parallel across locations."""
    if not api_key:
        print("YELP_API_KEY not set, skipping Yelp")
        return []

    coros = [
        _fetch_yelp_location(api_key, location, category)
        for location in SEARCH_NEIGHBORHOODS[:4]
        for category in YELP_CATEGORIES[:3]
    ]
    results = await gather_with_limit(coros, max_concurrent=5)
    docs = []
    for result in results:
        if result:
            docs.extend(result)
    return docs


async def _fetch_google_location(api_key: str, location: str) -> list[dict]:
    """Fetch a single Google Places location."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            "https://maps.googleapis.com/maps/api/place/textsearch/json",
            params={
                "query": f"businesses in {location}",
                "key": api_key,
            },
        )
        if resp.status_code == 429:
            print(f"Google Places rate limited [{location}]: HTTP 429, skipping")
            return []
        if resp.status_code != 200:
            print(f"Google Places error [{location}]: {resp.status_code}")
            return []

        docs = []
        neighborhood = location.split(",")[0]
        for place in resp.json().get("results", [])[:10]:
            docs.append({
                "id": f"gplaces-{place.get('place_id', '')}",
                "source": SourceType.GOOGLE_PLACES.value,
                "title": place.get("name", ""),
                "content": (
                    f"{place.get('name', '')} — {place.get('formatted_address', '')}. "
                    f"Rating: {place.get('rating', 'N/A')}/5 ({place.get('user_ratings_total', 0)} reviews)."
                ),
                "url": f"https://www.google.com/maps/place/?q=place_id:{place.get('place_id', '')}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metadata": {
                    "rating": place.get("rating"),
                    "user_ratings_total": place.get("user_ratings_total", 0),
                    "types": place.get("types", []),
                    "business_status": place.get("business_status", ""),
                    "price_level": place.get("price_level"),
                    "address": place.get("formatted_address", ""),
                    "neighborhood": neighborhood,
                },
                "geo": {
                    "lat": place.get("geometry", {}).get("location", {}).get("lat"),
                    "lng": place.get("geometry", {}).get("location", {}).get("lng"),
                    "neighborhood": neighborhood,
                },
            })
        return docs


async def _fetch_google_places(api_key: str) -> list[dict]:
    """Fetch business data from Google Places API — parallel across locations."""
    if not api_key:
        print("GOOGLE_PLACES_API_KEY not set, skipping Google Places")
        return []

    coros = [_fetch_google_location(api_key, loc) for loc in SEARCH_NEIGHBORHOODS[:4]]
    results = await gather_with_limit(coros, max_concurrent=5)
    docs = []
    for result in results:
        if result:
            docs.extend(result)
    return docs


def _compute_review_velocity(docs: list[dict]) -> None:
    """Annotate docs with review velocity estimates.

    Review velocity = review_count / estimated_months_open.
    Higher velocity = more active/popular business.
    """
    for doc in docs:
        meta = doc.get("metadata", {})
        review_count = meta.get("review_count") or meta.get("user_ratings_total", 0)
        if review_count and review_count > 0:
            velocity = round(review_count / 24, 2)
            meta["review_velocity"] = velocity
            meta["velocity_label"] = (
                "high" if velocity > 10
                else "medium" if velocity > 3
                else "low"
            )


@app.function(
    image=base_image,
    volumes={"/data": volume},
    secrets=[modal.Secret.from_name("alethia-secrets")],
    timeout=300,
)
async def review_ingester():
    """Ingest business reviews from Yelp Fusion and Google Places with fallback chains."""
    all_docs: list[dict] = []

    yelp_key = os.environ.get("YELP_API_KEY", "")
    gplaces_key = os.environ.get("GOOGLE_PLACES_API_KEY", "")

    # Yelp with fallback chain
    yelp_chain = FallbackChain("reviews", "yelp", cache_ttl_hours=168)
    yelp_docs = await yelp_chain.execute([
        lambda: _fetch_yelp(yelp_key),
    ])
    if yelp_docs:
        all_docs.extend(yelp_docs)
        print(f"Yelp: {len(yelp_docs)} businesses")

    # Google Places with fallback chain
    gplaces_chain = FallbackChain("reviews", "google_places", cache_ttl_hours=168)
    gplaces_docs = await gplaces_chain.execute([
        lambda: _fetch_google_places(gplaces_key),
    ])
    if gplaces_docs:
        all_docs.extend(gplaces_docs)
        print(f"Google Places: {len(gplaces_docs)} businesses")

    # Compute review velocity
    _compute_review_velocity(all_docs)

    # Dedup: skip already-seen documents
    seen = SeenSet("reviews")
    new_docs = [d for d in all_docs if not seen.contains(d["id"], max_age_hours=24)]
    print(f"Reviews: {len(all_docs)} fetched, {len(new_docs)} new (deduped {len(all_docs) - len(new_docs)})")

    if not new_docs:
        seen.save()
        await safe_volume_commit(volume, "reviews")
        print("Review ingester: no new documents")
        return 0

    # Save to volume
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = Path(RAW_DATA_PATH) / "reviews" / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    ingested_at = datetime.now(timezone.utc).isoformat()

    for doc_data in new_docs:
        doc_data["status"] = "raw"
        doc_data.setdefault("metadata", {})["ingested_at"] = ingested_at
        doc = build_document(doc_data)
        fpath = out_dir / f"{doc.id}.json"
        fpath.write_text(doc.model_dump_json(indent=2))
        seen.add(doc_data["id"])

    from modal_app.classify import doc_queue
    await safe_queue_push(doc_queue, new_docs, "reviews")

    seen.save()
    await safe_volume_commit(volume, "reviews")
    print(f"Review ingester complete: {len(new_docs)} documents saved to {out_dir}")
    return len(new_docs)
