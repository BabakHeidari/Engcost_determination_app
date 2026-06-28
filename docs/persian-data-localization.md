# Persian data-localization layer

## Purpose and safety boundary

This project now has a presentation-layer Persian data-localization layer for visible demo, sample, reference, report, chart, and lookup values. The layer is intentionally separate from canonical runtime data and business logic.

Data-safety rules followed by this implementation:

- Canonical production data under `Data/Overall` and `Data/Factories` is not overwritten, translated, migrated, or automatically mutated.
- Internal values, API keys, JSON keys, route names, form field names, IDs, formulas, and calculations remain unchanged.
- Persian text is applied at the presentation/read-only demo layer, with fallback to the original value when no mapping exists.
- Persian demo data is activated only by an explicit development environment variable.
- No database schema, binary file, spreadsheet, PDF, image, font, or generated artifact was created.

## Detected visible data sources

| Source type | Files/locations | Classification | Localization handling |
|---|---|---|---|
| Hardcoded template data | `templates/**/*.html` | UI labels, table headings, chart headings, alerts, placeholders | Existing Persian RTL UI remains in templates; data values can use `display_value` where rendered by Jinja. |
| Python dictionaries/constants | `modules/dashboard/routes.py`, `utils/localization.py`, profile page JavaScript constants | Demo/report values, message catalog, roles/modules/status labels | Dashboard sample values are Persian display data; reusable mappings live in `utils/localization.py`. |
| JavaScript arrays/chart datasets | `templates/dashboard/dashboard.html`, page-local scripts in cost/product/factory/profile templates | Chart labels, CSV headers, option lists, client-side generated table text | Dashboard labels/headers/tooltips are Persian; display-only dashboard numbers use Persian locale formatting. |
| JSON fixtures/sample data | `Data/Overall/sample_data.json`, `sample_product.json`, `category_table_sample.json` | Development templates/fallback fixtures | Persian equivalents exist under `Data/Demo/fa/`. |
| Active JSON application data | `Data/Overall/factories.json`, `ProductsLater.json`, `material_costs*.json`, `Data/Factories/**` | Canonical application data and calculation inputs | Not translated or changed. Optional demo reads can redirect known Overall fixture/catalog files to `Data/Demo/fa/`. |
| Seed/mock/development data | Dashboard static API payloads in `modules/dashboard/routes.py`; `Data_Better_Structure/**` | Mock/demo/reference structures | Dashboard mock values are Persian for presentation. `Data_Better_Structure/**` is documented but not wired into runtime demo activation. |
| Database-backed reference values | `Data/Overall/saba.db`, `utils/dbmanager.py` | Inactive/commented SQLite reference | Not changed; no database migration is introduced. |
| Authentication/user records | `Data/Overall/auth_data.*` | Sensitive operational data | Not changed and intentionally untranslated. |
| User-generated/transaction records | Edited BOMs, material costs, factory summaries/subfields, category weights, production prediction files under `Data/` | Production/business data | Not changed. Display mappings are separate from stored values. |
| Statuses/categories/units/lookups | Column names, statuses, departments, units, currencies, dashboard/report labels | Visible reference values | Mapped in `utils.localization.DISPLAY_MAPPINGS` with original-value fallback. |

## Persian display mappings

Mappings are maintained in `utils.localization.DISPLAY_MAPPINGS` and grouped by domain:

- `statuses`: `success`, `ok`, `error`, `failed`, `pending`, `active`, `inactive`, `draft`, `approved`, `rejected`, `completed`.
- `columns`: product/factory/category/BOM/material/factory-subfield column labels.
- `units`: common unit labels and abbreviations such as `kg`, `pc`, `hr`, `day`.
- `currencies`: `IRR`, `USD`, `EUR` and common UI option labels.
- `departments`: factory subfield names such as `Payroll`, `Overhead`, `FinancialCosts`.
- `categories`: dashboard/demo categories, factories, and common city names.
- `reports`: KPI/report keys such as `total_cost` and `detail_breakdown`.

Use `display_value(value, domain=None)` for UI/report labels. If the value is not mapped, it returns the original value so unknown production values remain visible and usable.

## Persian demo/sample equivalents

Persian development/demo equivalents were added as UTF-8 JSON files:

- `Data/Demo/fa/factories.json`
- `Data/Demo/fa/ProductsLater.json`
- `Data/Demo/fa/category_table_sample.json`
- `Data/Demo/fa/sample_data.json`
- `Data/Demo/fa/sample_product.json`

They preserve the expected schemas, keys, data types, and table shapes of their English/canonical counterparts. They are separate alternatives and do not replace canonical data.

## Activating Persian demo data

Persian demo data is off by default. To activate it for development/demo reads of known Overall fixture/catalog files, run the Flask app or verification commands with:

```bash
ENG_COST_DEMO_LOCALE=fa python app.py
```

or for a one-off check:

```bash
ENG_COST_DEMO_LOCALE=fa python - <<'PY'
from utils.load_data import load_json
from utils.paths import product_path
print(load_json(product_path + '.json'))
PY
```

Only the explicit value `fa` enables the demo selector. Without this environment variable, production behavior remains unchanged and canonical paths are used.

## Persian numeric and date presentation

- Raw numbers, calculations, IDs, formulas, monetary inputs, editable fields, API payloads, and CSV raw cost values remain unchanged.
- Display-only dashboard KPI/chart/table values use Persian locale formatting in the browser.
- `utils.localization.format_persian_digits()` is available for safe read-only text formatting.
- Jalali/Shamsi conversion is intentionally not introduced in this task; stored and processed dates remain unchanged.

## Charts, reports, and exports

- Dashboard chart titles, axis names, tooltips, table headings, and CSV headings are Persian.
- Dashboard sample API payload values are Persian where they are visible demo/report labels.
- Machine-readable keys such as `kpis`, `breakdown_by_category`, `factory`, `category`, `cost`, and product catalogue keys remain unchanged.
- CSV raw numeric cost values remain Latin/raw for downstream compatibility; Persian headings provide human-readable context.

## Intentionally untranslated values

The following remain English or raw by design:

- JSON keys, API payload fields, route names, form field names, session keys, Python/JavaScript identifiers, CSS selectors, and filenames.
- Canonical production data in `Data/Overall` and `Data/Factories`.
- Authentication data and user records.
- Product codes, material codes, email/URL-like values, currency codes, and technical acronyms where they are machine-readable or industry-standard.
- Inactive binary/root artifacts and inactive SQLite references.

## Future work

- Add optional Jalali display formatting behind the same presentation boundary.
- Expand Persian numeral formatting to other read-only dashboards and reports after auditing each editable field.
- Add display-only Persian columns to any future exports that also need raw technical columns.
- Extend mappings as product owners finalize manufacturing/accounting terminology.
- Add route-level safeguards if editable demo mode is expanded beyond read-only fixture/catalog selection.

## Persian UI font setup

The Persian RTL design system uses the licensed IRANSansX webfont files that are manually maintained under `static/fonts/` and referenced from the global stylesheet `static/css/style.css`.

Expected font files and weights:

- `static/fonts/IRANSansX-Regular.woff2` — weight `400`.
- `static/fonts/IRANSansX-Medium.woff2` — weight `500`.
- `static/fonts/IRANSansX-Bold.woff2` — weight `700`.

The global stylesheet declares these files with `@font-face`, `font-display: swap`, and relative URLs from `static/css/style.css` to `../fonts/...`, which is compatible with Flask's `/static/` asset serving in both development and production deployments.

The shared font stack is:

```css
"IRANSansX", "Vazirmatn", "Noto Naskh Arabic", Tahoma, "Segoe UI", Arial, sans-serif
```

This stack is applied through `--app-font-family` to the Persian UI shell, navigation, cards, forms, tables, modals, dropdowns, alerts, pagination, dashboard chart text, and print styles. Technical/code-like content still uses monospace fallbacks through the existing `code`, `pre`, `.code-like`, `.formula`, `.sku`, and related LTR utility selectors.

Future font-file replacements must be performed manually and legally by replacing the three files at the same paths with licensed equivalents of the same formats/weights. Do not download fonts from application code, add external font CDNs, rename the expected files, or change the CSS architecture unless the design system is intentionally migrated.
