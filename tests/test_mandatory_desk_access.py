import pytest

import app as app_module
from utils.profile_authorization import get_effective_level, has_access
from utils.profile_store import ProfileDataStore


def actor(*, role="USER", grants=None, active=True):
    return {
        "system_role": role,
        "access_grants": [] if grants is None else grants,
        "is_active": active,
    }


def test_ordinary_active_user_gets_read_floor_for_missing_or_legacy_empty_desk_grant():
    missing = actor()
    legacy_empty = actor(grants=[{
        "scope_type": "GLOBAL", "factory_id": None,
        "module": "desk", "permissions": [],
    }])
    for user in (missing, legacy_empty):
        assert get_effective_level(user, "desk", scope_type="GLOBAL") == "READ"
        assert has_access(user, "desk", "READ", scope_type="GLOBAL")
        assert not has_access(user, "desk", "WRITE", scope_type="GLOBAL")


@pytest.mark.parametrize("role", ["IT_ADMIN", "FINANCE_ECONOMIC_ADMIN"])
def test_top_level_roles_keep_implicit_modify_without_grants(role):
    user = actor(role=role)
    assert user["access_grants"] == []
    assert get_effective_level(user, "desk", scope_type="GLOBAL") == "MODIFY"


def test_inactive_user_and_other_missing_modules_do_not_gain_access():
    assert get_effective_level(actor(active=False), "desk", scope_type="GLOBAL") == "NONE"
    user = actor()
    for module in ("dashboard", "general_parameters", "profile"):
        assert get_effective_level(user, module, scope_type="GLOBAL") == "NONE"
    for module in ("cost_calculation", "factory_parameters", "product"):
        assert get_effective_level(user, module, "fac_a", scope_type="FACTORY") == "NONE"


def test_existing_user_without_desk_grant_can_open_desk_and_sees_no_protected_cards(tmp_path):
    path = tmp_path / "app_data.json"
    store = ProfileDataStore(path)
    store.initialize({})
    store.create_user({
        "id": "usr_baseline", "username": "baseline", "email": "baseline@example.com",
        "full_name": "کاربر پایه", "system_role": "USER", "job_title": "کارشناس",
        "access_grants": [], "is_active": True, "must_change_password": False,
        "password_hash": "unused", "password_scheme": "werkzeug", "revision": 1,
    })
    app_module.app.config.update(TESTING=True, APP_DATA_FILE=str(path), SECRET_KEY="test-secret")
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = "usr_baseline"

    response = client.get("/workdesk")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'href="/workdesk"' in body
    for protected_path in (
        "/dashboard", "/general_parameters/", "/factory_parameters/",
        "/product/production_selection", "/cost/cost_calculation", "/profile/profile",
    ):
        assert f'href="{protected_path}"' not in body

    denied = client.get("/dashboard")
    assert denied.status_code == 403
    assert "دسترسی به این بخش برای شما فعال نیست" in denied.get_data(as_text=True)


def test_anonymous_request_still_requires_authentication():
    response = app_module.app.test_client().get("/workdesk")
    assert response.status_code == 302
    assert response.location.endswith("/login")
