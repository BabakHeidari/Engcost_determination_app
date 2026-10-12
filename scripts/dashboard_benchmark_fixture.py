"""Synthetic, installed V2 inputs for the Dashboard benchmark.

Nothing imports the operational application or migrates operational inputs.
The fixture is deliberately all-valid: its many-product report calculates every
configuration, while the selected sensitivity configuration has 500 BOM rows.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from types import SimpleNamespace


FACTORY = "benchmark-factory"
OPERATIONAL = "benchmark-operational"
USER = "benchmark-user"


def write(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")


def install_fixture(root: Path, configurations=200, selected_bom_rows=500, other_bom_rows=3):
    from utils.costing_engine import FACTORY_POOL_IDS
    from utils.profile_store import ProfileDataStore

    root = root.resolve()
    data = root / "Data"
    factory = data / "Factories" / OPERATIONAL
    profiles = root / "profiles.json"
    bindings = root / "bindings.json"
    store = ProfileDataStore(profiles)
    store.initialize({})
    store.create_factory({"id": FACTORY, "code": FACTORY, "name": "کارخانه آزمایشی",
                          "is_active": True, "operational_key": OPERATIONAL})
    store.create_user({
        "id": USER, "username": USER, "email": "benchmark@example.test",
        "full_name": "کاربر آزمایشی", "system_role": "USER", "job_title": "کاربر",
        "is_active": True, "must_change_password": False,
        "password_hash": "unused-fixture-value", "password_scheme": "werkzeug", "revision": 1,
        "access_grants": [
            {"scope_type": "FACTORY", "factory_id": FACTORY,
             "module": module, "permissions": ["READ"]}
            for module in ("dashboard", "factory_parameters")
        ] + [{"scope_type": "GLOBAL", "factory_id": None,
              "module": "general_parameters", "permissions": ["READ"]}],
    })
    materials = [f"material-{index}" for index in range(4)]
    write(data / "Factories" / "__metadata.json", {
        "product_hierarchy": {OPERATIONAL: {"category": ["sub"]}},
    })
    write(data / "Overall" / "material_costs.json", {"data": {
        "material": materials, "unit": ["kg"] * 4,
        "currency": ["IRR - Iranian Rial"] * 4,
        "cost_per_unit_in_currency": [100, 150, 200, 250],
    }})
    names = [f"P{index:03d}" for index in range(configurations)]
    for index, name in enumerate(names):
        size = selected_bom_rows if index == 0 else other_bom_rows
        write(factory / "category" / "sub" / f"{name}.json", {"data": {
            "row_id": [f"row-{row + 1}" for row in range(size)],
            "materials": [materials[row % len(materials)] for row in range(size)],
            "usage": ["1.25"] * size, "lost_percentage": ["10"] * size,
            "recycability_percentage": ["20"] * size,
            "cost_of_material_in_rial": [777777] * size,
        }})
    configuration = factory / "configuration"
    write(configuration / "manifest.json", {
        "schema_version": 2, "migration_status": "COMPLETED",
        "factory_id": FACTORY, "operational_key": OPERATIONAL,
    })
    write(configuration / "category_weights.json", {"data": {
        "category": ["category"], "selling_share_of_category": ["50"],
    }})
    write(configuration / "production_prediction.json", {"data": {
        "Product Name": names, "Predicted Production": [10] * configurations,
    }})
    for index, pool in enumerate(FACTORY_POOL_IDS):
        write(configuration / "cost_pools" / f"{pool}.json", {"data": {
            "subject": ["fixture-pool"], "cost": [1000 * (index + 1)],
        }})
    write(bindings, {"bindings": [{
        "factory_id": FACTORY, "period_id": "P", "start": "2026-10-01", "end": "2026-12-31",
        "active": True, "approved": True, "status": "ACTIVE",
        "sources": ["materials", "bom", "weights", "predictions",
                    *(f"pool:{pool}" for pool in FACTORY_POOL_IDS)],
    }]})
    raw = json.dumps([OPERATIONAL, "category", "sub", names[0]], separators=(",", ":")).encode()
    selection = {"factory": FACTORY, "category": "category", "subcategory": "sub",
                 "product": base64.urlsafe_b64encode(raw).decode().rstrip("="), "period": "P"}
    return SimpleNamespace(root=root, data=data, factory=factory, profiles=profiles,
                           bindings=bindings, selection=selection, store=store,
                           dimensions={"configuration_population": configurations,
                                       "selected_BOM_rows": selected_bom_rows,
                                       "other_configuration_BOM_rows": other_bom_rows,
                                       "all_selected_BOM_rows": selected_bom_rows + (configurations - 1) * other_bom_rows,
                                       "material_count": len(materials), "category_count": 1,
                                       "subcategory_count": 1, "pool_count": len(FACTORY_POOL_IDS)})


def create_app(fixture):
    from flask import Flask
    from modules.dashboard.routes import dashboard_bp

    app = Flask(__name__, instance_path=str(fixture.root / "instance"))
    app.config.update(TESTING=True, SECRET_KEY="dashboard-benchmark-isolated",
                      APP_DATA_FILE=str(fixture.profiles), COSTING_DATA_ROOT=str(fixture.data),
                      COSTING_PERIOD_BINDINGS_FILE=str(fixture.bindings))
    app.add_url_rule("/login", endpoint="auth.login", view_func=lambda: "login")
    app.register_blueprint(dashboard_bp)
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = USER
    return app, client
