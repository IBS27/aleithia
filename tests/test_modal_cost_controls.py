from __future__ import annotations

from types import SimpleNamespace

import modal

from modal_app.cost_controls import apply_modal_cost_controls, demos_enabled, schedules_enabled


class _FakeApp:
    def __init__(self):
        self.function_calls: list[dict] = []
        self.cls_calls: list[dict] = []

    def function(self, **kwargs):
        def decorator(fn):
            self.function_calls.append(kwargs)
            return fn

        return decorator

    def cls(self, **kwargs):
        def decorator(cls):
            self.cls_calls.append(kwargs)
            return cls

        return decorator


def test_cost_controls_default_to_no_schedule_and_fast_scaledown(monkeypatch):
    monkeypatch.delenv("ALETHIA_MODAL_CHEAP_MODE", raising=False)
    monkeypatch.delenv("ALETHIA_MODAL_ENABLE_SCHEDULES", raising=False)
    monkeypatch.delenv("ALETHIA_MODAL_ENABLE_RETRIES", raising=False)
    app = apply_modal_cost_controls(_FakeApp())
    image = SimpleNamespace()

    @app.function(
        image=image,
        schedule=modal.Period(minutes=5),
        timeout=120,
        retries=modal.Retries(max_retries=2),
    )
    def scheduled_job():
        return None

    assert len(app.function_calls) == 1
    options = app.function_calls[0]
    assert options["image"] is image
    assert options["schedule"] is None
    assert options["timeout"] == 120
    assert options["retries"] == 0
    assert options["max_containers"] == 1
    assert options["scaledown_window"] == 2


def test_cost_controls_cap_gpu_classes(monkeypatch):
    monkeypatch.setenv("ALETHIA_MODAL_CHEAP_MODE", "true")
    monkeypatch.setenv("ALETHIA_MODAL_GPU_MAX_CONTAINERS", "1")
    monkeypatch.setenv("ALETHIA_MODAL_GPU_SCALEDOWN_WINDOW_SECONDS", "2")
    app = apply_modal_cost_controls(_FakeApp())

    @app.cls(gpu="T4", image=SimpleNamespace(), scaledown_window=120, timeout=120)
    class Analyzer:
        pass

    assert app.cls_calls[0]["gpu"] == "T4"
    assert app.cls_calls[0]["max_containers"] == 1
    assert app.cls_calls[0]["scaledown_window"] == 2


def test_schedule_and_demo_flags_are_opt_in(monkeypatch):
    monkeypatch.delenv("ALETHIA_MODAL_CHEAP_MODE", raising=False)
    monkeypatch.delenv("ALETHIA_MODAL_ENABLE_SCHEDULES", raising=False)
    monkeypatch.delenv("ALETHIA_MODAL_ENABLE_DEMOS", raising=False)
    assert schedules_enabled("news_ingester") is False
    assert demos_enabled() is False

    monkeypatch.setenv("ALETHIA_MODAL_ENABLE_NEWS_INGESTER_SCHEDULE", "1")
    monkeypatch.setenv("ALETHIA_MODAL_ENABLE_DEMOS", "1")
    assert schedules_enabled("news_ingester") is True
    assert demos_enabled() is True
