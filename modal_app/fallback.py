"""FallbackChain — tries primary → secondary → cached data from last success.

Cache stored on Modal Volume at /data/cache/{source}/{key}.json.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Coroutine

from modal_app.volume import CACHE_PATH


class FallbackChain:
    """Executes a list of async fetchers in order, caches on success.

    Usage:
        chain = FallbackChain("news", "rss_blockclub")
        result = await chain.execute([
            fetch_rss_direct,      # Tier 0: primary
            fetch_google_news_rss, # Tier 1: secondary
        ])
        # On total failure, returns cached data from last success
    """

    def __init__(self, source: str, key: str, cache_ttl_hours: int = 168):
        self.source = source
        self.key = key
        self.cache_dir = Path(CACHE_PATH) / source
        self.cache_file = self.cache_dir / f"{key}.json"
        self.cache_ttl_seconds = cache_ttl_hours * 3600
        self.last_tier: int = -1   # -1 = cache, 0+ = fetcher index
        self.last_source: str = ""  # "live" or "cache"

    def _read_cache(self) -> Any | None:
        """Read cached data from last successful fetch. Returns None if expired."""
        try:
            if self.cache_file.exists():
                age = time.time() - self.cache_file.stat().st_mtime
                if age > self.cache_ttl_seconds:
                    print(f"FallbackChain [{self.source}/{self.key}]: cache expired ({age/3600:.1f}h > {self.cache_ttl_seconds/3600:.0f}h)")
                    return None
                data = json.loads(self.cache_file.read_text())
                print(f"FallbackChain [{self.source}/{self.key}]: using cached data ({age/3600:.1f}h old)")
                return data
        except Exception as e:
            print(f"FallbackChain [{self.source}/{self.key}]: cache read error: {e}")
        return None

    def _write_cache(self, data: Any) -> None:
        """Cache successful fetch result."""
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self.cache_file.write_text(json.dumps(data, default=str))
        except Exception as e:
            print(f"FallbackChain [{self.source}/{self.key}]: cache write error: {e}")

    async def execute(
        self,
        fetchers: list[Callable[[], Coroutine[Any, Any, Any]]],
    ) -> Any | None:
        """Try each fetcher in order. Cache on success. Return cache on total failure."""
        for i, fetcher in enumerate(fetchers):
            try:
                result = await fetcher()
                if result is not None and result != [] and result != {}:
                    print(f"FallbackChain [{self.source}/{self.key}]: Tier {i} succeeded")
                    self._write_cache(result)
                    self.last_tier = i
                    self.last_source = "live"
                    return result
                print(f"FallbackChain [{self.source}/{self.key}]: Tier {i} returned empty")
            except Exception as e:
                print(f"FallbackChain [{self.source}/{self.key}]: Tier {i} failed: {e}")

        # All tiers failed — try cache
        cached = self._read_cache()
        if cached is not None:
            self.last_tier = -1
            self.last_source = "cache"
        return cached
