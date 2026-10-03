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
    _write(data / "Overall" / "material_costs.json", {"effective_date": "1405/02/10", "data": {"material": ["lead"]}})
    _write(data / "Factories" / "op-one" / "Cat" / "Sub" / "Product.json", {"business_date": "1405/01/15", "data": {"materials": ["lead"]}})
    _write(data / "Factories" / "op-one" / "ProductionPrediction.json", {"prediction_date": "1405/03/01", "data": {"Product Name": ["A"]}})

    draft = discover_initial_period(FactoryService(store), "F1", data, binding, clock=lambda: NOW)

    assert draft["start"] == "2026-04-04"
    assert draft["status"] == "ACTIVE" and draft["approved"] is True and draft["active"] is True
    assert draft["creation_reason"] == "FIRST_FACTORY_COSTING_INITIALIZATION"
    assert draft["date_origin"] == "SOURCE_DATE"
    assert draft["approved_by"] == draft["approval_type"] == "SYSTEM_INITIALIZATION"
    assert draft["end"] == "2026-09-27"
    assert draft["source_evidence"][0]["source_type"] == "PRODUCT_BOM"
    assert draft["source_evidence"][0]["source_identifier"] == "business_date"
    assert draft["created_at"] == NOW.isoformat()


def test_no_date_uses_explicit_system_initialization_baseline_not_source_timestamp(tmp_path):
    store = _registry(tmp_path)
    data, binding = tmp_path / "Data", tmp_path / "bindings.json"
    _write(data / "Overall" / "material_costs.json", {"data": {"material": ["lead"]}})
    _write(data / "Factories" / "op-one" / "ProductionPrediction.json", {"data": {"Product Name": ["A"]}})

    draft = discover_initial_period(FactoryService(store), "F1", data, binding, clock=lambda: NOW)

    assert draft["start"] == "2026-09-27"
    assert draft["creation_reason"] == "FIRST_FACTORY_COSTING_INITIALIZATION"
    assert draft["date_origin"] == "SYSTEM_INITIALIZATION_DATE"
    assert draft["discovery_status"] == "NO_AUTHORITATIVE_SOURCE_DATE"
    assert draft["source_evidence"] == []
    assert "actual_as_of" not in draft


def test_initialization_records_metadata_only_for_valid_readable_sources(tmp_path):
    store = _registry(tmp_path)
    data, binding = tmp_path / "Data", tmp_path / "bindings.json"
    _write(data / "Overall" / "material_costs.json", {"data": {"material": ["lead"]}})
    invalid = data / "Factories" / "op-one" / "category_weights.json"
    invalid.parent.mkdir(parents=True, exist_ok=True)
    invalid.write_text("{bad", encoding="utf-8")
    _write(data / "Factories" / "op-one" / "ProductionPrediction.json", {"data": {"Product Name": ["A"]}})

    initial = discover_initial_period(FactoryService(store), "F1", data, binding, clock=lambda: NOW)

    assert initial["source_metadata"] == [
        {"source_name": "materials", "location": "Data/Overall/material_costs.json"},
        {"source_name": "predictions", "location": "Data/Factories/op-one/ProductionPrediction.json"},
    ]
    assert "weights" in initial["sources"]


def test_automatic_initial_period_is_immediately_usable_and_not_duplicated(tmp_path):
    store = _registry(tmp_path)
    data, binding = tmp_path / "Data", tmp_path / "bindings.json"
    _write(data / "Overall" / "material_costs.json", {"effective_date": "2026-01-01", "data": {"material": ["lead"]}})
    discover_initial_period(FactoryService(store), "F1", data, binding, clock=lambda: NOW)
    loader = CostInputLoader(FactoryService(store), data_root=data, period_bindings_path=binding)
    period, sources = loader._period_binding("F1", "")
    active = discover_initial_period(FactoryService(store), "F1", data, binding, clock=lambda: NOW)
    assert active["status"] == "ACTIVE" and active["approved"] is True and active["active"] is True
    assert period.period_id == "INITIAL"
    assert json.loads(binding.read_text(encoding="utf-8"))["bindings"] == [active]


def test_factories_discover_independent_initial_dates(tmp_path):
    store = _registry(tmp_path)
    data, binding = tmp_path / "Data", tmp_path / "bindings.json"
    _write(data / "Overall" / "material_costs.json", {"data": {}})
    _write(data / "Factories" / "op-one" / "ProductionPrediction.json", {"business_date": "2025-01-02", "data": {"Product Name": ["A"]}})
    _write(data / "Factories" / "op-two" / "Factory_Data_Payroll.json", {"effective_date": "2024-03-04", "data": {"cost": [1]}})
    first = discover_initial_period(FactoryService(store), "F1", data, binding, clock=lambda: NOW)
    second = discover_initial_period(FactoryService(store), "F2", data, binding, clock=lambda: NOW)
    assert first["start"] == "2025-01-02"
    assert second["start"] == "2024-03-04"
    assert first["factory_id"] != second["factory_id"]


def test_period_diagnostic_traces_operational_resolution_and_draft_reason(tmp_path):
    store = _registry(tmp_path)
    data, binding = tmp_path / "Data", tmp_path / "bindings.json"
    _write(data / "Overall" / "material_costs.json", {"effective_date": "2026-01-01", "data": {"material": ["lead"]}})
    _write(binding, {"bindings": [{"factory_id": "F1", "period_id": "INITIAL", "start": "2026-01-01",
                                    "end": None, "status": "DRAFT", "approved": False, "active": False}]})

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
    _write(data / "Overall" / "material_costs.json", {"effective_date": "2026-01-01", "data": {"material": ["lead"]}})
    discover_initial_period(FactoryService(store), "F1", data, binding, clock=lambda: NOW)
    usable = validate_costing_period(FactoryService(store), binding, "F1", "INITIAL")
    assert usable["checks"] == {"active": True, "approved": True, "active_status": True, "valid_dates": True}
    assert usable["usable_by_costing"] is True and usable["approval_owner"] == "SYSTEM_INITIALIZATION"

    document = json.loads(binding.read_text(encoding="utf-8"))
    document["bindings"][0]["start_date"] = document["bindings"][0].pop("start")
    _write(binding, document)
    invalid = validate_costing_period(FactoryService(store), binding, "F1")
    assert invalid["usable_by_costing"] is False
    assert "canonical start/end fields" in invalid["reason"]


def test_future_history_and_invalid_factory_cannot_use_first_period_rule(tmp_path):
    store = _registry(tmp_path)
    data, binding = tmp_path / "Data", tmp_path / "bindings.json"
    _write(data / "Overall" / "material_costs.json", {"effective_date": "2026-01-01", "data": {"material": ["lead"]}})
    _write(binding, {"bindings": [{"factory_id": "F1", "period_id": "P2", "start": "2027-01-01",
                                    "end": "2027-12-31", "status": "DRAFT", "approved": False, "active": False}]})
    with pytest.raises(ValueError, match="first-period only"):
        discover_initial_period(FactoryService(store), "F1", data, binding, clock=lambda: NOW)
    with pytest.raises(ValueError, match="canonical factory"):
        discover_initial_period(FactoryService(store), "missing", data, binding, clock=lambda: NOW)
