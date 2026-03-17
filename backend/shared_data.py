"""Shared filesystem helpers for backend access to raw and processed data."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_ROOT.parent

_LAST_LOGGED_LAYOUT: tuple[str, str] | None = None


@dataclass(frozen=True)
class SharedDataPaths:
    raw_dir: Path
    processed_dir: Path


def _resolve_path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def _resolve_dir(explicit_env: str, suffix: str) -> Path:
    explicit_value = os.getenv(explicit_env, "").strip()
    if explicit_value:
        return _resolve_path(explicit_value)

    data_root = os.getenv("ALEITHIA_DATA_ROOT", "").strip()
    if data_root:
        return _resolve_path(data_root) / suffix

    return (REPO_ROOT / "data" / suffix).resolve()


def get_shared_data_paths() -> SharedDataPaths:
    global _LAST_LOGGED_LAYOUT

    paths = SharedDataPaths(
        raw_dir=_resolve_dir("ALEITHIA_RAW_DATA_DIR", "raw"),
        processed_dir=_resolve_dir("ALEITHIA_PROCESSED_DATA_DIR", "processed"),
    )
    layout = (str(paths.raw_dir), str(paths.processed_dir))
    if layout != _LAST_LOGGED_LAYOUT:
        _LAST_LOGGED_LAYOUT = layout
        logger.info(
            "Resolved Aleithia shared data directories: raw=%s processed=%s",
            paths.raw_dir,
            paths.processed_dir,
        )
        if not paths.raw_dir.exists():
            logger.warning("Aleithia raw data directory does not exist: %s", paths.raw_dir)
        if not paths.processed_dir.exists():
            logger.warning("Aleithia processed data directory does not exist: %s", paths.processed_dir)
    return paths


def get_raw_data_dir() -> Path:
    return get_shared_data_paths().raw_dir


def get_processed_data_dir() -> Path:
    return get_shared_data_paths().processed_dir


def _safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def safe_mtime(path: Path) -> float:
    return _safe_mtime(path)


def load_json_file(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return default


def load_processed_json(*parts: str, default: Any = None) -> Any:
    return load_json_file(get_processed_data_dir().joinpath(*parts), default=default)


def load_first_existing_json(paths: Iterable[Path], default: Any = None) -> Any:
    for path in paths:
        if not path.exists():
            continue
        parsed = load_json_file(path, default=None)
        if parsed is not None:
            return parsed
    return default


def load_first_matching_json(
    paths: Iterable[Path],
    *,
    predicate: Callable[[Any], bool],
    default: Any = None,
) -> Any:
    for path in paths:
        if not path.exists():
            continue
        parsed = load_json_file(path, default=None)
        if parsed is not None and predicate(parsed):
            return parsed
    return default


def load_processed_json_directory(
    *parts: str,
    stem_suffix_to_strip: str = "",
) -> dict[str, Any]:
    directory = get_processed_data_dir().joinpath(*parts)
    if not directory.exists():
        return {}

    loaded: dict[str, Any] = {}
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


def find_latest_processed_json_file(*parts: str, pattern: str = "*.json") -> Path | None:
    return find_latest_json_file(get_processed_data_dir().joinpath(*parts), pattern=pattern)


def iter_json_files(
    directory: Path,
    *,
    recursive: bool = True,
    sort_key: Callable[[Path], Any] | None = None,
    reverse: bool = True,
) -> list[Path]:
    if not directory.exists():
        return []

    iterator = directory.rglob("*.json") if recursive else directory.glob("*.json")
    files = [path for path in iterator if path.is_file()]
    return sorted(files, key=sort_key, reverse=reverse) if sort_key is not None else sorted(files, reverse=reverse)


def find_latest_json_file(directory: Path, pattern: str = "*.json") -> Path | None:
    candidates = [path for path in directory.glob(pattern) if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: (_safe_mtime(path), path.name))


def load_json_docs_from_paths(
    paths: Iterable[Path],
    *,
    limit: int | None = None,
    on_error: Callable[[Path, Exception], None] | None = None,
) -> list[dict]:
    docs: list[dict] = []
    for json_file in paths:
        try:
            parsed = json.loads(json_file.read_text())
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
    directory: Path,
    *,
    limit: int | None = None,
    recursive: bool = True,
    sort_key: Callable[[Path], Any] | None = None,
    reverse: bool = True,
    on_error: Callable[[Path, Exception], None] | None = None,
) -> list[dict]:
    return load_json_docs_from_paths(
        iter_json_files(directory, recursive=recursive, sort_key=sort_key, reverse=reverse),
        limit=limit,
        on_error=on_error,
    )


def scan_source_directories(
    source_dirs: Mapping[str, Path],
    *,
    neighborhood_sample_limit: int = 100,
    neighborhood_getter: Callable[[dict], str | None] | None = None,
) -> dict[str, dict[str, object]]:
    if neighborhood_getter is None:
        neighborhood_getter = lambda doc: doc.get("geo", {}).get("neighborhood") or None

    stats: dict[str, dict[str, object]] = {}
    for source, source_dir in source_dirs.items():
        json_files = iter_json_files(source_dir)
        latest = max(json_files, key=_safe_mtime, default=None)
        neighborhoods: set[str] = set()
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


def iter_raw_json_files(source: str) -> list[Path]:
    source_dir = get_raw_data_dir() / source

    def _sort_key(path: Path) -> tuple[str, float]:
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
