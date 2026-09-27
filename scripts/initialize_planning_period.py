#!/usr/bin/env python3
"""Discover a draft or approve the INITIAL costing period explicitly."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.factory_service import FactoryService
from utils.planning_periods import approve_initial_period, discover_initial_period
from utils.profile_store import ProfileDataStore


def parser():
    command = argparse.ArgumentParser(description="کشف و تأیید صریح نخستین دوره برنامه‌ریزی")
    command.add_argument("--profile-file", required=True, type=Path)
    command.add_argument("--binding-file", required=True, type=Path)
    subcommands = command.add_subparsers(dest="action", required=True)
    discover = subcommands.add_parser("discover", help="ایجاد DRAFT غیرفعال")
    discover.add_argument("--factory-id", required=True)
    discover.add_argument("--data-root", required=True, type=Path)
    discover.add_argument("--write", action="store_true")
    approve = subcommands.add_parser("approve", help="تأیید DRAFT توسط مدیر ارشد")
    approve.add_argument("--factory-id", required=True)
    approve.add_argument("--actor-id", required=True)
    approve.add_argument("--end", required=True)
    approve.add_argument("--source", action="append", required=True, dest="sources")
    approve.add_argument("--write", action="store_true")
    return command


def main(argv=None):
    args = parser().parse_args(argv)
    store = ProfileDataStore(args.profile_file)
    if args.action == "discover":
        result = discover_initial_period(FactoryService(store), args.factory_id, args.data_root,
                                         args.binding_file, persist=args.write)
    else:
        result = approve_initial_period(store, args.binding_file, args.factory_id, args.actor_id,
                                        args.end, args.sources, persist=args.write)
    import json
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("PERSISTED" if args.write else "VALID (dry-run; use --write to persist)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
