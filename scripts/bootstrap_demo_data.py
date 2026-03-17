#!/usr/bin/env python3
"""Copy tracked demo fixtures into the local runtime data tree."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = PROJECT_ROOT / "fixtures" / "demo_data"


def resolve_data_root() -> Path:
    from os import environ

    data_root = environ.get("ALEITHIA_DATA_ROOT", "").strip()
    if data_root:
        return Path(data_root).expanduser().resolve()
    return (PROJECT_ROOT / "data").resolve()


def copy_tree(src_root: Path, dest_root: Path, force: bool) -> tuple[int, int]:
    copied = 0
    skipped = 0

    for src_path in src_root.rglob("*"):
        if not src_path.is_file():
            continue
        relative = src_path.relative_to(src_root)
        dest_path = dest_root / relative
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        if dest_path.exists() and not force:
            skipped += 1
            continue
        shutil.copy2(src_path, dest_path)
        copied += 1

    return copied, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite existing runtime files with fixture files",
    )
    args = parser.parse_args()

    data_root = resolve_data_root()
    copied, skipped = copy_tree(FIXTURE_ROOT, data_root, force=args.force)

    print(f"Bootstrapped demo fixtures into {data_root}")
    print(f"Copied {copied} files")
    if skipped:
        print(f"Skipped {skipped} existing files (use --force to overwrite)")


if __name__ == "__main__":
    main()
