"""Discovery/import helpers for the canonical Profile factory registry.

Operational files are migration inputs only. Profile pages consume the records
persisted by :class:`ProfileDataStore`, never these files directly.
"""

from __future__ import annotations

import json
from pathlib import Path

from utils.localization import display_value


DEFAULT_DATA_ROOT = Path(__file__).resolve().parents[1] / "Data"


def _load_json(path: Path):
    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, json.JSONDecodeError):
        return None


def discover_factories(data_root=DEFAULT_DATA_ROOT) -> dict:
    """Return deterministic factory candidates and traceability information."""
    root = Path(data_root)
    records: dict[str, dict] = {}
    sources: dict[str, set[str]] = {}
    missing_names: list[str] = []

    def observe(value, source, *, location=None):
        if not isinstance(value, str) or not value.strip():
            missing_names.append(str(source))
            return
        operational_key = value.strip()
        key = operational_key.casefold()
        sources.setdefault(key, set()).add(Path(source).as_posix())
        records.setdefault(key, {
            # Existing factory names are already stable operational identifiers
            # used by routes, products, and Data/Factories directory names.
            "id": operational_key,
            "code": operational_key,
            "name": operational_key,
            "display_name": display_value(operational_key),
            "location": location,
            "is_active": True,
            "operational_key": operational_key,
        })
        if location and not records[key].get("location"):
            records[key]["location"] = location

    table_path = root / "Overall" / "factories.json"
    table = _load_json(table_path)
    if isinstance(table, dict) and isinstance(table.get("data"), dict):
        columns = table["data"]
        names = columns.get("factory name", [])
        cities = columns.get("city", [])
        for index, name in enumerate(names if isinstance(names, list) else []):
            city = cities[index] if isinstance(cities, list) and index < len(cities) else None
            observe(name, table_path.relative_to(root.parent), location=city or None)

    factories_dir = root / "Factories"
    if factories_dir.is_dir():
        for child in sorted(factories_dir.iterdir(), key=lambda item: item.name.casefold()):
            if child.is_dir():
                observe(child.name, child.relative_to(root.parent))

    metadata_path = factories_dir / "__metadata.json"
    metadata = _load_json(metadata_path)
    hierarchy = metadata.get("product_hierarchy") if isinstance(metadata, dict) else None
    if isinstance(hierarchy, dict):
        for name in hierarchy:
            observe(name, metadata_path.relative_to(root.parent))

    products_path = root / "Overall" / "ProductsLater.json"
    products = _load_json(products_path)
    product_factories = products.get("Factory") if isinstance(products, dict) else None
    if isinstance(product_factories, dict):
        for name in product_factories.values():
            observe(name, products_path.relative_to(root.parent))

    ordered = [records[key] for key in sorted(records)]
    return {
        "factories": ordered,
        "sources": {records[key]["id"]: sorted(sources[key]) for key in sorted(records)},
        "missing_names": missing_names,
    }


def populate_factory_registry(store, data_root=DEFAULT_DATA_ROOT) -> dict:
    """Discover factories and merge them through the canonical store service."""
    discovery = discover_factories(data_root)
    result = store.merge_factories(discovery["factories"])
    return {**result, "discovered": len(discovery["factories"]), "sources": discovery["sources"]}
