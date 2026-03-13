"""Legacy and compatibility Modal API routes."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from modal_app.volume import PROCESSED_DATA_PATH, volume

router = APIRouter()

SETTINGS_PATH = Path(PROCESSED_DATA_PATH) / "user_settings.json"
DEFAULT_USER_ID = os.environ.get("ALEITHIA_DEFAULT_USER_ID", "local-user").strip() or "local-user"


class UserSettingsPayload(BaseModel):
    location_type: str = Field(..., min_length=1)
    neighborhood: str = Field(..., min_length=1)


def read_settings_store() -> dict:
    if SETTINGS_PATH.exists():
        try:
            return json.loads(SETTINGS_PATH.read_text())
        except Exception:
            pass
    return {}


def write_settings_store(store: dict) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(store, indent=2))
    volume.commit()


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


@router.get("/user/settings")
async def get_user_settings(x_user_id: str = Header(default="")):
    user_id = x_user_id.strip()
    if not user_id:
        return JSONResponse({"error": "Missing x-user-id header"}, status_code=401)
    store = read_settings_store()
    entry = store.get(user_id)
    if not entry:
        return JSONResponse({"error": "No settings found"}, status_code=404)
    return {"user_id": user_id, "location_type": entry.get("location_type", ""), "neighborhood": entry.get("neighborhood", "")}


@router.put("/user/settings")
async def put_user_settings(payload: UserSettingsPayload, x_user_id: str = Header(default="")):
    user_id = x_user_id.strip()
    if not user_id:
        return JSONResponse({"error": "Missing x-user-id header"}, status_code=401)
    store = read_settings_store()
    store[user_id] = {"location_type": payload.location_type, "neighborhood": payload.neighborhood}
    write_settings_store(store)
    return {"user_id": user_id, "location_type": payload.location_type, "neighborhood": payload.neighborhood}
