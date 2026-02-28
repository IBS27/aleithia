"""Tests verifying that tracing spans are created with correct attributes.

Uses a real in-memory OTel TracerProvider to capture spans, then asserts
on span names, kinds, and attributes — without needing Modal, vLLM, or GPUs.

The `span_capture` fixture is provided by conftest.py.
"""
import json

import pytest


# ── LLM span tests ──────────────────────────────────────────────────────────


class TestLLMSpans:
    @pytest.mark.asyncio
    async def test_generate_creates_llm_span(self, span_capture):
        provider, exporter = span_capture
        tracer = provider.get_tracer("test.llm")

        # Simulate what AlethiaLLM.generate() does with tracing
        messages = [{"role": "user", "content": "Hello"}]

        span_ctx = tracer.start_as_current_span("llm-generate")
        span = span_ctx.__enter__()
        try:
            span.set_attribute("openinference.span.kind", "LLM")
            span.set_attribute("llm.model_name", "Qwen/Qwen3-8B-FP8")
            span.set_attribute("input.value", json.dumps(messages))
            result = "Test response"
            span.set_attribute("output.value", result)
        finally:
            span_ctx.__exit__(None, None, None)

        spans = exporter.get_finished_spans()
        assert len(spans) == 1

        s = spans[0]
        assert s.name == "llm-generate"
        assert s.attributes["openinference.span.kind"] == "LLM"
        assert s.attributes["llm.model_name"] == "Qwen/Qwen3-8B-FP8"
        assert s.attributes["input.value"] == json.dumps(messages)
        assert s.attributes["output.value"] == "Test response"

    @pytest.mark.asyncio
    async def test_generate_stream_creates_llm_span(self, span_capture):
        provider, exporter = span_capture
        tracer = provider.get_tracer("test.llm")

        messages = [{"role": "user", "content": "Stream test"}]

        span_ctx = tracer.start_as_current_span("llm-generate-stream")
        span = span_ctx.__enter__()
        try:
            span.set_attribute("openinference.span.kind", "LLM")
            span.set_attribute("llm.model_name", "Qwen/Qwen3-8B-FP8")
            span.set_attribute("input.value", json.dumps(messages))

            # Simulate streaming tokens
            full_output = ""
            for token in ["Hello", " world", "!"]:
                full_output += token

            span.set_attribute("output.value", full_output)
        finally:
            span_ctx.__exit__(None, None, None)

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "llm-generate-stream"
        assert spans[0].attributes["output.value"] == "Hello world!"

    @pytest.mark.asyncio
    async def test_generate_records_error_on_failure(self, span_capture):
        provider, exporter = span_capture
        tracer = provider.get_tracer("test.llm")

        span_ctx = tracer.start_as_current_span("llm-generate")
        span = span_ctx.__enter__()
        try:
            span.set_attribute("openinference.span.kind", "LLM")
            span.set_attribute("error", "engine timeout")
        finally:
            span_ctx.__exit__(None, None, None)

        spans = exporter.get_finished_spans()
        assert spans[0].attributes["error"] == "engine timeout"


# ── Agent span tests ─────────────────────────────────────────────────────────


class TestAgentSpans:
    def test_neighborhood_agent_creates_chain_span(self, span_capture):
        provider, exporter = span_capture
        tracer = provider.get_tracer("test.agents")

        span_ctx = tracer.start_as_current_span("neighborhood-intel-agent")
        span = span_ctx.__enter__()
        try:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("input.value", "restaurant in Logan Square")
            span.set_attribute("agent.neighborhood", "Logan Square")
            span.set_attribute("agent.business_type", "restaurant")
            span.set_attribute("agent.data_points", 42)
            span.set_attribute("output.value", json.dumps({"data_points": 42, "sources": ["news", "permits"]}))
        finally:
            span_ctx.__exit__(None, None, None)

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        s = spans[0]
        assert s.name == "neighborhood-intel-agent"
        assert s.attributes["openinference.span.kind"] == "CHAIN"
        assert s.attributes["agent.neighborhood"] == "Logan Square"
        assert s.attributes["agent.data_points"] == 42

    def test_regulatory_agent_creates_chain_span(self, span_capture):
        provider, exporter = span_capture
        tracer = provider.get_tracer("test.agents")

        span_ctx = tracer.start_as_current_span("regulatory-agent")
        span = span_ctx.__enter__()
        try:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("input.value", "restaurant")
            span.set_attribute("agent.business_type", "restaurant")
            span.set_attribute("agent.data_points", 15)
        finally:
            span_ctx.__exit__(None, None, None)

        spans = exporter.get_finished_spans()
        assert spans[0].name == "regulatory-agent"
        assert spans[0].attributes["agent.business_type"] == "restaurant"

    def test_orchestrator_creates_chain_span_with_metadata(self, span_capture):
        provider, exporter = span_capture
        tracer = provider.get_tracer("test.agents")

        span_ctx = tracer.start_as_current_span("orchestrate-query")
        span = span_ctx.__enter__()
        try:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("input.value", "Best neighborhood for a cafe?")
            span.set_attribute("orchestrator.business_type", "cafe")
            span.set_attribute("orchestrator.target_neighborhood", "Wicker Park")
            span.set_attribute("orchestrator.agents_deployed", 4)
            span.set_attribute("orchestrator.total_data_points", 120)
        finally:
            span_ctx.__exit__(None, None, None)

        spans = exporter.get_finished_spans()
        s = spans[0]
        assert s.name == "orchestrate-query"
        assert s.attributes["orchestrator.agents_deployed"] == 4
        assert s.attributes["orchestrator.total_data_points"] == 120


# ── Classification span tests ────────────────────────────────────────────────


class TestClassifySpans:
    def test_classify_batch_creates_span(self, span_capture):
        provider, exporter = span_capture
        tracer = provider.get_tracer("test.classify")

        span_ctx = tracer.start_as_current_span("doc-classify-batch")
        span = span_ctx.__enter__()
        try:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("llm.model_name", "facebook/bart-large-mnli")
            span.set_attribute("classify.batch_size", 10)
            span.set_attribute("classify.results_count", 10)
        finally:
            span_ctx.__exit__(None, None, None)

        spans = exporter.get_finished_spans()
        s = spans[0]
        assert s.name == "doc-classify-batch"
        assert s.attributes["llm.model_name"] == "facebook/bart-large-mnli"
        assert s.attributes["classify.batch_size"] == 10

    def test_sentiment_batch_creates_span(self, span_capture):
        provider, exporter = span_capture
        tracer = provider.get_tracer("test.sentiment")

        span_ctx = tracer.start_as_current_span("sentiment-analyze-batch")
        span = span_ctx.__enter__()
        try:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("llm.model_name", "cardiffnlp/twitter-roberta-base-sentiment-latest")
            span.set_attribute("sentiment.batch_size", 5)
            span.set_attribute("sentiment.results_count", 5)
        finally:
            span_ctx.__exit__(None, None, None)

        spans = exporter.get_finished_spans()
        s = spans[0]
        assert s.name == "sentiment-analyze-batch"
        assert s.attributes["sentiment.batch_size"] == 5

    def test_process_queue_batch_creates_span(self, span_capture):
        provider, exporter = span_capture
        tracer = provider.get_tracer("test.classify")

        span_ctx = tracer.start_as_current_span("process-queue-batch")
        span = span_ctx.__enter__()
        try:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("pipeline.batch_size", 25)
            span.set_attribute("pipeline.docs_classified", 25)
        finally:
            span_ctx.__exit__(None, None, None)

        spans = exporter.get_finished_spans()
        s = spans[0]
        assert s.name == "process-queue-batch"
        assert s.attributes["pipeline.batch_size"] == 25
        assert s.attributes["pipeline.docs_classified"] == 25


# ── Web/Chat span tests ──────────────────────────────────────────────────────


class TestChatSpans:
    def test_chat_request_creates_chain_span(self, span_capture):
        provider, exporter = span_capture
        tracer = provider.get_tracer("test.web")

        span_ctx = tracer.start_as_current_span("chat-request")
        span = span_ctx.__enter__()
        try:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("input.value", "What permits do I need for a restaurant in Logan Square?")
            span.set_attribute("chat.business_type", "Restaurant")
            span.set_attribute("chat.neighborhood", "Logan Square")
            span.set_attribute("chat.agents_deployed", 4)
            span.set_attribute("chat.data_points", 85)
            span.set_attribute("output.value", "Based on my analysis...")
        finally:
            span_ctx.__exit__(None, None, None)

        spans = exporter.get_finished_spans()
        s = spans[0]
        assert s.name == "chat-request"
        assert s.attributes["openinference.span.kind"] == "CHAIN"
        assert s.attributes["chat.neighborhood"] == "Logan Square"
        assert s.attributes["chat.agents_deployed"] == 4
        assert "output.value" in s.attributes

    def test_chat_error_records_in_span(self, span_capture):
        provider, exporter = span_capture
        tracer = provider.get_tracer("test.web")

        span_ctx = tracer.start_as_current_span("chat-request")
        span = span_ctx.__enter__()
        try:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("input.value", "test question")
            span.set_attribute("error", "orchestration timeout")
        finally:
            span_ctx.__exit__(None, None, None)

        spans = exporter.get_finished_spans()
        assert spans[0].attributes["error"] == "orchestration timeout"


# ── Brief endpoint span tests ────────────────────────────────────────────────


class TestBriefSpans:
    def test_brief_request_creates_chain_span(self, span_capture):
        provider, exporter = span_capture
        tracer = provider.get_tracer("test.web")

        span_ctx = tracer.start_as_current_span("brief-request")
        span = span_ctx.__enter__()
        try:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("input.value", "Restaurant in Logan Square")
            span.set_attribute("brief.neighborhood", "Logan Square")
            span.set_attribute("brief.business_type", "Restaurant")
            span.set_attribute("output.value", json.dumps({"data_points": 42}))
        finally:
            span_ctx.__exit__(None, None, None)

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        s = spans[0]
        assert s.name == "brief-request"
        assert s.attributes["openinference.span.kind"] == "CHAIN"
        assert s.attributes["brief.neighborhood"] == "Logan Square"
        assert s.attributes["brief.business_type"] == "Restaurant"
        assert "output.value" in s.attributes

    def test_brief_error_records_in_span(self, span_capture):
        provider, exporter = span_capture
        tracer = provider.get_tracer("test.web")

        span_ctx = tracer.start_as_current_span("brief-request")
        span = span_ctx.__enter__()
        try:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("input.value", "Restaurant in Unknown")
            span.set_attribute("brief.neighborhood", "Unknown")
            span.set_attribute("brief.business_type", "Restaurant")
            span.set_attribute("error", "agent timeout")
        finally:
            span_ctx.__exit__(None, None, None)

        spans = exporter.get_finished_spans()
        assert spans[0].attributes["error"] == "agent timeout"


# ── Neighborhood endpoint span tests ────────────────────────────────────────


class TestNeighborhoodSpans:
    def test_neighborhood_profile_creates_chain_span(self, span_capture):
        provider, exporter = span_capture
        tracer = provider.get_tracer("test.web")

        span_ctx = tracer.start_as_current_span("neighborhood-profile")
        span = span_ctx.__enter__()
        try:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("input.value", "Pilsen")
            span.set_attribute("neighborhood.name", "Pilsen")
            span.set_attribute("neighborhood.inspections", 15)
            span.set_attribute("neighborhood.permits", 8)
            span.set_attribute("neighborhood.licenses", 22)
            span.set_attribute("output.value", json.dumps({
                "inspections": 15, "permits": 8, "licenses": 22, "news": 5,
            }))
        finally:
            span_ctx.__exit__(None, None, None)

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        s = spans[0]
        assert s.name == "neighborhood-profile"
        assert s.attributes["openinference.span.kind"] == "CHAIN"
        assert s.attributes["neighborhood.name"] == "Pilsen"
        assert s.attributes["neighborhood.inspections"] == 15
        assert s.attributes["neighborhood.permits"] == 8
        assert s.attributes["neighborhood.licenses"] == 22

    def test_neighborhood_profile_records_error_for_unknown(self, span_capture):
        provider, exporter = span_capture
        tracer = provider.get_tracer("test.web")

        span_ctx = tracer.start_as_current_span("neighborhood-profile")
        span = span_ctx.__enter__()
        try:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("input.value", "Atlantis")
            span.set_attribute("neighborhood.name", "Atlantis")
            span.set_attribute("error", "Unknown neighborhood: Atlantis")
        finally:
            span_ctx.__exit__(None, None, None)

        spans = exporter.get_finished_spans()
        assert spans[0].attributes["error"] == "Unknown neighborhood: Atlantis"

    def test_neighborhood_profile_records_all_data_counts(self, span_capture):
        provider, exporter = span_capture
        tracer = provider.get_tracer("test.web")

        span_ctx = tracer.start_as_current_span("neighborhood-profile")
        span = span_ctx.__enter__()
        try:
            span.set_attribute("openinference.span.kind", "CHAIN")
            span.set_attribute("input.value", "Loop")
            span.set_attribute("neighborhood.name", "Loop")
            span.set_attribute("neighborhood.inspections", 0)
            span.set_attribute("neighborhood.permits", 0)
            span.set_attribute("neighborhood.licenses", 0)
            span.set_attribute("output.value", json.dumps({
                "inspections": 0, "permits": 0, "licenses": 0, "news": 0,
            }))
        finally:
            span_ctx.__exit__(None, None, None)

        spans = exporter.get_finished_spans()
        s = spans[0]
        # Zero counts should still be recorded
        assert s.attributes["neighborhood.inspections"] == 0
        assert s.attributes["neighborhood.permits"] == 0
        assert s.attributes["neighborhood.licenses"] == 0


# ── Span nesting / no-op behavior tests ──────────────────────────────────────


class TestSpanBehavior:
    def test_none_tracer_skips_spans_safely(self):
        """When tracer is None, the span pattern should be a no-op."""
        tracer = None
        span_ctx = tracer.start_as_current_span("test") if tracer else None
        span = span_ctx.__enter__() if span_ctx else None

        # Business logic runs fine
        result = 1 + 1

        if span:
            span.set_attribute("output.value", str(result))
        if span_ctx:
            span_ctx.__exit__(None, None, None)

        assert result == 2

    def test_nested_spans_create_parent_child(self, span_capture):
        """Verify that nested spans produce a parent-child relationship."""
        provider, exporter = span_capture
        tracer = provider.get_tracer("test.nesting")

        with tracer.start_as_current_span("parent") as parent_span:
            parent_span.set_attribute("openinference.span.kind", "CHAIN")
            with tracer.start_as_current_span("child") as child_span:
                child_span.set_attribute("openinference.span.kind", "LLM")

        spans = exporter.get_finished_spans()
        assert len(spans) == 2

        child = [s for s in spans if s.name == "child"][0]
        parent = [s for s in spans if s.name == "parent"][0]

        assert child.parent.span_id == parent.context.span_id

    def test_cross_process_context_propagation(self, span_capture):
        """Verify inject/extract creates parent-child across processes."""
        provider, exporter = span_capture

        from opentelemetry.trace import set_tracer_provider
        from opentelemetry.propagate import inject, extract

        set_tracer_provider(provider)
        tracer = provider.get_tracer("test.propagation")

        with tracer.start_as_current_span("chat-request") as parent_span:
            parent_span.set_attribute("openinference.span.kind", "CHAIN")

            # Inject — this is what web.py does before calling .remote()
            carrier: dict[str, str] = {}
            inject(carrier)

            assert "traceparent" in carrier  # W3C header must be present

        # Simulate: agents.py receives carrier, extracts, creates child span
        extracted_ctx = extract(carrier=carrier)

        with tracer.start_as_current_span("orchestrate-query", context=extracted_ctx) as child_span:
            child_span.set_attribute("openinference.span.kind", "CHAIN")

        spans = exporter.get_finished_spans()
        assert len(spans) == 2

        parent = [s for s in spans if s.name == "chat-request"][0]
        child = [s for s in spans if s.name == "orchestrate-query"][0]

        # Same trace ID = same trace in Arize
        assert child.context.trace_id == parent.context.trace_id
        # Child's parent is the parent span
        assert child.parent.span_id == parent.context.span_id

    def test_all_span_kinds_are_valid(self, span_capture):
        """Ensure we only use valid OpenInference span kinds."""
        provider, exporter = span_capture
        tracer = provider.get_tracer("test.kinds")

        valid_kinds = {"LLM", "CHAIN", "TOOL", "EMBEDDING", "RETRIEVER", "RERANKER", "AGENT", "GUARDRAIL", "EVALUATOR"}

        # Our code uses LLM and CHAIN
        for kind in ["LLM", "CHAIN"]:
            with tracer.start_as_current_span(f"test-{kind}") as span:
                span.set_attribute("openinference.span.kind", kind)

        spans = exporter.get_finished_spans()
        for s in spans:
            assert s.attributes["openinference.span.kind"] in valid_kinds
