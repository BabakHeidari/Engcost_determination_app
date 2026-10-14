# Engineering cost determination application

Flask application for factory configuration, product BOMs, production costing,
and a Persian RTL Dashboard. The Dashboard analyzes current operational inputs
and non-persistent hypothetical scenarios. It does not capture cost history.

For offline desktop installers and one-click local launch, see the
[Persian installation/setup/backup guide](docs/offline-installers.md) and
[platform validation status](docs/pr11-validation.md). Native installer CI keeps
unsigned packages, checksums and validation reports as review artifacts.

Use Python 3.12 and Node.js 20 or newer (validated with 24.19.0). From this
repository root:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements-test.txt
.venv/bin/python scripts/setup_dashboard_browser.py
PLAYWRIGHT_BROWSERS_PATH="$PWD/work/browser-cache" .venv/bin/python scripts/validate_dashboard_release.py
.venv/bin/python scripts/benchmark_dashboard.py --help
```

The validation command copies the source into a disposable runtime and prepares
an isolated empty profile store before importing the application. Do not run
application initialization or migrations against operational data during tests.
Browser compatibility checks are reported separately from the shipped-client
suite. All JUnit files and logs are kept in `work/pr10-evidence/`.

For local development, first install the canonical profile registry, completed
Factory Configuration V2, and explicit costing period bindings. See the
[release operations guide](docs/dashboard-release-operations.md) before launch:

```bash
APP_DATA_FILE=/absolute/path/to/prepared/profiles.json APP_SECRET_KEY=local-development-only .venv/bin/python app.py
```

Production requires a stable secret, HTTPS, secure cookies, debug disabled,
protected runtime storage and an appropriate WSGI server/reverse proxy. Importing
`app.py` intentionally initializes registered factory configurations; a Dashboard
analytical request does not perform that initialization.

- [Release readiness and evidence](docs/pr10-dashboard-release-readiness.md)
- [Owner UAT checklist](docs/dashboard-release-uat.md)
- [Dashboard product contract](docs/dashboard-product-contract.md)
- [Current visual analytics API](docs/pr09a-dashboard-visual-analytics.md)
- [Authorization matrix](docs/authorization-matrix.md)
- [Costing semantics](docs/costing-semantics.md)
- [Persian user guide](docs/dashboard-visual-analytics-user-guide.md)

Owner UAT and production release approval remain PENDING until explicitly given.
