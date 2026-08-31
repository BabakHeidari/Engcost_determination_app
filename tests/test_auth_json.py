import json
import hashlib

import pytest
from werkzeug.security import generate_password_hash

import app as app_module
from utils.profile_store import ProfileDataStore


ROLES = {"IT Admin": {"scope": "global", "permissions": {}}}


@pytest.fixture
def client(tmp_path):
    path = tmp_path / "app_data.json"
    store = ProfileDataStore(path)
    store.initialize(ROLES)
    store.create_user({
        "id": "usr_active", "username": "user@example.com", "email": "user@example.com",
        "full_name": "کاربر", "role": "IT Admin", "factory_id": None, "is_active": True,
        "must_change_password": False, "password_hash": generate_password_hash("درست-Password-123"),
        "password_scheme": "werkzeug", "revision": 1,
    })
    store.create_user({
        "id": "usr_migrated", "username": "legacy@example.com", "email": "legacy@example.com",
        "role": "IT Admin", "factory_id": None, "is_active": True, "must_change_password": True,
        "password_hash": hashlib.sha256("Legacy-Password-123".encode("utf-8")).hexdigest(),
        "password_scheme": "legacy_sha256", "revision": 1,
    })
    store.create_user({
        "id": "usr_inactive", "username": "off@example.com", "email": "off@example.com",
        "role": "IT Admin", "factory_id": None, "is_active": False, "must_change_password": False,
        "password_hash": generate_password_hash("درست-Password-123"), "password_scheme": "werkzeug", "revision": 1,
    })
    store.create_user({
        "id": "usr_reset", "username": "reset@example.com", "email": "reset@example.com",
        "role": "IT Admin", "factory_id": None, "is_active": True, "must_change_password": True,
        "password_hash": generate_password_hash("Old-Password-123"), "password_scheme": "werkzeug", "revision": 1,
    })
    app_module.app.config.update(TESTING=True, APP_DATA_FILE=str(path), SECRET_KEY="test-secret")
    return app_module.app.test_client(), path


def login(client, email, password):
    return client.post("/login", data={"username": email, "password": password})


def test_login_normalization_session_safety_and_atomic_last_login(client):
    web, path = client
    before = ProfileDataStore(path).load_data()["metadata"]["revision"]
    response = login(web, "  USER@EXAMPLE.COM ", "درست-Password-123")
    assert response.status_code == 302 and response.location.endswith("/workdesk")
    with web.session_transaction() as session:
        assert dict(session) == {"user_id": "usr_active"}
    data = ProfileDataStore(path).load_data()
    assert data["metadata"]["revision"] == before + 1
    assert next(u for u in data["users"] if u["id"] == "usr_active")["last_login_at"]


@pytest.mark.parametrize("email,password", [
    ("user@example.com", "wrong-password"),
    ("off@example.com", "درست-Password-123"),
])
def test_wrong_password_and_inactive_user_fail(client, email, password):
    response = login(client[0], email, password)
    assert response.status_code == 200
    with client[0].session_transaction() as session:
        assert "user_id" not in session


def test_reset_required_password_change_and_old_password_rejected(client, caplog):
    web, path = client
    assert login(web, "reset@example.com", "Old-Password-123").location.endswith("/change-password")
    assert web.get("/workdesk").location.endswith("/change-password")
    response = web.post("/change-password", data={
        "password": "New-Password-456", "password_confirmation": "New-Password-456"
    })
    assert response.location.endswith("/workdesk")
    web.get("/logout")
    assert login(web, "reset@example.com", "Old-Password-123").status_code == 200
    assert login(web, "reset@example.com", "New-Password-456").location.endswith("/workdesk")
    raw = json.dumps(ProfileDataStore(path).list_users())
    assert "password_hash" not in raw.casefold()
    assert "New-Password-456" not in raw
    assert "New-Password-456" not in caplog.text


def test_existing_migrated_sha256_user_can_authenticate(client):
    response = login(client[0], "LEGACY@EXAMPLE.COM", "Legacy-Password-123")
    assert response.status_code == 302
    assert response.location.endswith("/change-password")


def test_legacy_file_cannot_override_canonical_store(client):
    assert "read_excel" not in __import__("utils.auth", fromlist=["x"]).__dict__
    assert login(client[0], "user@example.com", "درست-Password-123").status_code == 302


def test_missing_canonical_store_returns_setup_message_without_traceback(tmp_path):
    app_module.app.config.update(
        TESTING=True,
        APP_DATA_FILE=str(tmp_path / "missing.json"),
        SECRET_KEY="test-secret",
    )
    with app_module.app.test_client() as web:
        response = login(web, "admin", "admin")
    assert response.status_code == 503
    body = response.get_data(as_text=True)
    assert "اطلاعات کاربران هنوز منتقل نشده است" in body
    assert "ProfileStoreError" not in body
    assert "app_data.json" not in body
