"""Safe presentation model for the canonical Profile access model."""

from utils.profile_authorization import (
    MODULE_SCOPES,
    PERMISSIONS,
    TOP_LEVEL_ROLES,
    can_manage_users,
    can_manage_factories,
    get_effective_access,
    is_top_level_admin,
)
from utils.factory_service import FactoryService
from utils.profile_store import ProfileStoreError

ROLE_LABELS = {
    "IT_ADMIN": "مدیر IT",
    "FINANCE_ECONOMIC_ADMIN": "مدیر مالی و اقتصادی",
    "USER": "کاربر",
}
MODULE_LABELS = {
    "DESK": "میز کار", "DASHBOARD": "داشبورد", "PROFILE": "پروفایل",
    "GENERAL_PARAMETERS": "پارامترهای عمومی", "FACTORY_PARAMETERS": "پارامترهای کارخانه",
    "PRODUCT": "محصول", "COST_CALCULATION": "محاسبه بهای تمام‌شده",
}
PERMISSION_LABELS = {"READ": "مشاهده", "WRITE": "ثبت و تغییر"}


def _public_user(user):
    return {
        "id": user["id"], "username": user.get("username", ""),
        "full_name": user.get("full_name") or user.get("username") or user["email"],
        "email": user["email"], "system_role": user["system_role"],
        "system_role_label": ROLE_LABELS[user["system_role"]],
        "job_title": user.get("job_title", ""), "last_login_at": user.get("last_login_at"),
        "is_active": bool(user.get("is_active")), "revision": user.get("revision", 1),
        "access_grants": user.get("access_grants", []),
    }


def _group_grants(user, factory_names):
    effective_access = get_effective_access(user)
    # Top-level administrators are represented by the compact FULL_ACCESS
    # sentinel, not by a list of stored grants. The template renders that state
    # through ``full_access`` and must not try to treat the sentinel's key as a
    # grant object.
    if not isinstance(effective_access, list):
        return []
    groups = []
    for grant in effective_access:
        groups.append({
            "scope_type": grant["scope_type"],
            "scope_label": "سراسری" if grant["scope_type"] == "GLOBAL" else factory_names.get(grant["factory_id"], grant["factory_id"]),
            "module": grant["module"], "module_label": MODULE_LABELS[grant["module"]],
            "permissions": [PERMISSION_LABELS[p] for p in grant["permissions"]],
        })
    return groups


def build_profile_view_model(store, authenticated_user):
    data = store.load_data()
    current = next((u for u in data["users"] if u["id"] == authenticated_user["id"]), None)
    if current is None or not current.get("is_active", False):
        raise ProfileStoreError("Authenticated user is unavailable")
    admin = is_top_level_admin(current)
    factory_names = {f["id"]: f.get("display_name") or f.get("name") or f["code"] for f in data["factories"]}
    visible_users = [u for u in data["users"] if admin or (u.get("is_active") and u["id"] == current["id"])]
    # Profile access management may show any factory granted in any business
    # module.  Administrators implicitly receive every active registry entry.
    visible_factories = [FactoryService._public(f) for f in data["factories"] if f.get("is_active", True)] if admin else [
        FactoryService._public(f)
        for f in data["factories"] if f.get("is_active", True) and any(
            g["scope_type"] == "FACTORY" and g["factory_id"] == f["id"] for g in current["access_grants"]
        )
    ]
    visible_ids = {u["id"] for u in visible_users}
    audit_events = [{"id": e["id"], "occurred_at": e.get("occurred_at"), "action": e.get("action", ""), "outcome": e.get("outcome")}
                    for e in data["audit_events"] if e.get("actor_user_id") == current["id"] or e.get("target_id") == current["id"] or (admin and e.get("target_id") in visible_ids)]
    audit_events.sort(key=lambda e: e.get("occurred_at") or "", reverse=True)
    return {
        "current_user": _public_user(current), "full_access": admin,
        "effective_grants": _group_grants(current, factory_names),
        "users": [_public_user(u) for u in visible_users],
        "factories": visible_factories,
        "audit_events": audit_events,
        "features": {"add_user": can_manage_users(current), "edit_user": can_manage_users(current), "add_factory": can_manage_factories(current), "edit_permissions": can_manage_users(current)},
        "create_user": {
            "roles": [{"value": key, "label": ROLE_LABELS[key], "is_admin": key in TOP_LEVEL_ROLES} for key in ("IT_ADMIN", "FINANCE_ECONOMIC_ADMIN", "USER")],
            "modules": [
                {
                    "value": key,
                    "label": MODULE_LABELS[key] + (" (کارخانه)" if len(scopes) > 1 and scope == "FACTORY" else ""),
                    "scope": scope,
                }
                for key, scopes in MODULE_SCOPES.items() for scope in sorted(scopes)
            ],
            "permissions": [{"value": key, "label": PERMISSION_LABELS[key]} for key in sorted(PERMISSIONS)],
        },
    }
