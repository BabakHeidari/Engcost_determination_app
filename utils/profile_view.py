"""Safe, read-only presentation model for the authenticated Profile page."""

from __future__ import annotations

import copy

from utils.profile_store import ProfileStoreError


ROLE_LABELS = {
    "IT Admin": "مدیر فناوری اطلاعات",
    "Official Admin": "مدیر سازمانی",
    "Factory Admin": "مدیر کارخانه",
    "Office Staff": "کارشناس ستادی",
    "Factory Staff": "کارشناس کارخانه",
}


def _effective_permissions(data, user):
    role = data["role_permissions"].get(user["role"], {})
    permissions = copy.deepcopy(role.get("permissions", {}))
    for override in data["user_permission_overrides"]:
        if override.get("user_id") != user["id"]:
            continue
        module = override.get("module")
        actions = override.get("actions", [])
        if not isinstance(module, str) or not isinstance(actions, list):
            continue
        current = set(permissions.get(module, []))
        if override.get("effect") == "deny":
            current.difference_update(actions)
        elif override.get("effect") == "allow":
            current.update(actions)
        permissions[module] = sorted(current)
    return permissions


def _has_global_scope(data, user):
    return data["role_permissions"].get(user["role"], {}).get("scope") == "global"


def _public_user(user, factory_names):
    return {
        "id": user["id"],
        "username": user.get("username", ""),
        "full_name": user.get("full_name") or user.get("username") or user["email"],
        "email": user["email"],
        "role": user["role"],
        "role_label": ROLE_LABELS.get(user["role"], user["role"]),
        "factory_id": user.get("factory_id"),
        "factory_name": factory_names.get(user.get("factory_id")),
        "last_login_at": user.get("last_login_at"),
    }


def build_profile_view_model(store, authenticated_user):
    """Load one canonical snapshot and return only browser-safe profile fields."""
    data = store.load_data()
    current = next(
        (user for user in data["users"] if user["id"] == authenticated_user["id"]), None
    )
    if current is None or not current.get("is_active", False):
        raise ProfileStoreError("Authenticated user is unavailable")

    global_scope = _has_global_scope(data, current)
    factory_id = current.get("factory_id")
    visible_factories = [
        factory for factory in data["factories"]
        if factory.get("is_active", True)
        and (global_scope or (factory_id is not None and factory["id"] == factory_id))
    ]
    factory_names = {
        factory["id"]: factory.get("display_name") or factory.get("name") or factory["code"]
        for factory in data["factories"]
    }
    visible_users = [
        user for user in data["users"]
        if user.get("is_active", False)
        and (
            global_scope
            or user["id"] == current["id"]
            or (factory_id is not None and user.get("factory_id") == factory_id)
        )
    ]
    visible_user_ids = {user["id"] for user in visible_users}
    audit_events = [
        {
            "id": event["id"],
            "occurred_at": event.get("occurred_at"),
            "action": event.get("action", ""),
            "outcome": event.get("outcome"),
        }
        for event in data["audit_events"]
        if event.get("actor_user_id") == current["id"]
        or event.get("target_id") == current["id"]
        or (global_scope and event.get("target_id") in visible_user_ids)
    ]
    audit_events.sort(key=lambda event: event.get("occurred_at") or "", reverse=True)

    creatable_roles = {
        "IT Admin": list(data["role_permissions"]),
        "Official Admin": ["Official Admin", "Factory Admin", "Office Staff", "Factory Staff"],
        "Factory Admin": ["Factory Staff"],
    }.get(current["role"], [])
    return {
        "current_user": _public_user(current, factory_names),
        "effective_permissions": _effective_permissions(data, current),
        "users": [_public_user(user, factory_names) for user in visible_users],
        "factories": [
            {
                "id": factory["id"],
                "code": factory["code"],
                "name": factory_names[factory["id"]],
                "location": factory.get("location"),
            }
            for factory in visible_factories
        ],
        "audit_events": audit_events,
        "features": {
            "add_user": bool(creatable_roles),
            "edit_user": False,
            "add_factory": False,
            "edit_permissions": False,
        },
        "create_user": {"roles": [
            {"value": role, "label": ROLE_LABELS.get(role, role),
             "requires_factory": data["role_permissions"][role].get("scope") == "factory"}
            for role in creatable_roles if role in data["role_permissions"]
        ]},
    }
