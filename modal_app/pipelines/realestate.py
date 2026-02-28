"""Real estate ingester — pulls commercial real estate listings for Chicago.

Cadence: Weekly
Sources: LoopNet (fallback to placeholders for demo)
Pattern: async + FallbackChain (LoopNet → placeholders → cache) + gather_with_limit
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
import modal

from modal_app.common import Document, SourceType, CHICAGO_NEIGHBORHOODS, detect_neighborhood, gather_with_limit
from modal_app.fallback import FallbackChain
from modal_app.volume import app, volume, base_image, RAW_DATA_PATH

# LoopNet search parameters
LOOPNET_PROPERTY_TYPES = ["retail", "restaurant", "office", "industrial"]

SEARCH_AREAS = [
    "Lincoln Park", "Wicker Park", "Logan Square", "West Loop",
    "River North", "South Loop", "Pilsen", "Hyde Park",
]


async def _fetch_loopnet_area(area: str) -> list[dict]:
    """Fetch listings for a single area from LoopNet."""
    docs = []
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            "https://www.loopnet.com/api/search",
            params={
                "q": f"commercial property {area} Chicago IL",
                "type": "lease",
            },
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; AlethiaBot/0.1; educational hackathon project)",
            },
        )

        if resp.status_code != 200:
            print(f"LoopNet [{area}]: {resp.status_code} (expected — use CoStar API for production)")
            return docs

        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        listings = data.get("listings", data.get("results", []))

        for listing in listings[:10]:
            docs.append({
                "id": f"realestate-{listing.get('id', hash(str(listing)))}",
                "source": SourceType.REAL_ESTATE.value,
                "title": listing.get("title", listing.get("address", f"Commercial Property in {area}")),
                "content": (
                    f"Commercial property in {area}, Chicago. "
                    f"Type: {listing.get('property_type', 'N/A')}. "
                    f"Size: {listing.get('size', 'N/A')} sqft. "
                    f"Price: {listing.get('price', 'N/A')}."
                ),
                "url": listing.get("url", ""),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metadata": {
                    "property_type": listing.get("property_type", ""),
                    "size_sqft": listing.get("size", ""),
                    "price": listing.get("price", ""),
                    "neighborhood": area,
                    "listing_type": listing.get("listing_type", "lease"),
                },
                "geo": {
                    "neighborhood": area,
                    "lat": listing.get("latitude"),
                    "lng": listing.get("longitude"),
                },
            })

    return docs


async def _fetch_loopnet_listings() -> list[dict]:
    """Fetch all areas in parallel from LoopNet."""
    coros = [_fetch_loopnet_area(area) for area in SEARCH_AREAS]
    results = await gather_with_limit(coros, max_concurrent=5)
    docs = []
    for result in results:
        if result:
            docs.extend(result)
    return docs


async def _create_placeholder_listings() -> list[dict]:
    """Create placeholder listings to demonstrate the pipeline structure."""
    placeholder_data = [
        {
            "area": "Lincoln Park",
            "type": "Retail",
            "size": "1,200",
            "price": "$3,500/mo",
            "desc": "Street-level retail space on Clark St. High foot traffic, near DePaul.",
        },
        {
            "area": "West Loop",
            "type": "Restaurant",
            "size": "2,800",
            "price": "$8,000/mo",
            "desc": "Restaurant space on Randolph St. Former restaurant, grease trap installed.",
        },
        {
            "area": "Wicker Park",
            "type": "Retail/Coffee",
            "size": "900",
            "price": "$2,800/mo",
            "desc": "Corner unit on Milwaukee Ave. Great visibility, outdoor seating potential.",
        },
        {
            "area": "Pilsen",
            "type": "Mixed Use",
            "size": "3,200",
            "price": "$4,200/mo",
            "desc": "Ground floor commercial with apartment above. 18th St corridor.",
        },
        {
            "area": "Logan Square",
            "type": "Restaurant",
            "size": "1,800",
            "price": "$5,500/mo",
            "desc": "Former taqueria on Kedzie. Built-in hood system, walk-in cooler.",
        },
        {
            "area": "Hyde Park",
            "type": "Office/Retail",
            "size": "1,500",
            "price": "$2,200/mo",
            "desc": "53rd St storefront near University of Chicago. Student foot traffic.",
        },
        {
            "area": "River North",
            "type": "Restaurant/Bar",
            "size": "3,500",
            "price": "$12,000/mo",
            "desc": "Prime location on Hubbard. Liquor license transferable. Patio space.",
        },
        {
            "area": "South Loop",
            "type": "Retail",
            "size": "2,000",
            "price": "$4,800/mo",
            "desc": "Michigan Ave ground floor. Near Roosevelt CTA. New construction.",
        },
    ]

    docs = []
    for i, p in enumerate(placeholder_data):
        docs.append({
            "id": f"realestate-placeholder-{i}",
            "source": SourceType.REAL_ESTATE.value,
            "title": f"{p['type']} Space — {p['area']}",
            "content": f"{p['desc']} Size: {p['size']} sqft. Price: {p['price']}.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": {
                "property_type": p["type"],
                "size_sqft": p["size"],
                "price": p["price"],
                "neighborhood": p["area"],
                "is_placeholder": True,
            },
            "geo": {"neighborhood": p["area"]},
        })

    return docs


@app.function(
    image=base_image,
    volumes={"/data": volume},
    secrets=[modal.Secret.from_name("alethia-secrets")],
    schedule=modal.Period(days=7),
    timeout=180,
)
async def realestate_ingester():
    """Ingest commercial real estate data for Chicago neighborhoods."""
    # FallbackChain: LoopNet → placeholders → cache
    chain = FallbackChain("realestate", "listings")
    all_docs = await chain.execute([
        _fetch_loopnet_listings,
        _create_placeholder_listings,
    ])

    if not all_docs:
        print("Real estate ingester: no data from any source")
        return 0

    # Save to volume
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = Path(RAW_DATA_PATH) / "realestate" / date_str
    out_dir.mkdir(parents=True, exist_ok=True)

    for doc_data in all_docs:
        doc = Document(**{k: v for k, v in doc_data.items() if k != "timestamp"})
        fpath = out_dir / f"{doc.id}.json"
        fpath.write_text(doc.model_dump_json(indent=2))

    volume.commit()
    print(f"Real estate ingester complete: {len(all_docs)} documents saved to {out_dir}")
    return len(all_docs)
