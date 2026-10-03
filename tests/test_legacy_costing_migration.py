import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from utils.costing_engine import (
    CostInputError, CostInputLoader, CostState, FACTORY_POOL_IDS, ProductIdentity, calculate_cost,
)
from utils.legacy_costing_migration import ensure_canonical_costing_sources


NOW = datetime(2026, 10, 3, tzinfo=timezone.utc)
IDENTITY = ProductIdentity("F1", "Cat", "Sub", "Product")


class FactoryServiceStub:
    def get_factory(self, factory_id):
        return {"id": "F1", "operational_key": "legacy"} if factory_id == "F1" else None

    def operational_key(self, factory):
        return factory["operational_key"]

    def require_access(self, factory_id, user, module):
        assert user["allowed"] is True
        return self.get_factory(factory_id)


def _write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _legacy(data: Path, rows):
    _write(data / "Factories" / "legacy" / "Factory_Data.json", {"data": {
        "Subfield": [name for name, _ in rows],
        "Cost": [cost for _, cost in rows],
        "PercentageOfAll": [99] * len(rows),
    }})


def _canonical_pool(data: Path, pool: str, value):
    path = data / "Factories" / "legacy" / f"Factory_Data_{pool}.json"
    _write(path, {"_order": ["subject", "cost"], "data": {"subject": ["manual"], "cost": [value]}})
    return path


def _complete_non_pool_sources(data: Path):
    factory = data / "Factories" / "legacy"
    _write(data / "Overall" / "material_costs.json", {"data": {
        "material": ["lead"], "unit": ["kg"], "currency": ["IRR - Iranian Rial"],
        "cost_per_unit_in_currency": [2],
    }})
    _write(factory / "Cat" / "Sub" / "Product.json", {"data": {
        "materials": ["lead"], "usage": [3], "lost_percentage": [0],
        "recycability_percentage": [0],
    }})
    _write(factory / "ProductionPrediction.json", {"data": {
        "Product Name": ["Product"], "Predicted Production": [10],
    }})
    _write(factory / "category_weights.json", {"data": {
        "category": ["Cat"], "selling_share_of_category": [100],
    }})


def _binding(path: Path):
    sources = ["materials", "bom", "weights", "predictions",
               *(f"pool:{pool}" for pool in FACTORY_POOL_IDS)]
    _write(path, {"bindings": [{"factory_id": "F1", "period_id": "INITIAL",
                                 "start": "2026-01-01", "end": "2026-12-31",
                                 "active": True, "approved": True, "status": "ACTIVE",
                                 "sources": sources}]})


def test_dinmohamadpour_like_zero_and_nonzero_pools_are_migrated_exactly(tmp_path):
    data = tmp_path / "Data"
    _legacy(data, [("AdministrativeandResearch", 321.75), ("Depriciation", 0),
                   ("NonOperationalCostsandIncomes", 0)])

    report = ensure_canonical_costing_sources(
        FactoryServiceStub(), "F1", data, persist=True, clock=lambda: NOW,
    )

    assert {"pool:AdministrativeandResearch", "pool:Depriciation",
            "pool:NonOperationalCostsandIncomes"} <= set(report["created_sources"])
    for pool, expected in (("AdministrativeandResearch", 321.75), ("Depriciation", 0),
                           ("NonOperationalCostsandIncomes", 0)):
        document = json.loads((data / "Factories" / "legacy" / f"Factory_Data_{pool}.json").read_text())
        assert document["data"]["cost"] == [expected]
        assert document["_migration"]["status"] == "READY"
        assert document["_migration"]["business_value_invented"] is False


def test_nasooz_like_explicit_zero_rows_all_generate_canonical_sources(tmp_path):
    data = tmp_path / "Data"
    pools = ("Overhead", "Depriciation", "NonOperationalCostsandIncomes")
    _legacy(data, [(pool, 0.0) for pool in pools])
    report = ensure_canonical_costing_sources(FactoryServiceStub(), "F1", data, persist=True)
    assert {f"pool:{pool}" for pool in pools} <= set(report["created_sources"])


def test_absent_or_malformed_legacy_pool_never_becomes_zero(tmp_path):
    data = tmp_path / "Data"
    _legacy(data, [("Payroll", None)])
    report = ensure_canonical_costing_sources(FactoryServiceStub(), "F1", data, persist=True)
    assert "pool:Payroll" in report["unrecoverable"]
    assert not (data / "Factories" / "legacy" / "Factory_Data_Payroll.json").exists()


def test_existing_canonical_wins_and_conflict_is_reported_without_overwrite(tmp_path):
    data = tmp_path / "Data"
    _legacy(data, [("Payroll", 500)])
    canonical = _canonical_pool(data, "Payroll", 100)
    before = canonical.read_bytes()
    report = ensure_canonical_costing_sources(FactoryServiceStub(), "F1", data, persist=True)
    assert "pool:Payroll" in report["conflicts"]
    assert canonical.read_bytes() == before


def test_repeated_migration_is_byte_stable(tmp_path):
    data = tmp_path / "Data"
    _legacy(data, [("Payroll", 42)])
    ensure_canonical_costing_sources(FactoryServiceStub(), "F1", data, persist=True, clock=lambda: NOW)
    path = data / "Factories" / "legacy" / "Factory_Data_Payroll.json"
    before = path.read_bytes()
    second = ensure_canonical_costing_sources(FactoryServiceStub(), "F1", data, persist=True,
                                              clock=lambda: datetime(2030, 1, 1, tzinfo=timezone.utc))
    assert path.read_bytes() == before
    assert "pool:Payroll" in second["already_available"]


def test_dry_run_and_path_traversal_are_fail_closed(tmp_path):
    data = tmp_path / "Data"
    _legacy(data, [("Payroll", 42)])
    report = ensure_canonical_costing_sources(FactoryServiceStub(), "F1", data, persist=False)
    payroll = next(item for item in report["actions"] if item["source_name"] == "pool:Payroll")
    assert payroll["status"] == "WOULD_CREATE_READY"
    assert not (data / "Factories" / "legacy" / "Factory_Data_Payroll.json").exists()
    escaping = ProductIdentity("F1", "../../..", "..", "outside")
    with pytest.raises(ValueError, match="leaves the data root"):
        ensure_canonical_costing_sources(FactoryServiceStub(), "F1", data, escaping, persist=True)
    assert not (tmp_path / "outside.json").exists()


def test_prediction_weights_and_bom_placeholders_require_input_not_zero(tmp_path):
    data = tmp_path / "Data"
    factory = data / "Factories" / "legacy"
    _write(factory / "Cat" / "Sub" / "Known.json", {"data": {}})
    _write(factory / "Cat" / "Sub" / "Product_meta.json", {"capacity": 999})
    _legacy(data, [("Overhead", 1)])
    report = ensure_canonical_costing_sources(
        FactoryServiceStub(), "F1", data, IDENTITY, persist=True, clock=lambda: NOW,
    )
    assert {"predictions", "weights", "bom"} <= set(report["needs_input"])
    prediction = json.loads((factory / "ProductionPrediction.json").read_text())
    weights = json.loads((factory / "category_weights.json").read_text())
    bom = json.loads((factory / "Cat" / "Sub" / "Product.json").read_text())
    assert prediction["data"]["Predicted Production"] == [None]
    assert weights["data"]["selling_share_of_category"] == [None]
    assert bom["data"]["materials"] == []
    assert all(item["_migration"]["status"] == "NEEDS_INPUT" for item in (prediction, weights, bom))


def test_loader_self_heals_recoverable_pool_and_calculates_normally(tmp_path):
    data, binding = tmp_path / "Data", tmp_path / "binding.json"
    _complete_non_pool_sources(data)
    _legacy(data, [(pool, 0 if pool != "Payroll" else 100) for pool in FACTORY_POOL_IDS])
    _binding(binding)
    loader = CostInputLoader(FactoryServiceStub(), data_root=data, period_bindings_path=binding)
    inputs = loader.load("F1", {"allowed": True}, IDENTITY, "INITIAL")
    assert next(pool.raw_amount for pool in inputs.factory_pools if pool.pool_id == "Payroll") == 100
    assert (data / "Factories" / "legacy" / "Factory_Data_Payroll.json").exists()
    assert calculate_cost(inputs).state is CostState.OK


def test_loader_blocks_generated_incomplete_source_with_diagnostic(tmp_path):
    data, binding = tmp_path / "Data", tmp_path / "binding.json"
    _complete_non_pool_sources(data)
    (data / "Factories" / "legacy" / "ProductionPrediction.json").unlink()
    _legacy(data, [(pool, 0) for pool in FACTORY_POOL_IDS])
    _binding(binding)
    loader = CostInputLoader(FactoryServiceStub(), data_root=data, period_bindings_path=binding)
    with pytest.raises(CostInputError) as caught:
        loader.load("F1", {"allowed": True}, IDENTITY, "INITIAL")
    assert caught.value.detail.code == "LEGACY_SOURCE_NEEDS_INPUT"
    prediction = next(item for item in caught.value.diagnostic["source_resolutions"]
                      if item["source_name"] == "predictions")
    assert prediction["migration_status"] == "NEEDS_INPUT"
    assert prediction["calculation_ready"] is False


def test_missing_known_bom_is_generated_incomplete_and_never_costed_as_zero(tmp_path):
    data, binding = tmp_path / "Data", tmp_path / "binding.json"
    _complete_non_pool_sources(data)
    factory = data / "Factories" / "legacy"
    (factory / "Cat" / "Sub" / "Product.json").unlink()
    _write(factory / "Cat" / "Sub" / "Product_meta.json", {"capacity": 5000})
    _legacy(data, [(pool, 0) for pool in FACTORY_POOL_IDS])
    _binding(binding)
    loader = CostInputLoader(FactoryServiceStub(), data_root=data, period_bindings_path=binding)
    with pytest.raises(CostInputError) as caught:
        loader.load("F1", {"allowed": True}, IDENTITY, "INITIAL")
    assert caught.value.detail.code == "LEGACY_SOURCE_NEEDS_INPUT"
    bom = json.loads((factory / "Cat" / "Sub" / "Product.json").read_text())
    assert bom["data"]["materials"] == []
    assert bom["_migration"]["status"] == "NEEDS_INPUT"


def test_loader_reports_conflict_when_healing_cannot_safely_reconcile(tmp_path):
    data, binding = tmp_path / "Data", tmp_path / "binding.json"
    _complete_non_pool_sources(data)
    _legacy(data, [(pool, 100 if pool == "Payroll" else 0) for pool in FACTORY_POOL_IDS])
    for pool in FACTORY_POOL_IDS:
        if pool != "Depriciation":
            _canonical_pool(data, pool, 999 if pool == "Payroll" else 0)
    _binding(binding)
    loader = CostInputLoader(FactoryServiceStub(), data_root=data, period_bindings_path=binding)
    with pytest.raises(CostInputError) as caught:
        loader.load("F1", {"allowed": True}, IDENTITY, "INITIAL")
    assert caught.value.detail.code == "LEGACY_SOURCE_CONFLICT"
    assert "pool:Payroll" in caught.value.diagnostic["legacy_migration"]["conflicts"]
    assert json.loads((data / "Factories" / "legacy" / "Factory_Data_Payroll.json").read_text())["data"]["cost"] == [999]
