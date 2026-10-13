"""PR-10 release proofs for the approved engine and every numerical surface.

The reusable PR-08 fixture prepares isolated operational/Profile/V2 inputs before
registering real blueprints. This module never imports the startup application.
"""

import copy
import json
from dataclasses import asdict, replace
from decimal import Decimal

import pytest

from test_dashboard_cost_analysis import (
    FACTORY, OPERATIONAL, analysis, _bom, _reference, _set_pools, _write,
)
from test_dashboard_sensitivity import (
    sensitivity, SELECTION, _change, _g2_fixture, _grant, _material_fixture,
    _parameter, _parameters, _scenario,
)
from utils.costing_engine import (
    FACTORY_POOL_IDS, CostInputLoader, CostOverrides, ProductIdentity,
    SourceProvenance, calculate_cost,
)
from utils.dashboard_visual_sensitivity import comparison
from utils.factory_service import FactoryService
from utils.profile_authorization import canonicalize_access_grants


VISUALS = "/api/dashboard/cost-analysis/visuals"
LAB = "/api/dashboard/sensitivity/visual-analysis"
ALL_SELECTION = dict(SELECTION, category="__ALL__", subcategory="__ALL__", product="__ALL__")
IDENTITY = ProductIdentity(FACTORY, "category", "sub", "A")


def decimal(value):
    assert isinstance(value, str), "API monetary and quantity values must be Decimal strings"
    return Decimal(value)


def lab(env, a=(), b=(), *, experiment=None, selection=None):
    return env.client.post(LAB, json={
        **(selection or SELECTION),
        "scenarios": [{"id": "A", "overrides": list(a)}, {"id": "B", "overrides": list(b)}],
        "experiment": experiment,
    })


def captured(env):
    loader = CostInputLoader(FactoryService(env.store), data_root=env.data,
                             period_bindings_path=env.binding, read_only=True)
    return loader.load(FACTORY, env.store.get_user_by_id("both-groups"), IDENTITY, "P", module="dashboard")


def semantic_inputs(inputs, timestamp):
    """Compare actual loaders while excluding display-only provenance roles/time."""
    neutral = SourceProvenance("capture", "same")
    return replace(inputs, loaded_at=timestamp, provenance=(),
                   bom_lines=tuple(replace(line, price=replace(line.price, provenance=neutral))
                                   for line in inputs.bom_lines),
                   factory_pools=tuple(replace(pool, provenance=neutral) for pool in inputs.factory_pools))


def cost_grant(env):
    env.store.update_user("both-groups", {"access_grants": canonicalize_access_grants([
        _grant("dashboard"), _grant("general_parameters"), _grant("factory_parameters"),
        _grant("cost_calculation"),
    ], [FACTORY])})


@pytest.mark.parametrize("vector,bom,unit,projected", [
    ("G1", "98000000", "98000100", "980001000"),
    ("duplicate", "140", "140", "1400"),
    ("G2", "0", "100", "1000"),
])
def test_all_five_http_surfaces_use_identical_captured_inputs_and_engine(
        sensitivity, monkeypatch, vector, bom, unit, projected):
    env = sensitivity
    if vector == "duplicate":
        _material_fixture(env)
    elif vector == "G2":
        _g2_fixture(env)
    cost_grant(env)
    frozen = captured(env)
    original = CostInputLoader.load
    seen = []

    def same_capture(loader, *args, **kwargs):
        actual = original(loader, *args, **kwargs)
        assert semantic_inputs(actual, frozen.loaded_at) == semantic_inputs(frozen, frozen.loaded_at)
        seen.append((kwargs.get("module"), actual))
        return frozen

    monkeypatch.setattr(CostInputLoader, "load", same_capture)
    pure = calculate_cost(frozen)
    cost = env.client.post("/cost/get_cost", json={
        "Factory": FACTORY, "Category": "category", "Subcategory": "sub", "Product_Name": "A", "Period": "P",
    })
    canonical = env.client.get("/api/cost_analysis", query_string=SELECTION)
    wrapper = env.client.get(VISUALS, query_string=SELECTION)
    scenario = _scenario(env)
    comparison_response = lab(env)
    assert [r.status_code for r in (cost, canonical, wrapper, scenario, comparison_response)] == [200] * 5
    assert len(seen) == 5 and seen[0][0] == "cost_calculation"
    assert all(module == "dashboard" for module, _ in seen[1:])
    expected_identity = asdict(IDENTITY)
    expected_period = {"id": "P", "start": "2026-10-01", "end": "2026-12-31"}
    cost_body, report, wrapped, single, compared = (r.json for r in (cost, canonical, wrapper, scenario, comparison_response))
    rows = [report["detail_rows"][0], wrapped["analysis"]["detail_rows"][0], single["baseline"],
            single["scenario"], compared["baseline"], *[s["result"] for s in compared["scenarios"]]]
    assert pure.bom_total == Decimal(bom) and pure.value == Decimal(unit)
    assert decimal(cost_body["value"]) == pure.value
    assert decimal(cost_body["bom_total"]) == pure.bom_total
    assert cost_body["identity"] == expected_identity and cost_body["period"] == expected_period
    for row in rows:
        assert decimal(row["unit_cost"]) == pure.value
        assert decimal(row["bom_total"]) == pure.bom_total
        assert decimal(row["projected_cost"]) == Decimal(projected)
    for body in (single, compared):
        assert body["identity"] == expected_identity and body["period"] == expected_period
    for body in (report, wrapped["analysis"]):
        assert body["detail_rows"][0]["identity"] == expected_identity and body["period"] == expected_period
    assert wrapped["visuals"]["products"][0]["identity"] == expected_identity
    assert decimal(wrapped["visuals"]["products"][0]["unit_cost"]) == pure.value
    if vector == "duplicate":
        assert len(cost_body["bom_components"]) == len(cost_body["BOM_Details"]) - 1 == 2
        assert len({row["row_id"] for row in cost_body["bom_components"]}) == 2


def test_duplicate_bom_140_154_168_agrees_between_single_ab_and_pure(sensitivity):
    env = sensitivity
    _material_fixture(env)
    material = _parameter(env, "material:")
    frozen = captured(env)
    unchanged = copy.deepcopy(frozen)
    responses = [_scenario(env, [_change(material, str(p), "percent_change")]) for p in (10, 20)]
    ab = lab(env, [_change(material, "10", "percent_change")], [_change(material, "20", "percent_change")]).json
    assert [decimal(ab["baseline"]["unit_cost"]), *[decimal(s["result"]["unit_cost"]) for s in ab["scenarios"]]] == [140, 154, 168]
    row_ids = [line.row_id for line in frozen.bom_lines]
    assert len(row_ids) == len(set(row_ids)) == 2
    assert [component.live_cost_in_rial for component in calculate_cost(frozen).bom_components] == [100, 40]
    for response, scenario, price in zip(responses, ab["scenarios"], (Decimal(110), Decimal(120))):
        assert response.status_code == 200
        overrides = CostOverrides(material_unit_prices=dict.fromkeys(row_ids, price))
        override_before = copy.deepcopy(overrides)
        pure = calculate_cost(frozen, overrides)
        assert decimal(response.json["scenario"]["unit_cost"]) == decimal(scenario["result"]["unit_cost"]) == pure.value
        assert [decimal(r["live_cost_in_rial"]) for r in scenario["result"]["breakdown"]["bom_components"]] == [c.live_cost_in_rial for c in pure.bom_components]
        assert overrides == override_before
    assert frozen == unchanged


@pytest.mark.parametrize("mixed_material", [False, True])
def test_duplicate_explicit_bom_row_ids_are_ambiguous_on_every_surface(sensitivity, mixed_material):
    env = sensitivity
    _material_fixture(env)
    document = json.loads((env.data / "Overall" / "material_costs.json").read_text())
    for column, value in {"material": "copper", "unit": "kg", "currency": "IRR - Iranian Rial", "cost_per_unit_in_currency": 200}.items():
        document["data"][column].append(value)
    _write(env.data / "Overall" / "material_costs.json", document)
    bom = _bom([1, 0.4], loss=0, recycling=0)
    bom["data"]["row_id"] = ["duplicate", "duplicate"]
    if mixed_material:
        bom["data"]["materials"] = ["lead", "copper"]
    _write(env.factory / "category" / "sub" / "A.json", bom)
    cost_grant(env)
    cost = env.client.post("/cost/get_cost", json={
        "Factory": FACTORY, "Category": "category", "Subcategory": "sub", "Product_Name": "A", "Period": "P",
    })
    responses = [cost, env.client.get("/api/cost_analysis", query_string=SELECTION),
                 env.client.get(VISUALS, query_string=SELECTION), _scenario(env), lab(env)]
    assert [r.status_code for r in responses] == [422] * 5, [(r.status_code, r.json.get("state")) for r in responses]
    for response in responses:
        body = response.json.get("analysis", response.json)
        assert body["state"] == "AMBIGUOUS_INPUT"
        issues = body.get("issues", body.get("errors", []))
        assert any(issue["code"] == "BOM_ROW_ID_NOT_UNIQUE" for issue in issues)


def test_pure_engine_rejects_duplicate_row_ids_before_override_mapping(sensitivity):
    _material_fixture(sensitivity)
    inputs = captured(sensitivity)
    invalid = replace(inputs, bom_lines=tuple(replace(line, row_id="duplicate") for line in inputs.bom_lines))
    before = copy.deepcopy(invalid)
    overrides = CostOverrides(material_unit_prices={"duplicate": Decimal(200)})
    result = calculate_cost(invalid, overrides)
    assert result.state.value == "AMBIGUOUS_INPUT" and result.value is result.bom_total is None
    assert result.errors[0].code == "BOM_ROW_ID_NOT_UNIQUE"
    assert invalid == before and overrides.material_unit_prices == {"duplicate": Decimal(200)}


def test_g2_prediction_share_ab_actual_projected_differences_and_pure(sensitivity):
    env = sensitivity
    _g2_fixture(env)
    prediction, share = _parameter(env, "prediction:"), _parameter(env, "category_share:")
    frozen = captured(env)
    body = lab(env, [_change(prediction, "30")], [_change(share, "25")]).json
    single_a = _scenario(env, [_change(prediction, "30")]).json
    single_b = _scenario(env, [_change(share, "25")]).json
    results = [body["baseline"], *[scenario["result"] for scenario in body["scenarios"]]]
    assert [decimal(row["unit_cost"]) for row in results] == [100, 50, 200]
    assert [decimal(row["projected_cost"]) for row in results] == [1000, 1500, 2000]
    for result, single, overrides in zip(results[1:], (single_a, single_b), (
            CostOverrides(product_predictions={IDENTITY: Decimal(30)}), CostOverrides(category_share=Decimal(25)))):
        pure = calculate_cost(frozen, overrides)
        assert decimal(result["unit_cost"]) == decimal(single["scenario"]["unit_cost"]) == pure.value
        quantity = overrides.product_predictions.get(IDENTITY, frozen.product_prediction)
        assert decimal(result["projected_cost"]) == pure.value * quantity
    difference = body["comparisons"]["B_minus_A"]
    assert decimal(difference["unit_cost"]["amount"]) == 150
    assert decimal(difference["projected_cost"]["amount"]) == 500
    assert difference["unit_cost"]["direction"] == "B_minus_A"
    assert decimal(difference["unit_cost"]["percentage_denominator"]) == 50
    assert decimal(difference["projected_cost"]["percentage_denominator"]) == 1500
    for compared in body["comparisons"].values():
        waterfall = compared["waterfall"]
        assert {row["id"] for row in waterfall["components"]} == {"BOM", *FACTORY_POOL_IDS}
        assert decimal(waterfall["target"]) - decimal(waterfall["reference"]) == sum((decimal(r["value"]) for r in waterfall["components"]), Decimal(0)) + decimal(waterfall["reconciliation"])
        assert waterfall["meaning"] == "output_component_differences_not_independent_input_effects"


@pytest.mark.parametrize("invalid_b", [False, True])
def test_filter_and_bom_exclusion_keep_full_category_allocation_population(sensitivity, invalid_b):
    env = sensitivity
    _g2_fixture(env)
    _write(env.factory / "category" / "sub" / "B.json", _bom([0]))
    if invalid_b:
        _write(env.factory / "category" / "sub" / "B.json", _bom([1], loss=101))
    full = env.client.get(VISUALS, query_string=ALL_SELECTION).json
    filtered = env.client.get(VISUALS, query_string=SELECTION).json
    for wrapper in (full, filtered):
        report = wrapper["analysis"]
        row = next(r for r in report["detail_rows"] if r["identity"]["product"] == "A")
        assert decimal(row["unit_cost"]) == 100
        pool = next(p for p in report["breakdowns"]["factory_pools"] if p["id"] == "Payroll")
        assert decimal(pool["raw_total"]) == 1000
        assert decimal(pool["modeled_category_total"]) == 2000
        assert decimal(pool["categories"][0]["prediction_denominator"]) == 20
        assert pool["raw_scope"] == "whole_factory"
        assert wrapper["visuals"]["coverage"] == report["coverage"]
    assert decimal(filtered["analysis"]["breakdowns"]["factory_pools"][1]["modeled_selected_total"]) == 1000
    if invalid_b:
        assert full["analysis"]["state"] == "PARTIAL"
        assert full["analysis"]["coverage"] == {"configured": 2, "calculated": 1, "excluded": 1, "percentage": "50"}
        assert full["analysis"]["kpis"]["projected_total"] is None
        assert decimal(full["analysis"]["kpis"]["partial_total"]) == 1000
        assert full["visuals"]["excluded"][0]["unit_cost"] is None
        assert len(full["visuals"]["products"]) == 1
    else:
        assert full["analysis"]["coverage"]["calculated"] == 2
        assert decimal(full["analysis"]["kpis"]["projected_total"]) == 2000


def test_weighted_average_counts_units_ties_and_shares(sensitivity):
    env = sensitivity
    _material_fixture(env, usages=(1,))
    _write(env.factory / "category" / "sub" / "B.json", _bom([0.4], loss=0, recycling=0))
    _write(env.factory / "configuration" / "production_prediction.json", {"data": {
        "Product Name": ["A", "B"], "Predicted Production": [10, 30],
    }})
    payroll_path = env.factory / "configuration" / "cost_pools" / "Payroll.json"
    document = json.loads(payroll_path.read_text())
    document["data"]["cost"] = [1100]
    _write(payroll_path, document)
    report = env.client.get(VISUALS, query_string=ALL_SELECTION).json["analysis"]
    # BOM 100*10+40*30=2,200 ties the inverse 50% allocation of raw 1,100.
    assert decimal(report["kpis"]["projected_total"]) == 4400
    average = report["kpis"]["weighted_average"]
    assert decimal(average["numerator"]) == 4400 and decimal(average["denominator"]) == 40
    assert decimal(average["value"]) == 110
    assert average["unit"] == "IRR/product" and average["population"] == "selected_calculated_configurations"
    assert report["kpis"]["matched_configuration_count"] == report["coverage"]["configured"] == 2
    top = report["kpis"]["top_cost_driver"]
    assert top["id"] == "BOM" and top["tie"] and top["tied_ids"] == ["BOM", "Payroll"]
    assert decimal(top["value"]) == 2200 and decimal(top["share"]) == 50
    assert top["unit"] == "IRR/period" and top["coverage"] == report["coverage"]
    assert sum((decimal(d["share"]) for d in report["breakdowns"]["drivers"]), Decimal(0)) == 100
    assert all(row["unit"] == "IRR/product" and row["projected_cost_unit"] == "IRR/period"
               and row["prediction_unit"] == "product/period" for row in report["detail_rows"])


def test_pareto_hierarchy_and_same_name_rows_reconcile_to_projected_population(sensitivity):
    env = sensitivity
    _material_fixture(env)
    _write(env.data / "Overall" / "material_costs.json", {"data": {
        "material": ["lead", "copper"], "unit": ["kg", "kg"],
        "currency": ["IRR - Iranian Rial"] * 2, "cost_per_unit_in_currency": [100, 25],
    }})
    bom = _bom([1, 0.4, 2], loss=0, recycling=0)
    bom["data"]["materials"] = ["lead", "lead", "copper"]
    _write(env.factory / "category" / "sub" / "A.json", bom)
    _write(env.factory / "category" / "sub" / "B.json", _bom([0.5], loss=0, recycling=0))
    _write(env.factory / "category" / "other" / "A.json", _bom([0.2], material="copper", loss=0, recycling=0))
    _write(env.factory / "configuration" / "production_prediction.json", {"data": {
        "Product Name": ["A", "B"], "Predicted Production": [10, 20],
    }})
    _write(env.data / "Factories" / "__metadata.json", {"product_hierarchy": {OPERATIONAL: {"category": ["sub", "other"]}}})
    wrapper = env.client.get(VISUALS, query_string=ALL_SELECTION).json
    report, visual = wrapper["analysis"], wrapper["visuals"]
    assert report["coverage"]["configured"] == report["coverage"]["calculated"] == 3
    identities = [product["identity"] for product in visual["products"]]
    assert len({tuple(identity.values()) for identity in identities}) == 3
    assert sum(identity["product"] == "A" for identity in identities) == 2
    assert decimal(report["kpis"]["projected_total"]) == decimal(visual["hierarchy"][0]["value"]) == 2950
    assert visual["hierarchy_unit"] == "IRR/period"
    assert [decimal(m["value"]) for m in visual["materials"]] == [2400, 550]
    assert visual["materials"][0]["material"] == "lead"
    assert len(visual["materials"][0]["rows"]) == 3
    assert decimal(visual["pareto_denominator"]) == 2950 and decimal(visual["material_reconciliation"]) == 0
    assert visual["pareto_denominator_scope"] == "selected_calculated_projected_BOM_total"
    assert decimal(visual["materials"][-1]["cumulative_share"]) == 100
    for material in visual["materials"]:
        assert decimal(material["value"]) == sum((decimal(r["projected_contribution"]) for r in material["rows"]), Decimal(0))
        assert decimal(material["share"]) == decimal(material["value"]) / Decimal(2950) * 100
    for category in visual["hierarchy"]:
        assert decimal(category["value"]) == sum((decimal(s["value"]) for s in category["children"]), Decimal(0))
        for subcategory in category["children"]:
            assert decimal(subcategory["value"]) == sum((decimal(p["value"]) for p in subcategory["children"]), Decimal(0))
    registry = _parameters(env).json
    assert not any(p["parameter_id"].startswith("prediction:") for p in registry["parameters"])
    assert any(p["reason"] == "AMBIGUOUS_PREDICTION_MAPPING" for p in registry["unsupported_parameters"])


@pytest.mark.parametrize("damage,state", [("missing", "AMBIGUOUS_INPUT"), ("negative", "INVALID_INPUT"), ("duplicate", "AMBIGUOUS_INPUT")])
def test_invalid_and_ambiguous_prediction_are_unavailable_across_surfaces(sensitivity, damage, state):
    env = sensitivity
    _g2_fixture(env)
    names, quantities = {"missing": (["A"], [10]), "negative": (["A", "B"], [10, -1]),
                         "duplicate": (["A", "A", "B"], [10, 20, 10])}[damage]
    _write(env.factory / "configuration" / "production_prediction.json", {"data": {
        "Product Name": names, "Predicted Production": quantities,
    }})
    responses = [env.client.get("/api/cost_analysis", query_string=SELECTION),
                 env.client.get(VISUALS, query_string=SELECTION), _scenario(env), lab(env)]
    assert all(r.status_code == 422 for r in responses)
    canonical, wrapper, single, ab = (r.json for r in responses)
    for report in (canonical, wrapper["analysis"]):
        assert report["state"] == state
        assert report["kpis"]["projected_total"] is report["kpis"]["partial_total"] is None
        assert report["detail_rows"][0]["unit_cost"] is None
    assert wrapper["visuals"]["products"] == []
    for response in (single, ab):
        assert response["state"] == state
        assert response["baseline"] is None or response["baseline"]["unit_cost"] is None


def test_zero_reference_math_zero_combination_and_valid_zero_are_distinct(sensitivity):
    env = sensitivity
    _material_fixture(env, price=0, currency="USD", usages=(1,))
    parameters = _parameters(env).json["parameters"]
    price = next(p["parameter_id"] for p in parameters if p["parameter_id"].startswith("material:"))
    fx = next(p for p in parameters if p["parameter_id"].startswith("fx:"))
    assert fx["effect_state"] == "MATHEMATICAL_ZERO" and fx["dependencies"]
    body = lab(env, b=[_change(price, "10"), _change(fx["parameter_id"], "6")], experiment={
        "type": "two_factor", "axes": [
            {"parameter_id": price, "mode": "absolute", "values": ["0", "10"]},
            {"parameter_id": fx["parameter_id"], "mode": "absolute", "values": ["5", "6"]},
        ],
    }).json
    assert [decimal(p["unit_cost"]) for p in body["experiment"]["points"]] == [0, 0, 50, 60]
    delta = body["comparisons"]["B_minus_baseline"]
    for name in ("unit_cost", "projected_cost"):
        assert decimal(delta[name]["percentage_denominator"]) == 0
        assert delta[name]["percentage"] is None and delta[name]["percentage_state"] == "NOT_APPLICABLE"
    wrapper = env.client.get(VISUALS, query_string=SELECTION).json
    assert wrapper["analysis"]["state"] == "OK"
    assert decimal(wrapper["analysis"]["kpis"]["projected_total"]) == 0
    assert all(r["share"] is None for r in wrapper["analysis"]["breakdowns"]["drivers"])
    assert not wrapper["visuals"]["treemap_available"]
    assert wrapper["visuals"]["pareto_mode"] == "signed_bar"
    assert wrapper["visuals"]["materials"][0]["share"] is None
    assert wrapper["analysis"]["kpis"]["top_cost_driver"]["tied_ids"] == sorted(["BOM", *FACTORY_POOL_IDS])


def test_zero_selected_prediction_has_valid_unit_cost_and_unavailable_weighted_average(sensitivity):
    env = sensitivity
    _g2_fixture(env, predictions=(0, 10))
    wrapper = env.client.get(VISUALS, query_string=SELECTION).json
    report = wrapper["analysis"]
    assert report["state"] == "OK" and report["coverage"]["calculated"] == 1
    assert decimal(report["detail_rows"][0]["unit_cost"]) == 200
    assert decimal(report["detail_rows"][0]["prediction"]) == decimal(report["kpis"]["projected_total"]) == 0
    average = report["kpis"]["weighted_average"]
    assert average["state"] == "NOT_APPLICABLE" and average["value"] is None
    assert decimal(average["numerator"]) == decimal(average["denominator"]) == 0
    assert wrapper["visuals"]["products"][0]["unit_cost"] == report["detail_rows"][0]["unit_cost"]
    single, ab = _scenario(env).json, lab(env).json
    assert decimal(single["baseline"]["unit_cost"]) == decimal(ab["baseline"]["unit_cost"]) == 200
    assert decimal(single["baseline"]["projected_cost"]) == decimal(ab["baseline"]["projected_cost"]) == 0
    assert ab["comparisons"]["A_minus_baseline"]["projected_cost"]["percentage"] is None


def test_source_alias_fans_out_coherently_and_conflicting_overrides_reject(sensitivity):
    env = sensitivity
    _g2_fixture(env)
    pool = env.factory / "configuration" / "cost_pools" / "Payroll.json"
    alias = pool.with_name("Overhead.json")
    alias.unlink()
    alias.symlink_to(pool.name)
    frozen = captured(env)
    inputs_before = copy.deepcopy(frozen)
    single = _scenario(env, [_change("pool:Payroll", "2000")]).json
    body = lab(env, a=[_change("pool:Payroll", "2000")]).json
    pure = calculate_cost(frozen, CostOverrides(factory_pool_amounts={"Payroll": Decimal(2000), "Overhead": Decimal(2000)}))
    assert decimal(single["baseline"]["unit_cost"]) == decimal(body["baseline"]["unit_cost"]) == 200
    assert decimal(single["scenario"]["unit_cost"]) == decimal(body["scenarios"][0]["result"]["unit_cost"]) == pure.value == 400
    baseline_pools = {component.pool_id: component for component in frozen.factory_pools}
    assert baseline_pools["Payroll"].provenance.fingerprint == baseline_pools["Overhead"].provenance.fingerprint
    assert baseline_pools["Payroll"].provenance.source == "pool:Payroll"
    assert baseline_pools["Overhead"].provenance.source == "pool:Overhead"
    conflicting = [_change("pool:Payroll", "2000"), _change("pool:Overhead", "3000")]
    for response in (_scenario(env, conflicting), lab(env, a=conflicting)):
        assert response.status_code == 400
        assert any(issue["code"] == "CONFLICTING_SOURCE_OVERRIDES" for issue in response.json["issues"])
    assert frozen == inputs_before


def test_each_post_captures_once_ignores_stale_get_and_does_not_mutate_pure_inputs(sensitivity, monkeypatch):
    import utils.dashboard_sensitivity as single_module
    import utils.dashboard_visual_sensitivity as ab_module
    env = sensitivity
    _material_fixture(env)
    listing = _parameters(env).json
    assert decimal(listing["baseline"]["unit_cost"]) == 140
    price = next(p["parameter_id"] for p in listing["parameters"] if p["parameter_id"].startswith("material:"))
    _material_fixture(env, price=200)
    original_load = CostInputLoader.load
    loads, calculations = [], []

    def load(loader, *args, **kwargs):
        result = original_load(loader, *args, **kwargs)
        loads.append(result)
        return result

    def calculate(inputs, overrides=None):
        def values(change):
            return None if change is None else (
                dict(change.material_unit_prices), dict(change.fx_rates),
                dict(change.factory_pool_amounts), change.category_share,
                dict(change.product_predictions),
            )
        before_inputs, before_overrides = copy.deepcopy(inputs), values(overrides)
        result = calculate_cost(inputs, overrides)
        assert inputs == before_inputs and values(overrides) == before_overrides
        calculations.append((inputs, overrides))
        return result

    monkeypatch.setattr(CostInputLoader, "load", load)
    monkeypatch.setattr(single_module, "calculate_cost", calculate)
    monkeypatch.setattr(ab_module, "calculate_cost", calculate)
    single = _scenario(env, [_change(price, "10", "percent_change")]).json
    assert len(loads) == 1 and len(calculations) == 2
    assert all(inputs is loads[0] for inputs, _ in calculations)
    assert sum(overrides is None for _, overrides in calculations) == 1
    assert decimal(single["baseline"]["unit_cost"]) == 280 and decimal(single["scenario"]["unit_cost"]) == 308
    loads.clear(); calculations.clear()
    ab = lab(env, [_change(price, "10", "percent_change")], [_change(price, "20", "percent_change")], experiment={
        "type": "one_factor", "axes": [{"parameter_id": price, "mode": "absolute", "values": ["0", "200", "300"]}],
    }).json
    assert len(loads) == 1 and len(calculations) == 6
    assert all(inputs is loads[0] for inputs, _ in calculations)
    assert sum(overrides is None for _, overrides in calculations) == 1
    assert [decimal(ab["baseline"]["unit_cost"]), *[decimal(s["result"]["unit_cost"]) for s in ab["scenarios"]]] == [280, 308, 336]
    assert [decimal(point["unit_cost"]) for point in ab["experiment"]["points"]] == [0, 280, 420]


def test_technical_decimal_residue_is_explicit_and_component_leaves_are_unchanged():
    def result(value):
        return {"unit_cost": Decimal(value), "projected_cost": Decimal(value), "bom_total": Decimal(1),
                "breakdown": {"driver_components": [{"pool_id": pool, "per_unit_contribution": Decimal(0)}
                                                     for pool in FACTORY_POOL_IDS]}}
    reference, target = result("1"), result("1.000000000000000000000000001")
    before = copy.deepcopy((reference, target))
    report = comparison(reference, target, "B_minus_A")
    assert all(row["value"] == 0 for row in report["waterfall"]["components"])
    assert report["waterfall"]["reconciliation"] == Decimal("0.000000000000000000000000001")
    assert report["waterfall"]["technical_reconciliation"]["value"] == report["waterfall"]["reconciliation"]
    assert (reference, target) == before


def test_visual_wrapper_preserves_finite_decimal_aggregate_residue(sensitivity):
    env = sensitivity
    names, quantities, usages = ["A", "B", "C", "D", "E"], [62, 48, 1, 52, 31], [120, 571, 219, 981, 255]
    _material_fixture(env, price=1)
    for name, usage in zip(names, usages):
        _write(env.factory / "category" / "sub" / f"{name}.json", _bom([usage], loss=0, recycling=0))
    _write(env.factory / "configuration" / "production_prediction.json", {"data": {
        "Product Name": names, "Predicted Production": quantities,
    }})
    _write(env.factory / "configuration" / "category_weights.json", {"data": {
        "category": ["category"], "selling_share_of_category": [33],
    }})
    pool_path = env.factory / "configuration" / "cost_pools" / "Payroll.json"
    document = json.loads(pool_path.read_text())
    document["data"]["cost"] = [1000]
    _write(pool_path, document)
    wrapper = env.client.get(VISUALS, query_string=ALL_SELECTION).json
    report, visual = wrapper["analysis"], wrapper["visuals"]
    reconciliation = report["arithmetic_reconciliation"]
    total = decimal(report["kpis"]["projected_total"])
    row_sum = sum((decimal(r["projected_cost"]) for r in visual["products"]), Decimal(0))
    driver_sum = sum((decimal(r["value"]) for r in report["breakdowns"]["drivers"]), Decimal(0))
    assert total == row_sum == decimal(reconciliation["projected_rows_total"])
    assert driver_sum == decimal(reconciliation["driver_components_total"])
    assert total - driver_sum == decimal(reconciliation["difference"]) == Decimal("-0.00000000000000000000001")
    for plotted, row in zip(visual["products"], report["breakdowns"]["products"]):
        assert plotted["unit_cost"] == row["unit_cost"] and plotted["projected_cost"] == row["projected_cost"]
        assert decimal(plotted["reconciliation"]) == decimal(row["projected_cost"]) - sum((decimal(v) for v in plotted["projected_components"].values()), Decimal(0))
