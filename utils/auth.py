"""Authentication backed exclusively by the canonical profile JSON store."""

from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass
from functools import wraps

from flask import abort, current_app, g, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from utils.profile_store import ProfileDataStore, ProfileStoreError
from utils.profile_authorization import has_access, is_top_level_admin


MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 256


@dataclass(frozen=True)
class AuthenticationResult:
    user: dict
    must_change_password: bool


def get_profile_store() -> ProfileDataStore:
    settings = dict(os.environ)
    settings.update({key: value for key, value in current_app.config.items() if key.startswith("APP_DATA_")})
    return ProfileDataStore.from_environment(current_app.instance_path, settings)


def validate_password(password: str) -> None:
    if not isinstance(password, str):
        raise ValueError("گذرواژه نامعتبر است.")
    if not password.strip():
        raise ValueError("گذرواژه نمی‌تواند خالی یا فقط شامل فاصله باشد.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"گذرواژه باید حداقل {MIN_PASSWORD_LENGTH} نویسه داشته باشد.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"گذرواژه نباید بیش از {MAX_PASSWORD_LENGTH} نویسه داشته باشد.")


def set_password(user: dict, plaintext_password: str) -> None:
    validate_password(plaintext_password)
    user["password_hash"] = generate_password_hash(plaintext_password)
    user["password_scheme"] = "werkzeug"


def check_password(user: dict, plaintext_password: str) -> bool:
    if not isinstance(plaintext_password, str) or len(plaintext_password) > MAX_PASSWORD_LENGTH:
        return False
    stored_hash = user.get("password_hash")
    if not isinstance(stored_hash, str) or not stored_hash:
        return False
    if user.get("password_scheme") == "legacy_sha256":
        candidate = hashlib.sha256(plaintext_password.encode("utf-8")).hexdigest()
        return hmac.compare_digest(stored_hash.casefold(), candidate)
    try:
        return check_password_hash(stored_hash, plaintext_password)
    except (ValueError, TypeError):
        return False


def authenticate(email: str, password: str) -> AuthenticationResult | None:
    if not isinstance(email, str) or not isinstance(password, str):
        return None
    user = get_profile_store().authenticate_user(email, password, check_password)
    if user is None:
        return None
    return AuthenticationResult(user, bool(user.get("must_change_password")))


def load_current_user() -> dict | None:
    user_id = session.get("user_id")
    if not isinstance(user_id, str):
        return None
    try:
        user = get_profile_store().get_user_by_id(user_id)
    except ProfileStoreError:
        return None
    if user is None or not user.get("is_active", False):
        return None
    return user


def login_required(view):
    @wraps(view)
    def decorated_function(*args, **kwargs):
        user = load_current_user()
        if user is None:
            session.clear()
            return redirect(url_for("auth.login"))
        g.current_user = user
        if user.get("must_change_password") and request.endpoint != "auth.change_password":
            return redirect(url_for("auth.change_password"))
        return view(*args, **kwargs)
    return decorated_function


def require_access(module, required_level="READ", *, scope_type="GLOBAL"):
    """Enforce a global route action after ``login_required`` loaded the user."""
    def decorator(view):
        @wraps(view)
        def protected(*args, **kwargs):
            if not has_access(g.current_user, module, required_level, scope_type=scope_type):
                abort(403)
            return view(*args, **kwargs)
        return protected
    return decorator


def require_top_level_admin(view):
    """Gate administrative actions independently of payloads and grants."""
    @wraps(view)
    def protected(*args, **kwargs):
        if not is_top_level_admin(g.current_user):
            abort(403)
        return view(*args, **kwargs)
    return protected
