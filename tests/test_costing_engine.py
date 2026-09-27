"""Business-approved PR-05 costing golden tests."""

from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json

import pytest

from utils.costing_engine import (
    FACTORY_POOL_IDS,
    BomLineItem,
    CostInputError,
    CostInputLoader,
    CostInputs,
    CostOverrides,
    CostState,
    FactoryPool,
    MaterialPrice,
    PlanningPeriod,
    ProductIdentity,
    ProductPrediction,
    SourceProvenance,
    calculate_live_bom_line,
    calculate_cost,
    validate_live_bom_payload,
)


IDENTITY_A = ProductIdentity("factory-1", "category", "sub", "A")
IDENTITY_B = ProductIdentity("factory-1", "category", "sub", "B")
PERIOD = PlanningPeriod("P", date(2026, 10, 1), date(2026, 12, 31))
PROVENANCE = SourceProvenance("fixture", "abc", owner_assigned_baseline=date(2026, 9, 27))


def _inputs(*, lines=(), pools=(), share="50", predictions=((IDENTITY_A, "10"), (IDENTITY_B, "10"))):
    product_predictions = tuple(ProductPrediction(identity, Decimal(value)) for identity, value in predictions)
    return CostInputs(
        IDENTITY_A, PERIOD, tuple(lines), tuple(pools), Decimal(share),
        product_predictions[0].quantity, product_predictions, (PROVENANCE,),
        datetime(2026, 9, 27, tzinfo=timezone.utc),
    )


def _line(row_id, material, usage, price, *, loss="0", recyclable="0", currency="IRR", fx="1", historical=None):
    return BomLineItem(
        row_id, material, usage, loss, recyclable,
        MaterialPrice(material, "kg", currency, Decimal(price), Decimal(fx), PROVENANCE),
        None if historical is None else Decimal(historical),
    )


def test_g1_live_bom_formula_ignores_historical_stored_amount():
    inputs = _inputs(lines=[_line("row-1", "lead", "100", "2", loss="10", recyclable="20",
                                  currency="USD", fx="500000", historical="777777")])

    result = calculate_cost(inputs)

    assert result.state is CostState.OK
    assert result.bom_components[0].gross_cost_in_rial == Decimal("100000000")
    assert result.bom_components[0].adjustment_factor == Decimal("0.98")
    assert result.bom_total == Decimal("98000000")
    assert result.value == Decimal("98000000")
    assert result.to_dict()["Final_Production_Cost"] == 98000000
    assert result.to_dict()["BOM_Details"]["row-1:lead"] == 98000000


@pytest.mark.parametrize(
    ("loss", "recyclable", "factor", "expected"),
    [
        ("10", "80", "0.92", "92000"),
        ("10", "0", "1", "100000"),
        ("0", "80", "1", "100000"),
        ("0", "100", "1", "100000"),
        ("100", "100", "0", "0"),
    ],
)
def test_g1_independent_percentages_and_boundaries(loss, recyclable, factor, expected):
    gross, efficiency, live = calculate_live_bom_line(100, 1000, 1, loss, recyclable)
    assert gross == Decimal("100000")
    assert efficiency == Decimal(factor)
    assert live == Decimal(expected)


def test_g2_pool_is_allocated_once_over_full_category_population():
    pool = FactoryPool("Payroll", Decimal("1000"), PROVENANCE)

    a = calculate_cost(_inputs(pools=[pool]))
    b_inputs = _inputs(pools=[pool])
    b_inputs = CostInputs(IDENTITY_B, b_inputs.period, b_inputs.bom_lines, b_inputs.factory_pools,
                          b_inputs.category_share, Decimal("10"), b_inputs.category_predictions,
                          b_inputs.provenance, b_inputs.loaded_at)
    b = calculate_cost(b_inputs)

    component = a.driver_components[0]
    assert component.adjusted_category_pool == Decimal("2000")
    assert component.category_prediction_total == Decimal("20")
    assert component.per_unit_contribution == Decimal("100")
    assert component.product_period_contribution == Decimal("1000")
    assert component.modeled_minus_raw == Decimal("1000")
    assert a.value == b.value == Decimal("100")
    assert component.product_period_contribution + b.driver_components[0].product_period_contribution == Decimal("2000")


def test_g2_unit_cost_is_invariant_when_display_selection_is_narrowed():
    pool = FactoryPool("Payroll", Decimal("1000"), PROVENANCE)
    baseline = calculate_cost(_inputs(pools=[pool]))
    # Display selection is deliberately absent from CostInputs; the complete
    # category population remains the denominator.
    selected_product_only = calculate_cost(_inputs(pools=[pool]))
    assert selected_product_only.value == baseline.value == Decimal("100")


def test_g4_duplicate_material_rows_keep_independent_identity_and_sum():
    result = calculate_cost(_inputs(lines=[
        _line("row-1", "lead", "1", "100"),
        _line("row-2", "lead", "1", "40"),
    ]))

    assert [item.row_id for item in result.bom_components] == ["row-1", "row-2"]
    assert [item.live_cost_in_rial for item in result.bom_components] == [Decimal("100"), Decimal("40")]
    assert result.bom_total == result.value == Decimal("140")


@pytest.mark.parametrize("loss,recyclable", [("-1", "0"), ("101", "0"), ("0", "101"), ("bad", "0")])
def test_invalid_percentages_are_rejected_without_clamping(loss, recyclable):
    result = calculate_cost(_inputs(lines=[_line("row-1", "lead", "1", "1", loss=loss, recyclable=recyclable)]))
    assert result.state is CostState.INVALID_INPUT
    assert result.value is None


@pytest.mark.parametrize(
    "inputs,state",
    [
        (_inputs(share="0"), CostState.INVALID_INPUT),
        (_inputs(share="-1"), CostState.INVALID_INPUT),
        (_inputs(predictions=((IDENTITY_A, "0"), (IDENTITY_B, "0"))), CostState.INVALID_INPUT),
    ],
)
def test_invalid_division_inputs_have_typed_states(inputs, state):
    assert calculate_cost(inputs).state is state


def test_complete_genuine_zero_is_ok_not_missing():
    result = calculate_cost(_inputs(lines=[_line("row-1", "lead", "0", "0")], pools=[FactoryPool("Payroll", Decimal(0), PROVENANCE)]))
    assert result.state is CostState.OK
    assert result.value == Decimal(0)


def test_in_memory_overrides_change_result_without_mutating_inputs():
    inputs = _inputs(lines=[_line("row-1", "lead", "2", "10")])
    result = calculate_cost(inputs, CostOverrides(material_unit_prices={"row-1": Decimal("20")}))
    assert result.value == Decimal("40")
    assert inputs.bom_lines[0].price.unit_price == Decimal("10")


def test_fx_share_and_prediction_changes_reach_the_result():
    line = _line("row-1", "lead", "1", "2", currency="USD", fx="5")
    pool = FactoryPool("Payroll", Decimal("1000"), PROVENANCE)
    inputs = _inputs(lines=[line], pools=[pool])
    baseline = calculate_cost(inputs)
    changed = calculate_cost(inputs, CostOverrides(
        fx_rates={"USD": Decimal("10")}, category_share=Decimal("25"),
        product_predictions={IDENTITY_A: Decimal("30"), IDENTITY_B: Decimal("10")},
    ))
    assert baseline.bom_total == Decimal("10")
    assert changed.bom_total == Decimal("20")
    assert baseline.driver_total == Decimal("100")
    assert changed.driver_total == Decimal("100")  # 4000 / (30 + 10)
    assert changed.driver_components[0].product_period_contribution == Decimal("3000")


class _FactoryService:
    def require_access(self, factory_id, user, module):
        assert factory_id == "factory-1"
        return {"id": factory_id}

    def operational_key(self, factory):
        return "operational"


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _fixture_tree(tmp_path):
    data = tmp_path / "Data"
    factory = data / "Factories" / "operational"
    _write(data / "Overall" / "material_costs.json", {"data": {
        "material": ["lead", "USD"], "unit": ["kg", "currency"],
        "currency": ["USD", "IRR - Iranian Rial"], "cost_per_unit_in_currency": [2, 500000],
    }})
    for product, usage in (("A", 100), ("B", 40)):
        _write(factory / "category" / "sub" / f"{product}.json", {"data": {
            "materials": ["lead"], "usage": [usage], "lost_percentage": [10],
            "recycability_percentage": [20], "cost_of_material_in_rial": [777777],
        }})
    _write(factory / "category_weights.json", {"data": {"category": ["category"], "selling_share_of_category": [50]}})
    _write(factory / "ProductionPrediction.json", {"data": {"Product Name": ["A", "B"], "Predicted Production": [10, 10]}})
    for pool_id in FACTORY_POOL_IDS:
        _write(factory / f"Factory_Data_{pool_id}.json", {"data": {"cost": [1000 if pool_id == "Payroll" else 0]}})
    sources = ["materials", "bom", "weights", "predictions", *(f"pool:{item}" for item in FACTORY_POOL_IDS)]
    binding = tmp_path / "bindings.json"
    _write(binding, {"bindings": [{"factory_id": "factory-1", "period_id": "P", "active": True, "start": "2026-10-01", "end": "2026-12-31", "sources": sources}]})
    return data, binding


def _hashes(root):
    return {path.relative_to(root): hashlib.sha256(path.read_bytes()).hexdigest() for path in root.rglob("*") if path.is_file()}


def test_loader_g3_binding_provenance_current_price_and_no_writes(tmp_path):
    data, binding = _fixture_tree(tmp_path)
    before = _hashes(tmp_path)
    loader = CostInputLoader(_FactoryService(), data_root=data, period_bindings_path=binding)

    inputs = loader.load("factory-1", {}, IDENTITY_A, "P")
    result = calculate_cost(inputs)

    assert result.state is CostState.OK
    assert result.bom_total == Decimal("98000000")
    assert result.driver_components[1].per_unit_contribution == Decimal("100")
    assert all(item.actual_as_of is None for item in result.source_metadata)
    assert all(item.owner_assigned_baseline == date(2026, 9, 27) for item in result.source_metadata)
    assert _hashes(tmp_path) == before


def test_loader_does_not_reuse_binding_for_another_period(tmp_path):
    data, binding = _fixture_tree(tmp_path)
    loader = CostInputLoader(_FactoryService(), data_root=data, period_bindings_path=binding)
    with pytest.raises(CostInputError) as caught:
        loader.load("factory-1", {}, IDENTITY_A, "Q")
    assert caught.value.state is CostState.MISSING_INPUT
    assert caught.value.detail.code == "PERIOD_NOT_BOUND"


def test_loader_uses_only_the_owner_marked_active_period_when_legacy_caller_omits_period(tmp_path):
    data, binding = _fixture_tree(tmp_path)
    inputs = CostInputLoader(_FactoryService(), data_root=data, period_bindings_path=binding).load(
        "factory-1", {}, IDENTITY_A, ""
    )
    assert inputs.period.period_id == "P"


def test_loader_reports_parse_failure_instead_of_zero(tmp_path):
    data, binding = _fixture_tree(tmp_path)
    (data / "Factories" / "operational" / "Factory_Data_Payroll.json").write_text("{bad", encoding="utf-8")
    with pytest.raises(CostInputError) as caught:
        CostInputLoader(_FactoryService(), data_root=data, period_bindings_path=binding).load("factory-1", {}, IDENTITY_A, "P")
    assert caught.value.state is CostState.INVALID_INPUT
    assert caught.value.detail.code == "SOURCE_PARSE_ERROR"


def test_loader_preserves_repeated_material_rows_with_stable_local_ids(tmp_path):
    data, binding = _fixture_tree(tmp_path)
    _write(data / "Factories" / "operational" / "category" / "sub" / "A.json", {"data": {
        "materials": ["lead", "lead"], "usage": [1, 2], "lost_percentage": [0, 0],
        "recycability_percentage": [0, 0], "cost_of_material_in_rial": [999, 999],
    }})
    inputs = CostInputLoader(_FactoryService(), data_root=data, period_bindings_path=binding).load(
        "factory-1", {}, IDENTITY_A, "P"
    )
    result = calculate_cost(inputs)
    assert [item.row_id for item in result.bom_components] == ["row-1", "row-2"]
    assert result.bom_total == Decimal("3000000")


def test_bom_save_validation_round_trips_live_values_and_duplicate_rows():
    payload = {"_order": ["materials", "usage", "lost_percentage", "recycability_percentage"], "data": {
        "materials": ["lead", "lead"], "usage": [100, 40],
        "lost_percentage": [10, 0], "recycability_percentage": [80, 100],
        "cost_of_material_in_rial": [0, 0],
    }}
    materials = {"data": {
        "material": ["lead"], "unit": ["kg"], "currency": ["IRR - Iranian Rial"],
        "cost_per_unit_in_currency": [1],
    }}
    saved = validate_live_bom_payload(payload, materials)
    assert saved["data"]["recycability_percentage"] == [80, 100]
    assert saved["data"]["cost_of_material_in_rial"] == [92, 40]
    assert sum(saved["data"]["cost_of_material_in_rial"]) == 132


@pytest.mark.parametrize("field,value", [
    ("usage", ""), ("usage", -1), ("lost_percentage", -1),
    ("lost_percentage", 101), ("recycability_percentage", "bad"),
    ("recycability_percentage", 101),
])
def test_bom_save_validation_rejects_invalid_required_values(field, value):
    data = {"materials": ["lead"], "usage": [1], "lost_percentage": [0], "recycability_percentage": [0]}
    data[field][0] = value
    materials = {"data": {"material": ["lead"], "unit": ["kg"],
                           "currency": ["IRR - Iranian Rial"], "cost_per_unit_in_currency": [1]}}
    with pytest.raises(CostInputError):
        validate_live_bom_payload({"_order": list(data), "data": data}, materials)


def test_bom_save_validation_rejects_missing_price_and_fx_instead_of_saving_zero():
    payload = {"_order": [], "data": {"materials": ["lead"], "usage": [1],
                                      "lost_percentage": [0], "recycability_percentage": [0]}}
    missing_price = {"data": {"material": [], "unit": [], "currency": [], "cost_per_unit_in_currency": []}}
    with pytest.raises(CostInputError) as caught:
        validate_live_bom_payload(payload, missing_price)
    assert caught.value.state is CostState.MISSING_INPUT

    missing_fx = {"data": {"material": ["lead"], "unit": ["kg"],
                           "currency": ["USD"], "cost_per_unit_in_currency": [2]}}
    with pytest.raises(CostInputError) as caught:
        validate_live_bom_payload(payload, missing_fx)
    assert caught.value.state is CostState.AMBIGUOUS_INPUT
