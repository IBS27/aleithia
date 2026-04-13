"""Shared Modal runtime helpers and queue constants."""
from __future__ import annotations

import os

import modal

from modal_app.volume import app

MODAL_APP_NAME = app.name
RAW_DOC_QUEUE_NAME = "new-docs"
IMPACT_QUEUE_NAME = "impact-docs"


def env_flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


ENABLE_CCTV_ANALYSIS = env_flag("ENABLE_CCTV_ANALYSIS", default=True)


def get_modal_function(name: str) -> modal.Function:
    """Resolve a deployed Modal function from the current app."""
    return modal.Function.from_name(MODAL_APP_NAME, name)


def get_modal_cls(name: str) -> modal.Cls:
    """Resolve a deployed Modal class from the current app."""
    return modal.Cls.from_name(MODAL_APP_NAME, name)


def get_raw_doc_queue() -> modal.Queue:
    """Shared queue for raw docs headed to the classifier."""
    return modal.Queue.from_name(RAW_DOC_QUEUE_NAME, create_if_missing=True)


def get_impact_queue() -> modal.Queue:
    """Shared queue for high-impact documents headed to Lead Analyst."""
    return modal.Queue.from_name(IMPACT_QUEUE_NAME, create_if_missing=True)
