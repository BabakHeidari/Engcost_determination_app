import json
import multiprocessing
import os
from pathlib import Path
from unittest import mock

import pytest

import utils.profile_store as profile_store

from utils.profile_store import (
    ProfileDataStore,
    ProfileDataValidationError,
    ProfileStoreNotInitializedError,
    public_user,
    validate_data,
)


ROLES = {"IT Admin": {"scope": "global", "permissions": {}}}


def document():
    return {
        "schema_version": 1,
        "metadata": {"revision": 1},
        "users": [],
        "factories": [],
        "role_permissions": ROLES.copy(),
        "user_permission_overrides": [],
        "audit_events": [],
    }


def write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def user(user_id="usr_1", email="admin@example.com", factory_id=None):
    return {
        "id": user_id,
        "email": email,
        "role": "IT Admin",
        "factory_id": factory_id,
        "password_hash": "scrypt:secret-hash-material",
    }


def concurrent_create(path, index):
    store = ProfileDataStore(path, lock_timeout=5)
    store.create_user(user(f"usr_{index}", f"user{index}@example.com"))


def test_valid_file_loads_and_returns_detached_data(tmp_path):
    path = tmp_path / "app_data.json"
    write(path, document())
    loaded = ProfileDataStore(path).load_data()
    loaded["users"].append({})
    assert ProfileDataStore(path).load_data()["users"] == []


def test_created_records_receive_safe_defaults(tmp_path):
    path = tmp_path / "app_data.json"
    write(path, document())
    created = ProfileDataStore(path).create_user(user())
    assert created["factory_id"] is None
    assert created["revision"] == 1
    assert "password_hash" not in created


def test_user_lookup_accepts_normalized_username(tmp_path):
    path = tmp_path / "app_data.json"
    write(path, document())
    values = user()
    values["username"] = "Named Admin"
    ProfileDataStore(path).create_user(values)
    found = ProfileDataStore(path).get_user_by_identifier("  NAMEDADMIN ")
    assert found["id"] == "usr_1"
    assert "password_hash" not in found


@pytest.mark.parametrize("bad", [[], {"schema_version": 99}, {"schema_version": 1}])
def test_invalid_schema_fails(bad):
    with pytest.raises(ProfileDataValidationError):
        validate_data(bad)


def test_duplicate_user_ids_fail():
    data = document()
    data["users"] = [user(), user(email="second@example.com")]
    with pytest.raises(ProfileDataValidationError, match="Duplicate user id"):
        validate_data(data)


def test_duplicate_normalized_emails_fail():
    data = document()
    data["users"] = [user(), user("usr_2", " ADMIN@EXAMPLE.COM ")]
    with pytest.raises(ProfileDataValidationError, match="Duplicate normalized user email"):
        validate_data(data)


def test_invalid_factory_reference_fails():
    data = document()
    data["users"] = [user(factory_id="fac_missing")]
    with pytest.raises(ProfileDataValidationError, match="unknown factory"):
        validate_data(data)


def test_plaintext_password_field_fails():
    data = document()
    data["users"] = [dict(user(), password="never")]
    with pytest.raises(ProfileDataValidationError, match="Plaintext password"):
        validate_data(data)


def test_atomic_write_preserves_valid_json(tmp_path):
    path = tmp_path / "app_data.json"
    write(path, document())
    ProfileDataStore(path).create_factory({"id": "fac_1", "code": "F1", "name": "کارخانه"})
    with path.open(encoding="utf-8") as stream:
        assert json.load(stream)["factories"][0]["id"] == "fac_1"
    assert not list(tmp_path.glob(".*.tmp"))


def test_failed_replace_preserves_previous_file(tmp_path):
    path = tmp_path / "app_data.json"
    write(path, document())
    before = path.read_bytes()
    store = ProfileDataStore(path)
    with mock.patch("utils.profile_store.os.replace", side_effect=OSError("disk failure")):
        with pytest.raises(OSError, match="disk failure"):
            store.create_factory({"id": "fac_1", "code": "F1"})
    assert path.read_bytes() == before
    assert validate_data(json.loads(path.read_text(encoding="utf-8")))


def test_concurrent_writes_do_not_lose_updates(tmp_path):
    path = tmp_path / "app_data.json"
    write(path, document())
    processes = [multiprocessing.Process(target=concurrent_create, args=(path, index)) for index in range(8)]
    for process in processes:
        process.start()
    for process in processes:
        process.join(10)
        assert process.exitcode == 0
    assert len(ProfileDataStore(path).list_users()) == 8


def test_platform_lock_adapter_round_trip(tmp_path):
    descriptor = os.open(tmp_path / "adapter.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        profile_store._prepare_lock_file(descriptor)
        profile_store._acquire_file_lock(descriptor, exclusive=True)
        profile_store._release_file_lock(descriptor)
    finally:
        os.close(descriptor)


def test_windows_directory_sync_does_not_open_directory(tmp_path):
    with mock.patch.object(profile_store.os, "name", "nt"), mock.patch.object(
        profile_store.os, "open"
    ) as open_mock:
        profile_store._sync_parent_directory(tmp_path)
    open_mock.assert_not_called()


def test_windows_lock_import_is_conditional_and_documented():
    source = Path(profile_store.__file__).read_text(encoding="utf-8")
    assert 'if os.name == "nt":\n    import msvcrt\nelse:\n    import fcntl' in source
    documentation = Path("docs/profile-json-data-access-layer.md").read_text(encoding="utf-8")
    assert "Windows deployments use `msvcrt`" in documentation


def test_backups_are_created_and_bounded(tmp_path):
    path = tmp_path / "app_data.json"
    write(path, document())
    store = ProfileDataStore(path, backup_limit=2)
    for index in range(4):
        store.create_factory({"id": f"fac_{index}", "code": f"F{index}"})
    backups = list((tmp_path / "backups").glob("app_data.*.json"))
    assert len(backups) == 2
    for backup in backups:
        validate_data(json.loads(backup.read_text(encoding="utf-8")))


def test_data_file_is_not_served_through_static_routes(tmp_path):
    instance = tmp_path / "instance"
    store = ProfileDataStore.from_environment(instance, {})
    assert store.path == instance / "app_data.json"
    assert store.path.parent.name != "static"
    route_sources = "".join(path.read_text(encoding="utf-8") for path in Path("modules").glob("*/routes.py"))
    assert "app_data.json" not in route_sources


def test_password_hash_is_never_in_public_serialization():
    result = public_user({"id": "usr_1", "password_hash": "secret", "nested": {"password_hash": "secret"}})
    assert "secret" not in json.dumps(result)


def test_absent_store_requires_explicit_initialization(tmp_path):
    store = ProfileDataStore(tmp_path / "app_data.json")
    with pytest.raises(ProfileStoreNotInitializedError, match="not initialized"):
        store.load_data()
    initialized = store.initialize(ROLES)
    assert initialized["users"] == []
    assert not any("password" in json.dumps(value) for value in initialized["users"])
