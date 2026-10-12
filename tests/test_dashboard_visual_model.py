"""Node validation/export checks against real authorized API responses."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from test_dashboard_sensitivity import sensitivity, analysis, _material_fixture, _parameter, _change, SELECTION
from test_dashboard_visual_analysis import run, VISUALS

ROOT=Path(__file__).resolve().parents[1]


def test_real_wrapper_adapters_freeze_reject_malformed_and_export_exact(sensitivity):
    if not shutil.which('node'):pytest.skip('Node is required for browser-model tests')
    env=sensitivity
    _material_fixture(env,usages=(1,))
    p=_parameter(env,'material:')
    lab=run(env,[_change(p,'0.000000000000000000000000001')],[_change(p,'-100','percent_change')],
        experiment={'type':'one_factor','axes':[{'parameter_id':p,'mode':'percent_change','values':['-110','0','10']}]}).json
    cost=env.client.get(VISUALS,query_string=SELECTION).json
    script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');global.window=global;
for(const file of ['dashboard-numbers.js','dashboard-report.js','dashboard-visuals.js','dashboard-sensitivity-model.js','dashboard-lab.js'])vm.runInThisContext(fs.readFileSync('static/js/'+file,'utf8'));
const {lab,cost}=JSON.parse(fs.readFileSync(0,'utf8'));
const a=DashboardLab.adapt(lab);assert(Object.isFrozen(a.lab));assert(Object.isFrozen(a.lab.experiment.points));
const c=DashboardVisuals.adaptCost(cost);assert(Object.isFrozen(c.visuals.products));
const altered=structuredClone(lab);altered.baseline.prediction='123';altered.permissions.factory_parameters=false;assert.throws(()=>DashboardLab.adapt(altered));
const bad=structuredClone(lab);bad.comparisons.B_minus_A.projected_cost.amount=500;assert.throws(()=>DashboardLab.adapt(bad));
const malformed=structuredClone(cost);malformed.visuals.products[0].unit_cost=1;assert.throws(()=>DashboardVisuals.adaptCost(malformed));
const injected=structuredClone(lab);function inject(v){if(v&&typeof v==='object'){if('factory_id' in v)v.factory_id='=HYPERLINK("bad")';Object.values(v).forEach(inject);}}inject(injected);
const csv=DashboardLab.csv(injected);assert(csv.startsWith('\uFEFF'));assert(csv.includes("'=HYPERLINK"));
assert(csv.includes('0.000000000000000000000000001'));assert(csv.includes('"-100"'));assert(!csv.includes("'-100"));
assert(csv.includes('experiment_final_input'));assert(csv.includes('INVALID_INPUT'));assert(csv.includes('percentage'));
assert(csv.includes('point_minus_baseline'));assert(csv.includes('B_minus_A'));assert(csv.includes('IRR/period'));
console.log('exact adapters, immutable snapshots, redaction rejection, safe CSV and unavailable points passed');
'''
    result=subprocess.run(['node','-e',script],cwd=ROOT,input=json.dumps({'lab':lab,'cost':cost}),text=True,capture_output=True)
    assert result.returncode==0,result.stderr
