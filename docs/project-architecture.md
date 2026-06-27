# Project architecture

## High-level request flow

1. A browser requests a Flask route exposed by a blueprint registered in `app.py`.
2. For protected pages/APIs, `utils.auth.login_required` checks whether `session["user"]` exists; unauthenticated users are redirected to the login route.
3. Route handlers in `modules/*/routes.py` load JSON/Excel-backed data through `utils.load_data`, `utils.paths`, pandas, or update helpers.
4. Page routes render Jinja templates from `templates/`, usually extending `templates/base.html`.
5. Templates include shared navigation/header markup plus page-local JavaScript that renders editable tables, calls JSON endpoints with `fetch`, or performs client-side filtering/export behavior.
6. Save/API endpoints receive JSON/form payloads, update files under `Data/`, and return JSON status/cost payloads.

## Important modules and dependencies

- `app.py`
  - Imports all feature blueprints from `modules/*/routes.py`.
  - Registers `cost_calculation_bp` with the `/cost` URL prefix.
  - Provides a template context variable named `user` from the Flask session.

- `utils.paths`
  - Derives `parent_path` from the repository location and defines global data prefixes for products, materials, factories, and sample data.

- `utils.auth`
  - Provides `login_required` for session gating.
  - Reads `Data/Overall/auth_data.xlsx` with pandas and compares SHA-256 password hashes.

- `utils.load_data`
  - Loads JSON files.
  - Locates BOMs, factory summaries, factory subfields, and category weights.

- `utils.updaters`
  - Converts JSON to Excel.
  - Saves module data to JSON/Excel.
  - Adds products/categories/subcategories.
  - Traces factory directory metadata.
  - Creates product metadata.
  - Updates material current/history files.
  - Writes product capacity metadata.

- `utils.cost_determiners`
  - Calculates BOM material totals.
  - Sums factory subfield costs.
  - Allocates subfield costs by category selling-share weight and production prediction.
  - Aggregates final production cost.

## Active data stores

The active application persistence layer is file-based:

- JSON files are the primary runtime data source for products, materials, factories, BOMs, category weights, and production predictions.
- Excel files are used for authentication and for some converted/parallel data copies.
- `Data/Overall/saba.db` exists, but no active route uses it; `utils/dbmanager.py` contains commented SQLite code only.

## Route and data-flow details

### Authentication

- `GET /login` renders the login page.
- `POST /login` reads `username` and `password` from form data.
- `utils.auth.authenticate()` lowercases the username lookup, hashes the submitted password with SHA-256, and compares it with `auth_data.xlsx`.
- On success, `session["user"]` is set and the browser is redirected to `desk.workdesk`.
- `/logout` clears the session.

### Work desk

- `/workdesk` renders `templates/desk/workdesk.html` behind `login_required`.
- Shared sidebar links route users to general parameters, factory parameters, product configuration, cost calculation, dashboard, and profile/profile-like pages.

### General material parameters

- `/general_parameters/` loads `Data/Overall/material_costs.json` and embeds it as `table_json` in `templates/general_parameters/general_parameters.html`.
- Page JavaScript renders an editable table, tracks added/edited/deleted rows, and posts to `/save_materials`.
- `/save_materials` builds an update payload and calls `utils.updaters.material_data_updater()`, which updates current/history material files.

### Factory parameters

- `/factory_parameters/` loads the factory directory from `Data/Overall/factories.json`.
- Posting to `/factory_parameters/<factory_name>` uses the submitted `factory name`, stores it in session, loads:
  - factory summary `Factory_Data.json`,
  - category weights `category_weights.json`,
  - production prediction data from `ProductionPrediction.json` or a fallback generated from the product catalogue.
- Factory detail JavaScript saves:
  - factory summary to `/save_factories`,
  - category weights to `/save_category_table`,
  - production prediction to `/save_prediction_production_per_capita`.
- Posting to `/factory_parameters/<factory_name>/<Subfield>` loads a subfield JSON file and renders an editable subfield table.
- `/save_factory_subfields` writes the subfield JSON, updates the matching Excel sheet, and modifies the factory summary.

### Product configuration and BOMs

- `/product/production_selection` regenerates product metadata from the `Data/Factories` tree, loads the product catalogue, and renders the product selection table.
- `/api/product_options` traces factory/category/subcategory/product hierarchy metadata and returns distinct option lists plus relationships.
- `/add_product`, `/add_category`, and `/add_subcategory` mutate the factory directory structure/data through updater helpers.
- Posting to `/product/<product_name>` loads the selected BOM and material-cost data, stores the BOM path in session, and renders `templates/product/product_page.html`.
- `/save_bom` writes the edited BOM payload back to the session-stored recipe path.

### Cost calculation

- `/cost/cost_calculation` loads the product catalogue and renders `templates/cost/calculation.html`.
- Client-side JavaScript filters/searches products, requests costs, and supports CSV export behavior.
- `/cost/get_cost` accepts a single product object with `Product_Name`, `Factory`, `Category`, and `Subcategory` and returns a cost breakdown.
- `/cost/get_costs_bulk` accepts a list of product objects and returns a product-name-keyed map of cost breakdowns.
- `utils.cost_determiners.cost_aggregator()` is the high-risk core calculation dependency for these APIs.

### Dashboard, charts, and reporting

- `/dashboard` renders `templates/dashboard/dashboard.html`.
- `/api/cost_analysis` currently returns static/sample KPI, category, subcategory, and detail-breakdown data.
- Dashboard JavaScript populates filters from `/api/product_options`, requests `/api/cost_analysis`, renders KPI cards and chart/table areas, and exposes a CSV download button.
- Charting appears to be page-level browser JavaScript; verify exact library/script tags in the template before changing dashboard behavior.

### PDF, print, and document artifacts

- Existing root-level files include `report.pdf`, `report.docx`, `backlog.docx`, `version05232026.pdf`, and `version05232026.pptx`.
- No active backend route was found that generates PDF/DOCX output.
- Search results did not confirm active `window.print`, `jsPDF`, or server-side PDF generation in source routes/templates.

## Relationship between templates, CSS, JavaScript, and routes

- `templates/base.html` loads Bootstrap and Font Awesome from CDNs, then shared `static/css/style.css` and `static/js/main.js`.
- `templates/components/sidebar.html` contains hard-coded route links and `url_for()` links for major features.
- Most feature templates embed their own `<script>` blocks and CSS rather than relying only on shared static files.
- Static assets provide the global shell, responsive sidebar behavior, favicon, and vendored spreadsheet/table libraries.
- Route handlers pass JSON-like Python data into templates with variables such as `table_json`, `factory_name`, `category_table`, `bom_json`, and `materials_data`.

## Likely localization-sensitive areas

Future end-user UI changes should be Persian (`fa-IR`) and RTL by default. High-impact localization areas include:

- Shared shell: `templates/base.html`, `templates/components/header.html`, `templates/components/sidebar.html`.
- Page titles, buttons, table labels, modals, alerts, and placeholders in all feature templates.
- Client-side generated text in page-local JavaScript.
- Currency/number formatting in cost/factory templates and JavaScript.
- Dashboard chart labels, CSV headers, KPI labels, and filter labels.

Do not translate or rename internal route names, JSON keys, form field names, database/data fields, environment variables, or Python identifiers unless explicitly requested.

## High-risk files to change

- `utils/cost_determiners.py`: core production-cost formulas.
- `utils/updaters.py`: writes JSON/Excel files, product metadata, material history, and hierarchy data.
- `utils/auth.py`: authentication/session helper and password hashing.
- `utils/paths.py`: central data path prefixes.
- `modules/*/routes.py`: route URLs, API contracts, session keys, and persistence behavior.
- `Data/Overall/auth_data.xlsx`: credential source.
- `Data/Factories/**/category_weights.json`, `ProductionPrediction.json`, `Factory_Data*.json`, and product BOM JSON files: calculation inputs.
- `templates/*/*.html` with embedded JavaScript: frontend behavior and API payload contracts.
