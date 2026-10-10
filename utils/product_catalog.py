"""Canonical semantic discovery for factory product/BOM files.

A product is a JSON BOM at exactly ``factory/category/subcategory/product.json``.
Application-owned namespaces are excluded before any file is considered.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from pathlib import Path
from typing import Iterable, Iterator

logger = logging.getLogger(__name__)
RESERVED_FACTORY_NAMESPACES = frozenset({"configuration", "backups", "archive"})
RESERVED_FILE_NAMES = frozenset({"__metadata.json", "__detailed_metadata.json"})


@dataclass(frozen=True)
class ProductCatalogItem:
    factory: str
    category: str
    subcategory: str
    product: str
    bom_path: Path
    metadata_path: Path
    capacity: object | None


def _business_directory(path: Path) -> bool:
    return path.is_dir() and not path.name.startswith(('.', '__')) and path.name not in RESERVED_FACTORY_NAMESPACES


def _capacity(metadata_path: Path) -> object | None:
    if not metadata_path.is_file():
        return None
    try:
        document = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.warning("Invalid product metadata for %s: %s", metadata_path.name, exc)
        return None
    if not isinstance(document, dict):
        logger.warning("Invalid product metadata object for %s", metadata_path.name)
        return None
    return document.get("capacity")


def iter_factory_products(factories_root: Path, factory_keys: Iterable[str] | None = None) -> Iterator[ProductCatalogItem]:
    """Yield products within registered/trusted factory roots in stable order."""
    root = Path(factories_root)
    keys = sorted(set(factory_keys), key=str.casefold) if factory_keys is not None else sorted(
        (path.name for path in root.iterdir() if _business_directory(path)), key=str.casefold
    )
    for factory in keys:
        factory_root = root / factory
        if not factory_root.is_dir():
            continue
        for category_path in sorted((path for path in factory_root.iterdir() if _business_directory(path)), key=lambda p: p.name.casefold()):
            for subcategory_path in sorted((path for path in category_path.iterdir() if _business_directory(path)), key=lambda p: p.name.casefold()):
                for bom_path in sorted(subcategory_path.glob("*.json"), key=lambda p: p.name.casefold()):
                    if (bom_path.name in RESERVED_FILE_NAMES or bom_path.name.startswith(('.', '__'))
                            or bom_path.stem.endswith("_meta")):
                        continue
                    metadata = bom_path.with_name(f"{bom_path.stem}_meta.json")
                    yield ProductCatalogItem(factory, category_path.name, subcategory_path.name,
                                             bom_path.stem, bom_path, metadata, _capacity(metadata))


def build_product_catalog(factories_root: Path, factory_keys: Iterable[str] | None = None) -> list[ProductCatalogItem]:
    return list(iter_factory_products(factories_root, factory_keys))


def product_catalog_document(factories_root: Path, factory_keys: Iterable[str] | None = None) -> dict:
    """Return the established column-oriented ``ProductsLater`` contract."""
    products = build_product_catalog(factories_root, factory_keys)
    columns = {
        "Product_Name": [item.product for item in products],
        "Factory": [item.factory for item in products],
        "Category": [item.category for item in products],
        "Subcategory": [item.subcategory for item in products],
        "Capacity": [item.capacity for item in products],
    }
    return {name: {str(index): value for index, value in enumerate(values)}
            for name, values in columns.items()}


def build_product_hierarchy(factories_root: Path, factory_keys: Iterable[str] | None = None) -> dict[str, dict[str, list[str]]]:
    """Return trusted factory/category/subcategory directories, excluding system namespaces."""
    root = Path(factories_root)
    keys = sorted(set(factory_keys), key=str.casefold) if factory_keys is not None else sorted(
        (path.name for path in root.iterdir() if _business_directory(path)), key=str.casefold
    )
    hierarchy = {}
    for factory in keys:
        factory_root = root / factory
        if not factory_root.is_dir():
            continue
        categories = {}
        for category in sorted((path for path in factory_root.iterdir() if _business_directory(path)), key=lambda p: p.name.casefold()):
            categories[category.name] = [path.name for path in sorted(
                (path for path in category.iterdir() if _business_directory(path)), key=lambda p: p.name.casefold()
            )]
        hierarchy[factory] = categories
    return hierarchy
