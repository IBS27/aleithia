"""Supermemory integration — RAG context, user profiles, and document sync.

Provides persistent memory layer for the Alethia intelligence engine.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
import modal

from modal_app.volume import app, volume, base_image, RAW_DATA_PATH, PROCESSED_DATA_PATH

SUPERMEMORY_BASE = "https://api.supermemory.ai/v3"


class SupermemoryClient:
    """Async httpx wrapper for Supermemory v3 API."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def add_memory(self, content: str, metadata: dict | None = None, container_tag: str = "chicago_data") -> dict:
        """Push a document to Supermemory with metadata and container tag."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{SUPERMEMORY_BASE}/memories",
                headers=self.headers,
                json={
                    "content": content[:10000],
                    "metadata": metadata or {},
                    "containerTags": [container_tag],
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def search(self, query: str, container_tags: list[str] | None = None, limit: int = 10) -> list[dict]:
        """Search Chicago data with optional container tag filters."""
        params: dict = {"q": query, "limit": limit}
        if container_tags:
            params["containerTags"] = ",".join(container_tags)

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{SUPERMEMORY_BASE}/memories/search",
                headers=self.headers,
                params=params,
            )
            resp.raise_for_status()
            return resp.json().get("results", [])

    async def get_user_profile(self, user_id: str) -> dict:
        """Fetch user profile from user-specific container."""
        results = await self.search(
            query="user profile preferences",
            container_tags=[f"user_{user_id}"],
            limit=5,
        )
        if results:
            return results[0].get("metadata", {})
        return {}

    async def store_conversation(self, user_id: str, messages: list[dict]) -> dict:
        """Store chat history for user context."""
        content = "\n".join(
            f"{m.get('role', 'user')}: {m.get('content', '')}"
            for m in messages[-10:]  # Last 10 messages
        )
        return await self.add_memory(
            content=content,
            metadata={"type": "conversation", "user_id": user_id, "message_count": len(messages)},
            container_tag=f"user_{user_id}",
        )

    async def sync_user_profile(self, user_id: str, business_type: str, neighborhood: str) -> dict:
        """Seed user profile during onboarding."""
        content = f"User {user_id} is exploring opening a {business_type} in {neighborhood}, Chicago. They need information about permits, zoning, competition, safety, and market conditions."
        return await self.add_memory(
            content=content,
            metadata={
                "type": "user_profile",
                "user_id": user_id,
                "business_type": business_type,
                "neighborhood": neighborhood,
            },
            container_tag=f"user_{user_id}",
        )


@app.function(
    image=base_image,
    volumes={"/data": volume},
    secrets=[modal.Secret.from_name("alethia-secrets")],
    timeout=600,
)
async def push_pipeline_data_to_supermemory():
    """Batch-sync processed data from Modal volume to Supermemory."""
    api_key = os.environ.get("SUPERMEMORY_API_KEY", "")
    if not api_key:
        print("SUPERMEMORY_API_KEY not set, skipping sync")
        return 0

    client = SupermemoryClient(api_key)
    synced = 0

    # Sync enriched documents (classified + sentiment-analyzed)
    enriched_dir = Path(PROCESSED_DATA_PATH) / "enriched"
    if enriched_dir.exists():
        for json_file in list(enriched_dir.rglob("*.json"))[:200]:
            try:
                doc = json.loads(json_file.read_text())
                content = f"{doc.get('title', '')}\n\n{doc.get('content', '')}"
                metadata = {
                    "source": doc.get("source", ""),
                    "neighborhood": doc.get("geo", {}).get("neighborhood", ""),
                    "classification": doc.get("classification", {}),
                    "sentiment": doc.get("sentiment", {}),
                    "timestamp": doc.get("timestamp", ""),
                    "doc_id": doc.get("id", ""),
                }
                await client.add_memory(content, metadata, container_tag="chicago_data")
                synced += 1
            except Exception as e:
                print(f"Supermemory sync error for {json_file.name}: {e}")

    # Sync raw data from each pipeline source
    for source in ["news", "politics", "public_data", "demographics"]:
        raw_dir = Path(RAW_DATA_PATH) / source
        if not raw_dir.exists():
            continue

        json_files = sorted(raw_dir.rglob("*.json"), reverse=True)[:50]
        for json_file in json_files:
            try:
                doc = json.loads(json_file.read_text())
                content = f"{doc.get('title', '')}\n\n{doc.get('content', '')}"
                metadata = {
                    "source": source,
                    "neighborhood": doc.get("geo", {}).get("neighborhood", ""),
                    "timestamp": doc.get("timestamp", ""),
                    "doc_id": doc.get("id", ""),
                }
                await client.add_memory(content, metadata, container_tag=f"chicago_{source}")
                synced += 1
            except Exception as e:
                print(f"Supermemory raw sync error for {json_file.name}: {e}")

    print(f"Supermemory sync complete: {synced} documents pushed")
    return synced
