"""Material identity stays Unicode through Windows reads, edits and BOM saves."""
import builtins
import json
from pathlib import Path

import pytest

from html_contract import javascript_json
from utils.profile_store import ProfileDataStore


@pytest.fixture
def material_workflow(tmp_path, monkeypatch):
    import app as app_module

    profiles = tmp_path / 'profiles.json'
    store = ProfileDataStore(profiles)
    store.initialize({})
    store.create_factory({'id':'unicode-factory', 'code':'UNICODE', 'name':'کارخانه آزمون',
                                    'operational_key':'unicode-factory', 'is_active':True})
    user = store.create_user({'id':'unicode-owner', 'username':'unicode-owner', 'email':'unicode@example.test',
                              'full_name':'کاربر آزمون', 'system_role':'IT_ADMIN', 'is_active':True,
                              'must_change_password':False, 'password_hash':'unused', 'password_scheme':'werkzeug'})
    data = tmp_path / 'Data'
    overall = data / 'Overall'
    overall.mkdir(parents=True)
    columns = ['material','unit','currency','cost_per_unit_in_currency']
    for name in ('material_costs', 'material_costs_history'):
        document = {'_order':columns, 'data':{key:[] for key in columns}}
        if name.endswith('_history'):
            document['data']['modification_date'] = []
        (overall / (name + '.json')).write_text(json.dumps(document), encoding='utf-8')
    bom = data / 'Factories/unicode-factory/دسته/زیر دسته/محصول.json'
    bom.parent.mkdir(parents=True)
    bom.write_text(json.dumps({'_order':['materials','usage','lost_percentage','recycability_percentage'],
                               'data':{'materials':[],'usage':[],'lost_percentage':[],'recycability_percentage':[]}}), encoding='utf-8')
    prefix = str(overall / 'material_costs')
    for module in ('modules.general_parameters.routes', 'modules.product.routes', 'utils.updaters'):
        monkeypatch.setattr(module + '.material_path', prefix)
    monkeypatch.setattr('utils.load_data.parent_path', str(data))
    monkeypatch.setitem(app_module.app.config, 'APP_DATA_FILE', str(profiles))
    monkeypatch.setitem(app_module.app.config, 'SECRET_KEY', 'isolated-unicode-test')
    monkeypatch.setitem(app_module.app.config, 'TESTING', True)
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session['user_id'] = user['id']
    return client, overall, bom


def windows_default_reader(monkeypatch, material_file):
    original = builtins.open
    def open_like_windows(file, mode='r', *args, **kwargs):
        if (isinstance(file, (str, Path)) and Path(file) == material_file
                and 'r' in mode and 'b' not in mode and not args and kwargs.get('encoding') is None):
            kwargs['encoding'] = 'cp1252'
        return original(file, mode, *args, **kwargs)
    monkeypatch.setattr(builtins, 'open', open_like_windows)


@pytest.mark.parametrize('name', ['اسید', 'سرب\u200cاسید', 'اسید "ویژه" & </script>'])
def test_add_reload_edit_and_bom_keep_exact_unicode_identity(material_workflow, monkeypatch, name):
    client, overall, bom = material_workflow
    windows_default_reader(monkeypatch, overall / 'material_costs.json')
    material = {'material':name, 'unit':'کیلوگرم', 'currency':'IRR - Iranian Rial', 'cost_per_unit_in_currency':125}
    def save(added=None, edited=None):
        return client.post('/save_materials', data=json.dumps({'added':added or [], 'edited':edited or [],
            'deleted':[], 'last_modification_date':'2026-10-14T00:00:00Z'}, ensure_ascii=False).encode('utf-8'),
            content_type='application/json')
    assert save(added=[material]).status_code == 200
    path = overall / 'material_costs.json'
    raw = path.read_bytes()
    assert json.loads(raw)['data']['material'] == [name]
    page = client.get('/general_parameters/')
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'Ø§Ø³ÛŒØ¯' not in html
    delivered = javascript_json(html, 'tableJSON')['data']
    assert delivered['material'] == [name] and delivered['unit'] == ['کیلوگرم']
    assert path.read_bytes() == raw
    assert save(edited=[{'_originalIndex':0, **{key:value[0] for key,value in delivered.items()},
                        'cost_per_unit_in_currency':150}]).status_code == 200
    assert json.loads(path.read_bytes())['data']['material'] == [name]
    history_names = json.loads((overall / 'material_costs_history.json').read_bytes())['data']['material']
    assert history_names and all(value == name for value in history_names)
    product = client.post('/product/محصول', data={'factory':'unicode-factory','category':'دسته','subcategory':'زیر دسته'})
    assert product.status_code == 200
    lookup = javascript_json(product.get_data(as_text=True), 'materialsData')['data']
    assert lookup['material'] == [name] and lookup['cost_per_unit_in_currency'] == [150]
    response = client.post('/save_bom', json={'_order':['materials','usage','lost_percentage','recycability_percentage'],
                       'data':{'materials':[name],'usage':[2],'lost_percentage':[0],'recycability_percentage':[0]}})
    assert response.status_code == 200
    stored = json.loads(bom.read_bytes())['data']
    assert stored['materials'] == [name] and stored['unit'] == ['کیلوگرم']
    assert stored['cost_of_material_in_rial'] == [300]


def test_template_serializes_null_and_script_delimiters_as_json(material_workflow):
    client, overall, _ = material_workflow
    path = overall / 'material_costs.json'
    value = {'_order':['material','note'], 'data':{'material':['اسید </script>'], 'note':[None]}, 'available':False}
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    html = client.get('/general_parameters/').get_data(as_text=True)
    assert javascript_json(html, 'tableJSON') == value
    assert 'اسید </script>' not in html
