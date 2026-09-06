import json
from unittest import mock

import pytest

from utils.profile_authorization import (
    can_access_module, can_manage_user, canonicalize_access_grants,
    get_effective_access, is_top_level_admin,
)
from utils.profile_store import ProfileDataStore
from utils.profile_view import build_profile_view_model
from utils.profile_access_manager import access_state_to_grants, grants_to_access_state


def account(role="USER", grants=None, title=""):
    return {"id": "u", "system_role": role, "access_grants": grants or [], "job_title": title}


def test_parallel_admins_have_dynamic_identical_full_access():
    for role in ("IT_ADMIN", "FINANCE_ECONOMIC_ADMIN"):
        user = account(role)
        assert is_top_level_admin(user)
        assert get_effective_access(user) == {"full_access": True}
        assert can_access_module(user, "COST_CALCULATION", "future_factory", "WRITE")
        assert can_access_module(user, "DASHBOARD", permission="READ")


@pytest.mark.parametrize("role", ["IT_ADMIN", "FINANCE_ECONOMIC_ADMIN"])
def test_top_level_admin_profile_uses_full_access_state_without_iterating_sentinel(role):
    admin = {
        "id": "admin", "username": "admin", "email": "admin@example.com",
        "full_name": "مدیر", "system_role": role, "job_title": "",
        "access_grants": [], "is_active": True,
    }

    class Store:
        @staticmethod
        def merge_factories(candidates):
            return {"created": [], "created_count": 0}

        @staticmethod
        def load_data():
            return {"users": [admin], "factories": [], "audit_events": []}

    model = build_profile_view_model(Store(), admin)
    assert model["full_access"] is True
    assert model["effective_grants"] == []


def test_user_is_deny_by_default_and_job_title_is_inert():
    for title in ("admin", "مدیرعامل کارخانه", "CEO"):
        user = account(title=title)
        assert not is_top_level_admin(user)
        assert not can_manage_user(user, account("IT_ADMIN"))
        assert not can_access_module(user, "DASHBOARD")


def test_grants_are_paired_deduplicated_and_scoped():
    grants = canonicalize_access_grants([
        {"scope_type": "FACTORY", "factory_id": "F1", "module": "PRODUCT", "permissions": ["READ"]},
        {"scope_type": "FACTORY", "factory_id": "F1", "module": "PRODUCT", "permissions": ["WRITE", "READ"]},
        {"scope_type": "FACTORY", "factory_id": "F2", "module": "COST_CALCULATION", "permissions": ["READ"]},
        {"scope_type": "GLOBAL", "factory_id": None, "module": "GENERAL_PARAMETERS", "permissions": ["READ"]},
    ], {"F1", "F2"})
    user = account(grants=grants)
    assert len(grants) == 3
    assert can_access_module(user, "PRODUCT", "F1", "WRITE")
    assert not can_access_module(user, "PRODUCT", "F2", "WRITE")
    assert can_access_module(user, "GENERAL_PARAMETERS")


@pytest.mark.parametrize(("level", "permissions"), [
    ("NONE", None), ("READ", ["READ"]), ("WRITE", ["READ", "WRITE"]),
    ("MODIFY", ["READ", "WRITE", "MODIFY"]),
])
def test_visual_levels_serialize_to_hierarchical_permissions(level, permissions):
    grants = access_state_to_grants({"global": {"PROFILE": level}, "factories": {}})
    assert (grants[0]["permissions"] if grants else None) == permissions


def test_visual_access_round_trip_multiple_scopes_and_normalizes_duplicates():
    canonical = canonicalize_access_grants([
        {"scope_type": "GLOBAL", "factory_id": None, "module": "PROFILE", "permissions": ["WRITE"]},
        {"scope_type": "GLOBAL", "factory_id": None, "module": "PROFILE", "permissions": ["READ"]},
        {"scope_type": "FACTORY", "factory_id": "F1", "module": "PRODUCT", "permissions": ["MODIFY"]},
        {"scope_type": "FACTORY", "factory_id": "F2", "module": "PRODUCT", "permissions": ["READ"]},
    ], {"F1", "F2"})
    state = grants_to_access_state(canonical)
    assert state == {"global": {"PROFILE": "WRITE"}, "factories": {
        "F1": {"PRODUCT": "MODIFY"}, "F2": {"PRODUCT": "READ"}}}
    assert grants_to_access_state(access_state_to_grants(state)) == state


def test_profile_template_uses_visual_selector_not_raw_json():
    template = open("templates/profile/profile.html", encoding="utf-8").read()
    assert 'name="access_grants"' not in template
    assert "grant-row" not in template
    assert "profile-access-manager.js" in template


@pytest.mark.parametrize("grant", [
    {"scope_type": "OTHER", "factory_id": None, "module": "DASHBOARD", "permissions": ["READ"]},
    {"scope_type": "FACTORY", "factory_id": "missing", "module": "PRODUCT", "permissions": ["READ"]},
    {"scope_type": "GLOBAL", "factory_id": None, "module": "UNKNOWN", "permissions": ["READ"]},
    {"scope_type": "GLOBAL", "factory_id": None, "module": "DASHBOARD", "permissions": ["DELETE"]},
])
def test_unknown_grant_values_fail_closed(grant):
    with pytest.raises(ValueError):
        canonicalize_access_grants([grant], {"F1"})


def legacy_document():
    return {
        "schema_version": 1, "metadata": {"revision": 1}, "factories": [],
        "role_permissions": {"IT Admin": {"scope": "global", "permissions": {}}},
        "user_permission_overrides": [], "audit_events": [], "users": [
            {"id": "admin", "username": "admin", "email": "ADMIN@example.com", "role": "IT Admin", "password_hash": "hash", "is_active": True},
            {"id": "staff", "username": "staff", "email": "staff@example.com", "role": "Factory Staff", "password_hash": "hash", "is_active": True},
        ],
    }


def test_migration_backs_up_and_does_not_overgrant(tmp_path):
    path = tmp_path / "app_data.json"
    path.write_text(json.dumps(legacy_document()), encoding="utf-8")
    result = ProfileDataStore(path).migrate_access_model()
    data = ProfileDataStore(path).load_data()
    assert result == {"migrated": True, "review_user_ids": ["staff"]}
    assert data["users"][0]["system_role"] == "IT_ADMIN"
    assert data["users"][1]["system_role"] == "USER"
    assert data["users"][1]["access_grants"] == []
    assert list((tmp_path / "backups").glob("*.json"))
    assert "password_hash" in data["users"][0]


def test_existing_schema_v1_credentials_trigger_safe_runtime_migration(tmp_path):
    path = tmp_path / "app_data.json"
    legacy = legacy_document()
    legacy["users"] = [{
        "id": "usr_existing", "username": "mohsen1224",
        "email": "heidari.babak@gmail.com", "full_name": "Mohsen Valizadeh",
        "role": "IT Admin", "factory_id": None, "is_active": True,
        "must_change_password": False, "password_hash": "existing-scrypt-hash",
        "password_scheme": "werkzeug", "revision": 3,
        "last_login_at": "2026-09-06T08:45:02Z",
    }]
    path.write_text(json.dumps(legacy), encoding="utf-8")

    authenticated = ProfileDataStore(path).authenticate_user(
        "mohsen1224", "existing-password",
        lambda user, password: user["password_hash"] == "existing-scrypt-hash"
        and password == "existing-password",
    )

    assert authenticated["id"] == "usr_existing"
    assert authenticated["system_role"] == "IT_ADMIN"
    assert "password_hash" not in authenticated
    migrated = json.loads(path.read_text(encoding="utf-8"))
    assert migrated["schema_version"] == 2
    assert migrated["users"][0]["password_hash"] == "existing-scrypt-hash"
    assert migrated["users"][0]["must_change_password"] is False
    assert list((tmp_path / "backups").glob("*.json"))


def test_failed_migration_preserves_source_and_backup(tmp_path):
    path = tmp_path / "app_data.json"
    path.write_text(json.dumps(legacy_document()), encoding="utf-8")
    before = path.read_bytes()
    with mock.patch("utils.profile_store.os.replace", side_effect=OSError("disk")):
        with pytest.raises(OSError):
            ProfileDataStore(path).migrate_access_model()
    assert path.read_bytes() == before
    assert list((tmp_path / "backups").glob("*.json"))
