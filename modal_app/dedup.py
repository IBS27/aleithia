"""SeenSet — persistent deduplication set backed by shared JSON storage.

Stores seen document IDs at /data/dedup/{source}.json.
Follows the same persistence pattern as FallbackChain cache files.
Uses advisory locks to prevent concurrent pipeline runs from losing dedup
entries across mounted volumes and S3/object storage.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.shared_data import get_dedup_data_dir, load_json_file, shared_data_lock, write_json_file

DEDUP_PATH = None
MAX_IDS = 10_000
DEFAULT_DEDUP_LOCK_TIMEOUT_SECONDS = 180.0
DEFAULT_DEDUP_LOCK_STALE_SECONDS = 60.0
DEFAULT_DEDUP_LOCK_POLL_SECONDS = 1.0


def _positive_env_float(name: str, default: float, *, minimum: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return max(minimum, value)


def _dedup_lock_settings() -> tuple[float, float, float]:
    stale_seconds = _positive_env_float(
        "ALEITHIA_DEDUP_LOCK_STALE_SECONDS",
        DEFAULT_DEDUP_LOCK_STALE_SECONDS,
        minimum=5.0,
    )
    timeout_seconds = _positive_env_float(
        "ALEITHIA_DEDUP_LOCK_TIMEOUT_SECONDS",
        max(DEFAULT_DEDUP_LOCK_TIMEOUT_SECONDS, stale_seconds + 30.0),
        minimum=10.0,
    )
    if timeout_seconds <= stale_seconds:
        timeout_seconds = stale_seconds + 30.0
    poll_seconds = _positive_env_float(
        "ALEITHIA_DEDUP_LOCK_POLL_SECONDS",
        DEFAULT_DEDUP_LOCK_POLL_SECONDS,
        minimum=0.1,
    )
    return timeout_seconds, poll_seconds, stale_seconds


def _parse_dedup_payload(data: Any) -> tuple[list[str], dict[str, str]] | None:
    if isinstance(data, list):
        return [doc_id for doc_id in data if isinstance(doc_id, str)], {}

    if isinstance(data, dict):
        raw_ids = data.get("ids", [])
        if not isinstance(raw_ids, list):
            return [], {}

        ids = [doc_id for doc_id in raw_ids if isinstance(doc_id, str)]
        raw_seen_at = data.get("seen_at", {})
        seen_at: dict[str, str] = {}
        if isinstance(raw_seen_at, dict):
            seen_at = {
                key: str(value)
                for key, value in raw_seen_at.items()
                if isinstance(key, str)
            }
        return ids, seen_at

    return None


class SeenSet:
    """Persistent set of document IDs for cross-run deduplication.

    Usage:
        seen = SeenSet("news")
        if not seen.contains(doc_id):
            # process document
            seen.add(doc_id)
        seen.save()
    """

    def __init__(self, source: str):
        self.source = source
        self.dir = Path(DEDUP_PATH) if DEDUP_PATH is not None else get_dedup_data_dir()
        self.file = self.dir / f"{source}.json"
        self._lock_file = self.dir / f"{source}.lock"
        self._list: list[str] = []
        self._set: set[str] = set()
        self._seen_at: dict[str, str] = {}
        self._lock_cm = None
        self._load()

    def _load(self) -> None:
        """Load existing IDs from Volume."""
        try:
            if self.file.exists():
                data = load_json_file(self.file, default=None)
                parsed = _parse_dedup_payload(data)
                if parsed is not None:
                    self._list, self._seen_at = parsed
                    self._set = set(self._list)
                    print(f"SeenSet [{self.source}]: loaded {len(self._set)} IDs")
                    return
        except Exception as e:
            print(f"SeenSet [{self.source}]: load error: {e}")
        print(f"SeenSet [{self.source}]: starting empty")

    def _acquire_lock(
        self,
        *,
        timeout_seconds: float | None = None,
        poll_seconds: float | None = None,
        stale_seconds: float | None = None,
    ) -> None:
        """Acquire exclusive file lock for save operations."""
        default_timeout_seconds, default_poll_seconds, default_stale_seconds = _dedup_lock_settings()
        self._lock_cm = shared_data_lock(
            self._lock_file,
            timeout_seconds=timeout_seconds if timeout_seconds is not None else default_timeout_seconds,
            poll_seconds=poll_seconds if poll_seconds is not None else default_poll_seconds,
            stale_seconds=stale_seconds if stale_seconds is not None else default_stale_seconds,
        )
        try:
            self._lock_cm.__enter__()
        except Exception:
            self._lock_cm = None
            raise

    def _release_lock(self) -> None:
        """Release file lock."""
        if self._lock_cm:
            self._lock_cm.__exit__(None, None, None)
            self._lock_cm = None

    def contains(self, doc_id: str, max_age_hours: int | None = None) -> bool:
        """Check if a document ID has been seen before.

        If `max_age_hours` is set, stale IDs are treated as unseen so mutable
        records can refresh periodically.
        """
        if doc_id not in self._set:
            return False

        if max_age_hours is None:
            return True

        ts_str = self._seen_at.get(doc_id, "")
        if not ts_str:
            # Legacy dedup files had no timestamp metadata; allow refresh.
            return False

        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except ValueError:
            return False

        age_hours = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
        return age_hours <= max_age_hours

    def add(self, doc_id: str, seen_at: str | None = None) -> None:
        """Mark a document ID as seen."""
        if seen_at is None:
            seen_at = datetime.now(timezone.utc).isoformat()
        self._seen_at[doc_id] = seen_at
        if doc_id not in self._set:
            self._list.append(doc_id)
            self._set.add(doc_id)

    def save(
        self,
        *,
        timeout_seconds: float | None = None,
        poll_seconds: float | None = None,
        stale_seconds: float | None = None,
    ) -> bool:
        """Persist the set to Volume under exclusive file lock.

        Lock → reload from disk (merge any IDs added by concurrent runs) →
        merge in-memory additions → write → unlock.
        """
        try:
            self._acquire_lock(
                timeout_seconds=timeout_seconds,
                poll_seconds=poll_seconds,
                stale_seconds=stale_seconds,
            )
            try:
                # Reload from disk under lock to merge concurrent additions
                disk_ids: list[str] = []
                disk_seen_at: dict[str, str] = {}
                if self.file.exists():
                    data = load_json_file(self.file, default=None)
                    parsed = _parse_dedup_payload(data)
                    if parsed is not None:
                        disk_ids, disk_seen_at = parsed

                # Merge: disk IDs first, then our in-memory IDs (preserves order)
                merged_set = set(disk_ids)
                merged_list = list(disk_ids)
                merged_seen_at = dict(disk_seen_at)
                for doc_id in self._list:
                    if doc_id not in merged_set:
                        merged_list.append(doc_id)
                        merged_set.add(doc_id)
                    # Always take our timestamp (more recent)
                    if doc_id in self._seen_at:
                        merged_seen_at[doc_id] = self._seen_at[doc_id]

                # Cap at MAX_IDS, dropping oldest
                if len(merged_list) > MAX_IDS:
                    merged_list = merged_list[-MAX_IDS:]
                    merged_set = set(merged_list)
                merged_seen_at = {k: merged_seen_at.get(k, "") for k in merged_list}

                payload = {"ids": merged_list, "seen_at": merged_seen_at}
                write_json_file(self.file, payload, indent=None)

                # Update in-memory state to match
                self._list = merged_list
                self._set = merged_set
                self._seen_at = merged_seen_at
                print(f"SeenSet [{self.source}]: saved {len(self._list)} IDs")
                return True
            finally:
                self._release_lock()
        except Exception as e:
            print(f"SeenSet [{self.source}]: save error: {e}")
            raise
