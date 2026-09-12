import pytest

import app as app_module
from utils.profile_store import ProfileDataStore


MODULE_PATHS = {
    "cost_calculation": "/cost/cost_calculation",
    "dashboard": "/dashboard",
    "desk": "/workdesk",
    "factory_parameters": "/factory_parameters/",
    "general_parameters": "/general_parameters/",
    "product": "/product/production_selection",
    "profile": "/profile/profile",
}


def grant(module, permissions=("READ",), factory_id=None):
    return {
        "scope_type": "FACTORY" if factory_id else "GLOBAL",
        "factory_id": factory_id,
        "module": module,
        "permissions": list(permissions),
    }


def create_user(store, user_id, grants=(), role="USER"):
    store.create_user({
        "id": user_id,
        "username": user_id,
        "email": f"{user_id}@example.com",
        "full_name": "کاربر آزمون",
        "system_role": role,
        "job_title": "کارشناس",
        "access_grants": list(grants),
        "is_active": True,
        "must_change_password": False,
        "password_hash": "unused",
        "password_scheme": "werkzeug",
        "revision": 1,
    })


@pytest.fixture
def app_store(tmp_path):
    path = tmp_path / "app_data.json"
    store = ProfileDataStore(path)
    store.initialize({})
    app_module.app.config.update(TESTING=True, APP_DATA_FILE=str(path), SECRET_KEY="test-secret")
    return store


def authenticated_client(app_store, user_id, grants=(), role="USER"):
    create_user(app_store, user_id, grants, role)
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user_id
    return client


@pytest.mark.parametrize("module", sorted(MODULE_PATHS))
def test_all_grantable_module_pages_use_friendly_rtl_403(app_store, module):
    client = authenticated_client(app_store, f"usr_{module}")
    response = client.get(MODULE_PATHS[module])
    body = response.get_data(as_text=True)

    assert response.status_code == 403
    assert response.mimetype == "text/html"
    assert '<html lang="fa" dir="rtl">' in body
    assert "دسترسی به این بخش برای شما فعال نیست" in body
    assert "Forbidden" not in body
    assert "You don't have the permission" not in body
    assert "auth" not in body


def test_api_403_stays_json_and_hides_authorization_internals(app_store):
    client = authenticated_client(app_store, "usr_api", [grant("profile")])
    response = client.post("/api/profile/factories", json={"name": "کارخانه پنهان"})

    assert response.status_code == 403
    assert response.is_json
    assert response.content_type.startswith("application/json")
    assert response.get_json() == {
        "success": False,
        "error": "forbidden",
        "message": "سطح دسترسی فعلی حساب شما برای انجام این عملیات کافی نیست.",
    }
    assert b"<!DOCTYPE html>" not in response.data
    assert b"MODIFY" not in response.data


def test_authentication_redirect_and_authorization_403_remain_distinct(app_store):
    anonymous = app_module.app.test_client().get("/workdesk")
    authorized_client = authenticated_client(app_store, "usr_denied")
    denied = authorized_client.get("/workdesk")

    assert anonymous.status_code == 302
    assert anonymous.headers["Location"].endswith("/login")
    assert denied.status_code == 403
    assert not denied.is_json


@pytest.mark.parametrize(
    ("grants", "expected_href", "expected_label"),
    [
        ([grant("desk")], "/workdesk", "رفتن به میز کار"),
        ([grant("profile")], "/profile/profile", "رفتن به بخش در دسترس"),
        ([], "/logout", "خروج امن"),
    ],
)
def test_safe_fallback_uses_effective_access(app_store, grants, expected_href, expected_label):
    client = authenticated_client(app_store, f"usr_fallback_{len(grants)}_{expected_href[-1]}", grants)
    response = client.get("/dashboard")
    body = response.get_data(as_text=True)

    assert response.status_code == 403
    assert f'href="{expected_href}"' in body
    assert expected_label in body


def test_top_level_admin_fallback_is_desk(app_store):
    client = authenticated_client(app_store, "usr_admin", role="IT_ADMIN")
    with client:
        client.get("/login")
        response, status = app_module.forbidden(None)

    assert status == 403
    assert 'href="/workdesk"' in response


def test_factory_scoped_denial_is_friendly_and_does_not_leak_factory(app_store):
    app_store.create_factory({
        "id": "fac_a", "code": "A", "name": "کارخانه مجاز",
        "operational_key": "FactoryA", "is_active": True, "revision": 1,
    })
    app_store.create_factory({
        "id": "fac_secret", "code": "SECRET", "name": "کارخانه محرمانه",
        "operational_key": "FactorySecret", "is_active": True, "revision": 1,
    })
    client = authenticated_client(
        app_store,
        "usr_factory",
        [grant("factory_parameters", factory_id="fac_a")],
    )
    response = client.get("/factory_parameters/fac_secret")
    body = response.get_data(as_text=True)

    assert response.status_code == 403
    assert "دسترسی به این بخش برای شما فعال نیست" in body
    assert "کارخانه محرمانه" not in body
    assert "fac_secret" not in body
    assert "SECRET" not in body


def test_json_accept_header_gets_machine_readable_403(app_store):
    client = authenticated_client(app_store, "usr_accept")
    response = client.get("/workdesk", headers={"Accept": "application/json"})

    assert response.status_code == 403
    assert response.is_json
    assert response.get_json()["error"] == "forbidden"
