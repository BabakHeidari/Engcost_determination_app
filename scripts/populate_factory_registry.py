"""Populate the canonical Profile factory registry from operational data."""
import argparse
from pathlib import Path

from scripts.bootstrap_it_admin import store_path
from utils.factory_registry import DEFAULT_DATA_ROOT, populate_factory_registry
from utils.profile_store import ProfileDataStore


def main():
    parser = argparse.ArgumentParser(description="Discover and import canonical factory identities")
    parser.add_argument("path", nargs="?", type=Path, default=store_path())
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    args = parser.parse_args()
    result = populate_factory_registry(ProfileDataStore(args.path), args.data_root)
    print(f"Discovered {result['discovered']} factories; created {result['created_count']} canonical records.")


if __name__ == "__main__":
    main()
