"""Authorized, write-free period context for the Dashboard page bootstrap."""

import hashlib
import json
from types import SimpleNamespace

from flask import Flask
from jinja2 import DictLoader
import pytest

from utils.costing_engine import CostInputError, CostInputLoader
from utils.dashboard_periods import DashboardPeriodMetadata
from utils.factory_service import FactoryAccessDeniedError, FactoryService
from utils.profile_store import ProfileDataStore


def _binding(factory="allowed", identifier="P", **changes):
    return {"factory_id": factory, "period_id": identifier,
            "start": "2026-10-01", "end": "2026-12-31",
            "active": True, "approved": True, "status": "ACTIVE",
            "sources": ["materials", "bom"], **changes}


def _write(path, document):
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")


def _snapshot(root):
    return {path.relative_to(root).as_posix(): (
        hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns
    ) if path.is_file() else None for path in root.rglob("*")}


@pytest.fixture
def periods(tmp_path):
    # Standalone app avoids app.py's source initialization and migrations.
    from modules.dashboard.routes import dashboard_bp
    profiles = tmp_path / "profiles.json"
    bindings = tmp_path / "bindings.json"
    store = ProfileDataStore(profiles)
    store.initialize({})
    for identifier, active in (("allowed", True), ("secret", True), ("inactive", False)):
        store.create_factory({"id": identifier, "code": identifier, "name": identifier,
                              "is_active": active, "operational_key": f"folder-{identifier}"})
    store.create_user({
        "id": "dashboard-user", "username": "dashboard-user", "email": "user@example.test",
        "full_name": "کاربر", "system_role": "USER", "job_title": "کاربر",
        "is_active": True, "must_change_password": False,
        "password_hash": "unused", "password_scheme": "werkzeug", "revision": 1,
        "access_grants": [{"scope_type": "FACTORY", "factory_id": "allowed",
                           "module": "dashboard", "permissions": ["READ"]}],
    })
    _write(bindings, {"bindings": [_binding(), _binding("secret", "SECRET"),
                                   _binding("inactive", "OFF")]})
    app = Flask(__name__, instance_path=str(tmp_path / "instance"))
    app.config.update(TESTING=True, SECRET_KEY="period-tests", APP_DATA_FILE=str(profiles),
                      COSTING_DATA_ROOT=str(tmp_path / "Data"),
                      COSTING_PERIOD_BINDINGS_FILE=str(bindings))
    # Exercise the real authenticated route and Jinja bootstrap boundary while
    # keeping this metadata test independent of the application's shared shell.
    app.jinja_loader = DictLoader({"dashboard/dashboard.html": "{{ filter_options|tojson }}"})
    app.add_url_rule("/login", endpoint="auth.login", view_func=lambda: "login")
    app.register_blueprint(dashboard_bp)
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = "dashboard-user"
    service = FactoryService(store)
    return SimpleNamespace(app=app, client=client, root=tmp_path, bindings=bindings,
                           store=store, service=service, user=store.get_user_by_id("dashboard-user"))


def _metadata(periods):
    response = periods.client.get("/dashboard")
    assert response.status_code == 200
    return json.loads(response.get_data(as_text=True))


def test_page_bootstraps_only_authorized_public_binding_bounds_without_writes(periods):
    before = _snapshot(periods.root)
    bootstrap = _metadata(periods)
    assert [factory["id"] for factory in bootstrap["factories"]] == ["allowed"]
    assert set(bootstrap["periods_by_factory"]) == {"allowed"}
    assert bootstrap["periods_by_factory"]["allowed"] == {
        "options": [{"id": "P", "start": "2026-10-01", "end": "2026-12-31"}],
        "default_period_id": "P", "default_state": "OK", "issues": [],
    }
    encoded = json.dumps(bootstrap)
    assert "SECRET" not in encoded and "OFF" not in encoded
    assert str(periods.root) not in encoded and "folder-" not in encoded
    assert "sources" not in encoded and "approved_by" not in encoded
    assert _snapshot(periods.root) == before


def test_multiple_active_bindings_have_explicit_choices_without_inventing_a_default(periods):
    _write(periods.bindings, {"bindings": [_binding(identifier="Q"), _binding()]})
    before = _snapshot(periods.root)
    metadata = _metadata(periods)["periods_by_factory"]["allowed"]
    assert [period["id"] for period in metadata["options"]] == ["P", "Q"]
    assert metadata["default_period_id"] is None
    assert metadata["default_state"] == "MISSING_INPUT"
    assert metadata["issues"][0]["code"] == "PERIOD_NOT_BOUND"
    loader = CostInputLoader(periods.service, period_bindings_path=periods.bindings, read_only=True)
    with pytest.raises(CostInputError):
        loader.resolve_period("allowed")
    for option in metadata["options"]:
        resolved = loader.resolve_period("allowed", option["id"], start=option["start"], end=option["end"])
        assert resolved.period_id == option["id"]
    assert _snapshot(periods.root) == before


@pytest.mark.parametrize("changes", [
    {"active": False}, {"approved": False}, {"status": "DRAFT"},
    {"start": "invalid"}, {"start": "2027-01-01"}, {"sources": "not-an-array"},
])
def test_choices_use_the_existing_binding_lifecycle_and_validation(periods, changes):
    _write(periods.bindings, {"bindings": [_binding(**changes)]})
    before = _snapshot(periods.root)
    metadata = _metadata(periods)["periods_by_factory"]["allowed"]
    assert metadata["options"] == [] and metadata["default_period_id"] is None
    assert metadata["default_state"] in {"MISSING_INPUT", "INVALID_INPUT"}
    assert metadata["issues"]
    assert _snapshot(periods.root) == before


def test_duplicate_ids_are_not_offered_and_system_initialization_binding_is_allowed(periods):
    _write(periods.bindings, {"bindings": [_binding(), _binding()]})
    assert _metadata(periods)["periods_by_factory"]["allowed"]["options"] == []
    _write(periods.bindings, {"bindings": [_binding(identifier="INITIAL",
        approved_by="SYSTEM_INITIALIZATION", approval_type="SYSTEM_INITIALIZATION")]})
    metadata = _metadata(periods)["periods_by_factory"]["allowed"]
    assert metadata["default_period_id"] == "INITIAL"
    assert metadata["options"][0]["id"] == "INITIAL"


@pytest.mark.parametrize("failure", ["missing", "broken-json", "invalid-schema", "invalid-record"])
def test_unavailable_binding_context_is_safe_and_never_initializes_sources(periods, failure):
    if failure == "missing":
        periods.bindings.unlink()
    elif failure == "broken-json":
        periods.bindings.write_text("{not-json", encoding="utf-8")
    elif failure == "invalid-schema":
        _write(periods.bindings, {"bindings": {}})
    else:
        _write(periods.bindings, {"bindings": [None]})
    before = _snapshot(periods.root)
    metadata = _metadata(periods)["periods_by_factory"]["allowed"]
    assert metadata["options"] == [] and metadata["default_period_id"] is None
    assert metadata["default_state"] in {"MISSING_INPUT", "INVALID_INPUT"}
    assert metadata["issues"]
    assert str(periods.root) not in json.dumps(metadata)
    assert _snapshot(periods.root) == before


def test_helper_authorizes_before_any_binding_read(periods, monkeypatch):
    metadata = DashboardPeriodMetadata(periods.service, period_bindings_path=periods.bindings)
    monkeypatch.setattr(metadata.loader, "_read", lambda *_: pytest.fail("unauthorized binding lookup"))
    with pytest.raises(FactoryAccessDeniedError):
        metadata.for_factory("secret", periods.user)


def test_binding_document_is_snapshotted_across_factory_choices(periods, monkeypatch):
    metadata = DashboardPeriodMetadata(periods.service, period_bindings_path=periods.bindings)
    read = metadata.loader._read
    changed = False

    def mutate_after_read(path):
        nonlocal changed
        result = read(path)
        if not changed:
            changed = True
            _write(periods.bindings, {"bindings": [_binding(identifier="REPLACEMENT")]})
        return result

    monkeypatch.setattr(metadata.loader, "_read", mutate_after_read)
    result = metadata.for_factory("allowed", periods.user)
    assert result["default_period_id"] == "P"
    assert [option["id"] for option in result["options"]] == ["P"]
