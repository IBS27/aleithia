"""SeenSet — persistent deduplication set backed by JSON on Modal Volume.

Stores seen document IDs at /data/dedup/{source}.json.
Follows the same persistence pattern as FallbackChain cache files.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from modal_app.volume import VOLUME_MOUNT

DEDUP_PATH = f"{VOLUME_MOUNT}/dedup"
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
        self.dir = Path(DEDUP_PATH)
        self.file = self.dir / f"{source}.json"
        self._list: list[str] = []
        self._set: set[str] = set()
        self._seen_at: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        """Load existing IDs from Volume."""
        try:
            if self.file.exists():
                data = json.loads(self.file.read_text())
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
        """Persist the set to Volume. Caps at MAX_IDS, dropping oldest."""
        try:
            if len(self._list) > MAX_IDS:
                self._list = self._list[-MAX_IDS:]
                self._set = set(self._list)
            self._seen_at = {doc_id: self._seen_at.get(doc_id, "") for doc_id in self._list}
            self.dir.mkdir(parents=True, exist_ok=True)
            payload = {"ids": self._list, "seen_at": self._seen_at}
            self.file.write_text(json.dumps(payload))
            print(f"SeenSet [{self.source}]: saved {len(self._list)} IDs")
        except Exception as e:
            print(f"SeenSet [{self.source}]: save error: {e}")
