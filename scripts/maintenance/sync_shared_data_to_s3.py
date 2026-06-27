#!/usr/bin/env python3
"""Copy Aleithia shared runtime data from the Modal volume to object storage.

The command is dry-run by default. Pass --write to upload objects to the
S3-compatible backend configured by ALEITHIA_OBJECT_STORAGE_*.
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.shared_data import (  # noqa: E402
    DEFAULT_MODAL_VOLUME_NAME,
    MountedVolumeAccessor,
    ModalVolumeAccessor,
    S3ObjectStorageAccessor,
    SharedDataAccessor,
    SharedFileEntry,
    _get_volume,
)

DEFAULT_PREFIXES = ("raw", "processed", "cache", "dedup")


def _is_syncable_file(entry: SharedFileEntry) -> bool:
    return entry.is_file and not entry.path.endswith(".lock")


@dataclass
class PrefixSyncResult:
    prefix: str
    discovered: int = 0
    copied: int = 0
    skipped_existing: int = 0
    bytes_discovered: int = 0
    bytes_copied: int = 0


def iter_source_files(accessor: SharedDataAccessor, prefix: str) -> list[SharedFileEntry]:
    direct = accessor.get_entry(prefix)
    if direct is not None and _is_syncable_file(direct):
        return [direct]
    entries = accessor.list_entries(prefix, recursive=True)
    return sorted(
        (entry for entry in entries if _is_syncable_file(entry)),
        key=lambda entry: entry.path,
    )


def list_existing_destination_files(accessor: SharedDataAccessor, prefix: str) -> set[str]:
    existing: set[str] = set()
    direct = accessor.get_entry(prefix)
    if direct is not None and direct.is_file:
        existing.add(direct.path)
    for entry in accessor.list_entries(prefix, recursive=True):
        if entry.is_file:
            existing.add(entry.path)
    return existing


def sync_prefix(
    *,
    source: SharedDataAccessor,
    destination: SharedDataAccessor,
    prefix: str,
    write: bool,
    overwrite: bool,
    limit: int | None = None,
    progress_every: int = 500,
    retries: int = 3,
) -> PrefixSyncResult:
    result = PrefixSyncResult(prefix=prefix)
    existing_destination_files = set() if overwrite or not write else list_existing_destination_files(destination, prefix)
    for entry in iter_source_files(source, prefix):
        if limit is not None and result.discovered >= limit:
            break
        result.discovered += 1
        result.bytes_discovered += int(entry.size or 0)

        if not write:
            continue

        if not overwrite and entry.path in existing_destination_files:
            result.skipped_existing += 1
            continue

        payload = source.read_bytes(entry.path)
        content_type = "application/json" if entry.path.endswith(".json") else None
        for attempt in range(max(1, retries)):
            try:
                destination.write_bytes(entry.path, payload, content_type=content_type)
                break
            except Exception as exc:
                if attempt >= max(1, retries) - 1:
                    raise
                delay_seconds = min(2 ** attempt, 5)
                print(
                    f"{prefix}: retrying {entry.path} after upload error "
                    f"({type(exc).__name__}: {exc}); attempt {attempt + 2}/{max(1, retries)}",
                    flush=True,
                )
                time.sleep(delay_seconds)
        result.copied += 1
        result.bytes_copied += len(payload)
        existing_destination_files.add(entry.path)

        if progress_every > 0 and result.discovered % progress_every == 0:
            print(
                f"{prefix}: processed {result.discovered} files, "
                f"copied {result.copied}, skipped {result.skipped_existing}",
                flush=True,
            )
    return result


def _format_bytes(value: int) -> str:
    units = ("B", "KB", "MB", "GB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.1f} {unit}" if unit != "B" else f"{int(amount)} B"
        amount /= 1024
    return f"{value} B"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dry-run or copy Modal Volume shared runtime data into the configured S3-compatible backend.",
    )
    parser.add_argument(
        "--prefix",
        action="append",
        dest="prefixes",
        help="Top-level shared-data prefix to copy. Repeatable. Defaults to raw, processed, cache, dedup.",
    )
    parser.add_argument("--write", action="store_true", help="Actually upload destination objects.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite destination objects that already exist.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum files to process per prefix.")
    parser.add_argument("--progress-every", type=int, default=500, help="Print copy progress every N source files.")
    parser.add_argument("--retries", type=int, default=3, help="Upload retry attempts per object.")
    parser.add_argument(
        "--source-root",
        default="",
        help="Read source files from a local shared-data root instead of the Modal Volume.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    prefixes = tuple(args.prefixes or DEFAULT_PREFIXES)
    source_root = str(args.source_root or "").strip()
    source = MountedVolumeAccessor(Path(source_root).expanduser().resolve()) if source_root else ModalVolumeAccessor(_get_volume())
    destination = S3ObjectStorageAccessor.from_env()

    action = "copy" if args.write else "dry-run"
    print(f"Shared-data S3 sync ({action})", flush=True)
    print(f"Source: {source.display_uri('') if source_root else f'modal://{DEFAULT_MODAL_VOLUME_NAME}'}", flush=True)
    print(f"Destination: {destination.display_uri('')}", flush=True)
    if not args.write:
        print("Pass --write to upload missing destination objects.", flush=True)

    totals = PrefixSyncResult(prefix="total")
    for prefix in prefixes:
        result = sync_prefix(
            source=source,
            destination=destination,
            prefix=prefix,
            write=bool(args.write),
            overwrite=bool(args.overwrite),
            limit=args.limit,
            progress_every=args.progress_every,
            retries=args.retries,
        )
        totals.discovered += result.discovered
        totals.copied += result.copied
        totals.skipped_existing += result.skipped_existing
        totals.bytes_discovered += result.bytes_discovered
        totals.bytes_copied += result.bytes_copied
        print(
            f"{prefix}: {result.discovered} files discovered"
            f", {result.copied} copied"
            f", {result.skipped_existing} skipped"
            f", {_format_bytes(result.bytes_discovered)} discovered"
            f", {_format_bytes(result.bytes_copied)} uploaded",
            flush=True,
        )

    print(
        f"total: {totals.discovered} files discovered"
        f", {totals.copied} copied"
        f", {totals.skipped_existing} skipped"
        f", {_format_bytes(totals.bytes_discovered)} discovered"
        f", {_format_bytes(totals.bytes_copied)} uploaded",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
