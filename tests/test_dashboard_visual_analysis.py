"""PR-09A real API goldens, shared capture, bounds, redaction and no writes."""
import json
from decimal import Decimal

import pytest

from test_dashboard_sensitivity import (
    sensitivity, analysis, SELECTION, _change, _parameter, _g2_fixture,
    _material_fixture, _client, _snapshot, _write, _parameters,
)
from utils.costing_engine import CostInputLoader
from utils.dashboard_visual_sensitivity import comparison

LAB = '/api/dashboard/sensitivity/visual-analysis'
VISUALS = '/api/dashboard/cost-analysis/visuals'


def run(env, a=(), b=(), experiment=None, client=None, **extra):
    return (client or env.client).post(LAB, json={**SELECTION,
        'scenarios': [{'id': 'A', 'overrides': list(a)}, {'id': 'B', 'overrides': list(b)}],
        'experiment': experiment, **extra})


def test_ab_g2_projected_deltas_and_waterfalls(sensitivity):
    env = sensitivity
    _g2_fixture(env)
    prediction = _parameter(env, 'prediction:')
    share = _parameter(env, 'category_share:')
    before = _snapshot(env.root)
    response = run(env, [_change(prediction, '30')], [_change(share, '25')])
    assert response.status_code == 200
    body = response.json
    assert [body['baseline']['unit_cost'], *[s['result']['unit_cost'] for s in body['scenarios']]] == ['100', '50', '200']
    assert [body['baseline']['projected_cost'], *[s['result']['projected_cost'] for s in body['scenarios']]] == ['1000', '1500', '2000']
    difference = body['comparisons']['B_minus_A']
    assert difference['unit_cost']['amount'] == '150'
    assert difference['projected_cost']['amount'] == '500'
    for compared in body['comparisons'].values():
        w = compared['waterfall']
        assert Decimal(w['reference']) + sum((Decimal(c['value']) for c in w['components']), Decimal(0)) + Decimal(w['reconciliation']) == Decimal(w['target'])
    canonical = env.client.get('/api/cost_analysis', query_string=SELECTION).json
    assert canonical['detail_rows'][0]['unit_cost'] == body['baseline']['unit_cost']
    assert _snapshot(env.root) == before


def test_duplicate_bom_and_fresh_baseline(sensitivity):
    env = sensitivity
    _material_fixture(env)
    parameter = _parameter(env, 'material:')
    response = run(env, [_change(parameter, '10', 'percent_change')], [_change(parameter, '20', 'percent_change')])
    assert response.status_code == 200
    assert [response.json['baseline']['unit_cost'], *[s['result']['unit_cost'] for s in response.json['scenarios']]] == ['140.0', '154.00', '168.00']
    rows = response.json['baseline']['breakdown']['bom_components']
    assert len(rows) == len({r['row_id'] for r in rows}) == 2
    _material_fixture(env, price=200)
    fresh = run(env).json
    assert Decimal(fresh['baseline']['unit_cost']) == 280


@pytest.mark.parametrize('user,groups', [('dashboard-user', (False, False)), ('general-only', (True, False)),
    ('factory-only', (False, True)), ('both-groups', (True, True))])
def test_permissions_and_whitelist(sensitivity, user, groups):
    env = sensitivity
    response = run(env, client=_client(env.app, user))
    assert response.status_code == 200
    body = response.json
    assert tuple(body['permissions'].values()) == groups or body['permissions'] == dict(zip(('general_parameters', 'factory_parameters'), groups))
    for result in [body['baseline'], *[s['result'] for s in body['scenarios']]]:
        assert ('prediction' in result) == groups[1]
        assert all(('raw_factory_pool' in r) == groups[1] for r in result['breakdown']['driver_components'])
        assert all(set(r) == {'row_id', 'material', 'live_cost_in_rial'} for r in result['breakdown']['bom_components'])


def test_every_point_same_capture_and_compact(sensitivity, monkeypatch):
    env = sensitivity
    _g2_fixture(env)
    prediction = _parameter(env, 'prediction:')
    share = _parameter(env, 'category_share:')
    import utils.dashboard_visual_sensitivity as lab
    original = lab.calculate_cost
    seen = []
    def calculate(inputs, overrides):
        seen.append(inputs)
        return original(inputs, overrides)
    monkeypatch.setattr(lab, 'calculate_cost', calculate)
    response = run(env, experiment={'type': 'two_factor', 'axes': [
        {'parameter_id': prediction, 'mode': 'absolute', 'values': ['10', '30']},
        {'parameter_id': share, 'mode': 'absolute', 'values': ['50', '25']}]})
    assert response.status_code == 200
    body = response.json
    assert len(seen) == 6 and all(i is seen[0] for i in seen)
    assert body['evaluation_budget'] == {'reserved': 7, 'executed': 7, 'maximum': 200}
    assert [p['unit_cost'] for p in body['experiment']['points']] == ['100', '200', '50', '100']
    assert all('breakdown' not in p and 'parameters' not in p for p in body['experiment']['points'])


def test_domain_invalid_samples_not_zero(sensitivity):
    env = sensitivity
    _g2_fixture(env)
    share = _parameter(env, 'category_share:')
    before = _snapshot(env.root)
    response = run(env, experiment={'type': 'one_factor', 'axes': [
        {'parameter_id': share, 'mode': 'absolute', 'values': ['0', '25', '101']}]})
    assert response.status_code == 200
    e = response.json['experiment']
    assert (e['valid_count'], e['invalid_count']) == (1, 2)
    assert [p['unit_cost'] for p in e['points']] == [None, '200', None]
    assert _snapshot(env.root) == before


@pytest.mark.parametrize('experiment', [
    {'type': 'one_factor', 'axes': [{'parameter_id': 'pool:Payroll', 'mode': 'absolute', 'values': ['1'] * 42}]},
    {'type': 'two_factor', 'axes': [{'parameter_id': 'pool:Payroll', 'mode': 'absolute', 'values': ['1'] * 12}] * 2},
    {'type': 'tornado', 'ranges': [{'parameter_id': 'pool:Payroll', 'mode': 'absolute', 'low': '0', 'high': '1'}] * 11},
    {'type': 'one_factor', 'axes': [{'parameter_id': 'pool:Payroll', 'mode': 'absolute', 'values': ['']}]},
])
def test_bounds_and_grammar_before_source_reads(sensitivity, monkeypatch, experiment):
    def forbidden(*args, **kwargs):
        pytest.fail('Malformed request opened operational inputs')
    monkeypatch.setattr(CostInputLoader, 'snapshot_population', forbidden)
    assert run(sensitivity, experiment=experiment).status_code == 400


def test_unauthorized_before_read_and_no_write(sensitivity, monkeypatch):
    env = sensitivity
    before = _snapshot(env.root)
    monkeypatch.setattr(CostInputLoader, 'snapshot_population', lambda *a, **k: pytest.fail('unauthorized source read'))
    assert run(env, [_change('pool:Payroll', '1')], client=_client(env.app, 'general-only')).status_code == 403
    assert _snapshot(env.root) == before


def test_alias_axes_and_tornado_rejected(sensitivity):
    for experiment in [
        {'type': 'two_factor', 'axes': [{'parameter_id': 'pool:Payroll', 'mode': 'absolute', 'values': ['1']}] * 2},
        {'type': 'tornado', 'ranges': [{'parameter_id': 'pool:Payroll', 'mode': 'absolute', 'low': '0', 'high': '1'}] * 2},
    ]:
        response = run(sensitivity, experiment=experiment)
        assert response.status_code == 400
        assert response.json['issues'][0]['code'] in {'ALIASED_EXPERIMENT_PARAMETERS', 'DUPLICATE_PARAMETER_ID'}


def test_visuals_derived_once_all_partial_rows(sensitivity, monkeypatch):
    env = sensitivity
    _material_fixture(env)
    from utils.dashboard_analysis import DashboardAnalysisService
    original = DashboardAnalysisService.analyze
    calls = []
    def analyze(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(result)
        return result
    monkeypatch.setattr(DashboardAnalysisService, 'analyze', analyze)
    before = _snapshot(env.root)
    response = env.client.get(VISUALS, query_string={**SELECTION, 'category': '__ALL__', 'subcategory': '__ALL__', 'product': '__ALL__'})
    assert response.status_code == 200 and len(calls) == 1
    body = response.json
    v = body['visuals']
    assert v['coverage'] == body['analysis']['coverage']
    assert sum(len(m['rows']) for m in v['materials']) == sum(len(p['bom_components']) for p in body['analysis']['breakdowns']['products'])
    assert len(v['products']) == v['coverage']['calculated']
    assert len(v['excluded']) == v['coverage']['excluded']
    assert _snapshot(env.root) == before


def test_mathematical_zero_combination_and_null_percentage(sensitivity):
    env = sensitivity
    _material_fixture(env, price=0, currency='USD', usages=(1,))
    registry = _parameters(env).json['parameters']
    price = next(p['parameter_id'] for p in registry if p['parameter_id'].startswith('material:'))
    fx = next(p for p in registry if p['parameter_id'].startswith('fx:'))
    assert fx['effect_state'] == 'MATHEMATICAL_ZERO'
    body = run(env, b=[_change(price, '10'), _change(fx['parameter_id'], '6')], experiment={
        'type':'two_factor','axes':[{'parameter_id':price,'mode':'absolute','values':['0','10']},
                                  {'parameter_id':fx['parameter_id'],'mode':'absolute','values':['5','6']}]}).json
    assert [p['unit_cost'] for p in body['experiment']['points']] == ['0','0','50','60']
    assert body['comparisons']['B_minus_baseline']['unit_cost']['percentage'] is None
    assert body['comparisons']['B_minus_baseline']['unit_cost']['percentage_state'] == 'NOT_APPLICABLE'


def test_different_ids_same_source_axes_safe_rejection(sensitivity):
    env = sensitivity
    _g2_fixture(env)
    target = env.factory / 'configuration' / 'cost_pools' / 'Payroll.json'
    alias = target.with_name('Overhead.json'); alias.unlink(); alias.symlink_to(target.name)
    before = _snapshot(env.root)
    response = run(env, experiment={'type':'two_factor','axes':[
        {'parameter_id':p,'mode':'absolute','values':['1','2']} for p in ['pool:Payroll','pool:Overhead']]})
    assert response.status_code == 400
    assert response.json['issues'][0]['code'] == 'ALIASED_EXPERIMENT_PARAMETERS'
    assert 'منبع مشترک' in response.json['issues'][0]['message']
    assert _snapshot(env.root) == before


@pytest.mark.parametrize('value',['0.000000000000000000000000001','1000000000000000000000000000000000000000000000000000000000000'])
def test_exact_extreme_strings(sensitivity,value):
    env = sensitivity
    _material_fixture(env,usages=(1,))
    p = _parameter(env,'material:')
    body = run(env,[_change(p,value)]).json
    assert Decimal(body['scenarios'][0]['result']['unit_cost']) == Decimal(value)
    assert body['scenarios'][0]['effective_overrides'][0]['value'] == value


def test_finite_precision_waterfall_residue_is_explicit():
    def result(unit,bom):
        return {'unit_cost':Decimal(unit),'projected_cost':Decimal(unit),'bom_total':Decimal(bom),
                'breakdown':{'driver_components':[{'pool_id':p,'per_unit_contribution':Decimal('0')} for p in (
                    'AdministrativeandResearch','Payroll','Overhead','FinancialCosts','Depriciation','NonOperationalCostsandIncomes')]}}
    reference=result('1','1');target=result('1.000000000000000000000000001','1')
    c=comparison(reference,target,'B_minus_A')
    assert c['waterfall']['target'] == target['unit_cost']
    assert c['waterfall']['reconciliation'] == Decimal('0.000000000000000000000000001')
    assert all(p['value']==0 for p in c['waterfall']['components'])


@pytest.mark.parametrize('extra', [{'baseline':{}},{'snapshot_token':'invented'},{'scenario_id':'saved'},
    {'source_mapping':{}},{'period':'Q'},{'product':'__ALL__'}])
def test_rejected_requests_no_write(sensitivity,extra):
    before=_snapshot(sensitivity.root)
    assert run(sensitivity,**extra).status_code in {400,422}
    assert _snapshot(sensitivity.root)==before


def test_limits_body_override_count_and_duplicates(sensitivity):
    env=sensitivity
    before=_snapshot(env.root)
    assert run(env,[_change('pool:Payroll','1')]*65).status_code==400
    assert run(env,[_change('pool:Payroll','1'*129)]).status_code==400
    assert env.client.post(LAB,data='{"factory":"a","factory":"b"}',content_type='application/json').status_code==400
    assert env.client.post(LAB,data=' '*(65537),content_type='application/json').status_code==413
    assert _snapshot(env.root)==before


def test_tornado_isolated_baseline_ranges_rank_measured_impact(sensitivity):
    env=sensitivity
    _g2_fixture(env)
    p=_parameter(env,'prediction:');s=_parameter(env,'category_share:')
    body=run(env,[_change(p,'30')],experiment={'type':'tornado','ranges':[
        {'parameter_id':p,'mode':'absolute','low':'10','high':'30'},
        {'parameter_id':s,'mode':'absolute','low':'25','high':'50'}]}).json
    assert [x['unit_cost'] for x in body['experiment']['points']]==['100','50','200','100']
    assert [x['impact'] for x in body['experiment']['ranking']]==['100','50']
    assert body['experiment']['ranking'][0]['parameter_id']==s


def test_large_fixture_budget_single_capture_reads_latency_and_payload(sensitivity,monkeypatch):
    import time
    import os
    from pathlib import Path
    import utils.dashboard_sensitivity as original
    import utils.dashboard_visual_sensitivity as lab
    env=sensitivity
    _material_fixture(env,usages=[1]*500)
    names=['A','B',*[f'P{i:03}' for i in range(198)]]
    for name in names[2:]:
        _write(env.factory/'category'/'sub'/(name+'.json'), {'data':{'material':['lead'],'Usage':[1],'Loss':[0],'Recyclability':[0]}})
    _write(env.factory/'configuration'/'production_prediction.json',{'data':{'Product Name':names,'Predicted Production':[10]*200}})
    p=_parameter(env,'material:');reads=[];captures=[]
    real_read=Path.read_bytes;real_calc=lab.calculate_cost
    def read(path):
        if env.data in path.parents or path==env.binding:reads.append(path)
        return real_read(path)
    def calc(inputs,overrides=None):
        captures.append((inputs,overrides));return real_calc(inputs,overrides)
    before=_snapshot(env.root)
    monkeypatch.setattr(Path,'read_bytes',read)
    monkeypatch.setattr(original,'calculate_cost',calc);monkeypatch.setattr(lab,'calculate_cost',calc)
    start=time.perf_counter()
    response=run(env,experiment={'type':'two_factor','axes':[
        {'parameter_id':p,'mode':'absolute','values':[str(i) for i in range(11)]},
        {'parameter_id':'pool:Payroll','mode':'absolute','values':[str(i*100) for i in range(11)]}]})
    elapsed=time.perf_counter()-start
    assert response.status_code==200
    body=response.json
    assert body['evaluation_budget']['executed']==124
    assert len(captures)==124 and sum(o is None for _,o in captures)==1
    assert all(i is captures[0][0] for i,_ in captures)
    assert len(reads)==len(set(reads))
    evidence={'configuration_population':200,'selected_BOM_rows':500,'points':121,'evaluations':124,
              'latency_seconds':round(elapsed,6),'source_reads':len(reads),'payload_bytes':len(response.data),
              'experiment_bytes':len(json.dumps(body['experiment']).encode())}
    print(json.dumps(evidence))
    target=os.environ.get('DASHBOARD_BENCHMARK_PATH')
    if target:Path(target).write_text(json.dumps(evidence,indent=2)+'\n')
    monkeypatch.setattr(Path,'read_bytes',real_read)
    assert _snapshot(env.root)==before
