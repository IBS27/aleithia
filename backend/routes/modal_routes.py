"""
Routes that call deployed Modal functions.

Uses Modal's recommended pattern:
  1. modal.Function.from_name() to look up a deployed function
  2. .spawn() for async / .remote() for sync invocation
  3. FunctionCall.from_id() to poll results
"""

import os

import modal
from fastapi import APIRouter, HTTPException

router = APIRouter()

MODAL_APP_NAME = os.getenv("MODAL_APP_NAME", "hackillinois2026")


@router.post("/submit")
async def submit_job(payload: dict):
    """Submit a job to Modal and return a call ID for polling."""
    try:
        func = modal.Function.from_name(MODAL_APP_NAME, "hello")
        call = func.spawn(payload.get("name", "world"))
        return {"call_id": call.object_id}
    except modal.exception.NotFoundError:
        raise HTTPException(
            status_code=503,
            detail="Modal function not deployed. Run: modal deploy modal/app.py",
        )


@router.get("/result/{call_id}")
async def get_result(call_id: str):
    """Poll for the result of a previously submitted Modal job."""
    try:
        call = modal.functions.FunctionCall.from_id(call_id)
        result = call.get(timeout=0)
    except TimeoutError:
        return {"status": "processing"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "complete", "result": result}
