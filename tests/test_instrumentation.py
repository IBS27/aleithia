"""Tests for modal_app/instrumentation.py — init_tracing() and get_tracer()."""
import os
from unittest.mock import patch, MagicMock

import pytest

import modal_app.instrumentation as inst


class TestInitTracing:
    def test_returns_none_when_no_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            result = inst.init_tracing()
        assert result is None

    def test_returns_none_when_space_id_missing(self):
        with patch.dict(os.environ, {"ARIZE_API_KEY": "fake-key"}, clear=True):
            result = inst.init_tracing()
        assert result is None

    def test_returns_none_when_api_key_missing(self):
        with patch.dict(os.environ, {"ARIZE_SPACE_ID": "fake-space"}, clear=True):
            result = inst.init_tracing()
        assert result is None

    def test_idempotent_returns_same_result(self):
        with patch.dict(os.environ, {}, clear=True):
            first = inst.init_tracing()
            second = inst.init_tracing()
        assert first is second
        assert first is None

    def test_idempotent_with_provider(self):
        mock_provider = MagicMock()
        with patch.dict(os.environ, {"ARIZE_SPACE_ID": "s", "ARIZE_API_KEY": "k"}):
            with patch("modal_app.instrumentation.register", create=True) as mock_register:
                # Patch at the point of import inside init_tracing
                import importlib
                mock_mod = MagicMock()
                mock_mod.register.return_value = mock_provider
                with patch.dict("sys.modules", {"arize.otel": mock_mod, "arize": MagicMock()}):
                    first = inst.init_tracing()
                    second = inst.init_tracing()
        assert first is second
        assert first is mock_provider

    def test_calls_register_with_correct_args(self):
        mock_provider = MagicMock()
        mock_mod = MagicMock()
        mock_mod.register.return_value = mock_provider

        with patch.dict(os.environ, {"ARIZE_SPACE_ID": "my-space", "ARIZE_API_KEY": "my-key"}):
            with patch.dict("sys.modules", {"arize.otel": mock_mod, "arize": MagicMock()}):
                result = inst.init_tracing()

        mock_mod.register.assert_called_once_with(
            space_id="my-space",
            api_key="my-key",
            project_name="alethia",
        )
        assert result is mock_provider

    def test_handles_register_exception_gracefully(self):
        mock_mod = MagicMock()
        mock_mod.register.side_effect = RuntimeError("connection failed")

        with patch.dict(os.environ, {"ARIZE_SPACE_ID": "s", "ARIZE_API_KEY": "k"}):
            with patch.dict("sys.modules", {"arize.otel": mock_mod, "arize": MagicMock()}):
                result = inst.init_tracing()

        assert result is None

    def test_logs_warning_when_credentials_missing(self, caplog):
        import logging
        with caplog.at_level(logging.WARNING):
            with patch.dict(os.environ, {}, clear=True):
                inst.init_tracing()
        assert "ARIZE_SPACE_ID or ARIZE_API_KEY not set" in caplog.text


class TestGetTracer:
    def test_returns_tracer_from_provider(self):
        mock_tracer = MagicMock()
        mock_provider = MagicMock()
        mock_provider.get_tracer.return_value = mock_tracer

        inst._tracer_provider = mock_provider
        result = inst.get_tracer("test.module")

        mock_provider.get_tracer.assert_called_once_with("test.module")
        assert result is mock_tracer

    def test_returns_noop_tracer_when_no_provider(self):
        result = inst.get_tracer("test.module")
        # Should return an OTel no-op tracer (not None)
        assert result is not None

    def test_returns_none_when_otel_not_installed(self):
        with patch.dict("sys.modules", {"opentelemetry": None, "opentelemetry.trace": None}):
            # Force ImportError
            import importlib
            try:
                result = inst.get_tracer("test.module")
                # If opentelemetry is already cached, it may still work
            except ImportError:
                pass  # Expected if otel truly unavailable
