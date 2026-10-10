import json
from pathlib import Path
from unittest import mock

import pytest
from flask import Flask, current_app, has_app_context

import app as app_module
from utils.factory_configuration import ensure_factory_configuration_v2 as real_ensure


FACTORIES = [{"id": "factory-1"}, {"id": "factory-2"}]


class FakeService:
    def __init__(self, store):
        self.store = store

    def list_factories(self):
        return FACTORIES

    def operational_key(self, factory):
        return f"op-{factory['id']}"


def configured_app(tmp_path):
    application = Flask(__name__, instance_path=str(tmp_path / "instance"))
    application.config["PROFILE_STORE_PATH"] = str(tmp_path / "profiles.json")
    return application


def test_startup_store_access_is_inside_application_context(tmp_path):
    application = configured_app(tmp_path)

    def context_bound_store():
        assert has_app_context()
        assert current_app is application
        assert current_app.config["PROFILE_STORE_PATH"].endswith("profiles.json")
        assert Path(current_app.instance_path).name == "instance"
        return object()

    migrated = []
    with mock.patch.object(app_module, "get_profile_store", side_effect=context_bound_store), \
         mock.patch.object(app_module, "FactoryService", FakeService), \
         mock.patch.object(app_module, "ensure_factory_configuration_v2",
                           side_effect=lambda factory_id, operational_key, persist: migrated.append((factory_id, operational_key, persist))):
        app_module.initialize_factory_configuration_v2(application)

    assert migrated == [("factory-1", "op-factory-1", True), ("factory-2", "op-factory-2", True)]


def test_expected_failure_warns_and_next_factory_still_migrates(tmp_path):
    application = configured_app(tmp_path)
    migrated = []

    def migrate(factory_id, operational_key, persist):
        migrated.append(factory_id)
        if factory_id == "factory-1":
            raise OSError("unavailable")

    with mock.patch.object(app_module, "get_profile_store", return_value=object()), \
         mock.patch.object(app_module, "FactoryService", FakeService), \
         mock.patch.object(app_module, "ensure_factory_configuration_v2", side_effect=migrate), \
         pytest.warns(RuntimeWarning, match="factory-1"):
        app_module.initialize_factory_configuration_v2(application)

    assert migrated == ["factory-1", "factory-2"]


def test_unexpected_programming_error_is_not_swallowed(tmp_path):
    application = configured_app(tmp_path)
    with mock.patch.object(app_module, "get_profile_store", return_value=object()), \
         mock.patch.object(app_module, "FactoryService", FakeService), \
         mock.patch.object(app_module, "ensure_factory_configuration_v2", side_effect=RuntimeError("bug")), \
         pytest.raises(RuntimeError, match="bug"):
        app_module.initialize_factory_configuration_v2(application)


def test_second_startup_initialization_is_idempotent(tmp_path):
    application = configured_app(tmp_path)
    data_root = tmp_path / "Data"
    factory_root = data_root / "Factories" / "op-factory-1"
    factory_root.mkdir(parents=True)
    (factory_root / "Factory_Data.json").write_text(json.dumps({"data": {
        "Subfield": ["Payroll"], "Cost": [0], "PercentageOfAll": [0],
    }}), encoding="utf-8")

    class OneFactoryService(FakeService):
        def list_factories(self):
            return FACTORIES[:1]

    statuses = []

    def migrate(factory_id, operational_key, persist):
        result = real_ensure(factory_id, operational_key, data_root=data_root, persist=persist)
        statuses.append(result["status"])
        return result

    with mock.patch.object(app_module, "get_profile_store", return_value=object()), \
         mock.patch.object(app_module, "FactoryService", OneFactoryService), \
         mock.patch.object(app_module, "ensure_factory_configuration_v2", side_effect=migrate):
        app_module.initialize_factory_configuration_v2(application)
        manifest = factory_root / "configuration" / "manifest.json"
        first_mtime = manifest.stat().st_mtime_ns
        app_module.initialize_factory_configuration_v2(application)
        assert manifest.stat().st_mtime_ns == first_mtime

    assert statuses == ["COMPLETED", "ALREADY_V2"]
