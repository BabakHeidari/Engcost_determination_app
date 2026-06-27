# AGENTS.md

## Project overview

This repository is a Flask-based engineering cost determination application. It manages factory/product/material data from JSON and Excel files under `Data/`, lets users edit parameters and BOMs through Jinja/JavaScript pages, and calculates production costs from BOM costs plus allocated factory subfield costs.

## Important folders and responsibilities

- `app.py`: Flask application entry point, blueprint registration, template user context, local dev server.
- `modules/`: Flask blueprints and route handlers by feature.
  - `auth`: login/logout.
  - `desk`: authenticated work desk.
  - `general_parameters`: material-cost page and save route.
  - `factory_parameters`: factory directory/detail/subfield pages and save routes.
  - `product`: product hierarchy, product/category/subcategory creation, BOM pages and save route.
  - `cost_calculation`: cost page and single/bulk cost JSON endpoints.
  - `dashboard`: dashboard page and sample cost-analysis API.
  - `profile`: profile page; profile APIs are currently placeholders only.
- `utils/`: shared paths, authentication helper, cost formulas, data loading, JSON/Excel conversion, metadata/update helpers.
- `templates/`: Jinja templates and page-local JavaScript/CSS.
- `static/`: shared CSS/JS, favicon, and vendored browser libraries.
- `Data/`: active JSON/XLSX application data. Treat as application data, not source-code logic.
- `docs/`: durable project documentation.

## Confirmed commands

No test/lint/build configuration files are present. Confirmed safe commands:

```bash
python app.py
python -m compileall app.py modules utils
python - <<'PY'
import app
print(app.app.url_map)
PY
```

Install currently imported runtime dependencies manually if needed:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install Flask pandas openpyxl
```

## Coding conventions observed

- Python route modules use Flask `Blueprint` objects named by feature, e.g. `dashboard_bp`.
- Protected pages generally use `@login_required` from `utils.auth`.
- Data tables are commonly stored as column-oriented JSON with `_order` and `data` keys.
- Most templates extend `templates/base.html` and include page-local scripts for table behavior.
- Existing code uses direct helper imports from `utils.*`; keep shared data access/costing behavior centralized there.
- Do not wrap imports in `try`/`except` blocks.

## Definition of done for future tasks

- Inspect all related route, utility, template, static, and data-shape files before editing.
- Make the smallest change that satisfies the request.
- Preserve existing behavior unless the task explicitly requires a behavioral change.
- Run relevant safe checks after changes, at minimum `python -m compileall app.py modules utils` for Python changes.
- For UI changes to a runnable web app, take a screenshot when practical.
- Update README/docs when commands, data contracts, setup, or architecture change.
- Commit changes on the current branch and prepare a pull request summary when required by the task environment.

## Safety rules

- Do not alter database schema, migrations, routes, API contracts, calculations, pricing/costing formulas, authentication, or integrations unless explicitly instructed.
- Do not rename internal variables, database fields, URLs, form field names, API keys, JSON keys, or identifiers merely for translation.
- Preserve existing functionality unless the task explicitly requires a behavioral change.
- Treat files under `Data/` as sensitive application data; avoid changing them unless the user specifically requests data changes.
- Do not commit real secrets, credentials, or password hashes.

## Localization rule

- All future end-user interface changes must be Persian (`fa-IR`) and right-to-left (RTL) by default unless explicitly instructed otherwise.
- Internal code, database values, route names, API fields, environment variables, and identifiers remain English unless explicitly requested.
