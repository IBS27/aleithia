"""Shared compute cost tracking helpers for Modal functions/classes."""
from __future__ import annotations

import inspect
import time
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, TypeVar, cast

import modal

# GPU/CPU cost rates (USD per second).
COST_RATES = {
    "H100": 0.001389,
    "A100-80GB": 0.001042,
    "A10G": 0.000306,
    "T4": 0.000164,
    "CPU": 0.0000125,
}

cost_dict = modal.Dict.from_name("alethia-costs", create_if_missing=True)

F = TypeVar("F", bound=Callable[..., Any])


def _make_key(function_name: str) -> str:
    date_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"{function_name}_{date_key}"


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _build_entry(
    existing: dict[str, Any] | None,
    *,
    function_name: str,
    gpu: str,
    duration_seconds: float,
    invocations: int,
) -> dict[str, Any]:
    prev = existing if isinstance(existing, dict) else {}
    rate = COST_RATES.get(gpu, COST_RATES["CPU"])
    increment_cost = rate * duration_seconds

    return {
        "total_cost": _to_float(prev.get("total_cost")) + increment_cost,
        "total_seconds": _to_float(prev.get("total_seconds")) + duration_seconds,
        "invocations": _to_int(prev.get("invocations")) + invocations,
        "gpu": gpu,
        "function": function_name,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


def log_cost(
    function_name: str,
    gpu: str,
    duration_seconds: float,
    *,
    invocations: int = 1,
) -> None:
    """Record compute cost for a sync function call."""
    if duration_seconds <= 0 or invocations <= 0:
        return

    key = _make_key(function_name)
    try:
        try:
            existing = cost_dict[key]
        except KeyError:
            existing = None
        cost_dict[key] = _build_entry(
            existing,
            function_name=function_name,
            gpu=gpu,
            duration_seconds=duration_seconds,
            invocations=invocations,
        )
    except Exception:
        # Cost accounting should never fail application logic.
        pass


async def log_cost_aio(
    function_name: str,
    gpu: str,
    duration_seconds: float,
    *,
    invocations: int = 1,
) -> None:
    """Record compute cost for an async function call."""
    if duration_seconds <= 0 or invocations <= 0:
        return

    key = _make_key(function_name)
    try:
        existing = None
        get_aio = getattr(cost_dict.get, "aio", None)
        if callable(get_aio):
            existing = await get_aio(key)
        else:
            try:
                existing = cost_dict[key]
            except KeyError:
                existing = None

        entry = _build_entry(
            existing,
            function_name=function_name,
            gpu=gpu,
            duration_seconds=duration_seconds,
            invocations=invocations,
        )

        put_aio = getattr(cost_dict.put, "aio", None)
        if callable(put_aio):
            await put_aio(key, entry)
        else:
            cost_dict[key] = entry
    except Exception:
        # Cost accounting should never fail application logic.
        pass


def track_cost(function_name: str, gpu: str) -> Callable[[F], F]:
    """Decorator that logs runtime cost for sync/async/async-generator callables."""

    def _decorator(func: F) -> F:
        if inspect.isasyncgenfunction(func):
            @wraps(func)
            async def _asyncgen_wrapper(*args: Any, **kwargs: Any):
                start = time.perf_counter()
                try:
                    async for item in func(*args, **kwargs):
                        yield item
                finally:
                    await log_cost_aio(function_name, gpu, time.perf_counter() - start)

            return cast(F, _asyncgen_wrapper)

        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def _async_wrapper(*args: Any, **kwargs: Any):
                start = time.perf_counter()
                try:
                    return await func(*args, **kwargs)
                finally:
                    await log_cost_aio(function_name, gpu, time.perf_counter() - start)

            return cast(F, _async_wrapper)

        @wraps(func)
        def _sync_wrapper(*args: Any, **kwargs: Any):
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                log_cost(function_name, gpu, time.perf_counter() - start)

        return cast(F, _sync_wrapper)

    return _decorator
