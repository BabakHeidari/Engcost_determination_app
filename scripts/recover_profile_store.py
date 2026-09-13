"""Restore canonical Profile JSON from the newest valid bounded backup."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from utils.profile_store import ProfileDataStore, ProfileStoreError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate backups and restore the newest valid Profile JSON snapshot."
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="Canonical app_data.json path (defaults to APP_DATA_FILE or instance/app_data.json)",
    )
    args = parser.parse_args(argv)
    default_path = Path(__file__).resolve().parents[1] / "instance" / "app_data.json"
    path = Path(args.path or os.environ.get("APP_DATA_FILE", default_path))
    store = ProfileDataStore(path)
    try:
        result = store.restore_latest_valid_backup()
    except ProfileStoreError as exc:
        parser.exit(1, f"Recovery failed: {exc}\n")
    print(f"Restored revision {result['revision']} from {result['source_backup']}")
    if result["corrupt_copy"]:
        print(f"Preserved prior canonical bytes at {result['corrupt_copy']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
