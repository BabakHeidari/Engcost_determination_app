"""Real Dashboard analysis contracts, shared-engine goldens and read-only HTTP paths.

Use a standalone Flask application: importing ``app.py`` would activate startup
migrations before the fixture's operational and runtime paths are isolated.
"""

import base64
from datetime import datetime
import hashlib
import json
from decimal import Decimal
import shutil
from types import SimpleNamespace

from flask import Flask
import pytest

from utils.costing_engine import FACTORY_POOL_IDS, CostInputError, CostInputLoader, ProductIdentity, calculate_cost
from utils.factory_configuration import ensure_factory_configuration_v2
from utils.factory_service import FactoryService
from utils.product_hierarchy_service import ALL
from utils.profile_store import ProfileDataStore


FACTORY = "factory-canonical"
OPERATIONAL = "legacy-folder"
SELECTION = {"factory": FACTORY, "category": ALL, "subcategory": ALL, "product": ALL}


def _write(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")


def _reference(category, subcategory, product, *, factory=OPERATIONAL):
    raw = json.dumps([factory, category, subcategory, product], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _bom(usages, *, material="lead", loss=10, recycling=20):
    return {"data": {
        "materials": [material] * len(usages), "usage": usages,
        "lost_percentage": [loss] * len(usages),
        "recycability_percentage": [recycling] * len(usages),
        "cost_of_material_in_rial": [777777] * len(usages),
    }}


def _client(app, user):
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user
    return client


def _snapshot(root):
    """Content, modification times and directory population detect any writes."""
    return {
        path.relative_to(root).as_posix(): (
            "file", hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns
        ) if path.is_file() else ("directory",)
        for path in root.rglob("*")
    }


@pytest.fixture
def analysis(tmp_path, monkeypatch):
    # Isolate all known runtime paths before importing route modules. Never
    # import app.py: startup behavior belongs to separate migration tests.
    profiles = tmp_path / "profiles.json"
    data = tmp_path / "Data"
    binding = tmp_path / "bindings.json"
    monkeypatch.setenv("APP_DATA_FILE", str(profiles))
    monkeypatch.setenv("COSTING_DATA_ROOT", str(data))
    monkeypatch.setenv("COSTING_PERIOD_BINDINGS_FILE", str(binding))
    from modules.cost_calculation.routes import cost_calculation_bp
    from modules.dashboard.routes import dashboard_bp

    store = ProfileDataStore(profiles)
    store.initialize({})
    for factory_id, active, operational in (
        (FACTORY, True, OPERATIONAL),
        ("factory-secret", True, "secret-folder"),
        ("factory-inactive", False, "inactive-folder"),
    ):
        store.create_factory({
            "id": factory_id, "code": factory_id, "name": factory_id,
            "is_active": active, "operational_key": operational,
        })
    for user_id, role, modules in (
        ("dashboard-user", "USER", ["dashboard"]),
        ("all-modules-user", "USER", ["dashboard", "product", "cost_calculation"]),
        ("cost-only-user", "USER", ["cost_calculation"]),
        ("admin", "IT_ADMIN", []),
        ("finance-admin", "FINANCE_ECONOMIC_ADMIN", []),
    ):
        store.create_user({
            "id": user_id, "username": user_id, "email": f"{user_id}@example.test",
            "full_name": user_id, "system_role": role, "job_title": "کاربر",
            "is_active": True, "must_change_password": False,
            "password_hash": "unused", "password_scheme": "werkzeug", "revision": 1,
            "access_grants": [{"scope_type": "FACTORY", "factory_id": FACTORY,
                               "module": module, "permissions": ["READ"]} for module in modules],
        })
    factory = data / "Factories" / OPERATIONAL
    _write(data / "Overall" / "material_costs.json", {"data": {
        "material": ["lead", "USD"], "unit": ["kg", "currency"],
        "currency": ["USD", "IRR - Iranian Rial"], "cost_per_unit_in_currency": [2, 500000],
    }})
    _write(factory / "category" / "sub" / "A.json", _bom([100]))
    _write(factory / "category" / "sub" / "B.json", _bom([40]))
    _write(factory / "category_weights.json", {"data": {
        "category": ["category"], "selling_share_of_category": [50],
    }})
    _write(factory / "ProductionPrediction.json", {"data": {
        "Product Name": ["A", "B"], "Predicted Production": [10, 10],
    }})
    for pool in FACTORY_POOL_IDS:
        _write(factory / f"Factory_Data_{pool}.json", {"data": {
            "subject": [f"{pool} fixture"], "cost": [1000 if pool == "Payroll" else 0],
        }})
    _write(data / "Factories" / "__metadata.json", {"product_hierarchy": {
        OPERATIONAL: {"category": ["sub", "empty"]}, "secret-folder": {"secret": ["hidden"]},
    }})
    (factory / "category" / "empty").mkdir()
    _write(binding, {"bindings": [{
        "factory_id": FACTORY, "period_id": "P", "start": "2026-10-01", "end": "2026-12-31",
        "active": True, "approved": True, "status": "ACTIVE",
        "sources": ["materials", "bom", "weights", "predictions", *(f"pool:{p}" for p in FACTORY_POOL_IDS)],
    }]})
    # V2 is installed explicitly before any analytical request; setup writes
    # cannot accidentally satisfy the read-only assertions below.
    ensure_factory_configuration_v2(FACTORY, OPERATIONAL, data_root=data)
    app = Flask(__name__, instance_path=str(tmp_path / "instance"))
    app.config.update(TESTING=True, SECRET_KEY="analysis-test", APP_DATA_FILE=str(profiles),
                      COSTING_DATA_ROOT=str(data), COSTING_PERIOD_BINDINGS_FILE=str(binding))
    app.add_url_rule("/login", endpoint="auth.login", view_func=lambda: "login")
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(cost_calculation_bp, url_prefix="/cost")
    return SimpleNamespace(
        app=app, client=_client(app, "dashboard-user"), root=tmp_path, data=data,
        factory=factory, binding=binding, store=store,
    )


def _request(analysis, **changes):
    return analysis.client.get("/api/cost_analysis", query_string={**SELECTION, **changes})


def _amount(value):
    assert isinstance(value, str), "Numerical API amounts must preserve Decimal precision as strings"
    return Decimal(value)


def _valid_rows(body):
    return [row for row in body["detail_rows"] if row["state"] == "OK"]


def _row(body, product):
    return next(row for row in body["detail_rows"] if row["identity"]["product"] == product)


def _pool(body, pool="Payroll"):
    return next(row for row in body["breakdowns"]["factory_pools"] if row["id"] == pool)


def _set_pools(analysis, value=0):
    for pool in FACTORY_POOL_IDS:
        path = analysis.factory / "configuration" / "cost_pools" / f"{pool}.json"
        document = json.loads(path.read_text())
        document["data"]["cost"] = [value]
        _write(path, document)


def test_dashboard_only_access_full_contract_and_g1_g2_no_writes(analysis):
    before = _snapshot(analysis.root)
    response = _request(analysis)
    assert response.status_code == 200
    body = response.get_json()
    assert set(("version", "state", "scope", "period", "calculated_at", "source_lineage",
                "coverage", "kpis", "breakdowns", "detail_rows", "issues")) <= body.keys()
    assert body["version"] == "1" and body["state"] == "OK"
    assert body["period"]["id"] == "P"
    assert body["coverage"] == {"configured": 2, "calculated": 2, "excluded": 0, "percentage": "100"}
    assert body["kpis"]["matched_configuration_count"] == 2
    assert _amount(body["kpis"]["projected_total"]) == Decimal("1372002000")
    assert body["kpis"]["partial_total"] is None
    average = body["kpis"]["weighted_average"]
    assert _amount(average["value"]) == Decimal("68600100")
    assert _amount(average["numerator"]) == Decimal("1372002000")
    assert _amount(average["denominator"]) == Decimal("20")
    assert average["unit"] == "IRR/product"
    assert _amount(_row(body, "A")["bom_total"]) == Decimal("98000000")  # Approved G1.
    assert _amount(_row(body, "A")["unit_cost"]) == Decimal("98000100")
    assert _amount(_row(body, "A")["prediction"]) == Decimal("10")
    assert _amount(_row(body, "A")["projected_cost"]) == Decimal("980001000")
    assert {row["identity"]["factory_id"] for row in body["detail_rows"]} == {FACTORY}
    payroll = _pool(body)
    assert _amount(payroll["raw_total"]) == Decimal("1000")
    assert _amount(payroll["modeled_selected_total"]) == _amount(payroll["modeled_category_total"]) == Decimal("2000")
    assert _amount(payroll["selected_minus_raw"]) == _amount(payroll["category_minus_raw"]) == Decimal("1000")  # Approved G2.
    assert body["breakdowns"]["products"] == _valid_rows(body)
    drivers = body["breakdowns"]["drivers"]
    assert {item["id"] for item in drivers} == {"BOM", *FACTORY_POOL_IDS}
    assert sum((_amount(item["value"]) for item in drivers), Decimal(0)) == _amount(body["kpis"]["projected_total"])
    top = body["kpis"]["top_cost_driver"]
    assert top["state"] == "OK" and top["id"] == "BOM"
    assert _amount(top["value"]) == Decimal("1372000000")
    assert _amount(top["share"]) == Decimal("1372000000") / Decimal("1372002000") * 100
    assert top["tie"] is False and top["tied_ids"] == ["BOM"]
    assert _snapshot(analysis.root) == before
    assert str(analysis.root) not in response.get_data(as_text=True)
    # Dashboard access is independent of Product and Cost Calculation grants.
    assert analysis.client.post("/cost/get_cost", json={
        "Factory": FACTORY, "Category": "category", "Subcategory": "sub", "Product_Name": "A", "Period": "P",
    }).status_code == 403


@pytest.mark.parametrize("user", ["admin", "finance-admin"])
def test_admin_roles_can_analyze_active_canonical_factory(analysis, user):
    response = _client(analysis.app, user).get("/api/cost_analysis", query_string=SELECTION)
    assert response.status_code == 200 and response.get_json()["state"] == "OK"


@pytest.mark.parametrize("factory,status", [
    ("factory-secret", 403), ("factory-inactive", 403), ("unknown", 404), (OPERATIONAL, 404),
])
def test_authorization_precedes_operational_lookup(analysis, monkeypatch, factory, status):
    def unexpected_lookup(*_args, **_kwargs):
        pytest.fail("Operational lookup occurred before exact-factory authorization")
    monkeypatch.setattr(FactoryService, "operational_key", unexpected_lookup)
    before = _snapshot(analysis.root)
    response = _request(analysis, factory=factory)
    assert response.status_code == status
    assert str(analysis.root) not in response.get_data(as_text=True)
    assert _snapshot(analysis.root) == before


def test_cost_calculation_grant_does_not_authorize_dashboard(analysis):
    response = _client(analysis.app, "cost-only-user").get("/api/cost_analysis", query_string=SELECTION)
    assert response.status_code == 403
    assert analysis.app.test_client().get("/api/cost_analysis", query_string=SELECTION).status_code == 302


@pytest.mark.parametrize("missing", ["factory", "category", "subcategory", "product"])
def test_each_absent_selection_is_not_selected(analysis, missing):
    selection = {key: value for key, value in SELECTION.items() if key != missing}
    response = analysis.client.get("/api/cost_analysis", query_string=selection)
    assert response.status_code == 400
    assert response.get_json()["state"] == "NOT_SELECTED"


@pytest.mark.parametrize("field,value", [
    ("factory", ""), ("factory", ALL), ("category", ""), ("subcategory", ""), ("product", ""),
    ("category", "foreign"), ("subcategory", "foreign"), ("product", "A"),
    ("category", "../category"), ("product", "{bad"),
])
def test_empty_unknown_and_malformed_selection_never_broadens_scope(analysis, field, value):
    response = _request(analysis, **{field: value})
    assert response.status_code == 400
    assert response.get_json()["state"] in {"INVALID_SELECTION", "INVALID_REQUEST"}


@pytest.mark.parametrize("query", [
    [*SELECTION.items(), ("category", ALL)],
    [*SELECTION.items(), ("unknown_input", "anything")],
    [*SELECTION.items(), ("period", "P"), ("period", "P")],
])
def test_repeated_and_unexpected_query_parameters_fail_closed(analysis, query):
    response = analysis.client.get("/api/cost_analysis", query_string=query)
    assert response.status_code == 400
    assert response.get_json()["state"] in {"INVALID_SELECTION", "INVALID_REQUEST"}


@pytest.mark.parametrize("product", [
    _reference("other", "sub", "A"),
    _reference("category", "sub", "A", factory="secret-folder"),
])
def test_parent_child_and_foreign_factory_product_tampering(analysis, product):
    response = _request(analysis, category="category", subcategory="sub", product=product)
    assert response.status_code == 400 and response.get_json()["state"] == "INVALID_SELECTION"
    assert _request(analysis, category="category", subcategory="foreign").status_code == 400


def test_no_match_is_distinct_from_not_selected_and_has_unavailable_kpis(analysis):
    response = _request(analysis, category="category", subcategory="empty")
    assert response.status_code == 200
    body = response.get_json()
    assert body["state"] == "NO_MATCH"
    assert body["coverage"]["configured"] == 0 and body["detail_rows"] == []
    assert body["kpis"]["projected_total"] is None
    assert body["kpis"]["weighted_average"]["value"] is None


def test_filtering_keeps_full_category_denominator_and_agrees_with_cost_calculation(analysis):
    full = _request(analysis).get_json()
    selected = _request(analysis, category="category", subcategory="sub",
                        product=_reference("category", "sub", "A")).get_json()
    assert selected["coverage"]["configured"] == 1
    assert _amount(_row(full, "A")["unit_cost"]) == _amount(_row(selected, "A")["unit_cost"]) == Decimal("98000100")
    assert _amount(_pool(selected)["modeled_selected_total"]) == Decimal("1000")
    assert _amount(_pool(selected)["modeled_category_total"]) == Decimal("2000")
    all_grants = _client(analysis.app, "all-modules-user")
    cost = all_grants.post("/cost/get_cost", json={
        "Factory": FACTORY, "Category": "category", "Subcategory": "sub", "Product_Name": "A", "Period": "P",
    })
    assert cost.status_code == 200
    assert Decimal(str(cost.get_json()["Final_Production_Cost"])) == _amount(_row(selected, "A")["unit_cost"])


def test_same_name_products_keep_distinct_four_part_identity(analysis):
    _write(analysis.factory / "other" / "different" / "A.json", _bom([1]))
    _write(analysis.data / "Factories" / "__metadata.json", {"product_hierarchy": {
        OPERATIONAL: {"category": ["sub"], "other": ["different"]},
    }})
    _write(analysis.factory / "configuration" / "category_weights.json", {"data": {
        "category": ["category", "other"], "selling_share_of_category": [50, 50],
    }})
    # Reserved application namespaces must never add configurations.
    _write(analysis.factory / "configuration" / "bogus" / "A.json", _bom([100000]))
    _write(analysis.factory / "backups" / "bogus" / "A.json", _bom([100000]))
    response = _request(analysis)
    assert response.status_code == 200
    body = response.get_json()
    assert body["coverage"]["configured"] == 3
    same = [row for row in body["detail_rows"] if row["identity"]["product"] == "A"]
    assert len(same) == 2
    assert {(row["identity"]["category"], row["identity"]["subcategory"]) for row in same} == {
        ("category", "sub"), ("other", "different"),
    }
    assert {_amount(row["unit_cost"]) for row in same} == {Decimal("98000100"), Decimal("980200")}
    payroll = _pool(body)
    # A whole-factory raw pool appears once even when two category allocations
    # each model 2,000 from its inverse 50% share.
    assert _amount(payroll["raw_total"]) == Decimal("1000")
    assert _amount(payroll["modeled_selected_total"]) == Decimal("4000")
    assert _amount(payroll["modeled_category_total"]) == Decimal("4000")
    assert _amount(payroll["category_minus_raw"]) == Decimal("3000")
    assert {item["category"]: _amount(item["prediction_denominator"]) for item in payroll["categories"]} == {
        "category": Decimal("20"), "other": Decimal("10"),
    }


def test_partial_coverage_excludes_invalid_configuration_without_complete_total(analysis):
    _write(analysis.factory / "category" / "sub" / "B.json", _bom([40], loss=101))
    before = _snapshot(analysis.root)
    response = _request(analysis)
    assert response.status_code == 200
    body = response.get_json()
    assert body["state"] == "PARTIAL"
    assert body["coverage"] == {"configured": 2, "calculated": 1, "excluded": 1, "percentage": "50"}
    assert body["kpis"]["projected_total"] is None
    assert _amount(body["kpis"]["partial_total"]) == Decimal("980001000")
    assert body["kpis"]["partial_total_label"] == "مجموع جزئی"
    assert _row(body, "B")["unit_cost"] is None and _row(body, "B")["issues"]
    assert body["breakdowns"]["products"] == [_row(body, "A")]
    # Excluding a malformed BOM does not remove its valid prediction from the
    # full category allocation denominator.
    assert _amount(_row(body, "A")["unit_cost"]) == Decimal("98000100")
    assert body["kpis"]["top_cost_driver"]["state"] == "PARTIAL"
    assert body["kpis"]["top_cost_driver"]["id"] == "BOM"
    assert _amount(body["kpis"]["top_cost_driver"]["value"]) == Decimal("980000000")
    assert _snapshot(analysis.root) == before


def test_genuine_zero_remains_available(analysis):
    for product in ("A", "B"):
        _write(analysis.factory / "category" / "sub" / f"{product}.json", _bom([0]))
    _set_pools(analysis)
    response = _request(analysis)
    assert response.status_code == 200
    body = response.get_json()
    assert body["state"] == "OK" and _amount(body["kpis"]["projected_total"]) == 0
    assert _amount(body["kpis"]["weighted_average"]["value"]) == 0
    assert {_amount(row["unit_cost"]) for row in body["detail_rows"]} == {Decimal(0)}
    top = body["kpis"]["top_cost_driver"]
    assert top["state"] == "OK" and _amount(top["value"]) == 0
    assert top["share"] is None and top["tie"] is True
    assert top["tied_ids"] == sorted(["BOM", *FACTORY_POOL_IDS])
    assert top["id"] == top["tied_ids"][0]


def test_g4_independent_duplicate_bom_rows_contribute_100_plus_40(analysis):
    _write(analysis.data / "Overall" / "material_costs.json", {"data": {
        "material": ["lead"], "unit": ["kg"], "currency": ["IRR - Iranian Rial"],
        "cost_per_unit_in_currency": [100],
    }})
    _write(analysis.factory / "category" / "sub" / "A.json", _bom([1, 0.4], loss=0, recycling=0))
    _set_pools(analysis)
    response = _request(analysis, category="category", subcategory="sub", product=_reference("category", "sub", "A"))
    assert response.status_code == 200
    assert _amount(_row(response.get_json(), "A")["bom_total"]) == Decimal("140")
    assert _amount(_row(response.get_json(), "A")["unit_cost"]) == Decimal("140")


@pytest.mark.parametrize("changes,status", [
    ({"period": "P", "start": "2026-10-01", "end": "2026-12-31"}, 200),
    ({"start": "2026-10-01", "end": "2026-12-31"}, 200),
    ({"period": "Q"}, 422),
    ({"period": "P", "start": "2026-10-02", "end": "2026-12-31"}, 422),
    ({"start": "2026-01-01", "end": "2026-01-31"}, 422),
    ({"start": "2026-10-01"}, 400),
    ({"start": "not-date", "end": "2026-12-31"}, 400),
    ({"period": ""}, 400),
])
def test_periods_resolve_existing_bindings_only(analysis, changes, status):
    before = _snapshot(analysis.root)
    response = _request(analysis, **changes)
    assert response.status_code == status
    assert _snapshot(analysis.root) == before
    if status == 200:
        assert response.get_json()["period"]["id"] == "P"
    else:
        assert response.get_json()["kpis"]["projected_total"] is None


def test_system_initialization_binding_is_accepted_without_reapproval(analysis):
    document = json.loads(analysis.binding.read_text())
    document["bindings"][0].update(period_id="INITIAL", approved_by="SYSTEM_INITIALIZATION",
                                    approval_type="SYSTEM_INITIALIZATION")
    _write(analysis.binding, document)
    before = _snapshot(analysis.root)
    response = _request(analysis)
    assert response.status_code == 200 and response.get_json()["period"]["id"] == "INITIAL"
    assert _snapshot(analysis.root) == before


def test_omitted_period_requires_one_unique_active_binding(analysis):
    document = json.loads(analysis.binding.read_text())
    document["bindings"].append({**document["bindings"][0], "period_id": "Q"})
    _write(analysis.binding, document)
    before = _snapshot(analysis.root)
    omitted = _request(analysis)
    same_dates = _request(analysis, start="2026-10-01", end="2026-12-31")
    explicit = _request(analysis, period="P")
    assert omitted.status_code == same_dates.status_code == 422
    assert omitted.get_json()["state"] == "MISSING_INPUT"
    assert omitted.get_json()["kpis"]["projected_total"] is None
    assert explicit.status_code == 200 and explicit.get_json()["period"]["id"] == "P"
    assert _snapshot(analysis.root) == before


@pytest.mark.parametrize("lifecycle", [{"active": False}, {"approved": False}, {"status": "DRAFT"}])
def test_requested_period_requires_approved_active_lifecycle(analysis, lifecycle):
    document = json.loads(analysis.binding.read_text())
    document["bindings"][0].update(lifecycle)
    _write(analysis.binding, document)
    before = _snapshot(analysis.root)
    response = _request(analysis, period="P")
    assert response.status_code == 422 and response.get_json()["state"] == "MISSING_INPUT"
    assert response.get_json()["kpis"]["projected_total"] is None
    assert _snapshot(analysis.root) == before


@pytest.mark.parametrize("failure", ["missing-binding", "missing-v2", "missing-pool", "missing-materials", "bad-materials", "bad-bom", "invalid-share", "missing-prediction", "negative-prediction", "zero-population"])
def test_missing_and_invalid_sources_never_write_or_fabricate_zero(analysis, failure):
    if failure == "missing-binding":
        analysis.binding.unlink()
    elif failure == "missing-v2":
        shutil.rmtree(analysis.factory / "configuration")
    elif failure == "missing-pool":
        (analysis.factory / "configuration" / "cost_pools" / "Payroll.json").unlink()
    elif failure == "missing-materials":
        (analysis.data / "Overall" / "material_costs.json").unlink()
    elif failure == "bad-materials":
        (analysis.data / "Overall" / "material_costs.json").write_text("{bad", encoding="utf-8")
    elif failure == "invalid-share":
        _write(analysis.factory / "configuration" / "category_weights.json", {"data": {
            "category": ["category"], "selling_share_of_category": [0],
        }})
    elif failure in {"missing-prediction", "negative-prediction", "zero-population"}:
        values = {"missing-prediction": [10], "negative-prediction": [-1, 10], "zero-population": [0, 0]}[failure]
        _write(analysis.factory / "configuration" / "production_prediction.json", {"data": {
            "Product Name": ["A", "B"][:len(values)], "Predicted Production": values,
        }})
    else:
        for product in ("A", "B"):
            _write(analysis.factory / "category" / "sub" / f"{product}.json", _bom([1], loss=101))
    before = _snapshot(analysis.root)
    response = _request(analysis)
    assert response.status_code == 422
    body = response.get_json()
    assert body["state"] in {"MISSING_INPUT", "INVALID_INPUT", "AMBIGUOUS_INPUT", "UNAVAILABLE"}
    assert body["kpis"]["projected_total"] is None and body["kpis"]["partial_total"] is None
    assert body["kpis"]["weighted_average"]["value"] is None
    assert body["kpis"]["weighted_average"]["state"] == body["state"]
    assert body["kpis"]["top_cost_driver"]["state"] == body["state"]
    assert body["coverage"]["calculated"] == 0
    assert body["issues"] or any(row["issues"] for row in body["detail_rows"])
    assert _snapshot(analysis.root) == before
    text = response.get_data(as_text=True)
    assert str(analysis.root) not in text
    assert "JSONDecodeError" not in text and "Expecting property name" not in text


def test_read_only_loader_uses_dashboard_grant_and_never_migrates_missing_v2(analysis):
    loader = CostInputLoader(FactoryService(analysis.store), data_root=analysis.data,
                             period_bindings_path=analysis.binding, read_only=True)
    identity = ProductIdentity(FACTORY, "category", "sub", "A")
    user = analysis.store.get_user_by_id("dashboard-user")
    before = _snapshot(analysis.root)
    inputs = loader.load(FACTORY, user, identity, "P", module="dashboard")
    assert calculate_cost(inputs).to_dict()["Final_Production_Cost"] == 98000100
    assert _snapshot(analysis.root) == before
    shutil.rmtree(analysis.factory / "configuration")
    before = _snapshot(analysis.root)
    fresh_loader = CostInputLoader(FactoryService(analysis.store), data_root=analysis.data,
                                   period_bindings_path=analysis.binding, read_only=True)
    with pytest.raises(CostInputError) as error:
        fresh_loader.load(FACTORY, user, identity, "P", module="dashboard")
    assert error.value.detail.code in {"CONFIGURATION_NOT_INSTALLED", "SOURCE_UNAVAILABLE"}
    assert _snapshot(analysis.root) == before


def test_service_keeps_one_snapshot_when_source_changes_between_configurations(analysis, monkeypatch):
    from utils.dashboard_analysis import DashboardAnalysisService
    source = analysis.data / "Overall" / "material_costs.json"
    original_load = CostInputLoader.load
    calls = []

    def change_current_price_after_first_load(loader, *args, **kwargs):
        assert loader.read_only is True and kwargs["module"] == "dashboard"
        inputs = original_load(loader, *args, **kwargs)
        calls.append(inputs.identity)
        if len(calls) == 1:
            document = json.loads(source.read_text())
            document["data"]["cost_per_unit_in_currency"][0] = 2000
            _write(source, document)
        return inputs

    monkeypatch.setattr(CostInputLoader, "load", change_current_price_after_first_load)
    service = DashboardAnalysisService(FactoryService(analysis.store), data_root=analysis.data,
                                       period_bindings_path=analysis.binding)
    report = service.analyze(FACTORY, analysis.store.get_user_by_id("dashboard-user"),
                             category=ALL, subcategory=ALL, product=ALL)
    assert len(calls) == 2 and report["state"] == "OK"
    assert _row(report, "A")["unit_cost"] == Decimal("98000100")
    assert _row(report, "B")["unit_cost"] == Decimal("39200100")
    assert report["kpis"]["projected_total"] == Decimal("1372002000")
    # A later request must use the newly current source, without any cache
    # surviving beyond the prior request's immutable snapshot.
    fresh_service = DashboardAnalysisService(FactoryService(analysis.store), data_root=analysis.data,
                                             period_bindings_path=analysis.binding)
    fresh = fresh_service.analyze(FACTORY, analysis.store.get_user_by_id("dashboard-user"),
                                  category=ALL, subcategory=ALL, product=ALL)
    assert _row(fresh, "A")["unit_cost"] == Decimal("98000000100")
    assert _row(fresh, "B")["unit_cost"] == Decimal("39200000100")


def test_source_lineage_distinguishes_actual_dates_baseline_and_calculation(analysis):
    source = analysis.data / "Overall" / "material_costs.json"
    document = json.loads(source.read_text())
    document["last_modification_date"] = "2026-10-02T11:15:00Z"
    _write(source, document)
    before = _snapshot(analysis.root)
    body = _request(analysis).get_json()
    materials = next(item for item in body["source_lineage"] if item["source"] == "materials")
    assert materials["actual_as_of"] == "2026-10-02T11:15:00+00:00"
    assert materials["owner_assigned_baseline"] is None
    boms = [item for item in body["source_lineage"] if item["source"] == "bom"]
    assert len(boms) == 2
    assert all(item["actual_as_of"] is None and item["owner_assigned_baseline"] == "2026-09-27" for item in boms)
    assert all(len(item["fingerprint"]) == 64 for item in body["source_lineage"])
    assert datetime.fromisoformat(body["calculated_at"]).tzinfo is not None
    assert body["calculated_at"] != materials["actual_as_of"]
    assert _snapshot(analysis.root) == before


def test_missing_hierarchy_and_unexpected_failure_are_safe_and_read_only(analysis, monkeypatch):
    metadata = analysis.data / "Factories" / "__metadata.json"
    metadata.unlink()
    before = _snapshot(analysis.root)
    response = _request(analysis)
    assert response.status_code == 503 and response.get_json()["state"] == "UNAVAILABLE"
    assert _snapshot(analysis.root) == before
    _write(metadata, {"product_hierarchy": {OPERATIONAL: {"category": ["sub"]}}})

    def unexpected_failure(*args, **kwargs):
        raise RuntimeError(f"internal secret source at {analysis.root}/private.json")

    monkeypatch.setattr(CostInputLoader, "load", unexpected_failure)
    before = _snapshot(analysis.root)
    response = _request(analysis)
    assert response.status_code == 500
    text = response.get_data(as_text=True)
    assert "internal secret" not in text and str(analysis.root) not in text
    assert _snapshot(analysis.root) == before


def test_invalid_peer_prediction_excludes_category_without_narrowing_denominator(analysis):
    _write(analysis.factory / "configuration" / "production_prediction.json", {"data": {
        "Product Name": ["A", "B"], "Predicted Production": [10, "invalid"],
    }})
    before = _snapshot(analysis.root)
    full = _request(analysis)
    selected = _request(analysis, category="category", subcategory="sub", product=_reference("category", "sub", "A"))
    assert full.status_code == selected.status_code == 422
    assert full.get_json()["coverage"] == {"configured": 2, "calculated": 0, "excluded": 2, "percentage": "0"}
    assert selected.get_json()["coverage"] == {"configured": 1, "calculated": 0, "excluded": 1, "percentage": "0"}
    assert all(row["unit_cost"] is None for row in full.get_json()["detail_rows"])
    assert _row(selected.get_json(), "A")["unit_cost"] is None
    assert _snapshot(analysis.root) == before


def test_zero_target_prediction_is_valid_but_weighted_average_is_not_applicable(analysis):
    _write(analysis.factory / "configuration" / "production_prediction.json", {"data": {
        "Product Name": ["A", "B"], "Predicted Production": [0, 10],
    }})
    before = _snapshot(analysis.root)
    response = _request(analysis, category="category", subcategory="sub", product=_reference("category", "sub", "A"))
    assert response.status_code == 200
    body = response.get_json()
    assert body["state"] == "OK"
    assert body["coverage"] == {"configured": 1, "calculated": 1, "excluded": 0, "percentage": "100"}
    assert _amount(_row(body, "A")["prediction"]) == 0
    assert _amount(_row(body, "A")["unit_cost"]) == Decimal("98000200")
    assert _amount(body["kpis"]["projected_total"]) == 0
    average = body["kpis"]["weighted_average"]
    assert average["state"] == "NOT_APPLICABLE" and average["value"] is None
    assert _amount(average["numerator"]) == _amount(average["denominator"]) == 0
    payroll = _pool(body)
    assert _amount(payroll["modeled_selected_total"]) == 0
    assert _amount(payroll["modeled_category_total"]) == Decimal("2000")
    assert _amount(payroll["categories"][0]["prediction_denominator"]) == Decimal("10")
    assert _snapshot(analysis.root) == before


@pytest.mark.parametrize("malformation", ["missing-column", "column-length", "object-material", "list-material", "null-material"])
def test_malformed_bom_sources_return_typed_states_with_no_writes(analysis, malformation):
    for product in ("A", "B"):
        document = _bom([1])
        if malformation == "missing-column":
            del document["data"]["usage"]
        elif malformation == "column-length":
            document["data"]["usage"] = []
        else:
            document["data"]["materials"] = [{"object-material": {}, "list-material": [], "null-material": None}[malformation]]
        _write(analysis.factory / "category" / "sub" / f"{product}.json", document)
    before = _snapshot(analysis.root)
    response = _request(analysis)
    assert response.status_code == 422
    body = response.get_json()
    assert body["state"] == "INVALID_INPUT"
    assert body["coverage"]["calculated"] == 0
    assert body["kpis"]["projected_total"] is None
    assert body["kpis"]["weighted_average"]["state"] == "INVALID_INPUT"
    assert body["kpis"]["top_cost_driver"]["state"] == "INVALID_INPUT"
    assert _snapshot(analysis.root) == before


@pytest.mark.parametrize("bom_projected,winner,share,tied_ids", [
    (150, "BOM", "60", ["BOM"]),
    (100, "BOM", "50", ["BOM", "Payroll"]),
    (50, "Payroll", "66.66666666666666666666666667", ["Payroll"]),
])
def test_top_driver_ranks_bom_and_pools_with_deterministic_ties(analysis, bom_projected, winner, share, tied_ids):
    _write(analysis.data / "Overall" / "material_costs.json", {"data": {
        "material": ["lead"], "unit": ["kg"], "currency": ["IRR - Iranian Rial"],
        "cost_per_unit_in_currency": [bom_projected / 10],
    }})
    _write(analysis.factory / "category" / "sub" / "A.json", _bom([1], loss=0, recycling=0))
    _set_pools(analysis)
    pool_path = analysis.factory / "configuration" / "cost_pools" / "Payroll.json"
    pool_document = json.loads(pool_path.read_text())
    pool_document["data"]["cost"] = [100]
    _write(pool_path, pool_document)
    before = _snapshot(analysis.root)
    response = _request(analysis, category="category", subcategory="sub", product=_reference("category", "sub", "A"))
    assert response.status_code == 200
    body = response.get_json()
    drivers = {row["id"]: _amount(row["value"]) for row in body["breakdowns"]["drivers"]}
    assert drivers["BOM"] == Decimal(bom_projected) and drivers["Payroll"] == Decimal(100)
    assert _amount(body["kpis"]["projected_total"]) == Decimal(bom_projected + 100)
    top = body["kpis"]["top_cost_driver"]
    assert top["state"] == "OK" and top["id"] == winner
    assert _amount(top["value"]) == max(Decimal(bom_projected), Decimal(100))
    assert _amount(top["share"]) == Decimal(share)
    assert top["tied_ids"] == tied_ids and top["tie"] is (len(tied_ids) > 1)
    assert _snapshot(analysis.root) == before


def test_all_parent_scope_rejects_product_from_another_categories_subcategory(analysis):
    # "sub" belongs to category, not other. A global union of subcategories
    # must not make this orphan a legitimate child of other.
    _write(analysis.factory / "other" / "sub" / "Orphan.json", _bom([1]))
    _write(analysis.data / "Factories" / "__metadata.json", {"product_hierarchy": {
        OPERATIONAL: {"category": ["sub"], "other": ["different"]},
    }})
    before = _snapshot(analysis.root)
    options = analysis.client.get("/api/dashboard/filter-options", query_string={
        "factory": FACTORY, "category": ALL, "subcategory": ALL,
    })
    assert options.status_code == 200
    assert "Orphan" not in {item["label"] for item in options.get_json()["options"]["products"]}
    response = _request(analysis, product=_reference("other", "sub", "Orphan"))
    assert response.status_code == 400 and response.get_json()["state"] == "INVALID_SELECTION"
    full = _request(analysis)
    assert full.status_code == 200 and full.get_json()["coverage"]["configured"] == 2
    assert _snapshot(analysis.root) == before


def test_fractional_share_reports_decimal_residue_without_forcing_reconciliation(analysis):
    products = ["A", "B", "C", "D", "E"]
    predictions = [62, 48, 1, 52, 31]
    bom_costs = [120, 571, 219, 981, 255]
    _write(analysis.data / "Overall" / "material_costs.json", {"data": {
        "material": ["lead"], "unit": ["kg"], "currency": ["IRR - Iranian Rial"],
        "cost_per_unit_in_currency": [1],
    }})
    for product, amount in zip(products, bom_costs):
        _write(analysis.factory / "category" / "sub" / f"{product}.json", _bom([amount], loss=0, recycling=0))
    _write(analysis.factory / "configuration" / "production_prediction.json", {"data": {
        "Product Name": products, "Predicted Production": predictions,
    }})
    _write(analysis.factory / "configuration" / "category_weights.json", {"data": {
        "category": ["category"], "selling_share_of_category": [33],
    }})
    _set_pools(analysis)
    payroll_path = analysis.factory / "configuration" / "cost_pools" / "Payroll.json"
    document = json.loads(payroll_path.read_text())
    document["data"]["cost"] = [1000]
    _write(payroll_path, document)
    before = _snapshot(analysis.root)
    response = _request(analysis)
    selected = _request(analysis, category="category", subcategory="sub", product=_reference("category", "sub", "A"))
    assert response.status_code == selected.status_code == 200
    body = response.get_json()
    reconcile = body["arithmetic_reconciliation"]
    rows_total = sum((_amount(row["projected_cost"]) for row in body["detail_rows"]), Decimal(0))
    drivers_total = sum((_amount(row["value"]) for row in body["breakdowns"]["drivers"]), Decimal(0))
    assert _amount(reconcile["projected_rows_total"]) == rows_total == _amount(body["kpis"]["projected_total"])
    assert _amount(reconcile["driver_components_total"]) == drivers_total
    assert _amount(reconcile["difference"]) == rows_total - drivers_total == Decimal("-1E-23")
    assert reconcile["unit"] == "IRR/period"
    assert _amount(_row(body, "A")["unit_cost"]) == _amount(_row(selected.get_json(), "A")["unit_cost"])
    assert _amount(_pool(body)["categories"][0]["prediction_denominator"]) == Decimal(194)
    assert _amount(_pool(selected.get_json())["categories"][0]["prediction_denominator"]) == Decimal(194)
    assert _snapshot(analysis.root) == before

