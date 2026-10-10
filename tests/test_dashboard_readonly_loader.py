"""Strict Dashboard input snapshots must never migrate operational sources."""

from datetime import date
from decimal import Decimal
import hashlib
import json

import pytest

from utils.costing_engine import (
    CostInputError, CostInputLoader, CostState, FACTORY_POOL_IDS,
    ProductIdentity, calculate_cost,
)
from utils.factory_configuration import ensure_factory_configuration_v2


A = ProductIdentity("canonical", "category", "sub", "A")
B = ProductIdentity("canonical", "category", "sub", "B")


class FactoryStub:
    def __init__(self):
        self.modules = []

    def require_access(self, factory_id, user, module):
        assert factory_id == "canonical"
        self.modules.append(module)
        return {"id": factory_id}

    def get_factory(self, factory_id):
        return {"id": factory_id} if factory_id == "canonical" else None

    def operational_key(self, factory):
        return "operational"


def write(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")


def files_and_directories(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            if path.is_file() else None for path in root.rglob("*")}


def fixture_tree(tmp_path, *, install=True):
    data = tmp_path / "Data"
    factory = data / "Factories" / "operational"
    write(data / "Overall" / "material_costs.json", {"data": {
        "material": ["lead", "USD"], "unit": ["kg", "currency"],
        "currency": ["USD", "IRR - Iranian Rial"], "cost_per_unit_in_currency": [2, 500000],
    }})
    for name, usage in (("A", 100), ("B", 40)):
        write(factory / "category" / "sub" / f"{name}.json", {"data": {
            "materials": ["lead"], "usage": [usage], "lost_percentage": [10],
            "recycability_percentage": [20], "cost_of_material_in_rial": [777777],
        }})
    write(factory / "category_weights.json", {"data": {
        "category": ["category"], "selling_share_of_category": [50],
    }})
    write(factory / "ProductionPrediction.json", {"data": {
        "Product Name": ["A", "B"], "Predicted Production": [10, 10],
    }})
    for pool_id in FACTORY_POOL_IDS:
        write(factory / f"Factory_Data_{pool_id}.json", {"data": {
            "subject": [pool_id], "cost": [1000 if pool_id == "Payroll" else 0],
        }})
    binding = tmp_path / "periods.json"
    write(binding, {"bindings": [{
        "factory_id": "canonical", "period_id": "INITIAL", "active": True,
        "approved": True, "status": "ACTIVE", "approval_type": "SYSTEM_INITIALIZATION",
        "approved_by": "SYSTEM_INITIALIZATION", "start": "2026-10-01", "end": "2026-12-31",
        "sources": ["materials", "bom", "weights", "predictions", *(f"pool:{pool}" for pool in FACTORY_POOL_IDS)],
    }]})
    if install:
        ensure_factory_configuration_v2("canonical", "operational", data_root=data)
        # Analysis has no need to create even the configuration migration lock.
        (factory / ".factory-configuration-v2.lock").unlink()
    return data, factory, binding


def loader(data, binding, *, read_only=True):
    return CostInputLoader(FactoryStub(), data_root=data,
                           period_bindings_path=binding, read_only=read_only)


def test_installed_v2_dashboard_snapshot_uses_shared_goldens_without_any_writes(tmp_path, monkeypatch):
    data, _, binding = fixture_tree(tmp_path)
    before = files_and_directories(tmp_path)
    monkeypatch.setattr("utils.factory_configuration.ensure_factory_configuration_v2",
                        lambda *args, **kwargs: pytest.fail("Dashboard attempted V2 migration"))
    monkeypatch.setattr("utils.legacy_costing_migration.ensure_canonical_costing_sources",
                        lambda *args, **kwargs: pytest.fail("Dashboard attempted legacy migration"))
    inputs_loader = loader(data, binding)

    assert inputs_loader.snapshot_population("canonical", {}) == (A, B)
    first = inputs_loader.load("canonical", {}, A, "INITIAL", module="dashboard")
    second = inputs_loader.load("canonical", {}, B, "INITIAL", module="dashboard")
    result = calculate_cost(first)

    assert result.state is CostState.OK
    assert result.bom_total == Decimal("98000000")
    payroll = next(item for item in result.driver_components if item.pool_id == "Payroll")
    assert payroll.per_unit_contribution == Decimal("100")
    assert payroll.adjusted_category_pool == Decimal("2000")
    assert payroll.modeled_minus_raw == Decimal("1000")
    assert first.loaded_at == second.loaded_at
    assert inputs_loader.factory_service.modules == ["dashboard"] * 3
    assert {item.source for item in inputs_loader.snapshot_lineage()} >= {"period_binding", "configuration", "bom"}
    assert all(str(tmp_path) not in item.source for item in inputs_loader.snapshot_lineage())
    assert files_and_directories(tmp_path) == before


def test_dashboard_module_enforces_read_only_even_without_constructor_flag(tmp_path):
    data, _, binding = fixture_tree(tmp_path, install=False)
    before = files_and_directories(tmp_path)
    with pytest.raises(CostInputError) as caught:
        loader(data, binding, read_only=False).load("canonical", {}, A, "INITIAL", module="dashboard")
    assert caught.value.state is CostState.MISSING_INPUT
    assert caught.value.detail.source == "configuration"
    assert files_and_directories(tmp_path) == before


@pytest.mark.parametrize("damage,expected_state", [
    ("missing", CostState.MISSING_INPUT), ("malformed", CostState.INVALID_INPUT),
    ("unfinished", CostState.MISSING_INPUT), ("invalid", CostState.INVALID_INPUT),
])
def test_missing_and_invalid_canonical_pools_have_safe_typed_states_and_no_writes(tmp_path, damage, expected_state):
    data, factory, binding = fixture_tree(tmp_path)
    pool = factory / "configuration" / "cost_pools" / "Payroll.json"
    if damage == "missing":
        pool.unlink()
    elif damage == "malformed":
        pool.write_text('{"private": "sensitive", bad}', encoding="utf-8")
    else:
        write(pool, {"status": "NEEDS_INPUT" if damage == "unfinished" else "INVALID_LEGACY_SOURCE",
                     "data": {"cost": []}})
    before = files_and_directories(tmp_path)
    inputs_loader = loader(data, binding)
    assert inputs_loader.snapshot_population("canonical", {}) == (A, B)
    with pytest.raises(CostInputError) as caught:
        inputs_loader.load("canonical", {}, A, "INITIAL", module="dashboard")
    assert caught.value.state is expected_state
    assert caught.value.detail.source == "pool:Payroll"
    assert "sensitive" not in str(caught.value)
    assert str(tmp_path) not in str(caught.value)
    assert files_and_directories(tmp_path) == before


def test_request_snapshot_freezes_all_boms_shared_sources_bindings_and_population(tmp_path):
    data, factory, binding = fixture_tree(tmp_path)
    inputs_loader = loader(data, binding)
    assert inputs_loader.snapshot_population("canonical", {}) == (A, B)
    first = inputs_loader.load("canonical", {}, A, "INITIAL", module="dashboard")
    write(factory / "category" / "sub" / "B.json", {"broken": True})
    write(factory / "category" / "sub" / "C.json", {"broken": True})
    write(factory / "configuration" / "production_prediction.json", {"broken": True})
    binding.unlink()

    second = inputs_loader.load("canonical", {}, B, "INITIAL", module="dashboard")

    assert inputs_loader.snapshot_population("canonical", {}) == (A, B)
    assert second.category_predictions == first.category_predictions
    assert calculate_cost(second).bom_total == Decimal("39200000")
    assert second.period == first.period
    assert inputs_loader.resolve_period("canonical").period_id == "INITIAL"


def test_failed_source_read_is_frozen_for_remaining_request_rows(tmp_path):
    data, factory, binding = fixture_tree(tmp_path)
    path = factory / "category" / "sub" / "B.json"
    path.write_text("broken", encoding="utf-8")
    inputs_loader = loader(data, binding)
    inputs_loader.snapshot_population("canonical", {})
    write(path, {"data": {"materials": [], "usage": [], "lost_percentage": [], "recycability_percentage": []}})
    with pytest.raises(CostInputError) as caught:
        inputs_loader.load("canonical", {}, B, "INITIAL", module="dashboard")
    assert caught.value.detail.code == "SOURCE_PARSE_ERROR"


def test_snapshot_freezes_resolved_source_paths_when_same_factory_symlink_changes(tmp_path):
    data, factory, binding = fixture_tree(tmp_path)
    inputs_loader = loader(data, binding)
    inputs_loader.snapshot_population("canonical", {})
    bom = factory / "category" / "sub" / "B.json"
    bom.unlink()
    bom.symlink_to(bom.with_name("A.json"))

    result = calculate_cost(inputs_loader.load("canonical", {}, B, "INITIAL", module="dashboard"))

    assert result.bom_total == Decimal("39200000")


def test_same_factory_pool_alias_preserves_each_logical_provenance_role(tmp_path):
    data, factory, binding = fixture_tree(tmp_path)
    depreciation = factory / "configuration" / "cost_pools" / "Depriciation.json"
    depreciation.unlink()
    depreciation.symlink_to(depreciation.with_name("Payroll.json"))
    before = files_and_directories(tmp_path)

    inputs = loader(data, binding).load("canonical", {}, A, "INITIAL", module="dashboard")

    pools = {pool.pool_id: pool for pool in inputs.factory_pools}
    assert pools["Payroll"].provenance.source == "pool:Payroll"
    assert pools["Depriciation"].provenance.source == "pool:Depriciation"
    assert pools["Payroll"].provenance.fingerprint == pools["Depriciation"].provenance.fingerprint
    assert {source.source for source in inputs.provenance} == {
        "materials", "bom", "weights", "predictions", *(f"pool:{pool}" for pool in FACTORY_POOL_IDS),
    }
    assert files_and_directories(tmp_path) == before


@pytest.mark.parametrize("alias", ["bom", "metadata", "category", "configuration", "factory", "materials"])
def test_readonly_rejects_symlinks_into_foreign_operational_namespaces_without_writes(tmp_path, alias):
    data, factory, binding = fixture_tree(tmp_path)
    foreign = data / "Factories" / "foreign"
    if alias in {"bom", "metadata"}:
        source = factory / "category" / "sub" / ("A.json" if alias == "bom" else "A_meta.json")
        if source.exists():
            source.unlink()
        target = foreign / "category" / "sub" / "Private.json"
        write(target, {"private": "secret"})
    elif alias == "materials":
        source = data / "Overall" / "material_costs.json"
        source.unlink()
        target = foreign / "material_costs.json"
        write(target, {"private": "secret"})
    else:
        source = factory if alias == "factory" else factory / alias
        target = foreign if alias == "factory" else foreign / alias
        target.parent.mkdir(parents=True, exist_ok=True)
        source.rename(target)
    source.symlink_to(target, target_is_directory=target.is_dir())
    before = files_and_directories(tmp_path)

    with pytest.raises(CostInputError) as caught:
        loader(data, binding).snapshot_population("canonical", {})

    assert caught.value.state is CostState.INVALID_INPUT
    assert caught.value.detail.code == "UNSAFE_SOURCE_PATH"
    assert "secret" not in str(caught.value)
    assert files_and_directories(tmp_path) == before


def test_period_range_must_match_existing_valid_system_initialization_binding(tmp_path):
    data, _, binding = fixture_tree(tmp_path)
    inputs_loader = loader(data, binding)
    period = inputs_loader.resolve_period("canonical", start="2026-10-01", end="2026-12-31")
    assert period.start == date(2026, 10, 1)
    before = files_and_directories(tmp_path)
    with pytest.raises(CostInputError) as caught:
        inputs_loader.resolve_period("canonical", start="2026-10-02", end="2026-12-31")
    assert caught.value.detail.code == "PERIOD_MISMATCH"
    assert files_and_directories(tmp_path) == before


@pytest.mark.parametrize("document", [{"bindings": {}}, {"bindings": [None]}, {"bindings": [{
    "factory_id": "canonical", "period_id": "INITIAL", "active": True, "approved": True,
    "status": "ACTIVE", "start": "2026-10-01", "end": "2026-12-31", "sources": [{}],
}]}])
def test_malformed_binding_returns_typed_error_without_creating_any_files(tmp_path, document):
    data, _, binding = fixture_tree(tmp_path)
    write(binding, document)
    before = files_and_directories(tmp_path)
    with pytest.raises(CostInputError) as caught:
        loader(data, binding).resolve_period("canonical")
    assert caught.value.state is CostState.INVALID_INPUT
    assert caught.value.detail.code == "INVALID_PERIOD_BINDING"
    assert files_and_directories(tmp_path) == before


def test_scope_population_excludes_configuration_and_preserves_same_name_paths(tmp_path):
    data, factory, binding = fixture_tree(tmp_path)
    write(factory / "category" / "other" / "A.json", {"data": {
        "materials": ["lead"], "usage": [1], "lost_percentage": [0], "recycability_percentage": [0],
    }})
    write(factory / "configuration" / "cost_pools" / "Fake.json", {"data": {"cost": [999]}})
    inputs_loader = loader(data, binding)
    population = inputs_loader.snapshot_population("canonical", {})
    other_a = ProductIdentity("canonical", "category", "other", "A")

    assert set(population) == {A, B, other_a}
    first = inputs_loader.load("canonical", {}, A, "INITIAL", module="dashboard")
    other = inputs_loader.load("canonical", {}, other_a, "INITIAL", module="dashboard")
    assert {item.identity for item in first.category_predictions} == {A, B, other_a}
    assert calculate_cost(first).bom_total != calculate_cost(other).bom_total


def test_invalid_material_identity_is_typed_instead_of_unhandled_type_error(tmp_path):
    data, _, binding = fixture_tree(tmp_path)
    write(data / "Overall" / "material_costs.json", {"data": {
        "material": [["lead"]], "unit": ["kg"], "currency": ["IRR - Iranian Rial"],
        "cost_per_unit_in_currency": [1],
    }})
    before = files_and_directories(tmp_path)
    with pytest.raises(CostInputError) as caught:
        loader(data, binding).load("canonical", {}, A, "INITIAL", module="dashboard")
    assert caught.value.detail.code == "INVALID_SOURCE_SCHEMA"
    assert files_and_directories(tmp_path) == before


def test_authorization_precedes_every_operational_lookup(tmp_path, monkeypatch):
    class Denied(FactoryStub):
        def require_access(self, *args):
            raise PermissionError("denied")

        def operational_key(self, factory):
            pytest.fail("resolved operational key before authorization")

    monkeypatch.setattr("utils.costing_engine.build_product_catalog",
                        lambda *args, **kwargs: pytest.fail("read operational catalog before authorization"))
    inputs_loader = CostInputLoader(Denied(), data_root=tmp_path, read_only=True)
    with pytest.raises(PermissionError):
        inputs_loader.snapshot_population("canonical", {})
    with pytest.raises(PermissionError):
        inputs_loader.load("canonical", {}, A, "", module="dashboard")


def test_dashboard_and_cost_calculation_agree_for_identical_installed_inputs(tmp_path):
    data, _, binding = fixture_tree(tmp_path)
    readonly = loader(data, binding).load("canonical", {}, A, "INITIAL", module="dashboard")
    normal = loader(data, binding, read_only=False).load("canonical", {}, A, "INITIAL")

    analytical, calculation = calculate_cost(readonly), calculate_cost(normal)
    assert analytical.value == calculation.value
    assert analytical.bom_components == calculation.bom_components
    assert analytical.driver_components == calculation.driver_components


def test_metadata_lineage_does_not_invent_legacy_baseline_or_source_as_of(tmp_path):
    data, factory, binding = fixture_tree(tmp_path)
    binding_document = json.loads(binding.read_text())
    binding_document["bindings"][0]["approved_at"] = "2026-10-10T12:00:00+00:00"
    write(binding, binding_document)
    manifest_path = factory / "configuration" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["migrated_at"] = "2026-10-10T13:00:00+00:00"
    write(manifest_path, manifest)
    inputs_loader = loader(data, binding)
    inputs_loader.snapshot_population("canonical", {})

    metadata = [source for source in inputs_loader.snapshot_lineage()
                if source.source in {"period_binding", "configuration"}]

    assert len(metadata) == 2
    assert all(source.actual_as_of is None for source in metadata)
    assert all(source.owner_assigned_baseline is None for source in metadata)


def test_default_cost_calculation_keeps_accepting_unrelated_blank_source_cells(tmp_path):
    data, factory, binding = fixture_tree(tmp_path)
    material_path = data / "Overall" / "material_costs.json"
    materials = json.loads(material_path.read_text())
    for column, value in {"material": "unused", "unit": "", "currency": "", "cost_per_unit_in_currency": None}.items():
        materials["data"][column].append(value)
    write(material_path, materials)
    weights_path = factory / "configuration" / "category_weights.json"
    weights = json.loads(weights_path.read_text())
    weights["data"]["category"].append("")
    weights["data"]["selling_share_of_category"].append(None)
    write(weights_path, weights)
    prediction_path = factory / "configuration" / "production_prediction.json"
    predictions = json.loads(prediction_path.read_text())
    predictions["data"]["Product Name"].append("")
    predictions["data"]["Predicted Production"].append(None)
    write(prediction_path, predictions)

    result = calculate_cost(loader(data, binding, read_only=False).load("canonical", {}, A, "INITIAL"))

    assert result.state is CostState.OK
    assert result.bom_total == Decimal("98000000")
