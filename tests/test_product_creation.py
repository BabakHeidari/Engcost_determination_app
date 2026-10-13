"""Owner-UAT regression: real routes, only temporary operational fixtures."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from html_contract import javascript_json
from utils.factory_configuration import POOL_IDS, configuration_paths, ensure_factory_configuration_v2
from utils.profile_store import ProfileDataStore


CATEGORY = "دسته جدید (آزمون)"
SUB = "زیر دسته - یک"
PRODUCT = "محصول 'ویژه' + ۱"
FACTORY_ID = "factory-canonical"


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file() and p.name != '.product-creation.lock'}


def grant(module, level='READ'):
    return {'scope_type': 'FACTORY', 'factory_id': FACTORY_ID, 'module': module,
            'permissions': ['READ', 'WRITE', 'MODIFY'][:{'READ': 1, 'WRITE': 2, 'MODIFY': 3}[level]]}


@pytest.fixture
def journey(tmp_path, monkeypatch):
    profiles = tmp_path / 'profiles.json'
    store = ProfileDataStore(profiles); store.initialize({})
    # Empty registry before first app import, so startup cannot migrate real Data.
    monkeypatch.setenv('APP_DATA_FILE', str(profiles))
    import app as app_module
    from modules.product import routes
    from modules.factory_parameters import routes as financial
    from utils import updaters
    data = tmp_path / 'Data'; root = data / 'Factories' / 'f2'
    bom = {'_order': ['materials', 'usage', 'lost_percentage', 'recycability_percentage'], 'data': {
        'materials': ['lead'], 'usage': [1], 'lost_percentage': [0], 'recycability_percentage': [0]}}
    write(root / 'existing' / 'sub' / 'Original.json', bom)
    write(root / 'existing' / 'sub' / 'Original_meta.json', {'capacity': 123})
    write(data / 'Overall' / 'sample_product.json', bom)
    write(data / 'Overall' / 'material_costs.json', {'data': {
        'material': ['lead'], 'unit': ['kg'], 'currency': ['IRR - Iranian Rial'], 'cost_per_unit_in_currency': [2]}})
    write(root / 'category_weights.json', {'data': {'category': ['existing'], 'selling_share_of_category': [50]}})
    write(root / 'ProductionPrediction.json', {'data': {'Product Name': ['Original'], 'Predicted Production': [20]}})
    for pool in POOL_IDS:
        write(root / f'Factory_Data_{pool}.json', {'data': {'subject': ['fixture'], 'cost': [100]}})
    ensure_factory_configuration_v2(FACTORY_ID, 'f2', data_root=data)
    (root / 'category_weights.json').unlink(); (root / 'ProductionPrediction.json').unlink()
    for pool in POOL_IDS: (root / f'Factory_Data_{pool}.json').unlink()
    for factory_id, op, active in [(FACTORY_ID, 'f2', True), ('secret', 'other', True), ('inactive', 'off', False)]:
        store.create_factory({'id': factory_id, 'code': factory_id, 'name': 'کارخانه ' + factory_id,
                              'operational_key': op, 'is_active': active})
        (data / 'Factories' / op).mkdir(exist_ok=True)
    for uid, grants in [('writer', [grant('product', 'WRITE'), grant('factory_parameters'), grant('cost_calculation'), grant('dashboard')]),
                        ('finance', [grant('factory_parameters', 'MODIFY')]),
                        ('product-only', [grant('product', 'WRITE')]), ('reader', [grant('product')])]:
        store.create_user({'id': uid, 'username': uid, 'email': uid + '@example.test', 'full_name': 'کاربر',
                          'system_role': 'USER', 'job_title': 'کاربر', 'is_active': True, 'must_change_password': False,
                          'password_hash': 'unused', 'password_scheme': 'werkzeug', 'revision': 1, 'access_grants': grants})
    sources = ['materials', 'bom', 'weights', 'predictions', *[f'pool:{p}' for p in POOL_IDS]]
    binding = tmp_path / 'bindings.json'
    write(binding, {'bindings': [{'factory_id': FACTORY_ID, 'period_id': 'P', 'active': True, 'approved': True,
                                 'status': 'ACTIVE', 'start': '2026-10-01', 'end': '2026-12-31', 'sources': sources}]})
    for module in (routes, financial, updaters): monkeypatch.setattr(module, 'parent_path', data)
    for key, value in {'TESTING': True, 'APP_DATA_FILE': str(profiles), 'SECRET_KEY': 'fixture',
                       'COSTING_DATA_ROOT': str(data), 'COSTING_PERIOD_BINDINGS_FILE': str(binding)}.items():
        monkeypatch.setitem(app_module.app.config, key, value)
    client = app_module.app.test_client()
    with client.session_transaction() as session: session['user_id'] = 'writer'
    return app_module.app, client, root, data


def login(client, uid):
    with client.session_transaction() as session: session['user_id'] = uid


def product_payload(**changes):
    result = {'factory': FACTORY_ID, 'category': CATEGORY, 'subcategory': SUB, 'product_name': PRODUCT, 'capacity': 42}
    result.update(changes); return result


def parents(client):
    assert client.post('/add_category', json={'factory': FACTORY_ID, 'category_name': CATEGORY}).status_code == 200
    assert client.post('/add_subcategory', json={'factory': FACTORY_ID, 'category': CATEGORY, 'subcategory_name': SUB}).status_code == 200


def create_journey(client):
    parents(client)
    assert client.post('/add_product', json=product_payload()).status_code == 200


def test_v2_only_journey_financial_separation_and_later_authorized_save(journey):
    _, client, root, data = journey
    original = snapshot(root / 'configuration'); old_product = snapshot(root / 'existing')
    create_journey(client)
    assert snapshot(root / 'configuration') == original
    assert snapshot(root / 'existing') == old_product
    assert not (root / 'category_weights.json').exists()
    assert not (data / 'Factories' / FACTORY_ID).exists()
    assert json.loads((root / CATEGORY / SUB / f'{PRODUCT}_meta.json').read_text()) == {'capacity': 42}
    metadata = json.loads((data / 'Factories' / '__metadata.json').read_text())
    assert metadata['product_hierarchy']['f2'][CATEGORY] == [SUB]
    assert 'configuration' not in metadata['product_hierarchy']['f2']
    assert client.get('/api/product_options').get_json()['product_hierarchy'] == {FACTORY_ID: {'existing': ['sub'], CATEGORY: [SUB]}}
    page = client.get('/product/production_selection')
    table = javascript_json(page.get_data(as_text=True), 'rawData')
    assert PRODUCT in table['Product_Name'].values()
    assert set(table['Factory'].values()) == {FACTORY_ID}
    filters = client.get('/api/dashboard/filter-options', query_string={'factory': FACTORY_ID, 'category': CATEGORY, 'subcategory': SUB})
    assert filters.status_code == 200
    assert PRODUCT in repr(filters.get_json())
    cost_payload = {'Factory': FACTORY_ID, 'Category': CATEGORY, 'Subcategory': SUB, 'Product_Name': PRODUCT}
    before_cost = client.post('/cost/get_cost', json=cost_payload).get_json()
    assert before_cost['state'] in {'MISSING_INPUT', 'AMBIGUOUS_INPUT', 'INVALID_INPUT'}
    page = client.get(f'/factory_parameters/{FACTORY_ID}'); assert page.status_code == 200
    body = page.get_data(as_text=True)
    weights, prediction = javascript_json(body, 'weights'), javascript_json(body, 'predictions')
    assert weights['data'] == {'category': ['existing', CATEGORY], 'selling_share_of_category': [50, None]}
    assert prediction['data'] == {'Product Name': ['Original', PRODUCT], 'Predicted Production': [20, None]}
    assert {k: v for k, v in weights.items() if k != 'data'} == {k: v for k, v in json.loads(original['category_weights.json']).items() if k != 'data'}
    assert {k: v for k, v in prediction.items() if k != 'data'} == {k: v for k, v in json.loads(original['production_prediction.json']).items() if k != 'data'}
    assert snapshot(root / 'configuration') == original  # GET does not save catalog rows.
    for suffix, payload in [('category-weights', weights), ('production-prediction', prediction)]:
        assert client.put(f'/factory_parameters/{FACTORY_ID}/{suffix}', json=payload).status_code == 403
    assert snapshot(root / 'configuration') == original
    login(client, 'finance')
    weights['data']['selling_share_of_category'][1] = 25
    prediction['data']['Predicted Production'][1] = 10
    for suffix, payload in [('category-weights', weights), ('production-prediction', prediction)]:
        assert client.put(f'/factory_parameters/{FACTORY_ID}/{suffix}', json=payload).status_code == 200
    paths = configuration_paths(root)
    assert json.loads(paths['weights'].read_text()) == weights
    assert json.loads(paths['predictions'].read_text()) == prediction
    assert (root / 'configuration' / 'manifest.json').read_bytes() == original['manifest.json']
    login(client, 'writer')
    assert client.post('/cost/get_cost', json=cost_payload).get_json()['state'] == 'OK'


def test_product_only_writer_can_create_without_financial_access(journey):
    _, client, root, _ = journey
    login(client, 'product-only'); before = snapshot(root / 'configuration')
    create_journey(client)
    assert client.get(f'/factory_parameters/{FACTORY_ID}').status_code == 403
    assert snapshot(root / 'configuration') == before


@pytest.mark.parametrize('broken', ['missing_weights', 'bad_weights', 'bad_columns', 'missing_predictions', 'bad_predictions', 'no_configuration'])
def test_creation_does_not_depend_on_financial_configuration(journey, broken):
    _, client, root, _ = journey
    paths = configuration_paths(root)
    if broken == 'missing_weights': paths['weights'].unlink()
    elif broken == 'bad_weights': paths['weights'].write_text('{bad')
    elif broken == 'bad_columns': write(paths['weights'], {'_order': ['category', 'selling_share_of_category'], 'data': {'category': [], 'selling_share_of_category': [1]}})
    elif broken == 'missing_predictions': paths['predictions'].unlink()
    elif broken == 'bad_predictions': paths['predictions'].write_text('{bad')
    else:
        import shutil
        shutil.rmtree(root / 'configuration')
    before = snapshot(root / 'configuration')
    create_journey(client)
    assert snapshot(root / 'configuration') == before
    if broken != 'no_configuration':
        assert client.get(f'/factory_parameters/{FACTORY_ID}').status_code == 503
        assert snapshot(root / 'configuration') == before


@pytest.mark.parametrize('existing', ['both', 'bom_only', 'capacity_only'])
def test_retry_and_old_failed_attempt_preserve_existing_files(journey, existing):
    _, client, root, data = journey
    parents(client); folder = root / CATEGORY / SUB
    if existing in {'both', 'bom_only'}: write(folder / f'{PRODUCT}.json', {'important': 'owner edited BOM'})
    if existing in {'both', 'capacity_only'}: write(folder / f'{PRODUCT}_meta.json', {'capacity': 999, 'owner': True})
    before = snapshot(data)
    response = client.post('/add_product', json=product_payload())
    assert response.status_code == 409
    assert snapshot(data) == before


@pytest.mark.parametrize('failure', ['stage', 'capacity', 'bom', 'metadata', 'refresh'])
def test_product_failure_compensates_only_new_files(journey, monkeypatch, failure):
    from utils import product_creation as creation
    from modules.product import routes
    _, client, root, data = journey
    parents(client); before = snapshot(data)
    original_replace = creation.os.replace
    if failure == 'stage':
        original_stage = creation.stage_bytes
        calls = 0
        def stage(path, content):
            nonlocal calls
            calls += 1
            if calls == 2: raise OSError('private filesystem diagnostic')
            return original_stage(path, content)
        monkeypatch.setattr(creation, 'stage_bytes', stage)
    elif failure == 'refresh':
        def refresh(*args, **kwargs): raise OSError('private filesystem diagnostic')
        monkeypatch.setattr(routes, 'directory_tracer', refresh)
    else:
        def replace(src, dst):
            if Path(dst).name == ('__metadata.json' if failure == 'metadata' else f"{PRODUCT}{'_meta' if failure == 'capacity' else ''}.json"):
                raise OSError('private filesystem diagnostic')
            return original_replace(src, dst)
        monkeypatch.setattr(creation.os, 'replace', replace)
    response = client.post('/add_product', json=product_payload())
    assert response.status_code == 500
    assert 'private' not in response.get_data(as_text=True) and str(data) not in response.get_data(as_text=True)
    assert snapshot(data) == before
    assert not list(root.rglob('.product-create-*'))


@pytest.mark.parametrize('url,payload', [('/add_category', {'factory': FACTORY_ID, 'category_name': CATEGORY}),
    ('/add_subcategory', {'factory': FACTORY_ID, 'category': 'existing', 'subcategory_name': SUB})])
def test_directory_failure_rolls_back(journey, monkeypatch, url, payload):
    _, client, root, data = journey
    from modules.product import routes
    def fail(*args, **kwargs): raise OSError('diagnostic')
    monkeypatch.setattr(routes, 'directory_tracer', fail)
    before = snapshot(data)
    assert client.post(url, json=payload).status_code == 500
    assert snapshot(data) == before
    assert not (root / CATEGORY).exists() and not (root / 'existing' / SUB).exists()


@pytest.mark.parametrize('name', ['../other', 'a/b', 'a\\b', '.', '..', 'configuration', 'Configuration', 'archive', '__metadata', 'CON', 'nul.txt', 'COM1', 'a:', 'a.', 'x\x00', '_meta'])
def test_name_rejection_before_writes(journey, name):
    _, client, _, data = journey
    before = snapshot(data)
    payload = {'factory': FACTORY_ID, 'category_name': name}
    if name == '_meta':
        parents(client); before = snapshot(data)
        response = client.post('/add_product', json=product_payload(product_name='x_meta'))
    else: response = client.post('/add_category', json=payload)
    assert response.status_code == 400
    assert snapshot(data) == before


@pytest.mark.parametrize('url,payload', [('/add_product', []), ('/add_product', None), ('/add_product', {'factory': []}),
    ('/add_category', {'factory': FACTORY_ID, 'category_name': 12}), ('/add_subcategory', {'factory': FACTORY_ID, 'category': None, 'subcategory_name': SUB})])
def test_malformed_shapes_are_safe_400(journey, url, payload):
    _, client, _, data = journey; before = snapshot(data)
    response = client.post(url, data=json.dumps(payload), content_type='application/json')
    assert response.status_code == 400 and response.is_json
    assert snapshot(data) == before


@pytest.mark.parametrize('capacity', [None, '', True, 0, -1, 1.5, 'NaN', 'Infinity', [], {}])
def test_invalid_capacity_is_preflighted(journey, capacity):
    _, client, _, data = journey; parents(client); before = snapshot(data)
    assert client.post('/add_product', json=product_payload(capacity=capacity)).status_code == 400
    assert snapshot(data) == before


@pytest.mark.parametrize('resource', ['missing_template', 'bad_template', 'missing_parent'])
def test_required_resource_preflight(journey, resource):
    _, client, root, data = journey; parents(client)
    template = data / 'Overall' / 'sample_product.json'
    if resource == 'missing_template': template.unlink()
    elif resource == 'bad_template': template.write_text('{bad')
    else: (root / CATEGORY / SUB).rmdir()
    before = snapshot(data)
    assert client.post('/add_product', json=product_payload()).status_code == (400 if resource == 'missing_parent' else 500)
    assert snapshot(data) == before


@pytest.mark.parametrize('factory,status', [('secret', 403), ('inactive', 403), ('unknown', 404), ('f2', 404)])
@pytest.mark.parametrize('url', ['/add_category', '/add_subcategory', '/add_product'])
def test_factory_authorization_before_writes(journey, factory, status, url):
    _, client, _, data = journey; before = snapshot(data)
    payload = product_payload(factory=factory, category_name=CATEGORY, subcategory_name=SUB)
    assert client.post(url, json=payload).status_code == status
    assert snapshot(data) == before


def test_product_read_cannot_create(journey):
    _, client, _, data = journey; login(client, 'reader'); before = snapshot(data)
    for url in ['/add_category', '/add_subcategory', '/add_product']:
        assert client.post(url, json=product_payload(category_name=CATEGORY, subcategory_name=SUB)).status_code == 403
    assert snapshot(data) == before


def test_symlink_parent_cannot_write_other_factory(journey):
    _, client, root, data = journey
    (root / CATEGORY).symlink_to(data / 'Factories' / 'other', target_is_directory=True)
    before = snapshot(data / 'Factories' / 'other')
    assert client.post('/add_subcategory', json={'factory': FACTORY_ID, 'category': CATEGORY, 'subcategory_name': SUB}).status_code == 400
    assert snapshot(data / 'Factories' / 'other') == before


def test_concurrent_retry_produces_one_product(journey):
    app, client, root, _ = journey; parents(client)
    def submit(_):
        other = app.test_client(); login(other, 'writer')
        return other.post('/add_product', json=product_payload()).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(submit, range(2))) == [200, 409]
    assert sorted(p.name for p in (root / CATEGORY / SUB).iterdir()) == [f'{PRODUCT}.json', f'{PRODUCT}_meta.json']


def test_path_helpers_use_native_joins_and_do_not_overwrite(journey):
    from utils import updaters
    _, _, root, _ = journey
    updaters.category_adder('f2', CATEGORY); updaters.subcategory_adder('f2', CATEGORY, SUB)
    updaters.product_adder(PRODUCT, 'f2', CATEGORY, SUB)
    updaters.capacity_writer(PRODUCT, 'f2', CATEGORY, SUB, 42)
    for sep in ['/', '\\']:
        assert updaters.capacity_reader(PRODUCT, sep.join(['f2', CATEGORY, SUB])) == 42
    before = snapshot(root)
    with pytest.raises(FileExistsError): updaters.product_adder(PRODUCT, 'f2', CATEGORY, SUB)
    with pytest.raises(FileExistsError): updaters.capacity_writer(PRODUCT, 'f2', CATEGORY, SUB, 999)
    assert snapshot(root) == before


def test_empty_new_category_can_be_configured_before_products_exist(journey):
    _, client, root, _ = journey
    parents(client); before = snapshot(root / 'configuration')
    page = client.get(f'/factory_parameters/{FACTORY_ID}')
    weights = javascript_json(page.get_data(as_text=True), 'weights')
    assert weights['data']['category'][-1] == CATEGORY
    assert weights['data']['selling_share_of_category'][-1] is None
    assert snapshot(root / 'configuration') == before


def test_canonical_weights_reader_ignores_legacy_and_does_not_create_defaults(journey, monkeypatch):
    from utils import load_data
    _, _, root, data = journey
    monkeypatch.setattr(load_data, 'parent_path', data)
    write(root / 'category_weights.json', {'data': {'category': ['legacy'], 'selling_share_of_category': [999]}})
    before = snapshot(root)
    assert load_data.load_category_weights_of_costs('f2')['data']['selling_share_of_category'] == [50]
    assert snapshot(root) == before
    configuration_paths(root)['weights'].unlink(); before = snapshot(root)
    with pytest.raises(FileNotFoundError): load_data.load_category_weights_of_costs('f2')
    assert snapshot(root) == before


def test_creation_preserves_other_factory_and_filter_authorization(journey):
    _, client, _, data = journey
    other = data / 'Factories' / 'other'
    write(other / 'hidden' / 'sub' / 'Hidden.json', {'owner': 'secret'})
    before = snapshot(other)
    create_journey(client)
    assert snapshot(other) == before
    assert 'Hidden' not in client.get('/product/production_selection').get_data(as_text=True)
    assert client.get('/api/dashboard/filter-options', query_string={'factory': 'secret'}).status_code == 403


def test_case_alias_retry_conflicts_on_both_platforms(journey):
    _, client, _, data = journey
    assert client.post('/add_category', json={'factory': FACTORY_ID, 'category_name': 'Battery'}).status_code == 200
    before = snapshot(data)
    assert client.post('/add_category', json={'factory': FACTORY_ID, 'category_name': 'battery'}).status_code == 409
    assert snapshot(data) == before
