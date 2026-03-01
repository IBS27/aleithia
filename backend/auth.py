"""Clerk authentication utilities."""

import os
from typing import Optional
import jwt
from fastapi import HTTPException, Header

CLERK_PUB_KEY = os.getenv("CLERK_SECRET_KEY", "").strip()


def verify_clerk_token(authorization: Optional[str]) -> str:
    """
    Verify Clerk JWT token and extract user ID.
    
    Token format: "Bearer <jwt_token>"
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0] != "Bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization header format")
    token = parts[1]
    
    try:
        # Decode without verification if no secret (development mode)
        # In production, verify with CLERK_SECRET_KEY
        if CLERK_PUB_KEY:
            payload = jwt.decode(token, CLERK_PUB_KEY, algorithms=["HS256"])
        else:
            # Development: decode without verification
            payload = jwt.decode(token, options={"verify_signature": False})
        
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: missing sub claim")
        return user_id
    except jwt.DecodeError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Auth error: {str(e)}")


def extract_user_id(authorization: Optional[str] = Header(default=None)) -> str:
    """FastAPI dependency to extract and verify user ID from Clerk token."""
    return verify_clerk_token(authorization)
