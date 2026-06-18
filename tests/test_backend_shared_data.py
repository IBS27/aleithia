from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime, timezone

from tests.backend_test_helpers import StrictRecursiveAccessor, install_local_accessor, write_json

import read_helpers
import shared_data


def test_shared_data_resolution_prefers_env_over_detected_layout(tmp_path, monkeypatch) -> None:
    data_root = tmp_path / "shared"
    (data_root / "raw").mkdir(parents=True)
    (data_root / "processed").mkdir(parents=True)
    install_local_accessor(monkeypatch, data_root)

    assert shared_data.get_raw_data_dir().relative_path == "raw"
    assert shared_data.get_processed_data_dir().relative_path == "processed"
    assert str(shared_data.get_raw_data_dir()).startswith("modal://")


def test_shared_data_can_resolve_explicit_object_storage_backend(monkeypatch) -> None:
    monkeypatch.setenv("ALEITHIA_SHARED_DATA_BACKEND", "s3")
    monkeypatch.setenv("ALEITHIA_OBJECT_STORAGE_BUCKET", "alethia-data-portable")
    monkeypatch.setenv("ALEITHIA_OBJECT_STORAGE_PREFIX", "runtime")
    monkeypatch.setenv("ALEITHIA_OBJECT_STORAGE_ENDPOINT_URL", "https://objects.example")
    shared_data._LAST_LOGGED_LAYOUT = None
    shared_data._VOLUME = None

    paths = shared_data.get_shared_data_paths()

    assert isinstance(paths.raw_dir.accessor, shared_data.S3ObjectStorageAccessor)
    assert str(paths.raw_dir) == "s3://alethia-data-portable/runtime/raw"
    assert str(paths.processed_dir) == "s3://alethia-data-portable/runtime/processed"


def test_modal_backend_uses_mounted_volume_accessor_when_data_root_exists(tmp_path, monkeypatch) -> None:
    data_root = tmp_path / "mounted-data"
    write_json(data_root / "raw" / "news" / "latest.json", '{"id":"n1"}')
    write_json(data_root / "processed" / "summary.json", '{"ok":true}')

    monkeypatch.setenv("ALEITHIA_MOUNTED_VOLUME_ROOT", str(data_root))
    monkeypatch.delenv("ALEITHIA_SHARED_DATA_BACKEND", raising=False)
    shared_data._LAST_LOGGED_LAYOUT = None
    shared_data._VOLUME = None

    paths = shared_data.get_shared_data_paths()

    assert isinstance(paths.raw_dir.accessor, shared_data.MountedVolumeAccessor)
    assert shared_data.load_json_docs_from_directory(paths.raw_dir / "news") == [{"id": "n1"}]
    assert shared_data.load_json_file(paths.processed_dir / "summary.json") == {"ok": True}


def test_mounted_accessor_lists_with_name_prefix(tmp_path) -> None:
    write_json(tmp_path / "raw" / "public_data" / "2026-06-10" / "public-food_inspections-1.json", '{"id":"insp"}')
    write_json(tmp_path / "raw" / "public_data" / "2026-06-10" / "public-building_permits-1.json", '{"id":"permit"}')

    accessor = shared_data.MountedVolumeAccessor(tmp_path)

    entries = accessor.list_entries_with_name_prefix(
        "raw/public_data/2026-06-10",
        name_prefix="public-food_inspections-",
    )

    assert [entry.name for entry in entries] == ["public-food_inspections-1.json"]


def test_modal_volume_accessor_lists_with_name_prefix() -> None:
    class FakeModalEntry:
        def __init__(self, path: str, entry_type) -> None:
            self.path = path
            self.type = entry_type
            self.mtime = 1
            self.size = 10

    class FakeVolume:
        def listdir(self, relative_path: str, recursive: bool = False):
            assert relative_path == "raw/public_data/2026-06-10"
            assert recursive is False
            return [
                FakeModalEntry("raw/public_data/2026-06-10/public-food_inspections-1.json", shared_data.FileEntryType.FILE),
                FakeModalEntry("raw/public_data/2026-06-10/public-building_permits-1.json", shared_data.FileEntryType.FILE),
            ]

    accessor = shared_data.ModalVolumeAccessor(FakeVolume())

    entries = accessor.list_entries_with_name_prefix(
        "raw/public_data/2026-06-10",
        name_prefix="public-food_inspections-",
    )

    assert [entry.name for entry in entries] == ["public-food_inspections-1.json"]


class _FakeObjectStorageResponse:
    def __init__(self, body: bytes = b"", *, status: int = 200, headers: dict[str, str] | None = None):
        self._body = body
        self.status = status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        return False

    def read(self) -> bytes:
        return self._body


def test_s3_object_storage_accessor_lists_reads_and_writes(monkeypatch) -> None:
    objects = {
        "runtime/raw/news/current.json": b'{"id":"current","title":"Current"}',
        "runtime/raw/news/2026/doc.json": b'{"id":"nested","title":"Nested"}',
    }
    uploads: dict[str, bytes] = {}

    def _key_from_url(url: str) -> str:
        parsed = urllib.parse.urlparse(url)
        parts = [urllib.parse.unquote(part) for part in parsed.path.strip("/").split("/")]
        return "/".join(parts[1:])

    def _list_xml(prefix: str, recursive: bool) -> bytes:
        if recursive:
            body = """
              <ListBucketResult>
                <Contents>
                  <Key>runtime/raw/news/current.json</Key>
                  <LastModified>2026-04-28T00:03:00Z</LastModified>
                  <Size>34</Size>
                </Contents>
                <Contents>
                  <Key>runtime/raw/news/2026/doc.json</Key>
                  <LastModified>2026-04-28T00:04:00Z</LastModified>
                  <Size>33</Size>
                </Contents>
                <IsTruncated>false</IsTruncated>
              </ListBucketResult>
            """
        else:
            assert prefix == "runtime/raw/news/"
            body = """
              <ListBucketResult>
                <Contents>
                  <Key>runtime/raw/news/current.json</Key>
                  <LastModified>2026-04-28T00:03:00Z</LastModified>
                  <Size>34</Size>
                </Contents>
                <CommonPrefixes>
                  <Prefix>runtime/raw/news/2026/</Prefix>
                </CommonPrefixes>
                <IsTruncated>false</IsTruncated>
              </ListBucketResult>
            """
        return body.encode("utf-8")

    def fake_urlopen(request, timeout=0):
        del timeout
        parsed = urllib.parse.urlparse(request.full_url)
        query = urllib.parse.parse_qs(parsed.query)
        method = request.get_method()
        if method == "GET" and query.get("list-type") == ["2"]:
            prefix = query.get("prefix", [""])[0]
            recursive = "delimiter" not in query
            return _FakeObjectStorageResponse(_list_xml(prefix, recursive))

        key = _key_from_url(request.full_url)
        if method == "GET":
            return _FakeObjectStorageResponse(objects[key])
        if method == "PUT":
            headers = {key.lower(): value for key, value in request.header_items()}
            if headers.get("if-none-match") == "*" and key in uploads:
                raise shared_data.urllib.error.HTTPError(request.full_url, 412, "precondition failed", {}, None)
            uploads[key] = request.data or b""
            return _FakeObjectStorageResponse()
        if method == "DELETE":
            uploads.pop(key, None)
            return _FakeObjectStorageResponse()
        raise AssertionError(f"unexpected object storage request: {method} {request.full_url}")

    monkeypatch.setattr(shared_data.urllib.request, "urlopen", fake_urlopen)
    accessor = shared_data.S3ObjectStorageAccessor(
        bucket="alethia-data-portable",
        prefix="runtime",
        endpoint_url="https://objects.example",
        timeout_seconds=1,
    )

    news_dir = shared_data.SharedDataPath(accessor, "raw/news")
    immediate = accessor.list_entries("raw/news")
    assert {(entry.path, entry.is_dir) for entry in immediate} == {
        ("raw/news/2026", True),
        ("raw/news/current.json", False),
    }

    docs = shared_data.load_json_docs_from_directory(news_dir)
    assert {doc["id"] for doc in docs} == {"current", "nested"}

    out_path = shared_data.SharedDataPath(accessor, "processed/summaries/news_summary.json")
    out_path.write_text('{"count":2}')
    assert uploads["runtime/processed/summaries/news_summary.json"] == b'{"count":2}'

    assert accessor.try_write_bytes_if_absent("locks/test.lock", b"owner") is True
    assert accessor.try_write_bytes_if_absent("locks/test.lock", b"other") is False
    accessor.delete_entry("locks/test.lock")
    assert "runtime/locks/test.lock" not in uploads


def test_s3_object_storage_accessor_lists_with_name_prefix(monkeypatch) -> None:
    observed_queries: list[dict[str, list[str]]] = []

    def fake_urlopen(request, timeout=0):
        del timeout
        parsed = urllib.parse.urlparse(request.full_url)
        query = urllib.parse.parse_qs(parsed.query)
        observed_queries.append(query)
        assert request.get_method() == "GET"
        assert query.get("list-type") == ["2"]
        assert query.get("prefix") == ["runtime/raw/public_data/2026-06-10/public-food_inspections-"]
        assert query.get("delimiter") == ["/"]
        assert query.get("max-keys") == ["3"]
        body = """
          <ListBucketResult>
            <Contents>
              <Key>runtime/raw/public_data/2026-06-10/public-food_inspections-1.json</Key>
              <LastModified>2026-06-10T00:03:00Z</LastModified>
              <Size>34</Size>
            </Contents>
            <Contents>
              <Key>runtime/raw/public_data/2026-06-10/public-food_inspections-2.json</Key>
              <LastModified>2026-06-10T00:04:00Z</LastModified>
              <Size>35</Size>
            </Contents>
            <IsTruncated>false</IsTruncated>
          </ListBucketResult>
        """
        return _FakeObjectStorageResponse(body.encode("utf-8"))

    monkeypatch.setattr(shared_data.urllib.request, "urlopen", fake_urlopen)
    accessor = shared_data.S3ObjectStorageAccessor(
        bucket="alethia-data-portable",
        prefix="runtime",
        endpoint_url="https://objects.example",
        timeout_seconds=1,
    )

    entries = accessor.list_entries_with_name_prefix(
        "raw/public_data/2026-06-10",
        name_prefix="public-food_inspections-",
        max_entries=3,
    )

    assert observed_queries
    assert [entry.name for entry in entries] == [
        "public-food_inspections-1.json",
        "public-food_inspections-2.json",
    ]


def test_shared_data_lock_uses_mounted_shared_path(tmp_path) -> None:
    accessor = shared_data.MountedVolumeAccessor(tmp_path)
    lock_path = shared_data.SharedDataPath(accessor, "dedup/test.lock")

    with shared_data.shared_data_lock(lock_path):
        assert (tmp_path / "dedup" / "test.lock").exists()


def test_shared_data_lock_times_out_when_mounted_lock_is_held(tmp_path) -> None:
    lock_file = tmp_path / "dedup" / "test.lock"
    script = (
        "import fcntl, pathlib, sys, time\n"
        "path = pathlib.Path(sys.argv[1])\n"
        "path.parent.mkdir(parents=True, exist_ok=True)\n"
        "with path.open('w') as handle:\n"
        "    fcntl.flock(handle, fcntl.LOCK_EX)\n"
        "    print('locked', flush=True)\n"
        "    time.sleep(2)\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", script, str(lock_file)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert proc.stdout is not None
        assert proc.stdout.readline().strip() == "locked"

        accessor = shared_data.MountedVolumeAccessor(tmp_path)
        lock_path = shared_data.SharedDataPath(accessor, "dedup/test.lock")

        started_at = time.monotonic()
        try:
            with shared_data.shared_data_lock(lock_path, timeout_seconds=0.1, poll_seconds=0.01):
                raise AssertionError("lock should not be acquired while another process holds it")
        except TimeoutError:
            pass
        assert time.monotonic() - started_at < 1.0
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_shared_data_lock_reclaims_stale_malformed_object_lock() -> None:
    class LockAccessor:
        def __init__(self) -> None:
            self.objects: dict[str, tuple[bytes, float]] = {
                "dedup/news.lock": (
                    b"not-json",
                    datetime.now(timezone.utc).timestamp() - 120,
                )
            }
            self.deleted: list[str] = []

        def display_uri(self, relative_path: str) -> str:
            return f"s3://example/{relative_path}"

        def get_entry(self, relative_path: str):
            if relative_path not in self.objects:
                return None
            data, mtime = self.objects[relative_path]
            return shared_data.SharedFileEntry(
                path=relative_path,
                is_file=True,
                is_dir=False,
                mtime=mtime,
                size=len(data),
            )

        def list_entries(self, relative_path: str, *, recursive: bool = False):
            del relative_path, recursive
            return []

        def read_bytes(self, relative_path: str) -> bytes:
            return self.objects[relative_path][0]

        def write_bytes(self, relative_path: str, data: bytes, *, content_type: str | None = None) -> None:
            del content_type
            self.objects[relative_path] = (data, datetime.now(timezone.utc).timestamp())

        def try_write_bytes_if_absent(
            self,
            relative_path: str,
            data: bytes,
            *,
            content_type: str | None = None,
        ) -> bool:
            del content_type
            if relative_path in self.objects:
                return False
            self.write_bytes(relative_path, data)
            return True

        def delete_entry(self, relative_path: str) -> None:
            self.deleted.append(relative_path)
            self.objects.pop(relative_path, None)

    accessor = LockAccessor()
    lock_path = shared_data.SharedDataPath(accessor, "dedup/news.lock")

    with shared_data.shared_data_lock(
        lock_path,
        timeout_seconds=0.5,
        poll_seconds=0.01,
        stale_seconds=60,
    ):
        payload = json.loads(accessor.objects["dedup/news.lock"][0].decode("utf-8"))
        assert payload["owner"]

    assert accessor.deleted.count("dedup/news.lock") == 2
    assert "dedup/news.lock" not in accessor.objects


def test_shared_data_lock_steals_stale_object_lock_when_delete_does_not_clear() -> None:
    class StickyLockAccessor:
        def __init__(self) -> None:
            self.objects: dict[str, tuple[bytes, float]] = {
                "dedup/news.lock": (
                    b"not-json",
                    datetime.now(timezone.utc).timestamp() - 120,
                )
            }
            self.deleted: list[str] = []

        def display_uri(self, relative_path: str) -> str:
            return f"s3://example/{relative_path}"

        def get_entry(self, relative_path: str):
            if relative_path not in self.objects:
                return None
            data, mtime = self.objects[relative_path]
            return shared_data.SharedFileEntry(
                path=relative_path,
                is_file=True,
                is_dir=False,
                mtime=mtime,
                size=len(data),
            )

        def list_entries(self, relative_path: str, *, recursive: bool = False):
            del relative_path, recursive
            return []

        def read_bytes(self, relative_path: str) -> bytes:
            return self.objects[relative_path][0]

        def write_bytes(self, relative_path: str, data: bytes, *, content_type: str | None = None) -> None:
            del content_type
            self.objects[relative_path] = (data, datetime.now(timezone.utc).timestamp())

        def try_write_bytes_if_absent(
            self,
            relative_path: str,
            data: bytes,
            *,
            content_type: str | None = None,
        ) -> bool:
            del data, content_type
            return relative_path not in self.objects

        def delete_entry(self, relative_path: str) -> None:
            self.deleted.append(relative_path)

    accessor = StickyLockAccessor()
    lock_path = shared_data.SharedDataPath(accessor, "dedup/news.lock")

    with shared_data.shared_data_lock(
        lock_path,
        timeout_seconds=0.5,
        poll_seconds=0.01,
        stale_seconds=60,
    ):
        payload = json.loads(accessor.objects["dedup/news.lock"][0].decode("utf-8"))
        assert payload["owner"]

    assert accessor.deleted


def test_load_raw_docs_recurses_and_skips_invalid_payloads(tmp_path, monkeypatch) -> None:
    data_root = tmp_path / "shared"
    install_local_accessor(monkeypatch, data_root)

    write_json(
        data_root / "raw" / "news" / "2026-03-17" / "latest.json",
        '{"id":"latest","title":"Latest","timestamp":"2026-03-17T12:00:00+00:00"}',
    )
    write_json(
        data_root / "raw" / "news" / "2026-03-16" / "older.json",
        '{"id":"older","title":"Older","timestamp":"2026-03-16T12:00:00+00:00"}',
    )
    write_json(data_root / "raw" / "news" / "2026-03-16" / "broken.json", '{"id":')
    write_json(data_root / "raw" / "news" / "2026-03-16" / "list.json", '["not", "a", "dict"]')

    assert shared_data.count_raw_json_files("news") == 4
    docs = shared_data.load_raw_docs("news")

    assert [doc["id"] for doc in docs] == ["latest", "older"]


def test_shared_data_recursive_scans_do_not_requery_child_entries(tmp_path, monkeypatch) -> None:
    data_root = tmp_path / "shared"
    accessor = StrictRecursiveAccessor(data_root)
    monkeypatch.setattr(shared_data, "_get_accessor", lambda: accessor)
    shared_data._LAST_LOGGED_LAYOUT = None
    shared_data._VOLUME = None

    write_json(
        data_root / "raw" / "news" / "2026-03-17" / "latest.json",
        '{"id":"latest","geo":{"neighborhood":"Loop"}}',
    )
    write_json(
        data_root / "raw" / "news" / "2026-03-16" / "older.json",
        '{"id":"older","geo":{"neighborhood":"West Loop"}}',
    )

    news_dir = shared_data.get_raw_data_dir() / "news"
    files = shared_data.iter_json_files(news_dir)
    assert [path.name for path in files] == ["latest.json", "older.json"]

    stats = shared_data.scan_source_directories({"news": news_dir}, neighborhood_sample_limit=2)
    assert stats["news"]["doc_count"] == 2
    assert stats["news"]["active"] is True
    assert stats["news"]["neighborhoods_covered"] == {"Loop", "West Loop"}


def test_processed_data_helpers_load_json_directory_and_latest_file(tmp_path, monkeypatch) -> None:
    data_root = tmp_path / "shared"
    install_local_accessor(monkeypatch, data_root)

    write_json(data_root / "processed" / "geo" / "neighborhood_metrics.json", '{"features": []}')
    write_json(data_root / "processed" / "summaries" / "news_summary.json", '{"count": 1}')
    write_json(data_root / "processed" / "summaries" / "politics_summary.json", '{"count": 2}')
    write_json(data_root / "processed" / "parking" / "analysis" / "loop_old.json", '{"id":"old"}')
    write_json(data_root / "processed" / "parking" / "analysis" / "loop_new.json", '{"id":"new"}')

    older = data_root / "processed" / "parking" / "analysis" / "loop_old.json"
    newer = data_root / "processed" / "parking" / "analysis" / "loop_new.json"
    os.utime(older, (1, 1))
    os.utime(newer, (2, 2))

    assert shared_data.load_processed_json("geo", "neighborhood_metrics.json", default={}) == {"features": []}
    assert shared_data.load_processed_json_directory("summaries", stem_suffix_to_strip="_summary") == {
        "news": {"count": 1},
        "politics": {"count": 2},
    }
    latest = shared_data.find_latest_processed_json_file("parking", "analysis", pattern="loop_*.json")
    assert latest is not None
    assert latest.name == "loop_new.json"


def test_source_status_heartbeat_overrides_stale_raw_mtime(tmp_path, monkeypatch) -> None:
    data_root = tmp_path / "shared"
    accessor = shared_data.MountedVolumeAccessor(data_root)
    monkeypatch.setattr(shared_data, "_get_accessor", lambda: accessor)
    shared_data._LAST_LOGGED_LAYOUT = None
    shared_data._VOLUME = None

    raw_doc = data_root / "raw" / "news" / "2026-03-17" / "latest.json"
    write_json(raw_doc, '{"id":"n1","title":"Old raw file"}')
    os.utime(raw_doc, (1, 1))

    status = shared_data.write_source_status("news", documents_seen=1, documents_written=0)
    stats = shared_data.get_source_freshness_stats(["news"])
    cheap_stats = shared_data.get_source_freshness_statuses(["news"])

    assert stats["news"]["doc_count"] == 1
    assert stats["news"]["active"] is True
    assert stats["news"]["last_update"] == status["last_success"]
    assert cheap_stats["news"]["doc_count"] == 0
    assert cheap_stats["news"]["last_update"] == status["last_success"]
    parsed = datetime.fromisoformat(stats["news"]["last_update"])
    assert parsed.tzinfo is not None
    assert parsed > datetime.fromtimestamp(1, tz=timezone.utc)


def test_s3_source_freshness_statuses_do_not_scan_raw_when_heartbeat_missing(monkeypatch) -> None:
    class NoRawScanAccessor:
        def get_entry(self, relative_path: str):
            return None

        def list_entries(self, relative_path: str, *, recursive: bool = False):
            if relative_path.startswith("raw/"):
                raise AssertionError("raw source scan should not run for missing S3 heartbeats")
            return []

        def read_bytes(self, relative_path: str) -> bytes:
            raise FileNotFoundError(relative_path)

    monkeypatch.setenv("ALEITHIA_SHARED_DATA_BACKEND", "s3")
    monkeypatch.setattr(shared_data, "_get_accessor", lambda: NoRawScanAccessor())
    shared_data._LAST_LOGGED_LAYOUT = None
    shared_data._VOLUME = None

    stats = shared_data.get_source_freshness_statuses(["news"])

    assert stats["news"] == {
        "doc_count": 0,
        "active": False,
        "last_update": None,
        "last_status": None,
        "missing_status": True,
    }


def test_raw_source_stats_and_read_helpers(tmp_path, monkeypatch) -> None:
    data_root = tmp_path / "shared"
    install_local_accessor(monkeypatch, data_root)

    write_json(
        data_root / "raw" / "news" / "2026-03-17" / "latest.json",
        '{"id":"n1","title":"Loop update","content":"Loop storefront changes","geo":{"neighborhood":"Loop"}}',
    )
    write_json(
        data_root / "raw" / "news" / "2026-03-16" / "older.json",
        '{"id":"n2","title":"Other update","geo":{"neighborhood":"Hyde Park"}}',
    )

    stats = shared_data.get_raw_source_stats(["news", "politics"])
    assert stats["news"]["doc_count"] == 2
    assert stats["news"]["active"] is True
    assert stats["news"]["last_update"] is not None
    assert stats["politics"] == {"doc_count": 0, "active": False, "last_update": None}

    docs = [
        {
            "id": "insp-1",
            "title": "Cafe inspection",
            "content": "Inspection in Loop",
            "metadata": {"dataset": "food_inspections", "raw_record": {"address": "123 Loop Ave"}},
            "geo": {"neighborhood": "Loop"},
        },
        {
            "id": "permit-1",
            "title": "Permit issued",
            "content": "Construction permit",
            "metadata": {"dataset": "building_permits", "raw_record": {"address": "456 Ashland"}},
            "geo": {"neighborhood": "West Town"},
        },
    ]

    assert [doc["id"] for doc in read_helpers.filter_docs_by_neighborhood(docs, "loop")] == ["insp-1"]
    assert [doc["id"] for doc in read_helpers.filter_public_data_by_dataset(docs, "food_inspections")] == ["insp-1"]

    transformed = read_helpers.transform_doc_for_graph(
        {
            "id": "doc-1",
            "title": "Doc",
            "memoryEntries": [
                {
                    "id": "mem-1",
                    "content": "Memory",
                    "memoryRelations": {"mem-0": "updates", "mem-x": "ignored"},
                }
            ],
            "x": 10,
            "y": 20,
        }
    )
    assert transformed["id"] == "doc-1"
    assert transformed["x"] == 10
    assert transformed["memoryEntries"][0]["memoryRelations"] == [
        {"targetMemoryId": "mem-0", "relationType": "updates"}
    ]
