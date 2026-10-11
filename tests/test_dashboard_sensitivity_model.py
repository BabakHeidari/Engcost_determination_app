"""PR-09 exact inputs, PR-08 envelopes, accepted snapshots and safe CSV."""

import json
from pathlib import Path
import shutil
import subprocess

import pytest

from test_dashboard_cost_analysis import analysis
from test_dashboard_sensitivity import SELECTION, _change, _parameters, _scenario, sensitivity


ROOT = Path(__file__).resolve().parents[1]


def _node(script, payload=None):
    node = shutil.which("node")
    if not node:
        pytest.skip("Sensitivity model checks require Node")
    prelude = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const context = {window: {}};
vm.runInNewContext(fs.readFileSync(process.argv[1] + '/static/js/dashboard-numbers.js', 'utf8'), context);
vm.runInNewContext(fs.readFileSync(process.argv[1] + '/static/js/dashboard-sensitivity-model.js', 'utf8'), context);
const m = context.window.DashboardSensitivityModel;
const data = JSON.parse(fs.readFileSync(0, 'utf8'));
const clone = value => JSON.parse(JSON.stringify(value));
"""
    result = subprocess.run([node, "-e", prelude + script, str(ROOT)], input=json.dumps(payload),
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.fixture
def envelopes(sensitivity):
    reports = {"get": _parameters(sensitivity).get_json(), "post": _scenario(sensitivity).get_json()}
    reports["override-post"] = _scenario(sensitivity, [_change("pool:Payroll", "9007199254740993.1234567890123456789000")]).get_json()
    for user in ("general-only", "factory-only", "wrong-factory-group"):
        reports[user + "-get"] = _parameters(sensitivity, user=user).get_json()
        reports[user + "-post"] = _scenario(sensitivity, user=user).get_json()
    reports["domain-failure"] = _scenario(sensitivity, [_change("pool:Payroll", "-1")]).get_json()
    reports["parser-failure"] = _scenario(sensitivity, [_change("pool:Payroll", 1)]).get_json()
    reports["access-failure"] = _parameters(sensitivity, factory="factory-secret").get_json()
    reports["selection-failure"] = _parameters(sensitivity, product="__ALL__").get_json()
    (sensitivity.data / "Overall" / "material_costs.json").unlink()
    reports["source-failure"] = _parameters(sensitivity).get_json()
    sensitivity.binding.unlink()
    reports["binding-failure"] = _parameters(sensitivity).get_json()
    reports["selection"] = {**SELECTION, "period_id": SELECTION["period"], "productLabel": "A"}
    return reports


def test_adapter_accepts_actual_pr08_success_grants_and_failure_envelopes(envelopes):
    _node(r"""
for (const [kind, report] of Object.entries(data)) {
    if (kind === 'selection') continue;
    assert.equal(m.validate(report), true, 'Actual PR08 schema rejected: ' + kind);
    const snapshot = m.adapt(report);
    assert.equal(Object.isFrozen(snapshot), true);
    assert.equal(Object.isFrozen(snapshot.parameters), true);
    assert.equal(JSON.stringify(snapshot), JSON.stringify(report));
}
assert.equal(data['access-failure'].baseline, null);
assert.equal(data['access-failure'].scenario, null);
assert.equal(data['parser-failure'].baseline, null);
assert.equal(data['parser-failure'].scenario, null);
assert.equal(data['source-failure'].baseline.unit_cost, null);
assert.equal(data['binding-failure'].period, null);
assert.equal(data['domain-failure'].baseline.state, 'OK');
assert.equal(data['domain-failure'].scenario.state, 'INVALID_INPUT');
assert.equal(data['wrong-factory-group-get'].parameters.length, 0);
assert.equal(m.canExport(data.get), false);
assert.equal(m.canExport(data.post), true);
assert.equal(m.canExport(data['override-post']), true);
for (const kind of ['access-failure', 'selection-failure', 'source-failure', 'binding-failure', 'domain-failure', 'parser-failure']) {
    assert.equal(m.canExport(data[kind]), false);
    assert.throws(() => m.csv(data[kind]));
}
""", envelopes)


def test_schema_rejects_untrusted_inconsistent_and_sensitive_fields(envelopes):
    _node(r"""
const invalid = [];
function changed(callback, source = data.post) {const result = clone(source); callback(result); invalid.push(result);}
changed(r => r.version = '2');
changed(r => r.formula_version = 'unknown-formula');
changed(r => r.non_persistent = false);
changed(r => r.baseline.unit_cost = 1);
changed(r => r.scenario.breakdown.driver_components[0].per_unit_contribution = 'NaN');
changed(r => r.parameters[0].domain.minimum = 0);
changed(r => r.parameters[0].domain.maximum = '-1');
changed(r => r.parameters[0].period.id = 'foreign-period');
changed(r => r.parameters[0].source_reference.file_path = '/private/source.json');
changed(r => r.parameters[0].group = r.parameters[0].group === 'general_parameters' ? 'factory_parameters' : 'general_parameters');
changed(r => r.parameters[0].provenance.fingerprint = '0'.repeat(64));
changed(r => r.parameters.push(clone(r.parameters[0])));
changed(r => r.parameters[0].effect_context = 'all_scenario_inputs');
changed(r => r.parameters[0].scope = 'all_factories');
changed(r => r.source_lineage[0].raw_inputs = {});
changed(r => r.scenario.projected_cost_scope = 'whole_factory');
changed(r => r.effective_overrides = [{parameter_id:'unknown',mode:'absolute',value:'1',baseline_value:'0',final_value:'1',unit:'IRR',provenance_state:'HYPOTHETICAL_OVERRIDE'}]);
changed(r => r.delta.percentage_state = 'NOT_APPLICABLE');
changed(r => r.delta = null);
changed(r => r.permissions.general_parameters = false);
changed(r => r.baseline.prediction = '100', data['general-only-post']);
changed(r => r.baseline.breakdown.driver_components[0].raw_factory_pool = '100', data['general-only-post']);
changed(r => r.scenario.unit_cost = '0', data['domain-failure']);
changed(r => r.identity.factory_id = 'different', data['source-failure']);
changed(r => r.period = {id:'P',start:'2026-02-30',end:'2026-03-01'});
for (const report of invalid) {
    assert.equal(m.validate(report), false);
    assert.throws(() => m.adapt(report));
}
""", envelopes)


def test_localized_decimal_input_preserves_precision_and_rejects_ambiguous_notation():
    _node(r"""
const cases = [
    ['  +۱۰٫۵۰۰۰  ', '10.5000'], ['١٢٣٫٤٥٠٠', '123.4500'], ['−۰٫۰۰۰', '-0.000'],
    ['۹۰۰۷۱۹۹۲۵۴۷۴۰۹۹۳٫۱۲۳۴۵۶۷۸۹۰۱۲۳۴۵۶۷۸۹۰', '9007199254740993.12345678901234567890'],
    ['-1.00000000000000000000001', '-1.00000000000000000000001'], ['0', '0']
];
for (const [raw, expected] of cases) {
    const normalized = m.normalizeInput(raw);
    assert.equal(normalized.valid, true, raw);
    assert.equal(normalized.value, expected);
}
for (const raw of ['', ' ', '1e2', '۱e۲', 'NaN', 'Infinity', '1,000', '۱٬۰۰۰', '1 000', '1,2',
        '١,٢', '1.2.3', '۱٫۲.۳', '.5', '1.', '01', '-01', '--1', '+-1', '++1', '1%', true, null, 100]) {
    const normalized = m.normalizeInput(raw);
    assert.equal(normalized.valid, false, String(raw));
    assert.equal(typeof normalized.error, 'string');
    assert.match(normalized.error, /[آ-ی]/);
}
assert.equal(m.normalizeInput('9'.repeat(128)).valid, true);
assert.equal(m.normalizeInput('9'.repeat(129)).code, 'DECIMAL_TOO_LONG');
assert.equal(m.normalizeInput('-' + '9'.repeat(127)).valid, true);
assert.equal(m.normalizeInput('-' + '9'.repeat(128)).valid, false);
""")


def test_absolute_domains_use_exact_comparison_and_relative_values_remain_server_authoritative():
    _node(r"""
const parameter = {parameter_id:'opaque-id',applicable:true,editable:true,supported_modes:['absolute','percent_change'],
    domain:{minimum:'9007199254740993.12345678901234567890',minimum_exclusive:true,
        maximum:'9007199254740993.12345678901234567892',maximum_exclusive:false}};
assert.equal(m.validateOverride(parameter, 'absolute', '9007199254740993.12345678901234567890').valid, false);
assert.equal(m.validateOverride(parameter, 'absolute', '9007199254740993.12345678901234567891').valid, true);
assert.equal(m.validateOverride(parameter, 'absolute', '9007199254740993.12345678901234567892').valid, true);
assert.equal(m.validateOverride(parameter, 'absolute', '9007199254740993.12345678901234567893').valid, false);
const share = {...parameter,domain:{minimum:'0',minimum_exclusive:true,maximum:'100',maximum_exclusive:false}};
assert.equal(m.validateOverride(share, 'absolute', '-0.000').valid, false);
assert.equal(m.validateOverride(share, 'absolute', '0.000000000000000000001').valid, true);
assert.equal(m.validateOverride(share, 'absolute', '100.000000000000000000001').valid, false);
assert.equal(m.validateOverride(share, 'absolute', '100.0000').override.value, '100.0000');
assert.equal(m.validateOverride(share, 'percent_change', '+۱۰٫۰۰').override.value, '10.00');
assert.equal(m.validateOverride(share, 'percent_change', '-100.001').valid, true);
assert.equal(m.validateOverride({...share,editable:false}, 'absolute', '20').valid, false);
assert.equal(m.validateOverride(share, 'unknown', '20').valid, false);
""")


def test_request_builder_has_only_pr08_fields_and_enforces_technical_limits(envelopes):
    _node(r"""
const selected = data.selection;
const change = {parameter_id:'opaque-registry-id',mode:'absolute',value:'9007199254740993.000001'};
const request = m.buildRequest({...selected, productLabel:'private label', client_baseline:'fake'}, [change]);
assert.equal(request.valid, true);
assert.equal(request.body.period, selected.period_id);
assert.equal(Object.keys(request.body).sort().join(','), 'category,factory,overrides,period,product,subcategory');
assert.equal(request.body.overrides[0].value, change.value);
assert.equal(request.json, JSON.stringify(request.body));
assert.equal(m.buildRequest(selected, []).valid, true);
assert.equal(m.buildRequest({...selected,product:'__ALL__'}, []).valid, false);
assert.equal(m.buildRequest({...selected,period_id:''}, []).valid, false);
assert.equal(m.buildRequest(selected, [change,change]).valid, false);
assert.equal(m.buildRequest(selected, [{...change,value:100}]).valid, false);
assert.equal(m.buildRequest(selected, [{...change,value:'+' + change.value}]).valid, false);
assert.equal(m.buildRequest(selected, [{...change,value:'9'.repeat(129)}]).valid, false);
assert.equal(m.buildRequest(selected, Array.from({length:65}, (_,i) => ({...change,parameter_id:'id-' + i}))).code, 'TOO_MANY_OVERRIDES');
assert.equal(m.buildRequest({...selected,start:'2026-01-01'}, []).code, 'INCOMPLETE_PERIOD_RANGE');
assert.equal(m.buildRequest({...selected,start:'2026-01-01',end:'2026-01-31'}, []).valid, true);
const longSelection = Object.fromEntries(['factory','category','subcategory','product','period_id'].map(key => [key,'ࠀ'.repeat(2048)]));
const manyChanges = Array.from({length:64}, (_,i) => ({parameter_id:String(i).padStart(3,'0') + 'ࠀ'.repeat(253),mode:'absolute',value:'9'.repeat(128)}));
assert.equal(m.buildRequest(longSelection, manyChanges).code, 'BODY_TOO_LARGE');
""", envelopes)


def test_scope_matching_uses_human_identity_and_snapshot_context_detects_source_changes(envelopes):
    _node(r"""
assert.equal(m.matchesScope(data.get, data.selection), true);
assert.equal(m.matchesScope(data.post, data.selection), true);
for (const key of ['factory','category','subcategory','period_id','productLabel']) {
    assert.equal(m.matchesScope(data.get, {...data.selection,[key]:'different'}), false);
}
assert.equal(m.matchesScope(data.get, {...data.selection,productLabel:undefined}), false);
assert.equal(m.matchesScope(data.get, {...data.selection,start:'1999-01-01'}), false);
assert.equal(m.matchesScope(data['access-failure'], data.selection), false);
const first = m.contextKey(data.get);
assert.equal(m.contextKey(data.post), first);
const changed = clone(data.get);
changed.calculated_at = '2026-10-01T10:00:00+00:00';
assert.equal(m.contextKey(changed), first);
changed.source_lineage[0].fingerprint = 'a'.repeat(64);
assert.notEqual(m.contextKey(changed), first);
""", envelopes)


def test_accepted_csv_preserves_exact_server_strings_and_neutralizes_text_formulas(envelopes):
    _node(r"""
const accepted = clone(data.post);
accepted.baseline.unit_cost = '9007199254740993.1234567890123456789000';
accepted.scenario.unit_cost = '9007199254740993.1234567890123456788999';
accepted.delta.amount = '-0.0000000000000000000001';
accepted.delta.percentage = '-0.000000000000000000000000000001';
accepted.identity.product = '=HYPERLINK("https://evil.example")';
accepted.baseline.breakdown.bom_components[0].material = '  +malicious';
accepted.source_lineage[0].business_version = '\t@SUM(A1)';
for (const parameter of accepted.parameters) {
    if (parameter.provenance.source === accepted.source_lineage[0].source) parameter.provenance.business_version = accepted.source_lineage[0].business_version;
    for (const dependency of parameter.dependencies) {
        if (dependency.kind === 'product_predictions') dependency.identity.product = accepted.identity.product;
    }
}
const snapshot = m.adapt(accepted);
accepted.scenario.unit_cost = '1';
assert.equal(snapshot.scenario.unit_cost, '9007199254740993.1234567890123456788999');
const csv = m.csv(snapshot);
assert.equal(csv.charCodeAt(0), 0xFEFF);
assert.equal(csv.includes('9007199254740993.1234567890123456789000'), true);
assert.equal(csv.includes('9007199254740993.1234567890123456788999'), true);
assert.equal(csv.includes('"-0.0000000000000000000001"'), true);
assert.equal(csv.includes('"\'=HYPERLINK(""https://evil.example"")"'), true);
assert.equal(csv.includes('"\'  +malicious"'), true);
assert.equal(csv.includes('"\'\t@SUM(A1)"'), true);
assert.equal(csv.includes('"non_persistent"'), true);
assert.equal(csv.includes('سناریوی فرضی؛ فقط شبیه‌سازی و بدون ذخیره در منابع'), true);
assert.equal(csv.includes('"direction"'), true);
assert.equal(csv.includes('"period_start"'), true);
assert.equal(csv.includes('scenario_minus_baseline'), true);
assert.equal(csv.includes('private/source.json'), false);
assert.throws(() => m.csv(data.get));
const overridden = clone(data['override-post']);
const selected = overridden.parameters.find(parameter => parameter.parameter_id === overridden.effective_overrides[0].parameter_id);
selected.label = '-malicious_parameter_name';
const overrideCsv = m.csv(m.adapt(overridden));
const exact = overridden.effective_overrides[0];
for (const key of ['value', 'baseline_value', 'final_value']) assert.equal(overrideCsv.includes('"' + exact[key] + '"'), true);
assert.equal(overrideCsv.includes('HYPOTHETICAL_OVERRIDE'), true);
assert.equal(overrideCsv.includes('"\'-malicious_parameter_name"'), true);
""", envelopes)


def test_csv_distinguishes_per_product_period_and_prediction_units_with_grant_redaction(envelopes):
    _node(r"""
function parsed(report) {
    // These actual fixture identities have no comma or quotes. Parse the
    // quoted cells without converting any financial string to a JS number.
    const lines = m.csv(report).slice(1).trimEnd().split('\r\n');
    const cells = line => line.slice(1, -1).split('\",\"').map(cell => cell.replace(/\"\"/g, '\"'));
    const headers = cells(lines.shift());
    return lines.map(line => Object.fromEntries(cells(line).map((cell, index) => [headers[index], cell])));
}
for (const kind of ['post', 'general-only-post', 'factory-only-post', 'wrong-factory-group-post']) {
    const rows = parsed(data[kind]);
    const summary = rows.find(row => row.row_type === 'scenario');
    assert.equal(summary.bom_total_unit, 'IRR/product');
    assert.equal(summary.driver_total_unit, 'IRR/product');
    assert.equal(summary.projected_cost_unit, 'IRR/period');
    const bom = rows.find(row => row.row_type === 'scenario_bom');
    assert.equal(bom.live_cost_in_rial_unit, 'IRR/product');
    const driver = rows.find(row => row.row_type === 'scenario_driver');
    assert.equal(driver.unit, '');
    assert.equal(driver.per_unit_contribution_unit, 'IRR/product');
    assert.equal(driver.product_period_contribution_unit, 'IRR/period');
    for (const key of ['raw_factory_pool','adjusted_category_pool','modeled_minus_raw','category_prediction_total']) {
        if (data[kind].permissions.factory_parameters) {
            assert.equal(driver[key + '_unit'], key === 'category_prediction_total' ? 'product/period' : 'IRR/period');
            assert.notEqual(driver[key], '');
        } else {
            assert.equal(driver[key], '');
            assert.equal(driver[key + '_unit'], '');
        }
    }
}
""", envelopes)
