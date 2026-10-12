"""Actual Flask/Chromium PR-09A interaction, exact exports and isolated evidence."""
import csv
import io
import json
import os
from pathlib import Path
from urllib.parse import urlparse

import pytest

from test_dashboard_cost_analysis import _snapshot, _reference, _client, _write, _bom
from test_dashboard_sensitivity import sensitivity, analysis, _material_fixture, _g2_fixture, _parameter
from test_dashboard_frontend import browser, ui, _select, _analyze, _real_echarts, _clipboard, _install_pending_fetch, _resolve
from test_dashboard_sensitivity_frontend import _choose, _add
from test_dashboard_visual_analysis import LAB, VISUALS


@pytest.fixture
def visual_ui(sensitivity, ui):
    before = [_snapshot(sensitivity.root)]
    requests = []
    ui['page'].on('request', lambda r: requests.append((r.method, urlparse(r.url).path)))
    ui['checkpoint'] = lambda: before.__setitem__(0, _snapshot(sensitivity.root))
    yield ui
    assert not ui['errors'], ui['errors']
    assert _snapshot(sensitivity.root) == before[0]
    assert all(method in {'GET', 'HEAD'} or path == LAB for method, path in requests)


def run(ui):
    page = ui['page']
    with page.expect_response(lambda r: urlparse(r.url).path == LAB) as pending:
        page.locator('#sens-run').press('Enter')
    response = pending.value
    page.wait_for_function("document.querySelector('#sens-status').dataset.state !== 'LOADING'")
    assert response.status == 200, response.text()
    assert page.locator('#sens-status').get_attribute('data-state') == 'OK'
    assert page.locator('#sens-results').is_visible()
    return response.json()


def panel(page, title, container='#sens-results'):
    return page.locator(container + ' .visual-panel').filter(has=page.get_by_text(title, exact=True)).first


def open_panel(page, title, container='#sens-results'):
    p = panel(page, title, container)
    if p.get_attribute('open') is None:
        p.locator(':scope > summary').press('Enter')
    return p


def evidence(page, name):
    target = os.environ.get('DASHBOARD_UI_EVIDENCE_DIR')
    if target:
        root = Path(target); root.mkdir(parents=True, exist_ok=True)
        title = next((title for kind,title in [('tornado','تورنادو'),('one_factor','منحنی پاسخ واقعی'),('two_factor','نقشه دو عامل')] if name.startswith(kind)), None)
        target_node = panel(page,'کاوش سلسله‌مراتب هزینه','#costDashboard') if name.startswith('cost-exploration') else panel(page,title+' — هزینه واحد') if title else page.locator('#costDashboard' if name.startswith('cost') else '#sens-results')
        page.evaluate('document.fonts.ready')
        if page.viewport_size['width'] < 992:
            page.wait_for_function("document.querySelector('#mainSidebar').getBoundingClientRect().left >= innerWidth - 1")
        target_node.evaluate("e=>e.scrollIntoView({block:'start',behavior:'instant'})")
        page.wait_for_timeout(450)  # Sidebar transition and ResizeObserver canvas layout.
        page.screenshot(path=str(root / (name + '.png')), full_page=False)


def experiment(page, kind, parameters, values):
    controls = page.locator('#lab-experiment-controls details')
    if controls.get_attribute('open') is None: controls.locator('summary').press('Enter')
    page.select_option('#lab-experiment-type', kind)
    for i, (parameter, value) in enumerate(zip(parameters if kind=='two_factor' else parameters[:1], values)):
        page.select_option('#lab-parameter-' + str(i), parameter)
        if kind == 'tornado':
            page.locator('#lab-low-' + str(i)).fill(value[0]); page.locator('#lab-high-' + str(i)).fill(value[1])
        else: page.locator('#lab-raw-' + str(i)).fill(value)


def test_ab_goldens_reset_drafts_export_and_real_echarts(visual_ui):
    ui = visual_ui; env = ui['analysis']; page = ui['page']
    _g2_fixture(env); prediction = _parameter(env, 'prediction:'); share = _parameter(env, 'category_share:'); ui['checkpoint']()
    _real_echarts(page); _choose(ui)
    _add(page, prediction, '۳۰')
    page.select_option('#lab-draft-scenario', 'B'); _add(page, share, '۲۵')
    page.select_option('#lab-draft-scenario', 'A')
    assert page.locator('[data-override-value]').input_value() == '۳۰'
    body = run(ui)
    assert body['comparisons']['B_minus_A']['projected_cost']['amount'] == '500'
    assert page.locator('#sens-results [data-raw="1500"]').count() > 0
    p = open_panel(page, 'آبشار هزینه واحد: A ← B')
    page.wait_for_function('(e)=>!!echarts.getInstanceByDom(e)', arg=p.locator('.report-chart').element_handle())
    assert page.locator('#sens-results [data-raw="150"]').count() > 0
    with page.expect_download() as pending: page.locator('#sens-export').press('Enter')
    raw = Path(pending.value.path()).read_bytes(); assert raw.startswith(b'\xef\xbb\xbf')
    rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
    assert any(r['scope']=='B_minus_A' and r['metric']=='projected_cost' and r['value']=='500' for r in rows)
    assert all(r['non_persistent']=='true' and r['period_id']=='P' for r in rows)
    evidence(page, 'ab-desktop')
    page.set_viewport_size({'width':390,'height':844}); evidence(page, 'ab-mobile')
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.locator('#sens-reset').press('Enter')
    assert not page.locator('#sens-results').is_visible()
    assert page.locator('#sens-baseline').is_visible() and page.locator('#sens-export').is_disabled()
    assert page.locator('#sens-draft .sens-draft-item').count() == 0
    page.select_option('#lab-draft-scenario', 'B'); assert page.locator('#sens-draft .sens-draft-item').count() == 0


def test_current_cost_workspace_lazy_focus_mobile_and_partial(visual_ui):
    ui = visual_ui; page = ui['page']; _real_echarts(page)
    _write(ui['analysis'].factory / 'category' / 'sub' / 'B.json', _bom([1], loss=101))
    ui['checkpoint']()
    _select(page); _analyze(page)
    assert page.locator('#analysisStatus').get_attribute('data-state') == 'PARTIAL'
    assert page.get_by_text('جمعیت منتخب محاسبه‌شده:', exact=False).count() > 0
    advanced = page.locator('#costDashboard details.visual-panel')
    assert advanced.count() == 4
    assert page.evaluate("Array.from(document.querySelectorAll('#costDashboard details.visual-panel .report-chart')).every(e=>!echarts.getInstanceByDom(e))")
    heat = open_panel(page, 'محصول × عامل', '#costDashboard')
    page.wait_for_function('(e)=>!!echarts.getInstanceByDom(e)', arg=heat.locator('.report-chart').element_handle())
    heat.locator('.visual-exact-table > summary').press('Enter')
    heat.locator('tbody .btn').first.press('Enter')
    assert page.locator('.visual-focus').is_visible(), page.locator('.visual-focus').evaluate('(e)=>({hidden:e.hidden,text:e.textContent,display:getComputedStyle(e).display,parent:e.parentElement.id})')
    assert page.get_by_text('ردیف‌های مستقل BOM',exact=True).count() > 0
    page.get_by_role('button',name='بازگشت / پاک کردن تمرکز',exact=True).press('Enter')
    assert not page.locator('.visual-focus').is_visible()
    heat.locator(':scope > summary').press('Enter')
    page.wait_for_function('(e)=>!echarts.getInstanceByDom(e)',arg=heat.locator('.report-chart').element_handle())
    for title in ['کاوش سلسله‌مراتب هزینه','پارتوی مواد','تولید و هزینه']:
        p = open_panel(page,title,'#costDashboard'); assert p.locator('table tbody tr').count() > 0
    hier = panel(page,'کاوش سلسله‌مراتب هزینه','#costDashboard')
    hier.get_by_role('button',name='بررسی category',exact=True).press('Enter')
    hier.get_by_role('button',name='بررسی sub',exact=True).press('Enter')
    hier.get_by_role('button',name='بررسی A',exact=True).press('Enter')
    assert page.locator('.visual-focus').is_visible()
    page.get_by_role('button',name='بازگشت / پاک کردن تمرکز',exact=True).press('Enter')
    evidence(page,'cost-exploration-desktop')
    evidence(page,'cost-desktop');page.set_viewport_size({'width':390,'height':844});evidence(page,'cost-mobile');evidence(page,'cost-exploration-mobile')
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')


@pytest.mark.parametrize('kind', ['tornado','one_factor','two_factor'])
def test_experiments_real_engine_exact_points_and_lazy_charts(visual_ui, kind):
    ui = visual_ui; env = ui['analysis']; page = ui['page']
    _g2_fixture(env); prediction = _parameter(env,'prediction:'); share = _parameter(env,'category_share:'); ui['checkpoint']()
    _real_echarts(page); _choose(ui)
    experiment(page,kind,[share,prediction], [('25','50')] if kind=='tornado' else ['25\n50','10\n30'])
    body = run(ui); e = body['experiment']
    assert e['valid_count'] == (4 if kind=='two_factor' else 2)
    title = {'tornado':'تورنادو','one_factor':'منحنی پاسخ واقعی','two_factor':'نقشه دو عامل'}[kind]
    p = open_panel(page,title+' — هزینه واحد')
    page.wait_for_function('(e)=>!!echarts.getInstanceByDom(e)',arg=p.locator('.report-chart').element_handle())
    open_panel(page,title+' — هزینه دوره')
    evidence(page,kind+'-desktop');page.set_viewport_size({'width':390,'height':844});evidence(page,kind+'-mobile')
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    # Any range edit clears the accepted comparison and export immediately.
    page.locator('#lab-low-0' if kind=='tornado' else '#lab-raw-0').fill('20')
    assert page.locator('#sens-export').is_disabled() and not page.locator('#sens-results').is_visible()


def test_chart_failure_retains_tables_and_exact_copy(visual_ui):
    ui = visual_ui; page = ui['page']; _choose(ui); page.evaluate("window.echarts={init:()=>{throw Error('fixture chart failure')}}")
    run(ui)
    assert page.locator('#sens-results table').count() >= 3
    assert page.locator('#sens-results .report-chart').filter(visible=True).count() == 0
    assert page.locator('#sens-export').is_enabled()


@pytest.mark.parametrize('edit', ['A','B','range','reset','selection'])
def test_delayed_response_cannot_restore_stale_results(visual_ui, edit):
    ui=visual_ui;env=ui['analysis'];page=ui['page'];_g2_fixture(env);share=_parameter(env,'category_share:');ui['checkpoint']();_choose(ui)
    if edit=='B':page.select_option('#lab-draft-scenario','B')
    _add(page,share,'25')
    if edit=='range':experiment(page,'one_factor',[share],['25\n50'])
    # Obtain an authorized server response before the browser request is delayed.
    from test_dashboard_visual_analysis import run as api_run
    body=api_run(env).json
    _install_pending_fetch(page,LAB)
    page.locator('#sens-run').press('Enter');page.wait_for_function('window.testPending.length===1')
    if edit in {'A','B'}:page.locator('[data-override-value]').fill('30')
    elif edit=='range':page.locator('#lab-raw-0').fill('20\n40')
    elif edit=='reset':page.locator('#sens-reset').press('Enter')
    else:page.select_option('#sens-product',_reference('category','sub','B'))
    _resolve(page,0,body)
    page.wait_for_timeout(100)
    assert page.locator('#sens-export').is_disabled() and not page.locator('#sens-results').is_visible()


@pytest.mark.parametrize('group,prefix',[('general_parameters','material:'),('factory_parameters','pool:')])
def test_observed_revocation_clears_both_drafts_results_and_exact_values(visual_ui,group,prefix):
    ui=visual_ui;env=ui['analysis'];page=ui['page'];_choose(ui);parameter=_parameter(env,prefix,baseline=1000 if prefix=='pool:' else None)
    _add(page,parameter,'999999');page.select_option('#lab-draft-scenario','B');_add(page,parameter,'888888');run(ui)
    table=page.locator('#sens-results .visual-exact-table').first
    if table.get_attribute('open') is None:table.locator('summary').press('Enter')
    page.locator('#sens-results [data-exact-trigger]').first.scroll_into_view_if_needed()
    page.locator('#sens-results [data-exact-trigger]').first.press('Enter')
    assert page.locator('.exact-popover').is_visible()
    user=env.store.get_user_by_id('both-groups')
    env.store.update_user('both-groups',{'access_grants':[g for g in user['access_grants'] if g['module']!=group]});ui['checkpoint']()
    with page.expect_response(lambda r:urlparse(r.url).path==LAB) as pending:page.locator('#sens-run').press('Enter')
    assert pending.value.status==403
    page.wait_for_function("document.querySelector('#sens-status').dataset.state==='FORBIDDEN'")
    assert '999999' not in page.locator('#sensitivity').inner_text() and '888888' not in page.locator('#sensitivity').inner_text()
    assert page.locator('#sens-draft .sens-draft-item').count()==0
    assert page.locator('#sens-export').is_disabled() and not page.locator('.exact-popover').is_visible()


def test_invalid_samples_and_empty_ranges(visual_ui):
    ui=visual_ui;env=ui['analysis'];page=ui['page'];_g2_fixture(env);share=_parameter(env,'category_share:');ui['checkpoint']();_real_echarts(page);_choose(ui)
    experiment(page,'one_factor',[share],['0\n25\n101']);body=run(ui)
    assert body['experiment']['invalid_count']==2
    p=open_panel(page,'منحنی پاسخ واقعی — هزینه واحد');p.locator('.visual-exact-table > summary').press('Enter')
    assert p.get_by_text('خارج از دامنه / در دسترس نیست',exact=True).count()==2
    page.locator('#lab-raw-0').fill('')
    assert page.locator('#sens-run').is_disabled() and page.locator('#sens-export').is_disabled()


def test_restricted_baseline_empty_ab_and_auth_failure(visual_ui):
    ui=visual_ui;env=ui['analysis'];page=ui['page']
    cookie=_client(env.app,'dashboard-user').get_cookie('session');ui['context'].add_cookies([{'name':'session','value':cookie.value,'url':ui['base']}])
    page.reload(wait_until='networkidle');_choose(ui);body=run(ui)
    assert not body['parameters'] and 'prediction' not in body['baseline']
    assert not any('raw_factory_pool' in r for r in body['baseline']['breakdown']['driver_components'])
    ui['context'].clear_cookies()
    page.locator('#sens-run').press('Enter')
    page.wait_for_function("document.querySelector('#sens-status').dataset.state==='UNAVAILABLE'")
    assert not page.locator('#sens-results').is_visible() and page.locator('#sens-export').is_disabled()


def test_source_labels_cannot_execute_in_real_charts_tables_or_csv(visual_ui):
    ui=visual_ui;env=ui['analysis'];page=ui['page'];_material_fixture(env)
    malicious='=1+1<img src=x onerror="window.__xss=1">'
    for path in [env.data/'Overall'/'material_costs.json',env.factory/'category'/'sub'/'A.json']:
        document=json.loads(path.read_text());_write(path,json.loads(json.dumps(document).replace('lead',json.dumps(malicious)[1:-1])))
    ui['checkpoint']();_real_echarts(page);_choose(ui);run(ui)
    bom=open_panel(page,'ردیف‌های مستقل BOM در مقایسه')
    assert bom.locator('img').count()==0
    assert page.evaluate('window.__xss') is None
    bom.locator('.visual-exact-table > summary').press('Enter')
    assert bom.get_by_text(malicious,exact=True).count()==6
    with page.expect_download() as pending:page.locator('#sens-export').press('Enter')
    raw=Path(pending.value.path()).read_text(encoding='utf-8-sig')
    assert any(r['metric'].endswith(malicious) for r in csv.DictReader(io.StringIO(raw)))
    page.locator('#cost-tab').press('Enter')
    _select(page);_analyze(page)
    pareto=open_panel(page,'پارتوی مواد','#costDashboard')
    page.wait_for_function('(e)=>!!echarts.getInstanceByDom(e)',arg=pareto.locator('.report-chart').element_handle())
    pareto.locator('.report-chart').evaluate("e=>echarts.getInstanceByDom(e).dispatchAction({type:'showTip',seriesIndex:0,dataIndex:0})")
    assert page.locator('#costDashboard img').count()==0 and page.evaluate('window.__xss') is None
