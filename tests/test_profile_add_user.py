import json
import threading
from unittest import mock

import pytest
from werkzeug.security import check_password_hash, generate_password_hash

import app as app_module
from utils.profile_store import ProfileDataConflictError, ProfileDataStore
from utils.profile_users import prepare_new_user


ROLES = {}


def seed_user(store, user_id, role, factory_id=None):
    store.create_user({
        "id": user_id, "username": user_id, "email": f"{user_id}@example.com",
        "full_name": user_id, "system_role": role, "job_title": "", "access_grants": [], "is_active": True,
        "must_change_password": False, "password_hash": generate_password_hash("Admin-Password-123"),
        "password_scheme": "werkzeug", "revision": 1,
    })


@pytest.fixture
def add_user_app(tmp_path):
    path = tmp_path / "app_data.json"
    store = ProfileDataStore(path)
    store.initialize(ROLES)
    store.create_factory({"id": "fac_a", "code": "A", "name": "الف", "is_active": True})
    store.create_factory({"id": "fac_b", "code": "B", "name": "ب", "is_active": True})
    seed_user(store, "usr_admin", "IT_ADMIN")
    seed_user(store, "usr_factory", "USER")
    seed_user(store, "usr_staff", "USER")
    app_module.app.config.update(TESTING=True, APP_DATA_FILE=str(path), SECRET_KEY="test")
    return app_module.app, path


def client_as(app, user_id):
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user_id
    return client


def payload(**changes):
    value = {
        "full_name": "کاربر جدید", "email": "NEW@Example.com", "system_role": "USER", "job_title": "کارشناس", "access_grants": [], "initial_password": "گذرواژه-اولیه-۱۲۳",
        "initial_password_confirmation": "گذرواژه-اولیه-۱۲۳",
    }
    value.update(changes)
    return value


def test_authorized_creation_stores_only_hash_and_safe_audit(add_user_app):
    app, path = add_user_app
    response = client_as(app, "usr_admin").post("/api/profile/users", json=payload())
    assert response.status_code == 201
    returned = response.get_json()["user"]
    assert "password_hash" not in returned and "initial_password" not in json.dumps(returned)
    data = ProfileDataStore(path).load_data()
    created = next(u for u in data["users"] if u["email"] == "new@example.com")
    assert created["password_hash"] != payload()["initial_password"]
    assert check_password_hash(created["password_hash"], payload()["initial_password"])
    assert created["must_change_password"] is True and created["created_by_id"] == "usr_admin"
    event = data["audit_events"][-1]
    assert event["action"] == "user.created"
    assert "password" not in json.dumps(event).casefold()


@pytest.mark.parametrize("user_id,changes,status", [
    ("usr_staff", {}, 400),
    ("usr_admin", {"initial_password_confirmation": "different"}, 400),
    ("usr_admin", {"initial_password": "   ", "initial_password_confirmation": "   "}, 400),
    ("usr_admin", {"system_role": "Unknown"}, 400),
    ("usr_admin", {"access_grants": [{"scope_type": "FACTORY", "factory_id": "missing", "module": "product", "permissions": ["READ"]}]}, 400),
    ("usr_factory", {}, 400),
])
def test_authorization_and_validation_failures(add_user_app, user_id, changes, status):
    response = client_as(add_user_app[0], user_id).post("/api/profile/users", json=payload(**changes))
    assert response.status_code == status


def test_duplicate_and_hostile_identity_fields_are_rejected(add_user_app):
    web = client_as(add_user_app[0], "usr_admin")
    assert web.post("/api/profile/users", json=payload()).status_code == 201
    assert web.post("/api/profile/users", json=payload()).status_code == 409
    assert web.post("/api/profile/users", json=payload(email="two@example.com", id="chosen")).status_code == 400
    assert web.post("/api/profile/users", json=payload(email="three@example.com", created_by_id="usr_staff")).status_code == 400


def test_client_actor_id_is_rejected(add_user_app):
    app, path = add_user_app
    response = client_as(app, "usr_admin").post(
        "/api/profile/users", json=payload(actor_id="usr_staff")
    )
    assert response.status_code == 400
    assert not any(u["email"] == "new@example.com" for u in ProfileDataStore(path).load_data()["users"])


def test_concurrent_duplicate_email_creates_exactly_one(add_user_app):
    path = add_user_app[1]
    barrier = threading.Barrier(2)
    outcomes = []
    candidate = prepare_new_user(payload())
    def create():
        barrier.wait()
        try:
            ProfileDataStore(path).create_user_as_actor("usr_admin", candidate)
            outcomes.append("created")
        except ProfileDataConflictError:
            outcomes.append("conflict")
    threads = [threading.Thread(target=create) for _ in range(2)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    assert sorted(outcomes) == ["conflict", "created"]
    assert sum(u["email"] == "new@example.com" for u in ProfileDataStore(path).load_data()["users"]) == 1


def test_new_user_login_and_first_password_change(add_user_app):
    app, _ = add_user_app
    web = client_as(app, "usr_admin")
    assert web.post("/api/profile/users", json=payload()).status_code == 201
    web.get("/logout")
    login = web.post("/login", data={"username": "new@example.com", "password": payload()["initial_password"]})
    assert login.location.endswith("/change-password")
    changed = web.post("/change-password", data={"password": "گذرواژه-جدید-۴۵۶", "password_confirmation": "گذرواژه-جدید-۴۵۶"})
    assert changed.location.endswith("/workdesk")


def test_failed_write_preserves_user_and_audit_document(add_user_app):
    path = add_user_app[1]
    before = path.read_bytes()
    with mock.patch("utils.profile_store.os.replace", side_effect=OSError("disk failure")):
        with pytest.raises(OSError):
            ProfileDataStore(path).create_user_as_actor("usr_admin", prepare_new_user(payload()))
    assert path.read_bytes() == before


def test_modal_password_contract_and_passwords_are_not_prefilled(add_user_app):
    body = client_as(add_user_app[0], "usr_admin").get("/profile/profile").get_data(as_text=True)
    assert body.count('type="password"') >= 2
    assert body.count('autocomplete="new-password"') >= 2
    assert 'name="initial_password"' in body and 'name="initial_password_confirmation"' in body
    assert "localStorage" not in body and "sessionStorage" not in body
    assert "hidden.bs.modal" in body and "clearPasswords" in body
