"""User context helpers for local, unauthenticated mode."""

import os
from typing import Optional
from fastapi import Request

DEFAULT_USER_ID = os.getenv("ALEITHIA_DEFAULT_USER_ID", "local-user").strip() or "local-user"


def resolve_user_id(request: Optional[Request] = None) -> str:
    """Return the local user id, allowing an optional explicit override header."""
    if request is None:
        return DEFAULT_USER_ID

    header_user_id = request.headers.get("x-user-id", "").strip()
    return header_user_id or DEFAULT_USER_ID


def extract_user_id(request: Request) -> str:
    """FastAPI dependency used by profile/history routes in local mode."""
    return resolve_user_id(request)
