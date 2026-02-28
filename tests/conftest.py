"""Shared fixtures for Arize tracing tests."""
import sys
from types import ModuleType
from typing import Sequence
from unittest.mock import MagicMock

import pytest

from opentelemetry.sdk.trace import TracerProvider, ReadableSpan
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult


class InMemorySpanExporter(SpanExporter):
    """Minimal in-memory span exporter for test assertions."""

    def __init__(self):
        self._spans: list[ReadableSpan] = []

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        self._spans.extend(spans)
        return SpanExportResult.SUCCESS

    def get_finished_spans(self) -> list[ReadableSpan]:
        return list(self._spans)

    def clear(self):
        self._spans.clear()

    def shutdown(self):
        self.clear()


@pytest.fixture(autouse=True)
def _reset_instrumentation():
    """Reset instrumentation module state between tests."""
    import modal_app.instrumentation as inst
    inst._tracer_provider = None
    inst._initialized = False
    yield
    inst._tracer_provider = None
    inst._initialized = False


@pytest.fixture()
def span_capture():
    """Provide a TracerProvider + exporter that captures spans in memory."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter
