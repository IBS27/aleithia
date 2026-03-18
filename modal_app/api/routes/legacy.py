"""Legacy and compatibility Modal API routes."""
from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()

@router.post("/chat")
async def chat():
    return JSONResponse(
        {
            "error": "chat_endpoint_retired",
            "message": "The /chat endpoint was retired on 2026-03-03. Use /brief, /analyze, /social-trends, or /neighborhood endpoints instead.",
            "status": 410,
        },
        status_code=410,
    )


@router.get("/user/memories")
async def user_memories(user_id: str = ""):
    if not user_id:
        return JSONResponse({"error": "user_id is required"}, status_code=400)

    api_key = os.environ.get("SUPERMEMORY_API_KEY", "")
    if not api_key:
        return {"profile": {}, "memories": [], "memory_count": 0}

    try:
        from modal_app.supermemory import SupermemoryClient

        sm = SupermemoryClient(api_key)
        profile_data, memories = await asyncio.gather(
            sm.get_profile(user_id),
            sm.search("", container_tags=[f"user_{user_id}"], limit=20),
            return_exceptions=True,
        )
        if isinstance(profile_data, Exception):
            profile_data = {}
        if isinstance(memories, Exception):
            memories = []

        memory_items = [
            {"content": memory.get("content", "")[:300], "type": memory.get("metadata", {}).get("type", "unknown")}
            for memory in memories
            if isinstance(memory, dict)
        ]
        return {
            "profile": profile_data if isinstance(profile_data, dict) else {},
            "memories": memory_items,
            "memory_count": len(memory_items),
        }
    except Exception as exc:
        return {"profile": {}, "memories": [], "memory_count": 0, "error": str(exc)}
