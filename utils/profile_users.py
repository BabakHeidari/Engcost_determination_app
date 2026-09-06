"""Server-side policy and validation for Phase 6 user creation."""

from __future__ import annotations

import re
import unicodedata

from werkzeug.security import generate_password_hash

from utils.auth import validate_password
from utils.profile_store import ProfileDataValidationError, normalize_email


EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
MAX_FULL_NAME_LENGTH = 120
FORBIDDEN_CLIENT_FIELDS = {
    "id", "user_id", "password_hash", "password_scheme", "created_by",
    "created_by_id", "created_by_user_id", "permissions", "permission_overrides",
}


def prepare_new_user(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ProfileDataValidationError("داده‌های ارسالی نامعتبر است.")
    if FORBIDDEN_CLIENT_FIELDS.intersection(payload):
        raise ProfileDataValidationError("فیلد غیرمجاز ارسال شده است.")
    full_name = payload.get("full_name")
    if not isinstance(full_name, str):
        raise ProfileDataValidationError("نام و نام خانوادگی الزامی است.")
    full_name = unicodedata.normalize("NFC", full_name).strip()
    if not full_name or len(full_name) > MAX_FULL_NAME_LENGTH:
        raise ProfileDataValidationError("نام و نام خانوادگی باید بین ۱ تا ۱۲۰ نویسه باشد.")
    try:
        email = normalize_email(payload.get("email"))
    except ProfileDataValidationError:
        raise ProfileDataValidationError("ایمیل نامعتبر است.") from None
    if len(email) > 254 or not EMAIL_PATTERN.fullmatch(email):
        raise ProfileDataValidationError("ایمیل نامعتبر است.")
    role = payload.get("role")
    if not isinstance(role, str) or not role:
        raise ProfileDataValidationError("نقش نامعتبر است.")
    factory_id = payload.get("factory_id") or None
    if factory_id is not None and not isinstance(factory_id, str):
        raise ProfileDataValidationError("کارخانه نامعتبر است.")
    password = payload.get("initial_password")
    if password != payload.get("initial_password_confirmation"):
        raise ProfileDataValidationError("گذرواژه و تکرار آن یکسان نیستند.")
    try:
        validate_password(password)
    except ValueError as exc:
        raise ProfileDataValidationError(str(exc)) from None
    return {
        "username": email, "email": email, "full_name": full_name, "role": role,
        "factory_id": factory_id, "password_hash": generate_password_hash(password),
    }
