"""PR-10 shipped-client rejection checks using actual isolated Flask envelopes.

These mutations attack boundaries and metadata. Browser code never recalculates
money, allocation, ranking, percentages or technical Decimal reconciliation.
"""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from test_dashboard_cost_analysis import analysis, _bom, _write
from test_dashboard_sensitivity import (
    sensitivity, SELECTION, _change, _client, _g2_fixture, _material_fixture, _parameter,
)
from test_dashboard_visual_analysis import run, VISUALS

ROOT = Path(__file__).resolve().parents[1]


def _node(script, payload):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required for shipped-client model verification')
    prelude = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');global.window=global;
for(const name of ['dashboard-numbers.js','dashboard-report.js','dashboard-visuals.js','dashboard-sensitivity-model.js','dashboard-lab.js'])
    vm.runInThisContext(fs.readFileSync('static/js/'+name,'utf8'));
const data=JSON.parse(fs.readFileSync(0,'utf8')),clone=structuredClone;
function rejects(source, mutations, adapter) {
    for (const [description, mutate] of mutations) {
        const value=clone(source);mutate(value);
        assert.throws(()=>adapter(value), undefined, description);
    }
}
'''
    result = subprocess.run([node, '-e', prelude + script], cwd=ROOT,
                            input=json.dumps(payload), text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.fixture
def cost_payloads(sensitivity):
    env = sensitivity
    _material_fixture(env)
    selection = {**SELECTION, 'product': '__ALL__'}
    full = env.client.get(VISUALS, query_string=selection)
    assert full.status_code == 200
    _write(env.factory / 'category' / 'sub' / 'B.json', _bom([1], loss=101))
    partial = env.client.get(VISUALS, query_string=selection)
    assert partial.json['analysis']['state'] == 'PARTIAL'
    env.binding.unlink()
    unavailable = env.client.get(VISUALS, query_string=selection)
    assert unavailable.status_code == 422
    return {'full': full.json, 'partial': partial.json, 'unavailable': unavailable.json}


@pytest.fixture
def lab_payloads(sensitivity):
    env = sensitivity
    _g2_fixture(env)
    share, prediction = _parameter(env, 'category_share:'), _parameter(env, 'prediction:')
    responses = {
        'base': run(env, [_change(prediction, '30')], [_change(share, '25')]),
        'one': run(env, experiment={'type': 'one_factor', 'axes': [
            {'parameter_id': share, 'mode': 'absolute', 'values': ['0', '25', '101']}]}),
        'repeated': run(env, experiment={'type': 'one_factor', 'axes': [
            {'parameter_id': share, 'mode': 'absolute', 'values': ['50', '25', '50']}]}),
        'two': run(env, experiment={'type': 'two_factor', 'axes': [
            {'parameter_id': share, 'mode': 'absolute', 'values': ['25', '50']},
            {'parameter_id': prediction, 'mode': 'absolute', 'values': ['10', '30']}]}),
        'tornado': run(env, experiment={'type': 'tornado', 'ranges': [
            {'parameter_id': share, 'mode': 'absolute', 'low': '25', 'high': '50'},
            {'parameter_id': prediction, 'mode': 'absolute', 'low': '10', 'high': '30'}]}),
        'invalid_tornado': run(env, experiment={'type': 'tornado', 'ranges': [
            {'parameter_id': share, 'mode': 'absolute', 'low': '0', 'high': '50'}]}),
        'maximum': run(env, experiment={'type': 'two_factor', 'axes': [
            {'parameter_id': share, 'mode': 'absolute', 'values': ['25'] * 11},
            {'parameter_id': prediction, 'mode': 'absolute', 'values': ['10'] * 11}]}),
    }
    for user in ['dashboard-user', 'general-only', 'factory-only', 'both-groups']:
        responses[user] = run(env, client=_client(env.app, user))
    assert all(r.status_code == 200 for r in responses.values())
    return {name: response.json for name, response in responses.items()}


def test_cost_accepts_real_full_partial_unavailable_and_freezes(cost_payloads):
    _node(r'''
for (const envelope of Object.values(data)) {
    const accepted=DashboardVisuals.adaptCost(envelope);
    assert(Object.isFrozen(accepted.analysis.detail_rows));assert(Object.isFrozen(accepted.visuals.hierarchy));
    assert.deepStrictEqual(accepted,envelope);
}
const source=clone(data.full), accepted=DashboardVisuals.adaptCost(source);
source.visuals.products[0].unit_cost='1';assert.notEqual(accepted.visuals.products[0].unit_cost,'1');
''', cost_payloads)


def test_cost_rejects_forged_nested_populations_factors_and_units(cost_payloads):
    _node(r'''
rejects(data.full,[
 ['factor duplicated',r=>r.visuals.factor_ids[1]='BOM'],
 ['technical factor in cost map',r=>r.visuals.factor_ids[1]='TECHNICAL_RECONCILIATION'],
 ['duplicate product',r=>r.visuals.products[1]=clone(r.visuals.products[0])],
 ['foreign material identity',r=>r.visuals.materials[0].rows[0].identity.factory_id='foreign'],
 ['unknown material row',r=>r.visuals.materials[0].rows[0].row_id='foreign'],
 ['duplicated material row',r=>r.visuals.materials[0].rows.push(clone(r.visuals.materials[0].rows[0]))],
 ['material original amount mismatched',r=>r.visuals.materials[0].rows[0].unit_contribution='1'],
 ['foreign hierarchy identity',r=>r.visuals.hierarchy[0].children[0].children[0].identity.factory_id='foreign'],
 ['wrong hierarchy path',r=>r.visuals.hierarchy[0].name='foreign'],
 ['duplicate hierarchy leaf',r=>r.visuals.hierarchy[0].children[0].children.push(clone(r.visuals.hierarchy[0].children[0].children[0]))],
 ['hierarchy missing leaves',r=>r.visuals.hierarchy=[]],
 ['unit component null',r=>r.visuals.products[0].unit_components.BOM=null],
 ['unit component wrong factor',r=>r.visuals.products[0].unit_components.unknown='0'],
 ['unit component disagrees with original',r=>r.visuals.products[0].unit_components.BOM='1'],
 ['wrong hierarchy unit',r=>r.visuals.hierarchy_unit='IRR/product'],
 ['unknown composition mode',r=>r.visuals.composition_mode='other'],
 ['unknown pareto mode',r=>r.visuals.pareto_mode='other'],
 ['wrong pareto scope',r=>r.visuals.pareto_denominator_scope='whole_factory'],
 ['wrong period',r=>r.visuals.period.id='foreign'],
 ['wrong coverage',r=>r.visuals.coverage.calculated=0],
 ['duplicate OTHER members',r=>{const p=r.visuals.composition.find(p=>p.id==='OTHER');p.members[1]=p.members[0];}],
 ['wrong composition unit',r=>r.visuals.composition[0].unit='IRR/product'],
 ['unexpected protected visual field',r=>r.visuals.source_path='/private/source.json'],
],DashboardVisuals.adaptCost);
rejects(data.partial,[
 ['foreign excluded identity',r=>r.visuals.excluded[0].identity.factory_id='foreign'],
 ['excluded shown as available',r=>r.visuals.excluded[0].state='OK'],
 ['excluded fabricated zero',r=>r.visuals.excluded[0].unit_cost='0'],
],DashboardVisuals.adaptCost);
''', cost_payloads)


def test_canonical_rows_reject_bad_components_counts_and_context(cost_payloads):
    _node(r'''
rejects(data.full,[
 ['wrong formula',r=>r.analysis.formula_version='unknown'],
 ['BOM numeric coercion',r=>r.analysis.detail_rows[0].bom_components[0].live_cost_in_rial=100],
 ['BOM null',r=>r.analysis.detail_rows[0].bom_components[0].live_cost_in_rial=null],
 ['driver wrong factor',r=>r.analysis.detail_rows[0].driver_components[0].pool_id='BOM'],
 ['missing driver',r=>r.analysis.detail_rows[0].driver_components.pop()],
 ['duplicate BOM row',r=>r.analysis.detail_rows[0].bom_components.push(clone(r.analysis.detail_rows[0].bom_components[0]))],
 ['different canonical product amount',r=>r.analysis.breakdowns.products[0].unit_cost='1'],
 ['weighted coverage mismatched',r=>r.analysis.kpis.weighted_average.coverage.calculated=0],
 ['pool coverage mismatched',r=>r.analysis.breakdowns.factory_pools[0].coverage.configured=99],
 ['top driver state mismatched',r=>r.analysis.kpis.top_cost_driver.state='NOT_APPLICABLE'],
 ['foreign lineage identity',r=>r.analysis.source_lineage.find(p=>p.identity).identity.factory_id='foreign'],
],r=>{assert(DashboardReport.validate(r.analysis));});
''', cost_payloads)


def test_lab_accepts_real_experiments_limits_nullable_and_redacted_grants(lab_payloads):
    _node(r'''
for (const [name, raw] of Object.entries(data)) {
    const accepted=DashboardLab.adapt(raw);assert.deepStrictEqual(accepted.lab,raw,name);
    assert(Object.isFrozen(accepted.lab.scenarios));assert(Object.isFrozen(accepted.context.parameters));
}
assert.equal(data.maximum.evaluation_budget.reserved,124);
assert.equal(data.one.experiment.invalid_count,2);
assert.equal(data.invalid_tornado.experiment.ranking[0].state,'INVALID_INPUT');
assert.equal(data['dashboard-user'].parameters.length,0);
''', lab_payloads)


def test_lab_rejects_comparison_directions_references_factors_and_budget(lab_payloads):
    _node(r'''
rejects(data.base,[
 ['duplicate scenario',r=>r.scenarios[1].id='A'],
 ['unknown scenario',r=>r.scenarios[1].id='C'],
 ['wrong baseline context',r=>r.baseline_context='cached'],
 ['wrong direction',r=>r.comparisons.B_minus_A.unit_cost.direction='A_minus_B'],
 ['wrong reference',r=>r.comparisons.B_minus_A.unit_cost.reference='0'],
 ['wrong target',r=>r.comparisons.B_minus_A.projected_cost.target='0'],
 ['wrong percentage denominator',r=>r.comparisons.B_minus_A.unit_cost.percentage_denominator='0'],
 ['false zero state',r=>{r.comparisons.B_minus_A.unit_cost.percentage_state='NOT_APPLICABLE';r.comparisons.B_minus_A.unit_cost.percentage=null;}],
 ['duplicate waterfall factor',r=>r.comparisons.B_minus_A.waterfall.components[1].id='BOM'],
 ['unknown waterfall factor',r=>r.comparisons.B_minus_A.waterfall.components[0].id='UNKNOWN'],
 ['wrong technical factor',r=>r.comparisons.B_minus_A.waterfall.technical_reconciliation.id='BOM'],
 ['wrong waterfall context',r=>r.comparisons.B_minus_A.waterfall.meaning='causal_input_attribution'],
 ['negative chart size',r=>r.comparisons.B_minus_A.waterfall.components[0].size='-1'],
 ['broken waterfall chain',r=>r.comparisons.B_minus_A.waterfall.components[1].start='99'],
 ['extra comparison',r=>r.comparisons.A_minus_B=clone(r.comparisons.B_minus_A)],
 ['negative executed',r=>r.evaluation_budget.executed=-1],
 ['baseline evaluations omitted',r=>r.evaluation_budget.executed=0],
 ['reserved wrong',r=>r.evaluation_budget.reserved=4],
 ['wrong budget maximum',r=>r.evaluation_budget.maximum=201],
 ['extra top protected field',r=>r.prediction='10'],
 ['missing scenario pool',r=>r.scenarios[0].result.breakdown.driver_components.pop()],
],DashboardLab.adapt);
''', lab_payloads)


def test_lab_rejects_point_indices_counts_axes_and_redaction(lab_payloads):
    _node(r'''
rejects(data.two,[
 ['duplicate cell',r=>r.experiment.points[1].indices=clone(r.experiment.points[0].indices)],
 ['negative index',r=>r.experiment.points[0].indices[0]=-1],
 ['sparse index',r=>r.experiment.points[0].indices[0]=10],
 ['noninteger index',r=>r.experiment.points[0].indices[0]=0.5],
 ['missing index',r=>r.experiment.points[0].indices.pop()],
 ['wrong source unit',r=>r.experiment.points[0].inputs[0].unit='IRR/product'],
 ['axis changes parameter',r=>r.experiment.points[1].inputs.reverse()],
 ['axis inconsistent coordinate',r=>r.experiment.points[1].inputs[0].value='26'],
 ['missing effective input',r=>r.experiment.points[0].effective_inputs.pop()],
 ['effective source mismatch',r=>r.experiment.points[0].effective_inputs[0].baseline_value='999'],
 ['duplicate effective input',r=>r.experiment.points[0].effective_inputs[1]=clone(r.experiment.points[0].effective_inputs[0])],
 ['fabricated valid count',r=>r.experiment.valid_count=99],
 ['wrong point delta target',r=>r.experiment.points[0].unit_delta.target='0'],
 ['wrong experiment unit',r=>r.experiment.unit_cost_unit='IRR/period'],
 ['protected full point result',r=>r.experiment.points[0].prediction='10'],
 ['protected input field',r=>r.experiment.points[0].inputs[0].source_path='/private/source.json'],
 ['missing successful evaluations',r=>r.evaluation_budget.executed=3],
],DashboardLab.adapt);
rejects(data.one,[
 ['invalid point fabricated zero',r=>r.experiment.points.find(p=>p.state==='INVALID_INPUT').unit_cost='0'],
 ['invalid point hides reason',r=>r.experiment.points.find(p=>p.state==='INVALID_INPUT').issue=null],
 ['invalid point exposes effective source',r=>r.experiment.points.find(p=>p.state==='INVALID_INPUT').effective_inputs=[r.experiment.points.find(p=>p.state==='OK').effective_inputs[0]]],
],DashboardLab.adapt);
rejects(data.tornado,[
 ['unknown side',r=>r.experiment.points[0].side='middle'],
 ['duplicate side',r=>r.experiment.points[1].side='low'],
 ['duplicate ranking',r=>r.experiment.ranking[1]=clone(r.experiment.ranking[0])],
 ['negative impact',r=>r.experiment.ranking[0].impact='-1'],
 ['wrong ranking state',r=>{r.experiment.ranking[0].state='INVALID_INPUT';r.experiment.ranking[0].impact=null;}],
],DashboardLab.adapt);
rejects(data['dashboard-user'],[
 ['protected prediction',r=>r.baseline.prediction='10'],
 ['protected raw pool',r=>r.scenarios[0].result.breakdown.driver_components[0].raw_factory_pool='1000'],
 ['protected extension input',r=>r.scenarios[0].source_path='/private/source.json'],
],DashboardLab.adapt);
''', lab_payloads)


def test_real_zero_projected_zero_unit_and_backend_residues_remain_accepted(sensitivity):
    from copy import deepcopy
    from decimal import Decimal
    from utils.dashboard_analysis import serialize
    from utils.dashboard_visual_sensitivity import comparison

    env = sensitivity
    _g2_fixture(env, predictions=(0, 10))
    projected_zero = run(env).json
    zero_product_cost = env.client.get(VISUALS, query_string=SELECTION).json
    _g2_fixture(env, pool=0)
    unit_zero = run(env).json
    zero_total_cost = env.client.get(VISUALS, query_string=SELECTION).json
    _g2_fixture(env)
    residue = deepcopy(run(env).json)
    residue['scenarios'][0]['result']['unit_cost'] = '100.0000000000000000000000001'

    def amounts(result):
        return {'unit_cost': Decimal(result['unit_cost']), 'projected_cost': Decimal(result['projected_cost']),
                'bom_total': Decimal(result['bom_total']), 'breakdown': {'driver_components': [
                    {'pool_id': row['pool_id'], 'per_unit_contribution': Decimal(row['per_unit_contribution'])}
                    for row in result['breakdown']['driver_components']]}}

    baseline, a, b = map(amounts, [residue['baseline'], *[s['result'] for s in residue['scenarios']]])
    residue['comparisons'] = serialize({direction: comparison(reference, target, direction)
        for direction, reference, target in [('A_minus_baseline', baseline, a),
                                              ('B_minus_baseline', baseline, b), ('B_minus_A', a, b)]})
    assert residue['comparisons']['A_minus_baseline']['waterfall']['reconciliation'] != '0'
    _node(r'''
for(const raw of [data.projected_zero,data.unit_zero,data.residue])DashboardLab.adapt(raw);
for(const raw of [data.zero_product_cost,data.zero_total_cost])DashboardVisuals.adaptCost(raw);
assert.equal(data.zero_product_cost.analysis.kpis.weighted_average.state,'NOT_APPLICABLE');
assert.equal(data.projected_zero.comparisons.B_minus_A.projected_cost.percentage,null);
assert.equal(data.unit_zero.comparisons.A_minus_baseline.unit_cost.percentage,null);
assert(DashboardLab.csv(data.residue).includes('0.0000000000000000000000001'));
rejects(data.unit_zero,[['zero must have null percentage',r=>{
    r.comparisons.A_minus_baseline.unit_cost.percentage_state='OK';r.comparisons.A_minus_baseline.unit_cost.percentage='0';
}]],DashboardLab.adapt);
''', {'projected_zero': projected_zero, 'unit_zero': unit_zero, 'residue': residue,
      'zero_product_cost': zero_product_cost, 'zero_total_cost': zero_total_cost})
