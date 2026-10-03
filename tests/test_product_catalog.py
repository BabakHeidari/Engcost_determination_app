import json

import pytest

from utils.product_catalog import build_product_catalog, build_product_hierarchy, product_catalog_document


POOLS = ("Overhead", "Payroll", "AdministrativeandResearch", "FinancialCosts",
         "Depriciation", "NonOperationalCostsandIncomes")


def write(path, value=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value or {}), encoding="utf-8")


def factory_fixture(root, factory="DinMohamadpour", product="RealProduct", with_meta=True):
    base = root / "Factories" / factory
    write(base / "RealCategory" / "RealSubcategory" / f"{product}.json", {"data": {}})
    if with_meta:
        write(base / "RealCategory" / "RealSubcategory" / f"{product}_meta.json", {"capacity": 125})
    write(base / "configuration" / "manifest.json")
    write(base / "configuration" / "cost_structure.json")
    for pool in POOLS:
        write(base / "configuration" / "cost_pools" / f"{pool}.json")
    return base


def test_v2_configuration_never_enters_catalog_or_hierarchy(tmp_path):
    factory_fixture(tmp_path)
    items = build_product_catalog(tmp_path / "Factories", ["DinMohamadpour"])
    assert [(item.factory, item.category, item.subcategory, item.product, item.capacity) for item in items] == [
        ("DinMohamadpour", "RealCategory", "RealSubcategory", "RealProduct", 125)
    ]
    hierarchy = build_product_hierarchy(tmp_path / "Factories", ["DinMohamadpour"])
    assert hierarchy == {"DinMohamadpour": {"RealCategory": ["RealSubcategory"]}}
    rendered = repr([(item.category, item.subcategory, item.product) for item in items]) + repr(hierarchy)
    assert "configuration" not in rendered and "cost_pools" not in rendered
    assert not any(pool in rendered for pool in POOLS)


def test_products_later_generation_handles_missing_meta_without_fabricating_capacity(tmp_path):
    factory_fixture(tmp_path, with_meta=False)
    document = product_catalog_document(tmp_path / "Factories", ["DinMohamadpour"])
    assert document["Product_Name"] == {"0": "RealProduct"}
    assert document["Capacity"] == {"0": None}
    assert "Overhead" not in repr(document)


def test_directory_metadata_and_multiple_factories_are_isolated(tmp_path):
    factory_fixture(tmp_path, "FactoryA", "A")
    factory_fixture(tmp_path, "FactoryB", "B")
    hierarchy = build_product_hierarchy(tmp_path / "Factories", ["FactoryA", "FactoryB"])
    assert hierarchy == {
        "FactoryA": {"RealCategory": ["RealSubcategory"]},
        "FactoryB": {"RealCategory": ["RealSubcategory"]},
    }
    items = build_product_catalog(tmp_path / "Factories", ["FactoryA", "FactoryB"])
    assert {(item.factory, item.product) for item in items} == {("FactoryA", "A"), ("FactoryB", "B")}


def test_production_selection_and_options_exclude_v2_configuration(tmp_path, monkeypatch):
    pytest.importorskip("flask")
    app_module = __import__("app")
    product_routes = __import__("modules.product.routes", fromlist=["routes"])
    updaters = __import__("utils.updaters", fromlist=["updaters"])
    ProfileDataStore = __import__("utils.profile_store", fromlist=["ProfileDataStore"]).ProfileDataStore

    data = tmp_path / "Data"
    factory_fixture(data, with_meta=False)
    (data / "Overall").mkdir(parents=True)
    store_path = tmp_path / "app_data.json"
    store = ProfileDataStore(store_path)
    store.initialize({})
    store.create_user({
        "id": "admin", "username": "admin", "email": "admin@example.com", "full_name": "مدیر",
        "system_role": "IT_ADMIN", "job_title": "مدیر", "access_grants": [], "is_active": True,
        "must_change_password": False, "password_hash": "unused", "password_scheme": "werkzeug", "revision": 1,
    })
    store.create_factory_as_actor("admin", {"code": "DinMohamadpour", "name": "کارخانه آزمون"})
    monkeypatch.setattr(product_routes, "parent_path", data)
    monkeypatch.setattr(product_routes, "product_path", str(data / "Overall" / "ProductsLater"))
    monkeypatch.setattr(updaters, "parent_path", data)
    app_module.app.config.update(TESTING=True, APP_DATA_FILE=str(store_path), SECRET_KEY="test")

    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = "admin"
    page = client.get("/product/production_selection")
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert "RealProduct" in body and "ثبت نشده" in body
    assert all(pool not in body for pool in POOLS)
    options = client.get("/api/product_options")
    assert options.status_code == 200
    payload = options.get_json()
    assert payload["product_hierarchy"] == {
        "DinMohamadpour": {"RealCategory": ["RealSubcategory"]}
    }
    assert "configuration" not in repr(payload) and "cost_pools" not in repr(payload)
