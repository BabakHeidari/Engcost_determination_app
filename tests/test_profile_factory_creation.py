import json
import threading
from unittest import mock

import pytest
from werkzeug.security import generate_password_hash

import app as app_module
from utils.profile_authorization import can_access_module
from utils.profile_store import ProfileDataConflictError, ProfileDataStore, validate_data


def seed_user(store, user_id, role, *, job_title=""):
    store.create_user({
        "id": user_id, "username": user_id, "email": f"{user_id}@example.com",
        "full_name": user_id, "system_role": role, "job_title": job_title,
        "access_grants": [], "is_active": True, "must_change_password": False,
        "password_hash": generate_password_hash("Admin-Password-123"),
        "password_scheme": "werkzeug", "revision": 1,
    })


@pytest.fixture
def factory_app(tmp_path):
    path = tmp_path / "app_data.json"
    store = ProfileDataStore(path)
    store.initialize({})
    seed_user(store, "usr_it", "IT_ADMIN")
    seed_user(store, "usr_finance", "FINANCE_ECONOMIC_ADMIN")
    seed_user(store, "usr_user", "USER", job_title="مدیر فناوری اطلاعات")
    app_module.app.config.update(TESTING=True, APP_DATA_FILE=str(path), SECRET_KEY="test")
    return app_module.app, path


def client_as(app, user_id):
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user_id
    return client


def payload(**changes):
    value = {"code": "F4", "name": "کارخانه تهران", "location": "تهران"}
    value.update(changes)
    return value


@pytest.mark.parametrize("actor_id", ["usr_it", "usr_finance"])
def test_top_level_admins_create_factory_with_identical_behavior(factory_app, actor_id):
    app, path = factory_app
    response = client_as(app, actor_id).post("/api/profile/factories", json=payload(code=f"{actor_id}-F"))
    assert response.status_code == 201
    factory = response.get_json()["factory"]
    assert factory["id"] == factory["code"] == f"{actor_id}-F"
    assert set(factory) == {"id", "code", "name", "location", "is_active"}
    persisted = next(f for f in ProfileDataStore(path).load_data()["factories"] if f["id"] == factory["id"])
    assert persisted["created_by_id"] == actor_id and persisted["is_active"] is True
    assert persisted["created_at"].endswith("Z")


def test_user_and_job_title_cannot_authorize_api_or_ui(factory_app):
    app, path = factory_app
    web = client_as(app, "usr_user")
    assert web.post("/api/profile/factories", json=payload()).status_code == 400
    assert ProfileDataStore(path).list_factories() == []
    assert "افزودن کارخانه جدید" not in web.get("/profile/profile").get_data(as_text=True)


@pytest.mark.parametrize("hostile", [
    {"actor_id": "usr_it"}, {"created_by_id": "usr_it"}, {"id": "chosen"},
    {"is_active": False}, {"user_id": "usr_it"},
])
def test_client_identity_and_internal_fields_are_rejected(factory_app, hostile):
    app, path = factory_app
    assert client_as(app, "usr_it").post("/api/profile/factories", json=payload(**hostile)).status_code == 400
    assert ProfileDataStore(path).list_factories() == []


def test_factory_persists_across_store_and_application_reload(factory_app):
    app, path = factory_app
    assert client_as(app, "usr_it").post("/api/profile/factories", json=payload()).status_code == 201
    reloaded_store = ProfileDataStore(path)
    assert reloaded_store.list_factories()[0]["name"] == "کارخانه تهران"
    body = client_as(app, "usr_it").get("/profile/profile").get_data(as_text=True)
    assert 'value="F4"' in body and "کارخانه تهران (F4)" in body


def test_duplicate_code_id_and_normalized_display_name_are_rejected_inside_lock(factory_app):
    app, path = factory_app
    web = client_as(app, "usr_it")
    assert web.post("/api/profile/factories", json=payload()).status_code == 201
    assert web.post("/api/profile/factories", json=payload(name="نام دیگر")).status_code == 409
    assert web.post("/api/profile/factories", json=payload(code="F5", name="  کارخانه   تهران  ")).status_code == 409
    assert len(ProfileDataStore(path).list_factories()) == 1


def test_concurrent_factory_creation_has_one_winner_and_no_lost_update(factory_app):
    path = factory_app[1]
    barrier = threading.Barrier(2)
    outcomes = []

    def create():
        barrier.wait()
        try:
            ProfileDataStore(path).create_factory_as_actor("usr_it", payload())
            outcomes.append("created")
        except ProfileDataConflictError:
            outcomes.append("conflict")

    threads = [threading.Thread(target=create) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["conflict", "created"]
    data = ProfileDataStore(path).load_data()
    assert len(data["factories"]) == 1 and len([e for e in data["audit_events"] if e["action"] == "FACTORY_CREATED"]) == 1


def test_factory_and_secret_free_audit_are_atomic(factory_app):
    app, path = factory_app
    assert client_as(app, "usr_it").post("/api/profile/factories", json=payload()).status_code == 201
    data = ProfileDataStore(path).load_data()
    event = data["audit_events"][-1]
    assert event["action"] == "FACTORY_CREATED" and event["factory_id"] == "F4"
    assert "password" not in json.dumps(event, ensure_ascii=False).casefold()
    before = path.read_bytes()
    with mock.patch("utils.profile_store.os.replace", side_effect=OSError("disk failure")):
        with pytest.raises(OSError):
            ProfileDataStore(path).create_factory_as_actor("usr_it", payload(code="F5", name="کارخانه قم"))
    assert path.read_bytes() == before
    validate_data(json.loads(path.read_text(encoding="utf-8")))


def test_new_factory_is_implicit_for_admins_and_denied_to_user(factory_app):
    app, path = factory_app
    client_as(app, "usr_it").post("/api/profile/factories", json=payload())
    data = ProfileDataStore(path).load_data()
    users = {user["id"]: user for user in data["users"]}
    assert can_access_module(users["usr_it"], "PRODUCT", "F4", "WRITE")
    assert can_access_module(users["usr_finance"], "PRODUCT", "F4", "WRITE")
    assert not can_access_module(users["usr_user"], "PRODUCT", "F4", "READ")
    assert all(user["access_grants"] == [] for user in users.values())


def test_admin_ui_uses_server_id_and_updates_factory_grant_options(factory_app):
    body = client_as(factory_app[0], "usr_it").get("/profile/profile").get_data(as_text=True)
    assert 'id="createFactoryModal"' in body
    assert 'name="code"' in body and 'name="name"' in body and 'name="location"' in body
    assert "crypto.randomUUID" not in body and "addFactoryOption(factory)" in body
    assert "grantTemplate" in body and "profile.create_factory" not in body
