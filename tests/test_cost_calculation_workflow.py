import json

import pytest

from utils.costing_engine import FACTORY_POOL_IDS
from utils.profile_store import ProfileDataStore


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def workflow(tmp_path, monkeypatch):
    import app as app_module

    profiles = tmp_path / "profiles.json"
    store = ProfileDataStore(profiles)
    store.initialize({})
    store.create_factory({"id": "factory-canonical", "code": "F01", "name": "کارخانه آزمون", "is_active": True, "operational_key": "legacy-folder"})
    store.create_factory({"id": "factory-secret", "code": "F02", "name": "کارخانه محرمانه", "is_active": True, "operational_key": "secret-folder"})
    store.create_user({
        "id": "cost-user", "username": "cost-user", "email": "cost@example.test", "full_name": "کاربر هزینه",
        "system_role": "USER", "job_title": "کاربر", "is_active": True, "must_change_password": False,
        "password_hash": "unused", "password_scheme": "werkzeug", "revision": 1,
        "access_grants": [{"scope_type": "FACTORY", "factory_id": "factory-canonical", "module": "cost_calculation", "permissions": ["READ"]}],
    })
    data = tmp_path / "Data"
    factory = data / "Factories" / "legacy-folder"
    catalogue = data / "Overall" / "ProductsLater.json"
    _write(catalogue, {"Product_Name": {"0": "A", "1": "Hidden"}, "Factory": {"0": "legacy-folder", "1": "secret-folder"},
                       "Category": {"0": "category", "1": "secret"}, "Subcategory": {"0": "sub", "1": "hidden"}})
    _write(data / "Overall" / "material_costs.json", {"data": {
        "material": ["lead", "USD"], "unit": ["kg", "currency"], "currency": ["USD", "IRR - Iranian Rial"],
        "cost_per_unit_in_currency": [2, 500000],
    }})
    for product, usage in (("A", 100), ("B", 40)):
        _write(factory / "category" / "sub" / f"{product}.json", {"data": {
            "materials": ["lead"], "usage": [usage], "lost_percentage": [10], "recycability_percentage": [20],
        }})
    _write(factory / "category_weights.json", {"data": {"category": ["category"], "selling_share_of_category": [50]}})
    _write(factory / "ProductionPrediction.json", {"data": {"Product Name": ["A", "B"], "Predicted Production": [10, 10]}})
    for pool in FACTORY_POOL_IDS:
        _write(factory / f"Factory_Data_{pool}.json", {"data": {"cost": [1000 if pool == "Payroll" else 0]}})
    sources = ["materials", "bom", "weights", "predictions", *(f"pool:{item}" for item in FACTORY_POOL_IDS)]
    binding = tmp_path / "costing_period_bindings.json"
    _write(binding, {"bindings": [{"factory_id": "factory-canonical", "period_id": "P", "active": True,
                                    "approved": True, "status": "ACTIVE",
                                    "start": "2026-10-01", "end": "2026-12-31", "sources": sources}]})
    monkeypatch.setattr("modules.cost_calculation.routes.product_path", str(catalogue.with_suffix("")))
    app_module.app.config.update(TESTING=True, APP_DATA_FILE=str(profiles), SECRET_KEY="test",
                                 COSTING_DATA_ROOT=str(data), COSTING_PERIOD_BINDINGS_FILE=str(binding))
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = "cost-user"
    return app_module.app, client, binding


def _payload(**changes):
    value = {"Factory": "factory-canonical", "Category": "category", "Subcategory": "sub", "Product_Name": "A"}
    value.update(changes)
    return value


def test_catalogue_maps_operational_key_to_canonical_id_and_hides_unauthorized(workflow):
    _, client, _ = workflow
    page = client.get("/cost/cost_calculation")
    assert page.status_code == 200
    text = page.get_data(as_text=True)
    assert "factory-canonical" in text and "کارخانه آزمون" in text
    assert "legacy-folder" not in text and "factory-secret" not in text and "Hidden" not in text


def test_single_route_golden_and_bulk_use_same_four_part_identity(workflow):
    _, client, _ = workflow
    response = client.post("/cost/get_cost", json=_payload())
    assert response.status_code == 200
    body = response.get_json()
    assert body["state"] == "OK"
    assert body["Final_Production_Cost"] == 98000100
    assert body["identity"] == {"factory_id": "factory-canonical", "category": "category", "subcategory": "sub", "product": "A"}
    bulk = client.post("/cost/get_costs_bulk", json=[_payload()]).get_json()
    key = json.dumps(["factory-canonical", "category", "sub", "A"], ensure_ascii=False, separators=(",", ":"))
    assert bulk["state"] == "OK" and bulk["coverage"] == {"configured": 1, "calculated": 1, "excluded": 0}
    assert bulk["results"][key]["Final_Production_Cost"] == 98000100


def test_missing_binding_is_typed_actionable_and_never_zero(workflow):
    app, client, binding = workflow
    app.config["COSTING_PERIOD_BINDINGS_FILE"] = str(binding.with_name("absent.json"))
    response = client.post("/cost/get_cost", json=_payload())
    assert response.status_code == 422
    body = response.get_json()
    assert body["state"] == "MISSING_INPUT" and body["error"]["code"] == "PERIOD_NOT_BOUND"
    assert "پیکربندی" in body["error"]["message"] and "Final_Production_Cost" not in body


def test_request_and_authorization_fail_closed(workflow):
    app, client, _ = workflow
    assert client.post("/cost/get_cost", data="{bad", content_type="application/json").status_code == 400
    assert client.post("/cost/get_cost", json={}).get_json()["error"]["code"] == "MISSING_IDENTITY"
    forbidden = client.post("/cost/get_cost", json=_payload(Factory="factory-secret"))
    assert forbidden.status_code == 403 and "کارخانه محرمانه" not in forbidden.get_data(as_text=True)
    missing = client.post("/cost/get_cost", json=_payload(Factory="tampered"))
    assert missing.status_code == 404
    anonymous = app.test_client().post("/cost/get_cost", json=_payload())
    assert anonymous.status_code == 302
    setup = client.post("/cost/planning-period/initial/discover", json={"factory_id": "factory-canonical"})
    assert setup.status_code == 403


def test_frontend_distinguishes_failures_zero_and_stale_responses(workflow):
    _, client, _ = workflow
    page = client.get("/cost/cost_calculation").get_data(as_text=True)
    for marker in ('kind: "network"', 'response.status === 400', 'response.status === 403',
                   'response.status === 404', 'response.status === 422', 'response.status >= 500',
                   'kind: "invalid-json"', 'kind: "non-json"', 'sequence !== calculationSequence'):
        assert marker in page
    assert "Final_Production_Cost ?? 0" not in page
    assert "داده‌های هزینه بارگذاری نشد. ممکن است Backend" not in page
