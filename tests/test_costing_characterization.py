"""Characterization tests for the current, not-yet-approved costing behavior.

These tests deliberately freeze observed implementation behavior.  Their
assertions are not an endorsement of the underlying business formulas.
"""

import hashlib
import importlib.util
import json
import sys
import types

import pytest

# The production module has a currently unused pandas import. Keep these
# focused tests runnable in the repository's dependency-light test environment
# without changing that production behavior.
if importlib.util.find_spec("pandas") is None:
    sys.modules["pandas"] = types.ModuleType("pandas")

from utils import cost_determiners, load_data


FACTORY = "fixture-factory"
CATEGORY = "fixture-category"
SUBCATEGORY = "fixture-subcategory"
PRODUCT = "fixture-product"


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def costing_fixture(tmp_path, monkeypatch):
    """Build a minimal, test-owned copy of the schemas read by the engine."""
    monkeypatch.setattr(cost_determiners, "parent_path", tmp_path)
    monkeypatch.setattr(load_data, "parent_path", tmp_path)

    factory = tmp_path / "Factories" / FACTORY
    bom_path = factory / CATEGORY / SUBCATEGORY / f"{PRODUCT}.json"
    _write_json(
        bom_path,
        {
            "_order": ["materials", "cost_per_unit_in_currency", "usage", "cost_of_material_in_rial"],
            "data": {
                "materials": ["material-a", "material-b"],
                # These raw-looking inputs are intentionally inconsistent with
                # the stored Rial totals. The current aggregator ignores them.
                "cost_per_unit_in_currency": [999999, 888888],
                "usage": [77, 66],
                "cost_of_material_in_rial": [1200, 800],
            },
        },
    )
    _write_json(factory / "Factory_Data.json", {"data": {"Subfield": ["Labor", "Energy"]}})
    _write_json(factory / "Factory_Data_Labor.json", {"data": {"cost": [600, 400]}})
    _write_json(factory / "Factory_Data_Energy.json", {"data": {"cost": [150, 50]}})
    _write_json(
        factory / "category_weights.json",
        {"data": {"category": [CATEGORY], "selling_share_of_category": [50]}},
    )
    _write_json(
        factory / "ProductionPrediction.json",
        {"data": {"Product Name": [PRODUCT], "Predicted Production": [10]}},
    )
    return {"root": tmp_path, "factory": factory, "bom": bom_path}


def _calculate():
    return cost_determiners.cost_aggregator(PRODUCT, FACTORY, CATEGORY, SUBCATEGORY)


def _file_hashes(root):
    return {
        path.relative_to(root): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_current_cost_aggregator_characterization_normal_multicomponent_baseline_and_no_writes(costing_fixture):
    before = _file_hashes(costing_fixture["root"])

    result = _calculate()

    assert result == {
        "Labor": 200.0,
        "Energy": 40.0,
        "BOM": 2000,
        "BOM_Details": {
            "material-a": 1200,
            "material-b": 800,
            "Total_BOM_Cost": 2000,
        },
        "Final_Production_Cost": 2240.0,
    }
    assert _file_hashes(costing_fixture["root"]) == before


def test_current_cost_aggregator_characterization_uses_precomputed_bom_rial_values(costing_fixture):
    """Current output uses stored Rial totals, not price/usage inputs."""
    result = _calculate()

    assert result["BOM_Details"] == {
        "material-a": 1200,
        "material-b": 800,
        "Total_BOM_Cost": 2000,
    }
    assert result["BOM"] == 2000


def test_current_cost_aggregator_characterization_category_weight_effect(costing_fixture):
    """This test captures the current implementation and does not approve the business semantics of category-weight allocation."""
    _write_json(
        costing_fixture["factory"] / "category_weights.json",
        {"data": {"category": [CATEGORY], "selling_share_of_category": [25]}},
    )

    result = _calculate()

    assert result["Labor"] == 400.0
    assert result["Energy"] == 80.0
    assert result["Final_Production_Cost"] == 2480.0


def test_current_cost_aggregator_characterization_prediction_effect(costing_fixture):
    _write_json(
        costing_fixture["factory"] / "ProductionPrediction.json",
        {"data": {"Product Name": [PRODUCT], "Predicted Production": [20]}},
    )

    result = _calculate()

    assert result["Labor"] == 100.0
    assert result["Energy"] == 20.0
    assert result["Final_Production_Cost"] == 2120.0


@pytest.mark.parametrize(
    ("prediction_data", "expected_exception"),
    [
        ({"Product Name": [PRODUCT], "Predicted Production": [0]}, ZeroDivisionError),
        ({"Product Name": ["different-product"], "Predicted Production": [10]}, ValueError),
        ({"Product Name": [PRODUCT], "Predicted Production": ["not-a-number"]}, TypeError),
    ],
)
def test_current_cost_aggregator_characterization_prediction_failures(
    costing_fixture, prediction_data, expected_exception
):
    _write_json(costing_fixture["factory"] / "ProductionPrediction.json", {"data": prediction_data})

    with pytest.raises(expected_exception):
        _calculate()


def test_current_cost_aggregator_characterization_missing_prediction_file(costing_fixture):
    (costing_fixture["factory"] / "ProductionPrediction.json").unlink()

    with pytest.raises(FileNotFoundError):
        _calculate()


@pytest.mark.parametrize("failure", ["missing", "malformed-json", "missing-cost-field"])
def test_current_cost_aggregator_characterization_subfield_failures_become_zero(costing_fixture, failure):
    path = costing_fixture["factory"] / "Factory_Data_Energy.json"
    if failure == "missing":
        path.unlink()
    elif failure == "malformed-json":
        path.write_text("{not json", encoding="utf-8")
    else:
        _write_json(path, {"data": {"different_field": [150, 50]}})

    result = _calculate()

    assert result["Energy"] == 0.0
    assert result["Final_Production_Cost"] == 2200.0


@pytest.mark.parametrize(
    ("category_data", "expected_exception"),
    [
        ({"category": [CATEGORY], "selling_share_of_category": [0]}, ZeroDivisionError),
        ({"category": ["different-category"], "selling_share_of_category": [50]}, ValueError),
    ],
)
def test_current_cost_aggregator_characterization_category_failures(
    costing_fixture, category_data, expected_exception
):
    _write_json(costing_fixture["factory"] / "category_weights.json", {"data": category_data})

    with pytest.raises(expected_exception):
        _calculate()


@pytest.mark.parametrize("failure", ["missing", "malformed-json"])
def test_current_cost_aggregator_characterization_bom_file_failures(costing_fixture, failure):
    if failure == "missing":
        costing_fixture["bom"].unlink()
        expected_exception = FileNotFoundError
    else:
        costing_fixture["bom"].write_text("{not json", encoding="utf-8")
        expected_exception = json.JSONDecodeError

    with pytest.raises(expected_exception):
        _calculate()


def test_current_cost_aggregator_characterization_zero_bom_and_empty_subfield_costs(costing_fixture):
    _write_json(
        costing_fixture["bom"],
        {"data": {"materials": ["material-a"], "cost_of_material_in_rial": [0]}},
    )
    _write_json(costing_fixture["factory"] / "Factory_Data_Labor.json", {"data": {"cost": []}})
    _write_json(costing_fixture["factory"] / "Factory_Data_Energy.json", {"data": {"cost": []}})

    result = _calculate()

    assert result["BOM"] == 0
    assert result["Labor"] == 0.0
    assert result["Energy"] == 0.0
    assert result["Final_Production_Cost"] == 0.0
