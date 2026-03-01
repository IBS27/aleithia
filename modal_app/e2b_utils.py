"""Shared E2B sandbox factory with key availability check.

All Modal functions that use E2B sandboxes should call these helpers
instead of creating ad-hoc clients.
"""
import os


def e2b_available() -> bool:
    """Check if E2B_API_KEY is set in the environment."""
    return bool(os.environ.get("E2B_API_KEY"))


async def create_sandbox(timeout: int = 120):
    """Return an E2B AsyncSandbox, or None if no API key."""
    if not e2b_available():
        return None
    from e2b_code_interpreter import AsyncSandbox
    return await AsyncSandbox.create(template="base", timeout=timeout)
