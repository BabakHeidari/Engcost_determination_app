#!/usr/bin/env python3
"""Preview or persist the Factory Configuration V2 migration."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from utils.auth import get_profile_store
from utils.factory_configuration import ensure_factory_configuration_v2
from utils.factory_service import FactoryService

parser = argparse.ArgumentParser()
parser.add_argument("--all-factories", action="store_true", required=True)
parser.add_argument("--write", action="store_true", help="persist changes (default is dry-run)")
args = parser.parse_args()
service = FactoryService(get_profile_store())
results = []
for factory in service.list_factories():
    try:
        result = ensure_factory_configuration_v2(factory["id"], service.operational_key(factory), persist=args.write)
        results.append({"factory_id": factory["id"], "status": result["status"]})
    except (OSError, ValueError) as exc:
        results.append({"factory_id": factory["id"], "status": "FAILED", "error": str(exc)})
print(json.dumps({"write": args.write, "results": results}, ensure_ascii=False, indent=2))
raise SystemExit(1 if any(item["status"] == "FAILED" for item in results) else 0)
