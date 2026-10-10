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
                                  timezone_id="America/Los_Angeles", has_touch=True, accept_downloads=True)
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
    icons = ROOT / "work" / "vendor" / "fontawesome"
    if (icons / "all.min.css").is_file():
        page.route("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css",
                   lambda route: route.fulfill(content_type="text/css", body=(icons / "all.min.css").read_bytes()))
    if (icons / "fa-solid-900.woff2").is_file():
        page.route("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/webfonts/fa-solid-900.woff2",
                   lambda route: route.fulfill(content_type="font/woff2", body=(icons / "fa-solid-900.woff2").read_bytes()))
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


def _real_echarts(page):
    library = Path(os.environ.get("DASHBOARD_ECHARTS_PATH", ROOT / "work" / "vendor" / "echarts.min.js"))
    if not library.is_file():
        pytest.skip("Real chart checks require a cached ECharts library or DASHBOARD_ECHARTS_PATH")
    page.route("https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js",
               lambda route: route.fulfill(content_type="application/javascript", body=library.read_bytes()))
    page.reload(wait_until="networkidle")


def _chart_options(page):
    return page.evaluate("""() => ['productCostChart','driverCompositionChart'].map(id =>
      echarts.getInstanceByDom(document.getElementById(id)).getOption())""")


def _chart_values(option):
    return [value["value"] if isinstance(value, dict) else value
            for value in option["series"][0]["data"]]


def _clipboard(page):
    # Intercept the browser capability, not the UI action: assertions exercise
    # the actual exact-value copy button and inspect its original ASCII input.
    page.evaluate("""() => {
      window.copiedExact = [];
      Object.defineProperty(navigator, 'clipboard', {configurable:true,
        value:{writeText: async value => {window.copiedExact.push(value);}}});
    }""")


def _expand_report(report, count=27):
    """Independent composite identities, repeated names and safe-precision gaps."""
    original = copy.deepcopy(report["detail_rows"][0])
    rows = []
    for index in range(count):
        row = copy.deepcopy(original)
        row["identity"].update(category=f"دسته {index // 6 + 1}",
                               subcategory=f"خانواده {index + 1}", product="محصول مشترک")
        row.update(unit_cost=f"9007199254740993.{index:02d}345678901234567890",
                   prediction=f"{index + 1}.000", projected_cost=f"156039333333.{index:02d}")
        rows.append(row)
    report["detail_rows"] = rows
    report["breakdowns"]["products"] = copy.deepcopy(rows)
    report["coverage"].update(configured=count, calculated=count, excluded=0, percentage="100")
    report["kpis"].update(matched_configuration_count=count, projected_total="156039333333")
    report["kpis"]["weighted_average"].update(value="9007199254740993.12345678901234567890",
                                                numerator="156039333333", denominator="378.000")
    for owner in (report["kpis"]["weighted_average"], report["kpis"]["top_cost_driver"],
                  *report["breakdowns"]["factory_pools"]):
        if "coverage" in owner:
            owner["coverage"] = copy.deepcopy(report["coverage"])
    return report


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
    assert page.locator("#detailTable tbody tr[data-state]").count() == 1
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
    assert page.locator("#detailTable tbody tr[data-state]").count() == 2
    excluded = page.locator("#detailTable tbody tr.report-excluded")
    assert "در دسترس نیست" in excluded.inner_text()
    assert "نامعتبر" in excluded.inner_text()
    excluded.locator(".row-details summary").click()
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
    page.locator(".report-ties summary").click()
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
    assert page.locator("#detailTable tbody tr[data-state]").count() == 2
    page.locator("#reportIssues > summary").click()
    assert "منابع لازم در دسترس نیست" in page.locator("#reportIssues").inner_text()
    page.locator("#detailTable .row-details summary").first.click()
    assert "SOURCE_UNAVAILABLE" in page.locator("#detailTable .row-details[open]").inner_text()
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
    page.locator("#totalCost[data-raw]").hover()
    assert page.locator(".exact-popover-value").inner_text().replace("٬", "").replace("٫", ".").translate(
        str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")).startswith(large)
    page.keyboard.press("Escape")
    assert "هم‌رتبه" in page.locator("#topDriver").locator("..").inner_text()
    page.locator(".report-ties summary").click()
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
    exported = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    assert next(row for row in exported if row["row_type"] == "arithmetic_reconciliation")["difference"] == negative
    assert next(row for row in exported if row["row_type"] == "kpis")["projected_total"] == large
    assert "بیشتر از −۰٫۰۱" in page.locator("#detailTable").inner_text()
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_function("document.documentElement.scrollWidth <= window.innerWidth + 1")
    assert page.locator("#totalCost").get_attribute("data-raw") == large
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
        return {setOption: options => {instance.options = options;}, on: () => {}, off: () => {},
                resize: () => {}, isDisposed: () => instance.disposed,
                dispose: () => {instance.disposed = true;}};
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
    assert _chart_values(charts[1]["options"]) == expected
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
    page = ui["page"]
    _real_echarts(page)
    _select(page)
    with page.expect_response("**/api/cost_analysis?*") as pending:
        _analyze(page)
    report = pending.value.json()
    options = _chart_options(page)
    assert len(options[0]["series"][0]["data"]) == report["coverage"]["calculated"]
    labels = options[0]["yAxis"][0]["data"]
    for row in report["breakdowns"]["products"]:
        assert any(row["identity"]["product"] in label and row["identity"]["subcategory"] in label for label in labels)
    assert _chart_values(options[1]) == [float(driver["value"]) for driver in report["breakdowns"]["drivers"]]
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


@pytest.mark.parametrize("raw,options,expected", [
    ("156039333333", {"unit": "IRR"}, "۱۵۶٫۰۴ میلیارد ریال"),
    ("9007199254740993.12345678901234567890", {"compact": False}, "۹٬۰۰۷٬۱۹۹٬۲۵۴٬۷۴۰٬۹۹۳٫۱۲"),
    ("999999995", {"unit": "IRR"}, "۱ میلیارد ریال"),
    ("999999999995", {"unit": "IRR"}, "۱ تریلیون ریال"),
    ("1.005", {"compact": False}, "۱٫۰۱"),
    ("-1.005", {"compact": False}, "−۱٫۰۱"),
    ("1234567.120000", {"compact": False}, "۱٬۲۳۴٬۵۶۷٫۱۲"),
    ("0", {}, "۰"),
    ("-0.000", {}, "−۰"),
    (None, {}, "در دسترس نیست"),
    (None, {"state": "NOT_APPLICABLE"}, "قابل اعمال نیست"),
    ("0.00000000000000000001", {}, "کمتر از ۰٫۰۱"),
    ("-0.00000000000000000001", {}, "بیشتر از −۰٫۰۱"),
    ("99.999", {"unit": "percentage", "coverage": True}, "بیش از ۹۹٫۹۹٪"),
    ("100", {"unit": "percentage", "coverage": True}, "۱۰۰٪"),
    ("-12.345", {"unit": "percentage"}, "−۱۲٫۳۵٪"),
    ("145.678", {"unit": "percentage"}, "۱۴۵٫۶۸٪"),
])
def test_string_number_presentation_preserves_boundaries_and_distinctions(ui, raw, options, expected):
    assert ui["page"].evaluate("args => DashboardNumbers.format(args.raw,args.options)",
                               {"raw": raw, "options": options}) == expected


def test_exact_value_hover_keyboard_copy_and_mobile_portal(ui):
    page = ui["page"]
    _select(page)
    report = _request(ui["analysis"]).get_json()
    precise = "9007199254740993.12345678901234567890"
    report["kpis"]["projected_total"] = "156039333333"
    report["kpis"]["weighted_average"]["value"] = precise
    _fulfill(page, report)
    _analyze(page)
    _clipboard(page)
    assert page.locator("#totalCost").inner_text().startswith("۱۵۶٫۰۴ میلیارد ریال")
    average = page.locator("#avgCost")
    assert average.get_attribute("data-raw") == precise
    average.hover()
    popup = page.locator(".exact-popover")
    assert popup.is_visible()
    assert popup.get_attribute("role") == "dialog"
    assert "۹٬۰۰۷٬۱۹۹٬۲۵۴٬۷۴۰٬۹۹۳٫۱۲۳۴۵۶۷۸۹۰۱۲۳۴۵۶۷۸۹۰" in popup.inner_text()
    assert "ریال" in popup.inner_text()
    popup.locator(".exact-copy").click()
    assert page.evaluate("window.copiedExact") == [precise]
    assert popup.locator(".exact-copy-status").inner_text()
    page.keyboard.press("Escape")
    assert not popup.is_visible()
    assert average.evaluate("element => element === document.activeElement")
    average.press("Enter")
    assert popup.is_visible()
    page.locator(".dashboard-heading h1").click()
    assert not popup.is_visible()
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_function("document.documentElement.scrollWidth <= window.innerWidth + 1")
    # The same browser pointer event used by mobile opens a body-level portal.
    average.tap()
    assert popup.is_visible()
    assert popup.evaluate("element => element.parentElement === document.body")
    bounds = popup.bounding_box()
    assert bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= 391
    popup.locator(".exact-copy").click()
    assert page.evaluate("window.copiedExact") == [precise, precise]
    popup.locator(".exact-close").click()
    assert not popup.is_visible()
    average.tap()
    assert popup.is_visible()
    page.select_option("#productSelect", "")
    assert not popup.is_visible()
    assert page.locator("#downloadCsvBtn").is_disabled()
    assert not ui["errors"]


def test_technical_disclosure_preserves_ascii_fingerprints_and_source_time_meanings(ui):
    page = ui["page"]
    _select(page)
    report = _request(ui["analysis"]).get_json()
    report["arithmetic_reconciliation"]["difference"] = "-0.00000000000000000000001"
    _fulfill(page, report)
    _analyze(page)
    _clipboard(page)
    technical = page.locator("#reportTechnical")
    assert technical.get_attribute("open") is None
    assert page.locator("#reportPools").get_attribute("open") is None
    assert not page.locator("#weightedNumerator").is_visible()
    assert report["formula_version"] not in page.locator("#reportToolbar").inner_text()
    assert "۱۴۰۵/۰۷/۰۹" in page.locator("#reportPeriod").inner_text()
    technical.locator(":scope > summary").click()
    assert report["formula_version"] in technical.inner_text()
    assert page.locator("#weightedNumerator").get_attribute("data-raw") == report["kpis"]["weighted_average"]["numerator"]
    assert page.locator("#weightedDenominator").get_attribute("data-raw") == report["kpis"]["weighted_average"]["denominator"]
    assert page.locator("#reportPrecision [data-raw='-0.00000000000000000000001']").count() == 1
    lineage = page.locator("#reportLineage")
    if lineage.evaluate("element => element.tagName === 'DETAILS'"):
        lineage.locator(":scope > summary").click()
    identifier = lineage.locator(".exact-identifier").first
    fingerprint = identifier.get_attribute("data-raw")
    assert fingerprint == report["source_lineage"][0]["fingerprint"]
    assert fingerprint not in identifier.inner_text()
    # Native Tab must scroll a below-fold source into view and expose the same
    # exact information. Locator.press alone does not perform that scrolling.
    page.locator("#reportPrecision .exact-value").last.focus()
    page.keyboard.press("Escape")
    page.evaluate("window.scrollTo(0,0)")
    page.keyboard.press("Tab")
    assert identifier.evaluate("element => element === document.activeElement")
    page.keyboard.press("Enter")
    page.locator(".exact-popover").wait_for(state="visible")
    exact = page.locator(".exact-popover-value")
    assert exact.inner_text() == fingerprint
    assert exact.get_attribute("dir") == "ltr"
    assert all(char in "0123456789abcdefABCDEF" for char in exact.inner_text())
    page.locator(".exact-copy").click()
    assert page.evaluate("window.copiedExact") == [fingerprint]
    page.keyboard.press("Escape")
    assert "زمان واقعی" in lineage.inner_text() and "baseline" not in lineage.inner_text().lower()
    assert "مبنای" in lineage.inner_text() or "تاریخ مبنا" in lineage.inner_text()
    assert "در دسترس نیست" in lineage.inner_text()


def test_table_exact_sort_search_pagination_and_csv_use_full_accepted_snapshot(ui):
    page = ui["page"]
    _select(page)
    report = _expand_report(_request(ui["analysis"]).get_json())
    excluded = report["detail_rows"][-1]
    excluded.update(state="INVALID_INPUT", unit_cost=None, prediction=None, projected_cost=None,
                    bom_total=None, issues=[{"state": "INVALID_INPUT", "code": "INVALID_PERCENTAGE",
                                             "message": "درصد ضایعات این پیکربندی نامعتبر است."}])
    report["breakdowns"]["products"] = copy.deepcopy(report["detail_rows"][:-1])
    report.update(state="PARTIAL")
    report["coverage"].update(calculated=26, excluded=1, percentage="96.29629629629629629629629630")
    report["kpis"].update(projected_total=None, partial_total="156039333333", partial_total_label="مجموع جزئی")
    report["kpis"]["weighted_average"]["state"] = "PARTIAL"
    report["kpis"]["top_cost_driver"]["state"] = "PARTIAL"
    _fulfill(page, report)
    _analyze(page)
    requests = []
    page.on("request", lambda request: requests.append(request.url))
    total = page.locator("#totalCost").get_attribute("data-raw")
    coverage = page.locator("#coverageSummary").inner_text()
    assert page.locator("#detailTable tbody tr[data-state]").count() == 10
    page.select_option("#tableSort", "unit_cost-desc")
    actual = page.locator("#detailTable td[data-value-key='unit_cost'] [data-raw]").evaluate_all(
        "elements => elements.map(element => element.dataset.raw)")
    expected = sorted((row["unit_cost"] for row in report["detail_rows"] if row["unit_cost"] is not None), key=Decimal, reverse=True)
    assert actual == expected[:10]
    page.locator("#tableNext").click()
    assert page.locator("#tablePrevious").is_enabled()
    assert page.locator("#detailTable td[data-value-key='unit_cost'] [data-raw]").first.get_attribute("data-raw") == expected[10]
    page.select_option("#tablePageSize", "25")
    assert page.locator("#detailTable tbody tr[data-state]").count() == 25
    # Search uses the source identity, while number localization is presentation.
    page.fill("#tableSearch", "خانواده 27")
    assert page.locator("#detailTable tbody tr[data-state]").count() == 1
    assert "نامعتبر" in page.locator("#detailTable").inner_text()
    page.select_option("#tableStateFilter", "OK")
    assert page.locator("#detailTable tbody tr[data-state]").count() == 0
    page.select_option("#tableStateFilter", "excluded")
    assert page.locator("#detailTable tbody tr[data-state]").count() == 1
    raw, exported = _download(page)
    assert len(exported) == 27
    for original, row in zip(report["detail_rows"], exported):
        assert row["category"] == original["identity"]["category"]
        assert row["subcategory"] == original["identity"]["subcategory"]
        assert row["unit_cost"] == (original["unit_cost"] or "")
        assert row["prediction"] == (original["prediction"] or "")
        assert row["projected_cost"] == (original["projected_cost"] or "")
    assert exported[-1]["row_state"] == "INVALID_INPUT"
    summary = next(row for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))) if row["row_type"] == "kpis")
    assert summary["weighted_average"] == "9007199254740993.12345678901234567890"
    assert page.locator("#totalCost").get_attribute("data-raw") == total
    assert page.locator("#coverageSummary").inner_text() == coverage
    assert not any(urlparse(url).path == "/api/cost_analysis" for url in requests)
    assert not ui["errors"]


@pytest.mark.parametrize("kind", ["signed", "zero"])
def test_real_signed_and_zero_driver_charts_retain_backend_shares_and_all_groups(ui, kind):
    page, fixture = ui["page"], ui["analysis"]
    if kind == "zero":
        for product in ("A", "B"):
            _write(fixture.factory / "category" / "sub" / f"{product}.json", _bom([0]))
        _set_pools(fixture)
    _real_echarts(page)
    _select(page)
    report = _request(fixture).get_json()
    if kind == "signed":
        for index, driver in enumerate(report["breakdowns"]["drivers"]):
            driver["value"] = ["-100.0000000000000000000001", "250.0000000000000000000001"][index] if index < 2 else "0.000"
            driver["share"] = ["-66.66666666666666666666666667", "166.6666666666666666666666667"][index] if index < 2 else "0"
        report["kpis"]["projected_total"] = "150"
        report["kpis"]["top_cost_driver"].update(id=report["breakdowns"]["drivers"][1]["id"],
            value="250.0000000000000000000001", share="166.6666666666666666666666667",
            tied_ids=[report["breakdowns"]["drivers"][1]["id"]])
    _fulfill(page, report)
    _analyze(page)
    driver = _chart_options(page)[1]
    assert driver["series"][0]["type"] == "bar"
    assert _chart_values(driver) == [float(row["value"]) for row in report["breakdowns"]["drivers"]]
    assert page.locator("#driverDonutView").is_disabled()
    assert page.locator("#driverTable tbody tr[data-driver]").count() == 7
    tooltip = page.evaluate("""() => echarts.getInstanceByDom(document.getElementById('driverCompositionChart'))
      .getOption().tooltip[0].formatter({dataIndex:0})""")
    first = report["breakdowns"]["drivers"][0]
    exact = page.evaluate("raw => DashboardNumbers.exact(raw,'IRR/period')", first["value"])
    assert exact in tooltip
    if kind == "signed":
        share = page.evaluate("raw => DashboardNumbers.exact(raw,'percentage')", first["share"])
        assert share in tooltip
        assert "۱۶۶٫۶۷٪" in page.locator("#driverTable").inner_text()
        assert "−۶۶٫۶۷٪" in page.locator("#driverTable").inner_text()
    else:
        assert first["share"] is None and "در دسترس نیست" in tooltip
    assert not ui["errors"]


def test_real_many_product_chart_focus_reset_dominant_bom_and_safe_tooltips(ui):
    page = ui["page"]
    _real_echarts(page)
    _select(page)
    report = _expand_report(_request(ui["analysis"]).get_json())
    report["kpis"]["top_cost_driver"].update(value="156039333330", share="99.999999998077408",
                                             tie=True, tied_ids=["BOM", "Payroll"])
    report["breakdowns"]["drivers"][0].update(value="156039333330", share="99.999999998077408")
    # A low contribution stays discoverable without inflating its visual share.
    for driver in report["breakdowns"]["drivers"][1:]:
        driver.update(value="0.50000000000000000001", share="0.00000000032043041111")
    report["detail_rows"][0]["identity"]["product"] = '<img src=x onerror="window.xss=1">'
    report["breakdowns"]["products"] = copy.deepcopy(report["detail_rows"])
    _fulfill(page, report)
    _analyze(page)
    options = _chart_options(page)
    assert len(options[0]["series"][0]["data"]) == 27
    assert len(options[0]["dataZoom"]) == 2
    assert len(set(options[0]["yAxis"][0]["data"])) == 27
    assert all("خانواده" in value and "دسته" in value for value in options[0]["yAxis"][0]["data"])
    assert page.locator("#driverTable tbody tr[data-driver]").count() == 7
    colors = page.locator("#driverTable .driver-dot").evaluate_all("elements => elements.map(element => getComputedStyle(element).backgroundColor)")
    assert len(colors) == len(set(colors)) == 7
    assert "هم‌رتبه" in page.locator("#topDriver").locator("..").inner_text()
    assert page.locator("#driverDonutView").is_enabled()
    page.locator("#driverDonutView").click()
    assert _chart_options(page)[1]["series"][0]["type"] == "pie"
    assert page.locator("#driverDonutView").get_attribute("aria-pressed") == "true"
    page.locator("#driverBarView").click()
    requests = []
    page.on("request", lambda request: requests.append(request.url))
    accepted_total = page.locator("#totalCost").get_attribute("data-raw")
    # Keyboard equivalents address every composite identity, including rows on
    # later pages. The controller reveals its details and clears table filters.
    alternative = page.locator("#productChartTable").locator("..").locator("..")
    if alternative.evaluate("element => element.tagName === 'DETAILS'"):
        alternative.locator(":scope > summary").click()
    target = page.locator(".chart-product-focus").nth(18)
    identity = target.get_attribute("data-identity")
    target.press("Enter")
    row = page.locator("#detailTable tr[data-identity]").filter(
        has=page.locator(".row-details[open]"))
    assert row.count() == 1 and row.get_attribute("data-identity") == identity
    assert page.locator("#tableResetFocus").is_visible()
    page.locator("#tableResetFocus").click()
    assert not page.locator("#tableResetFocus").is_visible()
    # Use a real canvas pointer event, with coordinates supplied by ECharts.
    page.locator("#productCostChart").scroll_into_view_if_needed()
    position = page.evaluate("""() => {
      const element=document.getElementById('productCostChart');
      const chart=echarts.getInstanceByDom(element), value=chart.getOption().series[0].data[0];
      const point=chart.convertToPixel({seriesIndex:0},[value/2,0]), rect=element.getBoundingClientRect();
      return {x:rect.left+point[0],y:rect.top+point[1]};
    }""")
    page.mouse.click(position["x"], position["y"])
    assert page.locator("#tableResetFocus").is_visible()
    assert page.locator("#detailTable .row-details[open]").count() == 1
    page.locator("#chartFocusReset").click()
    assert not page.locator("#tableResetFocus").is_visible()
    assert page.locator("#totalCost").get_attribute("data-raw") == accepted_total
    assert not any(urlparse(url).path == "/api/cost_analysis" for url in requests)
    tooltip = page.evaluate("""() => {
      const chart=echarts.getInstanceByDom(document.getElementById('productCostChart'));
      const labels=chart.getOption().yAxis[0].data;
      const index=labels.findIndex(label => label.includes('<img'));
      return chart.getOption().tooltip[0].formatter({dataIndex:index});
    }""")
    assert '<img src=x onerror="window.xss=1">' in tooltip
    assert FACTORY in tooltip and "خانواده 1" in tooltip
    assert page.locator("#costDashboard img,#costDashboard script").count() == 0
    assert page.evaluate("window.xss || 0") == 0
    assert not ui["errors"]


def test_chart_initialization_failure_keeps_table_exact_values_and_csv(ui):
    page = ui["page"]
    _select(page)
    page.evaluate("window.echarts = {init: () => {throw new Error('fixture-chart-failure');}}")
    with page.expect_response("**/api/cost_analysis?*") as pending:
        _analyze(page)
    report = pending.value.json()
    assert page.locator("#costDashboard").is_visible()
    assert "نمودار در دسترس نیست" in page.locator("#productCostChart").locator("..").inner_text()
    assert page.locator("#detailTable tbody tr[data-state]").count() == 2
    page.locator("#totalCost").press("Enter")
    assert page.locator(".exact-popover").is_visible()
    page.keyboard.press("Escape")
    _, rows = _download(page)
    assert [row["unit_cost"] for row in rows] == [row["unit_cost"] for row in report["detail_rows"]]
    assert not ui["errors"]


def test_accepted_snapshot_is_immutable_and_dom_edits_never_change_export(ui):
    page = ui["page"]
    page.add_init_script("""(() => {
      let shippedReport;
      Object.defineProperty(window, 'DashboardReport', {configurable:true,
        get: () => shippedReport,
        set: report => {shippedReport={...report, render:(...args) => {
          window.acceptedTestSnapshot=args[0]; return report.render(...args);
        }};}});
    })();""")
    page.reload(wait_until="networkidle")
    _select(page)
    with page.expect_response("**/api/cost_analysis?*") as pending:
        _analyze(page)
    report = pending.value.json()
    assert page.evaluate("""() => Object.isFrozen(acceptedTestSnapshot) &&
      Object.isFrozen(acceptedTestSnapshot.detail_rows) && Object.isFrozen(acceptedTestSnapshot.detail_rows[0]) &&
      Object.isFrozen(acceptedTestSnapshot.kpis.weighted_average)""")
    page.evaluate("""() => {
      acceptedTestSnapshot.detail_rows[0].unit_cost='1';
      document.getElementById('totalCost').textContent='1';
      document.querySelector('#detailTable [data-raw]').dataset.raw='1';
    }""")
    _, rows = _download(page)
    assert rows[0]["unit_cost"] == report["detail_rows"][0]["unit_cost"]
    assert page.evaluate("acceptedTestSnapshot.detail_rows[0].unit_cost") == report["detail_rows"][0]["unit_cost"]


@pytest.mark.parametrize("kind", ["long-dominant", "partial"])
def test_redesigned_real_charts_desktop_and_mobile_visual_evidence(ui, kind):
    page, fixture = ui["page"], ui["analysis"]
    if kind == "partial":
        _write(fixture.factory / "category" / "sub" / "B.json", _bom([40], loss=101))
    _real_echarts(page)
    _select(page)
    report = _request(fixture).get_json()
    if kind == "long-dominant":
        report = _expand_report(report, count=18)
        report["breakdowns"]["drivers"][0].update(value="156039333330.12345678901234567890", share="99.999999998077408")
        report["kpis"]["top_cost_driver"].update(value="156039333330.12345678901234567890", share="99.999999998077408")
        for driver in report["breakdowns"]["drivers"][1:]:
            driver.update(value="0.50000000000000000001", share="0.00000000032043041111")
        _fulfill(page, report)
    _analyze(page)
    assert page.locator("#productCostChart canvas").count() > 0
    assert page.locator("#driverCompositionChart canvas").count() > 0
    assert page.locator(".report-kpi").count() == 4
    assert page.locator("#reportTechnical").get_attribute("open") is None
    assert page.locator("#reportPools").get_attribute("open") is None
    if kind == "partial":
        assert page.locator("#reportStatus").get_attribute("data-state") == "PARTIAL"
        assert "مجموع جزئی" in page.locator("#totalCostLabel").inner_text()
        assert page.locator("#detailTable tr.report-excluded").count() == 1
    else:
        assert page.locator("#totalCost").inner_text().startswith("۱۵۶٫۰۴ میلیارد ریال")
    folder = Path(os.environ.get("DASHBOARD_REDESIGN_EVIDENCE_DIR", ROOT / "work" / "redesign-evidence"))
    folder.mkdir(parents=True, exist_ok=True)
    page.evaluate("document.fonts.ready")
    for device, viewport in (("desktop", {"width": 1440, "height": 1100}),
                             ("mobile", {"width": 390, "height": 844})):
        page.set_viewport_size(viewport)
        page.wait_for_function("document.documentElement.scrollWidth <= window.innerWidth + 1")
        if device == "mobile":
            page.wait_for_function("document.querySelector('#mainSidebar').getBoundingClientRect().left >= window.innerWidth - 1")
        page.wait_for_timeout(850)  # ECharts and fonts have completed their layout.
        page.evaluate("window.scrollTo(0,0)")
        heights = page.locator(".report-kpi").evaluate_all("elements => elements.map(element => element.getBoundingClientRect().height)")
        assert max(heights) < 230
        page.screenshot(path=str(folder / f"dashboard-{kind}-{device}.png"), full_page=True)
    # The sidebar narrows the content around the four-card breakpoint. Check
    # the number boxes themselves: a page overflow check alone can miss text
    # running into a neighboring card without expanding the document.
    for width in (1251, 1024):
        page.set_viewport_size({"width": width, "height": 1100})
        page.wait_for_timeout(250)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        boxes = page.locator(".report-kpi > .report-number").evaluate_all("""elements => elements.map(element => ({
          id:element.id,text:element.textContent,width:element.clientWidth,contentWidth:element.scrollWidth,
          fontSize:getComputedStyle(element).fontSize,parentWidth:element.parentElement.clientWidth}))""")
        assert all(box["contentWidth"] <= box["width"] + 1 for box in boxes), json.dumps(
            {"viewport": width, "boxes": boxes}, ensure_ascii=False)
    assert not ui["errors"]


def test_mobile_chart_keyboard_focus_exposes_row_details_and_can_reset(ui):
    page = ui["page"]
    _real_echarts(page)
    _select(page)
    report = _expand_report(_request(ui["analysis"]).get_json())
    _fulfill(page, report)
    _analyze(page)
    page.set_viewport_size({"width": 390, "height": 844})
    page.emulate_media(reduced_motion="reduce")
    alternative = page.locator("#productChartTable").locator("..").locator("..")
    alternative.locator(":scope > summary").click()
    target = page.locator(".chart-product-focus").nth(20)
    identity = target.get_attribute("data-identity")
    requests = []
    page.on("request", lambda request: requests.append(request.url))
    target.press("Enter")
    summary = page.locator("#detailTable .row-details[open] > summary")
    assert summary.count() == 1
    assert summary.locator("xpath=ancestor::tr").get_attribute("data-identity") == identity
    assert summary.evaluate("element => document.activeElement === element")
    page.wait_for_function("""() => {
      const element=document.querySelector('#detailTable .row-details[open] > summary');
      const rect=element.getBoundingClientRect();
      return rect.left >= -1 && rect.right <= innerWidth + 1 && rect.top >= -1 && rect.bottom <= innerHeight + 1;
    }""")
    assert page.locator("#tableScrollHint").is_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    page.locator("#tableResetFocus").click()
    assert not page.locator("#tableResetFocus").is_visible()
    assert not any(urlparse(url).path == "/api/cost_analysis" for url in requests)


def test_excluded_not_applicable_row_keeps_distinct_status_and_blank_csv_values(ui):
    page, fixture = ui["page"], ui["analysis"]
    _write(fixture.factory / "category" / "sub" / "B.json", _bom([40], loss=101))
    _select(page)
    report = _request(fixture).get_json()
    excluded = next(row for row in report["detail_rows"] if row["state"] != "OK")
    # Exercise the existing typed API state; accounting values remain the real
    # PARTIAL fixture values and the excluded quantities remain null.
    excluded["state"] = "NOT_APPLICABLE"
    excluded["issues"] = [{"state": "NOT_APPLICABLE", "code": "CALCULATION_NOT_APPLICABLE",
                           "message": "محاسبه برای این پیکربندی قابل اعمال نیست."}]
    _fulfill(page, report)
    _analyze(page)
    row = page.locator("#detailTable tr[data-state='NOT_APPLICABLE']")
    assert row.count() == 1
    for key in ("unit_cost", "prediction", "projected_cost"):
        value = row.locator(f"td[data-value-key='{key}']")
        assert "قابل اعمال نیست" in value.inner_text()
        assert value.locator("[data-raw]").count() == 0
    row.locator(".row-details summary").click()
    assert "قابل اعمال نیست" in row.locator(".row-details").inner_text()
    _, exported = _download(page)
    original = next(value for value in exported if value["row_state"] == "NOT_APPLICABLE")
    assert original["unit_cost"] == original["prediction"] == original["projected_cost"] == ""
    assert "مجموع جزئی" in page.locator("#totalCostLabel").inner_text()
    assert not ui["errors"]
