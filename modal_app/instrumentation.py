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

        # Auto-instrument OpenAI (GPT-4V calls in vision pipeline)
        try:
            from openinference.instrumentation.openai import OpenAIInstrumentor
            OpenAIInstrumentor().instrument(tracer_provider=_tracer_provider)
        except ImportError:
            pass  # openinference-instrumentation-openai not installed in this image

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


def inject_context() -> dict:
    """Serialize current trace context into a dict for cross-process propagation.

    Call this inside an active span to capture traceparent/tracestate,
    then pass the returned dict to a remote Modal function.
    """
    try:
        from opentelemetry.propagate import inject

        carrier: dict[str, str] = {}
        inject(carrier)
        return carrier
    except Exception:
        return {}


def extract_context(carrier: dict | None):
    """Deserialize a trace context dict into an OTel Context object.

    Use the returned context when starting a span to make it a child
    of the remote parent:
        ctx = extract_context(trace_context)
        with tracer.start_as_current_span("name", context=ctx): ...
    """
    if not carrier:
        return None
    try:
        from opentelemetry.propagate import extract

        return extract(carrier)
    except Exception:
        return None
