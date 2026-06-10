"""Shared dataset helpers for backend access to portable raw and processed data."""

from __future__ import annotations

import fnmatch
import hashlib
import hmac
import html
import io
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import Any, Callable, Iterable, Mapping, Protocol

import modal
from modal.volume import FileEntryType

logger = logging.getLogger(__name__)

DEFAULT_MODAL_VOLUME_NAME = "alethia-data"
DEFAULT_RAW_PREFIX = "raw"
DEFAULT_PROCESSED_PREFIX = "processed"
DEFAULT_OBJECT_STORAGE_REGION = "us-east-1"
DEFAULT_MOUNTED_VOLUME_ROOT = "/data"

_LAST_LOGGED_LAYOUT: tuple[str, str] | None = None
_VOLUME: modal.Volume | None = None


class SharedDataAccessor(Protocol):
    def get_entry(self, relative_path: str) -> "SharedFileEntry | None": ...

    def list_entries(self, relative_path: str, *, recursive: bool = False) -> list["SharedFileEntry"]: ...

    def read_bytes(self, relative_path: str) -> bytes: ...

    def write_bytes(self, relative_path: str, data: bytes, *, content_type: str | None = None) -> None: ...


@dataclass(frozen=True)
class SharedFileEntry:
    path: str
    is_file: bool
    is_dir: bool
    mtime: float
    size: int = 0

    @property
    def name(self) -> str:
        return PurePosixPath(self.path).name

    @property
    def suffix(self) -> str:
        return PurePosixPath(self.path).suffix

    @property
    def stem(self) -> str:
        return PurePosixPath(self.path).stem


def _normalize_relative_path(value: str | PurePosixPath | "SharedDataPath") -> str:
    if isinstance(value, SharedDataPath):
        return value.relative_path
    raw = str(value or "").strip().replace("\\", "/")
    if raw in ("", "."):
        return ""
    normalized = str(PurePosixPath(raw))
    return "" if normalized == "." else normalized.strip("/")


@dataclass(frozen=True)
class SharedDataPath:
    accessor: SharedDataAccessor
    relative_path: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "relative_path", _normalize_relative_path(self.relative_path))

    def __str__(self) -> str:
        display_uri = getattr(self.accessor, "display_uri", None)
        if callable(display_uri):
            return display_uri(self.relative_path)

        volume_name = os.getenv("ALEITHIA_MODAL_VOLUME_NAME", DEFAULT_MODAL_VOLUME_NAME).strip() or DEFAULT_MODAL_VOLUME_NAME
        return f"modal://{volume_name}/{self.relative_path}" if self.relative_path else f"modal://{volume_name}"

    def __repr__(self) -> str:
        return f"SharedDataPath({self.relative_path!r})"

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, SharedDataPath):
            return NotImplemented
        return self.relative_path < other.relative_path

    def __truediv__(self, key: str) -> "SharedDataPath":
        return self.joinpath(key)

    @property
    def name(self) -> str:
        return PurePosixPath(self.relative_path).name

    @property
    def suffix(self) -> str:
        return PurePosixPath(self.relative_path).suffix

    @property
    def stem(self) -> str:
        return PurePosixPath(self.relative_path).stem

    @property
    def parent(self) -> "SharedDataPath":
        parent = PurePosixPath(self.relative_path).parent
        parent_str = "" if str(parent) == "." else str(parent)
        return SharedDataPath(self.accessor, parent_str)

    def joinpath(self, *parts: str) -> "SharedDataPath":
        current = PurePosixPath(self.relative_path) if self.relative_path else PurePosixPath()
        joined = current.joinpath(*[str(part) for part in parts])
        return SharedDataPath(self.accessor, str(joined))

    def relative_to(self, other: "SharedDataPath") -> PurePosixPath:
        return PurePosixPath(self.relative_path).relative_to(PurePosixPath(other.relative_path))

    def exists(self) -> bool:
        return self.accessor.get_entry(self.relative_path) is not None

    def is_file(self) -> bool:
        entry = self.accessor.get_entry(self.relative_path)
        return bool(entry and entry.is_file)

    def is_dir(self) -> bool:
        entry = self.accessor.get_entry(self.relative_path)
        return bool(entry and entry.is_dir)

    def stat(self) -> SimpleNamespace:
        entry = self.accessor.get_entry(self.relative_path)
        if entry is None:
            raise OSError(f"No such file or directory: {self}")
        return SimpleNamespace(st_mtime=entry.mtime, st_size=entry.size)

    def read_bytes(self) -> bytes:
        return self.accessor.read_bytes(self.relative_path)

    def read_text(self, encoding: str = "utf-8") -> str:
        return self.read_bytes().decode(encoding)

    def write_bytes(self, data: bytes, *, content_type: str | None = None) -> None:
        write_bytes = getattr(self.accessor, "write_bytes", None)
        if not callable(write_bytes):
            raise OSError(f"Shared data accessor is read-only: {self}")
        write_bytes(self.relative_path, data, content_type=content_type)

    def write_text(self, data: str, encoding: str = "utf-8") -> None:
        self.write_bytes(data.encode(encoding), content_type="text/plain; charset=utf-8")

    def iterdir(self) -> list["SharedDataPath"]:
        return [SharedDataPath(self.accessor, entry.path) for entry in self.accessor.list_entries(self.relative_path)]

    def glob(self, pattern: str) -> list["SharedDataPath"]:
        return _glob_paths(self, pattern, recursive=False)

    def rglob(self, pattern: str) -> list["SharedDataPath"]:
        return _glob_paths(self, pattern, recursive=True)


@dataclass(frozen=True)
class SharedDataPaths:
    raw_dir: SharedDataPath
    processed_dir: SharedDataPath


class ModalVolumeAccessor:
    def __init__(self, volume: modal.Volume):
        self._volume = volume
        self._volume_name = os.getenv("ALEITHIA_MODAL_VOLUME_NAME", DEFAULT_MODAL_VOLUME_NAME).strip() or DEFAULT_MODAL_VOLUME_NAME

    def display_uri(self, relative_path: str) -> str:
        normalized = _normalize_relative_path(relative_path)
        return f"modal://{self._volume_name}/{normalized}" if normalized else f"modal://{self._volume_name}"

    def _entry_from_modal(self, entry: object) -> SharedFileEntry | None:
        entry_path = getattr(entry, "path", None)
        entry_type = getattr(entry, "type", None)
        if not isinstance(entry_path, str) or entry_type is None:
            return None
        return SharedFileEntry(
            path=entry_path.strip("/"),
            is_file=entry_type == FileEntryType.FILE,
            is_dir=entry_type == FileEntryType.DIRECTORY,
            mtime=float(getattr(entry, "mtime", 0) or 0),
            size=int(getattr(entry, "size", 0) or 0),
        )

    def get_entry(self, relative_path: str) -> SharedFileEntry | None:
        normalized = _normalize_relative_path(relative_path)
        if not normalized:
            return SharedFileEntry(path="", is_file=False, is_dir=True, mtime=0.0, size=0)
        parent = PurePosixPath(normalized).parent
        parent_path = "" if str(parent) == "." else str(parent)
        try:
            entries = self._volume.listdir(parent_path, recursive=False)
        except Exception:
            return None
        for entry in entries:
            parsed = self._entry_from_modal(entry)
            if parsed is None:
                continue
            if parsed.path == normalized:
                return parsed
        return None

    def list_entries(self, relative_path: str, *, recursive: bool = False) -> list[SharedFileEntry]:
        normalized = _normalize_relative_path(relative_path)
        try:
            entries = self._volume.listdir(normalized, recursive=recursive)
        except Exception:
            return []
        parsed_entries = [self._entry_from_modal(entry) for entry in entries]
        return [entry for entry in parsed_entries if entry is not None]

    def read_bytes(self, relative_path: str) -> bytes:
        normalized = _normalize_relative_path(relative_path)
        chunks = []
        for chunk in self._volume.read_file(normalized):
            chunks.append(chunk)
        return b"".join(chunks)

    def write_bytes(self, relative_path: str, data: bytes, *, content_type: str | None = None) -> None:
        del content_type
        normalized = _normalize_relative_path(relative_path)
        with self._volume.batch_upload(force=True) as batch:
            batch.put_file(io.BytesIO(data), f"/{normalized}")


class MountedVolumeAccessor:
    """Shared-data accessor for the Modal Volume mounted into remote containers."""

    def __init__(self, root: str | Path = DEFAULT_MOUNTED_VOLUME_ROOT):
        self.root = Path(root)

    def display_uri(self, relative_path: str) -> str:
        normalized = _normalize_relative_path(relative_path)
        return str(self.root / normalized) if normalized else str(self.root)

    def _full_path(self, relative_path: str) -> Path:
        return self.root / _normalize_relative_path(relative_path)

    def _entry_from_path(self, path: Path) -> SharedFileEntry | None:
        try:
            stat = path.stat()
        except OSError:
            return None
        try:
            relative = path.relative_to(self.root).as_posix()
        except ValueError:
            return None
        return SharedFileEntry(
            path=relative.strip("/"),
            is_file=path.is_file(),
            is_dir=path.is_dir(),
            mtime=float(stat.st_mtime),
            size=int(stat.st_size),
        )

    def get_entry(self, relative_path: str) -> SharedFileEntry | None:
        normalized = _normalize_relative_path(relative_path)
        if not normalized:
            return SharedFileEntry(path="", is_file=False, is_dir=True, mtime=0.0, size=0)
        return self._entry_from_path(self._full_path(normalized))

    def list_entries(self, relative_path: str, *, recursive: bool = False) -> list[SharedFileEntry]:
        directory = self._full_path(relative_path)
        if not directory.exists() or not directory.is_dir():
            return []
        iterator = directory.rglob("*") if recursive else directory.iterdir()
        entries = [self._entry_from_path(path) for path in iterator]
        return [entry for entry in entries if entry is not None]

    def read_bytes(self, relative_path: str) -> bytes:
        return self._full_path(relative_path).read_bytes()

    def write_bytes(self, relative_path: str, data: bytes, *, content_type: str | None = None) -> None:
        del content_type
        path = self._full_path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def try_write_bytes_if_absent(
        self,
        relative_path: str,
        data: bytes,
        *,
        content_type: str | None = None,
    ) -> bool:
        del content_type
        path = self._full_path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            return False
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        return True

    def delete_entry(self, relative_path: str) -> None:
        try:
            self._full_path(relative_path).unlink()
        except FileNotFoundError:
            return


class ObjectStorageError(RuntimeError):
    """Raised when the configured object storage backend cannot serve a request."""


class S3ObjectStorageAccessor:
    """S3-compatible shared-data accessor for S3, R2, and compatible object stores."""

    def __init__(
        self,
        *,
        bucket: str,
        prefix: str = "",
        endpoint_url: str | None = None,
        region: str = DEFAULT_OBJECT_STORAGE_REGION,
        access_key_id: str = "",
        secret_access_key: str = "",
        session_token: str = "",
        timeout_seconds: float = 10.0,
    ):
        bucket = bucket.strip()
        if not bucket:
            raise ValueError("ALEITHIA_OBJECT_STORAGE_BUCKET is required when ALEITHIA_SHARED_DATA_BACKEND=s3")

        self.bucket = bucket
        self.prefix = _normalize_relative_path(prefix)
        self.region = region.strip() or DEFAULT_OBJECT_STORAGE_REGION
        self.access_key_id = access_key_id.strip()
        self.secret_access_key = secret_access_key
        self.session_token = session_token.strip()
        self.timeout_seconds = timeout_seconds
        self.endpoint_url = (endpoint_url or f"https://s3.{self.region}.amazonaws.com").rstrip("/")

    @classmethod
    def from_env(cls) -> "S3ObjectStorageAccessor":
        timeout_raw = os.getenv("ALEITHIA_OBJECT_STORAGE_TIMEOUT_SECONDS", "10").strip()
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError:
            timeout_seconds = 10.0

        return cls(
            bucket=(
                os.getenv("ALEITHIA_OBJECT_STORAGE_BUCKET")
                or os.getenv("ALEITHIA_S3_BUCKET")
                or ""
            ),
            prefix=(
                os.getenv("ALEITHIA_OBJECT_STORAGE_PREFIX")
                or os.getenv("ALEITHIA_S3_PREFIX")
                or ""
            ),
            endpoint_url=(
                os.getenv("ALEITHIA_OBJECT_STORAGE_ENDPOINT_URL")
                or os.getenv("ALEITHIA_S3_ENDPOINT_URL")
                or None
            ),
            region=(
                os.getenv("ALEITHIA_OBJECT_STORAGE_REGION")
                or os.getenv("AWS_REGION")
                or os.getenv("AWS_DEFAULT_REGION")
                or DEFAULT_OBJECT_STORAGE_REGION
            ),
            access_key_id=(
                os.getenv("ALEITHIA_OBJECT_STORAGE_ACCESS_KEY_ID")
                or os.getenv("AWS_ACCESS_KEY_ID")
                or ""
            ),
            secret_access_key=(
                os.getenv("ALEITHIA_OBJECT_STORAGE_SECRET_ACCESS_KEY")
                or os.getenv("AWS_SECRET_ACCESS_KEY")
                or ""
            ),
            session_token=(
                os.getenv("ALEITHIA_OBJECT_STORAGE_SESSION_TOKEN")
                or os.getenv("AWS_SESSION_TOKEN")
                or ""
            ),
            timeout_seconds=timeout_seconds,
        )

    def display_uri(self, relative_path: str) -> str:
        key = self._object_key(relative_path)
        return f"s3://{self.bucket}/{key}" if key else f"s3://{self.bucket}"

    def _object_key(self, relative_path: str) -> str:
        normalized = _normalize_relative_path(relative_path)
        if self.prefix and normalized:
            return f"{self.prefix}/{normalized}"
        return self.prefix or normalized

    def _relative_from_key(self, key: str) -> str:
        key = key.strip("/")
        if self.prefix:
            prefix = f"{self.prefix}/"
            if key == self.prefix:
                return ""
            if not key.startswith(prefix):
                return ""
            key = key[len(prefix):]
        return key.strip("/")

    def _url_for_key(self, key: str, query: Mapping[str, str] | None = None) -> str:
        encoded_bucket = urllib.parse.quote(self.bucket, safe="")
        encoded_key = "/".join(urllib.parse.quote(part, safe="-_.~") for part in key.split("/") if part)
        path = f"/{encoded_bucket}"
        if encoded_key:
            path = f"{path}/{encoded_key}"
        query_string = _canonical_query_string(query or {})
        return f"{self.endpoint_url}{path}{f'?{query_string}' if query_string else ''}"

    def _signing_headers(
        self,
        *,
        method: str,
        url: str,
        body: bytes,
        extra_headers: Mapping[str, str],
    ) -> dict[str, str]:
        parsed = urllib.parse.urlparse(url)
        payload_hash = hashlib.sha256(body).hexdigest()
        headers = {
            "host": parsed.netloc,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
            **{key.lower(): value for key, value in extra_headers.items()},
        }
        if self.session_token:
            headers["x-amz-security-token"] = self.session_token

        if not self.access_key_id or not self.secret_access_key:
            return headers

        signed_header_names = sorted(headers)
        canonical_headers = "".join(f"{name}:{headers[name].strip()}\n" for name in signed_header_names)
        canonical_request = "\n".join(
            [
                method.upper(),
                parsed.path or "/",
                parsed.query,
                canonical_headers,
                ";".join(signed_header_names),
                payload_hash,
            ]
        )
        date_stamp = headers["x-amz-date"][:8]
        credential_scope = f"{date_stamp}/{self.region}/s3/aws4_request"
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                headers["x-amz-date"],
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        signing_key = _aws_sigv4_signing_key(self.secret_access_key, date_stamp, self.region, "s3")
        signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        headers["authorization"] = (
            "AWS4-HMAC-SHA256 "
            f"Credential={self.access_key_id}/{credential_scope}, "
            f"SignedHeaders={';'.join(signed_header_names)}, "
            f"Signature={signature}"
        )
        return headers

    def _request(
        self,
        method: str,
        key: str = "",
        *,
        query: Mapping[str, str] | None = None,
        body: bytes = b"",
        headers: Mapping[str, str] | None = None,
    ) -> tuple[int, Mapping[str, str], bytes]:
        url = self._url_for_key(key, query)
        signed_headers = self._signing_headers(
            method=method,
            url=url,
            body=body,
            extra_headers=headers or {},
        )
        request = urllib.request.Request(
            url,
            data=body if method.upper() in {"POST", "PUT"} else None,
            headers={key: value for key, value in signed_headers.items()},
            method=method.upper(),
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return int(getattr(response, "status", 200) or 200), response.headers, response.read()
        except urllib.error.HTTPError as exc:
            raise ObjectStorageError(f"object storage {method.upper()} {key or '/'} failed with {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise ObjectStorageError(f"object storage {method.upper()} {key or '/'} failed: {exc}") from exc

    def get_entry(self, relative_path: str) -> SharedFileEntry | None:
        normalized = _normalize_relative_path(relative_path)
        if not normalized:
            return SharedFileEntry(path="", is_file=False, is_dir=True, mtime=0.0, size=0)

        key = self._object_key(normalized)
        try:
            _, headers, _ = self._request("HEAD", key)
            return SharedFileEntry(
                path=normalized,
                is_file=True,
                is_dir=False,
                mtime=_parse_http_mtime(headers.get("Last-Modified")),
                size=int(headers.get("Content-Length") or 0),
            )
        except ObjectStorageError as exc:
            if " with 404" not in str(exc):
                return None

        dir_prefix = f"{key.rstrip('/')}/"
        try:
            _, _, raw = self._request(
                "GET",
                "",
                query={"list-type": "2", "prefix": dir_prefix, "max-keys": "1"},
            )
        except ObjectStorageError:
            return None
        entries, is_truncated, _token = self._parse_list_response(raw, base_relative=normalized, recursive=True)
        del is_truncated, _token
        return SharedFileEntry(path=normalized, is_file=False, is_dir=True, mtime=0.0, size=0) if entries else None

    def list_entries(self, relative_path: str, *, recursive: bool = False) -> list[SharedFileEntry]:
        normalized = _normalize_relative_path(relative_path)
        prefix_key = self._object_key(normalized)
        if prefix_key:
            prefix_key = f"{prefix_key.rstrip('/')}/"

        entries: list[SharedFileEntry] = []
        token = ""
        while True:
            query = {"list-type": "2", "prefix": prefix_key}
            if not recursive:
                query["delimiter"] = "/"
            if token:
                query["continuation-token"] = token
            try:
                _, _, raw = self._request("GET", "", query=query)
            except ObjectStorageError:
                return []
            page_entries, is_truncated, token = self._parse_list_response(
                raw,
                base_relative=normalized,
                recursive=recursive,
            )
            entries.extend(page_entries)
            if not is_truncated or not token:
                break
        return entries

    def read_bytes(self, relative_path: str) -> bytes:
        _, _, raw = self._request("GET", self._object_key(relative_path))
        return raw

    def write_bytes(self, relative_path: str, data: bytes, *, content_type: str | None = None) -> None:
        headers = {"content-type": content_type} if content_type else {}
        self._request("PUT", self._object_key(relative_path), body=data, headers=headers)

    def try_write_bytes_if_absent(
        self,
        relative_path: str,
        data: bytes,
        *,
        content_type: str | None = None,
    ) -> bool:
        headers = {"if-none-match": "*"}
        if content_type:
            headers["content-type"] = content_type
        try:
            self._request("PUT", self._object_key(relative_path), body=data, headers=headers)
        except ObjectStorageError as exc:
            if " with 409" in str(exc) or " with 412" in str(exc):
                return False
            raise
        return True

    def delete_entry(self, relative_path: str) -> None:
        try:
            self._request("DELETE", self._object_key(relative_path))
        except ObjectStorageError:
            return

    def _parse_list_response(
        self,
        raw: bytes,
        *,
        base_relative: str,
        recursive: bool,
    ) -> tuple[list[SharedFileEntry], bool, str]:
        del recursive
        text = raw.decode("utf-8", errors="replace")

        entries: list[SharedFileEntry] = []
        seen: set[str] = set()
        base_path = PurePosixPath(base_relative) if base_relative else PurePosixPath()
        for item in _xml_blocks(text, "Contents"):
            key = (_xml_text(item, "Key") or "").strip()
            relative = self._relative_from_key(key)
            if not relative or relative == base_relative:
                continue
            try:
                rel_to_base = PurePosixPath(relative).relative_to(base_path) if base_relative else PurePosixPath(relative)
            except ValueError:
                continue
            if str(rel_to_base) in {"", "."}:
                continue
            size = int(_xml_text(item, "Size") or 0)
            mtime = _parse_s3_mtime(_xml_text(item, "LastModified"))
            if relative not in seen:
                entries.append(SharedFileEntry(path=relative, is_file=True, is_dir=False, mtime=mtime, size=size))
                seen.add(relative)

        for item in _xml_blocks(text, "CommonPrefixes"):
            key = (_xml_text(item, "Prefix") or "").strip().rstrip("/")
            relative = self._relative_from_key(key)
            if not relative or relative == base_relative:
                continue
            try:
                rel_to_base = PurePosixPath(relative).relative_to(base_path) if base_relative else PurePosixPath(relative)
            except ValueError:
                continue
            if str(rel_to_base) in {"", "."}:
                continue
            if relative not in seen:
                entries.append(SharedFileEntry(path=relative, is_file=False, is_dir=True, mtime=0.0, size=0))
                seen.add(relative)

        is_truncated = (_xml_text(text, "IsTruncated") or "").strip().lower() == "true"
        next_token = (_xml_text(text, "NextContinuationToken") or "").strip()
        return entries, is_truncated, next_token


def _canonical_query_string(query: Mapping[str, str]) -> str:
    pairs = []
    for key, value in sorted((str(k), str(v)) for k, v in query.items()):
        pairs.append(
            f"{urllib.parse.quote(key, safe='-_.~')}={urllib.parse.quote(value, safe='-_.~')}"
        )
    return "&".join(pairs)


def _xml_blocks(text: str, tag: str) -> list[str]:
    pattern = rf"<(?:[A-Za-z0-9_.-]+:)?{re.escape(tag)}\b[^>]*>(.*?)</(?:[A-Za-z0-9_.-]+:)?{re.escape(tag)}>"
    return [match.group(1) for match in re.finditer(pattern, text, flags=re.DOTALL)]


def _xml_text(text: str, tag: str) -> str:
    blocks = _xml_blocks(text, tag)
    return html.unescape(blocks[0].strip()) if blocks else ""


def _aws_sigv4_signing_key(secret_key: str, date_stamp: str, region: str, service: str) -> bytes:
    date_key = hmac.new(f"AWS4{secret_key}".encode("utf-8"), date_stamp.encode("utf-8"), hashlib.sha256).digest()
    region_key = hmac.new(date_key, region.encode("utf-8"), hashlib.sha256).digest()
    service_key = hmac.new(region_key, service.encode("utf-8"), hashlib.sha256).digest()
    return hmac.new(service_key, b"aws4_request", hashlib.sha256).digest()


def _parse_s3_mtime(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _parse_http_mtime(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        from email.utils import parsedate_to_datetime

        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except (TypeError, ValueError):
        return 0.0

def _get_volume() -> modal.Volume:
    global _VOLUME
    if _VOLUME is not None:
        return _VOLUME

    volume_name = os.getenv("ALEITHIA_MODAL_VOLUME_NAME", DEFAULT_MODAL_VOLUME_NAME).strip() or DEFAULT_MODAL_VOLUME_NAME
    environment_name = os.getenv("ALEITHIA_MODAL_ENVIRONMENT", "").strip() or None
    _VOLUME = modal.Volume.from_name(volume_name, environment_name=environment_name, create_if_missing=False)
    return _VOLUME


def _get_accessor() -> SharedDataAccessor:
    backend = os.getenv("ALEITHIA_SHARED_DATA_BACKEND", "modal").strip().lower()
    if backend in {"", "modal", "modal-volume", "volume"}:
        mounted_root = Path(os.getenv("ALEITHIA_MOUNTED_VOLUME_ROOT", DEFAULT_MOUNTED_VOLUME_ROOT))
        if (mounted_root / DEFAULT_RAW_PREFIX).exists() and (mounted_root / DEFAULT_PROCESSED_PREFIX).exists():
            return MountedVolumeAccessor(mounted_root)
        return ModalVolumeAccessor(_get_volume())
    if backend in {"mounted", "mount", "filesystem", "fs"}:
        return MountedVolumeAccessor(os.getenv("ALEITHIA_MOUNTED_VOLUME_ROOT", DEFAULT_MOUNTED_VOLUME_ROOT))
    if backend in {"s3", "r2", "gcs", "object", "object-storage"}:
        return S3ObjectStorageAccessor.from_env()
    raise ValueError(
        "Unsupported ALEITHIA_SHARED_DATA_BACKEND="
        f"{backend!r}; expected 'modal' or 's3'"
    )


def get_shared_data_paths() -> SharedDataPaths:
    global _LAST_LOGGED_LAYOUT

    accessor = _get_accessor()
    paths = SharedDataPaths(
        raw_dir=SharedDataPath(accessor, DEFAULT_RAW_PREFIX),
        processed_dir=SharedDataPath(accessor, DEFAULT_PROCESSED_PREFIX),
    )
    layout = (str(paths.raw_dir), str(paths.processed_dir))
    if layout != _LAST_LOGGED_LAYOUT:
        _LAST_LOGGED_LAYOUT = layout
        logger.info(
            "Resolved Aleithia shared data roots: raw=%s processed=%s",
            paths.raw_dir,
            paths.processed_dir,
        )
    return paths


def get_raw_data_dir() -> SharedDataPath:
    return get_shared_data_paths().raw_dir


def get_processed_data_dir() -> SharedDataPath:
    return get_shared_data_paths().processed_dir


def get_shared_data_dir(*parts: str) -> SharedDataPath:
    return SharedDataPath(_get_accessor(), "/".join(part.strip("/") for part in parts if part))


def get_cache_data_dir() -> SharedDataPath:
    return get_shared_data_dir("cache")


def get_dedup_data_dir() -> SharedDataPath:
    return get_shared_data_dir("dedup")


def local_filesystem_path(path: Path | SharedDataPath) -> Path | None:
    """Return a concrete filesystem path when shared data is mounted locally."""
    if isinstance(path, Path):
        return path

    root = getattr(path.accessor, "root", None)
    if root is not None:
        return Path(root) / path.relative_path

    display_path = str(path)
    if display_path.startswith("/"):
        return Path(display_path)
    return None


@contextmanager
def shared_data_lock(
    lock_path: Path | SharedDataPath,
    *,
    timeout_seconds: float = 30.0,
    poll_seconds: float = 0.1,
):
    """Acquire an advisory lock for local mounts or object-storage lock keys."""
    local_path = local_filesystem_path(lock_path)
    if local_path is not None:
        import fcntl

        local_path.parent.mkdir(parents=True, exist_ok=True)
        with open(local_path, "w") as lock_fd:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
        return

    if isinstance(lock_path, SharedDataPath):
        try_create = getattr(lock_path.accessor, "try_write_bytes_if_absent", None)
        delete_entry = getattr(lock_path.accessor, "delete_entry", None)
        if callable(try_create) and callable(delete_entry):
            owner = str(uuid.uuid4())
            payload = json.dumps(
                {
                    "owner": owner,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                separators=(",", ":"),
            ).encode("utf-8")
            deadline = time.monotonic() + timeout_seconds
            acquired = False
            while time.monotonic() <= deadline:
                if try_create(lock_path.relative_path, payload, content_type="application/json"):
                    acquired = True
                    break
                time.sleep(poll_seconds)
            if not acquired:
                raise TimeoutError(f"Timed out acquiring shared data lock: {lock_path}")
            try:
                yield
            finally:
                delete_entry(lock_path.relative_path)
            return

    yield


def _relative_entry_path(directory: SharedDataPath, entry_path: str) -> PurePosixPath | None:
    candidate = PurePosixPath(entry_path)
    if directory.relative_path:
        try:
            relative = candidate.relative_to(PurePosixPath(directory.relative_path))
        except ValueError:
            return None
    else:
        relative = candidate
    return None if str(relative) in {"", "."} else relative


def _shared_entries(
    directory: SharedDataPath,
    *,
    recursive: bool,
    pattern: str | None = None,
    files_only: bool | None = None,
) -> list[SharedFileEntry]:
    entries = directory.accessor.list_entries(directory.relative_path, recursive=recursive)
    matched: list[SharedFileEntry] = []
    for entry in entries:
        relative = _relative_entry_path(directory, entry.path)
        if relative is None:
            continue
        if not recursive and len(relative.parts) != 1:
            continue
        if files_only is True and not entry.is_file:
            continue
        if files_only is False and not entry.is_dir:
            continue
        if pattern is not None and not fnmatch.fnmatch(PurePosixPath(entry.path).name, pattern):
            continue
        matched.append(entry)
    return matched


def _glob_paths(directory: SharedDataPath, pattern: str, *, recursive: bool) -> list[SharedDataPath]:
    entries = _shared_entries(directory, recursive=recursive, pattern=pattern)
    return sorted(SharedDataPath(directory.accessor, entry.path) for entry in entries)


def _safe_mtime(path: Path | SharedDataPath) -> float:
    try:
        return float(path.stat().st_mtime)
    except OSError:
        return 0.0


def safe_mtime(path: Path | SharedDataPath) -> float:
    return _safe_mtime(path)


def read_file_bytes(path: Path | SharedDataPath, default: bytes | None = None) -> bytes | None:
    if isinstance(path, SharedDataPath):
        try:
            return path.read_bytes()
        except Exception:
            return default

    if not path.exists() or not path.is_file():
        return default
    try:
        return path.read_bytes()
    except OSError:
        return default


def write_file_bytes(path: Path | SharedDataPath, data: bytes, *, content_type: str | None = None) -> None:
    if isinstance(path, SharedDataPath):
        path.write_bytes(data, content_type=content_type)
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def load_json_file(path: Path | SharedDataPath, default: Any = None) -> Any:
    raw_bytes = read_file_bytes(path, default=None)
    if raw_bytes is None:
        return default
    try:
        return json.loads(raw_bytes.decode("utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return default


def write_json_file(path: Path | SharedDataPath, data: Any, *, indent: int | None = 2) -> None:
    raw = json.dumps(data, indent=indent, default=str).encode("utf-8")
    write_file_bytes(path, raw, content_type="application/json")


def load_processed_json(*parts: str, default: Any = None) -> Any:
    return load_json_file(get_processed_data_dir().joinpath(*parts), default=default)


def load_first_existing_json(paths: Iterable[Path | SharedDataPath], default: Any = None) -> Any:
    for path in paths:
        parsed = load_json_file(path, default=None)
        if parsed is not None:
            return parsed
    return default


def load_first_matching_json(
    paths: Iterable[Path | SharedDataPath],
    *,
    predicate: Callable[[Any], bool],
    default: Any = None,
) -> Any:
    for path in paths:
        parsed = load_json_file(path, default=None)
        if parsed is not None and predicate(parsed):
            return parsed
    return default


def load_processed_json_directory(
    *parts: str,
    stem_suffix_to_strip: str = "",
) -> dict[str, Any]:
    directory = get_processed_data_dir().joinpath(*parts)
    loaded: dict[str, Any] = {}
    if isinstance(directory, SharedDataPath):
        for entry in sorted(_shared_entries(directory, recursive=False, pattern="*.json", files_only=True), key=lambda item: item.path):
            path = SharedDataPath(directory.accessor, entry.path)
            parsed = load_json_file(path, default=None)
            if parsed is None:
                continue
            key = path.stem
            if stem_suffix_to_strip:
                key = key.removesuffix(stem_suffix_to_strip)
            loaded[key] = parsed
        return loaded

    if not directory.exists():
        return {}

    for path in sorted(directory.iterdir()):
        if not path.is_file() or path.suffix != ".json":
            continue
        parsed = load_json_file(path, default=None)
        if parsed is None:
            continue
        key = path.stem
        if stem_suffix_to_strip:
            key = key.removesuffix(stem_suffix_to_strip)
        loaded[key] = parsed
    return loaded


def find_latest_processed_json_file(*parts: str, pattern: str = "*.json") -> Path | SharedDataPath | None:
    return find_latest_json_file(get_processed_data_dir().joinpath(*parts), pattern=pattern)


def iter_json_files(
    directory: Path | SharedDataPath,
    *,
    recursive: bool = True,
    sort_key: Callable[[Path | SharedDataPath], Any] | None = None,
    reverse: bool = True,
) -> list[Path | SharedDataPath]:
    if isinstance(directory, SharedDataPath):
        entries = _shared_entries(directory, recursive=recursive, pattern="*.json", files_only=True)
        files = [SharedDataPath(directory.accessor, entry.path) for entry in entries]
    else:
        if not directory.exists():
            return []
        iterator = directory.rglob("*.json") if recursive else directory.glob("*.json")
        files = [path for path in iterator if path.is_file()]
    return sorted(files, key=sort_key, reverse=reverse) if sort_key is not None else sorted(files, reverse=reverse)


def _limited_shared_json_files(
    directory: SharedDataPath,
    *,
    limit: int,
    recursive: bool,
    reverse: bool,
) -> list[SharedDataPath]:
    """Collect up to ``limit`` JSON files without recursively listing the full tree."""
    if limit <= 0:
        return []

    files: list[SharedDataPath] = []

    def _visit(current: SharedDataPath) -> None:
        if len(files) >= limit:
            return

        entries = sorted(
            current.accessor.list_entries(current.relative_path, recursive=False),
            key=lambda entry: entry.path,
            reverse=reverse,
        )
        for entry in entries:
            if len(files) >= limit:
                break
            if entry.is_file:
                if fnmatch.fnmatch(PurePosixPath(entry.path).name, "*.json"):
                    files.append(SharedDataPath(current.accessor, entry.path))
                continue
            if recursive and entry.is_dir:
                _visit(SharedDataPath(current.accessor, entry.path))

    _visit(directory)
    return files


def iter_files(
    directory: Path | SharedDataPath,
    *,
    recursive: bool = True,
    pattern: str = "*",
    reverse: bool = True,
) -> list[Path | SharedDataPath]:
    if isinstance(directory, SharedDataPath):
        entries = _shared_entries(directory, recursive=recursive, pattern=pattern, files_only=True)
        listed = [SharedDataPath(directory.accessor, entry.path) for entry in entries]
        return sorted(
            listed,
            key=lambda path: (
                next(entry.mtime for entry in entries if entry.path == path.relative_path),
                str(path),
            ),
            reverse=reverse,
        )
    else:
        if not directory.exists():
            return []
        iterator = directory.rglob(pattern) if recursive else directory.glob(pattern)
        listed = [path for path in iterator if path.is_file()]
    return sorted(listed, key=lambda path: (safe_mtime(path), str(path)), reverse=reverse)


def count_files(directory: Path | SharedDataPath, *, pattern: str = "*", recursive: bool = True) -> int:
    if isinstance(directory, SharedDataPath):
        return len(_shared_entries(directory, recursive=recursive, pattern=pattern, files_only=True))
    return len(iter_files(directory, recursive=recursive, pattern=pattern))


def find_latest_json_file(directory: Path | SharedDataPath, pattern: str = "*.json") -> Path | SharedDataPath | None:
    if isinstance(directory, SharedDataPath):
        candidates = _shared_entries(directory, recursive=False, pattern=pattern, files_only=True)
        if not candidates:
            return None
        latest = max(candidates, key=lambda entry: (entry.mtime, PurePosixPath(entry.path).name))
        return SharedDataPath(directory.accessor, latest.path)

    candidates = [path for path in directory.glob(pattern) if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: (_safe_mtime(path), path.name))


def load_json_docs_from_paths(
    paths: Iterable[Path | SharedDataPath],
    *,
    limit: int | None = None,
    on_error: Callable[[Path | SharedDataPath, Exception], None] | None = None,
) -> list[dict]:
    docs: list[dict] = []
    for json_file in paths:
        try:
            raw_bytes = read_file_bytes(json_file, default=None)
            if raw_bytes is None:
                continue
            parsed = json.loads(raw_bytes.decode("utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
            if on_error is not None:
                on_error(json_file, exc)
            continue
        if not isinstance(parsed, dict):
            continue
        docs.append(parsed)
        if limit is not None and len(docs) >= limit:
            break
    return docs


def load_json_docs_from_directory(
    directory: Path | SharedDataPath,
    *,
    limit: int | None = None,
    recursive: bool = True,
    sort_key: Callable[[Path | SharedDataPath], Any] | None = None,
    reverse: bool = True,
    on_error: Callable[[Path | SharedDataPath, Exception], None] | None = None,
) -> list[dict]:
    if isinstance(directory, SharedDataPath) and limit is not None and sort_key is None:
        paths = _limited_shared_json_files(
            directory,
            limit=limit,
            recursive=recursive,
            reverse=reverse,
        )
    else:
        paths = iter_json_files(directory, recursive=recursive, sort_key=sort_key, reverse=reverse)

    return load_json_docs_from_paths(
        paths,
        limit=limit,
        on_error=on_error,
    )


def scan_source_directories(
    source_dirs: Mapping[str, Path | SharedDataPath],
    *,
    neighborhood_sample_limit: int = 100,
    neighborhood_getter: Callable[[dict], str | None] | None = None,
) -> dict[str, dict[str, object]]:
    if neighborhood_getter is None:
        neighborhood_getter = lambda doc: doc.get("geo", {}).get("neighborhood") or None

    stats: dict[str, dict[str, object]] = {}
    for source, source_dir in source_dirs.items():
        neighborhoods: set[str] = set()
        if isinstance(source_dir, SharedDataPath):
            entries = _shared_entries(source_dir, recursive=True, pattern="*.json", files_only=True)
            latest_entry = max(entries, key=lambda entry: (entry.mtime, entry.path), default=None)
            for entry in entries[:neighborhood_sample_limit]:
                parsed = load_json_file(SharedDataPath(source_dir.accessor, entry.path), default=None)
                if not isinstance(parsed, dict):
                    continue
                neighborhood = neighborhood_getter(parsed)
                if neighborhood:
                    neighborhoods.add(neighborhood)

            stats[source] = {
                "doc_count": len(entries),
                "active": bool(entries),
                "last_update": (
                    datetime.fromtimestamp(latest_entry.mtime, tz=timezone.utc).isoformat()
                    if latest_entry is not None
                    else None
                ),
                "neighborhoods_covered": neighborhoods,
            }
            continue

        json_files = iter_json_files(source_dir)
        latest = max(json_files, key=_safe_mtime, default=None)
        for json_file in json_files[:neighborhood_sample_limit]:
            parsed = load_json_file(json_file, default=None)
            if not isinstance(parsed, dict):
                continue
            neighborhood = neighborhood_getter(parsed)
            if neighborhood:
                neighborhoods.add(neighborhood)

        stats[source] = {
            "doc_count": len(json_files),
            "active": bool(json_files),
            "last_update": (
                datetime.fromtimestamp(_safe_mtime(latest), tz=timezone.utc).isoformat()
                if latest is not None
                else None
            ),
            "neighborhoods_covered": neighborhoods,
        }
    return stats


def iter_raw_json_files(source: str) -> list[Path | SharedDataPath]:
    source_dir = get_raw_data_dir() / source

    if isinstance(source_dir, SharedDataPath):
        entries = _shared_entries(source_dir, recursive=True, pattern="*.json", files_only=True)
        entries.sort(
            key=lambda entry: (
                str(_relative_entry_path(source_dir, entry.path).parent),
                entry.mtime,
                entry.path,
            ),
            reverse=True,
        )
        return [SharedDataPath(source_dir.accessor, entry.path) for entry in entries]

    def _sort_key(path: Path | SharedDataPath) -> tuple[str, float]:
        if isinstance(path, SharedDataPath):
            rel_parent = str(path.relative_to(source_dir).parent)
        else:
            try:
                rel_parent = str(path.relative_to(source_dir).parent)
            except ValueError:
                rel_parent = str(path.parent)
        mtime = _safe_mtime(path)
        return (rel_parent, mtime)

    return iter_json_files(source_dir, sort_key=_sort_key, reverse=True)


def count_raw_json_files(source: str) -> int:
    return len(iter_raw_json_files(source))


def load_raw_docs(source: str, limit: int | None = None) -> list[dict]:
    return load_json_docs_from_paths(iter_raw_json_files(source), limit=limit)


def get_raw_source_stats(sources: Iterable[str]) -> dict[str, dict[str, object]]:
    stats = scan_source_directories({source: get_raw_data_dir() / source for source in sources})
    return {
        source: {
            "doc_count": data["doc_count"],
            "active": data["active"],
            "last_update": data["last_update"],
        }
        for source, data in stats.items()
    }
