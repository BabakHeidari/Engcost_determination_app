#!/usr/bin/env python3
"""Read-only diagnostic for canonical factory and runtime period integration."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.factory_service import FactoryService
from utils.planning_periods import validate_costing_period
from utils.profile_store import ProfileDataStore, ProfileStoreError


def main(argv=None):
    parser = argparse.ArgumentParser(description="اعتبارسنجی فقط‌خواندنی دوره محاسبه هزینه")
    parser.add_argument("--profile-file", required=True, type=Path)
    parser.add_argument("--binding-file", required=True, type=Path)
    parser.add_argument("--factory-id", required=True, help="canonical ID یا operational key برای تشخیص")
    parser.add_argument("--period-id", default="")
    args = parser.parse_args(argv)
    try:
        result = validate_costing_period(FactoryService(ProfileDataStore(args.profile_file)),
                                         args.binding_file, args.factory_id, args.period_id)
    except ProfileStoreError:
        result = {"factory_input": args.factory_id, "canonical_id": None,
                  "factory_resolution": "REGISTRY_UNAVAILABLE",
                  "binding_file": str(args.binding_file),
                  "binding_file_exists": args.binding_file.is_file(),
                  "period_found": False, "usable_by_costing": False,
                  "reason": "Canonical profile registry is not installed or readable."}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["usable_by_costing"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
