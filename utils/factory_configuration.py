"""Canonical Factory Configuration V2 storage and legacy migration.

Legacy files are migration inputs only.  Once a completed V2 manifest exists,
all reads and writes in this module use ``configuration/`` exclusively.
"""
from __future__ import annotations

from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any

from utils.paths import parent_path


POOL_IDS = (
    "AdministrativeandResearch", "Payroll", "Overhead", "FinancialCosts",
    "Depriciation", "NonOperationalCostsandIncomes",
)
MIGRATION_VERSION = "factory-config-v2"
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class FactoryConfigurationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def validate_identifier(value: str, kind: str = "identifier") -> str:
    if not isinstance(value, str) or not SAFE_ID.fullmatch(value) or value in {".", ".."}:
        raise FactoryConfigurationError("INVALID_IDENTIFIER", f"invalid {kind}")
    return value


def validate_pool_id(pool_id: str) -> str:
    if pool_id not in POOL_IDS:
        raise FactoryConfigurationError("UNKNOWN_COST_POOL", "unknown cost pool")
    return pool_id


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON root must be an object")
    return value


def _fingerprint(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _number(value: Any) -> int | float:
    if isinstance(value, bool) or value in (None, ""):
        raise ValueError("cost is required")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("cost must be numeric") from None
    if not number.is_finite() or number < 0:
        raise ValueError("cost must be a finite non-negative number")
    return int(number) if number == number.to_integral_value() else float(number)


def _rows(document: dict, required: tuple[str, ...]) -> list[dict]:
    data = document.get("data")
    if not isinstance(data, dict) or any(not isinstance(data.get(key), list) for key in required):
        raise ValueError("invalid column-oriented data")
    lengths = {len(data[key]) for key in required}
    if len(lengths) != 1:
        raise ValueError("column lengths differ")
    return [{key: data[key][index] for key in data if isinstance(data[key], list) and len(data[key]) in lengths}
            for index in range(next(iter(lengths), 0))]


def _stable_ids(subjects: list[Any]) -> list[str]:
    used: set[str] = set()
    result = []
    for index, subject in enumerate(subjects, 1):
        raw = str(subject).strip()
        base = raw if SAFE_ID.fullmatch(raw) and raw not in {".", ".."} else f"Item{index}"
        candidate, suffix = base, 2
        while candidate in used:
            candidate, suffix = f"{base}-{suffix}", suffix + 1
        used.add(candidate)
        result.append(candidate)
    return result


def _pool_document(pool_id: str, rows: list[dict], status: str, source: str | None,
                   fingerprint: str | None, warnings: list[str]) -> dict:
    subjects = [row["subject"] for row in rows]
    return {
        "_schema": "factory-cost-pool-v2", "schema_version": 2,
        "pool_id": pool_id, "depth": 2, "parent_id": "cost_structure",
        "status": status, "_order": ["id", "subject", "cost"],
        "data": {"id": _stable_ids(subjects), "subject": subjects,
                 "cost": [_number(row["cost"]) for row in rows]},
        "_migration": {"status": status, "source": source,
                       "source_fingerprint": fingerprint, "warnings": warnings},
    }


@contextmanager
def _factory_lock(factory_root: Path):
    factory_root.mkdir(parents=True, exist_ok=True)
    lock_path = factory_root / ".factory-configuration-v2.lock"
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        yield
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _legacy_summary(factory_root: Path) -> tuple[dict[str, Any], Path]:
    path = factory_root / "Factory_Data.json"
    try:
        rows = _rows(_read(path), ("Subfield", "Cost"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}, path
    result: dict[str, Any] = {}
    for pool_id in POOL_IDS:
        matches = [row for row in rows if row["Subfield"] == pool_id]
        if len(matches) == 1:
            try:
                result[pool_id] = _number(matches[0]["Cost"])
            except ValueError:
                pass
    return result, path


def _copy_or_incomplete(factory_root: Path, legacy_name: str, order: list[str],
                        data: dict[str, list], known: list[str], key: str) -> tuple[dict, dict]:
    source = factory_root / legacy_name
    try:
        document = _read(source)
        _rows(document, tuple(order))
        migrated = {"_schema": f"factory-{key}-v2", "schema_version": 2,
                    "status": "MIGRATED_DETAIL", "_order": order,
                    "data": {column: list(document["data"][column]) for column in order}}
        meta = {"source": source.name, "source_fingerprint": _fingerprint(source),
                "result": "MIGRATED_DETAIL", "warnings": []}
        return migrated, meta
    except (OSError, ValueError, json.JSONDecodeError):
        migrated = {"_schema": f"factory-{key}-v2", "schema_version": 2,
                    "status": "NEEDS_INPUT", "_order": order,
                    "data": {order[0]: known, order[1]: [None] * len(known)}}
        return migrated, {"source": None, "source_fingerprint": None,
                          "result": "NEEDS_INPUT", "warnings": []}


def _known_products(factory_root: Path) -> list[str]:
    return sorted({path.stem for path in factory_root.glob("*/*/*.json") if not path.name.startswith("_")})


def _known_categories(factory_root: Path) -> list[str]:
    return sorted({path.parent.parent.name for path in factory_root.glob("*/*/*.json") if not path.name.startswith("_")})


def ensure_factory_configuration_v2(factory_id: str, operational_key: str | None = None,
                                    *, data_root: Path | None = None, persist: bool = True) -> dict:
    """Return a migration plan, atomically persisting it when requested."""
    validate_identifier(factory_id, "factory id")
    operational_key = validate_identifier(operational_key or factory_id, "operational key")
    root = Path(data_root or parent_path).resolve()
    factory_root = (root / "Factories" / operational_key).resolve()
    if root not in factory_root.parents:
        raise FactoryConfigurationError("UNSAFE_SOURCE_PATH", "factory path leaves data root")
    config = factory_root / "configuration"
    manifest_path = config / "manifest.json"
    # A dry run is strictly read-only (even a lock file would be an unwanted
    # mutation). Persisting callers serialize the complete inspect/write cycle.
    with (_factory_lock(factory_root) if persist else nullcontext()):
        if manifest_path.is_file():
            manifest = _read(manifest_path)
            if manifest.get("schema_version") == 2 and manifest.get("migration_status") == "COMPLETED":
                return {"status": "ALREADY_V2", "configuration_path": str(config), "manifest": manifest}

        summary, summary_path = _legacy_summary(factory_root)
        pool_documents, components = {}, {}
        for pool_id in POOL_IDS:
            detail = factory_root / f"Factory_Data_{pool_id}.json"
            warnings: list[str] = []
            try:
                legacy_rows = _rows(_read(detail), ("subject", "cost"))
                rows = [{"subject": row["subject"], "cost": _number(row["cost"])} for row in legacy_rows]
                detail_total = sum((Decimal(str(row["cost"])) for row in rows), Decimal(0))
                if pool_id in summary and detail_total != Decimal(str(summary[pool_id])):
                    warnings.append("LEGACY_SUMMARY_MISMATCH")
                result = "WARNING_SUMMARY_MISMATCH" if warnings else "MIGRATED_DETAIL"
                pool_documents[pool_id] = _pool_document(pool_id, rows, result, detail.name,
                                                          _fingerprint(detail), warnings)
                components[f"pool:{pool_id}"] = {"source": detail.name,
                    "source_fingerprint": _fingerprint(detail), "result": result, "warnings": warnings}
            except FileNotFoundError:
                if pool_id in summary:
                    rows = [{"subject": "مبلغ تجمیعی مهاجرت‌شده", "cost": summary[pool_id]}]
                    pool_documents[pool_id] = _pool_document(pool_id, rows, "MIGRATED_SUMMARY_ONLY",
                                                              summary_path.name, _fingerprint(summary_path), [])
                    pool_documents[pool_id]["data"]["id"] = ["LegacyMigratedTotal"]
                    components[f"pool:{pool_id}"] = {"source": summary_path.name,
                        "source_fingerprint": _fingerprint(summary_path), "result": "MIGRATED_SUMMARY_ONLY", "warnings": []}
                else:
                    pool_documents[pool_id] = _pool_document(pool_id, [], "NEEDS_INPUT", None, None, [])
                    components[f"pool:{pool_id}"] = {"source": None, "source_fingerprint": None,
                                                     "result": "NEEDS_INPUT", "warnings": []}
            except (ValueError, json.JSONDecodeError):
                pool_documents[pool_id] = _pool_document(pool_id, [], "INVALID_LEGACY_SOURCE", detail.name,
                                                          _fingerprint(detail), ["INVALID_LEGACY_SOURCE"])
                components[f"pool:{pool_id}"] = {"source": detail.name, "source_fingerprint": _fingerprint(detail),
                    "result": "INVALID_LEGACY_SOURCE", "warnings": ["INVALID_LEGACY_SOURCE"]}

        weights, weights_meta = _copy_or_incomplete(factory_root, "category_weights.json",
            ["category", "selling_share_of_category"], {}, _known_categories(factory_root), "category-weights")
        predictions, predictions_meta = _copy_or_incomplete(factory_root, "ProductionPrediction.json",
            ["Product Name", "Predicted Production"], {}, _known_products(factory_root), "production-prediction")
        components["weights"], components["predictions"] = weights_meta, predictions_meta
        migrated_at = datetime.now(timezone.utc).isoformat()
        manifest = {"schema": "factory-configuration-v2", "schema_version": 2,
            "factory_id": factory_id, "operational_key": operational_key, "max_cost_depth": 3,
            "migration_version": MIGRATION_VERSION, "migration_status": "COMPLETED",
            "migrated_at": migrated_at, "migration": {"status": "COMPLETED",
                "migration_version": MIGRATION_VERSION, "migrated_at": migrated_at,
                "source": "legacy-factory-configuration", "components": components}}
        plan = {"status": "WOULD_MIGRATE" if not persist else "COMPLETED",
                "configuration_path": str(config), "manifest": manifest}
        if not persist:
            return plan
        staging = Path(tempfile.mkdtemp(prefix=".configuration-v2-", dir=factory_root))
        try:
            (staging / "cost_pools").mkdir()
            structure = {"schema": "factory-cost-structure-v2", "schema_version": 2, "max_depth": 3,
                "root": {"id": "cost_structure", "depth": 1},
                "groups": [{"id": pool, "depth": 2, "parent_id": "cost_structure"} for pool in POOL_IDS]}
            documents = {"cost_structure.json": structure, "category_weights.json": weights,
                         "production_prediction.json": predictions}
            for name, document in documents.items():
                (staging / name).write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
            for pool_id, document in pool_documents.items():
                (staging / "cost_pools" / f"{pool_id}.json").write_text(
                    json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
            # Manifest is written last in staging; rename makes the completed tree visible atomically.
            (staging / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            if config.exists():
                shutil.rmtree(config)
            os.replace(staging, config)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        return plan


def configuration_paths(factory_root: Path) -> dict[str, Path]:
    config = factory_root / "configuration"
    paths = {"weights": config / "category_weights.json", "predictions": config / "production_prediction.json"}
    paths.update({f"pool:{pool}": config / "cost_pools" / f"{pool}.json" for pool in POOL_IDS})
    return paths


def load_pool(factory_root: Path, pool_id: str) -> dict:
    validate_pool_id(pool_id)
    return _read(factory_root / "configuration" / "cost_pools" / f"{pool_id}.json")


def save_pool(factory_root: Path, pool_id: str, payload: dict) -> dict:
    validate_pool_id(pool_id)
    rows = _rows(payload, ("id", "subject", "cost"))
    ids = [validate_identifier(str(row["id"]), "item id") for row in rows]
    if len(ids) != len(set(ids)):
        raise FactoryConfigurationError("DUPLICATE_ITEM_ID", "item IDs must be unique within a pool")
    normalized = _pool_document(pool_id, [{"subject": row["subject"], "cost": row["cost"]} for row in rows],
                                "READY", "user-input", None, [])
    normalized["data"]["id"] = ids
    path = factory_root / "configuration" / "cost_pools" / f"{pool_id}.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)
    return normalized


def derived_summary(factory_root: Path) -> dict:
    totals = {}
    for pool in POOL_IDS:
        document = load_pool(factory_root, pool)
        totals[pool] = sum((_number(value) for value in document["data"]["cost"]), 0)
    factory_total = sum(totals.values())
    return {"pool_totals": totals, "factory_total": factory_total,
            "percentages": {pool: (totals[pool] / factory_total * 100 if factory_total else 0) for pool in POOL_IDS}}
