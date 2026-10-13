"""Legacy PR-09 Chromium compatibility checks of the authorized PR-08 API.

The PR-07 Flask/browser harness and PR-08 V2 fixture are deliberately reused:
no app.py import, operational Data access, source-save route, or mock costing
formula is needed. Every test retains fixture inventory/SHA-256/mtime evidence.
Explicit test-only caller adapters preserve the pre-PR09A contract; the PR-10
release suite validates the shipped assets and visual-analysis endpoints.
Optional DASHBOARD_UI_EVIDENCE_DIR captures actual desktop/mobile views.
"""

import csv
import io
import json
import os
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

import pytest

from test_dashboard_cost_analysis import (
    FACTORY, OPERATIONAL, _bom, _client, _reference, _set_pools, _snapshot, _write,
)
from test_dashboard_frontend import (
    browser, ui, _analyze as _analyze_cost, _select as _select_cost,
    _clipboard, _install_pending_fetch, _real_echarts, _resolve,
)
from test_dashboard_sensitivity import (
    PARAMETERS, SCENARIO, SELECTION, analysis, sensitivity,
    _change, _g2_fixture, _material_fixture, _parameter, _parameters, _scenario,
)
from utils.costing_engine import CostInputLoader


@pytest.fixture
def sui(sensitivity, ui):
    """The same authenticated Flask server, plus strict no-write evidence."""
    page = ui["page"]
    page.set_default_timeout(8000)
    requests = []
    page.on("request", lambda request: requests.append((request.method, request.url)))
    # Cached third-party presentation assets make screenshots reproducible
    # while scripts remain offline unless the real-ECharts test opts in.
    asset_root = Path(os.environ.get("DASHBOARD_BOOTSTRAP_PATH", "/nonexistent")).parent
    for url, relative, mime in (
        ("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css",
         "fontawesome/all.min.css", "text/css"),
        ("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/webfonts/fa-solid-900.woff2",
         "fontawesome/fa-solid-900.woff2", "font/woff2"),
    ):
        path = asset_root / relative
        if path.is_file():
            page.route(url, lambda route, request, path=path, mime=mime:
                       route.fulfill(content_type=mime, body=path.read_bytes()))
    page.reload(wait_until="networkidle")
    ui["requests"] = requests
    expected = [_snapshot(sensitivity.root)]
    # Tests intentionally change isolated sources/grants to exercise freshness
    # and revocation, then renew the checkpoint before browser API interactions.
    ui["checkpoint"] = lambda: expected.__setitem__(0, _snapshot(sensitivity.root))
    yield ui
    assert _snapshot(sensitivity.root) == expected[0], "Browser/API wrote fixture sources or artifacts"
    assert all(method in {"GET", "HEAD"} or urlparse(url).path == SCENARIO
               for method, url in requests), "Browser sent a source-save request"
    assert not ui["errors"], ui["errors"]


def _activate(page):
    page.locator("#sensitivity-tab").press("Enter")
    assert page.locator("#sensitivity-tab").get_attribute("aria-selected") == "true"
    assert page.locator("#sensitivity").is_visible()


def _choose(ui, *, category="category", subcategory="sub", product=None, period="P"):
    page = ui["page"]
    _activate(page)
    page.select_option("#sens-factory", FACTORY)
    page.wait_for_function("!document.querySelector('#sens-category').disabled")
    assert page.locator("#sens-category").input_value() == ""
    page.select_option("#sens-category", category)
    page.wait_for_function("!document.querySelector('#sens-subcategory').disabled")
    assert page.locator("#sens-subcategory").input_value() == ""
    page.select_option("#sens-subcategory", subcategory)
    page.wait_for_function("!document.querySelector('#sens-product').disabled")
    assert page.locator("#sens-product").input_value() == ""
    page.select_option("#sens-product", product or _reference(category, subcategory, "A"))
    page.wait_for_function("Array.from(document.querySelector('#sens-period').options).some(o => o.value === 'P')")
    assert page.locator("#sens-period").input_value() == ""
    assert page.locator("#sens-run").is_disabled()
    page.select_option("#sens-period", period)
    page.wait_for_function("document.querySelector('#sens-status').dataset.state !== 'LOADING' && !document.querySelector('#sens-refresh').disabled")
    page.wait_for_function("document.querySelector('#sens-baseline').textContent.length > 0")


def _row(page, parameter):
    return page.locator("#sens-draft .sens-draft-item").filter(
        has=page.locator(f"[data-remove-parameter='{parameter}']"))


def _catalog_open(page):
    catalog = page.locator("#sens-catalog")
    if catalog.count() and catalog.get_attribute("open") is None:
        catalog.locator(":scope > summary").press("Enter")


def _add(page, parameter, value, mode="absolute"):
    _catalog_open(page)
    page.locator(f"[data-add-parameter='{parameter}']").press("Enter")
    row = _row(page, parameter)
    row.locator("[data-override-mode]").select_option(mode)
    row.locator("[data-override-value]").fill(value)
    return row


def _run(ui, status=200):
    page = ui["page"]
    assert page.locator("#sens-run").is_enabled()
    with page.expect_response(lambda response: urlparse(response.url).path == SCENARIO) as pending:
        page.locator("#sens-run").press("Enter")
    response = pending.value
    assert response.status == status
    page.wait_for_function("document.querySelector('#sens-status').dataset.state !== 'LOADING'")
    assert page.locator("#sens-status").get_attribute("data-http-status") == str(status)
    return response.json(), response.request.post_data_json


def _metric(page, metric, container="#sens-results"):
    return page.locator(f"{container} [data-sensitivity-metric='{metric}'] [data-raw]").get_attribute("data-raw")


def _baseline(page):
    container = "#sens-baseline" if page.locator("#sens-baseline [data-sensitivity-metric='baseline-unit-cost']").count() else "#sens-results"
    return _metric(page, "baseline-unit-cost", container)


def _assert_costs(page, baseline, scenario):
    assert Decimal(_metric(page, "baseline-unit-cost")) == Decimal(baseline)
    assert Decimal(_metric(page, "scenario-unit-cost")) == Decimal(scenario)


def _csv(ui):
    page = ui["page"]
    before = len(ui["requests"])
    with page.expect_download() as pending:
        page.locator("#sens-export").press("Enter")
    raw = Path(pending.value.path()).read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert len(ui["requests"]) == before, "CSV export fetched a new baseline or costing result"
    return raw, list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))


def _evidence(ui, name, mobile=False):
    destination = os.environ.get("DASHBOARD_UI_EVIDENCE_DIR")
    if not destination:
        return
    page = ui["page"]
    if mobile:
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_function("document.querySelector('#mainSidebar').getBoundingClientRect().left >= window.innerWidth - 1")
    path = Path(destination)
    path.mkdir(parents=True, exist_ok=True)
    # A full-page capture otherwise places position:sticky UI at the old scroll
    # offset, making the persistent notice appear midway through the document.
    page.evaluate("window.scrollTo({top:0, left:0, behavior:'instant'})")
    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
    page.screenshot(path=str(path / f"{name}{'-mobile' if mobile else '-desktop'}.png"), full_page=True)


def _login(ui, user):
    cookie = _client(ui["analysis"].app, user).get_cookie("session")
    ui["context"].add_cookies([{"name": "session", "value": cookie.value, "url": ui["base"]}])
    ui["page"].reload(wait_until="networkidle")


def test_exact_selection_material_golden_csv_fallback_and_reset_without_fetch(sui):
    page, env = sui["page"], sui["analysis"]
    _material_fixture(env)
    sui["checkpoint"]()
    parameter = _parameter(env, "material:")
    _activate(page)
    assert page.locator("#sens-run").is_disabled()
    for name in ("factory", "category", "subcategory", "product"):
        assert page.locator(f"#sens-{name} option[value='__ALL__']").count() == 0
    assert "این تغییرات فقط شبیه‌سازی‌اند" in page.locator("#sens-notice").inner_text()
    _choose(sui)
    assert Decimal(_baseline(page)) == 140
    assert "۱۴۰۵" in page.locator("#sens-period").inner_text()
    _add(page, parameter, "۱۰", "percent_change")
    body, sent = _run(sui)
    assert sent == {**SELECTION, "overrides": [_change(parameter, "10", "percent_change")]}
    _assert_costs(page, 140, 154)
    assert _metric(page, "delta-amount") == body["delta"]["amount"]
    assert page.locator("#sens-results [data-sensitivity-table='drivers'] tbody tr").count() == 7
    assert page.evaluate("typeof window.echarts") == "undefined"
    assert page.locator("#sens-results [data-sensitivity-chart='drivers']").count() == 1
    assert "نمودار در دسترس نیست" in page.locator("#sens-results").inner_text()
    canonical = env.client.get("/api/cost_analysis", query_string=SELECTION).get_json()["detail_rows"][0]
    assert body["baseline"]["unit_cost"] == canonical["unit_cost"]
    raw, rows = _csv(sui)
    for exact in (b"140", b"154", b"14", b"2026-10-01", b"2026-12-31"):
        assert exact in raw
    assert rows and b'"non_persistent"' in raw and b'"HYPOTHETICAL_OVERRIDE"' in raw
    assert str(env.root).encode() not in raw
    before = len(sui["requests"])
    page.locator("#sens-reset").press("Enter")
    assert len(sui["requests"]) == before
    assert page.locator("#sens-draft .sens-draft-item").count() == 0
    assert page.locator("#sens-comparison").is_hidden()
    assert page.locator("#sens-export").is_disabled()
    assert Decimal(_baseline(page)) == 140
    empty, sent = _run(sui)
    assert sent["overrides"] == [] and empty["baseline"] == empty["scenario"]


@pytest.mark.parametrize("prefix,value,unit,projected", [
    ("prediction:", "۳۰", "50", "1500"),
    ("category_share:", "۲۵", "200", "2000"),
])
def test_prediction_and_share_established_goldens(sui, prefix, value, unit, projected):
    page, env = sui["page"], sui["analysis"]
    _g2_fixture(env)
    sui["checkpoint"]()
    parameter = _parameter(env, prefix)
    _choose(sui)
    _add(page, parameter, value)
    body, sent = _run(sui)
    _assert_costs(page, "100", unit)
    assert Decimal(_metric(page, "baseline-projected-cost")) == 1000
    assert Decimal(_metric(page, "scenario-projected-cost")) == Decimal(projected)
    assert sent["overrides"][0]["value"] in {"25", "30"}
    assert _metric(page, "scenario-projected-cost") == body["scenario"]["projected_cost"]


def test_same_name_composite_identity_explicit_period_and_unsupported_mapping(sui):
    page, env = sui["page"], sui["analysis"]
    _material_fixture(env)
    _write(env.factory / "category" / "other" / "A.json", _bom([2], loss=0, recycling=0))
    _write(env.data / "Factories" / "__metadata.json", {"product_hierarchy": {
        OPERATIONAL: {"category": ["sub", "other"]},
    }})
    sui["checkpoint"]()
    _choose(sui, subcategory="other")
    assert page.locator("#sens-product").input_value() == _reference("category", "other", "A")
    body, sent = _run(sui)
    assert sent["period"] == "P"
    assert sent["product"] != SELECTION["product"]
    assert body["identity"]["subcategory"] == "other"
    assert Decimal(_metric(page, "baseline-unit-cost")) == 200
    assert page.locator("[data-add-parameter^='prediction:']").count() == 0
    _catalog_open(page)
    page.locator("#sens-unsupported summary").press("Enter")
    assert page.locator("#sens-unsupported").inner_text().strip()
    page.locator("#cost-tab").press("Enter")
    assert page.locator("#cost").is_visible()
    _select_cost(page)
    assert page.locator("#productSelect option[value='__ALL__']").count() == 1
    _activate(page)
    assert page.locator("#sens-product").input_value() == sent["product"]


@pytest.mark.parametrize("user,groups", [
    ("general-only", {"general_parameters"}),
    ("factory-only", {"factory_parameters"}),
    ("both-groups", {"general_parameters", "factory_parameters"}),
    ("dashboard-user", set()), ("wrong-factory-group", set()),
])
def test_real_permission_matrix_renders_only_authorized_registry(sui, user, groups):
    page, env = sui["page"], sui["analysis"]
    _login(sui, user)
    _choose(sui)
    body, sent = _run(sui)
    assert sent["overrides"] == []
    authorized = {entry["parameter_id"] for entry in body["parameters"]}
    dom = set(page.locator("[data-add-parameter]").evaluate_all(
        "nodes => nodes.map(node => node.dataset.addParameter)"))
    assert dom == authorized
    assert {entry["group"] for entry in body["parameters"]} == groups
    _, csv_rows = _csv(sui)
    exported = [dict(zip(csv_rows[0], row)) for row in csv_rows[1:]]
    if "factory_parameters" not in groups:
        assert page.locator("[data-add-parameter^='prediction:']").count() == 0
        assert page.locator("[data-add-parameter^='category_share:']").count() == 0
        for field in ("prediction", "category_share", "raw_factory_pool", "adjusted_category_pool",
                      "category_prediction_total", "modeled_minus_raw"):
            assert all(not row.get(field) for row in exported), field
    if "general_parameters" not in groups:
        for field in ("unit_price", "fx_rate", "usage", "loss_percentage", "recyclability_percentage",
                      "gross_cost_in_rial", "adjustment_factor"):
            assert all(not row.get(field) for row in exported), field
    if user == "dashboard-user":
        _evidence(sui, "sensitivity-restricted")
        _evidence(sui, "sensitivity-restricted", mobile=True)


@pytest.mark.parametrize("group,prefix", [("general_parameters", "material:"),
                                          ("factory_parameters", "pool:Payroll")])
def test_revocation_between_get_post_clears_protected_draft_dom_and_popover(sui, group, prefix):
    page, env = sui["page"], sui["analysis"]
    _material_fixture(env)
    sui["checkpoint"]()
    parameter = _parameter(env, prefix)
    _choose(sui)
    _add(page, parameter, "1234567.891234")
    page.locator(f"[data-parameter-id='{parameter}'] [data-exact-trigger]").first.press("Enter")
    assert page.locator(".exact-popover").is_visible()
    user = env.store.get_user_by_id("both-groups")
    env.store.update_user("both-groups", {"access_grants": [
        grant for grant in user["access_grants"] if grant["module"] != group
    ]})
    sui["checkpoint"]()
    _run(sui, 403)
    assert page.locator("#sens-comparison").is_hidden()
    assert page.locator("#sens-export").is_disabled()
    assert page.locator("#sens-draft .sens-draft-item").count() == 0
    assert page.locator(f"[data-parameter-id='{parameter}']").count() == 0
    assert page.locator(".exact-popover").is_hidden()
    assert "1234567.891234" not in page.content()
    assert not page.locator(".exact-popover-value").inner_text().strip()
    assert not page.locator(".exact-popover-label").inner_text().strip()


def test_localized_numeric_grammar_zero_negative_and_exact_domain(sui):
    page, env = sui["page"], sui["analysis"]
    _material_fixture(env, usages=(1,))
    sui["checkpoint"]()
    parameter = _parameter(env, "material:")
    _choose(sui)
    row = _add(page, parameter, "١٢٣٫٤٥")
    body, sent = _run(sui)
    assert sent["overrides"][0]["value"] == "123.45"
    _assert_costs(page, 100, "123.45")
    assert page.locator(f"[data-add-parameter='{parameter}']").is_disabled()
    assert page.locator("#sens-draft .sens-draft-item").count() == 1
    for invalid in ("", "1e3", "NaN", "1,2,3", "12 kg", "1.2.3", "1" * 129, "-1"):
        before = len(sui["requests"])
        row.locator("[data-override-value]").fill(invalid)
        assert page.locator("#sens-run").is_disabled(), invalid
        assert page.locator("#sens-export").is_disabled()
        assert len(sui["requests"]) == before
    row.locator("[data-override-mode]").select_option("percent_change")
    row.locator("[data-override-value]").fill("−۱۰۰")
    body, sent = _run(sui)
    assert sent["overrides"][0]["value"] == "-100"
    assert Decimal(body["scenario"]["unit_cost"]) == 0
    assert "۰" in page.locator("#sens-results [data-sensitivity-metric='scenario-unit-cost']").inner_text()
    row.locator("[data-override-value]").fill("۰")
    _run(sui)
    _assert_costs(page, 100, 100)


def test_percentage_uses_baseline_and_server_final_constraints_preserve_baseline(sui):
    page, env = sui["page"], sui["analysis"]
    _g2_fixture(env)
    sui["checkpoint"]()
    share = _parameter(env, "category_share:")
    _choose(sui)
    row = _add(page, share, "10", "percent_change")
    body, _ = _run(sui)
    assert Decimal(body["effective_overrides"][0]["final_value"]) == 55
    row.locator("[data-override-value]").fill("101")
    assert page.locator("#sens-run").is_enabled()  # Percent is not an absolute share.
    invalid, _ = _run(sui, 400)
    assert invalid["baseline"]["state"] == "OK"
    assert Decimal(_baseline(page)) == 100
    assert page.locator("#sens-comparison").is_hidden()
    assert page.locator("#sens-export").is_disabled()
    row.locator("[data-override-mode]").select_option("absolute")
    row.locator("[data-override-value]").fill("100.0000000000000000000000000001")
    assert page.locator("#sens-run").is_disabled()
    row.locator("[data-override-value]").fill("0")
    assert page.locator("#sens-run").is_disabled()


def test_mathematical_zero_stays_editable_and_combined_changes_activate_it(sui):
    page, env = sui["page"], sui["analysis"]
    _material_fixture(env, price=0, currency="USD", usages=(1,))
    sui["checkpoint"]()
    registry = _parameters(env).get_json()
    material = next(e["parameter_id"] for e in registry["parameters"] if e["unit"] == "USD/kg")
    fx = next(e["parameter_id"] for e in registry["parameters"] if e["unit"] == "IRR/USD")
    assert next(e for e in registry["parameters"] if e["parameter_id"] == fx)["effect_state"] == "MATHEMATICAL_ZERO"
    _choose(sui)
    assert page.locator(f"[data-add-parameter='{fx}']").is_enabled()
    _add(page, material, "10")
    _add(page, fx, "100", "percent_change")
    body, sent = _run(sui)
    assert len(sent["overrides"]) == len(body["effective_overrides"]) == 2
    _assert_costs(page, 0, 100)
    assert body["delta"]["percentage"] is None
    percentage = page.locator("#sens-results [data-sensitivity-metric='delta-percentage']")
    assert percentage.locator("[data-raw]").count() == 0
    assert "قابل اعمال نیست" in percentage.inner_text()
    assert page.locator("#sens-results .sens-technical").get_attribute("open") is None
    _evidence(sui, "sensitivity-zero")
    _evidence(sui, "sensitivity-zero", mobile=True)


def test_post_freshness_renders_both_sides_and_effective_values_from_post(sui):
    page, env = sui["page"], sui["analysis"]
    _material_fixture(env)
    sui["checkpoint"]()
    material = _parameter(env, "material:")
    _choose(sui)
    assert Decimal(_baseline(page)) == 140
    _add(page, material, "10", "percent_change")
    path = env.data / "Overall" / "material_costs.json"
    source = json.loads(path.read_text())
    source["data"]["cost_per_unit_in_currency"][0] = 1000
    _write(path, source)
    sui["checkpoint"]()
    body, sent = _run(sui)
    assert set(sent) == {*SELECTION, "overrides"}
    _assert_costs(page, 1400, 1540)
    assert Decimal(_baseline(page)) == 1400
    assert Decimal(body["effective_overrides"][0]["baseline_value"]) == 1000
    assert "خط" in page.locator("#sens-status").inner_text()
    raw, _ = _csv(sui)
    assert b"1400" in raw and b"1540" in raw and b"1100" in raw
    before = len(sui["requests"])
    page.locator("#sens-reset").press("Enter")
    assert len(sui["requests"]) == before
    assert Decimal(_baseline(page)) == 1400


@pytest.mark.parametrize("action", ["edit", "remove", "reset", "selection"])
def test_late_scenario_after_revision_or_scope_change_is_ignored(sui, action):
    page, env = sui["page"], sui["analysis"]
    _material_fixture(env)
    sui["checkpoint"]()
    parameter = _parameter(env, "material:")
    accepted = _scenario(env, [_change(parameter, "10", "percent_change")]).get_json()
    _choose(sui)
    row = _add(page, parameter, "10", "percent_change")
    _install_pending_fetch(page, SCENARIO)
    page.locator("#sens-run").press("Enter")
    page.wait_for_function("window.testPending.length === 1")
    assert page.locator("#sens-run").is_disabled()
    page.locator("#sens-run").evaluate("node => node.click()")
    assert page.evaluate("window.testPending.length") == 1
    if action == "edit":
        row.locator("[data-override-value]").fill("20")
    elif action == "remove":
        row.locator("[data-remove-parameter]").press("Enter")
    elif action == "reset":
        before = len(sui["requests"])
        page.locator("#sens-reset").press("Enter")
        assert len(sui["requests"]) == before
    else:
        page.select_option("#sens-product", _reference("category", "sub", "B"))
    assert page.evaluate("window.testPending[0].signal.aborted")
    _resolve(page, 0, accepted)
    page.wait_for_function("document.querySelector('#sens-status').dataset.state !== 'LOADING'")
    assert page.locator("#sens-comparison").is_hidden()
    assert page.locator("#sens-export").is_disabled()
    if action == "selection":
        current = _parameters(env, product=_reference("category", "sub", "B")).get_json()
        assert Decimal(_baseline(page)) == Decimal(current["baseline"]["unit_cost"])
    else:
        assert Decimal(_baseline(page)) == 140


def test_out_of_order_registry_response_cannot_restore_previous_configuration(sui):
    page, env = sui["page"], sui["analysis"]
    _material_fixture(env)
    sui["checkpoint"]()
    _choose(sui)
    original = _parameters(env).get_json()
    latest = _parameters(env, product=_reference("category", "sub", "B")).get_json()
    _install_pending_fetch(page, PARAMETERS)
    page.locator("#sens-refresh").press("Enter")
    page.wait_for_function("window.testPending.length === 1")
    page.select_option("#sens-product", _reference("category", "sub", "B"))
    page.wait_for_function("window.testPending.length === 2")
    _resolve(page, 1, latest)
    page.wait_for_function("document.querySelector('#sens-status').dataset.state !== 'LOADING'")
    _resolve(page, 0, original)
    page.wait_for_timeout(80)
    assert Decimal(_baseline(page)) == Decimal(latest["baseline"]["unit_cost"])
    assert page.locator("#sens-product").input_value() == _reference("category", "sub", "B")
    assert page.locator("#sens-comparison").is_hidden()


def test_distinct_source_alias_conflict_is_explained_without_old_comparison(sui):
    page, env = sui["page"], sui["analysis"]
    _g2_fixture(env)
    target = env.factory / "configuration" / "cost_pools" / "Payroll.json"
    alias = target.with_name("Overhead.json")
    alias.unlink()
    alias.symlink_to(target.name)
    sui["checkpoint"]()
    _choose(sui)
    _add(page, "pool:Payroll", "2000")
    _run(sui)
    _add(page, "pool:Overhead", "3000")
    assert page.locator("#sens-export").is_disabled()
    body, _ = _run(sui, 400)
    assert any(issue["code"] == "CONFLICTING_SOURCE_OVERRIDES" for issue in body["issues"])
    assert page.locator("#sens-comparison").is_hidden()
    assert page.locator("#sens-status").inner_text().strip()


def test_high_precision_copy_and_csv_keep_original_backend_decimal(sui):
    page, env = sui["page"], sui["analysis"]
    _material_fixture(env, usages=(1,))
    sui["checkpoint"]()
    material = _parameter(env, "material:")
    _choose(sui)
    value = "9007199254740993.1234567890123456789012345678"
    row = _add(page, material, value)
    body, sent = _run(sui)
    assert sent["overrides"][0]["value"] == value
    exact = body["scenario"]["unit_cost"]
    assert _metric(page, "scenario-unit-cost") == exact
    _clipboard(page)
    page.locator("#sens-results [data-sensitivity-metric='scenario-unit-cost'] [data-exact-trigger]").press("Enter")
    page.locator(".exact-copy").press("Enter")
    assert page.evaluate("window.copiedExact") == [exact]
    page.locator(".exact-close").press("Enter")
    raw, _ = _csv(sui)
    assert exact.encode() in raw and value.encode() in raw
    row.locator("[data-override-value]").fill("0.0000000000000000000000000001")
    _run(sui)
    assert "کمتر از ۰٫۰۱" in page.locator("#sens-results [data-sensitivity-metric='scenario-unit-cost']").inner_text()


def test_cost_analysis_clear_preserves_sensitivity_exact_copy_identifiers_and_source_units(sui):
    page, env = sui["page"], sui["analysis"]
    _choose(sui)
    _run(sui)
    page.locator("#cost-tab").press("Enter")
    _select_cost(page)
    _analyze_cost(page)
    page.fill("#startDate", "۱۴۰۵/۰۷/۱۰")
    _activate(page)
    _clipboard(page)
    value = page.locator("#sens-results [data-sensitivity-metric='scenario-unit-cost'] [data-exact-trigger]")
    expected = value.get_attribute("data-raw")
    value.press("Enter")
    page.locator(".exact-copy").press("Enter")
    assert page.evaluate("window.copiedExact") == [expected]
    page.locator(".exact-close").press("Enter")
    technical = page.locator("#sens-results .sens-technical")
    technical.locator("summary").press("Enter")
    identifier = technical.locator(".exact-identifier").first
    expected_identifier = identifier.get_attribute("data-raw")
    identifier.press("Enter")
    page.locator(".exact-copy").press("Enter")
    assert page.evaluate("window.copiedExact") == [expected, expected_identifier]
    page.locator(".exact-close").press("Enter")
    _catalog_open(page)
    source = page.locator("#sens-general-parameters [data-unit='USD/kg']").first
    source.press("Enter")
    assert "USD/kg" in page.locator(".exact-popover").inner_text()


def test_real_missing_input_keeps_typed_null_baseline_distinct_from_zero(sui):
    page, env = sui["page"], sui["analysis"]
    (env.data / "Overall" / "material_costs.json").unlink()
    sui["checkpoint"]()
    response = _parameters(env)
    assert response.status_code == 422 and response.get_json()["baseline"]["unit_cost"] is None
    _choose(sui)
    assert page.locator("#sens-status").get_attribute("data-http-status") == "422"
    metric = page.locator("#sens-baseline [data-sensitivity-metric='baseline-unit-cost']")
    assert metric.locator("[data-raw]").count() == 0
    assert "در دسترس نیست" in metric.inner_text()
    assert page.locator("#sens-run").is_disabled()
    assert page.locator("#sens-export").is_disabled()
    assert page.locator("#sens-draft .sens-draft-item").count() == 0


def test_real_echarts_grouped_contributions_row_link_resize_and_multichange_evidence(sui):
    page, env = sui["page"], sui["analysis"]
    _real_echarts(page)
    _g2_fixture(env)
    sui["checkpoint"]()
    _choose(sui)
    share = _parameter(env, "category_share:")
    _add(page, "pool:Payroll", "1200")
    _add(page, share, "25")
    body, _ = _run(sui)
    page.wait_for_function("echarts.getInstanceByDom(document.querySelector('#sens-results [data-sensitivity-chart]')) !== undefined")
    options = page.evaluate("""() => echarts.getInstanceByDom(
      document.querySelector('#sens-results [data-sensitivity-chart]')).getOption()""")
    assert len(options["series"]) == 2
    assert all(len(series["data"]) == 7 for series in options["series"])
    tooltip = page.evaluate("""() => {
      const chart = echarts.getInstanceByDom(document.querySelector('#sens-results [data-sensitivity-chart]'));
      return chart.getOption().tooltip[0].formatter([{dataIndex:2}]);
    }""")
    payroll = next(driver for driver in body["scenario"]["breakdown"]["driver_components"] if driver["pool_id"] == "Payroll")
    assert payroll["per_unit_contribution"] in tooltip
    table = page.locator("#sens-results [data-sensitivity-table='drivers']")
    assert table.locator("tbody tr").count() == 7
    row = table.locator("[data-driver-id='Payroll']").filter(has=page.locator(".sens-driver-select")).first
    row.locator(".sens-driver-select").press("Enter")
    assert row.locator(".sens-driver-select").get_attribute("aria-pressed") == "true"
    page.evaluate("""() => {
      const chart = echarts.getInstanceByDom(document.querySelector('#sens-results [data-sensitivity-chart]'));
      chart.trigger('mouseover', {dataIndex:0});
      chart.trigger('click', {dataIndex:0});
    }""")
    assert table.locator(".sens-driver-select[data-driver-id='BOM']").get_attribute("aria-pressed") == "true"
    # Keep the meaningful nonzero driver selected for the visual evidence.
    row.locator(".sens-driver-select").press("Enter")
    assert body["effective_overrides"] and Decimal(_metric(page, "scenario-unit-cost")) == 240
    _evidence(sui, "sensitivity-multiple")
    page.locator("#cost-tab").press("Enter")
    _activate(page)
    _evidence(sui, "sensitivity-multiple", mobile=True)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_echarts_initialization_failure_keeps_table_cards_and_export_usable(sui):
    page, env = sui["page"], sui["analysis"]
    _g2_fixture(env)
    sui["checkpoint"]()
    page.evaluate("window.echarts = {init: () => {throw new Error('chart unavailable')}}")
    _choose(sui)
    _add(page, "pool:Payroll", "2000")
    _run(sui)
    _assert_costs(page, 100, 200)
    assert page.locator("#sens-results [data-sensitivity-table='drivers'] tbody tr").count() == 7
    assert page.locator("#sens-export").is_enabled()
    _csv(sui)


@pytest.mark.parametrize("status", [400, 403, 404, 413, 422, 503, 500])
def test_http_failure_clears_accepted_comparison_preserves_status_and_safe_message(sui, status, monkeypatch):
    page, env = sui["page"], sui["analysis"]
    _material_fixture(env)
    sui["checkpoint"]()
    material = _parameter(env, "material:")
    if status == 400:
        response = _scenario(env, [_change(material, "-1")])
    elif status == 403:
        response = _scenario(env, [_change(material, "2")], user="dashboard-user")
    elif status == 404:
        response = _scenario(env, factory="unknown")
    elif status == 413:
        response = env.client.post(SCENARIO, data=b"{" + b" " * 65536 + b"}",
                                   content_type="application/json")
    elif status in {422, 503}:
        source = (env.data / "Overall" / "material_costs.json" if status == 422
                  else env.data / "Factories" / "__metadata.json")
        original = source.read_bytes()
        source.unlink()
        response = _scenario(env)
        source.write_bytes(original)
    else:
        def unavailable(*args, **kwargs):
            raise RuntimeError("browser fixture calculation unavailable")
        with monkeypatch.context() as patch:
            patch.setattr(CostInputLoader, "load", unavailable)
            response = _scenario(env)
    assert response.status_code == status
    error = response.get_json()
    sui["checkpoint"]()
    _choose(sui)
    _run(sui)
    page.route("**" + SCENARIO, lambda route: route.fulfill(
        status=status, content_type="application/json", body=json.dumps(error, ensure_ascii=False)))
    _run(sui, status)
    assert page.locator("#sens-status").get_attribute("data-state") == error["state"]
    assert page.locator("#sens-comparison").is_hidden()
    assert page.locator("#sens-export").is_disabled()
    assert page.locator("#sens-status").inner_text().strip()
    if status == 400:
        assert Decimal(_baseline(page)) == 140


@pytest.mark.parametrize("failure", ["html", "invalid-json", "invalid-schema", "network", "login"])
def test_transport_session_and_invalid_payload_fail_closed(sui, failure):
    page = sui["page"]
    _choose(sui)
    _run(sui)
    if failure == "network":
        page.route("**" + SCENARIO, lambda route: route.abort())
    elif failure == "login":
        page.route("**" + SCENARIO, lambda route: route.fulfill(status=302, headers={"Location": "/login"}))
    else:
        content_type, payload = {
            "html": ("text/html", "<html>temporary gateway failure</html>"),
            "invalid-json": ("application/json", "{broken"),
            "invalid-schema": ("application/json", '{"version":"1","state":"OK"}'),
        }[failure]
        page.route("**" + SCENARIO, lambda route: route.fulfill(
            status=200, content_type=content_type, body=payload))
    page.locator("#sens-run").press("Enter")
    page.wait_for_function("document.querySelector('#sens-status').dataset.state !== 'LOADING'")
    assert page.locator("#sens-comparison").is_hidden()
    assert page.locator("#sens-export").is_disabled()
    assert page.locator("#sens-status").inner_text().strip()


def test_mobile_keyboard_xss_and_csv_formula_injection_safety(sui):
    page, env = sui["page"], sui["analysis"]
    _material_fixture(env)
    sui["checkpoint"]()
    registry = _parameters(env).get_json()
    material = next(entry for entry in registry["parameters"] if entry["group"] == "general_parameters")
    payload = '<img src=x onerror="window.pwned=true">'
    material["label"] = payload
    page.route("**" + PARAMETERS + "?*", lambda route: route.fulfill(
        content_type="application/json", body=json.dumps(registry, ensure_ascii=False)))
    page.set_viewport_size({"width": 390, "height": 844})
    _choose(sui)
    assert payload in page.locator("#sens-general-parameters").inner_text()
    assert page.locator("#sens-general-parameters img").count() == 0
    assert page.evaluate("window.pwned === undefined")
    _add(page, material["parameter_id"], "۱۰", "percent_change")
    accepted = _scenario(env, [_change(material["parameter_id"], "10", "percent_change")]).get_json()
    next(entry for entry in accepted["parameters"] if entry["parameter_id"] == material["parameter_id"])["label"] = '=HYPERLINK("https://example.test","x")'
    page.route("**" + SCENARIO, lambda route: route.fulfill(
        content_type="application/json", body=json.dumps(accepted, ensure_ascii=False)))
    _run(sui)
    raw, rows = _csv(sui)
    assert any(cell.startswith("'=HYPERLINK") for row in rows for cell in row)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    trigger = page.locator("#sens-results [data-sensitivity-metric='scenario-unit-cost'] [data-exact-trigger]")
    trigger.press("Enter")
    assert page.locator(".exact-popover").is_visible()
    assert page.locator(".exact-popover").evaluate("node => {const r=node.getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth}")
    page.locator(".exact-close").press("Enter")
    assert trigger.evaluate("node => node === document.activeElement")
