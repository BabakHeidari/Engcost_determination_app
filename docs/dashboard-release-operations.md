# Dashboard runtime, validation, upgrade and rollback

PR-10 preserves G1–G4, `cost-v1-owner-approved-2026-09-27`, Decimal precision,
Factory Configuration V2, canonical identities, full-category allocation and
period rules. It adds no migration, storage format, history or scenario cache.

## Reproducible dependencies and checks

Python 3.12 is the validated runtime. `requirements.txt` pins runtime dependencies
including transitives; `requirements-test.txt` adds the tested pytest version.
`requirements-browser.txt` and `scripts/setup_dashboard_browser.py` install pinned
Playwright, its Chromium and integrity-checked presentation assets into `work/`.
Node is needed for exact-number/model tests (validated Node 24.19.0).
ECharts 5.6.0 is vendored in `static/vendor/echarts/`, with license, notice,
integrity metadata and template SRI. Tables and exports survive chart failure.

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements-test.txt
.venv/bin/python scripts/setup_dashboard_browser.py
PLAYWRIGHT_BROWSERS_PATH="$PWD/work/browser-cache" .venv/bin/python scripts/validate_dashboard_release.py --suite all
.venv/bin/python scripts/benchmark_dashboard.py --help
.venv/bin/python -m compileall -q app.py modules utils scripts
for asset in static/js/dashboard-*.js; do node --check "$asset"; done
git diff --check
```

To use an already installed browser, explicitly set `DASHBOARD_CHROMIUM_PATH` to
its absolute executable; record its version with the results. No hidden workspace
cache or PYTHONPATH dependency is required. Browser checks use the actual Jinja
page, unchanged local business JavaScript, real Flask routes and pinned ECharts.
Serving the same Bootstrap/icon asset bytes locally is presentation-only.

The validation host permits the pinned presentation package hosts but rejects
the managed Chromium download host `cdn.playwright.dev` with HTTP 403. Its
explicit installed Chromium 154.0.8037.57 was used for the recorded checks:

```bash
.venv/bin/python scripts/setup_dashboard_browser.py --chromium-path /usr/bin/chromium
DASHBOARD_CHROMIUM_PATH=/usr/bin/chromium .venv/bin/python scripts/validate_dashboard_release.py --suite all
```

The managed-browser download remains available on a host whose network policy
allows that destination. The alternative above validates the selected executable
and records its version; it does not bypass a network policy or rely on a cache.
Required browser skips make the release runner fail.

The validation runner creates a disposable checkout below `work/pr10-runs/` and
initializes an empty isolated profile store **before** pytest collection/import.
It retains command logs, JUnit and JSON summaries in `work/pr10-evidence/` and
checks the original `Data/` and `instance/` file/directory inventories, hashes and
mtimes. Successful, invalid and forbidden analytical requests also have isolated
fixture inventory checks. Source-save routes and operational migrations must
never be invoked as validation preparation against the operational checkout.

## Installed prerequisites and writable paths

- `APP_DATA_FILE`: absolute protected canonical profile JSON; default is
  `instance/app_data.json`. Existing permissions, factory IDs and operational
  mappings must be installed. Password material is never committed as evidence.
- `APP_SECRET_KEY`: strong stable deployment secret. An unset key produces the
  existing warning and ephemeral development sessions; it is not a production
  setup. `APP_COOKIE_SECURE=1` requires HTTPS. `FLASK_DEBUG` stays unset/false.
  Existing HttpOnly/SameSite and session/POST middleware remain enabled.
- `Data/Overall`: accepted current material and FX inputs; each authorized
  `Data/Factories/<operational_key>` must have current BOMs and completed V2
  manifest, prediction, weights and six pool files. Missing/ambiguous inputs
  produce typed unavailable results rather than invented zeros.
- `instance/costing_period_bindings.json`: installed explicit factory/period
  dates and source binding. Dashboard does not install a binding. An existing
  `SYSTEM_INITIALIZATION` binding retains its distinct provenance.
- Profile directory: existing lock file, backups, temporary atomic replacement
  and audit storage need permissions for existing administrative/login actions.
  `APP_DATA_BACKUP_LIMIT`, `APP_DATA_LOCK_TIMEOUT` and `APP_AUDIT_EVENT_LIMIT`
  retain their existing behavior. Complete deliberate preparation before taking
  a read-only baseline, including the profile lock file.
- Factory configuration directories and lock need startup/authorized source
  editing permissions. **Application import intentionally initializes V2**;
  Dashboard analytical requests use the read-only loader. These are separate
  boundaries. Existing Cost Calculation first-period initialization is retained.

`COSTING_DATA_ROOT` and `COSTING_PERIOD_BINDINGS_FILE` are Flask configuration
keys used by isolated harnesses/custom application configuration, not automatic
shell environment settings. Default deployment paths remain unchanged.

Run [read-only period/source diagnostics](pr05-5-cost-calculation-runbook.md)
before considering binding repairs. Do not infer owner period dates from mtimes,
fingerprints or the owner-assigned legacy baseline. Existing setup/migration
commands are operational procedures requiring their own review and backups;
PR-10 validation does not run them against operational stores.

Local launch after prerequisites are prepared:

```bash
APP_DATA_FILE=/absolute/path/to/prepared/profiles.json APP_SECRET_KEY=local-development-only .venv/bin/python app.py
```

Production serves the existing `app:app` WSGI object through the deployment's
WSGI server and HTTPS reverse proxy. Preserve Origin/Host protections and any
installed POST middleware. The built-in Flask development server is a local
launch command. This PR does not deploy or select a new hosting architecture.

## Upgrade and rollback without replacing operational data

Record the current code SHA, installed dependency versions, profile/binding
locations and file permissions. Take reviewed backups of operational data and
configuration using existing operator procedures. Install this candidate code
and pinned dependencies in a separate code/runtime directory; retain protected
profile/binding and operational data mounts. Perform the fixture checks first,
then owner UAT against the representative authorized factory. Do not copy fixture
stores or screenshots into production data.

For rollback, stop/reload workers as appropriate and select the previous code
SHA and its matching dependency environment. Preserve the existing operational
data, V2 configuration, profile and bindings; do not roll those stores back
merely to roll back code. PR-10 has no schema migration to reverse. Restart may
perform the pre-existing idempotent V2 initialization; assess incomplete existing
configuration separately. Run read-only diagnostics and the authorized default
journey after a controlled change. No release/deployment approval is inferred
from automated checks; owner UAT is separately PENDING.
