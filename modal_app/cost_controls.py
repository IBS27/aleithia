"""Deploy-time Modal cost controls.

These defaults keep the app callable while making accidental Modal spend hard:
scheduled jobs and demo fan-out are opt-in, containers scale down quickly, and
cheap mode caps fan-out to one container per function/class.
"""
from __future__ import annotations

import functools
import os
from collections.abc import Callable
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}

DEFAULT_CHEAP_MODE = True
DEFAULT_MAX_CONTAINERS = 1
DEFAULT_SCALEDOWN_WINDOW_SECONDS = 2


def env_flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    if raw in _TRUE_VALUES:
        return True
    if raw in _FALSE_VALUES:
        return False
    return default


def _env_int(name: str, default: int, minimum: int | None = None) -> int:
    raw = (os.environ.get(name) or "").strip()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        return max(minimum, value)
    return value


def cheap_mode_enabled() -> bool:
    return env_flag("ALETHIA_MODAL_CHEAP_MODE", default=DEFAULT_CHEAP_MODE)


def schedules_enabled(function_name: str | None = None) -> bool:
    default_enabled = not cheap_mode_enabled()
    if function_name:
        env_key = f"ALETHIA_MODAL_ENABLE_{function_name.upper()}_SCHEDULE"
        if (os.environ.get(env_key) or "").strip():
            return env_flag(env_key, default=default_enabled)
    return env_flag("ALETHIA_MODAL_ENABLE_SCHEDULES", default=default_enabled)


def retries_enabled() -> bool:
    return env_flag("ALETHIA_MODAL_ENABLE_RETRIES", default=not cheap_mode_enabled())


def demos_enabled() -> bool:
    return env_flag("ALETHIA_MODAL_ENABLE_DEMOS", default=False)


def _cost_controlled_options(kind: str, name: str | None, kwargs: dict[str, Any]) -> dict[str, Any]:
    options = dict(kwargs)

    if kind == "function" and options.get("schedule") is not None and not schedules_enabled(name):
        options["schedule"] = None

    if not retries_enabled() and options.get("retries") is not None:
        options["retries"] = 0

    if not cheap_mode_enabled():
        return options

    max_containers_key = (
        "ALETHIA_MODAL_GPU_MAX_CONTAINERS"
        if options.get("gpu") is not None
        else "ALETHIA_MODAL_MAX_CONTAINERS"
    )
    scaledown_key = (
        "ALETHIA_MODAL_GPU_SCALEDOWN_WINDOW_SECONDS"
        if options.get("gpu") is not None
        else "ALETHIA_MODAL_SCALEDOWN_WINDOW_SECONDS"
    )

    max_containers = _env_int(max_containers_key, DEFAULT_MAX_CONTAINERS, minimum=1)
    current_max = options.get("max_containers")
    if current_max is None or current_max > max_containers:
        options["max_containers"] = max_containers

    scaledown_window = _env_int(
        scaledown_key,
        DEFAULT_SCALEDOWN_WINDOW_SECONDS,
        minimum=DEFAULT_SCALEDOWN_WINDOW_SECONDS,
    )
    current_scaledown = options.get("scaledown_window")
    if current_scaledown is None or current_scaledown > scaledown_window:
        options["scaledown_window"] = scaledown_window

    return options


def apply_modal_cost_controls(app: Any) -> Any:
    """Wrap ``app.function`` and ``app.cls`` with Aleithia cheap defaults."""
    if getattr(app, "_alethia_cost_controls_applied", False):
        return app

    original_function = app.function
    original_cls = app.cls

    @functools.wraps(original_function)
    def cost_controlled_function(*args: Any, **kwargs: Any):
        def decorate(target: F) -> F:
            name = getattr(target, "__name__", None)
            options = _cost_controlled_options("function", name, kwargs)
            return original_function(*args, **options)(target)

        return decorate

    @functools.wraps(original_cls)
    def cost_controlled_cls(*args: Any, **kwargs: Any):
        def decorate(target: F) -> F:
            name = getattr(target, "__name__", None)
            options = _cost_controlled_options("cls", name, kwargs)
            return original_cls(*args, **options)(target)

        return decorate

    app.function = cost_controlled_function
    app.cls = cost_controlled_cls
    setattr(app, "_alethia_cost_controls_applied", True)
    return app
