"""Canonical, deny-by-default Profile authorization policy.

Job titles are deliberately absent from this module: they are profile metadata,
not authorization input.
"""

from __future__ import annotations

import copy


IT_ADMIN = "IT_ADMIN"
FINANCE_ECONOMIC_ADMIN = "FINANCE_ECONOMIC_ADMIN"
USER = "USER"
SYSTEM_ROLES = frozenset({IT_ADMIN, FINANCE_ECONOMIC_ADMIN, USER})
TOP_LEVEL_ROLES = frozenset({IT_ADMIN, FINANCE_ECONOMIC_ADMIN})
SCOPE_TYPES = frozenset({"GLOBAL", "FACTORY"})
PERMISSION_ORDER = ("READ", "WRITE", "MODIFY")
PERMISSIONS = frozenset(PERMISSION_ORDER)
PERMISSION_LEVELS = {
    "NONE": (),
    "READ": ("READ",),
    "WRITE": ("READ", "WRITE"),
    "MODIFY": PERMISSION_ORDER,
}
LEVEL_RANK = {"NONE": 0, "READ": 1, "WRITE": 2, "MODIFY": 3}

# Scope follows the actual routes: pages/actions operating on a selected factory
# are factory scoped; the shell, shared material table and aggregate dashboard are
# global. Permission levels are hierarchical: MODIFY includes WRITE and READ.
MODULE_SCOPES = {
    "DESK": frozenset({"GLOBAL"}),
    # Dashboard shell is global; its optional factory filter is factory scoped.
    "DASHBOARD": frozenset({"GLOBAL", "FACTORY"}),
    "PROFILE": frozenset({"GLOBAL"}),
    "GENERAL_PARAMETERS": frozenset({"GLOBAL"}),
    "FACTORY_PARAMETERS": frozenset({"FACTORY"}),
    "PRODUCT": frozenset({"FACTORY"}),
    "COST_CALCULATION": frozenset({"FACTORY"}),
}
FULL_ACCESS = {"full_access": True}
AUDIT_EVENTS = frozenset({
    "SYSTEM_ROLE_CHANGED", "JOB_TITLE_CHANGED", "ACCESS_GRANTS_CHANGED",
    "TOP_LEVEL_ADMIN_UPDATED",
})


def is_top_level_admin(user: object) -> bool:
    return isinstance(user, dict) and user.get("system_role") in TOP_LEVEL_ROLES


def canonicalize_access_grants(grants: object, factory_ids) -> list[dict]:
    if not isinstance(grants, list):
        raise ValueError("فهرست دسترسی‌ها نامعتبر است.")
    known_factories = set(factory_ids)
    combined: dict[tuple[str, str | None, str], set[str]] = {}
    for grant in grants:
        if not isinstance(grant, dict) or set(grant) != {"scope_type", "factory_id", "module", "permissions"}:
            raise ValueError("ساختار دسترسی نامعتبر است.")
        scope, factory_id, module, permissions = (
            grant.get("scope_type"), grant.get("factory_id"), grant.get("module"), grant.get("permissions")
        )
        if scope not in SCOPE_TYPES or module not in MODULE_SCOPES or scope not in MODULE_SCOPES[module]:
            raise ValueError("دامنه یا ماژول دسترسی ناشناخته است.")
        if scope == "GLOBAL" and factory_id is not None:
            raise ValueError("دسترسی سراسری نباید کارخانه داشته باشد.")
        if scope == "FACTORY" and factory_id not in known_factories:
            raise ValueError("کارخانه دسترسی ناشناخته است.")
        if not isinstance(permissions, list) or not permissions or any(p not in PERMISSIONS for p in permissions):
            raise ValueError("مجوز دسترسی ناشناخته است.")
        combined.setdefault((scope, factory_id, module), set()).update(permissions)
    return [
        {"scope_type": scope, "factory_id": factory_id, "module": module,
         "permissions": [permission for permission in PERMISSION_ORDER if permission in values]}
        for (scope, factory_id, module), values in sorted(
            combined.items(), key=lambda item: (item[0][0], item[0][1] or "", item[0][2])
        )
    ]


def get_effective_access(user: object):
    if is_top_level_admin(user):
        return copy.deepcopy(FULL_ACCESS)
    if not isinstance(user, dict) or user.get("system_role") != USER:
        return []
    grants = user.get("access_grants")
    return copy.deepcopy(grants) if isinstance(grants, list) else []


def get_effective_level(user, module, factory_id=None, *, scope_type=None) -> str:
    """Resolve one canonical level without trusting grant array order.

    ``scope_type`` is optional for compatibility; when omitted it is derived
    from the presence of a factory ID.  Callers handling a MIXED module should
    pass it explicitly so a global action can never inherit a factory grant.
    """
    expected_scope = scope_type or ("FACTORY" if factory_id is not None else "GLOBAL")
    if (module not in MODULE_SCOPES or expected_scope not in SCOPE_TYPES
            or expected_scope not in MODULE_SCOPES[module]):
        return "NONE"
    if expected_scope == "GLOBAL" and factory_id is not None:
        return "NONE"
    if expected_scope == "FACTORY" and (not isinstance(factory_id, str) or not factory_id):
        return "NONE"
    if is_top_level_admin(user):
        return "MODIFY"
    if not isinstance(user, dict) or user.get("system_role") != USER:
        return "NONE"
    effective_rank = 0
    for grant in user.get("access_grants", []):
        if not isinstance(grant, dict):
            continue
        if (grant.get("scope_type") == expected_scope and grant.get("factory_id") == factory_id
                and grant.get("module") == module):
            effective_rank = max(
                effective_rank,
                max((LEVEL_RANK.get(value, 0) for value in grant.get("permissions", [])), default=0),
            )
    return next(level for level, rank in LEVEL_RANK.items() if rank == effective_rank)


def has_access(user, module, required_level="READ", factory_id=None, *, scope_type=None) -> bool:
    if required_level not in PERMISSIONS:
        return False
    effective = get_effective_level(user, module, factory_id, scope_type=scope_type)
    return LEVEL_RANK[effective] >= LEVEL_RANK[required_level]


def can_access_module(user, module, factory_id=None, permission="READ") -> bool:
    """Backward-compatible name for the canonical hierarchical resolver."""
    return has_access(user, module, permission, factory_id)


def can_manage_users(user) -> bool:
    return is_top_level_admin(user)


def can_manage_user(actor, target) -> bool:
    return is_top_level_admin(actor) and isinstance(target, dict)


def can_manage_sensitive_user_fields(actor, target) -> bool:
    return is_top_level_admin(actor) and is_top_level_admin(target) and actor.get("id") != target.get("id")


def can_manage_factories(user) -> bool:
    return is_top_level_admin(user)


def would_leave_active_admin(data: dict, target_id: str, new_role: str, is_active: bool) -> bool:
    return not any(
        u.get("is_active") and u.get("system_role") in TOP_LEVEL_ROLES
        for u in data.get("users", [])
        if u.get("id") != target_id
    ) and (new_role not in TOP_LEVEL_ROLES or not is_active)
