#!/usr/bin/env python3
"""Dry-run or apply safe legacy costing source normalization."""

import argparse
import json
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from utils.factory_service import FactoryService
from utils.legacy_costing_migration import ensure_canonical_costing_sources
from utils.profile_store import ProfileDataStore


def main(argv=None):
    parser = argparse.ArgumentParser(description="نرمال‌سازی امن منابع قدیمی محاسبه هزینه")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--factory-id")
    target.add_argument("--all-factories", action="store_true")
    parser.add_argument("--write", action="store_true", help="ثبت فایل‌ها؛ حالت پیش‌فرض dry run است")
    parser.add_argument("--profile-file", type=Path,
                        default=Path(os.environ.get("APP_DATA_FILE", PROJECT_ROOT / "instance" / "app_data.json")))
    parser.add_argument("--data-root", type=Path, default=PROJECT_ROOT / "Data")
    args = parser.parse_args(argv)

    service = FactoryService(ProfileDataStore(args.profile_file))
    factory_ids = ([factory["id"] for factory in service.list_factories()]
                   if args.all_factories else [args.factory_id])
    reports = []
    exit_code = 0
    for factory_id in factory_ids:
        try:
            reports.append(ensure_canonical_costing_sources(
                service, factory_id, args.data_root, persist=args.write,
            ))
        except ValueError as exc:
            reports.append({"factory_id": factory_id, "actions": [], "error": str(exc)})
            exit_code = 2
    print(json.dumps({"mode": "WRITE" if args.write else "DRY_RUN", "factories": reports},
                     ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
