import json
from datetime import datetime, timezone

import pytest

from utils.costing_engine import CostInputError, CostInputLoader, FACTORY_POOL_IDS
from utils.factory_service import FactoryService
from utils.planning_periods import REQUIRED_SOURCES, approve_initial_period, discover_initial_period, validate_costing_period
from utils.profile_store import ProfileDataStore


NOW = datetime(2026, 9, 27, 8, 30, tzinfo=timezone.utc)


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _registry(tmp_path):
    store = ProfileDataStore(tmp_path / "profiles.json")
    store.initialize({})
    for factory_id, operational in (("F1", "op-one"), ("F2", "op-two")):
        store.create_factory({"id": factory_id, "code": factory_id, "name": factory_id,
                              "operational_key": operational, "is_active": True})
    for user_id, role in (("manager", "IT_ADMIN"), ("finance", "FINANCE_ECONOMIC_ADMIN"), ("ordinary", "USER")):
        store.create_user({"id": user_id, "username": user_id, "email": f"{user_id}@example.test",
                           "full_name": user_id, "system_role": role, "job_title": "test", "access_grants": [],
                           "is_active": True, "must_change_password": False, "password_hash": "unused",
                           "password_scheme": "werkzeug", "revision": 1})
    return store


def test_discovery_uses_earliest_valid_business_date_and_records_evidence(tmp_path):
    store = _registry(tmp_path)
    data, binding = tmp_path / "Data", tmp_path / "bindings.json"
    _write(data / "Overall" / "material_costs.json", {"effective_date": "1405/02/10"})
    _write(data / "Factories" / "op-one" / "Cat" / "Sub" / "Product.json", {"business_date": "1405/01/15"})
    _write(data / "Factories" / "op-one" / "ProductionPrediction.json", {"prediction_date": "1405/03/01"})

    draft = discover_initial_period(FactoryService(store), "F1", data, binding, clock=lambda: NOW)

    assert draft["start"] == "2026-04-04"
    assert draft["status"] == "DRAFT" and draft["approved"] is False and draft["active"] is False
    assert draft["creation_reason"] == "FIRST_AVAILABLE_DATA_DATE" and draft["baseline_type"] == "SOURCE_DATE"
    assert draft["source_evidence"][0]["source_type"] == "PRODUCT_BOM"
    assert draft["source_evidence"][0]["source_identifier"] == "business_date"
    assert draft["created_at"] == NOW.isoformat()


def test_no_date_uses_explicit_system_initialization_baseline_not_source_timestamp(tmp_path):
    store = _registry(tmp_path)
    data, binding = tmp_path / "Data", tmp_path / "bindings.json"
    _write(data / "Overall" / "material_costs.json", {"data": {}})
    _write(data / "Factories" / "op-one" / "ProductionPrediction.json", {"data": {}})

    draft = discover_initial_period(FactoryService(store), "F1", data, binding, clock=lambda: NOW)

    assert draft["start"] == "2026-09-27"
    assert draft["creation_reason"] == draft["baseline_type"] == "SYSTEM_INITIALIZATION_DATE"
    assert draft["discovery_status"] == "NO_AUTHORITATIVE_SOURCE_DATE"
    assert draft["source_evidence"] == []
    assert "actual_as_of" not in draft


def test_draft_is_rejected_then_manager_approval_makes_it_active(tmp_path):
    store = _registry(tmp_path)
    data, binding = tmp_path / "Data", tmp_path / "bindings.json"
    _write(data / "Overall" / "material_costs.json", {"effective_date": "2026-01-01"})
    discover_initial_period(FactoryService(store), "F1", data, binding, clock=lambda: NOW)
    loader = CostInputLoader(FactoryService(store), data_root=data, period_bindings_path=binding)
    with pytest.raises(CostInputError) as caught:
        loader._period_binding("F1", "INITIAL")
    assert caught.value.detail.code == "PERIOD_NOT_BOUND"
    with pytest.raises(PermissionError):
        approve_initial_period(store, binding, "F1", "ordinary", "2026-12-31", REQUIRED_SOURCES)

    active = approve_initial_period(store, binding, "F1", "finance", "2026-12-31", REQUIRED_SOURCES,
                                    clock=lambda: NOW)
    loader = CostInputLoader(FactoryService(store), data_root=data, period_bindings_path=binding)
    period, sources = loader._period_binding("F1", "")
    assert active["status"] == "ACTIVE" and active["approved"] is True and active["active"] is True
    assert period.period_id == "INITIAL" and sources == set(REQUIRED_SOURCES)


def test_factories_discover_independent_initial_dates(tmp_path):
    store = _registry(tmp_path)
    data, binding = tmp_path / "Data", tmp_path / "bindings.json"
    _write(data / "Overall" / "material_costs.json", {"data": {}})
    _write(data / "Factories" / "op-one" / "ProductionPrediction.json", {"business_date": "2025-01-02"})
    _write(data / "Factories" / "op-two" / "Factory_Data_Payroll.json", {"effective_date": "2024-03-04"})
    first = discover_initial_period(FactoryService(store), "F1", data, binding, clock=lambda: NOW)
    second = discover_initial_period(FactoryService(store), "F2", data, binding, clock=lambda: NOW)
    assert first["start"] == "2025-01-02"
    assert second["start"] == "2024-03-04"
    assert first["factory_id"] != second["factory_id"]


def test_period_diagnostic_traces_operational_resolution_and_draft_reason(tmp_path):
    store = _registry(tmp_path)
    data, binding = tmp_path / "Data", tmp_path / "bindings.json"
    _write(data / "Overall" / "material_costs.json", {"effective_date": "2026-01-01"})
    discover_initial_period(FactoryService(store), "F1", data, binding, clock=lambda: NOW)

    result = validate_costing_period(FactoryService(store), binding, "op-one")

    assert result["factory_input"] == "op-one"
    assert result["canonical_id"] == result["binding_factory_id"] == "F1"
    assert result["factory_resolution"] == "UNIQUE_OPERATIONAL_KEY"
    assert result["period_found"] is True and result["period_id"] == "INITIAL"
    assert result["status"] == "DRAFT" and result["approved"] is False
    assert result["usable_by_costing"] is False
    assert "owner approval is missing" in result["reason"]


def test_period_diagnostic_reports_active_approved_and_schema_failures(tmp_path):
    store = _registry(tmp_path)
    data, binding = tmp_path / "Data", tmp_path / "bindings.json"
    _write(data / "Overall" / "material_costs.json", {"effective_date": "2026-01-01"})
    discover_initial_period(FactoryService(store), "F1", data, binding, clock=lambda: NOW)
    approve_initial_period(store, binding, "F1", "manager", "2026-12-31", REQUIRED_SOURCES, clock=lambda: NOW)
    usable = validate_costing_period(FactoryService(store), binding, "F1", "INITIAL")
    assert usable["checks"] == {"active": True, "approved": True, "active_status": True, "valid_dates": True}
    assert usable["usable_by_costing"] is True and usable["approval_owner"] == "manager"

    document = json.loads(binding.read_text(encoding="utf-8"))
    document["bindings"][0]["start_date"] = document["bindings"][0].pop("start")
    _write(binding, document)
    invalid = validate_costing_period(FactoryService(store), binding, "F1")
    assert invalid["usable_by_costing"] is False
    assert "canonical start/end fields" in invalid["reason"]
