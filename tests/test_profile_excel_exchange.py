from io import BytesIO
from xml.etree import ElementTree
from zipfile import ZipFile

import app as app_module
from utils.module_registry import GRANTABLE_MODULES
from utils.profile_excel import SHEET_NAMES, profile_exchange_bytes
from utils.profile_store import ProfileDataStore


def _user(user_id, role="USER", grants=None, *, active=True):
    return {
        "id": user_id, "username": user_id, "email": f"{user_id}@example.com",
        "full_name": user_id, "system_role": role, "job_title": "کارشناس",
        "access_grants": grants or [], "is_active": active,
        "must_change_password": False, "password_hash": "sensitive-hash-value",
        "password_scheme": "werkzeug", "revision": 1,
    }


def _seeded_store(tmp_path):
    store = ProfileDataStore(tmp_path / "app_data.json")
    store.initialize({})
    store.create_factory({"id": "dynamic-1", "code": "D1", "name": "کارخانه پویا", "location": "قم", "is_active": True})
    store.create_user(_user("admin", "IT_ADMIN"))
    store.create_user(_user("finance", "FINANCE_ECONOMIC_ADMIN"))
    store.create_user(_user("ordinary", grants=[{
        "scope_type": "FACTORY", "factory_id": "dynamic-1", "module": "product",
        "permissions": ["READ", "WRITE"],
    }]))
    return store


NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _workbook(payload):
    archive = ZipFile(BytesIO(payload))
    workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    names = [node.attrib["name"] for node in workbook.findall(".//x:sheet", NS)]
    sheets = {}
    for index, name in enumerate(names, start=1):
        root = ElementTree.fromstring(archive.read(f"xl/worksheets/sheet{index}.xml"))
        values = []
        for row in root.findall(".//x:sheetData/x:row", NS):
            parsed = []
            for cell in row.findall("x:c", NS):
                value = cell.findtext("x:is/x:t", default=None, namespaces=NS)
                if value is None:
                    value = cell.findtext("x:v", default=None, namespaces=NS)
                    if cell.attrib.get("t") == "b" and value is not None:
                        value = value == "1"
                parsed.append(value)
            values.append(parsed)
        sheets[name] = [dict(zip(values[0], row)) for row in values[1:]]
    return names, sheets


def test_export_structure_dynamic_factories_registry_and_desk_policy(tmp_path):
    store = _seeded_store(tmp_path)
    names, workbook = _workbook(profile_exchange_bytes(
        store, generated_at="2026-09-12T12:00:00Z"
    ))
    assert tuple(names) == SHEET_NAMES
    assert any(row["FactoryId"] == "dynamic-1" for row in workbook["Factories"])

    metadata = {row["Key"]: row["Value"] for row in workbook["Metadata"]}
    exported_modules = {
        value for key, value in metadata.items() if key.startswith("GrantableModule.")
    }
    assert exported_modules == set(GRANTABLE_MODULES)
    assert "auth" not in exported_modules
    assert metadata["ImportEnabled"] is False

    grants = workbook["AccessGrants"]
    assert {row["UserId"] for row in grants}.isdisjoint({"admin", "finance"})
    desk = next(row for row in grants if row["UserId"] == "ordinary" and row["ModuleId"] == "desk")
    assert desk["ExplicitAccessLevel"] == "NONE"
    assert desk["EffectiveAccessLevel"] == "READ"
    assert desk["PolicySource"] == "MANDATORY_DESK_MINIMUM"
    product = next(row for row in grants if row["ModuleId"] == "product")
    assert product["ExplicitAccessLevel"] == product["EffectiveAccessLevel"] == "WRITE"
    assert all("Permissions" not in row for row in grants)


def test_export_excludes_credentials_and_does_not_mutate_json(tmp_path):
    store = _seeded_store(tmp_path)
    before = store.path.read_bytes()
    payload = profile_exchange_bytes(store, generated_at="2026-09-12T12:00:00Z")
    after = store.path.read_bytes()
    assert after == before

    names, workbook = _workbook(payload)
    cell_text = "\n".join(
        str(value) for rows in workbook.values() for row in rows
        for value in (*row.keys(), *row.values()) if value is not None
    ).casefold()
    for forbidden in ("password_hash", "sensitive-hash-value", "reset_token", "session_data"):
        assert forbidden not in cell_text
    assert "passwordstatus" in cell_text
    assert "rolepermissions" not in names
    assert "userpermissionoverrides" not in names


def test_export_endpoint_is_admin_only_and_returns_xlsx(tmp_path):
    store = _seeded_store(tmp_path)
    app_module.app.config.update(TESTING=True, APP_DATA_FILE=str(store.path), SECRET_KEY="test")

    ordinary = app_module.app.test_client()
    with ordinary.session_transaction() as session:
        session["user_id"] = "ordinary"
    assert ordinary.get("/api/profile/export.xlsx").status_code == 403

    admin = app_module.app.test_client()
    with admin.session_transaction() as session:
        session["user_id"] = "admin"
    response = admin.get("/api/profile/export.xlsx")
    assert response.status_code == 200
    assert response.mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert response.headers["Content-Disposition"].startswith("attachment;")
    assert _workbook(response.data)[0] == list(SHEET_NAMES)
