"""PR-10 PRIMARY release gate: actual Jinja, shipped business JS and Flask APIs.

No asset rewriting or legacy endpoint adapters. Only pinned presentation CDN
bytes are cached for deterministic screenshots; all Dashboard code is served by
Flask unchanged. Transport fault/race tests intercept fetch responses explicitly.
Never import app.py or access the repository's operational Data/instance stores.
"""
import copy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import threading
from time import perf_counter
from urllib.parse import parse_qs, urlparse

import pytest
from werkzeug.serving import make_server

from test_dashboard_cost_analysis import FACTORY, _bom, _client, _reference, _write, analysis
from test_dashboard_sensitivity import sensitivity, _g2_fixture, _material_fixture, _parameter
from test_dashboard_frontend import _clipboard, _install_pending_fetch, _resolve, _select
from test_dashboard_sensitivity_frontend import _add, _choose
from test_dashboard_visual_frontend import experiment, open_panel, panel
from test_dashboard_visual_analysis import LAB, VISUALS, run as api_run
from utils.localization import format_jalali_date
from utils.product_hierarchy_service import ProductHierarchyService

ROOT = Path(__file__).resolve().parents[1]
ASSET_MAP = {
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css': ('bootstrap.min.css', 'text/css'),
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js': ('bootstrap.bundle.min.js', 'application/javascript'),
    'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css': ('fontawesome/all.min.css', 'text/css'),
    **{f'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/webfonts/{name}.woff2':
       (f'fontawesome/{name}.woff2', 'font/woff2')
       for name in ['fa-solid-900', 'fa-regular-400', 'fa-brands-400']},
}


def inventory(root):
    """Assert file content/population plus every file AND directory mtime."""
    return {p.relative_to(root).as_posix():
            ('file', hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
            if p.is_file() else ('directory', p.stat().st_mtime_ns)
            for p in root.rglob('*')}


@pytest.fixture(scope='module')
def release_browser():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        if os.environ.get('DASHBOARD_REQUIRE_BROWSER') == '1':
            pytest.fail('Release gate requires requirements-browser.txt and Chromium')
        pytest.skip('Install requirements-browser.txt and run scripts/setup_dashboard_browser.py')
    os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(ROOT / 'work/browser-cache'))
    with sync_playwright() as runtime:
        selected = os.environ.get('DASHBOARD_CHROMIUM_PATH')
        cached = Path(runtime.chromium.executable_path)
        executable = selected or (str(cached) if cached.is_file() else shutil.which('chromium') or shutil.which('chromium-browser'))
        if not executable:
            if os.environ.get('DASHBOARD_REQUIRE_BROWSER') == '1':
                pytest.fail('Required Chromium missing: run scripts/setup_dashboard_browser.py')
            pytest.skip('Chromium unavailable: run scripts/setup_dashboard_browser.py')
        browser = runtime.chromium.launch(executable_path=executable, headless=True,
                                          args=['--no-sandbox', '--disable-dev-shm-usage'])
        yield browser
        browser.close()


@pytest.fixture
def release_ui(sensitivity, monkeypatch, release_browser, request, tmp_path):
    env = sensitivity
    if getattr(request, 'param', None) == 'benchmark':
        from scripts.dashboard_benchmark_fixture import install_fixture, create_app
        env = install_fixture(tmp_path / 'browser-benchmark')
        env.app, env.client = create_app(env)
        env.binding = env.bindings
        monkeypatch.setenv('APP_DATA_FILE', str(env.profiles))
        monkeypatch.setenv('COSTING_DATA_ROOT', str(env.data))
        monkeypatch.setenv('COSTING_PERIOD_BINDINGS_FILE', str(env.bindings))
    app = env.app
    app.template_folder = str(ROOT / 'templates')
    app.static_folder = str(ROOT / 'static')
    app.jinja_env.filters['jalali_date'] = format_jalali_date
    app.add_url_rule('/logout', endpoint='auth.logout', view_func=lambda: 'logout')
    app.context_processor(lambda: {'module_navigation': {'dashboard': True}, 'user': 'کاربر آزمون'})
    monkeypatch.setattr('modules.dashboard.routes.ProductHierarchyService',
                        lambda *args, **kwargs: ProductHierarchyService(env.data / 'Factories'))
    server = make_server('127.0.0.1', 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    context = release_browser.new_context(viewport={'width': 1440, 'height': 1100},
                                          timezone_id='Asia/Tehran', has_touch=True, accept_downloads=True)
    cookie = env.client.get_cookie('session')
    context.add_cookies([{'name': 'session', 'value': cookie.value, 'url': base}])
    # Instrument platform resource lifecycle, without replacing business assets.
    context.add_init_script("""(() => {
        const add=window.addEventListener.bind(window),remove=window.removeEventListener.bind(window),listeners=new Set();
        window.addEventListener=(type,fn,options)=>{if(type==='resize')listeners.add(fn);return add(type,fn,options);};
        window.removeEventListener=(type,fn,options)=>{if(type==='resize')listeners.delete(fn);return remove(type,fn,options);};
        const observers=new Set(),Native=window.ResizeObserver;
        window.ResizeObserver=class extends Native {
            observe(...args){observers.add(this);return super.observe(...args);}
            disconnect(){observers.delete(this);return super.disconnect();}
        };
        document.addEventListener('toggle',()=>{window.releaseToggleAt=performance.now();},true);
        window.releaseResources=()=>({resizeListeners:listeners.size,resizeObservers:observers.size,
            liveCharts:window.echarts?Array.from(document.querySelectorAll('.report-chart')).filter(n=>echarts.getInstanceByDom(n)).length:0});
    })();""")
    page = context.new_page()
    page.set_default_timeout(10000)
    errors, requests, assets = [], [], {}
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('request', lambda r: requests.append((r.method, urlparse(r.url).path)))
    def capture(response):
        path = urlparse(response.url).path
        if path.startswith('/static/js/dashboard-'):
            assets[path] = hashlib.sha256(response.body()).hexdigest()
    page.on('response', capture)
    def presentation(route):
        spec = ASSET_MAP.get(route.request.url)
        if not spec:
            route.abort()
            return
        path = ROOT / 'work/vendor' / spec[0]
        if not path.is_file():
            pytest.fail('Verified presentation cache missing: run scripts/setup_dashboard_browser.py')
        route.fulfill(content_type=spec[1], body=path.read_bytes())
    page.route('https://**/*', presentation)
    expected = [inventory(env.root)]
    page.goto(base + '/dashboard', wait_until='networkidle')
    assert page.evaluate('echarts.version') == '5.6.0'
    ui = {'page': page, 'context': context, 'base': base, 'analysis': env,
          'errors': errors, 'requests': requests,
          'checkpoint': lambda: expected.__setitem__(0, inventory(env.root))}
    try:
        yield ui
    finally:
        context.close()
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()
    assert not errors, errors
    assert inventory(env.root) == expected[0], 'Browser/API changed fixture content, inventory or mtimes'
    assert all(method in {'GET', 'HEAD'} or path == LAB for method, path in requests), requests
    # Require every shipped Dashboard business script, byte-for-byte.
    scripts = [p for p in (ROOT / 'static/js').glob('dashboard-*.js')]
    template = (ROOT / 'templates/dashboard/dashboard.html').read_text()
    required = {p for p in scripts if f'js/{p.name}' in template}
    assert len(required) >= 12
    for path in required:
        assert assets.get('/static/js/' + path.name) == hashlib.sha256(path.read_bytes()).hexdigest()


def analyze(ui):
    page = ui['page']
    with page.expect_response(lambda r: urlparse(r.url).path == VISUALS) as pending:
        page.locator('#analyzeBtn').press('Enter')
    response = pending.value
    page.wait_for_function("document.querySelector('#analysisStatus').dataset.state !== 'LOADING'")
    assert response.status == 200, response.text()
    return response.json(), parse_qs(urlparse(response.url).query)


def lab_run(ui):
    page = ui['page']
    with page.expect_response(lambda r: urlparse(r.url).path == LAB) as pending:
        page.locator('#sens-run').press('Enter')
    response = pending.value
    page.wait_for_function("document.querySelector('#sens-status').dataset.state !== 'LOADING'")
    assert response.status == 200, response.text()
    assert page.locator('#sens-status').get_attribute('data-state') == 'OK'
    return response.json(), response.request.post_data_json


def downloaded(page, selector):
    with page.expect_download() as pending:
        page.locator(selector).press('Enter')
    raw = Path(pending.value.path()).read_bytes()
    assert raw.startswith(b'\xef\xbb\xbf') and b'\r\n' in raw
    return raw, list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))


def chart(page, p):
    handle = p.locator('.report-chart').element_handle()
    page.wait_for_function('(n)=>!!echarts.getInstanceByDom(n)', arg=handle)
    return p.locator('.report-chart')


def screenshot(page, selector, name):
    target = os.environ.get('DASHBOARD_UI_EVIDENCE_DIR')
    if not target:
        return
    root = Path(target)
    root.mkdir(parents=True, exist_ok=True)
    page.evaluate('document.fonts.ready')
    anchor = page.locator(selector).first
    anchor.evaluate("e=>e.scrollIntoView({block:'start',behavior:'instant'})")
    if page.viewport_size['width'] < 992:
        page.wait_for_function("document.querySelector('#mainSidebar').getBoundingClientRect().left >= innerWidth - 1")
    page.wait_for_timeout(300)
    # Sidebar/canvas reflow can move the browser's scroll anchor after resizing.
    anchor.evaluate("e=>e.scrollIntoView({block:'start',behavior:'instant'})")
    page.screenshot(path=str(root / (name + '.png')))


def save_lifecycle(kind, document):
    target = Path(os.environ.get('DASHBOARD_BROWSER_LIFECYCLE_FILE',
                                 str(ROOT / 'work/pr10-evidence/browser-lifecycle.json')))
    target.parent.mkdir(parents=True, exist_ok=True)
    previous = json.loads(target.read_text()) if target.is_file() else {}
    evidence = {key: previous[key] for key in ('cost', 'sensitivity') if key in previous}
    evidence[kind] = document
    target.write_text(json.dumps(evidence, indent=2))


def test_default_cost_journey_partial_jalali_table_and_full_csv(release_ui):
    ui = release_ui; page = ui['page']; env = ui['analysis']
    _write(env.factory / 'category/sub/B.json', _bom([1], loss=101)); ui['checkpoint']()
    assert page.locator('html').get_attribute('dir') == 'rtl'
    assert page.locator('#analyzeBtn').is_disabled()
    assert page.locator('#factorySelect option[value="__ALL__"]').count() == 0
    page.select_option('#factorySelect', FACTORY)
    page.wait_for_function("!document.querySelector('#categorySelect').disabled")
    assert page.locator('#categorySelect').input_value() == ''
    assert page.locator('#subcategorySelect').is_disabled() and page.locator('#analyzeBtn').is_disabled()
    page.select_option('#categorySelect', '__ALL__')
    page.wait_for_function("!document.querySelector('#subcategorySelect').disabled")
    assert page.locator('#subcategorySelect').input_value() == ''
    page.select_option('#subcategorySelect', '__ALL__')
    page.wait_for_function("!document.querySelector('#productSelect').disabled")
    assert page.locator('#productSelect').input_value() == ''
    page.select_option('#productSelect', '__ALL__')
    page.wait_for_function("!document.querySelector('#analyzeBtn').disabled")
    assert page.locator('#startDate').input_value() == format_jalali_date('2026-10-01')
    assert page.locator('#endDate').input_value() == format_jalali_date('2026-12-31')
    original = page.locator('#startDate').input_value()
    page.locator('#startDate').fill('۱۴۰۵/۰۷/۱۰')
    assert page.locator('#analyzeBtn').is_disabled()
    page.locator('#startDate').fill(original)
    body, query = analyze(ui); report = body['analysis']
    assert query['start'] == ['2026-10-01'] and query['end'] == ['2026-12-31']
    assert query['product'] == query['category'] == query['subcategory'] == ['__ALL__']
    assert report['state'] == page.locator('#analysisStatus').get_attribute('data-state') == 'PARTIAL'
    assert report['coverage'] == {'configured': 2, 'calculated': 1, 'excluded': 1, 'percentage': '50'}
    for selector, value in [('#totalCost', report['kpis']['partial_total']), ('#avgCost', report['kpis']['weighted_average']['value']),
                            ('#productCount', '2'), ('#coveragePercentage', report['coverage']['percentage'])]:
        assert page.locator(selector).get_attribute('data-raw') == value
    assert 'مجموع جزئی' in page.locator('#totalCostLabel').inner_text()
    page.select_option('#tableStateFilter', 'excluded')
    assert page.locator('#detailTable tbody tr[data-state]').count() == 1
    assert page.locator('#detailTable tbody tr[data-state="OK"]').count() == 0
    page.select_option('#tableSort', 'unit_cost-desc'); page.select_option('#tablePageSize', '25')
    page.locator('#tableSearch').fill('B')
    before = len(ui['requests']); _, rows = downloaded(page, '#downloadCsvBtn')
    assert len(ui['requests']) == before, 'CSV requested a different report'
    configurations = [r for r in rows if r['row_type'] == 'configuration']
    assert len(configurations) == 2
    assert {r['product'] for r in configurations} == {'A', 'B'}
    assert page.locator('#totalCost').get_attribute('data-raw') == report['kpis']['partial_total']
    screenshot(page, '#costDashboard', 'partial-desktop')
    page.set_viewport_size({'width': 390, 'height': 844}); screenshot(page, '#costDashboard', 'partial-mobile')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_chart_click_drill_linked_focus_retains_scope_kpis_and_csv(release_ui):
    ui = release_ui; page = ui['page']; _material_fixture(ui['analysis']); ui['checkpoint']()
    _select(page); body, _ = analyze(ui)
    original_csv, _ = downloaded(page, '#downloadCsvBtn')
    original_total = page.locator('#totalCost').get_attribute('data-raw')
    p = panel(page, 'ترکیب هزینه محصولات', '#costDashboard'); node = chart(page, p)
    node.scroll_into_view_if_needed()
    point = node.evaluate("""n=>{const c=echarts.getInstanceByDom(n),o=c.getOption(),amount=o.series[0].data[0].value;
        const p=c.convertToPixel({xAxisIndex:0,yAxisIndex:0},[amount/2,0]),r=n.getBoundingClientRect();return [r.x+p[0],r.y+p[1]];}""")
    page.mouse.click(*point)
    assert page.locator('.visual-focus').is_visible()
    assert page.locator('#detailTable .report-focus-row').count() == 1
    assert 'A' in page.locator('#tableFocusStatus').inner_text()
    assert page.locator('#totalCost').get_attribute('data-raw') == original_total
    focused_csv, _ = downloaded(page, '#downloadCsvBtn'); assert focused_csv == original_csv
    page.get_by_role('button', name='بازگشت / پاک کردن تمرکز', exact=True).press('Enter')
    assert not page.locator('.visual-focus').is_visible()
    p = open_panel(page, 'کاوش سلسله‌مراتب هزینه', '#costDashboard'); chart(page, p)
    for name in ['category', 'sub', 'A']:
        p.get_by_role('button', name='بررسی ' + name, exact=True).press('Enter')
    assert page.locator('.visual-focus').is_visible()
    assert page.locator('#detailTable .report-focus-row').count() == 1
    assert len(body['visuals']['materials'][0]['rows']) == 3  # 2 independent A BOM rows plus B.
    assert page.get_by_text('ردیف‌های مستقل BOM', exact=True).count() == 1
    assert page.locator('#productSelect').input_value() == '__ALL__'
    page.get_by_role('button', name='بازگشت / پاک کردن تمرکز', exact=True).press('Enter')
    for title in ['پارتوی مواد', 'محصول × عامل', 'تولید و هزینه']:
        p = open_panel(page, title, '#costDashboard'); chart(page, p)
        assert p.locator('tbody tr').count() > 0


def test_ab_three_comparisons_waterfalls_exact_exports_and_reset(release_ui):
    ui = release_ui; page = ui['page']; env = ui['analysis']; _g2_fixture(env); ui['checkpoint']()
    prediction = _parameter(env, 'prediction:'); share = _parameter(env, 'category_share:'); _choose(ui)
    for selector in ['#sens-category', '#sens-subcategory', '#sens-product']:
        assert page.locator(selector + ' option[value="__ALL__"]').count() == 0
    _add(page, prediction, '۳۰'); page.select_option('#lab-draft-scenario', 'B'); _add(page, share, '۲۵')
    page.select_option('#lab-draft-scenario', 'A')
    assert page.locator('[data-override-value]').input_value() == '۳۰'
    body, submitted = lab_run(ui)
    assert submitted['product'] == _reference('category', 'sub', 'A')
    assert submitted['scenarios'][0]['overrides'][0]['value'] == '30'
    assert submitted['scenarios'][1]['overrides'][0]['value'] == '25'
    expected = {'A_minus_baseline': ('-50', '500'), 'B_minus_baseline': ('100', '1000'), 'B_minus_A': ('150', '500')}
    for direction, (unit_delta, period_delta) in expected.items():
        result = body['comparisons'][direction]
        assert result['unit_cost']['amount'] == unit_delta and result['projected_cost']['amount'] == period_delta
        title = {'A_minus_baseline': 'خط‌مبنا ← A', 'B_minus_baseline': 'خط‌مبنا ← B', 'B_minus_A': 'A ← B'}[direction]
        p = open_panel(page, 'آبشار هزینه واحد: ' + title); node = chart(page, p)
        options = node.evaluate('n=>echarts.getInstanceByDom(n).getOption()')
        assert len(options['series']) == 2
        assert options['series'][1]['data'][-1]['exactRow']['value'] == result['waterfall']['target']
    _, rows = downloaded(page, '#sens-export')
    for direction, (unit_delta, period_delta) in expected.items():
        assert any(r['row_type'] == 'delta' and r['scope'] == direction and r['metric'] == 'unit_cost' and r['value'] == unit_delta for r in rows)
        assert any(r['row_type'] == 'delta' and r['scope'] == direction and r['metric'] == 'projected_cost' and r['value'] == period_delta for r in rows)
    assert all(r['non_persistent'] == 'true' and r['period_id'] == 'P' for r in rows)
    screenshot(page, '#sens-results', 'ab-desktop')
    page.set_viewport_size({'width': 390, 'height': 844}); screenshot(page, '#sens-results', 'ab-mobile')
    page.locator('#sens-reset').press('Enter')
    assert page.locator('#sens-baseline').is_visible() and not page.locator('#sens-results').is_visible()
    assert page.locator('#sens-export').is_disabled() and page.locator('#sens-draft .sens-draft-item').count() == 0
    page.select_option('#lab-draft-scenario', 'B'); assert page.locator('#sens-draft .sens-draft-item').count() == 0


@pytest.mark.parametrize('kind', ['tornado', 'one_factor', 'two_factor'])
def test_experiments_shipped_charts_exact_backend_samples_and_viewports(release_ui, kind):
    ui = release_ui; page = ui['page']; env = ui['analysis']; _g2_fixture(env); ui['checkpoint']()
    share = _parameter(env, 'category_share:'); prediction = _parameter(env, 'prediction:'); _choose(ui)
    experiment(page, kind, [share, prediction], [('25', '50')] if kind == 'tornado' else ['25\n50', '10\n30'])
    body, _ = lab_run(ui); e = body['experiment']
    assert e['valid_count'] == (4 if kind == 'two_factor' else 2)
    assert [p['unit_cost'] for p in e['points']] == (['200', '100', '100', '50'] if kind == 'two_factor' else ['200', '100'])
    title = {'tornado': 'تورنادو', 'one_factor': 'منحنی پاسخ واقعی', 'two_factor': 'نقشه دو عامل'}[kind]
    p = open_panel(page, title + ' — هزینه واحد'); node = chart(page, p)
    options = node.evaluate('n=>echarts.getInstanceByDom(n).getOption()')
    assert options['series'][0]['type'] == {'tornado': 'bar', 'one_factor': 'line', 'two_factor': 'heatmap'}[kind]
    open_panel(page, title + ' — هزینه دوره')
    for width, height, viewport in [(1440, 1100, 'desktop'), (820, 1180, 'tablet'), (390, 844, 'mobile')]:
        page.set_viewport_size({'width': width, 'height': height})
        screenshot(page, '#sens-results details.visual-panel[open]', kind + '-' + viewport)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    _, rows = downloaded(page, '#sens-export')
    assert len([r for r in rows if r['row_type'] == 'experiment' and r['metric'] == 'unit_cost']) == len(e['points'])
    page.locator('#lab-low-0' if kind == 'tornado' else '#lab-raw-0').fill('20')
    assert page.locator('#sens-export').is_disabled() and not page.locator('#sens-results').is_visible()


def test_keyboard_touch_exact_copy_and_tab_disposal(release_ui):
    ui = release_ui; page = ui['page']; _select(page); analyze(ui); _clipboard(page)
    trigger = page.locator('#totalCost'); expected = trigger.get_attribute('data-raw')
    trigger.scroll_into_view_if_needed(); trigger.press('Enter')
    assert page.locator('.exact-popover').is_visible()
    page.locator('.exact-copy').press('Enter')
    page.wait_for_function('window.copiedExact.length===1')
    assert page.evaluate('window.copiedExact[0]') == expected
    page.locator('.exact-copy').press('Escape'); assert not page.locator('.exact-popover').is_visible()
    page.set_viewport_size({'width': 390, 'height': 844}); trigger.scroll_into_view_if_needed(); trigger.tap()
    assert page.locator('.exact-popover').is_visible()
    page.locator('.exact-copy').tap(); page.wait_for_function('window.copiedExact.length===2')
    assert page.evaluate('window.copiedExact[1]') == expected
    page.locator('#cost-tab').press('ArrowLeft')
    assert page.locator('#sensitivity-tab').get_attribute('aria-selected') == 'true'
    assert not page.locator('.exact-popover').is_visible()
    assert page.evaluate('releaseResources().liveCharts') == 0
    page.locator('#sensitivity-tab').press('Home')
    assert page.locator('#cost-tab').get_attribute('aria-selected') == 'true'
    assert page.evaluate('releaseResources().liveCharts') == 2


@pytest.mark.parametrize('mode', ['absent', 'initialization_failure'])
def test_chart_failure_preserves_exact_tables_keyboard_focus_and_csv(release_ui, mode):
    ui = release_ui; page = ui['page']
    if mode == 'absent':
        page.route('**/static/vendor/echarts/echarts-5.6.0.min.js', lambda route: route.abort())
        page.reload(wait_until='networkidle'); assert page.evaluate('typeof echarts') == 'undefined'
    else:
        page.evaluate("window.echarts={init:()=>{throw Error('explicit release failure')}}")
    _select(page); analyze(ui)
    p = panel(page, 'ترکیب هزینه محصولات', '#costDashboard')
    assert p.locator('.report-chart').is_hidden() and p.locator('.visual-exact-table').get_attribute('open') is not None
    p.locator('tbody .btn').first.press('Enter'); assert page.locator('.visual-focus').is_visible()
    assert page.locator('#detailTable .report-focus-row').count() == 1
    _, rows = downloaded(page, '#downloadCsvBtn'); assert len([r for r in rows if r['row_type'] == 'configuration']) == 2
    _choose(ui); lab_run(ui)
    assert page.locator('#sens-export').is_enabled()
    assert page.locator('#sens-results .visual-exact-table[open]').count() >= 2
    assert page.locator('#sens-results .report-chart').filter(visible=True).count() == 0
    downloaded(page, '#sens-export')


@pytest.mark.parametrize('edit', ['A', 'B', 'range', 'reset', 'selection', 'refresh'])
def test_late_real_server_response_cannot_restore_invalidated_lab(release_ui, edit):
    ui = release_ui; page = ui['page']; env = ui['analysis']; _g2_fixture(env); ui['checkpoint']()
    share = _parameter(env, 'category_share:'); _choose(ui)
    if edit == 'B': page.select_option('#lab-draft-scenario', 'B')
    _add(page, share, '25')
    if edit == 'range': experiment(page, 'one_factor', [share], ['25\n50'])
    # Capture a REAL authorized Flask result; delay only transport, deliberately
    # ignoring AbortSignal so client scope/revision guards are independently checked.
    body = api_run(env).json
    _install_pending_fetch(page, LAB)
    page.locator('#sens-run').press('Enter'); page.wait_for_function('testPending.length===1')
    if edit in {'A', 'B'}: page.locator('[data-override-value]').fill('30')
    elif edit == 'range': page.locator('#lab-raw-0').fill('20\n40')
    elif edit == 'reset': page.locator('#sens-reset').press('Enter')
    elif edit == 'refresh':
        assert page.locator('#sens-refresh').is_enabled()
        page.locator('#sens-refresh').press('Enter')
    else: page.select_option('#sens-product', _reference('category', 'sub', 'B'))
    _resolve(page, 0, body)
    page.wait_for_timeout(80)
    assert not page.locator('#sens-results').is_visible() and page.locator('#sens-export').is_disabled()


def test_duplicate_submit_and_cost_scope_race(release_ui):
    ui = release_ui; page = ui['page']; _select(page)
    body = ui['analysis'].client.get(VISUALS, query_string={'factory': FACTORY, 'category': '__ALL__', 'subcategory': '__ALL__', 'product': '__ALL__'}).json
    _install_pending_fetch(page, VISUALS)
    page.locator('#analyzeBtn').press('Enter'); page.wait_for_function('testPending.length===1')
    assert page.locator('#analyzeBtn').is_disabled()
    page.locator('#analysisForm').dispatch_event('submit')
    assert page.evaluate('testPending.length') == 1
    page.select_option('#productSelect', _reference('category', 'sub', 'B')); _resolve(page, 0, body)
    page.wait_for_timeout(80)
    assert not page.locator('#costDashboard').is_visible() and page.locator('#downloadCsvBtn').is_disabled()
    _choose(ui); _install_pending_fetch(page, LAB)
    page.locator('#sens-run').press('Enter'); page.wait_for_function('testPending.length===1')
    assert page.locator('#sens-run').is_disabled()
    page.locator('#sens-run').dispatch_event('click')
    assert page.evaluate('testPending.length') == 1
    page.locator('#sens-reset').press('Enter'); _resolve(page, 0, api_run(ui['analysis']).json)
    assert not page.locator('#sens-results').is_visible()


def test_fresh_sources_new_baseline_notice_and_refresh_invalidation(release_ui):
    ui = release_ui; page = ui['page']; env = ui['analysis']; _material_fixture(env); ui['checkpoint'](); _choose(ui)
    first, _ = lab_run(ui); assert first['baseline']['unit_cost'] == '140.0'
    _material_fixture(env, price=200); ui['checkpoint']()
    fresh, _ = lab_run(ui); assert fresh['baseline']['unit_cost'] == '280.0'
    assert first['source_lineage'] != fresh['source_lineage']
    assert 'تغییر' in page.locator('#sens-status').inner_text()
    with page.expect_response(lambda r: urlparse(r.url).path == '/api/dashboard/sensitivity/parameters'):
        page.locator('#sens-refresh').press('Enter')
    assert not page.locator('#sens-results').is_visible() and page.locator('#sens-export').is_disabled()
    assert page.locator('#sens-baseline').is_visible()


@pytest.mark.parametrize('malformation', ['cost_identity', 'cost_duplicate_factor', 'lab_budget', 'lab_factor'])
def test_malformed_received_document_never_enables_results_or_export(release_ui, malformation):
    ui = release_ui; page = ui['page']; env = ui['analysis']
    if malformation.startswith('cost'):
        _select(page)
        body = env.client.get(VISUALS, query_string={'factory': FACTORY, 'category': '__ALL__', 'subcategory': '__ALL__', 'product': '__ALL__'}).json
        if malformation == 'cost_identity': body['visuals']['hierarchy'][0]['children'][0]['children'][0]['identity']['factory_id'] = 'foreign'
        else: body['visuals']['factor_ids'][1] = body['visuals']['factor_ids'][0]
        page.route('**' + VISUALS + '?*', lambda r: r.fulfill(status=200, content_type='application/json', body=json.dumps(body)))
        page.locator('#analyzeBtn').press('Enter'); page.wait_for_function("document.querySelector('#analysisStatus').dataset.state !== 'LOADING'")
        assert not page.locator('#costDashboard').is_visible() and page.locator('#downloadCsvBtn').is_disabled()
    else:
        _choose(ui); body = api_run(env).json
        if malformation == 'lab_budget': body['evaluation_budget']['executed'] = -1
        else: body['comparisons']['B_minus_A']['waterfall']['components'][0]['id'] = 'unknown'
        page.route('**' + LAB, lambda r: r.fulfill(status=200, content_type='application/json', body=json.dumps(body)))
        page.locator('#sens-run').press('Enter'); page.wait_for_function("document.querySelector('#sens-status').dataset.state !== 'LOADING'")
        assert not page.locator('#sens-results').is_visible() and page.locator('#sens-export').is_disabled()


def test_repeated_panel_tab_and_report_replacement_disposes_resources(release_ui):
    ui = release_ui; page = ui['page']; _select(page)
    measurements = []
    initial = page.evaluate('releaseResources()')
    for cycle in range(4):
        started = perf_counter(); analyze(ui); analysis_ms = (perf_counter() - started) * 1000
        base = page.evaluate('releaseResources()')
        assert base['liveCharts'] == 2
        p = panel(page, 'محصول × عامل', '#costDashboard')
        started = perf_counter(); p.locator(':scope > summary').press('Enter'); node = chart(page, p)
        opening_ms = (perf_counter() - started) * 1000
        node.evaluate('n=>window.releaseRetired=echarts.getInstanceByDom(n)')
        p.locator(':scope > summary').press('Enter')
        page.wait_for_function('releaseRetired.isDisposed()')
        assert page.evaluate('releaseResources()') == base
        page.locator('#cost-tab').press('ArrowLeft'); assert page.evaluate('releaseResources().liveCharts') == 0
        page.locator('#sensitivity-tab').press('Home'); assert page.evaluate('releaseResources()') == base
        measurements.append({'cycle': cycle + 1, 'request_and_render_ms': round(analysis_ms, 3), 'open_advanced_panel_ms': round(opening_ms, 3), **base})
    assert len({(r['resizeListeners'], r['resizeObservers']) for r in measurements}) == 1
    page.locator('#startDate').fill('')
    cleared = page.evaluate('releaseResources()')
    # Exact-value controls share one lazy document manager across both tabs.
    # Its single resize listener remains until pagehide; report resources retire.
    assert cleared == {**initial, 'resizeListeners': initial['resizeListeners'] + 1}
    save_lifecycle('cost', {'browser': page.context.browser.version, 'viewport': page.viewport_size,
                           'initial': initial, 'cleared': cleared, 'cycles': measurements})


def test_repeated_lab_run_tab_waterfall_reset_disposes_resources(release_ui):
    ui = release_ui; page = ui['page']; _choose(ui)
    page.wait_for_function('releaseResources().resizeObservers===1')
    baseline = page.evaluate('releaseResources()')
    assert baseline['liveCharts'] == 0 and baseline['resizeObservers'] == 1
    measurements = []
    for cycle in range(4):
        lab_run(ui)
        accepted = page.evaluate('releaseResources()')
        assert accepted['liveCharts'] == 3 and accepted['resizeObservers'] == 1
        p = open_panel(page, 'آبشار هزینه واحد: A ← B'); node = chart(page, p)
        node.evaluate('n=>window.releaseRetired=echarts.getInstanceByDom(n)')
        p.locator(':scope > summary').press('Enter'); page.wait_for_function('releaseRetired.isDisposed()')
        assert page.evaluate('releaseResources()') == accepted
        page.locator('#sensitivity-tab').press('Home')
        assert page.evaluate('releaseResources().liveCharts') == 0
        page.locator('#cost-tab').press('ArrowLeft')
        assert page.evaluate('releaseResources()') == accepted
        page.locator('#sens-reset').press('Enter')
        page.wait_for_function('releaseResources().liveCharts===0')
        assert page.evaluate('releaseResources()') == baseline
        assert not page.locator('#sens-results').is_visible() and page.locator('#sens-export').is_disabled()
        measurements.append({'cycle': cycle + 1, 'accepted': accepted, 'reset': baseline})
    assert len({(r['accepted']['resizeListeners'], r['accepted']['resizeObservers']) for r in measurements}) == 1
    page.select_option('#sens-product', '')
    cleared = page.evaluate('releaseResources()')
    assert cleared == {**baseline, 'resizeObservers': 0, 'liveCharts': 0}
    save_lifecycle('sensitivity', {'browser': page.context.browser.version, 'viewport': page.viewport_size,
                                  'baseline': baseline, 'cleared': cleared, 'cycles': measurements})


@pytest.mark.parametrize('release_ui', ['benchmark'], indirect=True)
def test_many_product_browser_render_opening_and_bounded_resource_churn(release_ui):
    ui = release_ui; page = ui['page']; env = ui['analysis']
    page.select_option('#factorySelect', env.selection['factory'])
    for selector in ['#categorySelect', '#subcategorySelect', '#productSelect']:
        page.wait_for_function('(selector)=>!document.querySelector(selector).disabled', arg=selector)
        page.select_option(selector, '__ALL__')
    page.wait_for_function("!document.querySelector('#analyzeBtn').disabled")
    samples = []
    for width, height, viewport in [(1440, 1100, 'desktop'), (390, 844, 'mobile')]:
        page.set_viewport_size({'width': width, 'height': height})
        for cycle in range(31):  # One warmup and thirty measurements per viewport.
            started = perf_counter(); body, _ = analyze(ui)
            request_render_ms = (perf_counter() - started) * 1000
            assert body['analysis']['coverage']['calculated'] == 200
            render_ms = page.evaluate("""()=>{const resource=performance.getEntriesByType('resource').filter(r=>r.name.includes('/cost-analysis/visuals?')).at(-1);
                return performance.now()-resource.responseEnd;}""")
            base = page.evaluate('releaseResources()'); assert base['liveCharts'] == 2
            p = open_panel(page, 'محصول × عامل', '#costDashboard'); node = chart(page, p)
            opening_ms = page.evaluate('performance.now()-releaseToggleAt')
            node.evaluate('n=>window.releaseRetired=echarts.getInstanceByDom(n)')
            p.locator(':scope > summary').press('Enter'); page.wait_for_function('releaseRetired.isDisposed()')
            assert page.evaluate('releaseResources()') == base
            page.locator('#cost-tab').press('ArrowLeft'); assert page.evaluate('releaseResources().liveCharts') == 0
            page.locator('#sensitivity-tab').press('Home'); assert page.evaluate('releaseResources()') == base
            if cycle:
                samples.append({'viewport': viewport, 'width': width, 'height': height, 'cycle': cycle,
                                'request_and_render_ms': round(request_render_ms, 3),
                                'browser_after_response_ms': round(render_ms, 3),
                                'open_advanced_panel_ms': round(opening_ms, 3), **base})
    assert len({(r['resizeListeners'], r['resizeObservers'], r['liveCharts']) for r in samples}) == 1
    target = Path(os.environ.get('DASHBOARD_BROWSER_METRICS_FILE', str(ROOT / 'work/pr10-evidence/browser-performance.json')))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({'browser': page.context.browser.version, 'echarts': '5.6.0',
                                 'fixture': env.dimensions, 'warmup_per_viewport': 1,
                                 'measurement_scope': 'fetch+render; browser responseEnd to ready; toggle to mounted chart',
                                 'samples': samples}, indent=2))
