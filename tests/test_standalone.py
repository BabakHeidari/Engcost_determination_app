"""Storage/bootstrap/security contracts, separate from native package smoke."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import threading

import pytest

from standalone.controller import Controller
from standalone.workspace import first_admin, prepare, validate_existing
from utils.profile_store import ProfileDataConflictError, ProfileDataStore
from utils.runtime_paths import RuntimePaths


def admin():
    return {'username': 'owner', 'full_name': 'مدیر آزمایشی', 'email': 'owner@example.test',
            'password': 'Fixture-Password-123', 'confirmation': 'Fixture-Password-123'}


def test_standalone_paths_are_coherent_and_development_is_unchanged(tmp_path):
    paths = RuntimePaths.from_environment({'ENGCOST_STANDALONE': '1', 'ENGCOST_WORKSPACE': str(tmp_path)})
    assert paths.data == tmp_path / 'Data'
    assert paths.instance == tmp_path / 'instance'
    assert paths.flask_config()['APP_DATA_FILE'] == str(tmp_path / 'instance/app_data.json')
    assert RuntimePaths.from_environment({}).flask_config() == {}
    with pytest.raises(ValueError):
        RuntimePaths.from_environment({'ENGCOST_STANDALONE': '1', 'ENGCOST_WORKSPACE': 'relative'})


def test_fresh_workspace_has_empty_templates_unique_persistent_secret_and_no_account(tmp_path):
    root, first = prepare(tmp_path / 'نام با فاصله', fresh=True)
    assert ProfileDataStore(root / 'instance/app_data.json').load_data()['users'] == []
    assert prepare(root, fresh=True)[1] == first
    assert prepare(tmp_path / 'second', fresh=True)[1]['secret'] != first['secret']
    for path in (root / 'Data/Overall').glob('*.json'):
        document = json.loads(path.read_text())
        assert all(not values for values in document.get('data', {}).values())


def test_atomic_first_admin_has_one_winner_and_is_disabled_after_users_exist(tmp_path):
    root, _ = prepare(tmp_path / 'workspace', fresh=True)
    def create(_):
        try:
            first_admin(root, admin())
            return 'created'
        except ProfileDataConflictError:
            return 'conflict'
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sorted(pool.map(create, range(4))) == ['conflict', 'conflict', 'conflict', 'created']
    raw = (root / 'instance/app_data.json').read_text()
    assert admin()['password'] not in raw
    store = ProfileDataStore(root / 'instance/app_data.json')
    assert len(store.list_users()) == 1
    before = store.path.read_bytes()
    with pytest.raises(ProfileDataConflictError):
        first_admin(root, admin())
    assert store.path.read_bytes() == before


@pytest.mark.parametrize('kind', ['nonempty', 'corrupt-profile', 'corrupt-settings', 'edited-template'])
def test_incomplete_or_corrupt_workspace_never_resets_existing_bytes(tmp_path, kind):
    root = tmp_path / 'workspace'
    if kind == 'nonempty':
        root.mkdir(); target = root / 'do-not-overwrite'; target.write_text('private')
    else:
        prepare(root, fresh=True)
        target = root / {'corrupt-profile': 'instance/app_data.json',
                         'corrupt-settings': 'instance/standalone.json',
                         'edited-template': 'Data/Overall/sample_product.json'}[kind]
        target.write_text('{corrupt')
    before = target.read_bytes()
    with pytest.raises(Exception):
        prepare(root, fresh=True)
    assert target.read_bytes() == before


def test_existing_preflight_is_readonly_and_rejects_missing_profile_and_links(tmp_path):
    root, _ = prepare(tmp_path / 'workspace', fresh=True)
    first_admin(root, admin())
    before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
    assert validate_existing(root)['users'][0]['username'] == 'owner'
    assert {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()} == before
    (root / 'instance/app_data.json').unlink()
    with pytest.raises(Exception):
        validate_existing(root)


def test_private_setup_control_requires_capability_host_origin_and_csrf(tmp_path):
    controller = Controller(tmp_path, tmp_path / 'workspace')
    controller.host = '127.0.0.1:5555'
    web = controller.local.test_client()
    origin = 'http://' + controller.host
    def request(method, path, **kwargs):
        return web.open(path, method=method, base_url=origin, environ_overrides={'REMOTE_ADDR': '127.0.0.1'}, **kwargs)
    assert request('GET', '/_local/panel').status_code == 403
    assert request('GET', '/_local/health').status_code == 403
    assert request('POST', '/_local/authorize', json={'capability': controller.token}, headers={'Origin':'https://evil.test'}).status_code == 403
    assert request('POST', '/_local/authorize', json={'capability': controller.token}, headers={'Origin':origin}).status_code == 200
    assert request('GET', '/_local/panel').status_code == 200
    assert request('POST', '/_local/stop', data={'csrf':'bad'}, headers={'Origin':origin}).status_code == 403
    assert not controller.stop.is_set()
    assert request('POST', '/_local/admin', data={'csrf':controller.csrf}, headers={'Origin':origin}).status_code == 409
    assert request('POST', '/_local/stop', data={'csrf':controller.csrf}, headers={'Origin':origin}).status_code == 200
    assert controller.stop.is_set()


def test_graceful_drain_waits_for_in_progress_write_and_refuses_new_requests(tmp_path):
    controller = Controller(tmp_path, tmp_path / 'workspace')
    controller.host = '127.0.0.1:5555'
    entered = threading.Event(); release = threading.Event(); completed = threading.Event()
    def business(environ, respond):
        entered.set(); release.wait(5); completed.set()
        respond('200 OK', []); return [b'saved']
    controller.business = business
    env = {'PATH_INFO':'/edit', 'REMOTE_ADDR':'127.0.0.1', 'HTTP_HOST':controller.host}
    writer = threading.Thread(target=lambda: list(controller(env, lambda *_: None)))
    writer.start(); assert entered.wait(2)
    drain = threading.Thread(target=controller.drain); drain.start()
    status = []
    assert list(controller(env, lambda value, _:status.append(value))) != [b'saved']
    assert status == ['503 Service Unavailable']
    assert not completed.is_set() and drain.is_alive()
    release.set(); writer.join(2); drain.join(2)
    assert completed.is_set() and not drain.is_alive()
