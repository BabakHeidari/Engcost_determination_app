"""Actual application import/startup against prepared, disposable stores."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_actual_startup_registration_and_request_write_boundary(tmp_path):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    for name in ("modules", "utils", "templates", "static"):
        shutil.copytree(ROOT / name, checkout / name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(ROOT / "app.py", checkout / "app.py")
    # Configuration and fixture data exist before app.py is imported. Startup
    # migration is intentionally exercised only inside this disposable checkout.
    factory = checkout / "Data/Factories/OpTest"
    factory.mkdir(parents=True)
    (factory / "Factory_Data.json").write_text(json.dumps({"data": {
        "Subfield": ["AdministrativeandResearch", "Payroll", "Overhead", "FinancialCosts",
                     "Depriciation", "NonOperationalCostsandIncomes"],
        "Cost": [0] * 6, "PercentageOfAll": [0] * 6}}), encoding="utf-8")
    env = os.environ.copy()
    env.update(APP_DATA_FILE=str(tmp_path / "profiles.json"),
               APP_SECRET_KEY="isolated-startup-fixture-key", PYTHONPATH=str(checkout),
               PYTHONDONTWRITEBYTECODE="1")
    code = r'''
import hashlib, json, os
from pathlib import Path
from utils.profile_store import ProfileDataStore
store = ProfileDataStore(Path(os.environ["APP_DATA_FILE"]))
store.initialize({})
store.create_factory({"id":"factory-test","code":"T","name":"آزمایشی",
                      "is_active":True,"operational_key":"OpTest"})
store.create_user({"id":"viewer","username":"viewer","email":"viewer@example.test",
 "full_name":"آزمایش","system_role":"USER","job_title":"","is_active":True,
 "must_change_password":False,"password_hash":"unused","password_scheme":"werkzeug",
 "revision":1,"access_grants":[{"scope_type":"FACTORY","factory_id":"factory-test",
 "module":"dashboard","permissions":["READ"]}]})
assert not Path("Data/Factories/OpTest/configuration/manifest.json").exists()
import app
application = app.app
assert application.secret_key == os.environ["APP_SECRET_KEY"]
assert application.config["SESSION_COOKIE_HTTPONLY"] is True
assert application.config["SESSION_COOKIE_SAMESITE"] == "Lax"
manifest = Path("Data/Factories/OpTest/configuration/manifest.json")
assert json.loads(manifest.read_text())["migration_status"] == "COMPLETED"
expected = {"/dashboard","/api/dashboard/filter-options","/api/cost_analysis",
 "/api/dashboard/cost-analysis/visuals","/api/dashboard/sensitivity/parameters",
 "/api/dashboard/sensitivity/scenario","/api/dashboard/sensitivity/visual-analysis"}
assert expected <= {rule.rule for rule in application.url_map.iter_rules()}
def inventory():
 result = {}
 for root in [Path("Data"), Path(os.environ["APP_DATA_FILE"]).parent]:
  for path in [root, *root.rglob("*")]:
   # Profile parent also contains this checkout; limit that second traversal.
   if root.name != "Data" and path.name not in {"profiles.json","profiles.json.lock"}:
    continue
   result[str(path)] = [path.stat().st_mtime_ns,
     hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None]
 return result
web = application.test_client()
landing = web.get("/")
# The authentication blueprint owns the root alias and serves its login form.
assert landing.status_code == 200
assert b'name="username"' in landing.data and b'name="password"' in landing.data
with web.session_transaction() as session: session["user_id"] = "viewer"
before = inventory()
assert web.get("/dashboard").status_code == 200
assert web.get("/api/dashboard/filter-options?factory=missing").status_code == 404
assert web.get("/api/dashboard/sensitivity/parameters?factory=factory-test").status_code == 400
assert web.post("/api/dashboard/sensitivity/visual-analysis",data="{",content_type="application/json").status_code == 400
assert application.test_client().get("/api/cost_analysis").status_code == 302
assert inventory() == before
app.initialize_factory_configuration_v2(application)
assert inventory() == before
print(json.dumps({"startup":"COMPLETED","registered":len(expected),"request_writes":0,
                  "second_startup":"UNCHANGED"}))
'''
    result = subprocess.run([sys.executable, "-c", code], cwd=checkout, env=env,
                            text=True, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    evidence = json.loads(result.stdout)
    assert evidence == {"startup": "COMPLETED", "registered": 7,
                        "request_writes": 0, "second_startup": "UNCHANGED"}
