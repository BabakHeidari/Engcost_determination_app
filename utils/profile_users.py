"""Server-side validation for canonical access-model user creation."""

from __future__ import annotations

import re
import unicodedata

from werkzeug.security import generate_password_hash

from utils.auth import validate_password
from utils.profile_authorization import SYSTEM_ROLES, TOP_LEVEL_ROLES
from utils.profile_store import ProfileDataValidationError, normalize_email


EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
MAX_FULL_NAME_LENGTH = 120
MAX_JOB_TITLE_LENGTH = 160
FORBIDDEN_CLIENT_FIELDS = {
    "id", "user_id", "password_hash", "password_scheme", "created_by",
    "created_by_id", "created_by_user_id", "actor_id", "permissions", "permission_overrides",
}
EDITABLE_USER_FIELDS = {
    "full_name", "email", "job_title", "system_role", "access_grants",
    "is_active", "expected_revision",
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
    system_role = payload.get("system_role")
    if system_role not in SYSTEM_ROLES:
        raise ProfileDataValidationError("نقش نامعتبر است.")
    job_title = payload.get("job_title", "")
    if not isinstance(job_title, str):
        raise ProfileDataValidationError("عنوان شغلی نامعتبر است.")
    job_title = unicodedata.normalize("NFC", job_title).strip()
    if len(job_title) > MAX_JOB_TITLE_LENGTH:
        raise ProfileDataValidationError("عنوان شغلی نباید بیش از ۱۶۰ نویسه باشد.")
    access_grants = payload.get("access_grants", [])
    if not isinstance(access_grants, list):
        raise ProfileDataValidationError("فهرست دسترسی‌ها نامعتبر است.")
    if system_role in TOP_LEVEL_ROLES:
        access_grants = []
    password = payload.get("initial_password")
    if password != payload.get("initial_password_confirmation"):
        raise ProfileDataValidationError("گذرواژه و تکرار آن یکسان نیستند.")
    try:
        validate_password(password)
    except ValueError as exc:
        raise ProfileDataValidationError(str(exc)) from None
    return {
        "username": email, "email": email, "email_normalized": email,
        "full_name": full_name, "system_role": system_role, "job_title": job_title,
        "access_grants": access_grants, "password_hash": generate_password_hash(password),
    }


def prepare_user_update(payload: object) -> tuple[dict, int]:
    """Validate editable account fields without accepting derived/secret data."""
    if not isinstance(payload, dict) or not payload:
        raise ProfileDataValidationError("داده‌های ارسالی نامعتبر است.")
    unknown = set(payload) - EDITABLE_USER_FIELDS
    if unknown:
        raise ProfileDataValidationError("فیلد غیرمجاز ارسال شده است.")
    revision = payload.get("expected_revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise ProfileDataValidationError("نسخه رکورد کاربر نامعتبر است.")
    changes = {key: value for key, value in payload.items() if key != "expected_revision"}
    if "full_name" in changes:
        value = changes["full_name"]
        if not isinstance(value, str) or not (value := unicodedata.normalize("NFC", value).strip()) or len(value) > MAX_FULL_NAME_LENGTH:
            raise ProfileDataValidationError("نام و نام خانوادگی باید بین ۱ تا ۱۲۰ نویسه باشد.")
        changes["full_name"] = value
    if "email" in changes:
        value = normalize_email(changes["email"])
        if len(value) > 254 or not EMAIL_PATTERN.fullmatch(value):
            raise ProfileDataValidationError("ایمیل نامعتبر است.")
        changes["email"] = value
    if "job_title" in changes:
        value = changes["job_title"]
        if not isinstance(value, str) or len(value := unicodedata.normalize("NFC", value).strip()) > MAX_JOB_TITLE_LENGTH:
            raise ProfileDataValidationError("عنوان شغلی نامعتبر است.")
        changes["job_title"] = value
    if "system_role" in changes and changes["system_role"] not in SYSTEM_ROLES:
        raise ProfileDataValidationError("نقش نامعتبر است.")
    if "access_grants" in changes and not isinstance(changes["access_grants"], list):
        raise ProfileDataValidationError("فهرست دسترسی‌ها نامعتبر است.")
    if "is_active" in changes and not isinstance(changes["is_active"], bool):
        raise ProfileDataValidationError("وضعیت حساب نامعتبر است.")
    return changes, revision


def prepare_password_reset(payload: object) -> tuple[str, int]:
    if not isinstance(payload, dict) or set(payload) != {"password", "password_confirmation", "expected_revision"}:
        raise ProfileDataValidationError("داده‌های بازنشانی گذرواژه نامعتبر است.")
    if payload["password"] != payload["password_confirmation"]:
        raise ProfileDataValidationError("گذرواژه و تکرار آن یکسان نیستند.")
    revision = payload["expected_revision"]
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise ProfileDataValidationError("نسخه رکورد کاربر نامعتبر است.")
    try:
        validate_password(payload["password"])
    except ValueError as exc:
        raise ProfileDataValidationError(str(exc)) from None
    return generate_password_hash(payload["password"]), revision
