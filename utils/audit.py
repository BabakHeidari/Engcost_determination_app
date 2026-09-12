"""Canonical business-audit helpers shared by storage and presentation."""

from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone

from utils.module_registry import GRANTABLE_MODULES
from utils.profile_authorization import LEVEL_RANK, PERMISSION_ORDER, SCOPE_TYPES


AUDIT_ACTION_LABELS = {
    "USER_CREATED": "ایجاد کاربر",
    "USER_UPDATED": "ویرایش کاربر",
    "SYSTEM_ROLE_CHANGED": "تغییر نقش سامانه",
    "JOB_TITLE_CHANGED": "تغییر عنوان شغلی",
    "ACCESS_GRANTS_CHANGED": "تغییر دسترسی‌ها",
    "USER_ACTIVATED": "فعال‌سازی کاربر",
    "USER_DEACTIVATED": "غیرفعال‌سازی کاربر",
    "PASSWORD_CHANGED": "تغییر گذرواژه",
    "PASSWORD_RESET_BY_ADMIN": "بازنشانی گذرواژه توسط مدیر",
    "FACTORY_CREATED": "ایجاد کارخانه",
}
FORBIDDEN_AUDIT_KEY_PARTS = (
    "password", "credential", "secret", "token", "session", "authorization", "cookie",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def access_level(permissions) -> str:
    if not isinstance(permissions, list):
        return "NONE"
    highest = max((PERMISSION_ORDER.index(item) for item in permissions if item in PERMISSION_ORDER), default=-1)
    return "NONE" if highest < 0 else PERMISSION_ORDER[highest]


def summarize_grant_changes(before, after) -> list[dict]:
    """Return deterministic explicit grant changes without materializing policy grants."""
    def indexed(grants):
        result = {}
        for grant in grants:
            if not isinstance(grant, dict) or grant.get("module") not in GRANTABLE_MODULES:
                continue
            key = (grant.get("scope_type"), grant.get("factory_id"), grant["module"])
            result[key] = access_level(grant.get("permissions"))
        return result

    old, new = indexed(before), indexed(after)
    changes = []
    for scope, factory_id, module_id in sorted(set(old) | set(new), key=lambda key: (key[0] or "", key[1] or "", key[2])):
        before_level, after_level = old.get((scope, factory_id, module_id), "NONE"), new.get((scope, factory_id, module_id), "NONE")
        if before_level != after_level:
            changes.append({"scope_type": scope, "factory_id": factory_id, "module_id": module_id,
                            "before": before_level, "after": after_level})
    return changes


def new_event(actor_user_id, action, target_type, target_id, *, changes=None,
              factory_id=None, module_id=None, occurred_at=None) -> dict:
    event = {
        "id": f"aud_{uuid.uuid4().hex}", "occurred_at": occurred_at or utc_now(),
        "actor_user_id": actor_user_id, "target_type": target_type,
        "target_id": target_id, "action": action,
    }
    if factory_id is not None:
        event["factory_id"] = factory_id
    if module_id is not None:
        if module_id not in GRANTABLE_MODULES:
            raise ValueError("Audit module_id is not grantable")
        event["module_id"] = module_id
    if changes:
        event["changes"] = copy.deepcopy(changes)
    validate_safe_event(event)
    return event


def validate_safe_event(event) -> None:
    if not isinstance(event, dict):
        raise ValueError("Audit event must be an object")
    module_id = event.get("module_id")
    if module_id is not None and module_id not in GRANTABLE_MODULES:
        raise ValueError("Audit module_id is not canonical")

    def inspect(value):
        if isinstance(value, dict):
            for key, child in value.items():
                normalized = str(key).casefold()
                if any(part in normalized for part in FORBIDDEN_AUDIT_KEY_PARTS):
                    raise ValueError("Audit event contains forbidden secret metadata")
                if normalized == "module_id" and child not in GRANTABLE_MODULES:
                    raise ValueError("Audit module_id is not canonical")
                inspect(child)
        elif isinstance(value, list):
            for child in value:
                inspect(child)
    inspect(event)
    if event.get("action") == "ACCESS_GRANTS_CHANGED":
        grants = event.get("changes", {}).get("grants") if isinstance(event.get("changes"), dict) else None
        if not isinstance(grants, list) or not grants:
            raise ValueError("Access-change audit requires a non-empty normalized summary")
        for item in grants:
            if (not isinstance(item, dict) or item.get("scope_type") not in SCOPE_TYPES
                    or item.get("before") not in LEVEL_RANK or item.get("after") not in LEVEL_RANK):
                raise ValueError("Access-change audit summary is invalid")
