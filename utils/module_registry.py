"""Explicit canonical metadata for administratively grantable modules."""

from __future__ import annotations

MODULE_REGISTRY = (
    {"id": "cost_calculation", "label": "محاسبه هزینه", "scopes": ("FACTORY",)},
    {"id": "dashboard", "label": "داشبورد", "scopes": ("GLOBAL", "FACTORY")},
    {"id": "desk", "label": "میز کار", "scopes": ("GLOBAL",)},
    {"id": "factory_parameters", "label": "پارامترهای کارخانه", "scopes": ("FACTORY",)},
    {"id": "general_parameters", "label": "پارامترهای عمومی", "scopes": ("GLOBAL",)},
    {"id": "product", "label": "پیکربندی محصول", "scopes": ("FACTORY",)},
    {"id": "profile", "label": "پروفایل کاربر", "scopes": ("GLOBAL",)},
)

GRANTABLE_MODULES = frozenset(item["id"] for item in MODULE_REGISTRY)
MODULE_BY_ID = {item["id"]: item for item in MODULE_REGISTRY}
MODULE_LABELS = {item["id"]: item["label"] for item in MODULE_REGISTRY}
MODULE_SCOPES = {item["id"]: frozenset(item["scopes"]) for item in MODULE_REGISTRY}

# Authentication is intentionally absent: grantability never follows directory discovery.
INTERNAL_MODULES = frozenset({"auth"})
