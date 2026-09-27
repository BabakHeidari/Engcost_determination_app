import json
from pathlib import Path

import pytest

from utils.product_hierarchy_service import ALL, HierarchyMetadataError, HierarchySelectionError, ProductHierarchyService
from utils.profile_store import ProfileDataStore


def _write_hierarchy(root: Path):
    (root / "OpA" / "CatA" / "SubA").mkdir(parents=True)
    (root / "OpA" / "CatB" / "SubB").mkdir(parents=True)
    (root / "OpA" / "CatA" / "SubA" / "same<script>.json").write_text("{}", encoding="utf-8")
    (root / "OpA" / "CatB" / "SubB" / "same<script>.json").write_text("{}", encoding="utf-8")
    (root / "OpA" / "CatA" / "SubA" / "ignored_meta.json").write_text("{}", encoding="utf-8")
    (root / "__metadata.json").write_text(json.dumps({
        "product_hierarchy": {"OpA": {"CatB": ["SubB"], "CatA": ["SubA"]}, "OpB": {"Secret": ["Hidden"]}}
    }), encoding="utf-8")


def test_hierarchy_service_is_parent_scoped_deterministic_and_preserves_same_names(tmp_path):
    _write_hierarchy(tmp_path)
    service = ProductHierarchyService(tmp_path)
    initial = service.options("OpA")
    assert [item["id"] for item in initial["options"]["categories"]] == ["CatA", "CatB"]
    assert initial["options"]["subcategories"] == []

    result = service.options("OpA", category=ALL, subcategory=ALL)
    products = result["options"]["products"]
    assert [item["label"] for item in products] == ["same<script>", "same<script>"]
    assert len({item["id"] for item in products}) == 2
    assert {item["category"] for item in products} == {"CatA", "CatB"}
    assert all(item["category"] != "Secret" for item in products)


def test_hierarchy_service_rejects_tampered_children_and_missing_metadata(tmp_path):
    _write_hierarchy(tmp_path)
    service = ProductHierarchyService(tmp_path)
    with pytest.raises(HierarchySelectionError):
        service.options("OpA", category="CatA", subcategory="SubB")
    with pytest.raises(HierarchySelectionError):
        service.options("OpA", subcategory="SubA")
    with pytest.raises(HierarchyMetadataError):
        ProductHierarchyService(tmp_path / "missing").options("OpA")


def _grant(module, factory_id):
    return {"scope_type": "FACTORY", "factory_id": factory_id, "module": module, "permissions": ["READ"]}


@pytest.fixture
def dashboard_app(tmp_path, monkeypatch):
    import app as app_module
    hierarchy_root = tmp_path / "hierarchy"
    _write_hierarchy(hierarchy_root)
    monkeypatch.setattr(
        "modules.dashboard.routes.ProductHierarchyService",
        lambda: ProductHierarchyService(hierarchy_root),
    )
    path = tmp_path / "profiles.json"
    store = ProfileDataStore(path)
    store.initialize({})
    store.create_factory({"id": "fac_a", "code": "A", "name": "الف", "is_active": True, "operational_key": "OpA"})
    store.create_factory({"id": "fac_b", "code": "B", "name": "ب", "is_active": True, "operational_key": "OpB"})
    store.create_factory({"id": "fac_off", "code": "OFF", "name": "خاموش", "is_active": False, "operational_key": "OpA"})
    for user_id, role, grants in (
        ("limited", "USER", [_grant("dashboard", "fac_a")]),
        ("admin", "IT_ADMIN", []),
    ):
        store.create_user({
            "id": user_id, "username": user_id, "email": f"{user_id}@example.com",
            "full_name": user_id, "system_role": role, "job_title": "کاربر",
            "access_grants": grants, "is_active": True, "must_change_password": False,
            "password_hash": "unused", "password_scheme": "werkzeug", "revision": 1,
        })
    app_module.app.config.update(TESTING=True, APP_DATA_FILE=str(path), SECRET_KEY="test")
    return app_module.app


def _client(app, user_id):
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user_id
    return client


def test_dashboard_only_grant_works_without_product_grant_and_is_factory_isolated(dashboard_app):
    client = _client(dashboard_app, "limited")
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert b"fac_a" in page.data and b"fac_b" not in page.data
    response = client.get("/api/dashboard/filter-options?factory=fac_a&category=CatA&subcategory=SubA")
    assert response.status_code == 200
    assert response.get_json()["options"]["products"][0]["label"] == "same<script>"
    assert client.get("/api/dashboard/filter-options?factory=fac_b").status_code == 403
    assert client.get("/api/dashboard/filter-options?factory=unknown").status_code == 404
    assert client.get("/api/dashboard/filter-options?factory=fac_off").status_code == 403


def test_filter_endpoint_requires_factory_validates_parent_and_admin_sees_active_factories(dashboard_app):
    limited = _client(dashboard_app, "limited")
    assert limited.get("/api/dashboard/filter-options").get_json()["state"] == "NOT_SELECTED"
    tampered = limited.get("/api/dashboard/filter-options?factory=fac_a&category=CatA&subcategory=SubB")
    assert tampered.status_code == 400
    assert tampered.get_json()["state"] == "INVALID_SELECTION"

    admin = _client(dashboard_app, "admin")
    body = admin.get("/dashboard").data
    assert b"fac_a" in body and b"fac_b" in body and b"fac_off" not in body


def test_dashboard_frontend_uses_safe_dom_and_stale_response_guards():
    source = Path("templates/dashboard/dashboard.html").read_text(encoding="utf-8")
    assert "/api/filter_options" not in source
    assert "/api/dashboard/filter-options" in source
    assert "node.textContent = label" in source
    assert "sequence !== requestSequence" in source
    assert "activeRequest.abort()" in source
    assert ".innerHTML" not in source
    assert "همه کارخانه‌ها" not in source
