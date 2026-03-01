"""Shared OpenAI client factory with key availability check.

All Modal functions that use OpenAI should call these helpers
instead of creating ad-hoc clients.
"""
import os


def openai_available() -> bool:
    """Check if OPENAI_API_KEY is set in the environment."""
    return bool(os.environ.get("OPENAI_API_KEY"))


def get_openai_client():
    """Return an AsyncOpenAI client, or None if no API key."""
    if not openai_available():
        return None
    from openai import AsyncOpenAI
    return AsyncOpenAI()


def get_sync_openai_client():
    """Return a sync OpenAI client, or None if no API key."""
    if not openai_available():
        return None
    from openai import OpenAI
    return OpenAI()
