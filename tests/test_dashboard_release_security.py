"""PR-10 real-route security regressions on the existing isolated V2 fixture.

No import of app.py, operational startup, source saves, or business JS adapters.
"""
import json

from flask import jsonify, request
import pytest

from test_dashboard_sensitivity import (
    analysis, sensitivity, SELECTION, SCENARIO, PARAMETERS, _client, _grant,
    _parameters,
)
from utils.costing_engine import CostInputError, CostInputLoader, CostState
from utils.dashboard_analysis import DashboardAnalysisService, empty_report
from utils.product_hierarchy_service import HierarchyMetadataError, ProductHierarchyService
from utils.profile_authorization import canonicalize_access_grants


FILTERS = "/api/dashboard/filter-options"
COST = "/api/cost_analysis"
VISUALS = "/api/dashboard/cost-analysis/visuals"
LAB = "/api/dashboard/sensitivity/visual-analysis"
ROUTES = ("/dashboard", FILTERS, COST, VISUALS, PARAMETERS, SCENARIO, LAB)


def _inventory(root):
    """Observe directory mtimes as well as names, file contents and file mtimes."""
    import hashlib
    return {
        path.relative_to(root).as_posix(): (
            "file" if path.is_file() else "directory", path.stat().st_mtime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
        ) for path in (root, *root.rglob("*"))
    }


def _payload(route, **changes):
    body = dict(SELECTION)
    if route == SCENARIO:
        body["overrides"] = []
    elif route == LAB:
        body["scenarios"] = [{"id": "A", "overrides": []}, {"id": "B", "overrides": []}]
        body["experiment"] = None
    elif route == FILTERS:
        body.pop("period", None)
    body.update(changes)
    return body


def _request(env, route, *, user=None, **changes):
    client = _client(env.app, user) if user else env.client
    payload = _payload(route, **changes)
    if route in {SCENARIO, LAB}:
        return client.post(route, json=payload)
    return client.get(route, query_string={} if route == "/dashboard" else payload)


def _keys(value):
    if isinstance(value, dict):
        return set(value).union(*(_keys(v) for v in value.values()))
    if isinstance(value, list):
        return set().union(*(_keys(v) for v in value))
    return set()


@pytest.fixture
def release(sensitivity, monkeypatch):
    env = sensitivity
    for user, grants in (
        ("source-general-without-dashboard", [_grant("general_parameters")]),
        ("source-factory-without-dashboard", [_grant("factory_parameters")]),
        ("wrong-dashboard-factory", [_grant("dashboard", "factory-secret")]),
        ("no-access", []),
        ("global-dashboard", [{"scope_type": "GLOBAL", "factory_id": None,
                               "module": "dashboard", "permissions": ["READ"]}]),
    ):
        env.store.create_user({
            "id": user, "username": user, "email": f"{user}@example.test",
            "full_name": user, "system_role": "USER", "job_title": "کاربر",
            "is_active": True, "must_change_password": False,
            "password_hash": "unused", "password_scheme": "werkzeug", "revision": 1,
            "access_grants": grants,
        })
    # Exercise real page admission/period service independently of unrelated
    # shared-shell endpoints; shipped Jinja rendering has its own browser suite.
    monkeypatch.setattr("modules.dashboard.routes.render_template",
                        lambda _template, **context: jsonify(context))
    env.app.add_url_rule("/change-password", endpoint="auth.change_password",
                         view_func=lambda: "change-password")
    return env


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("user,status", [
    ("dashboard-user", 200), ("general-only", 200), ("factory-only", 200),
    ("both-groups", 200), ("wrong-factory-group", 200),
    ("source-general-without-dashboard", 403), ("source-factory-without-dashboard", 403),
    ("cost-only-user", 403), ("no-access", 403),
    ("admin", 200), ("finance-admin", 200), ("global-dashboard", 403),
])
def test_page_and_every_action_keep_exact_dashboard_admission(release, route, user, status):
    before = _inventory(release.root)
    response = _request(release, route, user=user)
    assert response.status_code == status
    if status == 200 and route == "/dashboard":
        ids = {factory["id"] for factory in response.json["filter_options"]["factories"]}
        assert "factory-inactive" not in ids
        if user not in {"admin", "finance-admin", "global-dashboard"}:
            assert ids == {SELECTION["factory"]}
    assert _inventory(release.root) == before


@pytest.mark.parametrize("route", ROUTES)
def test_a_different_dashboard_factory_only_admits_its_own_page_context(release, route):
    before = _inventory(release.root)
    response = _request(release, route, user="wrong-dashboard-factory")
    assert response.status_code == (200 if route == "/dashboard" else 403)
    if route == "/dashboard":
        assert {f["id"] for f in response.json["filter_options"]["factories"]} == {"factory-secret"}
    assert _inventory(release.root) == before


@pytest.mark.parametrize("route", ROUTES[1:])
@pytest.mark.parametrize("factory,status", [
    ("factory-secret", 403), ("factory-inactive", 403), ("forged-factory", 404),
    ("legacy-folder", 404),
])
def test_factory_denial_precedes_any_operational_lookup(release, monkeypatch, route, factory, status):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Rejected factory reached operational inputs")
    monkeypatch.setattr(CostInputLoader, "snapshot_population", forbidden)
    monkeypatch.setattr(ProductHierarchyService, "options", forbidden)
    before = _inventory(release.root)
    response = _request(release, route, factory=factory)
    assert response.status_code == status
    assert _inventory(release.root) == before


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("failure", ["logout", "inactive", "expired", "password-change", "revoked"])
def test_session_and_current_dashboard_grants_are_rechecked(release, route, failure):
    client = _client(release.app, "both-groups")
    if failure == "logout":
        with client.session_transaction() as session:
            session.clear()
    elif failure == "expired":
        with client.session_transaction() as session:
            session["user_id"] = "missing-user"
    else:
        release.store.update_user("both-groups", {
            "inactive": {"is_active": False},
            "password-change": {"must_change_password": True},
            "revoked": {"access_grants": canonicalize_access_grants(
                [_grant("general_parameters"), _grant("factory_parameters")],
                [SELECTION["factory"], "factory-secret", "factory-inactive"])},
        }[failure])
    before = _inventory(release.root)
    payload = _payload(route)
    response = (client.post(route, json=payload) if route in {SCENARIO, LAB}
                else client.get(route, query_string={} if route == "/dashboard" else payload))
    assert response.status_code == (403 if failure == "revoked" else 302)
    if response.status_code == 302:
        assert response.location.endswith("/change-password" if failure == "password-change" else "/login")
    assert _inventory(release.root) == before


def test_filter_options_uses_the_configured_isolated_operational_root(release):
    response = _request(release, FILTERS)
    assert response.status_code == 200
    assert response.json["selection"] == {k: SELECTION[k] for k in ("category", "subcategory", "product")}
    assert {item["label"] for item in response.json["options"]["products"]} == {"A", "B"}


@pytest.mark.parametrize("query", [
    [("factory", SELECTION["factory"]), ("factory", "factory-secret")],
    [("factory", SELECTION["factory"]), ("source_path", "/private")],
    [("factory", "")], [("factory", "__ALL__")], [("factory", " factory-canonical")],
    [("factory", SELECTION["factory"]), ("category", "")],
    [("factory", SELECTION["factory"]), ("category", "category\x7f")],
    [("factory", SELECTION["factory"]), ("product", "x" * 2049)],
])
def test_filter_query_ambiguity_and_controls_fail_before_hierarchy(release, monkeypatch, query):
    monkeypatch.setattr(ProductHierarchyService, "options",
                        lambda *_a, **_k: pytest.fail("Malformed query read hierarchy"))
    before = _inventory(release.root)
    response = release.client.get(FILTERS, query_string=query)
    assert response.status_code == 400 and response.json["state"] == "INVALID_SELECTION"
    assert _inventory(release.root) == before


@pytest.mark.parametrize("route", (COST, VISUALS))
def test_delete_control_character_is_rejected_in_cost_queries(release, monkeypatch, route):
    monkeypatch.setattr(CostInputLoader, "snapshot_population",
                        lambda *_a, **_k: pytest.fail("Malformed query opened inputs"))
    response = _request(release, route, category="category\x7f")
    body = response.json["analysis"] if route == VISUALS else response.json
    assert response.status_code == 400 and body["state"] == "INVALID_SELECTION"


@pytest.mark.parametrize("route", (SCENARIO, LAB))
@pytest.mark.parametrize("termination", [True, False])
def test_missing_length_bodies_are_bounded_and_fail_closed(release, route, termination):
    @release.app.before_request
    def lengthless_wsgi_body():
        request.environ.pop("CONTENT_LENGTH", None)
        if termination:
            request.environ["wsgi.input_terminated"] = True
        else:
            request.environ.pop("wsgi.input_terminated", None)
    raw = json.dumps(_payload(route)).encode()
    before = _inventory(release.root)
    response = release.client.post(route, data=raw, content_type="application/json")
    assert response.status_code == (200 if termination else 400)
    assert _inventory(release.root) == before


@pytest.mark.parametrize("route", (SCENARIO, LAB))
@pytest.mark.parametrize("limit", [65536, 1024])
@pytest.mark.parametrize("extra", [0, 1, 32768])
def test_chunked_valid_json_prefix_cannot_hide_bytes_beyond_either_limit(release, route, limit, extra):
    release.app.config["MAX_CONTENT_LENGTH"] = limit
    @release.app.before_request
    def chunked_wsgi_body():
        request.environ.pop("CONTENT_LENGTH", None)
        request.environ["wsgi.input_terminated"] = True
    raw = json.dumps(_payload(route)).encode()
    raw += b" " * (limit + extra - len(raw))
    before = _inventory(release.root)
    response = release.client.post(route, data=raw, content_type="application/json")
    assert response.status_code == (200 if extra == 0 else 413)
    if extra:
        assert response.json["issues"][0]["code"] == "PAYLOAD_TOO_LARGE"
    assert _inventory(release.root) == before


@pytest.mark.parametrize("route", (SCENARIO, LAB))
def test_terminated_stream_limit_is_enforced_with_a_zero_length_hint(release, route):
    @release.app.before_request
    def zero_length_hint():
        request.environ["CONTENT_LENGTH"] = "0"
        request.environ["wsgi.input_terminated"] = True
    raw = json.dumps(_payload(route)).encode()
    raw += b" " * (65537 - len(raw))
    before = _inventory(release.root)
    response = release.client.post(route, data=raw, content_type="application/json")
    assert response.status_code == 413 and response.json["issues"][0]["code"] == "PAYLOAD_TOO_LARGE"
    assert _inventory(release.root) == before


@pytest.mark.parametrize("route", (SCENARIO, LAB))
@pytest.mark.parametrize("missing_length", [False, True])
def test_cached_middleware_body_respects_a_later_stricter_per_request_limit(release, route, missing_length):
    @release.app.before_request
    def inspect_then_apply_limit():
        if request.method == "POST":
            assert request.get_json()["factory"] == SELECTION["factory"]
            request.max_content_length = 128
            if missing_length:
                request.environ.pop("CONTENT_LENGTH", None)
                request.environ["wsgi.input_terminated"] = True
    before = _inventory(release.root)
    response = _request(release, route)
    assert response.status_code == 413 and response.json["issues"][0]["code"] == "PAYLOAD_TOO_LARGE"
    assert _inventory(release.root) == before


@pytest.mark.parametrize("route", (SCENARIO, LAB))
def test_existing_post_protection_also_applies_to_the_lab(release, route):
    from flask import abort
    @release.app.before_request
    def protected_post():
        if request.method == "POST" and request.headers.get("X-Test-CSRF") != "valid":
            abort(403)
    assert _request(release, route).status_code == 403
    response = release.client.post(route, json=_payload(route), headers={"X-Test-CSRF": "valid"})
    assert response.status_code == 200


@pytest.mark.parametrize("kind", [None, [], {}, 1, True])
def test_malformed_experiment_type_is_a_safe_400_before_capture(release, monkeypatch, kind):
    monkeypatch.setattr(CostInputLoader, "snapshot_population",
                        lambda *_a, **_k: pytest.fail("Malformed experiment opened sources"))
    response = _request(release, LAB, experiment={"type": kind, "axes": []})
    assert response.status_code == 400 and response.json["state"] == "INVALID_REQUEST"


@pytest.mark.parametrize("route", (SCENARIO, LAB))
@pytest.mark.parametrize("fragment", [
    '"injected":NaN', '"injected":Infinity', '"injected":-Infinity',
    '"factory":"factory-secret"', '"comparisons":{"B_minus_A":"forged"}',
    '"source_mapping":{"path":"/private"}',
])
def test_duplicate_nonfinite_and_tampered_json_never_reaches_sources(release, monkeypatch, route, fragment):
    monkeypatch.setattr(CostInputLoader, "snapshot_population",
                        lambda *_a, **_k: pytest.fail("Malformed JSON opened sources"))
    raw = json.dumps(_payload(route))[:-1] + "," + fragment + "}"
    before = _inventory(release.root)
    response = release.client.post(route, data=raw, content_type="application/json")
    assert response.status_code == 400 and response.json["state"] == "INVALID_REQUEST"
    assert "forged" not in response.get_data(as_text=True) and "/private" not in response.get_data(as_text=True)
    assert _inventory(release.root) == before


@pytest.mark.parametrize("group,prefix", [("general_parameters", "material:"), ("factory_parameters", "prediction:")])
def test_lab_cannot_reuse_a_parameter_id_after_group_revocation(release, monkeypatch, group, prefix):
    registry = _parameters(release).json
    parameter = next(p["parameter_id"] for p in registry["parameters"] if p["parameter_id"].startswith(prefix))
    release.store.update_user("both-groups", {"access_grants": [
        _grant("dashboard"), _grant("factory_parameters" if group == "general_parameters" else "general_parameters"),
    ]})
    monkeypatch.setattr(CostInputLoader, "snapshot_population",
                        lambda *_a, **_k: pytest.fail("Revoked source group opened inputs"))
    before = _inventory(release.root)
    body = _payload(LAB)
    body["scenarios"][0]["overrides"] = [{"parameter_id": parameter, "mode": "absolute", "value": "10"}]
    response = release.client.post(LAB, json=body)
    assert response.status_code == 403 and response.json["state"] == "FORBIDDEN"
    assert {"baseline_value", "final_value", "raw_factory_pool", "prediction"}.isdisjoint(_keys(response.json))
    assert _inventory(release.root) == before


@pytest.mark.parametrize("route", (PARAMETERS, SCENARIO, LAB))
@pytest.mark.parametrize("user,general,factory", [
    ("dashboard-user", False, False), ("general-only", True, False),
    ("factory-only", False, True), ("wrong-factory-group", False, False),
    ("both-groups", True, True), ("admin", True, True), ("finance-admin", True, True),
])
def test_all_sensitivity_envelopes_redact_nested_source_inputs(release, route, user, general, factory):
    response = _request(release, route, user=user)
    assert response.status_code == 200
    body = response.json
    assert body["permissions"] == {"general_parameters": general, "factory_parameters": factory}
    assert {p["group"] for p in body["parameters"]} == {
        group for group, enabled in body["permissions"].items() if enabled
    }
    keys = _keys(body)
    assert {"unit_price", "fx_rate", "historical_cost_in_rial", "source_path"}.isdisjoint(keys)
    if not factory:
        assert {"prediction", "raw_factory_pool", "adjusted_category_pool", "category_prediction_total", "modeled_minus_raw"}.isdisjoint(keys)
    sources = {source["source"] for source in body["source_lineage"]}
    if not general:
        assert "materials" not in sources
    if not factory:
        assert not sources.intersection({"configuration", "weights", "predictions"})
        assert not any(source.startswith("pool:") for source in sources)


@pytest.mark.parametrize("route", (COST, VISUALS))
@pytest.mark.parametrize("failure", ["typed", "report"])
def test_calculation_error_keeps_500_in_both_analysis_envelopes(release, monkeypatch, route, failure):
    def fail(*_args, **_kwargs):
        if failure == "typed":
            raise CostInputError(CostState.CALCULATION_ERROR, "CALCULATION_FAILED", "/private internal secret")
        return empty_report("CALCULATION_ERROR")
    monkeypatch.setattr(DashboardAnalysisService, "analyze", fail)
    response = _request(release, route)
    assert response.status_code == 500
    body = response.json["analysis"] if route == VISUALS else response.json
    assert body["state"] == "CALCULATION_ERROR"
    assert "internal secret" not in response.get_data(as_text=True)


@pytest.mark.parametrize("failure,status,state", [("hierarchy", 503, "UNAVAILABLE"), ("unexpected", 500, "CALCULATION_ERROR")])
def test_filter_failures_are_typed_and_never_echo_exception_details(release, monkeypatch, failure, status, state):
    def fail(*_args, **_kwargs):
        error = HierarchyMetadataError if failure == "hierarchy" else RuntimeError
        raise error(f"{release.root}/private internal secret")
    monkeypatch.setattr(ProductHierarchyService, "options", fail)
    before = _inventory(release.root)
    response = _request(release, FILTERS)
    assert response.status_code == status and response.json["state"] == state
    assert "internal secret" not in response.get_data(as_text=True)
    assert str(release.root) not in response.get_data(as_text=True)
    assert _inventory(release.root) == before
