"""Exact prepared-tree inventory checks for successful and rejected Dashboard requests.

Isolation and V2/Profile preparation occur before each inventory baseline. These
proofs include directory timestamps and link targets, not only source contents.
Startup app imports belong to the separately isolated integration smoke.
"""

import hashlib
import os
from decimal import Decimal
import shutil
import stat

import pytest

from test_dashboard_cost_analysis import analysis, _bom, _client, _write
from test_dashboard_sensitivity import sensitivity, SELECTION, _change, _g2_fixture
from test_dashboard_release_numerics import ALL_SELECTION, LAB, VISUALS, lab
from utils.costing_engine import CostInputLoader
from utils.factory_service import FactoryService


FILTERS = "/api/dashboard/filter-options"
PARAMETERS = "/api/dashboard/sensitivity/parameters"
SCENARIO = "/api/dashboard/sensitivity/scenario"


def exact_inventory(root):
    """Track even transient file create/remove via parent directory mtimes."""
    paths = [root, *sorted(root.rglob("*"))]
    result = {}
    for path in paths:
        metadata = path.lstat()
        key = path.relative_to(root).as_posix()
        kind = "symlink" if stat.S_ISLNK(metadata.st_mode) else "directory" if path.is_dir() else "file"
        content = os.readlink(path) if kind == "symlink" else (
            hashlib.sha256(path.read_bytes()).hexdigest() if kind == "file" else None)
        result[key] = (kind, content, metadata.st_size, metadata.st_mtime_ns, stat.S_IMODE(metadata.st_mode))
    return result


def unchanged_request(env, request, expected):
    before = exact_inventory(env.root)
    response = request()
    assert response.status_code == expected
    assert exact_inventory(env.root) == before
    return response


def request(env, route, *, client=None, selection=None):
    client = client or env.client
    selection = selection or SELECTION
    if route == SCENARIO:
        return client.post(route, json={**selection, "overrides": []})
    if route == LAB:
        return client.post(route, json={**selection, "scenarios": [
            {"id": "A", "overrides": []}, {"id": "B", "overrides": []}], "experiment": None})
    if route == FILTERS:
        return client.get(route, query_string={key: value for key, value in selection.items() if key != "period"})
    return client.get(route, query_string=selection)


@pytest.mark.parametrize("route", [FILTERS, "/api/cost_analysis", VISUALS, PARAMETERS, SCENARIO, LAB])
def test_successful_dashboard_requests_preserve_exact_operational_bindings_v2_and_profile_tree(sensitivity, route):
    env = sensitivity
    # The inventory deliberately spans all these distinct prepared stores.
    assert env.binding.is_file() and env.factory.joinpath("configuration", "manifest.json").is_file()
    assert env.store.path.is_file()
    response = unchanged_request(env, lambda: request(env, route), 200)
    assert response.is_json


@pytest.mark.parametrize("route", [FILTERS, "/api/cost_analysis", VISUALS, PARAMETERS, SCENARIO, LAB])
@pytest.mark.parametrize("factory,status", [("factory-secret", 403), ("factory-inactive", 403), ("unknown", 404)])
def test_rejected_factory_requests_preserve_exact_inventory_and_precede_operational_reads(sensitivity, monkeypatch, route, factory, status):
    env = sensitivity
    monkeypatch.setattr(CostInputLoader, "snapshot_population",
                        lambda *args, **kwargs: pytest.fail("Denied request captured operational population"))
    monkeypatch.setattr(FactoryService, "operational_key",
                        lambda *args, **kwargs: pytest.fail("Denied request resolved an operational namespace"))
    response = unchanged_request(env, lambda: request(env, route, selection={**SELECTION, "factory": factory}), status)
    assert str(env.root) not in response.get_data(as_text=True)


@pytest.mark.parametrize("route", [FILTERS, "/api/cost_analysis", VISUALS, PARAMETERS, SCENARIO, LAB])
@pytest.mark.parametrize("user,status", [("cost-only-user", 403), (None, 302)])
def test_unauthorized_and_unauthenticated_requests_preserve_profile_and_inventory(sensitivity, route, user, status):
    env = sensitivity
    client = _client(env.app, user) if user else env.app.test_client()
    unchanged_request(env, lambda: request(env, route, client=client), status)


@pytest.mark.parametrize("route", ["/api/cost_analysis", VISUALS, PARAMETERS, SCENARIO, LAB])
@pytest.mark.parametrize("damage", ["missing_v2", "missing_binding", "invalid_materials", "invalid_bom"])
def test_missing_or_invalid_inputs_never_create_configuration_metadata_bindings_or_profile_artifacts(sensitivity, monkeypatch, route, damage):
    env = sensitivity
    if damage == "missing_v2":
        shutil.rmtree(env.factory / "configuration")
    elif damage == "missing_binding":
        env.binding.unlink()
    elif damage == "invalid_materials":
        (env.data / "Overall" / "material_costs.json").write_text("{broken", encoding="utf-8")
    else:
        _write(env.factory / "category" / "sub" / "A.json", _bom([1], loss=101))
    monkeypatch.setattr("utils.factory_configuration.ensure_factory_configuration_v2",
                        lambda *args, **kwargs: pytest.fail("Dashboard migrated V2 while reading"))
    monkeypatch.setattr("utils.legacy_costing_migration.ensure_canonical_costing_sources",
                        lambda *args, **kwargs: pytest.fail("Dashboard migrated legacy while reading"))
    response = unchanged_request(env, lambda: request(env, route), 422)
    assert response.is_json
    assert str(env.root) not in response.get_data(as_text=True)


@pytest.mark.parametrize("route", [SCENARIO, LAB])
def test_invalid_unauthorized_and_successful_what_if_overrides_never_write(sensitivity, route):
    env = sensitivity
    _g2_fixture(env)
    def post(overrides, client=None):
        if route == SCENARIO:
            return (client or env.client).post(route, json={**SELECTION, "overrides": overrides})
        return (client or env.client).post(route, json={**SELECTION, "scenarios": [
            {"id": "A", "overrides": overrides}, {"id": "B", "overrides": []}], "experiment": None})
    unchanged_request(env, lambda: post([_change("pool:Payroll", "2000")]), 200)
    unchanged_request(env, lambda: post([_change("pool:Payroll", "NaN")]), 400)
    unchanged_request(env, lambda: post([_change("pool:Payroll", "-1")]), 400)
    unchanged_request(env, lambda: post([_change("pool:Payroll", "2000")], _client(env.app, "general-only")), 403)
    unchanged_request(env, lambda: post([_change("pool:Payroll", "1")] * 65), 400)


def test_partial_visual_coverage_and_invalid_samples_preserve_exact_inventory(sensitivity):
    env = sensitivity
    _g2_fixture(env)
    _write(env.factory / "category" / "sub" / "B.json", _bom([1], loss=101))
    wrapper = unchanged_request(env, lambda: request(env, VISUALS, selection=ALL_SELECTION), 200).json
    assert wrapper["analysis"]["state"] == "PARTIAL"
    body = unchanged_request(env, lambda: lab(env, experiment={"type": "one_factor", "axes": [
        {"parameter_id": "pool:Payroll", "mode": "absolute", "values": ["-1", "0", "1000"]}]}), 200).json
    assert (body["experiment"]["valid_count"], body["experiment"]["invalid_count"]) == (2, 1)
    assert body["experiment"]["points"][0]["unit_cost"] is None


@pytest.mark.parametrize("route", [SCENARIO, LAB])
def test_duplicate_key_oversized_and_client_baseline_requests_leave_no_artifacts(sensitivity, route):
    env = sensitivity
    unchanged_request(env, lambda: env.client.post(route, data='{"factory":"a","factory":"b"}', content_type="application/json"), 400)
    unchanged_request(env, lambda: env.client.post(route, data=" " * 65537, content_type="application/json"), 413)
    body = {**SELECTION, "baseline": {"unit_cost": "0"}}
    body.update({"overrides": []} if route == SCENARIO else {"scenarios": [{"id": "A", "overrides": []}, {"id": "B", "overrides": []}]})
    unchanged_request(env, lambda: env.client.post(route, json=body), 400)


def test_pool_alias_preserves_link_metadata_and_rejects_conflicting_override_writes(sensitivity):
    env = sensitivity
    _g2_fixture(env)
    payroll = env.factory / "configuration" / "cost_pools" / "Payroll.json"
    alias = payroll.with_name("Overhead.json")
    alias.unlink()
    alias.symlink_to(payroll.name)
    body = unchanged_request(env, lambda: lab(env, a=[_change("pool:Payroll", "2000")]), 200).json
    assert Decimal(body["baseline"]["unit_cost"]) == 200
    assert Decimal(body["scenarios"][0]["result"]["unit_cost"]) == 400
    unchanged_request(env, lambda: lab(env, a=[_change("pool:Payroll", "2000"), _change("pool:Overhead", "3000")]), 400)
    unchanged_request(env, lambda: lab(env, experiment={"type": "two_factor", "axes": [
        {"parameter_id": parameter, "mode": "absolute", "values": ["1", "2"]}
        for parameter in ("pool:Payroll", "pool:Overhead")]}), 400)


def test_unexpected_engine_failure_preserves_prepared_tree_and_returns_safe_error(sensitivity, monkeypatch):
    env = sensitivity
    def fail(*args, **kwargs):
        raise RuntimeError(f"private failure at {env.root}/secret.json")
    monkeypatch.setattr(CostInputLoader, "load", fail)
    for route in ("/api/cost_analysis", VISUALS, PARAMETERS, SCENARIO, LAB):
        response = unchanged_request(env, lambda: request(env, route), 500)
        assert str(env.root) not in response.get_data(as_text=True)
        assert "private failure" not in response.get_data(as_text=True)
