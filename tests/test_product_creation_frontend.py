"""Actual Flask/Jinja editor: blank catalog rows and explicitly authorized saves."""
import os
from pathlib import Path
import threading

import pytest
from werkzeug.serving import make_server

from test_dashboard_release_frontend import ASSET_MAP, ROOT, release_browser
from test_product_creation import CATEGORY, FACTORY_ID, PRODUCT, create_journey, journey, login, snapshot
from utils.factory_configuration import configuration_paths


@pytest.mark.parametrize('width', [1440, 390])
def test_blank_financial_rows_and_authorized_editor_save(journey, release_browser, width):
    app, client, root, _ = journey
    create_journey(client); before = snapshot(root / 'configuration')
    server = make_server('127.0.0.1', 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    context = release_browser.new_context(viewport={'width': width, 'height': 1000}, timezone_id='Asia/Tehran')
    def authenticate(uid):
        login(client, uid)
        context.clear_cookies()
        context.add_cookies([{'name': 'session', 'value': client.get_cookie('session').value, 'url': base}])
    page = context.new_page(); errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('dialog', lambda dialog: dialog.accept())
    def presentation(route):
        relative, mime = ASSET_MAP[route.request.url]
        route.fulfill(body=(ROOT / 'work' / 'vendor' / relative).read_bytes(), content_type=mime)
    page.route('https://**/*', presentation)
    try:
        authenticate('writer')
        page.goto(base + f'/factory_parameters/{FACTORY_ID}', wait_until='networkidle')
        weights = page.locator('#weights tbody tr').filter(has_text=CATEGORY)
        predictions = page.locator('#predictions tbody tr').filter(has_text=PRODUCT)
        assert weights.locator('td').nth(1).inner_text() == ''
        assert predictions.locator('td').nth(1).inner_text() == ''
        assert weights.locator('td').first.get_attribute('contenteditable') is None
        assert snapshot(root / 'configuration') == before
        weights.locator('[contenteditable]').fill('25')
        with page.expect_response(lambda response: response.request.method == 'PUT') as pending:
            page.locator('#saveWeights').click()
        assert pending.value.status == 403
        assert snapshot(root / 'configuration') == before
        authenticate('finance')
        page.reload(wait_until='networkidle')
        weights = page.locator('#weights tbody tr').filter(has_text=CATEGORY)
        predictions = page.locator('#predictions tbody tr').filter(has_text=PRODUCT)
        assert weights.locator('[contenteditable]').inner_text() == ''
        assert predictions.locator('[contenteditable]').inner_text() == ''
        evidence = os.environ.get('PRODUCT_CREATION_EVIDENCE_DIR')
        if evidence:
            directory = Path(evidence); directory.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(directory / f'financial-editor-{width}.png'), full_page=True)
        weights.locator('[contenteditable]').fill('25')
        predictions.locator('[contenteditable]').fill('10')
        for button in ['#saveWeights', '#savePredictions']:
            with page.expect_response(lambda response: response.request.method == 'PUT') as pending:
                page.locator(button).click()
            assert pending.value.status == 200
        page.reload(wait_until='networkidle')
        assert page.locator('#weights tbody tr').filter(has_text=CATEGORY).locator('[contenteditable]').inner_text() == '25'
        assert page.locator('#predictions tbody tr').filter(has_text=PRODUCT).locator('[contenteditable]').inner_text() == '10'
        paths = configuration_paths(root)
        assert '42' not in paths['predictions'].read_text()  # Capacity was never a prediction.
        assert not errors
    finally:
        context.close(); server.shutdown(); thread.join(timeout=3); server.server_close()
