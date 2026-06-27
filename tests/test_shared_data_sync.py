from __future__ import annotations

from datetime import datetime, timezone

from backend.shared_data import SharedFileEntry
from scripts.maintenance import sync_shared_data_to_s3


class MemoryAccessor:
    def __init__(self, objects: dict[str, bytes] | None = None) -> None:
        self.objects = dict(objects or {})
        self.writes: list[tuple[str, bytes, str | None]] = []

    def get_entry(self, relative_path: str):
        if relative_path not in self.objects:
            return None
        return SharedFileEntry(
            path=relative_path,
            is_file=True,
            is_dir=False,
            mtime=datetime.now(timezone.utc).timestamp(),
            size=len(self.objects[relative_path]),
        )

    def list_entries(self, relative_path: str, *, recursive: bool = False):
        prefix = relative_path.strip("/")
        if prefix:
            prefix = f"{prefix}/"
        entries = []
        for path, payload in self.objects.items():
            if prefix and not path.startswith(prefix):
                continue
            remainder = path[len(prefix):] if prefix else path
            if not recursive and "/" in remainder:
                child = f"{prefix}{remainder.split('/', 1)[0]}".strip("/")
                if child not in {entry.path for entry in entries}:
                    entries.append(SharedFileEntry(path=child, is_file=False, is_dir=True, mtime=0, size=0))
                continue
            entries.append(
                SharedFileEntry(
                    path=path,
                    is_file=True,
                    is_dir=False,
                    mtime=datetime.now(timezone.utc).timestamp(),
                    size=len(payload),
                )
            )
        return entries

    def read_bytes(self, relative_path: str) -> bytes:
        return self.objects[relative_path]

    def write_bytes(self, relative_path: str, data: bytes, *, content_type: str | None = None) -> None:
        self.objects[relative_path] = data
        self.writes.append((relative_path, data, content_type))


def test_shared_data_sync_dry_run_does_not_write() -> None:
    source = MemoryAccessor(
        {
            "raw/news/doc.json": b'{"id":"n1"}',
            "raw/reviews/doc.json": b'{"id":"r1"}',
            "processed/geo/neighborhood_metrics.json": b'{"features":[]}',
        }
    )
    destination = MemoryAccessor()

    result = sync_shared_data_to_s3.sync_prefix(
        source=source,
        destination=destination,
        prefix="raw",
        write=False,
        overwrite=False,
    )

    assert result.discovered == 2
    assert result.copied == 0
    assert destination.objects == {}


def test_shared_data_sync_skips_existing_objects_by_default() -> None:
    source = MemoryAccessor(
        {
            "raw/news/existing.json": b'{"id":"old-source"}',
            "raw/news/new.json": b'{"id":"new"}',
        }
    )
    destination = MemoryAccessor({"raw/news/existing.json": b'{"id":"old-dest"}'})

    result = sync_shared_data_to_s3.sync_prefix(
        source=source,
        destination=destination,
        prefix="raw",
        write=True,
        overwrite=False,
    )

    assert result.discovered == 2
    assert result.copied == 1
    assert result.skipped_existing == 1
    assert destination.objects["raw/news/existing.json"] == b'{"id":"old-dest"}'
    assert destination.objects["raw/news/new.json"] == b'{"id":"new"}'
    assert destination.writes == [("raw/news/new.json", b'{"id":"new"}', "application/json")]


def test_shared_data_sync_can_overwrite_existing_objects() -> None:
    source = MemoryAccessor({"processed/status/sources/news.json": b'{"state":"success"}'})
    destination = MemoryAccessor({"processed/status/sources/news.json": b'{"state":"old"}'})

    result = sync_shared_data_to_s3.sync_prefix(
        source=source,
        destination=destination,
        prefix="processed",
        write=True,
        overwrite=True,
    )

    assert result.copied == 1
    assert result.skipped_existing == 0
    assert destination.objects["processed/status/sources/news.json"] == b'{"state":"success"}'


def test_shared_data_sync_accepts_direct_file_prefix() -> None:
    source = MemoryAccessor({"processed/demographics_summary.json": b'{"city_wide":{}}'})
    destination = MemoryAccessor()

    result = sync_shared_data_to_s3.sync_prefix(
        source=source,
        destination=destination,
        prefix="processed/demographics_summary.json",
        write=True,
        overwrite=False,
    )

    assert result.discovered == 1
    assert result.copied == 1
    assert destination.objects["processed/demographics_summary.json"] == b'{"city_wide":{}}'


def test_shared_data_sync_skips_dedup_lock_files() -> None:
    source = MemoryAccessor(
        {
            "dedup/news.json": b'{"ids":[]}',
            "dedup/news.lock": b'{"owner":"stale"}',
            "dedup/archive/old.lock": b"stale",
        }
    )
    destination = MemoryAccessor()

    result = sync_shared_data_to_s3.sync_prefix(
        source=source,
        destination=destination,
        prefix="dedup",
        write=True,
        overwrite=False,
    )

    assert result.discovered == 1
    assert result.copied == 1
    assert destination.objects == {"dedup/news.json": b'{"ids":[]}'}
    assert sync_shared_data_to_s3.iter_source_files(source, "dedup/news.lock") == []
