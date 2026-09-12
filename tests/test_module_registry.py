from pathlib import Path

import pytest

from utils.module_registry import GRANTABLE_MODULES, INTERNAL_MODULES, MODULE_REGISTRY
from utils.profile_access_manager import access_state_to_grants, grants_to_access_state
from utils.profile_authorization import canonicalize_access_grants, get_effective_level, has_access
from utils.profile_view import build_profile_view_model


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


def test_all_modules_round_trip_and_missing_grants_remain_none():
    state = {"global": {}, "factories": {"fac_a": {}}}
    for item in MODULE_REGISTRY:
        target = state["global"] if "GLOBAL" in item["scopes"] else state["factories"]["fac_a"]
        target[item["id"]] = "MODIFY"
    grants = access_state_to_grants(state)
    canonical = canonicalize_access_grants(grants, {"fac_a"})
    assert grants_to_access_state(canonical) == state
    ordinary = {"system_role": "USER", "access_grants": []}
    assert all(get_effective_level(ordinary, item["id"], "fac_a" if "FACTORY" in item["scopes"] and "GLOBAL" not in item["scopes"] else None) == "NONE" for item in MODULE_REGISTRY)


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
    assert tuple(has_access(user, module, needed, factory_id, scope_type=scope) for needed in ("READ", "WRITE", "MODIFY")) == expected


def test_visual_manager_has_one_select_and_no_raw_permission_controls():
    script = Path("static/js/profile-access-manager.js").read_text(encoding="utf-8")
    template = Path("templates/profile/profile.html").read_text(encoding="utf-8")
    assert "config.factory_modules.forEach(m=>card.append(selector(" in script
    assert "config.global_modules.forEach(m => section.append(selector(" in script
    assert "createElement('select')" in script
    assert 'name="access_grants"' not in template
    assert 'type="checkbox" name="permissions"' not in template

@pytest.mark.parametrize("permissions", [["WRITE"], ["MODIFY"], ["READ", "MODIFY"]])
def test_non_hierarchical_permission_arrays_are_rejected(permissions):
    with pytest.raises(ValueError):
        canonicalize_access_grants([{
            "scope_type": "GLOBAL", "factory_id": None,
            "module": "desk", "permissions": permissions,
        }], set())
