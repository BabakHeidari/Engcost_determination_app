"""Safe presentation model for the canonical Profile access model."""

from utils.profile_authorization import (
    PERMISSIONS,
    TOP_LEVEL_ROLES,
    can_manage_users,
    can_manage_factories,
    get_effective_access,
    is_top_level_admin,
    has_access,
)
from utils.audit import AUDIT_ACTION_LABELS
from utils.factory_service import FactoryService
from utils.profile_store import ProfileStoreError
from utils.profile_access_manager import grants_to_access_state
from utils.module_registry import MODULE_LABELS, MODULE_REGISTRY, MODULE_SCOPES

ROLE_LABELS = {
    "IT_ADMIN": "مدیر IT",
    "FINANCE_ECONOMIC_ADMIN": "مدیر مالی و اقتصادی",
    "USER": "کاربر",
}
PERMISSION_LABELS = {"READ": "فقط مشاهده", "WRITE": "ثبت اطلاعات", "MODIFY": "ویرایش کامل"}
LEVEL_LABELS = {"NONE": "بدون دسترسی", **PERMISSION_LABELS}
AUDIT_PAGE_LIMIT = 100


def _can_view_event(user, event, admin):
    if admin:
        return True
    if event.get("actor_user_id") != user["id"] and event.get("target_id") != user["id"]:
        return False
    module_id, factory_id = event.get("module_id"), event.get("factory_id")
    if module_id:
        return has_access(user, module_id, "READ", factory_id,
                          scope_type="FACTORY" if factory_id else "GLOBAL")
    # A personal user-lifecycle event is safe; a factory event without a
    # canonical module cannot be authorized for an ordinary user.
    return event.get("target_type") == "user" and factory_id is None


def _audit_summary(event, factory_names):
    grants = event.get("changes", {}).get("grants", []) if isinstance(event.get("changes"), dict) else []
    lines = []
    for item in grants:
        module_id = item.get("module_id")
        if module_id not in MODULE_LABELS:
            continue
        scope = "سراسری" if item.get("scope_type") == "GLOBAL" else factory_names.get(item.get("factory_id"), "کارخانه مجاز")
        lines.append(f'{scope} / {MODULE_LABELS[module_id]}: {LEVEL_LABELS.get(item.get("before"), "نامشخص")} ← {LEVEL_LABELS.get(item.get("after"), "نامشخص")}')
    return lines


def _public_user(user):
    return {
        "id": user["id"], "username": user.get("username", ""),
        "full_name": user.get("full_name") or user.get("username") or user["email"],
        "email": user["email"], "system_role": user["system_role"],
        "system_role_label": ROLE_LABELS[user["system_role"]],
        "job_title": user.get("job_title", ""), "last_login_at": user.get("last_login_at"),
        "is_active": bool(user.get("is_active")), "revision": user.get("revision", 1),
        "access_state": grants_to_access_state(user.get("access_grants", [])),
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
    user_names = {u["id"]: u.get("full_name") or u.get("username") or "کاربر" for u in data["users"]}
    audit_events = [{
        "id": e["id"], "occurred_at": e.get("occurred_at"), "action": e.get("action", ""),
        "action_label": AUDIT_ACTION_LABELS.get(e.get("action"), e.get("action", "رویداد ثبت‌شده")),
        "actor_label": user_names.get(e.get("actor_user_id"), "کاربر سامانه"),
        "target_label": (user_names.get(e.get("target_id"), "کاربر") if e.get("target_type") == "user"
                         else factory_names.get(e.get("target_id"), "کارخانه")),
        "module_label": MODULE_LABELS.get(e.get("module_id")),
        "summary_lines": _audit_summary(e, factory_names),
    } for e in data["audit_events"] if _can_view_event(current, e, admin)]
    audit_events.sort(key=lambda e: e.get("occurred_at") or "", reverse=True)
    audit_events = audit_events[:AUDIT_PAGE_LIMIT]
    return {
        "current_user": _public_user(current), "full_access": admin,
        "effective_grants": _group_grants(current, factory_names),
        "users": [_public_user(u) for u in visible_users],
        "factories": visible_factories,
        "audit_events": audit_events,
        "features": {"add_user": can_manage_users(current), "edit_user": can_manage_users(current), "add_factory": can_manage_factories(current), "edit_permissions": can_manage_users(current)},
        "access_manager": {
            "factories": [dict(FactoryService._public(f), is_active=bool(f.get("is_active", True))) for f in data["factories"]],
            "global_modules": [{
                "value": item["id"], "label": item["label"],
                "mandatory_access": bool(item.get("mandatory_access")),
                "minimum_level": item.get("minimum_level"),
            } for item in MODULE_REGISTRY if "GLOBAL" in item["scopes"]],
            "factory_modules": [{"value": item["id"], "label": item["label"]} for item in MODULE_REGISTRY if "FACTORY" in item["scopes"]],
            "levels": [{"value": value, "label": label} for value, label in (
                ("NONE", "بدون دسترسی"), ("READ", "فقط مشاهده"),
                ("WRITE", "ثبت اطلاعات"), ("MODIFY", "ویرایش کامل"))],
        },
        "create_user": {
            "roles": [{"value": key, "label": ROLE_LABELS[key], "is_admin": key in TOP_LEVEL_ROLES} for key in ("IT_ADMIN", "FINANCE_ECONOMIC_ADMIN", "USER")],
            "modules": [
                {
                    "value": key,
                    "label": MODULE_LABELS[key] + (" (کارخانه)" if len(scopes) > 1 and scope == "FACTORY" else ""),
                    "scope": scope,
                }
                for item in MODULE_REGISTRY
                for key, scopes in ((item["id"], item["scopes"]),)
                for scope in sorted(scopes)
            ],
            "permissions": [{"value": key, "label": PERMISSION_LABELS[key]} for key in sorted(PERMISSIONS)],
        },
    }
