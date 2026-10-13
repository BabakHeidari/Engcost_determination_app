"""Work bounds and freshness guards for the measured PR-10 bottleneck fixes."""
from collections import Counter
from decimal import Decimal

import pytest

from scripts.dashboard_benchmark_fixture import install_fixture
from utils.costing_engine import CostInputError, CostInputLoader, CostState, _decimal
from utils.factory_service import FactoryService


def loader_for(fixture):
    return CostInputLoader(FactoryService(fixture.store), data_root=fixture.data,
                           period_bindings_path=fixture.bindings, read_only=True)


def test_many_product_predictions_parsed_once_and_fresh_next_request(tmp_path, monkeypatch):
    fixture = install_fixture(tmp_path, configurations=80, selected_bom_rows=5)
    user = fixture.store.get_user_by_id("benchmark-user")
    loader = loader_for(fixture)
    population = loader.snapshot_population("benchmark-factory", user)
    original = CostInputLoader._rows
    parsed = Counter()

    def rows(document, source, required):
        parsed[source] += 1
        return original(document, source, required)

    monkeypatch.setattr(CostInputLoader, "_rows", staticmethod(rows))
    first = loader.load("benchmark-factory", user, population[0], "P", module="dashboard")
    for identity in population[1:]:
        result = loader.load("benchmark-factory", user, identity, "P", module="dashboard")
        assert result.category_predictions is first.category_predictions
        assert len(result.category_predictions) == 80  # allocation population is complete
    assert parsed["predictions"] == 1

    # A captured request stays internally consistent if a source changes. The
    # next request's new loader must see that edit, including an unselected row.
    path = fixture.factory / "configuration" / "production_prediction.json"
    import json
    document = json.loads(path.read_text())
    document["data"]["Predicted Production"][-1] = 30
    path.write_text(json.dumps(document))
    same_request = loader.load("benchmark-factory", user, population[-1], "P", module="dashboard")
    assert same_request.product_prediction == 10
    fresh = loader_for(fixture).load("benchmark-factory", user, population[-1], "P", module="dashboard")
    assert fresh.product_prediction == 30
    assert fresh.category_predictions is not first.category_predictions
    assert parsed["predictions"] == 2


@pytest.mark.parametrize("mutation,state,code", [
    ("duplicate", CostState.AMBIGUOUS_INPUT, "PREDICTION_NOT_UNIQUE"),
    ("missing", CostState.AMBIGUOUS_INPUT, "PREDICTION_NOT_UNIQUE"),
    ("negative", CostState.INVALID_INPUT, "INVALID_NUMBER"),
    ("malformed_name", CostState.INVALID_INPUT, "INVALID_SOURCE_SCHEMA"),
])
def test_prediction_index_retains_full_population_diagnostics(tmp_path, mutation, state, code):
    import json
    fixture = install_fixture(tmp_path, configurations=4, selected_bom_rows=1)
    path = fixture.factory / "configuration" / "production_prediction.json"
    document = json.loads(path.read_text())
    data = document["data"]
    if mutation == "duplicate":
        data["Product Name"].append(data["Product Name"][-1])
        data["Predicted Production"].append(10)
    elif mutation == "missing":
        for values in data.values():
            values.pop()
    elif mutation == "negative":
        data["Predicted Production"][-1] = -1
    else:
        data["Product Name"][-1] = 23
    path.write_text(json.dumps(document))
    user = fixture.store.get_user_by_id("benchmark-user")
    loader = loader_for(fixture)
    population = loader.snapshot_population("benchmark-factory", user)
    with pytest.raises(CostInputError) as error:
        loader.load("benchmark-factory", user, population[0], "P", module="dashboard")
    assert error.value.state is state
    assert error.value.detail.code == code


@pytest.mark.parametrize("value", [Decimal("0"), Decimal("0.000000000000000000000000001"),
                                   Decimal("999999999999999999999999999.123456789"), Decimal("-0")])
def test_decimal_fast_path_retains_exact_value_and_representation(value):
    result = _decimal(value, "input")
    assert result.as_tuple() == value.as_tuple()
    assert result.as_tuple() == _decimal(str(value), "input").as_tuple()


@pytest.mark.parametrize("value,state", [(True, CostState.MISSING_INPUT), (False, CostState.MISSING_INPUT),
    (Decimal("NaN"), CostState.INVALID_INPUT), (Decimal("sNaN"), CostState.INVALID_INPUT),
    (Decimal("Infinity"), CostState.INVALID_INPUT), (Decimal("-Infinity"), CostState.INVALID_INPUT),
    (Decimal("-1"), CostState.INVALID_INPUT)])
def test_decimal_fast_path_preserves_invalid_typed_states(value, state):
    with pytest.raises(CostInputError) as error:
        _decimal(value, "input")
    assert error.value.state is state
