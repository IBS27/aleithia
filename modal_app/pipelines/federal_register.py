"""Federal Register pipeline — tracks regulations from SBA, FDA, OSHA, EPA.

Cadence: Daily
Source: Federal Register API (free, no auth required)
Pattern: async + FallbackChain + modal.Retries
"""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx
import modal

from modal_app.common import SourceType, build_document, detect_neighborhood, safe_queue_push, safe_volume_commit
from modal_app.dedup import SeenSet
from modal_app.fallback import FallbackChain
from modal_app.volume import app, volume, base_image, RAW_DATA_PATH

FEDERAL_REGISTER_BASE = "https://www.federalregister.gov/api/v1"

# Agencies relevant to small businesses (slug → display label)
TARGET_AGENCIES = {
    "small-business-administration": "SBA",
    "food-and-drug-administration": "FDA",
    "occupational-safety-and-health-administration": "OSHA",
    "environmental-protection-agency": "EPA",
}

# Keywords for filtering relevant documents
BUSINESS_KEYWORDS = [
    "small business", "restaurant", "food service", "retail",
    "occupational safety", "health inspection", "zoning",
    "environmental compliance", "labor", "wage", "employment",
    "business license", "permit", "commercial",
]


async def _fetch_federal_register(since_days: int = 7) -> list[dict]:
    """Fetch recent documents from Federal Register API."""
    docs = []
    since = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%Y-%m-%d")

    async with httpx.AsyncClient(timeout=30) as client:
        for agency_slug, agency_label in TARGET_AGENCIES.items():
            try:
                resp = await client.get(
                    f"{FEDERAL_REGISTER_BASE}/documents.json",
                    params={
                        "conditions[agencies][]": agency_slug,
                        "conditions[publication_date][gte]": since,
                        "per_page": 20,
                        "order": "newest",
                        "fields[]": [
                            "title", "abstract", "document_number",
                            "html_url", "publication_date", "type",
                            "agencies", "action",
                        ],
                    },
                )
                if resp.status_code != 200:
                    print(f"Federal Register [{agency_label}]: HTTP {resp.status_code}")
                    continue

                results = resp.json().get("results", [])
                for result in results:
                    title = result.get("title", "")
                    abstract = result.get("abstract", "") or ""

                    # Filter for business relevance
                    combined = f"{title} {abstract}".lower()
                    if not any(kw in combined for kw in BUSINESS_KEYWORDS):
                        continue

                    neighborhood = detect_neighborhood(f"{title} {abstract}")

                    docs.append({
                        "id": f"fed-{result.get('document_number', '')}",
                        "source": SourceType.FEDERAL_REGISTER.value,
                        "title": title,
                        "content": abstract,
                        "url": result.get("html_url", ""),
                        "timestamp": result.get("publication_date", datetime.now(timezone.utc).isoformat()),
                        "metadata": {
                            "agency": agency_label,
                            "document_type": result.get("type", ""),
                            "action": result.get("action", ""),
                            "document_number": result.get("document_number", ""),
                            "pipeline": "federal_register",
                        },
                        "geo": {"neighborhood": neighborhood} if neighborhood else {},
                    })

                print(f"Federal Register [{agency_label}]: {len([d for d in docs if d.get('metadata', {}).get('agency') == agency_label])} relevant docs")

            except Exception as e:
                print(f"Federal Register [{agency_label}] error: {e}")

    return docs


async def _fetch_federal_register_fallback() -> list[dict]:
    """Fallback: broader search without agency filter."""
    docs = []
    since = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%d")

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.get(
                f"{FEDERAL_REGISTER_BASE}/documents.json",
                params={
                    "conditions[term]": "small business restaurant food safety",
                    "conditions[publication_date][gte]": since,
                    "per_page": 20,
                    "order": "relevance",
                    "fields[]": [
                        "title", "abstract", "document_number",
                        "html_url", "publication_date", "type",
                        "agencies", "action",
                    ],
                },
            )
            if resp.status_code == 200:
                for result in resp.json().get("results", []):
                    title = result.get("title", "")
                    abstract = result.get("abstract", "") or ""
                    agencies = result.get("agencies", [])
                    agency_names = [a.get("raw_name", "") for a in agencies] if agencies else []

                    docs.append({
                        "id": f"fed-{result.get('document_number', '')}",
                        "source": SourceType.FEDERAL_REGISTER.value,
                        "title": title,
                        "content": abstract,
                        "url": result.get("html_url", ""),
                        "timestamp": result.get("publication_date", datetime.now(timezone.utc).isoformat()),
                        "metadata": {
                            "agency": ", ".join(agency_names),
                            "document_type": result.get("type", ""),
                            "action": result.get("action", ""),
                            "document_number": result.get("document_number", ""),
                            "pipeline": "federal_register",
                        },
                        "geo": {},
                    })
        except Exception as e:
            print(f"Federal Register fallback error: {e}")

    return docs


@app.function(
    image=base_image,
    volumes={"/data": volume},
    timeout=300,
    retries=modal.Retries(max_retries=2, backoff_coefficient=2.0),
)
async def federal_register_ingester():
    """Ingest relevant federal regulations for small business impact analysis."""
    chain = FallbackChain("federal_register", "all_agencies", cache_ttl_hours=168)
    all_docs = await chain.execute([
        _fetch_federal_register,
        _fetch_federal_register_fallback,
    ])

    if not all_docs:
        print("Federal Register ingester: no relevant documents found")
        return 0

    # Dedup: skip already-seen documents
    seen = SeenSet("federal_register")
    new_docs = [d for d in all_docs if not seen.contains(d["id"], max_age_hours=24)]
    print(f"Federal Register: {len(all_docs)} fetched, {len(new_docs)} new (deduped {len(all_docs) - len(new_docs)})")

    if not new_docs:
        seen.save()
        await safe_volume_commit(volume, "federal_register")
        print("Federal Register ingester: no new documents")
        return 0

    # Save to volume
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = Path(RAW_DATA_PATH) / "federal_register" / date_str
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
    await safe_queue_push(doc_queue, new_docs, "federal_register")

    seen.save()
    await safe_volume_commit(volume, "federal_register")
    print(f"Federal Register ingester complete: {len(new_docs)} documents saved to {out_dir}")
    return len(new_docs)
