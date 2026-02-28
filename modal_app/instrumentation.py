"""Centralized Arize AX tracing setup for all Modal functions.

Provides init_tracing() to configure the Arize OTLP exporter and
get_tracer() to obtain a tracer for manual span creation.
Call init_tracing() once per container before creating LLM clients.
"""
import logging
import os

logger = logging.getLogger(__name__)

_tracer_provider = None
_initialized = False


def init_tracing():
    """Initialize Arize AX tracing. Idempotent — safe to call multiple times.

    Reads ARIZE_SPACE_ID and ARIZE_API_KEY from environment.
    Returns the TracerProvider, or None if credentials are missing.
    """
    global _tracer_provider, _initialized
    if _initialized:
        return _tracer_provider
    _initialized = True

    space_id = os.environ.get("ARIZE_SPACE_ID")
    api_key = os.environ.get("ARIZE_API_KEY")

    if not space_id or not api_key:
        logger.warning("ARIZE_SPACE_ID or ARIZE_API_KEY not set — tracing disabled")
        return None

    try:
        from arize.otel import register

        _tracer_provider = register(
            space_id=space_id,
            api_key=api_key,
            project_name="alethia",
        )
        logger.info("Arize AX tracing initialized for project 'alethia'")
        return _tracer_provider
    except Exception as e:
        logger.warning(f"Failed to initialize Arize tracing: {e}")
        return None


def get_tracer(name: str):
    """Get an OpenTelemetry tracer for manual span creation.

    Returns a real tracer if tracing is initialized, otherwise a no-op tracer.
    """
    if _tracer_provider is not None:
        return _tracer_provider.get_tracer(name)
    try:
        from opentelemetry.trace import get_tracer as _get_tracer
        return _get_tracer(name)
    except ImportError:
        return None
