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
    """Create the first factory period as an auditable system-approved ACTIVE binding."""
    factory = factory_service.get_factory(factory_id)
    if not factory:
        raise ValueError("canonical factory ID is absent from the profile registry")
    document = _read_bindings(binding_path)
    existing = [item for item in document["bindings"] if item.get("factory_id") == factory_id]
    if existing:
        initial = [item for item in existing if item.get("period_id") == "INITIAL"]
        if len(existing) == 1 and len(initial) == 1:
            candidate = initial[0]
            try:
                valid_dates = date.fromisoformat(candidate["start"]) <= date.fromisoformat(candidate["end"])
            except (KeyError, TypeError, ValueError):
                valid_dates = False
            if (candidate.get("active") is True and candidate.get("approved") is True
                    and candidate.get("status") == "ACTIVE" and valid_dates):
                return candidate
        raise ValueError("factory already has costing-period history; automatic initialization is first-period only")

    operational_key = factory_service.operational_key(factory)
    root, factory_root = Path(data_root).resolve(), Path(data_root).resolve() / "Factories" / operational_key
    paths = [root / "Overall" / "material_costs.json"]
    if factory_root.is_dir():
        paths.extend(sorted(path for path in factory_root.rglob("*.json") if not path.name.startswith("_")))
    evidence, readable_sources = [], 0
    for path in paths:
        try:
            source = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(source, dict):
            continue
        data = source.get("data")
        if isinstance(data, dict) and any(isinstance(value, list) and value for value in data.values()):
            readable_sources += 1
        for parsed, identifier, raw in _dates(source):
            evidence.append({"date": parsed.isoformat(), "source_type": _source_type(path, factory_root),
                             "source": path.name, "source_identifier": identifier, "raw_value": raw,
                             "confidence": "AUTHORITATIVE_SOURCE_DATE"})
    evidence.sort(key=lambda item: (item["date"], item["source_type"], item["source"], item["source_identifier"]))
    now = _utc_now(clock)
    if not readable_sources:
        raise ValueError("no valid costing data exists for initial period creation")
    if evidence:
        start, date_origin, discovery_status = evidence[0]["date"], "SOURCE_DATE", "DISCOVERED"
    else:
        start, date_origin, discovery_status = now.date().isoformat(), "SYSTEM_INITIALIZATION_DATE", "NO_AUTHORITATIVE_SOURCE_DATE"
    # The initialization instant is an explicit system boundary, not source
    # history. A future-dated authoritative source produces a one-day period.
    end = max(date.fromisoformat(start), now.date()).isoformat()
    initial = {
        "factory_id": factory_id, "period_id": "INITIAL", "start": start, "end": end,
        "active": True, "approved": True, "status": "ACTIVE",
        "approved_by": "SYSTEM_INITIALIZATION", "approval_type": "SYSTEM_INITIALIZATION",
        "approved_at": now.isoformat(), "creation_reason": "FIRST_FACTORY_COSTING_INITIALIZATION",
        "date_origin": date_origin, "end_date_origin": "SYSTEM_INITIALIZATION_BOUNDARY",
        "discovery_status": discovery_status, "created_at": now.isoformat(),
        "source_evidence": evidence, "sources": sorted(REQUIRED_SOURCES),
    }
    document["bindings"].append(initial)
    if persist:
        _write_document(Path(binding_path), document)
    return initial


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


def validate_costing_period(factory_service: FactoryService, binding_path: Path,
                            factory_reference: str, period_id: str = "") -> dict:
    """Explain canonical resolution and the exact G3 usability decision read-only."""
    canonical = factory_service.get_factory(factory_reference)
    resolution = "CANONICAL_ID"
    if canonical is None:
        matches = [factory for factory in factory_service.list_factories()
                   if factory_service.operational_key(factory) == factory_reference]
        if len(matches) == 1:
            canonical, resolution = matches[0], "UNIQUE_OPERATIONAL_KEY"
        elif len(matches) > 1:
            return {"factory_input": factory_reference, "canonical_id": None,
                    "factory_resolution": "AMBIGUOUS_OPERATIONAL_KEY", "period_found": False,
                    "usable_by_costing": False, "reason": "Factory operational key is not unique."}
        else:
            return {"factory_input": factory_reference, "canonical_id": None,
                    "factory_resolution": "NOT_FOUND", "period_found": False,
                    "usable_by_costing": False, "reason": "Factory is absent from the canonical registry."}
    result = {"factory_input": factory_reference, "canonical_id": canonical["id"],
              "factory_resolution": resolution, "binding_file": str(Path(binding_path)),
              "binding_file_exists": Path(binding_path).is_file()}
    if not result["binding_file_exists"]:
        return {**result, "period_found": False, "usable_by_costing": False,
                "reason": "Runtime costing period binding file is not installed."}
    try:
        document = _read_bindings(Path(binding_path))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return {**result, "period_found": False, "usable_by_costing": False,
                "reason": "Runtime costing period binding file is invalid."}
    factory_bindings = [item for item in document["bindings"] if item.get("factory_id") == canonical["id"]]
    considered = [item for item in factory_bindings if item.get("period_id") == period_id] if period_id else factory_bindings
    active = [item for item in considered if item.get("active") is True]
    selected = active[0] if len(active) == 1 else considered[0] if len(considered) == 1 else None
    if selected is None:
        reason = "No binding uses the canonical factory ID." if not considered else "Period lookup is ambiguous; exactly one active binding is required."
        return {**result, "period_found": bool(considered), "binding_count": len(considered),
                "usable_by_costing": False, "reason": reason}
    start, end = selected.get("start"), selected.get("end")
    schema_valid = True
    try:
        schema_valid = date.fromisoformat(start) <= date.fromisoformat(end)
    except (TypeError, ValueError):
        schema_valid = False
    checks = {
        "active": selected.get("active") is True,
        "approved": selected.get("approved") is True,
        "active_status": selected.get("status") == "ACTIVE",
        "valid_dates": schema_valid,
    }
    usable = all(checks.values()) and len(active) == 1
    reasons = []
    if not checks["active"]: reasons.append("period is not marked active")
    if not checks["approved"]: reasons.append("owner approval is missing")
    if not checks["active_status"]: reasons.append("status is not ACTIVE")
    if not checks["valid_dates"]: reasons.append("canonical start/end fields are missing or invalid")
    if len(active) != 1: reasons.append("active binding is not unique")
    return {**result, "period_found": True, "binding_count": len(considered),
            "binding_factory_id": selected.get("factory_id"), "period_id": selected.get("period_id"),
            "start_date": start, "end_date": end, "status": selected.get("status"),
            "approved": selected.get("approved"), "active": selected.get("active"),
            "approval_owner": selected.get("approved_by"), "checks": checks,
            "usable_by_costing": usable, "reason": "Usable by costing." if usable else "; ".join(reasons) + "."}
