"""Validation for Profile factory-management requests."""

from __future__ import annotations

from utils.profile_store import ProfileDataValidationError


FACTORY_CREATE_FIELDS = frozenset({"code", "name", "location"})


def prepare_new_factory(payload):
    """Accept descriptive create fields only; identity and authority stay server-side."""
    if not isinstance(payload, dict):
        raise ProfileDataValidationError("اطلاعات کارخانه نامعتبر است.")
    unexpected = set(payload) - FACTORY_CREATE_FIELDS
    if unexpected:
        raise ProfileDataValidationError("فیلدهای ارسالی برای ایجاد کارخانه مجاز نیستند.")
    return {key: payload.get(key) for key in FACTORY_CREATE_FIELDS}
