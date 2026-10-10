"""PR-08 sensitivity goldens, authorization and request-local no-write contracts.

Fixtures install V2 before any request and register real blueprints without
importing app.py, whose startup migrations are intentionally outside this API.
"""

from concurrent.futures import ThreadPoolExecutor
import copy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil
import threading

import pytest

from test_dashboard_cost_analysis import (
    FACTORY, OPERATIONAL, _bom, _client, _reference, _set_pools, _snapshot,
    _write, analysis,
)
from utils.costing_engine import (
    FACTORY_POOL_IDS, CostInputLoader, CostResult, ProductIdentity, calculate_cost,
)
from utils.factory_service import FactoryService
from utils.profile_authorization import canonicalize_access_grants


PARAMETERS = "/api/dashboard/sensitivity/parameters"
SCENARIO = "/api/dashboard/sensitivity/scenario"
SELECTION = {
    "factory": FACTORY, "category": "category", "subcategory": "sub",
    "product": _reference("category", "sub", "A"), "period": "P",
}


def _grant(module, factory=FACTORY):
    return {"scope_type": "GLOBAL" if module == "general_parameters" else "FACTORY",
            "factory_id": None if module == "general_parameters" else factory,
            "module": module, "permissions": ["READ"]}


@pytest.fixture
def sensitivity(analysis):
    for user, groups in (
        ("general-only", ["general_parameters"]),
        ("factory-only", ["factory_parameters"]),
        ("both-groups", ["general_parameters", "factory_parameters"]),
        ("wrong-factory-group", []),
    ):
        grants = [_grant("dashboard"), *(_grant(group) for group in groups)]
        if user == "wrong-factory-group":
            grants.append(_grant("factory_parameters", "factory-secret"))
        analysis.store.create_user({
            "id": user, "username": user, "email": f"{user}@example.test",
            "full_name": user, "system_role": "USER", "job_title": "کاربر",
            "is_active": True, "must_change_password": False,
            "password_hash": "unused", "password_scheme": "werkzeug", "revision": 1,
            "access_grants": grants,
        })
    analysis.client = _client(analysis.app, "both-groups")
    return analysis


def _parameters(env, *, user=None, **changes):
    client = _client(env.app, user) if user else env.client
    return client.get(PARAMETERS, query_string={**SELECTION, **changes})


def _scenario(env, overrides=(), *, user=None, **changes):
    client = _client(env.app, user) if user else env.client
    return client.post(SCENARIO, json={**SELECTION, "overrides": list(overrides), **changes})


def _parameter(env, prefix, *, baseline=None):
    response = _parameters(env)
    assert response.status_code == 200
    matches = [entry for entry in response.get_json()["parameters"]
               if entry["parameter_id"].startswith(prefix)]
    if baseline is not None:
        matches = [entry for entry in matches if Decimal(entry["baseline_value"]) == Decimal(baseline)]
    assert len(matches) == 1, matches
    return matches[0]["parameter_id"]


def _change(parameter_id, value, mode="absolute"):
    return {"parameter_id": parameter_id, "mode": mode, "value": value}


def _amount(value):
    assert isinstance(value, str), "Exact API amounts must be canonical Decimal strings"
    return Decimal(value)


def _result(body, key="scenario"):
    result = body[key]
    assert result["state"] == "OK"
    return result


def _driver(result, pool="Payroll"):
    return next(item for item in result["breakdown"]["driver_components"] if item["pool_id"] == pool)


def _material_fixture(env, *, price=100, currency="IRR - Iranian Rial", usages=(1, 0.4)):
    materials = {"data": {
        "material": ["lead"], "unit": ["kg"], "currency": [currency],
        "cost_per_unit_in_currency": [price],
    }}
    if currency != "IRR - Iranian Rial":
        for field, value in {"material": currency, "unit": "currency", "currency": "IRR - Iranian Rial",
                             "cost_per_unit_in_currency": 5}.items():
            materials["data"][field].append(value)
    _write(env.data / "Overall" / "material_costs.json", materials)
    _write(env.factory / "category" / "sub" / "A.json", _bom(list(usages), loss=0, recycling=0))
    _set_pools(env)


def _g2_fixture(env, *, predictions=(10, 10), pool=1000):
    _material_fixture(env, usages=(0,))
    _write(env.factory / "configuration" / "production_prediction.json", {"data": {
        "Product Name": ["A", "B"], "Predicted Production": list(predictions),
    }})
    path = env.factory / "configuration" / "cost_pools" / "Payroll.json"
    document = json.loads(path.read_text())
    document["data"]["cost"] = [pool]
    _write(path, document)


def _safe_json(response, env):
    text = response.get_data(as_text=True)
    for forbidden in (str(env.root), "material_costs.json", "production_prediction.json",
                      "manifest.json", "Traceback", "JSONDecodeError", "internal secret"):
        assert forbidden not in text
    body = response.get_json()
    assert isinstance(body, dict)
    return body


def _nested_keys(value):
    if isinstance(value, dict):
        return set(value) | set().union(*(_nested_keys(item) for item in value.values()), set())
    if isinstance(value, list):
        return set().union(*(_nested_keys(item) for item in value), set())
    return set()


def test_registry_exposes_only_mapped_authorized_inputs_with_genuine_provenance(sensitivity):
    before = _snapshot(sensitivity.root)
    response = _parameters(sensitivity)
    assert response.status_code == 200
    body = _safe_json(response, sensitivity)
    assert body["version"] == "1" and body["state"] == "OK" and body["non_persistent"] is True
    assert body["identity"] == {"factory_id": FACTORY, "category": "category", "subcategory": "sub", "product": "A"}
    assert body["period"] == {"id": "P", "start": "2026-10-01", "end": "2026-12-31"}
    entries = body["parameters"]
    assert len(entries) == 10  # material, foreign FX, six pools, share, prediction.
    ids = [entry["parameter_id"] for entry in entries]
    assert len(set(ids)) == len(ids)
    assert {item for item in ids if item.startswith("pool:")} == {f"pool:{pool}" for pool in FACTORY_POOL_IDS}
    assert not any("IRR" in item for item in ids if item.startswith("fx:"))
    for entry in entries:
        assert {"parameter_id", "group", "label", "unit", "numeric_type", "baseline_value",
                "supported_modes", "domain", "applicable", "editable", "reason", "source_reference",
                "provenance", "dependencies"} <= set(entry)
        assert entry["supported_modes"] == ["absolute", "percent_change"]
        assert entry["applicable"] is True and entry["editable"] is True
        assert entry["dependencies"] and entry["source_reference"]
        assert _amount(entry["baseline_value"]).is_finite()
        assert entry["provenance"]
    for entry in entries:
        if entry["parameter_id"].startswith("pool:"):
            assert entry["unit"] == "IRR/period"
    assert body["unsupported_parameters"]
    assert "historical_cost_in_rial" not in _nested_keys(body)
    assert _snapshot(sensitivity.root) == before


def test_empty_overrides_equal_baseline_analysis_and_shared_calculation_without_writes(sensitivity):
    sensitivity.store.update_user("both-groups", {"access_grants": canonicalize_access_grants([
        _grant("dashboard"), _grant("general_parameters"), _grant("factory_parameters"), _grant("cost_calculation"),
    ], [FACTORY])})
    before = _snapshot(sensitivity.root)
    response = _scenario(sensitivity)
    assert response.status_code == 200
    body = _safe_json(response, sensitivity)
    baseline, scenario = _result(body, "baseline"), _result(body)
    assert baseline == scenario
    assert _amount(body["delta"]["amount"]) == 0 and _amount(body["delta"]["percentage"]) == 0
    assert body["effective_overrides"] == [] and body["non_persistent"] is True
    assert {"Final_Production_Cost", "BOM_Details", "historical_cost_in_rial"}.isdisjoint(_nested_keys(body))
    analysis_body = sensitivity.client.get("/api/cost_analysis", query_string=SELECTION).get_json()
    row = analysis_body["detail_rows"][0]
    cost = sensitivity.client.post("/cost/get_cost", json={
        "Factory": FACTORY, "Category": "category", "Subcategory": "sub", "Product_Name": "A", "Period": "P",
    })
    assert cost.status_code == 200
    for field in ("unit_cost", "bom_total", "projected_cost"):
        assert _amount(baseline[field]) == _amount(row[field])
    assert _amount(baseline["unit_cost"]) == _amount(cost.get_json()["value"])
    loader = CostInputLoader(FactoryService(sensitivity.store), data_root=sensitivity.data,
                             period_bindings_path=sensitivity.binding, read_only=True)
    inputs = loader.load(FACTORY, sensitivity.store.get_user_by_id("both-groups"),
                         ProductIdentity(FACTORY, "category", "sub", "A"), "P", module="dashboard")
    assert _amount(baseline["unit_cost"]) == calculate_cost(inputs).value
    assert _snapshot(sensitivity.root) == before


def test_duplicate_material_price_fans_out_to_both_independent_bom_rows(sensitivity):
    _material_fixture(sensitivity)
    parameter = _parameter(sensitivity, "material:")
    before = _snapshot(sensitivity.root)
    response = _scenario(sensitivity, [_change(parameter, "10", "percent_change")])
    assert response.status_code == 200
    body = response.get_json()
    baseline, scenario = _result(body, "baseline"), _result(body)
    assert _amount(baseline["bom_total"]) == _amount(baseline["unit_cost"]) == 140
    assert _amount(scenario["bom_total"]) == _amount(scenario["unit_cost"]) == 154
    components = scenario["breakdown"]["bom_components"]
    assert len(components) == 2 and len({item["row_id"] for item in components}) == 2
    assert [_amount(item["live_cost_in_rial"]) for item in components] == [110, 44]
    assert _amount(body["delta"]["amount"]) == 14 and _amount(body["delta"]["percentage"]) == 10
    assert _amount(body["effective_overrides"][0]["baseline_value"]) == 100
    assert _amount(body["effective_overrides"][0]["final_value"]) == 110
    assert _snapshot(sensitivity.root) == before


def test_foreign_fx_change_affects_every_applicable_row_and_irr_is_fixed(sensitivity):
    _material_fixture(sensitivity, currency="USD", usages=(1, 0.4))
    fx = _parameter(sensitivity, "fx:")
    body = _scenario(sensitivity, [_change(fx, "20", "percent_change")]).get_json()
    assert _amount(_result(body, "baseline")["bom_total"]) == 700
    assert _amount(_result(body)["bom_total"]) == 840
    assert [_amount(item["live_cost_in_rial"]) for item in _result(body)["breakdown"]["bom_components"]] == [600, 240]
    _material_fixture(sensitivity, usages=(1,))
    assert not any(entry["parameter_id"].startswith("fx:") for entry in _parameters(sensitivity).get_json()["parameters"])
    forged = _scenario(sensitivity, [_change("fx:IRR", "2")])
    assert forged.status_code == 400


@pytest.mark.parametrize("pool", FACTORY_POOL_IDS)
def test_each_of_six_whole_factory_pool_amounts_recalculates(sensitivity, pool):
    _g2_fixture(sensitivity, pool=0)
    parameter = _parameter(sensitivity, f"pool:{pool}")
    body = _scenario(sensitivity, [_change(parameter, "1000")]).get_json()
    assert _amount(_result(body, "baseline")["unit_cost"]) == 0
    scenario = _result(body)
    assert _amount(scenario["unit_cost"]) == 100 and _amount(scenario["projected_cost"]) == 1000
    component = _driver(scenario, pool)
    assert _amount(component["raw_factory_pool"]) == 1000
    assert _amount(component["adjusted_category_pool"]) == 2000
    assert _amount(component["category_prediction_total"]) == 20


def test_g2_prediction_updates_full_category_denominator_and_selected_projection(sensitivity):
    _g2_fixture(sensitivity)
    prediction = _parameter(sensitivity, "prediction:")
    before = _snapshot(sensitivity.root)
    body = _scenario(sensitivity, [_change(prediction, "30")]).get_json()
    baseline, scenario = _result(body, "baseline"), _result(body)
    assert _amount(baseline["unit_cost"]) == 100 and _amount(baseline["projected_cost"]) == 1000
    assert _amount(scenario["unit_cost"]) == 50 and _amount(scenario["projected_cost"]) == 1500
    assert _amount(_driver(baseline)["category_prediction_total"]) == 20
    assert _amount(_driver(scenario)["category_prediction_total"]) == 40
    assert _amount(body["delta"]["amount"]) == -50 and _amount(body["delta"]["percentage"]) == -50
    assert _snapshot(sensitivity.root) == before


def test_share_absolute_preserves_inverse_allocation_and_percent_is_relative(sensitivity):
    _g2_fixture(sensitivity)
    share = _parameter(sensitivity, "category_share:")
    absolute = _scenario(sensitivity, [_change(share, "25")]).get_json()
    assert _amount(_driver(_result(absolute))["adjusted_category_pool"]) == 4000
    assert _amount(_result(absolute)["unit_cost"]) == 200
    relative = _scenario(sensitivity, [_change(share, "10", "percent_change")]).get_json()
    assert _amount(relative["effective_overrides"][0]["final_value"]) == 55
    assert _amount(_result(relative)["unit_cost"]) == Decimal(1000) / Decimal("0.55") / 20


def test_distinct_override_order_does_not_change_baseline_or_scenario(sensitivity):
    material = _parameter(sensitivity, "material:")
    fx = _parameter(sensitivity, "fx:")
    share = _parameter(sensitivity, "category_share:")
    prediction = _parameter(sensitivity, "prediction:")
    overrides = [_change(material, "10", "percent_change"), _change(fx, "400000"),
                 _change("pool:Payroll", "1200"), _change(share, "25"), _change(prediction, "30")]
    before = _snapshot(sensitivity.root)
    one, two = (_scenario(sensitivity, values).get_json() for values in (overrides, list(reversed(overrides))))
    assert _result(one, "baseline") == _result(two, "baseline")
    assert _result(one) == _result(two) and one["delta"] == two["delta"]
    assert one["source_lineage"] == two["source_lineage"]
    assert _snapshot(sensitivity.root) == before


def test_zero_baseline_is_undefined_percentage_and_zero_selected_quantity_is_valid(sensitivity):
    _g2_fixture(sensitivity, predictions=(0, 10), pool=0)
    body = _scenario(sensitivity, [_change("pool:Payroll", "1000")]).get_json()
    assert _amount(_result(body, "baseline")["unit_cost"]) == 0
    assert _amount(_result(body)["unit_cost"]) == 200
    assert _amount(_result(body)["projected_cost"]) == 0
    assert _amount(body["delta"]["amount"]) == 200
    assert body["delta"]["percentage"] is None and body["delta"]["percentage_state"] == "NOT_APPLICABLE"
    prediction = _parameter(sensitivity, "prediction:")
    percent = _scenario(sensitivity, [_change(prediction, "500", "percent_change")]).get_json()
    assert _amount(percent["effective_overrides"][0]["final_value"]) == 0


@pytest.mark.parametrize("prefix,value,mode", [
    ("material:", "-1", "absolute"), ("material:", "-101", "percent_change"),
    ("fx:", "0", "absolute"), ("fx:", "-100", "percent_change"),
    ("pool:Payroll", "-1", "absolute"), ("pool:Payroll", "-101", "percent_change"),
    ("category_share:", "0", "absolute"), ("category_share:", "100.0001", "absolute"),
    ("category_share:", "101", "percent_change"), ("prediction:", "-1", "absolute"),
])
def test_out_of_domain_final_values_are_rejected_without_writes(sensitivity, prefix, value, mode):
    parameter = _parameter(sensitivity, prefix)
    before = _snapshot(sensitivity.root)
    response = _scenario(sensitivity, [_change(parameter, value, mode)])
    assert response.status_code == 400
    body = _safe_json(response, sensitivity)
    assert body["identity"]["product"] == "A" and body["period"]["id"] == "P"
    assert body["baseline"]["state"] == "OK"
    assert body["scenario"]["state"] == "INVALID_INPUT"
    assert body["scenario"]["unit_cost"] is body["scenario"]["projected_cost"] is None
    assert body["effective_overrides"] == [] and body["delta"] is None
    assert _snapshot(sensitivity.root) == before


def test_prediction_override_cannot_make_full_category_denominator_zero(sensitivity):
    _g2_fixture(sensitivity, predictions=(10, 0))
    parameter = _parameter(sensitivity, "prediction:")
    response = _scenario(sensitivity, [_change(parameter, "0")])
    assert response.status_code == 400
    assert response.get_json()["state"] in {"INVALID_REQUEST", "INVALID_INPUT"}


@pytest.mark.parametrize("value", [None, True, 10, 1.5, "", "NaN", "Infinity", "-Infinity",
                                   "1e2", "+1", "01", " 1", "1 ", "1.", ".1", "1" * 129])
def test_override_values_require_canonical_finite_decimal_strings(sensitivity, value):
    before = _snapshot(sensitivity.root)
    response = _scenario(sensitivity, [_change("pool:Payroll", value)])
    assert response.status_code == 400
    _safe_json(response, sensitivity)
    assert _snapshot(sensitivity.root) == before


@pytest.mark.parametrize("overrides", [
    None, {}, "not-list", [None], [[]], ["not-object"],
    [{"parameter_id": "pool:Payroll", "value": "100"}],
    [{"parameter_id": "pool:Payroll", "mode": "absolute", "value": "100", "baseline_value": "0"}],
    [_change("pool:Payroll", "100", "percentage_points")],
    [_change("pool:Payroll", "100"), _change("pool:Payroll", "200")],
    [_change("pool:Payroll", "100"), _change("pool:Payroll", "100")],
    [_change("historical_bom_cost:any", "100")],
    [_change("material:forged", "100")],
    [_change("pool:Payroll", "100")] * 65,
])
def test_malformed_duplicate_unknown_and_oversized_overrides_fail_closed(sensitivity, overrides):
    before = _snapshot(sensitivity.root)
    response = sensitivity.client.post(SCENARIO, json={**SELECTION, "overrides": overrides})
    assert response.status_code == 400
    _safe_json(response, sensitivity)
    assert _snapshot(sensitivity.root) == before


@pytest.mark.parametrize("body", [None, [], "not-object", 1, True,
                                  {**SELECTION}, {**SELECTION, "overrides": [], "baseline": 0},
                                  {**SELECTION, "overrides": [], "products": ["A", "B"]}])
def test_post_requires_an_exact_single_selection_object(sensitivity, body):
    before = _snapshot(sensitivity.root)
    response = sensitivity.client.post(SCENARIO, data=json.dumps(body), content_type="application/json")
    assert response.status_code == 400
    assert _snapshot(sensitivity.root) == before


@pytest.mark.parametrize("data,content_type,status", [
    ("{bad", "application/json", 400), ("{}", "text/plain", 400),
    ('{"factory":"one","factory":"two","overrides":[]}', "application/json", 400),
    ('{"overrides":[{"parameter_id":"a","parameter_id":"b","mode":"absolute","value":"1"}]}', "application/json", 400),
    (" " * 65537, "application/json", 413),
], ids=["syntax", "mime", "duplicate-root", "duplicate-nested", "technical-size"])
def test_post_rejects_malformed_mime_duplicate_json_keys_and_technical_size_limit(sensitivity, data, content_type, status):
    before = _snapshot(sensitivity.root)
    response = sensitivity.client.post(SCENARIO, data=data, content_type=content_type)
    assert response.status_code == status
    assert _snapshot(sensitivity.root) == before


@pytest.mark.parametrize("field,value", [
    ("factory", "__ALL__"), ("category", "__ALL__"), ("subcategory", "__ALL__"), ("product", "__ALL__"),
    ("factory", ""), ("category", ""), ("subcategory", ""), ("product", "A"), ("period", ""),
    ("category", "other"), ("subcategory", "other"),
    ("product", _reference("other", "sub", "A")),
    ("product", _reference("category", "sub", "A", factory="secret-folder")),
    ("product", [SELECTION["product"]]), ("category", "../category"),
])
def test_parameters_and_scenario_reject_broad_missing_or_forged_selections(sensitivity, field, value):
    before = _snapshot(sensitivity.root)
    if not isinstance(value, list):
        assert _parameters(sensitivity, **{field: value}).status_code == 400
    assert _scenario(sensitivity, **{field: value}).status_code == 400
    assert _snapshot(sensitivity.root) == before


@pytest.mark.parametrize("missing", SELECTION)
def test_all_five_explicit_selections_are_required_on_each_endpoint(sensitivity, missing):
    selected = {key: value for key, value in SELECTION.items() if key != missing}
    assert sensitivity.client.get(PARAMETERS, query_string=selected).status_code == 400
    assert sensitivity.client.post(SCENARIO, json={**selected, "overrides": []}).status_code == 400


@pytest.mark.parametrize("query", [
    [*SELECTION.items(), ("category", "category")],
    [*SELECTION.items(), ("period", "P")],
    [*SELECTION.items(), ("parameter_id", "pool:Payroll")],
])
def test_get_rejects_repeated_and_unknown_query_fields(sensitivity, query):
    assert sensitivity.client.get(PARAMETERS, query_string=query).status_code == 400


@pytest.mark.parametrize("changes,status", [
    ({"start": "2026-10-01", "end": "2026-12-31"}, 200),
    ({"start": "2026-10-02", "end": "2026-12-31"}, 422),
    ({"period": "Q"}, 422), ({"start": "2026-10-01"}, 400),
    ({"start": "not-date", "end": "2026-12-31"}, 400),
])
def test_existing_period_binding_and_exact_dates_are_required_without_writes(sensitivity, changes, status):
    before = _snapshot(sensitivity.root)
    assert _parameters(sensitivity, **changes).status_code == status
    assert _scenario(sensitivity, **changes).status_code == status
    assert _snapshot(sensitivity.root) == before


def test_system_initialization_existing_binding_is_accepted(sensitivity):
    document = json.loads(sensitivity.binding.read_text())
    document["bindings"][0].update(approved_by="SYSTEM_INITIALIZATION", approval_type="SYSTEM_INITIALIZATION")
    _write(sensitivity.binding, document)
    before = _snapshot(sensitivity.root)
    assert _parameters(sensitivity).status_code == _scenario(sensitivity).status_code == 200
    assert _snapshot(sensitivity.root) == before


@pytest.mark.parametrize("user,groups", [
    ("general-only", {"general_parameters"}), ("factory-only", {"factory_parameters"}),
    ("both-groups", {"general_parameters", "factory_parameters"}),
    ("dashboard-user", set()), ("wrong-factory-group", set()),
    ("admin", {"general_parameters", "factory_parameters"}),
    ("finance-admin", {"general_parameters", "factory_parameters"}),
])
def test_permission_matrix_lists_only_authorized_groups_and_redacts_nested_inputs(sensitivity, user, groups):
    before = _snapshot(sensitivity.root)
    response = _parameters(sensitivity, user=user)
    assert response.status_code == 200
    body = _safe_json(response, sensitivity)
    assert {entry["group"] for entry in body["parameters"]} == groups
    assert all(item.get("group") is None or item["group"] in groups for item in body["unsupported_parameters"])
    sources = {item["source"] for item in body["source_lineage"]}
    if "general_parameters" not in groups:
        assert "materials" not in sources
    if "factory_parameters" not in groups:
        assert {"weights", "predictions", "configuration", *(f"pool:{pool}" for pool in FACTORY_POOL_IDS)}.isdisjoint(sources)
    response = _scenario(sensitivity, user=user)
    assert response.status_code == 200
    body = _safe_json(response, sensitivity)
    keys = _nested_keys(body)
    assert "historical_cost_in_rial" not in keys
    if "general_parameters" not in groups:
        assert {"unit_price", "fx_rate", "usage", "loss_percentage", "recyclability_percentage",
                "gross_cost_in_rial", "adjustment_factor"}.isdisjoint(keys)
    if "factory_parameters" not in groups:
        assert {"prediction", "category_share", "raw_factory_pool", "adjusted_category_pool",
                "category_prediction_total", "modeled_minus_raw"}.isdisjoint(keys)
    assert _snapshot(sensitivity.root) == before


def test_read_grants_allow_only_their_own_group_and_forgeries_do_not_reveal_values(sensitivity):
    material = _parameter(sensitivity, "material:")
    assert _scenario(sensitivity, [_change(material, "3")], user="general-only").status_code == 200
    assert _scenario(sensitivity, [_change("pool:Payroll", "2000")], user="factory-only").status_code == 200
    for user, parameter in (("general-only", "pool:Payroll"), ("factory-only", material),
                            ("dashboard-user", material), ("wrong-factory-group", "pool:Payroll")):
        before = _snapshot(sensitivity.root)
        response = _scenario(sensitivity, [_change(parameter, "2")], user=user)
        assert response.status_code == 403
        body = _safe_json(response, sensitivity)
        assert {"baseline_value", "final_value", "parameter_id", "raw_factory_pool"}.isdisjoint(_nested_keys(body))
        assert _snapshot(sensitivity.root) == before


@pytest.mark.parametrize("group,prefix", [("general_parameters", "material:"), ("factory_parameters", "pool:Payroll")])
def test_post_rechecks_grants_after_parameter_listing(sensitivity, group, prefix):
    parameter = _parameter(sensitivity, prefix)
    user = sensitivity.store.get_user_by_id("both-groups")
    sensitivity.store.update_user("both-groups", {"access_grants": [
        grant for grant in user["access_grants"] if grant["module"] != group
    ]})
    before = _snapshot(sensitivity.root)
    response = _scenario(sensitivity, [_change(parameter, "2")])
    assert response.status_code == 403
    _safe_json(response, sensitivity)
    assert _snapshot(sensitivity.root) == before


@pytest.mark.parametrize("factory,status", [("factory-secret", 403), ("factory-inactive", 403), ("unknown", 404), (OPERATIONAL, 404)])
def test_exact_factory_authorization_precedes_operational_lookup(sensitivity, monkeypatch, factory, status):
    def unexpected(*args, **kwargs):
        pytest.fail("Operational lookup must follow exact factory authorization")
    monkeypatch.setattr(FactoryService, "operational_key", unexpected)
    before = _snapshot(sensitivity.root)
    assert _parameters(sensitivity, factory=factory).status_code == status
    assert _scenario(sensitivity, factory=factory).status_code == status
    assert _snapshot(sensitivity.root) == before


def test_authentication_and_dashboard_denial_behavior_is_preserved(sensitivity):
    assert sensitivity.app.test_client().get(PARAMETERS, query_string=SELECTION).status_code == 302
    assert sensitivity.app.test_client().post(SCENARIO, json={**SELECTION, "overrides": []}).status_code == 302
    assert _parameters(sensitivity, user="cost-only-user").status_code == 403
    assert _scenario(sensitivity, user="cost-only-user").status_code == 403


def test_installed_post_protection_runs_for_sensitivity_route(sensitivity):
    # Install before the first request, as required by Flask's setup contract.
    from flask import abort, request
    @sensitivity.app.before_request
    def reject_untrusted_post():
        if request.method == "POST" and request.headers.get("X-Test-CSRF") != "valid":
            abort(403)
    assert _scenario(sensitivity).status_code == 403
    assert sensitivity.client.post(SCENARIO, json={**SELECTION, "overrides": []},
                                   headers={"X-Test-CSRF": "valid"}).status_code == 200


def test_middleware_may_read_cached_json_without_consuming_scenario_body(sensitivity):
    from flask import request
    captured = []
    @sensitivity.app.before_request
    def existing_body_inspection():
        if request.method == "POST":
            captured.append(request.get_json())
    response = _scenario(sensitivity, [_change("pool:Payroll", "2000")])
    assert response.status_code == 200
    assert captured == [{**SELECTION, "overrides": [_change("pool:Payroll", "2000")]}]
    assert _amount(_driver(_result(response.get_json()))["raw_factory_pool"]) == 2000


def test_existing_stricter_application_content_length_limit_is_preserved(sensitivity):
    sensitivity.app.config["MAX_CONTENT_LENGTH"] = 128
    before = _snapshot(sensitivity.root)
    response = _scenario(sensitivity)
    assert response.status_code == 413
    assert _snapshot(sensitivity.root) == before


@pytest.mark.parametrize("failure", ["materials-missing", "materials-bad", "materials-ambiguous", "fx-ambiguous",
                                     "bom-invalid", "manifest-missing", "pool-missing", "share-invalid",
                                     "prediction-missing", "peer-prediction-invalid", "zero-denominator", "bindings-missing"])
def test_failed_canonical_sources_cannot_be_repaired_by_overrides_or_create_artifacts(sensitivity, failure):
    parameter = _parameter(sensitivity, "material:")
    materials = sensitivity.data / "Overall" / "material_costs.json"
    if failure == "materials-missing":
        materials.unlink()
    elif failure == "materials-bad":
        materials.write_text("{bad", encoding="utf-8")
    elif failure in {"materials-ambiguous", "fx-ambiguous"}:
        document = json.loads(materials.read_text())
        index = 0 if failure == "materials-ambiguous" else 1
        for values in document["data"].values():
            values.append(values[index])
        _write(materials, document)
    elif failure == "bom-invalid":
        _write(sensitivity.factory / "category" / "sub" / "A.json", _bom([1], loss=101))
    elif failure == "manifest-missing":
        shutil.rmtree(sensitivity.factory / "configuration")
    elif failure == "pool-missing":
        (sensitivity.factory / "configuration" / "cost_pools" / "Payroll.json").unlink()
    elif failure == "share-invalid":
        _write(sensitivity.factory / "configuration" / "category_weights.json", {"data": {
            "category": ["category"], "selling_share_of_category": [0],
        }})
    elif failure in {"prediction-missing", "peer-prediction-invalid", "zero-denominator"}:
        values = {"prediction-missing": [10], "peer-prediction-invalid": [10, "invalid"], "zero-denominator": [0, 0]}[failure]
        _write(sensitivity.factory / "configuration" / "production_prediction.json", {"data": {
            "Product Name": ["A", "B"][:len(values)], "Predicted Production": values,
        }})
    else:
        sensitivity.binding.unlink()
    before = _snapshot(sensitivity.root)
    for response in (_parameters(sensitivity), _scenario(sensitivity, [_change(parameter, "100")])):
        assert response.status_code == 422
        body = _safe_json(response, sensitivity)
        assert body["state"] in {"MISSING_INPUT", "INVALID_INPUT", "AMBIGUOUS_INPUT"}
        assert body["issues"]
        assert body["identity"] == {"factory_id": FACTORY, "category": "category", "subcategory": "sub", "product": "A"}
        if failure != "bindings-missing":
            assert body["period"]["id"] == "P"
        assert body["baseline"]["state"] == body["state"]
        assert body["baseline"]["unit"] == "IRR/product"
        assert body["baseline"]["projected_cost_unit"] == "IRR/period"
        assert body["baseline"]["unit_cost"] is body["baseline"]["projected_cost"] is None
        assert body["baseline"]["bom_total"] is body["baseline"]["driver_total"] is None
        assert body["baseline"]["breakdown"] == {"bom_components": [], "driver_components": []}
        assert body["scenario"] is body["delta"] is None
        assert _snapshot(sensitivity.root) == before


def test_unused_parameters_are_excluded_and_legitimate_zero_effect_is_distinguished(sensitivity):
    source = sensitivity.data / "Overall" / "material_costs.json"
    document = json.loads(source.read_text())
    for field, value in {"material": "unused", "unit": "kg", "currency": "IRR - Iranian Rial",
                         "cost_per_unit_in_currency": 900}.items():
        document["data"][field].append(value)
    _write(source, document)
    body = _parameters(sensitivity).get_json()
    assert not any(Decimal(entry["baseline_value"]) == 900 for entry in body["parameters"])
    _g2_fixture(sensitivity)
    parameter = _parameter(sensitivity, "material:")
    body = _scenario(sensitivity, [_change(parameter, "200")]).get_json()
    assert _amount(_result(body)["unit_cost"]) == _amount(_result(body, "baseline")["unit_cost"]) == 100
    assert _amount(body["effective_overrides"][0]["final_value"]) == 200
    assert _amount(body["delta"]["amount"]) == 0


def test_source_aliases_are_coherent_individually_and_conflict_when_combined(sensitivity):
    _write(sensitivity.factory / "category" / "sub" / "A.json", {"data": {
        "materials": ["lead", "USD"], "usage": [1, 1], "lost_percentage": [0, 0],
        "recycability_percentage": [0, 0], "cost_of_material_in_rial": [0, 0],
    }})
    _set_pools(sensitivity)
    price = _parameter(sensitivity, "material:", baseline=500000)
    fx = _parameter(sensitivity, "fx:")
    before = _snapshot(sensitivity.root)
    for parameter in (price, fx):
        body = _scenario(sensitivity, [_change(parameter, "600000")]).get_json()
        assert _amount(_result(body, "baseline")["unit_cost"]) == 1500000
        assert _amount(_result(body)["unit_cost"]) == 1800000
    for values in ([_change(price, "600000"), _change(fx, "600000")],
                   [_change(fx, "600000"), _change(price, "700000")]):
        response = _scenario(sensitivity, values)
        assert response.status_code == 400
        assert any(issue["code"] == "CONFLICTING_SOURCE_OVERRIDES" for issue in response.get_json()["issues"])
    assert _snapshot(sensitivity.root) == before


def test_same_factory_pool_source_alias_updates_both_dependencies_and_rejects_conflict(sensitivity):
    _g2_fixture(sensitivity)
    target = sensitivity.factory / "configuration" / "cost_pools" / "Payroll.json"
    alias = target.with_name("Overhead.json")
    alias.unlink()
    alias.symlink_to(target.name)
    before = _snapshot(sensitivity.root)
    body = _scenario(sensitivity, [_change("pool:Payroll", "2000")]).get_json()
    assert _amount(_result(body, "baseline")["unit_cost"]) == 200
    assert _amount(_result(body)["unit_cost"]) == 400
    assert _amount(_driver(_result(body), "Payroll")["raw_factory_pool"]) == 2000
    assert _amount(_driver(_result(body), "Overhead")["raw_factory_pool"]) == 2000
    response = _scenario(sensitivity, [_change("pool:Payroll", "2000"), _change("pool:Overhead", "3000")])
    assert response.status_code == 400
    assert any(issue["code"] == "CONFLICTING_SOURCE_OVERRIDES" for issue in response.get_json()["issues"])
    assert _snapshot(sensitivity.root) == before


@pytest.mark.parametrize("same_material", [True, False])
def test_duplicate_explicit_bom_row_ids_cannot_map_distinct_independent_inputs(sensitivity, same_material):
    _material_fixture(sensitivity)
    source = sensitivity.data / "Overall" / "material_costs.json"
    document = json.loads(source.read_text())
    for field, value in {"material": "other", "unit": "kg", "currency": "IRR - Iranian Rial",
                         "cost_per_unit_in_currency": 200}.items():
        document["data"][field].append(value)
    _write(source, document)
    bom = _bom([1, 1], loss=0, recycling=0)
    bom["data"]["row_id"] = ["same-row", "same-row"]
    if not same_material:
        bom["data"]["materials"] = ["lead", "other"]
    _write(sensitivity.factory / "category" / "sub" / "A.json", bom)
    before = _snapshot(sensitivity.root)
    for response in (_parameters(sensitivity), _scenario(sensitivity)):
        assert response.status_code == 422
        assert response.get_json()["state"] == "AMBIGUOUS_INPUT"
    assert _snapshot(sensitivity.root) == before


@pytest.mark.parametrize("category", ["category", "different-category"])
def test_ambiguous_prediction_mapping_same_product_name_is_not_a_product_specific_control(sensitivity, category):
    _write(sensitivity.factory / category / "other" / "A.json", _bom([1]))
    _write(sensitivity.data / "Factories" / "__metadata.json", {"product_hierarchy": {
        OPERATIONAL: {"category": ["sub", "other"], **({category: ["other"]} if category != "category" else {})},
    }})
    before = _snapshot(sensitivity.root)
    body = _parameters(sensitivity).get_json()
    assert not any(entry["parameter_id"].startswith("prediction:") for entry in body["parameters"])
    assert any("prediction" in json.dumps(item).lower() for item in body["unsupported_parameters"])
    assert _snapshot(sensitivity.root) == before


def test_serialization_whitelist_does_not_use_legacy_costresult_to_dict(sensitivity, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Sensitivity must serialize a permission-aware Decimal whitelist")
    monkeypatch.setattr(CostResult, "to_dict", forbidden)
    assert _scenario(sensitivity).status_code == 200


def test_unauthorized_group_ids_are_rejected_before_any_source_lookup(sensitivity, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("A denied parameter group must fail before operational source capture")
    monkeypatch.setattr(CostInputLoader, "snapshot_population", unexpected)
    for user, parameter in (("general-only", "pool:Payroll"), ("factory-only", "material:forged"),
                            ("dashboard-user", "fx:forged")):
        assert _scenario(sensitivity, [_change(parameter, "1")], user=user).status_code == 403


@pytest.mark.parametrize("group", ["general_parameters", "factory_parameters"])
def test_protected_baseline_validation_details_are_redacted_from_other_group(sensitivity, group):
    if group == "general_parameters":
        source = sensitivity.data / "Overall" / "material_costs.json"
        document = json.loads(source.read_text())
        document["data"]["cost_per_unit_in_currency"][1] = 0
        _write(source, document)
        user = "factory-only"
        private_code = "INVALID_FX_RATE"
    else:
        _write(sensitivity.factory / "configuration" / "category_weights.json", {"data": {
            "category": ["category"], "selling_share_of_category": [0],
        }})
        user = "general-only"
        private_code = "INVALID_CATEGORY_SHARE"
    before = _snapshot(sensitivity.root)
    for response in (_parameters(sensitivity, user=user), _scenario(sensitivity, user=user)):
        assert response.status_code == 422
        body = _safe_json(response, sensitivity)
        assert private_code not in json.dumps(body)
        assert body["issues"][0]["code"] == "BASELINE_UNAVAILABLE"
        assert _snapshot(sensitivity.root) == before


def test_missing_hierarchy_is_unavailable_and_never_writes(sensitivity):
    (sensitivity.data / "Factories" / "__metadata.json").unlink()
    before = _snapshot(sensitivity.root)
    for response in (_parameters(sensitivity), _scenario(sensitivity)):
        assert response.status_code == 503
        assert _safe_json(response, sensitivity)["state"] == "UNAVAILABLE"
        assert _snapshot(sensitivity.root) == before


@pytest.mark.parametrize("kind", ["fx", "prediction"])
def test_mathematical_zero_effect_is_truthful_for_connected_parameters(sensitivity, kind):
    if kind == "fx":
        _material_fixture(sensitivity, price=0, currency="USD", usages=(1,))
    else:
        _material_fixture(sensitivity, usages=(1,))
        _write(sensitivity.factory / "category" / "sub" / "A.json", _bom([1], loss=100, recycling=100))
    entry = next(entry for entry in _parameters(sensitivity).get_json()["parameters"]
                 if entry["parameter_id"].startswith(kind + ":"))
    assert entry["effect_state"] == "MATHEMATICAL_ZERO" and entry["dependencies"]
    response = _scenario(sensitivity, [_change(entry["parameter_id"], "50", "percent_change")])
    assert response.status_code == 200
    assert _amount(response.get_json()["delta"]["amount"]) == 0


def test_nonnegative_zero_and_large_inputs_have_no_invented_financial_caps(sensitivity):
    _material_fixture(sensitivity)
    material = _parameter(sensitivity, "material:")
    zero = _scenario(sensitivity, [_change(material, "-100", "percent_change")]).get_json()
    assert _amount(_result(zero)["unit_cost"]) == 0
    large = "1" + "0" * 60
    response = _scenario(sensitivity, [_change(material, large)])
    assert response.status_code == 200
    assert _amount(response.get_json()["effective_overrides"][0]["final_value"]) == Decimal(large)


def test_decimal_precision_is_preserved_without_intermediate_api_rounding(sensitivity):
    _material_fixture(sensitivity, usages=(1,))
    material = _parameter(sensitivity, "material:")
    value = "0.1234567890123456789012345678"
    body = _scenario(sensitivity, [_change(material, value)]).get_json()
    assert _amount(_result(body)["unit_cost"]) == Decimal(value)
    assert _amount(body["effective_overrides"][0]["final_value"]) == Decimal(value)


def test_post_rebuilds_fresh_baseline_and_preserves_truthful_provenance(sensitivity):
    _material_fixture(sensitivity)
    listed = _parameters(sensitivity).get_json()
    material = next(entry["parameter_id"] for entry in listed["parameters"] if entry["parameter_id"].startswith("material:"))
    source = sensitivity.data / "Overall" / "material_costs.json"
    document = json.loads(source.read_text())
    document["data"]["cost_per_unit_in_currency"][0] = 1000
    document["last_modification_date"] = "2026-10-02T11:15:00Z"
    _write(source, document)
    fingerprint = hashlib.sha256(source.read_bytes()).hexdigest()
    before = _snapshot(sensitivity.root)
    body = _scenario(sensitivity, [_change(material, "10", "percent_change")]).get_json()
    assert _amount(_result(body, "baseline")["unit_cost"]) == 1400
    assert _amount(_result(body)["unit_cost"]) == 1540
    effective = body["effective_overrides"][0]
    assert _amount(effective["baseline_value"]) == 1000 and _amount(effective["final_value"]) == 1100
    assert effective["provenance_state"] == "HYPOTHETICAL_OVERRIDE"
    context = next(item for item in body["source_lineage"] if item["source"] == "materials")
    assert context["fingerprint"] == fingerprint
    assert context["actual_as_of"] == "2026-10-02T11:15:00+00:00"
    assert context["owner_assigned_baseline"] is None
    assert _snapshot(sensitivity.root) == before


def test_sources_are_read_once_and_shared_engine_calculates_baseline_once(sensitivity, monkeypatch):
    import utils.dashboard_sensitivity as module
    real_read, real_calculate = Path.read_bytes, module.calculate_cost
    reads, calculations = [], []
    def read(path):
        reads.append(path)
        return real_read(path)
    def calculate(inputs, overrides=None):
        calculations.append((inputs, overrides))
        return real_calculate(inputs, overrides)
    monkeypatch.setattr(Path, "read_bytes", read)
    monkeypatch.setattr(module, "calculate_cost", calculate)
    response = _scenario(sensitivity, [_change("pool:Payroll", "2000")])
    assert response.status_code == 200
    assert len(calculations) == 2 and calculations[0][1] is None and calculations[1][1] is not None
    assert calculations[0][0] is calculations[1][0]
    relevant = [path for path in reads if path == sensitivity.binding or sensitivity.data in path.parents]
    assert relevant and len(relevant) == len(set(relevant))


def test_unexpected_exception_is_safe_and_all_sources_including_profile_remain_unchanged(sensitivity, monkeypatch):
    def failed(*args, **kwargs):
        raise RuntimeError(f"internal secret source at {sensitivity.root}/private.json")
    monkeypatch.setattr(CostInputLoader, "load", failed)
    before = _snapshot(sensitivity.root)
    for response in (_parameters(sensitivity), _scenario(sensitivity)):
        assert response.status_code == 500
        assert _safe_json(response, sensitivity)["state"] == "CALCULATION_ERROR"
        assert _snapshot(sensitivity.root) == before


def test_service_uses_one_immutable_snapshot_when_sources_change_after_capture(sensitivity, monkeypatch):
    from utils.dashboard_sensitivity import DashboardSensitivityService
    _material_fixture(sensitivity)
    parameter = _parameter(sensitivity, "material:")
    original = CostInputLoader.load
    captured = []
    source = sensitivity.data / "Overall" / "material_costs.json"
    def capture_then_change(loader, *args, **kwargs):
        assert loader.read_only is True and kwargs["module"] == "dashboard"
        inputs = original(loader, *args, **kwargs)
        captured.append(inputs)
        if len(captured) == 1:
            document = json.loads(source.read_text())
            document["data"]["cost_per_unit_in_currency"][0] = 1000
            _write(source, document)
        return inputs
    monkeypatch.setattr(CostInputLoader, "load", capture_then_change)
    service = DashboardSensitivityService(FactoryService(sensitivity.store), data_root=sensitivity.data,
                                          period_bindings_path=sensitivity.binding)
    report = service.scenario(FACTORY, sensitivity.store.get_user_by_id("both-groups"),
                              category="category", subcategory="sub", product=SELECTION["product"], period_id="P",
                              overrides=[_change(parameter, "10", "percent_change")])
    assert len(captured) == 1
    assert report["baseline"]["unit_cost"] == Decimal(140)
    assert report["scenario"]["unit_cost"] == Decimal(154)
    assert all(line.price.unit_price == Decimal(100) for line in captured[0].bom_lines)
    fresh = _scenario(sensitivity).get_json()
    assert _amount(_result(fresh, "baseline")["unit_cost"]) == 1400


def test_failed_source_read_is_reused_if_file_appears_after_capture(sensitivity, monkeypatch):
    from utils.dashboard_sensitivity import DashboardSensitivityService
    source = sensitivity.data / "Overall" / "material_costs.json"
    saved = source.read_text()
    source.unlink()
    service = DashboardSensitivityService(FactoryService(sensitivity.store), data_root=sensitivity.data,
                                          period_bindings_path=sensitivity.binding)
    original = service.loader.snapshot_population
    def restore_after_capture(*args, **kwargs):
        population = original(*args, **kwargs)
        source.write_text(saved, encoding="utf-8")
        return population
    monkeypatch.setattr(service.loader, "snapshot_population", restore_after_capture)
    from utils.costing_engine import CostInputError
    with pytest.raises(CostInputError) as failure:
        service.scenario(FACTORY, sensitivity.store.get_user_by_id("both-groups"), category="category",
                         subcategory="sub", product=SELECTION["product"], period_id="P", overrides=[])
    assert failure.value.state.value == "MISSING_INPUT"
    assert _scenario(sensitivity).status_code == 200


def test_concurrent_scenarios_have_independent_overrides_and_do_not_mutate_inputs(sensitivity, monkeypatch):
    import utils.dashboard_sensitivity as module
    _material_fixture(sensitivity)
    parameter = _parameter(sensitivity, "material:")
    barrier = threading.Barrier(2)
    real = module.calculate_cost
    captures = []
    guard = threading.Lock()
    def calculate(inputs, overrides=None):
        immutable_before = copy.deepcopy(inputs)
        override_before = None if overrides is None else {
            "prices": dict(overrides.material_unit_prices), "fx": dict(overrides.fx_rates),
            "pools": dict(overrides.factory_pool_amounts), "share": overrides.category_share,
            "predictions": dict(overrides.product_predictions),
        }
        with guard:
            captures.append((inputs, immutable_before, overrides, override_before))
        if overrides is not None:
            barrier.wait(timeout=10)
        result = real(inputs, overrides)
        assert inputs == immutable_before
        return result
    monkeypatch.setattr(module, "calculate_cost", calculate)
    before = _snapshot(sensitivity.root)
    def execute(value):
        return _scenario(sensitivity, [_change(parameter, value)], user="both-groups")
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(execute, ["200", "300"]))
    assert all(response.status_code == 200 for response in responses)
    bodies = [response.get_json() for response in responses]
    assert [_amount(_result(body, "baseline")["unit_cost"]) for body in bodies] == [140, 140]
    assert [_amount(_result(body)["unit_cost"]) for body in bodies] == [280, 420]
    assert captures
    for inputs, old_inputs, overrides, old_overrides in captures:
        assert inputs == old_inputs
        if overrides is not None:
            assert {"prices": dict(overrides.material_unit_prices), "fx": dict(overrides.fx_rates),
                    "pools": dict(overrides.factory_pool_amounts), "share": overrides.category_share,
                    "predictions": dict(overrides.product_predictions)} == old_overrides
    assert _snapshot(sensitivity.root) == before
