"""Read-only access to the operational product hierarchy.

This service deliberately has no authorization policy.  Callers must first
resolve and authorize a canonical factory through :class:`FactoryService` and
then pass only its trusted operational key here.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

from utils.paths import parent_path
from utils.product_catalog import build_product_catalog


ALL = "__ALL__"


class HierarchyMetadataError(RuntimeError):
    """Operational hierarchy metadata is absent or malformed."""


class HierarchySelectionError(ValueError):
    """A requested hierarchy member is not a child of the supplied parent."""


class ProductHierarchyService:
    """Build deterministic, factory-isolated filter options without writes."""

    def __init__(self, factories_root: Path | None = None):
        self.factories_root = Path(factories_root or (Path(parent_path) / "Factories"))

    def options(
        self,
        operational_key: str,
        *,
        category: str | None = None,
        subcategory: str | None = None,
        product: str | None = None,
    ) -> dict:
        hierarchy = self._factory_hierarchy(operational_key)
        categories = sorted(hierarchy, key=str.casefold)
        self._validate_scope(category, categories, "دسته")

        selected_categories = categories if category == ALL else ([category] if category else [])
        subcategories = sorted(
            {child for parent in selected_categories for child in hierarchy[parent]}, key=str.casefold
        )
        self._validate_scope(subcategory, subcategories, "زیردسته")
        if subcategory and not category:
            raise HierarchySelectionError("انتخاب زیردسته بدون تعیین دامنه دسته مجاز نیست.")

        selected_subcategories = subcategories if subcategory == ALL else ([subcategory] if subcategory else [])
        products = self._products(operational_key, hierarchy, selected_categories, selected_subcategories)
        product_refs = [item["id"] for item in products]
        self._validate_scope(product, product_refs, "محصول")
        if product and not subcategory:
            raise HierarchySelectionError("انتخاب محصول بدون تعیین دامنه زیردسته مجاز نیست.")

        deepest_requested = category is not None or subcategory is not None
        state = "OK"
        if not categories:
            state = "UNCONFIGURED"
        elif deepest_requested and ((category is not None and not subcategories) or (subcategory is not None and not products)):
            state = "NO_MATCH"

        return {
            "state": state,
            "operators": {"all": ALL},
            "selection": {
                "category": category,
                "subcategory": subcategory,
                "product": product,
            },
            "options": {
                "categories": [{"id": value, "label": value} for value in categories],
                "subcategories": [{"id": value, "label": value} for value in subcategories],
                "products": products,
            },
        }

    def _factory_hierarchy(self, operational_key: str) -> dict[str, list[str]]:
        metadata_path = self.factories_root / "__metadata.json"
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            raw = metadata["product_hierarchy"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise HierarchyMetadataError("فراداده سلسله‌مراتب محصول در دسترس یا معتبر نیست.") from exc
        if not isinstance(raw, dict):
            raise HierarchyMetadataError("ساختار فراداده سلسله‌مراتب محصول معتبر نیست.")
        hierarchy = raw.get(operational_key)
        if hierarchy is None:
            return {}
        if not isinstance(hierarchy, dict) or any(
            not isinstance(category, str)
            or not isinstance(children, list)
            or any(not isinstance(child, str) for child in children)
            for category, children in hierarchy.items()
        ):
            raise HierarchyMetadataError("ساختار فراداده کارخانه معتبر نیست.")
        return {category: sorted(set(children), key=str.casefold) for category, children in hierarchy.items()}

    def _products(self, operational_key, hierarchy, categories, subcategories):
        result = []
        try:
            products = build_product_catalog(self.factories_root, [operational_key])
        except OSError as exc:
            raise HierarchyMetadataError("خواندن پیکربندی محصولات ممکن نیست.") from exc
        for item in products:
            if item.category in categories and item.subcategory in subcategories:
                    identity = [operational_key, item.category, item.subcategory, item.product]
                    encoded = base64.urlsafe_b64encode(
                        json.dumps(identity, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                    ).decode("ascii").rstrip("=")
                    result.append({
                        "id": encoded,
                        "label": item.product,
                        "category": item.category,
                        "subcategory": item.subcategory,
                    })
        return sorted(result, key=lambda item: (item["label"].casefold(), item["category"].casefold(), item["subcategory"].casefold()))

    @staticmethod
    def _validate_scope(value, valid_values, label):
        if value is not None and value != ALL and value not in valid_values:
            raise HierarchySelectionError(f"{label} در دامنه والد انتخاب‌شده وجود ندارد.")
