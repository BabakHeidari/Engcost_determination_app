import json

import pytest
from werkzeug.security import check_password_hash, generate_password_hash

import app as app_module
from utils.profile_authorization import can_access_module
from utils.profile_store import ProfileDataStore


PASSWORD = "Secure-Password-123"


def seed(store, user_id, role, active=True, title=""):
    return store.create_user({
        "id": user_id, "username": f"{user_id}@example.com", "email": f"{user_id}@example.com",
        "full_name": user_id, "system_role": role, "job_title": title, "access_grants": [],
        "is_active": active, "must_change_password": False,
        "password_hash": generate_password_hash(PASSWORD), "password_scheme": "werkzeug", "revision": 1,
    })


@pytest.fixture
def managed_app(tmp_path):
    path = tmp_path / "app_data.json"
    store = ProfileDataStore(path)
    store.initialize({})
    store.create_factory({"id": "fac_active", "code": "A", "name": "فعال", "is_active": True})
    store.create_factory({"id": "fac_inactive", "code": "I", "name": "غیرفعال", "is_active": False})
    seed(store, "usr_it", "IT_ADMIN")
    seed(store, "usr_finance", "FINANCE_ECONOMIC_ADMIN")
    seed(store, "usr_user", "USER", title="مدیر IT")
    app_module.app.config.update(TESTING=True, APP_DATA_FILE=str(path), SECRET_KEY="test")
    return app_module.app, path


def client_as(app, user_id):
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user_id
    return client


def revision(path, user_id):
    return ProfileDataStore(path).get_user_by_id(user_id)["revision"]


@pytest.mark.parametrize("actor", ["usr_it", "usr_finance"])
def test_peer_roles_equally_edit_ordinary_user_and_job_title_has_no_authority(managed_app, actor):
    app, path = managed_app
    response = client_as(app, actor).patch("/api/profile/users/usr_user", json={
        "expected_revision": revision(path, "usr_user"), "job_title": "مدیر کل IT",
        "access_grants": [{"scope_type": "FACTORY", "factory_id": "fac_active",
                           "module": "product", "permissions": ["WRITE", "READ", "READ"]}],
    })
    assert response.status_code == 200
    user = ProfileDataStore(path).get_user_by_id("usr_user")
    assert user["job_title"] == "مدیر کل IT"
    assert user["access_grants"][0]["permissions"] == ["READ", "WRITE"]
    assert can_access_module(user, "profile") is False


def test_user_cannot_edit_and_unknown_or_inactive_grants_fail_closed(managed_app):
    app, path = managed_app
    payload = {"expected_revision": revision(path, "usr_user"), "job_title": "admin"}
    assert client_as(app, "usr_user").patch("/api/profile/users/usr_it", json=payload).status_code == 400
    admin = client_as(app, "usr_it")
    for factory_id in ("missing", "fac_inactive"):
        response = admin.patch("/api/profile/users/usr_user", json={
            "expected_revision": revision(path, "usr_user"),
            "access_grants": [{"scope_type": "FACTORY", "factory_id": factory_id,
                               "module": "product", "permissions": ["READ"]}],
        })
        assert response.status_code == 400


def test_peer_sensitive_changes_and_last_admin_guarantee(managed_app):
    app, path = managed_app
    own = client_as(app, "usr_it").patch("/api/profile/users/usr_it", json={
        "expected_revision": revision(path, "usr_it"), "is_active": False,
    })
    assert own.status_code == 400
    peer = client_as(app, "usr_finance").patch("/api/profile/users/usr_it", json={
        "expected_revision": revision(path, "usr_it"), "system_role": "USER", "access_grants": [],
    })
    assert peer.status_code == 200
    last = client_as(app, "usr_finance").patch("/api/profile/users/usr_finance", json={
        "expected_revision": revision(path, "usr_finance"), "job_title": "توضیح مجاز",
    })
    assert last.status_code == 200
    forbidden = client_as(app, "usr_finance").patch("/api/profile/users/usr_finance", json={
        "expected_revision": revision(path, "usr_finance"), "system_role": "USER",
    })
    assert forbidden.status_code == 400


def test_password_reset_is_separate_safe_and_stale_edits_conflict(managed_app):
    app, path = managed_app
    old_revision = revision(path, "usr_user")
    response = client_as(app, "usr_it").post("/api/profile/users/usr_user/password-reset", json={
        "password": "Replacement-Password-456", "password_confirmation": "Replacement-Password-456",
        "expected_revision": old_revision,
    })
    assert response.status_code == 200
    assert "password" not in json.dumps(response.get_json()).casefold()
    raw = ProfileDataStore(path).get_user_by_id("usr_user", include_secret=True)
    assert check_password_hash(raw["password_hash"], "Replacement-Password-456")
    assert not check_password_hash(raw["password_hash"], PASSWORD)
    assert raw["must_change_password"] is True and raw["password_changed_at"]
    event = ProfileDataStore(path).load_data()["audit_events"][-1]
    assert event["action"] == "user.password_reset" and "password_hash" not in json.dumps(event)
    stale = client_as(app, "usr_it").patch("/api/profile/users/usr_user", json={
        "expected_revision": old_revision, "full_name": "از دست رفته",
    })
    assert stale.status_code == 409


def test_deactivation_blocks_login_and_peer_can_reactivate(managed_app):
    app, path = managed_app
    admin = client_as(app, "usr_it")
    assert admin.patch("/api/profile/users/usr_user", json={
        "expected_revision": revision(path, "usr_user"), "is_active": False,
    }).status_code == 200
    login = app.test_client().post("/login", data={"username": "usr_user@example.com", "password": PASSWORD})
    assert login.status_code == 200
    assert admin.patch("/api/profile/users/usr_user", json={
        "expected_revision": revision(path, "usr_user"), "is_active": True,
    }).status_code == 200
    assert app.test_client().post("/login", data={
        "username": "usr_user@example.com", "password": PASSWORD,
    }).location.endswith("/workdesk")
