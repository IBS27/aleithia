#!/usr/bin/env python3
"""Local test harness for data ingestion pipelines.

Mocks Modal entirely so every pipeline's _fetch_* functions can run locally.

Usage:
    python3 test_pipelines.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
import types
from pathlib import Path

# ── 1. Create a temporary directory for volume paths ──────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="pipeline_test_")

# ── 2. Build a fake `modal` module ────────────────────────────────────────────

_modal = types.ModuleType("modal")

# No-op decorator helpers
def _identity(fn=None, **_kw):
    """Return fn unchanged, or return a decorator that does the same."""
    if fn is not None:
        return fn
    return lambda f: f

def _identity_cls(cls=None, **_kw):
    if cls is not None:
        return cls
    return lambda c: c

class _FakeImage:
    """Fluent builder that returns itself for every chained call."""
    def __getattr__(self, _name):
        return lambda *_a, **_kw: self

class _FakeApp:
    """Fake modal.App — decorators are no-ops."""
    def __init__(self, *_a, **_kw): pass
    def function(self, fn=None, **_kw): return _identity(fn, **_kw)
    def cls(self, cls=None, **_kw): return _identity_cls(cls, **_kw)
    def local_entrypoint(self, fn=None, **_kw): return _identity(fn, **_kw)

class _FakeVolume:
    @staticmethod
    def from_name(*_a, **_kw): return _FakeVolume()
    def commit(self): pass
    def reload(self): pass

class _FakeQueue:
    @staticmethod
    def from_name(*_a, **_kw): return _FakeQueue()
    def put(self, *_a, **_kw): pass
    def get(self, *_a, **_kw): return None

class _FakeSecret:
    @staticmethod
    def from_name(*_a, **_kw): return _FakeSecret()

# Populate the fake modal module
_modal.App = _FakeApp
_modal.Volume = _FakeVolume
_modal.Queue = _FakeQueue
_modal.Secret = _FakeSecret
_modal.Image = _FakeImage()
_modal.enter = _identity
_modal.exit = _identity
_modal.method = _identity
_modal.batched = _identity
_modal.build = _identity
_modal.web_endpoint = _identity
_modal.asgi_app = _identity
_modal.Period = lambda **_kw: None
_modal.Retries = lambda *_a, **_kw: None
_modal.Cron = lambda *_a, **_kw: None
_modal.concurrent = _identity

class _FakeDict:
    """Fake modal.Dict — in-memory dict with .from_name() constructor."""
    _store: dict = {}
    @staticmethod
    def from_name(*_a, **_kw): return _FakeDict()
    def __getitem__(self, key): return self._store[key]
    def __setitem__(self, key, value): self._store[key] = value
    def keys(self): return iter(self._store.keys())
    def get(self, key): return self._store.get(key)

_modal.Dict = _FakeDict

sys.modules["modal"] = _modal

# ── 3. Mock modal_app.volume ──────────────────────────────────────────────────
# We build a real-ish module so pipeline imports like
#   from modal_app.volume import app, volume, base_image, RAW_DATA_PATH
# all resolve.

_vol_mod = types.ModuleType("modal_app.volume")
_vol_mod.app = _FakeApp("alethia")
_vol_mod.volume = _FakeVolume()
_vol_mod.weights_volume = _FakeVolume()
_vol_mod.VOLUME_MOUNT = os.path.join(_tmpdir, "data")
_vol_mod.WEIGHTS_MOUNT = os.path.join(_tmpdir, "weights")
_vol_mod.RAW_DATA_PATH = os.path.join(_tmpdir, "data", "raw")
_vol_mod.PROCESSED_DATA_PATH = os.path.join(_tmpdir, "data", "processed")
_vol_mod.CACHE_PATH = os.path.join(_tmpdir, "data", "cache")

# Image stubs
for _img_name in (
    "base_image", "reddit_image", "politics_image", "data_image",
    "vllm_image", "classify_image", "web_image", "video_image",
    "label_image", "yolo_image", "tiktok_image", "transcribe_image",
):
    setattr(_vol_mod, _img_name, _FakeImage())

sys.modules["modal_app.volume"] = _vol_mod

# ── 4. Mock modal_app.classify ────────────────────────────────────────────────
_cls_mod = types.ModuleType("modal_app.classify")
_cls_mod.doc_queue = _FakeQueue()
sys.modules["modal_app.classify"] = _cls_mod

# ── 5. Ensure temp dirs exist for dedup / fallback / raw data ─────────────────
for _sub in ("data/raw", "data/cache", "data/dedup", "data/processed"):
    Path(os.path.join(_tmpdir, _sub)).mkdir(parents=True, exist_ok=True)

# ── 6. Now import pipeline code ──────────────────────────────────────────────
from modal_app.pipelines import news, reddit, politics, public_data  # noqa: E402
from modal_app.pipelines import demographics, federal_register        # noqa: E402
from modal_app.pipelines import realestate, reviews                   # noqa: E402
from modal_app.pipelines import cctv                                  # noqa: E402

# ── Reporting helpers ─────────────────────────────────────────────────────────

def _geo_count(docs: list[dict]) -> tuple[int, int]:
    """Count docs that have a non-empty geo dict."""
    total = len(docs)
    geo = sum(
        1 for d in docs
        if d.get("geo") and any(d["geo"].values())
    )
    return geo, total

def _sample(docs: list[dict], max_len: int = 70) -> str:
    for d in docs:
        title = d.get("title") or d.get("content", "")
        if title:
            return (title[:max_len] + "...") if len(title) > max_len else title
    return "(no title)"

def _fields(docs: list[dict]) -> str:
    if not docs:
        return ""
    return ", ".join(sorted(docs[0].keys()))

def _report(label: str, docs: list[dict] | None, elapsed: float, error: str = ""):
    print(f"\n{'━' * 3} {label} {'━' * (60 - len(label))}")
    if error:
        print(f"  Status:    ERROR")
        print(f"  Error:     {error}")
        print(f"  Elapsed:   {elapsed:.1f}s")
        return
    if docs is None:
        print(f"  Status:    SKIPPED (no API key)")
        return
    geo, total = _geo_count(docs)
    geo_pct = f"{geo / total * 100:.0f}%" if total else "n/a"
    print(f"  Status:    OK")
    print(f"  Documents: {total}")
    print(f"  Sample:    \"{_sample(docs)}\"")
    print(f"  Geo-tagged: {geo}/{total} ({geo_pct})")
    print(f"  Fields:    {_fields(docs)}")
    print(f"  Elapsed:   {elapsed:.1f}s")


# ── Pipeline runners ──────────────────────────────────────────────────────────

async def run_all():
    results: list[tuple[str, list[dict] | None, float, str]] = []

    async def _run(label: str, coro_fn, *args):
        t0 = time.monotonic()
        try:
            docs = await coro_fn(*args)
            if docs is None:
                docs = []
            results.append((label, docs, time.monotonic() - t0, ""))
        except Exception as e:
            results.append((label, [], time.monotonic() - t0, str(e)))

    # ── No API key needed ─────────────────────────────────────────────────

    await _run("NEWS (RSS)", news._fetch_all_rss)
    await _run("NEWS (Google RSS)", news._fetch_google_news_rss)
    await _run("REDDIT (RSS)", reddit._fetch_all_rss)
    await _run("POLITICS (Legislation)", politics._fetch_legislation_rest)
    await _run("POLITICS (Events)", politics._fetch_events)
    await _run("PUBLIC DATA (no token)", public_data._fetch_all_without_token)
    await _run("DEMOGRAPHICS (Census)", demographics._fetch_census)
    await _run("FEDERAL REGISTER", federal_register._fetch_federal_register)
    await _run("REAL ESTATE (placeholders)", realestate._create_placeholder_listings)
    await _run("CCTV (IDOT cameras)", cctv._fetch_idot_cameras)

    # ── API-key gated ─────────────────────────────────────────────────────

    newsapi_key = os.environ.get("NEWSAPI_KEY", "")
    if newsapi_key:
        await _run("NEWS (NewsAPI)", news._fetch_newsapi, newsapi_key)
    else:
        results.append(("NEWS (NewsAPI)", None, 0, ""))

    yelp_key = os.environ.get("YELP_API_KEY", "")
    if yelp_key:
        await _run("REVIEWS (Yelp)", reviews._fetch_yelp, yelp_key)
    else:
        results.append(("REVIEWS (Yelp)", None, 0, ""))

    google_key = os.environ.get("GOOGLE_PLACES_API_KEY", "")
    if google_key:
        await _run("REVIEWS (Google Places)", reviews._fetch_google_places, google_key)
    else:
        results.append(("REVIEWS (Google Places)", None, 0, ""))

    # ── Print report ──────────────────────────────────────────────────────
    print("\n" + "=" * 64)
    print("  PIPELINE TEST REPORT")
    print("=" * 64)

    ok = err = skip = 0
    for label, docs, elapsed, error in results:
        _report(label, docs, elapsed, error)
        if docs is None:
            skip += 1
        elif error:
            err += 1
        else:
            ok += 1

    print("\n" + "=" * 64)
    print(f"  SUMMARY: {ok} OK / {err} ERROR / {skip} SKIPPED")
    print("=" * 64 + "\n")


if __name__ == "__main__":
    asyncio.run(run_all())
