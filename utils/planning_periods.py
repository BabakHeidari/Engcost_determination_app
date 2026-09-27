"""Discover and approve the first G3 planning period without implicit activation."""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Callable

from utils.costing_engine import FACTORY_POOL_IDS
from utils.factory_service import FactoryService
from utils.localization import parse_jalali_input
from utils.profile_authorization import is_top_level_admin


REQUIRED_SOURCES = frozenset({
    "materials", "bom", "weights", "predictions",
    *(f"pool:{pool}" for pool in FACTORY_POOL_IDS),
})
DATE_FIELD_MARKERS = ("date", "as_of", "effective_at", "effective_on", "timestamp")


def _utc_now(clock: Callable[[], datetime] | None = None) -> datetime:
    value = clock() if clock else datetime.now(timezone.utc)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _parse_business_date(value) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        head = text[:10]
        year = int(head[:4])
        if 1300 <= year <= 1600:
            return date.fromisoformat(parse_jalali_input(head))
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except (TypeError, ValueError):
        return None


def _dates(value, *, field="", location=""):
    if isinstance(value, dict):
        for key, child in value.items():
            child_location = f"{location}.{key}" if location else key
            if isinstance(child, str) and any(marker in key.casefold() for marker in DATE_FIELD_MARKERS):
                parsed = _parse_business_date(child)
                if parsed:
                    yield parsed, child_location, child
            yield from _dates(child, field=key, location=child_location)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _dates(child, field=field, location=f"{location}[{index}]")


def _source_type(path: Path, factory_root: Path) -> str:
    name = path.name
    if name == "material_costs.json":
        return "MATERIAL_PRICES"
    if name == "ProductionPrediction.json":
        return "PRODUCTION_PREDICTION"
    if name == "category_weights.json":
        return "FACTORY_PARAMETERS"
    if name.startswith("Factory_Data_"):
        suffix = name.removeprefix("Factory_Data_").removesuffix(".json")
        return "FACTORY_COST_POOL" if suffix in FACTORY_POOL_IDS else "FACTORY_PARAMETERS"
    if factory_root in path.parents:
        return "PRODUCT_BOM"
    return "FACTORY_PARAMETERS"


def _write_document(path: Path, document: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".planning-period-", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _read_bindings(path: Path) -> dict:
    if not path.exists():
        return {"bindings": []}
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or not isinstance(document.get("bindings"), list):
        raise ValueError("binding file must contain a bindings list")
    return document


def discover_initial_period(factory_service: FactoryService, factory_id: str, data_root: Path,
                            binding_path: Path, *, clock=None, persist=True) -> dict:
    """Create a non-active draft from the earliest embedded source date."""
    factory = factory_service.get_factory(factory_id)
    if not factory:
        raise ValueError("canonical factory ID is absent from the profile registry")
    document = _read_bindings(binding_path)
    existing = [item for item in document["bindings"] if item.get("factory_id") == factory_id]
    if any(item.get("active") is True and item.get("approved") is True and item.get("status") == "ACTIVE" for item in existing):
        raise ValueError("factory already has an approved active planning period")
    if any(item.get("period_id") == "INITIAL" for item in existing):
        raise ValueError("factory already has an INITIAL planning-period record")

    operational_key = factory_service.operational_key(factory)
    root, factory_root = Path(data_root).resolve(), Path(data_root).resolve() / "Factories" / operational_key
    paths = [root / "Overall" / "material_costs.json"]
    if factory_root.is_dir():
        paths.extend(sorted(path for path in factory_root.rglob("*.json") if not path.name.startswith("_")))
    evidence = []
    for path in paths:
        try:
            source = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        for parsed, identifier, raw in _dates(source):
            evidence.append({"date": parsed.isoformat(), "source_type": _source_type(path, factory_root),
                             "source": path.name, "source_identifier": identifier, "raw_value": raw,
                             "confidence": "AUTHORITATIVE_SOURCE_DATE"})
    evidence.sort(key=lambda item: (item["date"], item["source_type"], item["source"], item["source_identifier"]))
    now = _utc_now(clock)
    if evidence:
        start, reason, baseline_type, status = evidence[0]["date"], "FIRST_AVAILABLE_DATA_DATE", "SOURCE_DATE", "DISCOVERED"
    else:
        start, reason, baseline_type, status = now.date().isoformat(), "SYSTEM_INITIALIZATION_DATE", "SYSTEM_INITIALIZATION_DATE", "NO_AUTHORITATIVE_SOURCE_DATE"
    draft = {
        "factory_id": factory_id, "period_id": "INITIAL", "start": start, "end": None,
        "active": False, "approved": False, "status": "DRAFT", "creation_reason": reason,
        "baseline_type": baseline_type, "discovery_status": status, "created_at": now.isoformat(),
        "source_evidence": evidence,
    }
    document["bindings"].append(draft)
    if persist:
        _write_document(Path(binding_path), document)
    return draft


def approve_initial_period(store, binding_path: Path, factory_id: str, actor_id: str,
                           end: str, sources, *, clock=None, persist=True) -> dict:
    """Approve exactly one INITIAL draft as a top-level, explicit action."""
    actor = store.get_user_by_id(actor_id)
    if not actor or not actor.get("is_active") or not is_top_level_admin(actor):
        raise PermissionError("only an active IT or Finance/Economic manager may approve the initial period")
    approved_sources = set(sources)
    if approved_sources != REQUIRED_SOURCES:
        raise ValueError("all required costing sources must be approved explicitly")
    end_date = date.fromisoformat(end)
    document = _read_bindings(Path(binding_path))
    matches = [item for item in document["bindings"] if item.get("factory_id") == factory_id and item.get("period_id") == "INITIAL"]
    if len(matches) != 1 or matches[0].get("status") != "DRAFT" or matches[0].get("approved") is not False:
        raise ValueError("exactly one unapproved INITIAL draft is required")
    draft = matches[0]
    if end_date < date.fromisoformat(draft["start"]):
        raise ValueError("period end must not precede the discovered start")
    if any(item is not draft and item.get("factory_id") == factory_id and item.get("active") is True for item in document["bindings"]):
        raise ValueError("factory already has another active binding")
    draft.update({"end": end_date.isoformat(), "active": True, "approved": True, "status": "ACTIVE",
                  "sources": sorted(approved_sources), "approved_by": actor_id,
                  "approved_at": _utc_now(clock).isoformat()})
    if persist:
        _write_document(Path(binding_path), document)
    return draft
