"""Safe, idempotent normalization of approved legacy costing sources.

This module is the sole registry of legacy-to-canonical costing mappings.  It
never invents a business value and never overwrites a canonical source.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable

from utils.costing_engine import FACTORY_POOL_IDS, ProductIdentity


MIGRATION_VERSION = "legacy-costing-canonical-v1"
GENERATED_BY = "SYSTEM_LEGACY_MIGRATION"


def _inside(root: Path, path: Path) -> Path:
    resolved = path.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError("costing source path leaves the data root")
    return resolved


def _read_json(path: Path) -> tuple[dict | None, bytes | None]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None, None
    return (value, raw) if isinstance(value, dict) else (None, raw)


def _number(value: Any) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    try:
        return Decimal(str(value)).is_finite()
    except (InvalidOperation, ValueError):
        return False


def _metadata(status: str, *, source: str | None, fingerprint: str | None,
              fields: list[str], now: datetime) -> dict:
    return {
        "migration_version": MIGRATION_VERSION,
        "migration_type": "LEGACY_CANONICALIZATION",
        "status": status,
        "source": source,
        "source_fingerprint": fingerprint,
        "source_fields": fields,
        "generated_at": now.isoformat(),
        "generated_by": GENERATED_BY,
        "business_value_invented": False,
    }


def _atomic_create(path: Path, document: dict) -> bool:
    """Atomically install ``document`` only when ``path`` remains absent."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".legacy-costing-", text=True)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            return False
        return True
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _pool_rows(document: dict | None) -> dict[str, list[Any]]:
    data = document.get("data") if isinstance(document, dict) else None
    if not isinstance(data, dict):
        return {}
    names, costs = data.get("Subfield"), data.get("Cost")
    if not isinstance(names, list) or not isinstance(costs, list) or len(names) != len(costs):
        return {}
    result: dict[str, list[Any]] = {}
    for name, cost in zip(names, costs):
        if isinstance(name, str):
            result.setdefault(name, []).append(cost)
    return result


def _canonical_pool_total(document: dict | None) -> Decimal | None:
    data = document.get("data") if isinstance(document, dict) else None
    costs = data.get("cost") if isinstance(data, dict) else None
    if not isinstance(costs, list) or any(not _number(value) for value in costs):
        return None
    return sum((Decimal(str(value)) for value in costs), Decimal(0))


def _product_names(factory_root: Path) -> list[str]:
    return sorted({path.stem for path in factory_root.glob("*/*/*.json")
                   if not path.name.startswith("_") and not path.stem.endswith("_meta")})


def _category_names(factory_root: Path) -> list[str]:
    return sorted(path.name for path in factory_root.iterdir() if path.is_dir()) if factory_root.is_dir() else []


def _known_product(root: Path, factory_root: Path, operational_key: str,
                   identity: ProductIdentity) -> bool:
    metadata = factory_root / identity.category / identity.subcategory / f"{identity.product}_meta.json"
    if metadata.is_file():
        return True
    catalogue, _ = _read_json(root / "Overall" / "ProductsLater.json")
    if not isinstance(catalogue, dict):
        return False
    columns = [catalogue.get(name) for name in ("Factory", "Category", "Subcategory", "Product_Name")]
    if any(not isinstance(column, dict) for column in columns):
        return False
    indexes = set(columns[0]).intersection(*(set(column) for column in columns[1:]))
    target = (operational_key, identity.category, identity.subcategory, identity.product)
    return any(tuple(column[index] for column in columns) == target for index in indexes)


def ensure_canonical_costing_sources(factory_service, factory_id: str, data_root: Path,
                                     identity: ProductIdentity | None = None, *, persist: bool = True,
                                     clock: Callable[[], datetime] | None = None) -> dict:
    """Inspect and optionally create safe canonical sources for one factory."""
    factory = factory_service.get_factory(factory_id)
    if factory is None:
        raise ValueError("canonical factory ID is absent from the profile registry")
    root = Path(data_root).resolve()
    operational_key = factory_service.operational_key(factory)
    factory_root = _inside(root, root / "Factories" / operational_key)
    now = clock() if clock else datetime.now(timezone.utc)
    if not now.tzinfo:
        now = now.replace(tzinfo=timezone.utc)
    report = {
        "factory_id": factory_id, "created_sources": [], "already_available": [],
        "needs_input": [], "conflicts": [], "unrecoverable": [], "actions": [], "changed": False,
    }

    legacy_path = _inside(root, factory_root / "Factory_Data.json")
    legacy_document, legacy_raw = _read_json(legacy_path)
    rows = _pool_rows(legacy_document)
    fingerprint = hashlib.sha256(legacy_raw).hexdigest() if legacy_raw is not None else None
    for pool in FACTORY_POOL_IDS:
        source_name = f"pool:{pool}"
        canonical = _inside(root, factory_root / f"Factory_Data_{pool}.json")
        matches = rows.get(pool, [])
        if canonical.is_file():
            report["already_available"].append(source_name)
            current, _ = _read_json(canonical)
            total = _canonical_pool_total(current)
            if len(matches) == 1 and _number(matches[0]) and total is not None and total != Decimal(str(matches[0])):
                report["conflicts"].append(source_name)
                report["actions"].append({"source_name": source_name, "status": "CONFLICT",
                                          "canonical_path": str(canonical), "legacy_source": legacy_path.name})
            else:
                report["actions"].append({"source_name": source_name, "status": "AVAILABLE",
                                          "canonical_path": str(canonical)})
            continue
        if len(matches) == 1 and _number(matches[0]):
            document = {
                "_order": ["subject", "cost"],
                "data": {"subject": ["Legacy migrated total"], "cost": [matches[0]]},
                "_migration": _metadata("READY", source=legacy_path.name, fingerprint=fingerprint,
                                         fields=["Subfield", "Cost"], now=now),
            }
            status = "CREATED_READY" if persist and _atomic_create(canonical, document) else "WOULD_CREATE_READY"
            if persist and status == "WOULD_CREATE_READY":
                status = "AVAILABLE"
                report["already_available"].append(source_name)
            elif status == "CREATED_READY":
                report["created_sources"].append(source_name)
                report["changed"] = True
            report["actions"].append({"source_name": source_name, "status": status,
                                      "canonical_path": str(canonical), "legacy_source": legacy_path.name})
        else:
            reason = "matching legacy Subfield is absent" if not matches else "legacy Cost is missing, malformed, or ambiguous"
            report["unrecoverable"].append(source_name)
            report["actions"].append({"source_name": source_name, "status": "UNRECOVERABLE", "reason": reason,
                                      "canonical_path": str(canonical), "legacy_source": legacy_path.name})

    structural = []
    prediction_path = _inside(root, factory_root / "ProductionPrediction.json")
    if not prediction_path.exists():
        products = _product_names(factory_root)
        if products:
            structural.append(("predictions", prediction_path, {
                "_order": ["Product Name", "Predicted Production"],
                "data": {"Product Name": products, "Predicted Production": [None] * len(products)},
                "_migration": _metadata("NEEDS_INPUT", source=None, fingerprint=None,
                                         fields=["Product Name", "Predicted Production"], now=now),
            }))
        else:
            report["unrecoverable"].append("predictions")
            report["actions"].append({"source_name": "predictions", "status": "UNRECOVERABLE",
                                      "reason": "product identities are unavailable"})
    else:
        report["already_available"].append("predictions")
        report["actions"].append({"source_name": "predictions", "status": "AVAILABLE",
                                  "canonical_path": str(prediction_path)})

    weights_path = _inside(root, factory_root / "category_weights.json")
    if not weights_path.exists():
        categories = _category_names(factory_root)
        if categories:
            structural.append(("weights", weights_path, {
                "_order": ["category", "selling_share_of_category"],
                "data": {"category": categories, "selling_share_of_category": [None] * len(categories)},
                "_migration": _metadata("NEEDS_INPUT", source=None, fingerprint=None,
                                         fields=["category", "selling_share_of_category"], now=now),
            }))
        else:
            report["unrecoverable"].append("weights")
            report["actions"].append({"source_name": "weights", "status": "UNRECOVERABLE",
                                      "reason": "category identities are unavailable"})
    else:
        report["already_available"].append("weights")
        report["actions"].append({"source_name": "weights", "status": "AVAILABLE",
                                  "canonical_path": str(weights_path)})

    if identity is not None:
        bom_path = _inside(root, factory_root / identity.category / identity.subcategory / f"{identity.product}.json")
        if not bom_path.exists():
            if _known_product(root, factory_root, operational_key, identity):
                structural.append(("bom", bom_path, {
                    "_order": ["materials", "usage", "lost_percentage", "recycability_percentage"],
                    "data": {"materials": [], "usage": [], "lost_percentage": [], "recycability_percentage": []},
                    "_migration": _metadata("NEEDS_INPUT", source=None, fingerprint=None,
                                             fields=["materials", "usage", "lost_percentage", "recycability_percentage"], now=now),
                }))
            else:
                report["unrecoverable"].append("bom")
                report["actions"].append({"source_name": "bom", "status": "UNRECOVERABLE",
                                          "reason": "product identity is absent from approved catalogue metadata"})
        else:
            report["already_available"].append("bom")
            report["actions"].append({"source_name": "bom", "status": "AVAILABLE",
                                      "canonical_path": str(bom_path)})

    material_path = _inside(root, root / "Overall" / "material_costs.json")
    if material_path.exists():
        report["already_available"].append("materials")
        report["actions"].append({"source_name": "materials", "status": "AVAILABLE",
                                  "canonical_path": str(material_path)})
    else:
        report["unrecoverable"].append("materials")
        report["actions"].append({"source_name": "materials", "status": "UNRECOVERABLE",
                                  "reason": "no approved lossless legacy material-price mapping exists"})

    for source_name, path, document in structural:
        status = "CREATED_NEEDS_INPUT" if persist and _atomic_create(path, document) else "WOULD_CREATE_NEEDS_INPUT"
        if persist and status == "WOULD_CREATE_NEEDS_INPUT":
            status = "AVAILABLE"
            report["already_available"].append(source_name)
        else:
            report["needs_input"].append(source_name)
            if status == "CREATED_NEEDS_INPUT":
                report["created_sources"].append(source_name)
                report["changed"] = True
        report["actions"].append({"source_name": source_name, "status": status,
                                  "canonical_path": str(path)})
    return report
