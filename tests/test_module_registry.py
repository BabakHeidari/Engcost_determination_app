import json
from pathlib import Path

import pytest

from utils.module_registry import GRANTABLE_MODULES, INTERNAL_MODULES, MODULE_REGISTRY
from utils.profile_access_manager import access_state_to_grants, grants_to_access_state
from utils.profile_authorization import canonicalize_access_grants, get_effective_level, has_access
from utils.profile_view import build_profile_view_model
from utils.profile_store import ProfileDataStore


EXPECTED = {
    "cost_calculation", "dashboard", "desk", "factory_parameters",
    "general_parameters", "product", "profile",
}


def test_exact_explicit_grantable_registry_excludes_auth_and_aliases():
    assert GRANTABLE_MODULES == EXPECTED
    assert "auth" not in GRANTABLE_MODULES
    assert INTERNAL_MODULES == {"auth"}
    assert not ({"WORKBENCH", "PRODUCT_CONFIGURATION", "USER_PROFILE", "COST_CALCULATION"} & GRANTABLE_MODULES)


def test_access_manager_add_edit_metadata_comes_from_registry():
    admin = {
        "id": "admin", "username": "admin", "email": "admin@example.com",
        "full_name": "مدیر", "system_role": "IT_ADMIN", "job_title": "",
        "access_grants": [], "is_active": True,
    }

    class Store:
        @staticmethod
        def load_data():
            return {"users": [admin], "factories": [], "audit_events": []}

    model = build_profile_view_model(Store(), admin)
    access_modules = {
        item["value"] for group in ("global_modules", "factory_modules")
        for item in model["access_manager"][group]
    }
    add_modules = {item["value"] for item in model["create_user"]["modules"]}
    assert access_modules == add_modules == EXPECTED
    assert all(item["value"] != "auth" for group in ("global_modules", "factory_modules") for item in model["access_manager"][group])


def test_all_modules_round_trip_and_only_mandatory_desk_has_baseline_read():
    state = {"global": {}, "factories": {"fac_a": {}}}
    for item in MODULE_REGISTRY:
        target = state["global"] if "GLOBAL" in item["scopes"] else state["factories"]["fac_a"]
        target[item["id"]] = "MODIFY"
    grants = access_state_to_grants(state)
    canonical = canonicalize_access_grants(grants, {"fac_a"})
    assert grants_to_access_state(canonical) == state
    ordinary = {"system_role": "USER", "access_grants": []}
    levels = {
        item["id"]: get_effective_level(
            ordinary, item["id"],
            "fac_a" if "FACTORY" in item["scopes"] and "GLOBAL" not in item["scopes"] else None,
        )
        for item in MODULE_REGISTRY
    }
    assert levels.pop("desk") == "READ"
    assert set(levels.values()) == {"NONE"}


@pytest.mark.parametrize("module", sorted(EXPECTED))
@pytest.mark.parametrize("level,expected", [
    (None, (False, False, False)),
    ("READ", (True, False, False)),
    ("WRITE", (True, True, False)),
    ("MODIFY", (True, True, True)),
])
def test_hierarchy_for_every_grantable_module(module, level, expected):
    metadata = next(item for item in MODULE_REGISTRY if item["id"] == module)
    scope = metadata["scopes"][0]
    factory_id = "fac_a" if scope == "FACTORY" else None
    permissions = {"READ": ["READ"], "WRITE": ["READ", "WRITE"], "MODIFY": ["READ", "WRITE", "MODIFY"]}.get(level)
    grants = [] if permissions is None else [{"scope_type": scope, "factory_id": factory_id, "module": module, "permissions": permissions}]
    user = {"system_role": "USER", "access_grants": grants}
    if module == "desk" and level is None:
        expected = (True, False, False)
    assert tuple(has_access(user, module, needed, factory_id, scope_type=scope) for needed in ("READ", "WRITE", "MODIFY")) == expected


def test_desk_registry_and_visual_manager_expose_read_only_mandatory_policy():
    desk = next(item for item in MODULE_REGISTRY if item["id"] == "desk")
    assert desk["mandatory_access"] is True
    assert desk["minimum_level"] == "READ"
    script = Path("static/js/profile-access-manager.js").read_text(encoding="utf-8")
    assert "module.minimum_level === 'READ'" in script
    assert "حداقل اجباری: فقط مشاهده" in script
    assert ".filter(level => module.minimum_level !== 'READ' || level.value !== 'NONE')" in script


def test_visual_manager_has_one_select_and_no_raw_permission_controls():
    script = Path("static/js/profile-access-manager.js").read_text(encoding="utf-8")
    template = Path("templates/profile/profile.html").read_text(encoding="utf-8")
    assert "config.factory_modules.forEach(module => card.append(selector(" in script
    assert "config.global_modules.forEach(module => section.append(selector(" in script
    assert "element('select', 'form-select access-level')" in script
    assert 'name="access_grants"' not in template
    assert 'type="checkbox" name="permissions"' not in template

@pytest.mark.parametrize("permissions", [["WRITE"], ["MODIFY"], ["READ", "MODIFY"]])
def test_non_hierarchical_permission_arrays_are_rejected(permissions):
    with pytest.raises(ValueError):
        canonicalize_access_grants([{
            "scope_type": "GLOBAL", "factory_id": None,
            "module": "desk", "permissions": permissions,
        }], set())


def test_existing_phase_8_uppercase_grants_are_atomically_normalized(tmp_path):
    path = tmp_path / "app_data.json"
    store = ProfileDataStore(path)
    store.initialize({})
    store.create_factory({
        "id": "fac_a", "code": "A", "name": "کارخانه الف",
        "is_active": True, "revision": 1,
    })
    store.create_user({
        "id": "usr_old", "username": "old", "email": "old@example.com",
        "full_name": "کاربر قدیمی", "system_role": "USER", "job_title": "",
        "access_grants": [{
            "scope_type": "FACTORY", "factory_id": "fac_a",
            "module": "product", "permissions": ["READ", "WRITE"],
        }],
        "is_active": True, "password_hash": "hash", "revision": 1,
    })
    document = json.loads(path.read_text(encoding="utf-8"))
    document["users"][0]["access_grants"][0]["module"] = "PRODUCT"
    path.write_text(json.dumps(document), encoding="utf-8")

    authenticated = store.authenticate_user("old", "password", lambda _user, _password: True)
    loaded = store.load_data()

    assert authenticated["id"] == "usr_old"
    grant = loaded["users"][0]["access_grants"][0]
    assert grant["module"] == "product"
    assert grant["permissions"] == ["READ", "WRITE"]
    assert list((tmp_path / "backups").glob("*.json"))
