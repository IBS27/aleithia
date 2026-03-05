"""Shared OpenAI client factory with key availability check.

All Modal functions that use OpenAI should call these helpers
instead of creating ad-hoc clients.
"""
import os

DEFAULT_SOCIAL_TRENDS_MODEL = "gpt-5"
DEFAULT_VISION_ASSESS_MODEL = "gpt-5-mini"


def openai_available() -> bool:
    """Check if OPENAI_API_KEY is set in the environment."""
    return bool(os.environ.get("OPENAI_API_KEY"))


def get_social_trends_model() -> str:
    """Resolve model for social trends synthesis."""
    return os.environ.get("OPENAI_MODEL_SOCIAL_TRENDS", DEFAULT_SOCIAL_TRENDS_MODEL)


def get_vision_assess_model() -> str:
    """Resolve model for vision assessment."""
    return os.environ.get("OPENAI_MODEL_VISION_ASSESS", DEFAULT_VISION_ASSESS_MODEL)


def is_gpt5_family_model(model_name: str) -> bool:
    """GPT-5 family models are reasoning models that reject temperature and need higher token budgets."""
    return (model_name or "").strip().lower().startswith("gpt-5")


def build_chat_kwargs(
    model: str,
    messages: list[dict],
    *,
    max_completion_tokens: int = 512,
    gpt5_max_completion_tokens: int = 2048,
    temperature: float = 0.4,
    response_format: dict | None = None,
    reasoning_effort: str = "low",
    extra: dict | None = None,
) -> dict:
    """Build model-family-aware kwargs for chat completions.

    For GPT-5 family models:
      - Uses ``gpt5_max_completion_tokens`` (default 2048) to give reasoning headroom
      - Adds ``reasoning_effort`` (default "low") for extraction tasks
      - Omits ``temperature`` (unsupported by reasoning models)

    For other models:
      - Uses ``max_completion_tokens`` and ``temperature`` as-is
    """
    kwargs: dict = {
        "model": model,
        "messages": messages,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format

    if is_gpt5_family_model(model):
        kwargs["max_completion_tokens"] = gpt5_max_completion_tokens
        kwargs["reasoning_effort"] = reasoning_effort
    else:
        kwargs["max_completion_tokens"] = max_completion_tokens
        kwargs["temperature"] = temperature

    if extra:
        kwargs.update(extra)
    return kwargs


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
