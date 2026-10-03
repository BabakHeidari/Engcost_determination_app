#!/usr/bin/env python3
"""Print the active period's source metadata versus CostInputLoader paths."""

import argparse
import json
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from utils.costing_engine import CostInputError, CostInputLoader, ProductIdentity
from utils.factory_service import FactoryService
from utils.legacy_costing_migration import ensure_canonical_costing_sources
from utils.profile_store import ProfileDataStore


def main(argv=None):
    parser = argparse.ArgumentParser(description="تشخیص فقط‌خواندنی منابع محاسبه هزینه")
    parser.add_argument("--factory-id", required=True, help="شناسه canonical کارخانه")
    parser.add_argument("--profile-file", type=Path,
                        default=Path(os.environ.get("APP_DATA_FILE", PROJECT_ROOT / "instance" / "app_data.json")))
    parser.add_argument("--data-root", type=Path, default=PROJECT_ROOT / "Data")
    parser.add_argument("--binding-file", type=Path,
                        default=PROJECT_ROOT / "instance" / "costing_period_bindings.json")
    parser.add_argument("--period-id", default="")
    parser.add_argument("--category")
    parser.add_argument("--subcategory")
    parser.add_argument("--product")
    args = parser.parse_args(argv)
    identity_parts = (args.category, args.subcategory, args.product)
    if any(identity_parts) and not all(identity_parts):
        parser.error("--category, --subcategory and --product must be supplied together")
    identity = ProductIdentity(args.factory_id, *identity_parts) if all(identity_parts) else None
    loader = CostInputLoader(
        FactoryService(ProfileDataStore(args.profile_file)),
        data_root=args.data_root,
        period_bindings_path=args.binding_file,
    )
    try:
        result = loader.diagnose_sources(args.factory_id, args.period_id, identity)
        recovery = ensure_canonical_costing_sources(
            loader.factory_service, args.factory_id, args.data_root, identity, persist=False,
        )
        actions = {item["source_name"]: item for item in recovery["actions"]}
        for resolution in result["source_resolutions"]:
            action = actions.get(resolution["source_name"])
            if action:
                resolution["legacy_recovery_status"] = action["status"]
                if action.get("legacy_source"):
                    resolution["legacy_source"] = action["legacy_source"]
        result["legacy_recovery"] = recovery
    except CostInputError as exc:
        result = {"state": exc.state.value, "error": exc.detail.__dict__}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result["missing_sources"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
