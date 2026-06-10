"""SeenSet — persistent deduplication set backed by JSON on Modal Volume.

Stores seen document IDs at /data/dedup/{source}.json.
Follows the same persistence pattern as FallbackChain cache files.
Uses advisory file locking (fcntl) to prevent concurrent pipeline runs
from losing dedup entries.
"""
from __future__ import annotations

import fcntl
from datetime import datetime, timezone
from pathlib import Path

from backend.shared_data import get_dedup_data_dir, load_json_file, write_json_file

DEDUP_PATH = None
MAX_IDS = 10_000


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
        self._lock_fd = None
        self._load()

    def _load(self) -> None:
        """Load existing IDs from Volume."""
        try:
            if self.file.exists():
                data = load_json_file(self.file, default=None)
                if isinstance(data, list):
                    self._list = data
                    self._set = set(data)
                    self._seen_at = {}
                    print(f"SeenSet [{self.source}]: loaded {len(self._set)} IDs")
                    return
                if isinstance(data, dict):
                    ids = data.get("ids", [])
                    seen_at = data.get("seen_at", {})
                    if isinstance(ids, list):
                        self._list = ids
                        self._set = set(ids)
                        if isinstance(seen_at, dict):
                            self._seen_at = {
                                k: str(v) for k, v in seen_at.items() if isinstance(k, str)
                            }
                        print(f"SeenSet [{self.source}]: loaded {len(self._set)} IDs")
                        return
        except Exception as e:
            print(f"SeenSet [{self.source}]: load error: {e}")
        print(f"SeenSet [{self.source}]: starting empty")

    def _acquire_lock(self) -> None:
        """Acquire exclusive file lock for save operations."""
        if not isinstance(self._lock_file, Path):
            self._lock_fd = None
            return
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock_fd = open(self._lock_file, "w")
        fcntl.flock(self._lock_fd, fcntl.LOCK_EX)

    def _release_lock(self) -> None:
        """Release file lock."""
        if self._lock_fd:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            self._lock_fd.close()
            self._lock_fd = None

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

    def save(self) -> None:
        """Persist the set to Volume under exclusive file lock.

        Lock → reload from disk (merge any IDs added by concurrent runs) →
        merge in-memory additions → write → unlock.
        """
        try:
            self._acquire_lock()
            try:
                # Reload from disk under lock to merge concurrent additions
                disk_ids: list[str] = []
                disk_seen_at: dict[str, str] = {}
                if self.file.exists():
                    data = load_json_file(self.file, default=None)
                    if isinstance(data, list):
                        disk_ids = data
                    elif isinstance(data, dict):
                        disk_ids = data.get("ids", [])
                        disk_seen_at = data.get("seen_at", {})

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
            finally:
                self._release_lock()
        except Exception as e:
            print(f"SeenSet [{self.source}]: save error: {e}")
