import pytest

from utils.profile_authorization import get_effective_level, has_access
from utils.profile_store import ProfileDataStore


def grant(module, permissions, factory_id=None):
    return {
        "scope_type": "FACTORY" if factory_id else "GLOBAL",
        "factory_id": factory_id,
        "module": module,
        "permissions": permissions,
    }


def user(level=None, *, module="general_parameters", factory_id=None, role="USER"):
    permissions = {
        "READ": ["READ"],
        "WRITE": ["READ", "WRITE"],
        "MODIFY": ["READ", "WRITE", "MODIFY"],
    }.get(level)
    return {
        "id": "actor", "system_role": role, "job_title": "مدیر کل",
        "access_grants": [grant(module, permissions, factory_id)] if permissions else [],
    }


@pytest.mark.parametrize(
    ("level", "allowed"),
    [
        (None, (False, False, False)),
        ("READ", (True, False, False)),
        ("WRITE", (True, True, False)),
        ("MODIFY", (True, True, True)),
    ],
)
def test_canonical_hierarchy(level, allowed):
    actor = user(level)
    assert tuple(has_access(actor, "general_parameters", required) for required in ("READ", "WRITE", "MODIFY")) == allowed
    assert get_effective_level(actor, "general_parameters") == (level or "NONE")


@pytest.mark.parametrize("role", ["IT_ADMIN", "FINANCE_ECONOMIC_ADMIN"])
def test_peer_admins_have_identical_future_factory_access(role):
    actor = user(role=role)
    assert get_effective_level(actor, "product", "fac_future") == "MODIFY"
    assert has_access(actor, "profile", "MODIFY", scope_type="GLOBAL")


def test_module_factory_and_scope_must_match_exactly():
    actor = user("MODIFY", module="product", factory_id="fac_a")
    assert has_access(actor, "product", "MODIFY", "fac_a")
    assert not has_access(actor, "product", "READ", "fac_b")
    assert not has_access(actor, "cost_calculation", "READ", "fac_a")
    assert not has_access(actor, "dashboard", "READ", scope_type="GLOBAL")
    assert not has_access(actor, "product", "READ", scope_type="GLOBAL")


@pytest.fixture
def ordinary_client(tmp_path):
    import app as app_module

    path = tmp_path / "app_data.json"
    store = ProfileDataStore(path)
    store.initialize({})
    store.create_user({
        "id": "usr_user", "username": "ordinary", "email": "ordinary@example.com",
        "full_name": "کاربر", "system_role": "USER", "job_title": "مدیر سامانه",
        "access_grants": [grant("general_parameters", ["READ"])], "is_active": True,
        "must_change_password": False, "password_hash": "unused", "password_scheme": "werkzeug",
        "revision": 1,
    })
    app_module.app.config.update(TESTING=True, APP_DATA_FILE=str(path), SECRET_KEY="test-secret")
    with app_module.app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = "usr_user"
        yield client


def test_direct_mutation_requires_modify_and_authentication(ordinary_client, monkeypatch):
    called = False

    def forbidden_mutation(_payload):
        nonlocal called
        called = True

    monkeypatch.setattr("modules.general_parameters.routes.material_data_updater", forbidden_mutation)
    response = ordinary_client.post("/save_materials", json={})
    assert response.status_code == 403
    assert called is False

    ordinary_client.get("/logout")
    assert ordinary_client.post("/save_materials", json={}).status_code == 302


def test_ordinary_user_cannot_call_admin_api_despite_profile_like_job_title(ordinary_client):
    response = ordinary_client.post("/api/profile/factories", json={"code": "X", "name": "X"})
    assert response.status_code == 403
