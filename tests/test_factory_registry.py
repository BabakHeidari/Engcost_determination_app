import json
from pathlib import Path
from unittest import mock

import pytest

from utils.factory_registry import discover_factories, populate_factory_registry
from utils.profile_store import ProfileDataStore
from utils.profile_view import build_profile_view_model


def write_sources(root):
    (root / "Overall").mkdir(parents=True)
    (root / "Factories" / "Alpha").mkdir(parents=True)
    (root / "Factories" / "Alpha Unit 1").mkdir()
    (root / "Overall" / "factories.json").write_text(json.dumps({
        "data": {"factory name": ["Alpha", "Beta", ""], "city": ["Tehran", "Qom", "Nowhere"]}
    }), encoding="utf-8")
    (root / "Factories" / "__metadata.json").write_text(json.dumps({
        "product_hierarchy": {"Alpha": {}, "Gamma": {}}
    }), encoding="utf-8")


def test_discovery_extracts_sources_deduplicates_exact_identity_and_keeps_ambiguity(tmp_path):
    write_sources(tmp_path)
    result = discover_factories(tmp_path)
    assert [item["id"] for item in result["factories"]] == ["Alpha", "Alpha Unit 1", "Beta", "Gamma"]
    alpha = next(item for item in result["factories"] if item["id"] == "Alpha")
    assert alpha["location"] == "Tehran"
    assert len(result["sources"]["Alpha"]) == 3
    assert len(result["missing_names"]) == 1
    assert result["missing_names"][0].endswith("Overall/factories.json")


def test_population_preserves_existing_factory_and_persists_new_records(tmp_path):
    data_root = tmp_path / "Data"
    write_sources(data_root)
    store = ProfileDataStore(tmp_path / "app_data.json")
    store.initialize()
    store.create_factory({"id": "Alpha", "code": "Alpha", "name": "Manually maintained", "is_active": False})
    result = populate_factory_registry(store, data_root)
    factories = store.list_factories()
    assert result["created_count"] == 3
    assert len(factories) == 4
    assert next(item for item in factories if item["id"] == "Alpha")["name"] == "Manually maintained"
    assert {item["id"] for item in store.list_active_factories()} == {"Alpha Unit 1", "Beta", "Gamma"}


def test_failed_population_preserves_previous_json_and_creates_backup(tmp_path):
    data_root = tmp_path / "Data"
    write_sources(data_root)
    path = tmp_path / "app_data.json"
    store = ProfileDataStore(path)
    store.initialize()
    before = path.read_bytes()
    with mock.patch("utils.profile_store.os.replace", side_effect=OSError("disk failure")):
        with pytest.raises(OSError):
            populate_factory_registry(store, data_root)
    assert path.read_bytes() == before
    assert list((tmp_path / "backups").glob("*.json"))


def test_repository_factory_sources_are_detected():
    result = discover_factories()
    assert [item["id"] for item in result["factories"]] == [
        "Arefi", "DinMohamadpour", "HajAmini", "Nasooz", "TajdidPazir"
    ]


def test_profile_view_exposes_only_safe_active_canonical_factories(tmp_path):
    store = ProfileDataStore(tmp_path / "app_data.json")
    store.initialize()
    store.create_factory({"id": "active", "code": "ACT", "name": "کارخانه فعال", "is_active": True, "source": {"private": True}})
    store.create_factory({"id": "inactive", "code": "OFF", "name": "کارخانه غیرفعال", "is_active": False})
    admin = store.create_user({
        "id": "admin", "username": "admin", "email": "admin@example.com",
        "full_name": "مدیر", "system_role": "IT_ADMIN", "job_title": "",
        "access_grants": [], "is_active": True, "password_hash": "hash",
    })
    model = build_profile_view_model(store, admin)
    assert model["factories"] == [{"id": "active", "code": "ACT", "name": "کارخانه فعال"}]
    assert "source" not in model["factories"][0]


def test_add_user_template_uses_server_registry_and_has_truthful_empty_state():
    template = Path("templates/profile/profile.html").read_text(encoding="utf-8")
    assert '{% for factory in profile.factories %}' in template
    assert 'value="{{ factory.id }}"' in template
    assert "{{ factory.name }} ({{ factory.code }})" in template
    assert "هیچ کارخانه‌ای در داده‌های سیستم ثبت نشده است." in template
    assert "FACTORIES =" not in template
