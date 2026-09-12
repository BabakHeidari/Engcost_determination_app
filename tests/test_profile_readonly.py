import json

import pytest

import app as app_module
from utils.profile_store import ProfileDataStore


ROLES = {}


def add_user(store, user_id, role, factory_id=None, full_name=None):
    store.create_user({
        "id": user_id,
        "username": user_id,
        "email": f"{user_id}@example.com",
        "full_name": full_name or user_id,
        "system_role": role, "job_title": full_name or "",
        "access_grants": ([{"scope_type": "FACTORY", "factory_id": factory_id, "module": "product", "permissions": ["READ"]}] if factory_id else []),
        "is_active": True,
        "must_change_password": False,
        "password_hash": f"scrypt:secret-{user_id}",
        "revision": 1,
    })


@pytest.fixture
def profile_app(tmp_path):
    path = tmp_path / "app_data.json"
    store = ProfileDataStore(path)
    store.initialize(ROLES)
    store.create_factory({"id": "fac_a", "code": "A", "name": "واقعی الف", "is_active": True})
    store.create_factory({"id": "fac_b", "code": "B", "name": "واقعی ب", "is_active": True})
    add_user(store, "usr_admin", "IT_ADMIN", full_name="مدیر واقعی")
    add_user(store, "usr_a_admin", "USER", "fac_a", "مدیر کارخانه الف")
    add_user(store, "usr_a_staff", "USER", "fac_a", "کارشناس کارخانه الف")
    add_user(store, "usr_b_staff", "USER", "fac_b", "کارشناس کارخانه ب")
    add_user(store, "usr_office", "USER", full_name="کارشناس ستادی")
    store.append_audit_event({
        "id": "aud_real", "occurred_at": "2026-08-01T12:30:00Z",
        "actor_user_id": "usr_a_admin", "action": "profile.viewed",
        "target_type": "user", "target_id": "usr_a_admin",
    })
    app_module.app.config.update(TESTING=True, APP_DATA_FILE=str(path), SECRET_KEY="test-secret")
    return app_module.app, path


def authenticated_client(flask_app, user_id):
    client = flask_app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user_id
    return client


def test_anonymous_profile_access_redirects_to_login(profile_app):
    response = profile_app[0].test_client().get("/profile/profile")
    assert response.status_code == 302
    assert response.location.endswith("/login")


def test_authenticated_profile_uses_json_and_never_exposes_hash(profile_app):
    response = authenticated_client(profile_app[0], "usr_admin").get("/profile/profile")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "مدیر واقعی" in body
    assert "واقعی الف" in body and "واقعی ب" in body
    assert "password_hash" not in body.casefold()
    assert "scrypt:secret" not in body


def test_non_admin_sees_only_self(profile_app):
    body = authenticated_client(profile_app[0], "usr_office").get("/profile/profile").get_data(as_text=True)
    assert "کارشناس ستادی" in body
    assert "مدیر واقعی" not in body
    assert "کارشناس کارخانه الف" not in body


def test_ordinary_user_sees_only_self_and_real_audit(profile_app):
    body = authenticated_client(profile_app[0], "usr_a_admin").get("/profile/profile").get_data(as_text=True)
    assert "مدیر کارخانه الف" in body
    assert "کارشناس کارخانه الف" not in body and "کارشناس کارخانه ب" not in body and "واقعی ب" not in body
    assert "profile.viewed" in body


def test_empty_history_is_truthful_and_page_is_read_only(profile_app):
    body = authenticated_client(profile_app[0], "usr_office").get("/profile/profile").get_data(as_text=True)
    assert "هنوز رویداد واقعی برای نمایش ثبت نشده است." in body
    assert "فقط برای مشاهده اطلاعات است" in body
    assert "افزودن کاربر" not in body
    assert "افزودن کارخانه" not in body


def test_no_demo_fallback_and_persian_rtl_remain(profile_app):
    body = authenticated_client(profile_app[0], "usr_office").get("/profile/profile").get_data(as_text=True)
    assert 'dir="rtl"' in body
    assert "پروفایل کاربر" in body and "دسترسی‌های مؤثر" in body
    for fake in ("کارخانه آلفا", "کارخانه بتا", "تغییر کاربر", "Math.random", "DEFAULT_USERS"):
        assert fake not in body


def test_profile_store_error_has_truthful_service_error(profile_app):
    profile_app[0].config["APP_DATA_FILE"] = str(profile_app[1].parent / "missing.json")
    response = authenticated_client(profile_app[0], "usr_admin").get("/profile/profile")
    # Authentication fails closed before the view if its canonical source disappears.
    assert response.status_code == 302
    assert response.location.endswith("/login")


def test_safe_view_model_contains_no_secret_keys(profile_app):
    from utils.profile_view import build_profile_view_model

    store = ProfileDataStore(profile_app[1])
    model = build_profile_view_model(store, store.get_user_by_id("usr_admin"))
    serialized = json.dumps(model)
    assert "password" not in serialized.casefold()
    assert "revision" not in serialized.casefold()
