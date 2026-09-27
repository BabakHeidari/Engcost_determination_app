#!/usr/bin/env python3
"""Validate or explicitly persist one owner-approved legacy-source binding."""

import argparse
from datetime import date
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.costing_engine import FACTORY_POOL_IDS
from utils.profile_store import ProfileDataStore


KNOWN_SOURCES = {"materials", "bom", "weights", "predictions", *(f"pool:{item}" for item in FACTORY_POOL_IDS)}


def parser():
    command = argparse.ArgumentParser(description="مدیریت binding مصوب دوره محاسبه هزینه")
    command.add_argument("--profile-file", required=True, type=Path)
    command.add_argument("--binding-file", required=True, type=Path)
    command.add_argument("--factory-id", required=True)
    command.add_argument("--period-id", required=True)
    command.add_argument("--start", required=True)
    command.add_argument("--end", required=True)
    command.add_argument("--source", action="append", required=True, dest="sources")
    command.add_argument("--active", action="store_true")
    command.add_argument("--write", action="store_true", help="پس از validation فایل را atomically بنویس (پیش‌فرض dry-run است)")
    return command


def main(argv=None):
    args = parser().parse_args(argv)
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    if start > end:
        raise SystemExit("start must not follow end")
    unknown = sorted(set(args.sources) - KNOWN_SOURCES)
    if unknown:
        raise SystemExit(f"unknown source names: {', '.join(unknown)}")
    if set(args.sources) != KNOWN_SOURCES:
        raise SystemExit("all required sources must be approved explicitly with repeated --source options")
    store = ProfileDataStore(args.profile_file)
    factory = next((item for item in store.list_factories() if item.get("id") == args.factory_id), None)
    if not factory:
        raise SystemExit("canonical factory ID is absent from the profile registry")
    try:
        document = json.loads(args.binding_file.read_text(encoding="utf-8")) if args.binding_file.exists() else {"bindings": []}
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"binding file is not valid JSON: {exc}") from None
    bindings = document.get("bindings")
    if not isinstance(bindings, list):
        raise SystemExit("binding file must contain a bindings list")
    candidate = {"factory_id": args.factory_id, "period_id": args.period_id, "active": args.active,
                 "start": args.start, "end": args.end, "sources": args.sources}
    bindings = [item for item in bindings if not (item.get("factory_id") == args.factory_id and item.get("period_id") == args.period_id)]
    bindings.append(candidate)
    if args.active and sum(item.get("factory_id") == args.factory_id and item.get("active") is True for item in bindings) != 1:
        raise SystemExit("factory would not have exactly one active binding; deactivate the old binding explicitly")
    output = {**document, "bindings": bindings}
    if args.write:
        args.binding_file.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=args.binding_file.parent, prefix=".costing-bindings-", text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(output, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, args.binding_file)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        print(f"WROTE {args.binding_file}")
    else:
        print(json.dumps(candidate, ensure_ascii=False, indent=2))
        print("VALID (dry-run; use --write to persist)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
