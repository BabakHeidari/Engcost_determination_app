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
