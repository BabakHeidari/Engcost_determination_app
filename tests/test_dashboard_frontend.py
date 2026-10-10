"""Real Chromium checks of the authorized Dashboard and its shipped assets.

Install the optional ``playwright`` package and Chromium to run these checks.
No application startup or repository Data files are used: the API fixture from
PR-06 supplies isolated, installed V2 inputs and a real authenticated session.
"""

import copy
import csv
import io
import json
import os
from pathlib import Path
from decimal import Decimal
import shutil
import threading
from urllib.parse import parse_qs, urlparse

import pytest
from werkzeug.serving import make_server

from test_dashboard_cost_analysis import (
    FACTORY, _bom, _reference, _request, _set_pools, _write, analysis,
)
from utils.localization import format_jalali_date
from utils.dashboard_analysis import empty_report
from utils.product_hierarchy_service import ProductHierarchyService


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def browser():
    playwright = pytest.importorskip("playwright.sync_api", reason="Browser tests require optional Playwright")
    chromium = os.environ.get("DASHBOARD_CHROMIUM_PATH") or shutil.which("chromium") or shutil.which("chromium-browser")
    if not chromium:
        pytest.skip("Browser tests require Chromium (or DASHBOARD_CHROMIUM_PATH)")
    with playwright.sync_playwright() as runtime:
        instance = runtime.chromium.launch(executable_path=chromium, headless=True,
                                           args=["--no-sandbox", "--disable-dev-shm-usage"])
        yield instance
        instance.close()


@pytest.fixture
def ui(analysis, monkeypatch, browser):
    app = analysis.app
    app.template_folder = str(ROOT / "templates")
    app.static_folder = str(ROOT / "static")
    app.jinja_env.filters["jalali_date"] = format_jalali_date
    app.add_url_rule("/logout", endpoint="auth.logout", view_func=lambda: "logout")
    app.context_processor(lambda: {"module_navigation": {"dashboard": True}, "user": "کاربر آزمون"})
    monkeypatch.setattr("modules.dashboard.routes.ProductHierarchyService",
                        lambda: ProductHierarchyService(analysis.data / "Factories"))
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    context = browser.new_context(viewport={"width": 1440, "height": 1100},
                                  timezone_id="America/Los_Angeles", accept_downloads=True)
    # Obtain the signed session through the same login_required session contract.
    cookie = analysis.client.get_cookie("session")
    context.add_cookies([{"name": "session", "value": cookie.value, "url": base}])
    page = context.new_page()
    page.set_default_timeout(6000)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    # Offline chart fallback is an explicit supported mode; all local assets and
    # all Flask requests still execute. No remote resources are necessary.
    page.route("https://**/*", lambda route: route.abort())
    bootstrap_path = Path(os.environ.get("DASHBOARD_BOOTSTRAP_PATH", ROOT / "work" / "vendor" / "bootstrap.min.css"))
    if bootstrap_path.is_file():
        page.route("https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css",
                   lambda route: route.fulfill(content_type="text/css", body=bootstrap_path.read_bytes()))
    page.goto(base + "/dashboard", wait_until="networkidle")
    yield {"page": page, "context": context, "base": base, "analysis": analysis, "errors": errors}
    context.close()
    server.shutdown()
    thread.join(timeout=3)
    server.server_close()


def _select(page, category="__ALL__", subcategory="__ALL__", product="__ALL__", ready=True):
    page.select_option("#factorySelect", FACTORY)
    page.wait_for_function("!document.querySelector('#categorySelect').disabled")
    page.select_option("#categorySelect", category)
    page.wait_for_function("!document.querySelector('#subcategorySelect').disabled")
    page.select_option("#subcategorySelect", subcategory)
    page.wait_for_function("!document.querySelector('#productSelect').disabled")
    page.select_option("#productSelect", product)
    if ready:
        page.wait_for_function("!document.querySelector('#analyzeBtn').disabled")


def _analyze(page):
    page.locator("#analyzeBtn").press("Enter")
    page.wait_for_function("document.querySelector('#analysisStatus').dataset.state !== 'LOADING'")


def _fulfill(page, document, status=200):
    page.route("**/api/cost_analysis?*", lambda route: route.fulfill(
        status=status, content_type="application/json", body=json.dumps(document, ensure_ascii=False)))


def _download(page):
    requests = []
    listener = lambda request: requests.append(request.url)
    page.on("request", listener)
    with page.expect_download() as pending:
        page.locator("#downloadCsvBtn").press("Enter")
    raw = Path(pending.value.path()).read_bytes()
    page.remove_listener("request", listener)
    assert not any(urlparse(url).path == "/api/cost_analysis" for url in requests)
    assert raw.startswith(b"\xef\xbb\xbf")
    return raw, [row for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))) if row["row_type"] == "configuration"]


def _install_pending_fetch(page, path):
    # Deliberately ignore AbortSignal: sequence/scope guards must work even if a
    # response was already delivered before the browser observed cancellation.
    page.evaluate("""path => {
      const original = window.fetch;
      window.testPending = [];
      window.fetch = (url, options) => {
        if (new URL(url, location.href).pathname !== path) return original(url, options);
        return new Promise((resolve, reject) => {
          window.testPending.push({url: String(url), resolve, reject, signal: options && options.signal});
        });
      };
    }""", path)


def _resolve(page, index, document, status=200):
    page.evaluate("""args => window.testPending[args.index].resolve(new Response(
      JSON.stringify(args.document), {status: args.status, headers: {'Content-Type': 'application/json'}}))
    """, {"index": index, "document": document, "status": status})


def test_real_authorized_selection_analysis_csv_and_chart_fallback(ui):
    page, fixture = ui["page"], ui["analysis"]
    assert page.locator("html").get_attribute("dir") == "rtl"
    assert page.locator("#factorySelect option[value='__ALL__']").count() == 0
    assert page.locator("#analyzeBtn").is_disabled()
    page.select_option("#factorySelect", FACTORY)
    page.wait_for_function("!document.querySelector('#categorySelect').disabled")
    assert page.locator("#categorySelect").input_value() == ""
    assert page.locator("#analyzeBtn").is_disabled()
    page.select_option("#categorySelect", "category")
    page.wait_for_function("!document.querySelector('#subcategorySelect').disabled")
    assert page.locator("#subcategorySelect").input_value() == ""
    page.select_option("#subcategorySelect", "sub")
    page.wait_for_function("!document.querySelector('#productSelect').disabled")
    assert page.locator("#productSelect").input_value() == ""
    references = page.locator("#productSelect option").evaluate_all("nodes => nodes.map(n => n.value)")
    reference = next(value for value in references if value and value != "__ALL__")
    assert reference not in {"A", "B"}
    page.select_option("#productSelect", reference)
    with page.expect_response("**/api/cost_analysis?*") as pending:
        _analyze(page)
    response = pending.value
    assert response.status == 200
    body = response.json()
    query = parse_qs(urlparse(response.url).query)
    assert query["product"] == [reference]
    assert body["scope"]["factory"]["id"] == FACTORY
    assert body["coverage"]["configured"] == 1
    assert page.locator("#costDashboard").is_visible()
    assert page.locator("#totalCost[data-raw]").get_attribute("data-raw") == body["kpis"]["projected_total"]
    assert page.locator("#detailTable tbody tr").count() == 1
    assert page.locator("#driverTable tbody tr").count() == 7
    assert page.locator("#poolTable tbody tr").count() == 12
    assert page.locator("#downloadCsvBtn").is_enabled()
    assert page.evaluate("typeof window.echarts") == "undefined"
    assert "نمودار در دسترس نیست" in page.locator("#productCostChart").locator("..").inner_text()
    raw, rows = _download(page)
    assert len(rows) == 1
    assert body["kpis"]["projected_total"].encode() in raw
    assert b"2026-10-01" in raw and b"2026-12-31" in raw
    assert not ui["errors"]
    evidence = os.environ.get("DASHBOARD_UI_EVIDENCE_DIR")
    if evidence:
        folder = Path(evidence)
        folder.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(folder / "dashboard-desktop.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_function("document.querySelector('#mainSidebar').getBoundingClientRect().left >= window.innerWidth - 1")
        page.screenshot(path=str(folder / "dashboard-mobile.png"), full_page=True)


def test_explicit_all_and_jalali_validation_preserve_date_boundaries(ui):
    page = ui["page"]
    _select(page)
    assert page.locator("#startDate").input_value() == "۱۴۰۵/۰۷/۰۹"
    assert page.locator("#endDate").input_value() == "۱۴۰۵/۱۰/۱۰"
    page.fill("#startDate", "۱۴۰۵/۱۳/۰۹")
    assert page.locator("#analyzeBtn").is_disabled()
    assert page.locator("#startDate").get_attribute("aria-invalid") == "true"
    page.fill("#startDate", "1405/07/09")
    page.fill("#endDate", "۱۴۰۵/۱۰/۱۰")
    with page.expect_response("**/api/cost_analysis?*") as pending:
        _analyze(page)
    query = parse_qs(urlparse(pending.value.url).query)
    assert {key: query[key] for key in ("category", "subcategory", "product")} == {
        "category": ["__ALL__"], "subcategory": ["__ALL__"], "product": ["__ALL__"]}
    assert query["start"] == ["2026-10-01"] and query["end"] == ["2026-12-31"]
    assert "۱۴۰۵/۰۷/۰۹" in page.locator("#reportPeriod").inner_text()
    assert "۱۴۰۵/۱۰/۱۰" in page.locator("#reportPeriod").inner_text()
    page.fill("#startDate", "۱۴۰۵/۰۷/۱۰")
    assert page.locator("#downloadCsvBtn").is_disabled()
    assert page.locator("#analyzeBtn").is_disabled()


def test_out_of_order_hierarchy_response_cannot_restore_old_children(ui):
    page = ui["page"]
    _select(page)
    _install_pending_fetch(page, "/api/dashboard/filter-options")
    page.select_option("#categorySelect", "category")
    page.wait_for_function("window.testPending.length === 1")
    page.evaluate("document.querySelector('#categorySelect').value = '__ALL__'; document.querySelector('#categorySelect').dispatchEvent(new Event('change'))")
    page.wait_for_function("window.testPending.length === 2")
    assert page.locator("#analyzeBtn").is_disabled()
    assert page.evaluate("window.testPending[0].signal.aborted")
    current = ui["analysis"].client.get("/api/dashboard/filter-options", query_string={
        "factory": FACTORY, "category": "__ALL__"}).get_json()
    _resolve(page, 1, current)
    page.wait_for_function("!document.querySelector('#subcategorySelect').disabled")
    stale = copy.deepcopy(current)
    stale["selection"]["category"] = "category"
    stale["options"]["subcategories"] = [{"id": "stale", "label": "پاسخ قدیمی"}]
    _resolve(page, 0, stale)
    page.wait_for_timeout(50)
    assert page.locator("#categorySelect").input_value() == "__ALL__"
    assert page.locator("#subcategorySelect option[value='stale']").count() == 0
    assert page.locator("#subcategorySelect").input_value() == ""


def test_analysis_cancellation_scope_guards_and_duplicate_request_prevention(ui):
    page = ui["page"]
    _select(page)
    _install_pending_fetch(page, "/api/cost_analysis")
    page.locator("#analyzeBtn").press("Enter")
    page.wait_for_function("window.testPending.length === 1")
    assert page.locator("#analyzeBtn").is_disabled()
    page.evaluate("document.querySelector('#analysisForm').dispatchEvent(new Event('submit', {bubbles:true,cancelable:true}))")
    assert page.evaluate("window.testPending.length") == 1
    page.select_option("#productSelect", page.locator("#productSelect option").nth(2).get_attribute("value"))
    assert page.evaluate("window.testPending[0].signal.aborted")
    assert page.locator("#downloadCsvBtn").is_disabled()
    page.locator("#analyzeBtn").press("Enter")
    page.wait_for_function("window.testPending.length === 2")
    query = parse_qs(urlparse(page.evaluate("window.testPending[1].url")).query)
    current = ui["analysis"].client.get("/api/cost_analysis", query_string={k: v[0] for k, v in query.items()}).get_json()
    _resolve(page, 1, current)
    page.wait_for_function("!document.querySelector('#downloadCsvBtn').disabled")
    accepted = page.locator("#totalCost[data-raw]").get_attribute("data-raw")
    stale = _request(ui["analysis"]).get_json()
    _resolve(page, 0, stale)
    page.wait_for_timeout(50)
    assert page.locator("#totalCost[data-raw]").get_attribute("data-raw") == accepted
    page.select_option("#productSelect", "__ALL__")
    assert page.locator("#downloadCsvBtn").is_disabled()
    assert not page.locator("#costDashboard").is_visible()


def test_partial_exclusions_and_no_match_remain_truthful(ui):
    page, fixture = ui["page"], ui["analysis"]
    _write(fixture.factory / "category" / "sub" / "B.json", _bom([40], loss=101))
    _select(page)
    _analyze(page)
    assert page.locator("#analysisStatus").get_attribute("data-state") == "PARTIAL"
    assert "مجموع جزئی" in page.locator("#totalCostLabel").inner_text()
    assert page.locator("#totalCost[data-raw]").get_attribute("data-raw") == _request(fixture).get_json()["kpis"]["partial_total"]
    assert page.locator("#detailTable tbody tr").count() == 2
    excluded = page.locator("#detailTable tbody tr.report-excluded")
    assert "در دسترس نیست" in excluded.inner_text()
    assert "INVALID_PERCENTAGE" in excluded.inner_text()
    assert "۱" in page.locator("#coverageSummary").inner_text()
    _, rows = _download(page)
    assert len(rows) == 2
    assert any("INVALID_PERCENTAGE" in json.dumps(row) for row in rows)
    page.select_option("#categorySelect", "category")
    page.wait_for_function("!document.querySelector('#subcategorySelect').disabled")
    page.select_option("#subcategorySelect", "empty")
    page.wait_for_function("!document.querySelector('#productSelect').disabled")
    page.select_option("#productSelect", "__ALL__")
    _analyze(page)
    assert page.locator("#analysisStatus").get_attribute("data-state") == "NO_MATCH"
    assert "980001000" not in page.locator("#costDashboard").inner_text()
    assert page.locator("#detailTable tbody tr[data-state]").count() == 0


def test_zero_and_null_share_do_not_turn_into_unavailable_or_zero_percent(ui):
    page, fixture = ui["page"], ui["analysis"]
    for product in ("A", "B"):
        _write(fixture.factory / "category" / "sub" / f"{product}.json", _bom([0]))
    _set_pools(fixture)
    _select(page)
    _analyze(page)
    assert page.locator("#analysisStatus").get_attribute("data-state") == "OK"
    zero_report = _request(fixture).get_json()
    assert page.locator("#totalCost[data-raw]").get_attribute("data-raw") == zero_report["kpis"]["projected_total"]
    assert page.locator("#avgCost[data-raw]").get_attribute("data-raw") == zero_report["kpis"]["weighted_average"]["value"]
    assert Decimal(zero_report["kpis"]["projected_total"]) == 0
    assert "در دسترس نیست" in page.locator("#topDriver").locator("..").inner_text()
    assert "۰٪" not in page.locator("#topDriver").locator("..").inner_text()
    assert "۰%" not in page.locator("#topDriver").locator("..").inner_text()
    assert "هم‌رتبه" in page.locator("#topDriver").locator("..").inner_text()
    assert "استهلاک" in page.locator("#topDriver").locator("..").inner_text()
    _, rows = _download(page)
    assert all(Decimal(row["unit_cost"]) == 0 and Decimal(row["projected_cost"]) == 0 for row in rows)


def test_zero_target_prediction_preserves_not_applicable_average(ui):
    page, fixture = ui["page"], ui["analysis"]
    _write(fixture.factory / "configuration" / "production_prediction.json", {"data": {
        "Product Name": ["A", "B"], "Predicted Production": [0, 10]}})
    _select(page, "category", "sub", _reference("category", "sub", "A"))
    _analyze(page)
    assert Decimal(page.locator("#totalCost[data-raw]").get_attribute("data-raw")) == 0
    assert "قابل اعمال نیست" in page.locator("#avgCost").inner_text()
    assert Decimal(page.locator("#weightedNumerator[data-raw]").get_attribute("data-raw")) == 0
    assert Decimal(page.locator("#weightedDenominator[data-raw]").get_attribute("data-raw")) == 0


def test_422_preserves_coverage_excluded_rows_and_safe_issues(ui):
    page, fixture = ui["page"], ui["analysis"]
    _select(page)
    _analyze(page)
    assert page.locator("#downloadCsvBtn").is_enabled()
    (fixture.data / "Overall" / "material_costs.json").unlink()
    with page.expect_response("**/api/cost_analysis?*") as pending:
        _analyze(page)
    assert pending.value.status == 422
    body = pending.value.json()
    assert page.locator("#analysisStatus").get_attribute("data-state") == body["state"]
    assert page.locator("#detailTable tbody tr").count() == 2
    assert "SOURCE_UNAVAILABLE" in page.locator("#reportIssues").inner_text()
    assert page.locator("#totalCost[data-raw]").count() == 0
    assert "در دسترس نیست" in page.locator("#totalCost").inner_text()


@pytest.mark.parametrize("failure", [
    "400", "403", "404", "503", "500", "network", "redirect", "non-json", "invalid-json", "unsupported-schema",
])
def test_failure_after_success_never_reuses_previous_result(ui, failure):
    page = ui["page"]
    _select(page)
    _analyze(page)
    assert page.locator("#downloadCsvBtn").is_enabled()
    def fail(route):
        if failure == "network":
            return route.abort("failed")
        if failure == "redirect":
            return route.fulfill(status=302, headers={"Location": "/login"})
        if failure == "non-json":
            return route.fulfill(status=200, content_type="text/html", body="<html>login</html>")
        if failure == "invalid-json":
            return route.fulfill(status=200, content_type="application/json", body="{invalid")
        if failure == "unsupported-schema":
            return route.fulfill(status=200, content_type="application/json", body='{"version":"2","state":"OK"}')
        state = {"400": "INVALID_REQUEST", "403": "FORBIDDEN", "404": "UNKNOWN_FACTORY",
                 "503": "UNAVAILABLE", "500": "CALCULATION_ERROR"}[failure]
        return route.fulfill(status=int(failure), content_type="application/json",
                             body=json.dumps(empty_report(state)))
    page.route("**/api/cost_analysis?*", fail)
    _analyze(page)
    assert page.locator("#downloadCsvBtn").is_disabled()
    assert not page.locator("#costDashboard").is_visible()
    message = page.locator("#analysisStatus").inner_text()
    assert any("\u0600" <= char <= "\u06ff" for char in message)
    assert page.locator("#analysisStatus").get_attribute("data-state") not in {"OK", "PARTIAL", "LOADING"}
    if failure.isdigit():
        assert page.locator("#analysisStatus").get_attribute("data-http-status") == failure
        expected = {"400": "انتخاب‌ها", "403": "اجازه", "404": "کارخانه", "503": "دسترس", "500": "محاسبه"}
        assert expected[failure] in message
    if failure == "redirect":
        assert "دوباره وارد" in message
    assert not ui["errors"]


def test_high_precision_ties_html_text_and_csv_injection_are_preserved_safely(ui):
    page = ui["page"]
    _select(page)
    report = _request(ui["analysis"]).get_json()
    large = "90071992547409931234567.12345"
    negative = "-0.00000000000000000000001"
    report["kpis"]["projected_total"] = large
    report["kpis"]["weighted_average"].update(value=large, numerator=large)
    report["kpis"]["top_cost_driver"].update(id="BOM", value=large, share=None,
                                             tie=True, tied_ids=["BOM", "Depriciation"])
    report["arithmetic_reconciliation"]["difference"] = negative
    first, second = report["detail_rows"]
    first["identity"].update(category='<img src=x onerror="window.xss=1">',
                             subcategory="@خطر", product='=SUM(1,2)\n"محصول فارسی"')
    first.update(unit_cost=negative, prediction="-10", projected_cost=large)
    second["identity"].update(category="-2+3", product="<script>window.xss=1</script>")
    report["breakdowns"]["products"] = copy.deepcopy(report["detail_rows"])
    _fulfill(page, report)
    _analyze(page)
    assert page.locator("#totalCost[data-raw]").get_attribute("data-raw") == large
    assert page.locator("#totalCost[data-raw]").get_attribute("title") == large
    assert "هم‌رتبه" in page.locator("#topDriver").locator("..").inner_text()
    assert "استهلاک" in page.locator("#topDriver").locator("..").inner_text()
    assert "<script>window.xss=1</script>" in page.locator("#detailTable").inner_text()
    assert '<img src=x onerror="window.xss=1">' in page.locator("#detailTable").inner_text()
    assert page.locator("#detailTable img,#detailTable script").count() == 0
    assert page.evaluate("window.xss || 0") == 0
    raw, rows = _download(page)
    assert rows[0]["unit_cost"] == negative
    assert rows[0]["prediction"] == "-10"
    assert rows[0]["projected_cost"] == large
    assert rows[0]["product"] == "'" + first["identity"]["product"]
    assert rows[0]["subcategory"] == "'@خطر"
    assert rows[1]["category"] == "'-2+3"
    assert "محصول فارسی".encode() in raw
    assert len(rows) == 2
    assert not ui["errors"]


def test_hierarchy_labels_are_text_and_same_name_products_retain_composite_values(ui):
    page, fixture = ui["page"], ui["analysis"]
    def labels(route):
        query = {key: values[0] for key, values in parse_qs(urlparse(route.request.url).query).items()}
        body = fixture.client.get("/api/dashboard/filter-options", query_string=query).get_json()
        body["options"]["categories"][0]["label"] = '<img src=x onerror="window.xss=1">'
        for product in body["options"]["products"]:
            product["label"] = "<script>window.xss=1</script>"
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
    page.route("**/api/dashboard/filter-options?*", labels)
    _select(page)
    assert '<img src=x onerror="window.xss=1">' in page.locator("#categorySelect").inner_text()
    products = page.locator("#productSelect option").evaluate_all("nodes => nodes.slice(2).map(n => ({value:n.value,text:n.textContent}))")
    assert len(products) == 2
    assert len({item["value"] for item in products}) == 2
    assert products[0]["text"] == products[1]["text"]
    assert "<script>window.xss=1</script>" in products[0]["text"]
    assert page.locator(".dashboard-page img,.dashboard-page script[src='x']").count() == 0
    assert page.evaluate("window.xss || 0") == 0
    _analyze(page)
    assert page.locator("#analysisStatus").get_attribute("data-state") == "OK"


def test_chart_options_use_selected_contributions_and_safe_canvas_tooltips(ui):
    page = ui["page"]
    _select(page)
    page.evaluate("""() => {
      window.testCharts = [];
      window.echarts = {init: element => {
        const instance = {id:element.id, options:null, disposed:false};
        window.testCharts.push(instance);
        return {setOption: options => {instance.options = options;},
                resize: () => {}, dispose: () => {instance.disposed = true;}};
      }};
    }""")
    with page.expect_response("**/api/cost_analysis?*") as pending:
        _analyze(page)
    report = pending.value.json()
    charts = page.evaluate("window.testCharts.map(chart => ({id:chart.id,options:chart.options}))")
    assert [chart["id"] for chart in charts] == ["productCostChart", "driverCompositionChart"]
    assert charts[0]["options"]["tooltip"]["renderMode"] == "richText"
    assert charts[1]["options"]["tooltip"]["renderMode"] == "richText"
    expected = [float(driver["value"]) for driver in report["breakdowns"]["drivers"]]
    assert charts[1]["options"]["series"][0]["data"] == expected
    payroll = next(pool for pool in report["breakdowns"]["factory_pools"] if pool["id"] == "Payroll")
    index = next(index for index, driver in enumerate(report["breakdowns"]["drivers"]) if driver["id"] == "Payroll")
    assert expected[index] == float(payroll["modeled_selected_total"])
    assert expected[index] != float(payroll["raw_total"])
    page.select_option("#productSelect", "")
    assert page.evaluate("window.testCharts.every(chart => chart.disposed)")


def test_period_change_cancels_analysis_and_invalidates_export(ui):
    page = ui["page"]
    _select(page)
    _install_pending_fetch(page, "/api/cost_analysis")
    page.locator("#analyzeBtn").press("Enter")
    page.wait_for_function("window.testPending.length === 1")
    page.select_option("#periodSelect", "P")
    assert page.evaluate("window.testPending[0].signal.aborted")
    assert page.locator("#downloadCsvBtn").is_disabled()
    _resolve(page, 0, _request(ui["analysis"]).get_json())
    page.wait_for_timeout(50)
    assert not page.locator("#costDashboard").is_visible()
    assert page.locator("#downloadCsvBtn").is_disabled()
    page.locator("#analyzeBtn").press("Enter")
    page.wait_for_function("window.testPending.length === 2")
    _resolve(page, 1, _request(ui["analysis"], period="P").get_json())
    page.wait_for_function("!document.querySelector('#downloadCsvBtn').disabled")
    page.select_option("#periodSelect", "")
    assert page.locator("#downloadCsvBtn").is_disabled()


@pytest.mark.parametrize("binding_state", ["missing", "ambiguous"])
def test_installed_period_metadata_controls_analysis_availability(ui, binding_state):
    page, fixture = ui["page"], ui["analysis"]
    if binding_state == "missing":
        fixture.binding.unlink()
    else:
        document = json.loads(fixture.binding.read_text())
        document["bindings"].append({**document["bindings"][0], "period_id": "Q"})
        _write(fixture.binding, document)
    page.reload(wait_until="networkidle")
    _select(page, ready=False)
    assert page.locator("#analyzeBtn").is_disabled()
    assert page.locator("#startDate").is_disabled()
    assert page.locator("#downloadCsvBtn").is_disabled()
    if binding_state == "missing":
        assert "دوره معتبر نصب‌شده‌ای" in page.locator("#periodStatus").inner_text()
        assert page.locator("#periodSelect").is_disabled()
    else:
        assert page.locator("#periodSelect").input_value() == ""
        page.select_option("#periodSelect", "Q")
        with page.expect_response("**/api/cost_analysis?*") as pending:
            _analyze(page)
        assert parse_qs(urlparse(pending.value.url).query)["period"] == ["Q"]
        assert pending.value.status == 200
        assert "Q" in page.locator("#reportPeriod").inner_text()


@pytest.mark.parametrize("timezone", ["America/Los_Angeles", "Asia/Tehran", "Pacific/Kiritimati"])
def test_shared_jalali_date_only_all_months_and_timezones(ui, browser, timezone):
    dates = [f"2026-{month:02d}-01" for month in range(1, 13)]
    expected = ["۱۴۰۴/۱۰/۱۱", "۱۴۰۴/۱۱/۱۲", "۱۴۰۴/۱۲/۱۰", "۱۴۰۵/۰۱/۱۲", "۱۴۰۵/۰۲/۱۱", "۱۴۰۵/۰۳/۱۱",
                "۱۴۰۵/۰۴/۱۰", "۱۴۰۵/۰۵/۱۰", "۱۴۰۵/۰۶/۱۰", "۱۴۰۵/۰۷/۰۹", "۱۴۰۵/۰۸/۱۰", "۱۴۰۵/۰۹/۱۰"]
    context = browser.new_context(timezone_id=timezone)
    context.add_cookies(ui["context"].cookies())
    page = context.new_page()
    page.route("https://**/*", lambda route: route.abort())
    try:
        page.goto(ui["base"] + "/dashboard", wait_until="networkidle")
        actual = page.evaluate("dates => dates.map(date => JalaliDate.formatDateOnly(date))", dates)
        assert actual == expected
        assert page.evaluate("dates => dates.map(date => JalaliDate.parseJalaliInput(JalaliDate.formatDateOnly(date)))", dates) == dates
        assert page.evaluate("JalaliDate.formatDateOnly('2026-02-30', 'نامعتبر')") == "نامعتبر"
        assert page.evaluate("""() => {
          try { JalaliDate.parseJalaliInput('۱۴۰۴/۱۲/۳۰'); return false; }
          catch(error) { return true; }
        }""")
    finally:
        context.close()


def test_real_echarts_with_authorized_api_and_responsive_evidence(ui):
    library = Path(os.environ.get("DASHBOARD_ECHARTS_PATH", ROOT / "work" / "vendor" / "echarts.min.js"))
    if not library.is_file():
        pytest.skip("Optional real ECharts verification requires DASHBOARD_ECHARTS_PATH (fallback and chart contract still run)")
    page = ui["page"]
    page.route("https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js",
               lambda route: route.fulfill(content_type="application/javascript", body=library.read_bytes()))
    page.reload(wait_until="networkidle")
    _select(page)
    with page.expect_response("**/api/cost_analysis?*") as pending:
        _analyze(page)
    report = pending.value.json()
    options = page.evaluate("""() => ['productCostChart','driverCompositionChart'].map(id =>
      echarts.getInstanceByDom(document.getElementById(id)).getOption())""")
    assert len(options[0]["series"][0]["data"]) == report["coverage"]["calculated"]
    assert [label.split(" | ")[0] for label in options[0]["yAxis"][0]["data"]] == [
        row["identity"]["product"] for row in report["breakdowns"]["products"]]
    assert options[1]["series"][0]["data"] == [float(driver["value"]) for driver in report["breakdowns"]["drivers"]]
    assert all(option["tooltip"][0]["renderMode"] == "richText" for option in options)
    assert page.locator("#productCostChart canvas").count() > 0
    assert page.locator("#driverCompositionChart canvas").count() > 0
    assert not ui["errors"]
    assert page.locator("#cost-tab").evaluate("element => getComputedStyle(element).color") != "rgb(255, 255, 255)"
    evidence = os.environ.get("DASHBOARD_UI_EVIDENCE_DIR")
    if evidence:
        folder = Path(evidence)
        folder.mkdir(parents=True, exist_ok=True)
        page.wait_for_timeout(1100)  # Capture completed ECharts bar animation.
        page.evaluate("window.scrollTo(0, 0)")
        page.screenshot(path=str(folder / "dashboard-desktop.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_function("document.querySelector('#mainSidebar').getBoundingClientRect().left >= window.innerWidth - 1")
        page.wait_for_function("document.documentElement.scrollWidth <= window.innerWidth + 1")
        page.wait_for_timeout(400)  # Allow the chart canvas resize to settle.
        page.evaluate("window.scrollTo(0, 0)")
        page.screenshot(path=str(folder / "dashboard-mobile.png"), full_page=True)
