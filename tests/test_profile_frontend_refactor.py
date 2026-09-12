import json
import re
from pathlib import Path

import app as app_module
from utils.module_registry import GRANTABLE_MODULES
from utils.profile_store import ProfileDataStore


TEMPLATE = Path("templates/profile/profile.html")
ACCESS_SCRIPT = Path("static/js/profile-access-manager.js")
PAGE_SCRIPT = Path("static/js/profile-page.js")


def _admin_client(tmp_path, *, payload="مدیر آزمون"):
    store = ProfileDataStore(tmp_path / "app_data.json")
    store.initialize({})
    store.create_user({
        "id": "admin", "username": "admin", "email": "admin@example.com",
        "full_name": payload, "system_role": "IT_ADMIN", "job_title": payload,
        "access_grants": [], "is_active": True, "must_change_password": False,
        "password_hash": "unused", "password_scheme": "werkzeug", "revision": 1,
    })
    app_module.app.config.update(TESTING=True, APP_DATA_FILE=str(store.path), SECRET_KEY="test-secret")
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = "admin"
    return client


def test_profile_has_no_inline_behavior_style_or_raw_grant_editor():
    template = TEMPLATE.read_text(encoding="utf-8")
    assert "onclick=" not in template
    assert "<style>" not in template
    scripts = re.findall(r"<script(?![^>]*type=\"application/json\")[^>]*>(.*?)</script>", template, re.S)
    assert all(not body.strip() for body in scripts)
    assert 'name="access_grants"' not in template
    assert 'type="checkbox" name="permissions"' not in template
    assert "profile-page.js" in template
    assert "profile.css" in template


def test_access_manager_uses_server_metadata_safe_dom_and_one_selector_per_row():
    script = ACCESS_SCRIPT.read_text(encoding="utf-8")
    assert "config.global_modules.forEach" in script
    assert "config.factory_modules.forEach" in script
    assert "document.createElement('select')" not in script  # centralized element helper
    assert "element('select', 'form-select access-level')" in script
    assert "innerHTML" not in script
    assert "permissionMap = Object.freeze" in script
    assert set(GRANTABLE_MODULES) == {
        "cost_calculation", "dashboard", "desk", "factory_parameters",
        "general_parameters", "product", "profile",
    }
    assert "auth" not in json.dumps([item for item in GRANTABLE_MODULES])


def test_page_requests_are_locked_content_type_aware_and_clear_passwords():
    script = PAGE_SCRIPT.read_text(encoding="utf-8")
    assert "withSubmissionLock" in script
    assert "button.disabled = true" in script
    assert "contentType.includes('application/json')" in script
    assert "response.status === 401 || response.status === 403 || response.redirected" in script
    assert "clearPasswords" in script
    assert "innerHTML" not in script
    assert "console." not in script


def test_xss_payload_is_escaped_in_html_and_not_copied_to_data_attribute(tmp_path):
    payload = '\"><img src=x onerror=alert(1)>'
    response = _admin_client(tmp_path, payload=payload).get("/profile/profile")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert payload not in body
    assert "&lt;img src=x onerror=alert(1)&gt;" in body
    assert "data-user='" not in body
    assert 'data-user-id="admin"' in body
