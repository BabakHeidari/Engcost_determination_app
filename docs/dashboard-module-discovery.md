# Dashboard Module Discovery Report

## 1. Executive Summary

This document is a read-only current-state audit of the technical module ID `dashboard`. The audit found **two registered Dashboard endpoints**, **four displayed/calculated KPI fields**, **two active charts**, one detail table, one client-side CSV export, and four visible filters. Only `modules/dashboard/routes.py` is implementation code inside `modules/dashboard/`; the active presentation and almost all behavior live in `templates/dashboard/dashboard.html`.

**FACT:** `GET /dashboard` builds a factory list from the canonical Profile JSON-backed `factories[]` registry and a five-item hard-coded category list, then server-renders the page. The browser subsequently calls `/api/cost_analysis`, whose response is deliberately zero/empty because no canonical transactional Dashboard dataset exists. It reads no costing, BOM, material, production, or factory-operational files.

**FACT:** The page also calls `/api/filter_options`, but no such route is registered anywhere in the repository. Consequently, changing the factory/category/subcategory controls attempts to parse the HTML 404 response as JSON and rejects; there is no catch or user-facing recovery around those calls. Product, category, and subcategory filtering is therefore not functionally connected to data.

**FACT:** Authentication is consistently enforced with `login_required`. Factory-specific `/api/cost_analysis?factory=<id>` requests are validated server-side against the canonical registry, active state, and the user's factory-level `dashboard` READ grant. A no-factory API request requires GLOBAL `dashboard` READ. Both `IT_ADMIN` and `FINANCE_ECONOMIC_ADMIN` receive implicit full access and see all active factories.

**OBSERVATION — highest risk:** The page route does not require GLOBAL READ when the user has at least one accessible factory; this is reasonable for a mixed-scope shell but differs from older authorization documentation that labels the page GLOBAL-only. More importantly, the UI exposes an “all factories” choice to factory-only users. That request correctly fails closed (403), but the user experience implies an unavailable capability. No current cross-factory business data can leak because the API returns constants; factory validation would prevent a Factory A user requesting Factory B.

**OBSERVATION — security debt:** Future non-empty API data rendered by `renderDetailTable()` and filter loaders is interpolated into `innerHTML` without escaping. That is a latent DOM-XSS risk if product/factory/category fields become user-controlled. The current detail arrays are empty, so this path does not presently expose data.

**OBSERVATION — architecture:** Documentation predating the current route body describes sample or product-backed data, but current code is intentionally an honest empty report. The report below treats executable code as authoritative and identifies such documentation drift explicitly.

No implementation, route, template, JavaScript, CSS, test, registry, authorization, costing, or application-data file was changed. No screenshots or other image artifacts were created.

## 2. Files and Documentation Read

### Instructions

- `AGENTS.md` (the sole repository instruction file found; no nested `AGENTS.md` exists under `modules/`, `templates/`, `utils/`, `tests/`, or `docs/`).

### Documentation read

All Markdown files present under `docs/` at audit time were read:

1. `docs/access-denied-ux.md`
2. `docs/audit-history.md`
3. `docs/authentication-json-migration.md`
4. `docs/authorization-matrix.md`
5. `docs/factory-integration-inventory.md`
6. `docs/factory-registry-discovery.md`
7. `docs/jalali-date-localization.md`
8. `docs/localization-audit.md`
9. `docs/module-registry.md`
10. `docs/persian-data-localization.md`
11. `docs/phase-12-hardening-and-operations.md`
12. `docs/profile-access-control-model.md`
13. `docs/profile-excel-exchange.md`
14. `docs/profile-frontend-phase-10.md`
15. `docs/profile-json-data-access-layer.md`
16. `docs/profile-json-storage-architecture.md`
17. `docs/profile-module-current-state.md`
18. `docs/profile-module-implementation-plan.md`
19. `docs/profile-user-management.md`
20. `docs/project-architecture.md`
21. `docs/thesis-sections-3-to-5-fa.md`

Important documentation conclusions used in this audit are: the exact seven grantable IDs; `dashboard`'s GLOBAL+FACTORY scopes; the canonical `factories[]` registry; deny-by-default USER authorization; peer top-level administrator roles; custom HTML/JSON 403 behavior; canonical Gregorian/ISO storage with Jalali display; and `desk`'s mandatory READ baseline without inheritance of other module grants.

**Documentation drift:** `docs/project-architecture.md` says Dashboard JavaScript populates filters from `/api/product_options`, while the active template calls nonexistent `/api/filter_options`. It also calls the API “static/sample”; current `cost_analysis()` more precisely describes and returns an “honest empty report.” The older localization and thesis documents similarly describe sample data. These are historical descriptions, not the current executable data path.

### Implementation and evidence files read

- Dashboard: `modules/dashboard/__init__.py`, `modules/dashboard/routes.py`, `templates/dashboard/dashboard.html`, `templates/dashboard/dashboard_newer.html`, `templates/dashboard/dashboard copy.html`.
- Registration/shared shell: `app.py`, `templates/base.html`, `templates/components/header.html`, `templates/components/sidebar.html`, `static/css/style.css`, `static/js/main.js`, `static/js/jalali-date.js`.
- Authentication/authorization/factory/storage: `utils/auth.py`, `utils/profile_authorization.py`, `utils/module_registry.py`, `utils/factory_service.py`, and relevant portions of `utils/profile_store.py`, `utils/profile_view.py`, `utils/profile_access_manager.py`, `utils/localization.py`.
- Related module entry points: `modules/desk/routes.py`, `templates/desk/workdesk.html`, `modules/cost_calculation/routes.py`, `utils/cost_determiners.py`, `modules/factory_parameters/routes.py`, `modules/general_parameters/routes.py`, `modules/product/routes.py`, `modules/profile/routes.py`, and relevant loaders/path helpers under `utils/`.
- Tests found by Dashboard/reference search: `tests/test_friendly_forbidden.py`, `tests/test_mandatory_desk_access.py`, `tests/test_module_registry.py`, `tests/test_profile_access_model.py`, `tests/test_authorization_enforcement.py`, `tests/test_profile_frontend_refactor.py`, `tests/test_audit_history.py`, and `tests/test_iransans_font_setup.py`.
- Repository-wide searches covered route decorators, `filter_options`, `cost_analysis`, `dashboard`/`Dashboard`/`DASHBOARD`/`dashboard_module`, navigation, Desk references, data paths, tests, and chart-library usage. Application-data contents were not copied into this report.

## 3. Dashboard File/Directory Map

```text
modules/dashboard/
├── __init__.py                 # empty; no exports, configuration, or initialization
└── routes.py                   # blueprint, page route, empty-report JSON route

templates/dashboard/
├── dashboard.html              # active page; markup + inline CSS + inline JavaScript
├── dashboard_newer.html        # unreferenced alternate/prototype template
└── dashboard copy.html         # unreferenced older alternate/prototype template
```

`__pycache__` files may exist locally but are generated bytecode, not meaningful source.

There are no Dashboard-specific controllers, services, forms, schemas, serializers, test directories, Python utilities, configuration modules, static JS/CSS files, or data adapters. `app.py` imports `dashboard_bp` directly from `modules.dashboard.routes` and registers it without a URL prefix. Jinja resolves the active template through the global `templates/` directory.

The two alternate templates are not referenced by any Python route or Jinja include. Both expect a `dashboard_data` context that the active route does not supply. `dashboard copy.html` contains four revenue/profit KPIs and two charts; `dashboard_newer.html` adds client-side product filtering/table logic. They are historical/prototype code, not current behavior.

## 4. Routes and Entry Points

Blueprint: `dashboard_bp = Blueprint("dashboard", __name__)`. Technical module and blueprint ID: exactly `dashboard`. There is no URL prefix.

| Route | Method | Endpoint | Purpose | Auth Required | Required Permission | Factory Context | Parameters | Response Type |
|---|---|---|---|---|---|---|---|---|
| `/dashboard` | GET (HEAD/OPTIONS implicit) | `dashboard.dashboard` | Render the Dashboard shell and filter seed data | Yes, `@login_required` | FACTORY READ for at least one active factory **or** GLOBAL READ; top-level roles bypass through policy | Accessible active factories are listed; no selected factory | No query/form parameter is read | HTML/Jinja; 403 HTML or JSON according to `Accept`/request type |
| `/api/cost_analysis` | GET (HEAD/OPTIONS implicit) | `dashboard.cost_analysis` | Return the empty KPI/breakdown report contract | Yes, `@login_required` | FACTORY READ when non-empty `factory` is supplied; otherwise GLOBAL READ | `factory` query value, if truthy, is registry/access validated | Reads one `factory`; silently ignores repeated `category`, `subcategory`, and `product` query values sent by UI; no forms | JSON 200, custom JSON 403/404 |

**FACT:** Exactly two Dashboard-owned routes/endpoints are registered by source inspection.

**FACT:** `/api/filter_options` is called by the active browser code but is not registered in any blueprint. `/api/product_options` exists in `product`, but the Dashboard does not call it.

**FACT:** Neither route supports POST and there are no meaningful Dashboard WRITE or MODIFY operations. CSV generation is entirely local in the browser and does not mutate server state.

## 5. Request/Data Flow

### Page lifecycle

```text
Browser GET /dashboard
  → app.py-registered dashboard_bp
  → utils.auth.login_required
      → session["user_id"]
      → ProfileDataStore.get_user_by_id()
      → active-account and forced-password-change checks
      → g.current_user
  → modules.dashboard.routes.dashboard()
      → get_profile_store()
      → FactoryService(...).get_accessible_factories(user, "dashboard")
          → ProfileDataStore.list_factories()
          → active factory filter
          → can_access_module(..., factory_id, "READ")
          → public {id, code, name[, location]} objects
      → if list empty, has_access(... "dashboard", "READ", GLOBAL)
      → five hard-coded categories passed through display_value(..., "categories")
      → render_template("dashboard/dashboard.html", filter_options=...)
  → templates/base.html shared RTL shell
  → templates/dashboard/dashboard.html markup/inline CSS/inline JS
  → populateInitialFilters()
      → factory and category DOM options
  → user changes filters
      → fetch /api/filter_options (404; no route)
  → user clicks تحلیل هزینه
      → fetch /api/cost_analysis?factory=...&category=...&subcategory=...&product=...
      → login_required
      → factory-specific FactoryService.require_access(), or GLOBAL has_access()
      → fixed zero/empty JSON
  → renderDashboard(data)
      → format four KPIs
      → ECharts bar + doughnut-style pie initialization
      → detail table rendering
      → enable local CSV button
```

There is no server-side factory resolution for the initial selection because no selection is sent on page load. The route supplies allowed choices only. There are no Python transformations, KPI calculations, chart preparations, costing calls, Excel reads, or operational JSON reads after authorization. All active chart series mapping and number formatting occur in JavaScript.

### API response contract

The successful response always has:

```json
{
  "kpis": {
    "total_cost": 0,
    "avg_cost_per_product": 0,
    "product_count": 0,
    "top_cost_driver": "—"
  },
  "breakdown_by_category": [],
  "breakdown_by_subcategory": [],
  "detail_breakdown": []
}
```

That shape is the sole current source for the active KPI/chart/table payload. It is not derived from `cost_calculation` output.

## 6. Factory Context and Factory Isolation

### Selector origin and visibility

**FACT:** Factory identity comes from `ProfileDataStore.list_factories()` via `FactoryService.get_accessible_factories()`, so it uses canonical `factories[]`, not `Data/Factories` directory discovery or a Dashboard constant. Returned objects expose only public fields.

**FACT:** Active factories newly created in the canonical registry appear on the next `/dashboard` request if the current user has effective factory `dashboard` READ. Newly created factories appear automatically for `IT_ADMIN` and `FINANCE_ECONOMIC_ADMIN`, because both roles have implicit MODIFY for every valid module/scope. An ordinary USER sees only active factories with an exact factory-scoped `dashboard` grant at READ or higher.

**FACT:** Inactive factories are omitted. A top-level administrator does not see inactive factories in this selector because the default `active_only=True` applies to all roles.

### Selection and persistence

- The initial option is empty-string “همه کارخانه‌ها”. No individual factory is selected by default.
- Selection exists only as the `<select>` DOM value. It is not persisted in session, local storage, cookies, hidden form fields, or a page URL navigation.
- The browser adds `factory=<id>` to AJAX query strings only when the value is non-empty.
- Reloading the page resets selection to “all factories.”
- There is no server-chosen first factory and no memory across requests.

### Edge-case behavior

| Scenario | Actual current behavior |
|---|---|
| No factories exist | GLOBAL READ/top-level user receives page 200, selector is replaced by “هیچ کارخانه‌ای تعریف نشده است.” and disabled; Analyze sends no factory and returns empty report. USER without GLOBAL READ receives page 403. |
| USER has no applicable factory access and no GLOBAL READ | `/dashboard` aborts 403 before render. |
| USER has GLOBAL READ but no factory grant | Page renders with disabled “no factories” selector even if registry factories exist, because the list is factory-grant filtered; global analysis remains available. Message incorrectly says none are defined. |
| Selected/new factory has no operational data | API does not inspect operational data, so it returns the same zero/empty report. No “unconfigured” distinction exists. |
| Invalid factory ID | API returns JSON 404 with `{"error": "کارخانه در رجیستری سامانه وجود ندارد."}`. |
| Inactive factory ID | API returns JSON 403 with `{"error": "کارخانه غیرفعال است."}`. |
| Valid but inaccessible factory ID | API returns JSON 403 with `{"error": "دسترسی به این کارخانه مجاز نیست."}`. |
| No factory query | Requires GLOBAL Dashboard READ and then returns empty report. A factory-only USER receives 403. |
| Duplicate `factory` query keys | Flask `request.args.get()` uses the first value; that value is validated. |

### Isolation conclusion

**FACT:** Factory filtering is enforced server-side at the API boundary, not merely in the selector. A Factory A-only user who changes the request to Factory B is denied before any business-data load. Unknown IDs fail 404; inaccessible/inactive IDs fail 403.

**OBSERVATION:** Current cross-factory business-data leakage is not possible through this response because it contains no business data. Registry existence is partially distinguishable (404 versus 403), and the endpoint's custom errors disclose inactive/existence state and exception text, unlike the global generic 403 policy. This is a low-to-medium information-disclosure concern depending on threat model.

**OBSERVATION:** If data is later added after the existing access check, isolation remains structurally sound only if every query is scoped to the validated returned factory. The present route discards that returned object and does not establish an operational key, because it loads no operational files.

## 7. Authorization and Access Model

The canonical hierarchy is `NONE < READ < WRITE < MODIFY`; stored permission arrays are cumulative. The registry declares `dashboard` with both GLOBAL and FACTORY scopes. Missing Dashboard grants give ordinary USERs `NONE`. `IT_ADMIN` and `FINANCE_ECONOMIC_ADMIN` are peer top-level roles and resolve to implicit MODIFY.

### Enforcement layers

| Layer | Current enforcement |
|---|---|
| Navigation | Sidebar and Desk Dashboard links are shown only when `module_navigation['dashboard']` is truthy. This is convenience, not the sole boundary. |
| Page route | `login_required`; then route-local rule requires at least one accessible active factory or GLOBAL READ. No shared `@require_access` decorator is used. |
| API route | `login_required`; `FactoryService.require_access(..., "dashboard")` for a factory, or explicit GLOBAL `has_access()` without one. |
| Service/data | `FactoryService` enforces canonical identity, active status, and effective factory permission. No Dashboard analytical service/data layer exists. |

**Direct-route checks:** A user with `dashboard = NONE` globally and for every factory cannot open `/dashboard` (403) or successful `/api/cost_analysis` (403). A user with factory-level READ for A can open the page and query A, cannot query B, and cannot run the no-factory global report. A global-only READ user can open the page and global API but receives no selectable factories because GLOBAL does not imply FACTORY access.

**WRITE/MODIFY:** There are no Dashboard server mutations. Higher levels only inherit READ and currently unlock no additional Dashboard feature.

**Documentation discrepancy:** `docs/authorization-matrix.md` and `docs/module-registry.md` classify `GET /dashboard` as GLOBAL READ. Actual route code also admits a factory-only user when `get_accessible_factories()` is non-empty. This report records code behavior; intended product policy is unresolved.

## 8. UI Structure

```text
Shared base page (fa, RTL)
├── responsive right-side navigation / mobile overlay
├── shared header (welcome, last-login date, current time, logout)
├── main content
│   ├── Back button (history.back)
│   └── Dashboard panel
│       ├── H3: داشبورد هزینه ساخت باتری
│       ├── tab navigation
│       │   ├── active cost-analysis tab
│       │   └── sensitivity tab markup (tab control commented out)
│       └── cost-analysis pane
│           ├── filter card
│           │   ├── factory single-select
│           │   ├── category multi-select
│           │   ├── subcategory multi-select
│           │   ├── product multi-select
│           │   ├── Analyze button
│           │   └── disabled-until-success CSV button
│           ├── initially hidden Dashboard output
│           │   ├── four-card KPI grid
│           │   ├── category bar chart + subcategory ring/pie chart
│           │   └── responsive five-column detail table
│           └── initial instruction placeholder
└── shared footer
```

The sensitivity content exists in markup, including text saying it will be implemented later, but its tab link is commented out; normal users cannot navigate to it through the page control.

### Current UX assessment

**FACT OBSERVED FROM CODE:** The first visible Dashboard-specific content is Back, title, cost tab, filters, two actions, and an instructional placeholder. Results remain hidden until a successful API response. Analyze has no spinner, disabled state, or progress text. Success immediately shows four zero values, two empty charts, an empty table, and enables CSV. Filter-change requests provide no loading/error state. Analyze failure uses a generic browser `alert` plus console logging.

**POTENTIAL UX ISSUE:** The visually available “all factories” option fails for factory-only users; the page gives no advance explanation. Cascading filters silently fail because their API is absent. A zero/empty response replaces the useful instruction with blank output instead of explaining that canonical transactional data is unavailable. A no-factory selector message conflates “no registry factories” with “no factory-level grants.” Chart titles and Rial units are clear, but empty charts provide no legend/annotation explaining absence of data. The page is relatively sparse after response because the API contains no rows.

## 9. Filters

| Filter | Option source | Frontend control | Backend parameter | Default | Dependencies | Validation | Refresh/persistence |
|---|---|---|---|---|---|---|---|
| Factory | Canonical active accessible `factories[]` public views supplied in Jinja context | Single `<select>`; includes “all factories” | `factory` query | Empty/global | Intended to drive subcategory/product and analysis | Analysis API validates exact ID/access/active state; missing filter API does not validate | No page reload; AJAX on change and Analyze; DOM-only, reset on reload |
| Category | Five route constants: کاتد، آند، الکترولیت، جداکننده، بسته‌بندی, each passed through `display_value` | Multi-select, size 3 | Repeated `category` query | None selected | Intended factory/category cascade | Ignored by cost API; filter API absent | AJAX on change; DOM-only |
| Subcategory | Intended `data.subcategories` from `/api/filter_options` | Multi-select, size 3 | Repeated `subcategory` query | Empty | Factory + categories | No functioning backend; response assumptions only | AJAX on factory/category change; not persisted |
| Product | Intended `data.products` from `/api/filter_options` | Multi-select, size 3 | Repeated `product` query | Empty | Factory + categories + subcategories | No functioning backend; ignored by cost API | AJAX on factory/category/subcategory change; not persisted |

There is no time/period/date/cost-type/metric filter. Filter options are not encoded into the browser page URL, so Back/Forward and bookmarking cannot restore filter state.

**OBSERVATION:** Category options are loaded with `innerHTML +=`; subcategory/product responses use joined HTML strings. No shape check, response status check, escaping, abort/debounce, or race protection exists. Rapid changes could apply responses out of order even if the missing API is later supplied.

## 10. KPI Inventory

The count is **four current active KPIs**. They are both returned by Python and displayed as cards.

| Internal name | Persian label | Meaning | Formula/calculation | Input data | Factory/time/filter scope | Formatting | Empty behavior | Owner |
|---|---|---|---|---|---|---|---|---|
| `total_cost` | کل هزینه | Intended total cost | Constant `0`; intended business formula **UNRESOLVED** | None | Authorization is factory or GLOBAL; response is identical; no time or category/product filtering | `formatCurrency`: `fa-IR`, exactly 2 decimals + `ریال` | Displays `۰٫۰۰ ریال` | `cost_analysis()` constant (D: unknown placeholder); JS presentation |
| `avg_cost_per_product` | میانگین هزینه / محصول | Intended mean product cost | Constant `0`; intended numerator/denominator **UNRESOLVED** | None | Same as above | Same currency formatter | Displays `۰٫۰۰ ریال`; no divide occurs | Same |
| `product_count` | تعداد محصولات | Intended number of products | Constant `0`; counting/deduplication rule **UNRESOLVED** | None | Same as above | `fa-IR`, maximum 0 fractional digits | Displays `۰` | Same |
| `top_cost_driver` | مهم‌ترین عامل هزینه | Intended leading cost driver | Constant em dash (`—`); ranking/tie/unit rule **UNRESOLVED** | None | Same as above | Raw text; fallback `نامشخص` only for falsy value | Displays `—`, not fallback | Same |

No revenue, profit, margin, trend, period, capacity, production, or BOM KPI is active. Those names only occur in unreferenced alternate templates and must not be counted as current KPIs.

### Calculation ownership

- Zero constants and em dash: **D. Unknown/placeholder**, explicitly described by the route as an honest empty report.
- `formatNumber`, `formatInteger`, `formatCurrency`: **A. Dashboard presentation calculations**.
- Mapping breakdown items to chart arrays: **A. Dashboard presentation calculations**.
- No **B. reusable analytical calculation** exists.
- No **C. costing/business-domain calculation** is owned or duplicated by the active Dashboard. `utils.cost_determiners.cost_aggregator()` is not imported or invoked.

## 11. Chart Inventory

The count is **two active visualizations**, both constructed client-side with ECharts 5 loaded from jsDelivr.

### 1. هزینه بر اساس دسته

| Property | Current value |
|---|---|
| Type/library | Vertical bar, ECharts 5 |
| Python preparation | None; `breakdown_by_category` is always `[]` |
| JS function | `renderدستهBarChart(breakdown)` |
| Option generation | Maps each item `.name` to category X-axis and `.cost` to series data; disposes prior instance; initializes and calls `setOption` |
| X-axis | Category names; labels rotate 30 degrees |
| Y-axis | Numeric value; name `هزینه (ریال)`; no tick formatter |
| Series | One bar series named `هزینه`, color `#5470c6` |
| Tooltip | Axis trigger; `valueFormatter` calls `formatCurrency()` |
| Legend | None configured |
| Factory/time/filter dependency | Payload endpoint is authorized by factory/global; data does not vary; no time; non-factory filters ignored |
| Empty state | Empty axes/series; no explicit message |
| RTL/font | Shared computed `--app-font-family` applied. No ECharts `dir`, Persian alignment, bidi isolation, or explicit RTL tooltip styling |
| Responsiveness | Parent fixed height 400px; CSS collapses grid at 768px; global window resize calls instance `.resize()` |

### 2. هزینه بر اساس زیردسته

| Property | Current value |
|---|---|
| Type/library | Doughnut-style pie (`radius: ['40%', '70%']`), ECharts 5 |
| Python preparation | None; `breakdown_by_subcategory` is always `[]` |
| JS function | `renderزیردستهPieChart(breakdown)` |
| Option generation | Maps `.name` and `.cost` to `{name, value}`; disposes/reinitializes; calls `setOption` |
| Axes | None |
| Series/units | One unnamed pie series; values intended as Rial costs; percentage supplied by ECharts |
| Tooltip | Item trigger; name, formatted Rial value, and rounded Persian-locale percent |
| Labels | Always shown; `name: percent٪` with shared font |
| Legend | None configured |
| Factory/time/filter dependency | Same as category chart |
| Empty state | Blank ring area/no explicit message |
| RTL/font | Shared font only; no explicit RTL/bidi configuration |
| Responsiveness | Same fixed-height parent, breakpoint, and window listener |

**Chart failure behavior:** If CDN ECharts fails to load, `echarts` is undefined during rendering; the Analyze handler's surrounding `try` catches synchronous failure reached after the fetch and displays the generic load alert. If ECharts fails asynchronously internally, no chart-specific handler exists. The external library is unpinned at major version (`@5`) and has no local fallback or integrity attribute.

## 12. Tables and Detailed Views

One active detail table, `#detailTable`, appears after analysis.

| Aspect | Current behavior |
|---|---|
| Title | ریز تفکیک هزینه |
| Columns | کارخانه; دسته; زیردسته; محصول; هزینه (ریال) |
| Source | `detail_breakdown`, currently always empty |
| Rendering | `renderDetailTable(details)` clears `<tbody>`, appends an HTML template per row, defaults missing text to `نامشخص`, formats cost in Rial |
| Sorting | None; preserves API order |
| Filtering | Intended server query filters, but API ignores category/subcategory/product and returns no rows |
| Pagination | None |
| Factory context | Intended row-level factory; no current rows; API factory access is checked |
| Interactions | No links, drill-down, selection, hover only via Bootstrap table class |
| Responsiveness | Wrapped by `.table-responsive` for horizontal scrolling |
| Empty state | Empty `<tbody>` with headers; no row/message |

CSV export is a detailed-view action rather than a server endpoint. It exports the five fields in current API order, with a Persian header but ASCII filename `cost_breakdown.csv`. There is no UTF-8 BOM, CSV escaping of embedded double quotes, spreadsheet-formula neutralization, date/time, filter metadata, or indication that an empty file will be produced. It is enabled after any successful response, including the empty report.

There are no active rankings, summaries beyond KPI cards, drill-downs, modal details, pagination controls, or links/actions on rows.

## 13. Data Source Inventory

| Dashboard Element | Data Source | File/Function | Factory Scoped? | Transformation | Refresh Method |
|---|---|---|---|---|---|
| Factory selector | Canonical Profile JSON `factories[]` through configured `APP_DATA_FILE`/instance store | `get_profile_store`; `ProfileDataStore.list_factories`; `FactoryService.get_accessible_factories`; `dashboard()` | Yes, exact active factory grant; top admins implicit all-active | Public projection to id/code/name/location; active/access filtering | Fresh store read each page request; browser reload required for registry changes |
| Category selector | Static Python list | `modules/dashboard/routes.py:dashboard()` and `display_value` | No | Display mapping lookup | Re-created each page request, then inserted on initialization |
| Subcategory selector | Intended missing JSON API | `loadSubcategories()` → `/api/filter_options` | Intended, not implemented | Intended `.subcategories` → HTML options | Change event; currently 404/rejected |
| Product selector | Intended missing JSON API | `loadمحصولs()` → `/api/filter_options` | Intended, not implemented | Intended `.products` → HTML options | Change event; currently 404/rejected |
| Total/average/count/top-driver KPIs | Static empty-report dictionary | `cost_analysis()` | Access-scoped but not data-scoped | JS `fa-IR` numeric/currency formatting | Analyze fetch |
| Category chart | Static empty list | `cost_analysis`; `renderدستهBarChart` | Access-scoped only | JS maps names/costs | Analyze fetch |
| Subcategory chart | Static empty list | `cost_analysis`; `renderزیردستهPieChart` | Access-scoped only | JS maps names/costs and ECharts calculates percentage | Analyze fetch |
| Detail table | Static empty list | `cost_analysis`; `renderDetailTable` | Access-scoped only | DOM row templates | Analyze fetch |
| CSV | In-memory `currentData.detail_breakdown` | CSV click listener | Inherits last successful API payload | Client string concatenation → Blob/object URL | Manual click; no server refresh |
| Shared user/nav/header | Canonical user/session/profile store plus hard-coded shared header fallback | `app.py:inject_user`, shared templates | Navigation is effective module access; not factory data | Context/view labels and Jalali filter for header constant | Every page request; clock updates client-side |

**Not data sources:** No Dashboard route reads Excel, CSV, BOM JSON, material costs, category weights, production predictions, factory operational files, `utils.load_data`, or `utils.cost_determiners`. No generated costing results are persisted for Dashboard consumption. The ECharts CDN supplies code, not business data.

## 14. Product / Category / Subcategory Relationships

**FACT:** The active Dashboard backend does not load products or hierarchy relationships. It supplies five global-looking category labels without factory association. The template structurally assumes cascading `factory → category → subcategory → product`, but the called endpoint does not exist, so no actual relation reaches the page.

**FACT elsewhere in repository:** `product` owns hierarchy/catalog behavior. Repository documentation and routes describe product identity/catalog as global/multi-factory while assignment, recipe/BOM, capacity, and operational configuration are factory-specific. Category/subcategory directory/configuration paths are tied to factory operational context. This architecture is potentially reusable but is not a current Dashboard dependency.

Therefore the active Dashboard assumptions are:

- Products global vs factory-specific: **UNRESOLVED in active Dashboard**; UI suggests factory-filtered options, but no implementation supplies them.
- Product configurations: not read; repository product module treats operational configuration/BOM selection as factory-contextual.
- Categories: five static Dashboard options, effectively global in current page context.
- Subcategories: **UNRESOLVED**; no data source.
- Whether labels correspond to canonical product catalog values after `display_value`: **UNRESOLVED**; no joined data validates them.

## 15. Date and Time Handling

Dashboard-specific routes, filters, KPI payloads, charts, table, and CSV contain **no date or period fields**. There is no monthly/yearly aggregation, current-period calculation, default horizon, historical range, date sorting, or timezone operation. Consequently no Dashboard-specific Jalali conversion occurs.

The shared base/header provides only application-shell date behavior: a hard-coded Gregorian date string `2026-04-21` is rendered through the `jalali_date` Jinja filter, and `static/js/main.js` updates current time using browser behavior. The repository-wide policy keeps storage/API/sorting canonical Gregorian/ISO and localizes end-user displays to Jalali. Dashboard would need to apply that existing layer if time data is introduced; it currently has none to apply.

**Potential inconsistency:** The shared header's last-login date is a fixed template constant rather than the authenticated user's real `last_login_at`, while Desk uses a session value/fallback. This is shared-shell debt visible on Dashboard, not Dashboard-owned date logic.

## 16. Frontend Architecture

- **Server-rendered:** Shared shell, title/tabs, filter controls, hidden cards/charts/table, placeholder, and `filter_options` JSON literal.
- **Client-rendered:** Factory/category option population, intended cascading subcategory/product options, KPI text, both charts, detail rows, and CSV.
- **JavaScript location:** All Dashboard-specific JS is inline in `templates/dashboard/dashboard.html`; no Dashboard static bundle/module exists.
- **CSS location:** All Dashboard-specific CSS is inline; Bootstrap/shared `style.css` also applies.
- **API calls:** Two missing `/api/filter_options` call sites and one functional `/api/cost_analysis` call site.
- **Initialization:** Top-level constants/elements are captured; event listeners are registered; `populateInitialFilters()` runs immediately at the end of the script.
- **State:** `currentData`, two ECharts instance variables, and DOM selection values; all page-local globals.
- **DOM updates:** `textContent` for factory labels/KPIs; `innerHTML` for categories, dependent options, detail rows, and resets.
- **Loading:** None. Buttons remain active; no cancellation or request sequencing.
- **Error:** Analyze has `try/catch` with alert and console. Filter loaders have no `try/catch` and do not inspect `response.ok`.
- **Empty:** Initial instruction and special no-factory selector; no post-analysis data-empty state.
- **Reuse:** Shared base/sidebar/header/font CSS. Currency, table, option, request, and empty-state logic is page-local.
- **Events:** factory/category changes each start two asynchronous calls; subcategory starts one; Analyze starts one; CSV click creates a Blob; window resize resizes both charts.
- **Bootstrap mismatch:** The page uses Bootstrap 4-era tab attributes `data-toggle="tab"`, while base loads Bootstrap 5, which expects `data-bs-toggle`. The active pane is statically shown, and the only visible tab need not switch, masking this incompatibility.

The names `loadمحصولs`, `renderدستهBarChart`, and `renderزیردستهPieChart` mix Persian and English within identifiers. This is executable and valid JavaScript but inconsistent with the project's English-internal-identifier convention.

## 17. Empty States and Error Handling

| Condition/failure | Current result visible to user | Technical path |
|---|---|---|
| No registry factories | Disabled selector says none defined; global-capable user may still analyze empty report | `populateInitialFilters` |
| No accessible factory grants | If GLOBAL READ absent: custom Persian 403 page; if present: misleading “none defined” selector | `dashboard()` and global error handler |
| Selected factory has no data | Four zeros/em dash, blank charts, empty table; no explanation | API never loads data |
| Product data empty | Not distinguishable; dependent option endpoint is missing | filter fetch failure |
| Costing not calculated | Not distinguishable; costing is never queried | fixed API response |
| Missing/malformed operational JSON/Excel | No effect: Dashboard does not read them | N/A |
| Missing/malformed canonical Profile JSON | `login_required` generally treats store error as no user and redirects to login; direct factory listing errors are otherwise not caught | `load_current_user`, store/service |
| Metric cannot be calculated/divide by zero | No calculation occurs; zero constant masks distinction | `cost_analysis` |
| Empty chart series | Blank ECharts plot/pie; no explicit empty label | chart render functions |
| Invalid/inaccessible/inactive factory | Analyze alert says generic load error (`Failed to fetch data`); server's specific JSON message is not displayed | API custom 404/403 + Analyze catch |
| Dashboard NONE | HTML Persian custom 403 for normal navigation; generic JSON 403 for JSON/Accept requests | `app.py:forbidden` |
| Missing `/api/filter_options` | Unhandled rejected async function; normally console error, stale/empty controls | loaders parse HTML 404 as JSON |
| Missing expected API keys | JS TypeError such as `.map`/property access; Analyze catches errors arising in its awaited flow, filter functions do not | render/load functions |
| API malformed JSON/network error | Analyze alert + console; filter loaders unhandled | `fetch`/`.json()` |
| ECharts unavailable | Analyze-time ReferenceError caught as generic cost-data alert; no library fallback | chart render call |
| CSV row contains quotes/newlines/formulas | Invalid/unsafe spreadsheet interpretation possible; no warning | direct interpolation |

The app-wide 403 HTML page intentionally hides permission/factory details and keeps status 403. API behavior has two variants: `abort(403)` reaches the standard `{success:false,error:"forbidden",message:...}` handler; `cost_analysis()` catches factory exceptions and returns its own `{error: exception_text}` body. Unauthorized users are redirected to login by `login_required`; forced-password-change users are redirected to that flow.

No divide-by-zero, aggregation exception, missing product lookup, or path traversal is reachable because those operations do not exist in the active Dashboard.

## 18. Performance and Data Freshness

### Request characteristics

| Risk | Impact | Evidence |
|---|---|---|
| Profile store rereads | LOW at current scale | Authentication loads current user; page then constructs another store/service and lists factories. File-store locking/read details apply. No Dashboard cache. |
| Filter change fan-out | MEDIUM | Factory/category change each launch two failed requests; category changes may be frequent; no debounce/cancellation. |
| Chart lifecycle | LOW now | Instances are disposed/recreated on every analysis instead of updating; payload arrays are empty. |
| Detail rendering | LOW now / potentially HIGH with large future arrays | Repeated `tbody.innerHTML +=` reparses growing markup and is quadratic-like in practice; current array is empty. |
| Large Jinja context | LOW | Only accessible public factory objects and five categories. |
| Chart/API payload | LOW | Four scalar KPIs and three empty arrays. |
| Cost/Excel/file calculations | NONE currently | No operational reads or loops. |
| External CDN startup | MEDIUM availability risk | ECharts, Bootstrap, and Font Awesome require network; no local fallback for charting. |

### Files loaded/read per page request

At the application/business-data layer, the canonical Profile JSON is consulted to reload the session user and list factories; exact physical read count can vary with store methods/migration/locking. No Dashboard operational file is read. Templates and static resources follow normal Flask/browser loading. Each Analyze click causes another current-user load plus registry lookup only when a factory is supplied; the no-factory branch performs authorization on the user already loaded.

### Freshness

- User/factory/grant data is read live from the Profile store per request; there is no Dashboard cache or startup snapshot.
- Factory list changes require a browser page reload.
- KPI/chart/table data never becomes fresher because it is constant code, not persisted/generated output.
- Changes in `cost_calculation`, BOMs, materials, category weights, production predictions, or factory files cannot appear on Dashboard.
- User action needed today: reload for registry/access changes; click Analyze for the same empty response. There is no manual refresh button, polling, WebSocket, background generation, or calculated-result store.

## 19. Dependencies on Other Modules

| Module | Dependency | Data/Service Used | Required? | Coupling Level |
|---|---|---|---|---|
| `cost_calculation` | None in active Dashboard | No API, route, or `cost_aggregator` call | No | None |
| `desk` | Navigation links into Dashboard only | `url_for('dashboard.dashboard')`; shared access-derived navigation | No data dependency | Low |
| `factory_parameters` | Shared canonical factory identity indirectly, not module code/data | `FactoryService`/Profile registry; no factory operational files | Factory registry support required, feature module not required | Low |
| `general_parameters` | None | No material-cost data | No | None |
| `product` | UI appears to need hierarchy options, but no working dependency; does not call existing `/api/product_options` | None currently | No current data path | Intended/unknown |
| `profile` | Canonical profile store and authorization architecture via shared utilities | current user, grants, factories | Yes as infrastructure; no profile blueprint call | Medium infrastructure coupling |
| `auth` | Authentication helper import only; `auth` is internal and not a grantable Dashboard module dependency | `login_required`, `get_profile_store` | Yes as internal support | Low/explicit |

Legitimate support dependencies are Flask/Jinja, `utils.auth`, `utils.factory_service`, `utils.profile_authorization`, `utils.localization`, shared templates/static CSS/JS, and browser ECharts.

## 20. Desk Integration

**FACT:** `modules/desk/routes.py:workdesk()` only renders `templates/desk/workdesk.html`. Desk does not import Dashboard code, call `/api/cost_analysis`, embed KPIs/charts/tables, or pass Dashboard-derived data.

**FACT:** Desk and the shared sidebar conditionally render a Dashboard navigation card/link using `module_navigation`. `desk`'s mandatory READ baseline does not make that flag true for `dashboard`; ordinary users with `dashboard = NONE` see no Dashboard shortcut and direct access receives 403.

**Security conclusion:** A Desk-only user receives no Dashboard-derived business data through Desk. The only relationship is authorization-filtered navigation. No leakage via Desk was found.

## 21. Module Registry and 403 Integration

### Registry

The exact canonical registry contains seven grantable IDs:

`cost_calculation`, `dashboard`, `desk`, `factory_parameters`, `general_parameters`, `product`, `profile`.

The active Dashboard consistently passes lowercase `dashboard` to the blueprint, factory service, authorization resolver, registry, navigation map, and URL endpoint. `auth` is explicitly internal/not grantable.

Repository searches for `DASHBOARD`, `Dashboard`, and `dashboard_module` found:

- Uppercase `DASHBOARD` in a route comment describing the action; harmless prose, not an ID.
- Title-case `Dashboard` in English documentation/prototype labels, test class/name prose, CSS class names such as `dashboard-card`, and template commentary; harmless display/style terminology.
- No active `dashboard_module`, `DASHBOARD_MODULE`, `MAIN_DASHBOARD`, or `ANALYTICS_DASHBOARD` authorization ID.
- Profile-store migration may normalize uppercase spelling of a real known module ID to canonical lowercase, but aliases remain invalid.

### 403 integration

- Page denial via `abort(403)` receives the custom Persian RTL `errors/403.html`, maintains HTTP 403, and chooses a safe accessible fallback.
- Page denial with API/JSON/XHR semantics or `Accept: application/json` receives generic JSON from `app.py`.
- Global API denial returns its own Persian JSON `{error: ...}`.
- Factory authorization/inactive denial returns its own exception-derived Persian JSON and 403; unknown factory returns exception-derived JSON and 404.
- The Dashboard frontend discards these JSON messages and alerts only `Failed to fetch data`.

## 22. Security Review

| Finding | Severity | Evidence/current exposure |
|---|---|---|
| Factory ID manipulation fails closed | Positive control | `FactoryService.require_access` checks canonical identity, active status, exact `dashboard` factory grant before response. |
| Direct API bypass fails closed | Positive control | Both routes use `login_required`; global and factory action scopes are checked separately. |
| Latent DOM XSS in detail/filter rendering | **HIGH if real data is connected; LOW current exploitability** | `innerHTML` receives row factory/category/subcategory/product and future filter API values without escaping. Current report arrays are empty and category seeds fixed. |
| Existence/active-state disclosure | LOW–MEDIUM | 404 unknown versus 403 inactive/inaccessible, with raw service exception messages in factory API. IDs are expected stable identifiers but threat model is undocumented. |
| UI trusts response shape | MEDIUM availability/integrity | No schema validation; missing arrays/keys produce client exceptions. |
| CSV formula injection/escaping | MEDIUM if user-controlled exports arrive | Text fields quoted but quotes are not doubled; leading `=`, `+`, `-`, `@` are not neutralized. Current rows empty. |
| Path traversal | None found | Factory query is never interpolated into a path; registry lookup is exact. No file parameter exists. |
| Unsafe Jinja rendering | None found in active context | `filter_options|tojson` performs safe JSON/script escaping; ordinary autoescape applies. Risk begins only after JS converts values to HTML strings. |
| Cross-factory data exposure | None currently | No business data; exact factory check blocks B from A-only user. Global action is separate. |
| Desk leakage | None found | Desk does not load Dashboard data and hides link independently. |
| Error/internal filesystem leakage | Low in Dashboard-specific code | API exposes service messages but no paths. Uncaught store exceptions could become generic server errors/log tracebacks depending on Flask mode. Production debug defaults off. |
| Third-party CDN dependency | MEDIUM supply/availability | Unpinned minor ECharts CDN and external UI libraries lack SRI/local fallback. |
| CSRF | Not applicable to current Dashboard server operations | Both endpoints are GET/read-only; no mutation. Global application lacks dedicated CSRF, relevant only if Dashboard writes are later added. |

**Do not interpret the currently empty payload as proof that future data code will be safe.** The access check is a sound boundary, but future loaders must consume only the validated factory and must not trust category/product query values as paths or authorization evidence.

## 23. RTL / Persian / Jalali / Responsive Behavior

### Current implementation

- `templates/base.html` sets `<html lang="fa" dir="rtl">`; page labels, alerts, KPI/chart/table text, and CSV headings in the active template are Persian.
- Numbers use `toLocaleString('fa-IR')`; currency appends `ریال`; percentages append Persian percent sign `٪`.
- ECharts reads the shared IRANSansX CSS font stack into `APP_FONT_FAMILY` and applies it to global/chart/title/tooltip/axes/labels.
- Dashboard grid is four KPI columns and 2:1 charts on desktop, collapsing both to one column at `max-width: 768px`.
- Bootstrap filter columns use `col-md-3`; table uses responsive horizontal scrolling; charts resize on the window event.
- No date exists in Dashboard data. Shared header date is Jalali formatted; policy helpers are globally available.

### Likely issues

- ECharts canvas/SVG and tooltip overlays have no explicit RTL direction or alignment; mixed Persian/numeric/category strings may order unexpectedly.
- Rotated 30-degree Persian X labels and always-on pie labels may collide with long values; there is no truncation/overflow strategy.
- Fixed 400px chart boxes may be tall on phones and do not observe container-only resizes (only window resize).
- Multi-select `size=3` controls are harder to discover/use on touch devices and provide no instruction about multi-selection.
- Tabs use Bootstrap 4 data attributes against Bootstrap 5.
- Buttons rely partly on icons loaded externally; textual labels remain present, which is a useful fallback.
- Chart canvases lack ARIA role/description and there is no accessible textual empty state; the table could be an eventual alternative but is empty.
- `lang="fa"` is close but not the more specific `fa-IR`; application context defines locale but base does not interpolate it.
- CSV has no BOM, which can affect Persian text detection in some spreadsheet software.

No screenshot or visual snapshot was produced, per scope.

## 24. Configuration and Constants

| Constant/configuration | Location | Value/purpose |
|---|---|---|
| Blueprint/module ID | `modules/dashboard/routes.py` | `dashboard` |
| Routes | same | `/dashboard`, `/api/cost_analysis` |
| Category seed | `dashboard()` | کاتد، آند، الکترولیت، جداکننده، بسته‌بندی |
| KPI empty defaults | `cost_analysis()` | 0, 0, 0, `—` |
| Breakdown defaults | same | Three empty arrays |
| Factory query key | same/template | `factory` |
| Other query keys | template only | repeated `category`, `subcategory`, `product` |
| Missing filter route | template | `/api/filter_options` |
| Currency/locale | template helpers | `fa-IR`, 2 decimals, `ریال`; integer max 0 decimals |
| CSV | template | `text/csv`; `cost_breakdown.csv`; Persian five-column header |
| Chart library | template | `https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js` |
| Chart sizes/layout | inline CSS | 400px; 2fr/1fr; mobile breakpoint 768px |
| Bar style | chart option | `#5470c6`; X label rotate 30 |
| Pie style | chart option | inner/outer radius 40%/70% |
| Font | template/shared CSS | computed `--app-font-family`, fallback IRANSansX/Tahoma/sans-serif |
| Profile store path | `utils.auth:get_profile_store` | environment/config keys beginning `APP_DATA_`; canonical instance fallback |
| Session/security | `app.py` | `APP_SECRET_KEY`, `APP_COOKIE_SECURE`, HttpOnly, SameSite=Lax |
| Date windows/time thresholds | N/A | None |
| Dashboard environment variables/cache/feature flags | N/A | None |

The second Font Awesome kit loaded in the Dashboard template duplicates the Font Awesome stylesheet loaded by base and uses a remote kit identifier. No Dashboard config object centralizes these values.

## 25. Existing Tests and Coverage Gaps

The repository primarily uses `pytest`; `test_iransans_font_setup.py` is written with `unittest` but is pytest-discoverable.

### Related coverage found

| Test file | Relevant coverage |
|---|---|
| `tests/test_friendly_forbidden.py` | `/dashboard` denied page, safe fallback, JSON Accept behavior, non-disclosure in generic 403 |
| `tests/test_mandatory_desk_access.py` | Desk-only active user sees no Dashboard link and direct `/dashboard` gets 403 |
| `tests/test_module_registry.py` | Exact seven IDs, `dashboard` present, aliases/auth excluded, scopes/access serialization |
| `tests/test_profile_access_model.py` | Top-admin Dashboard access, default USER denial, invalid Dashboard grants |
| `tests/test_authorization_enforcement.py` | Hierarchy, top-level roles, exact module/factory/scope separation |
| `tests/test_iransans_font_setup.py` | Active Dashboard ECharts uses shared font variable |
| `tests/test_profile_frontend_refactor.py` | Exact grantable set and safe profile access-manager DOM, indirectly registry-related |
| `tests/test_audit_history.py` | Canonical Dashboard module ID in grant-change normalization, not route behavior |

### Major gaps

- No dedicated Dashboard test file.
- No success-route test for GLOBAL READ, factory-only READ, either top-level role, accessible list contents, inactive factories, or zero factories.
- No `/api/cost_analysis` success-contract, unauthenticated, global denial, invalid factory 404, inactive/inaccessible 403, or Factory A/B manipulation route test.
- No assertion that category/product query filters are ignored or intended to work.
- No test detects the nonexistent `/api/filter_options` endpoint.
- No KPI formula/data test (because none exists), chart payload test, CSV test, frontend DOM/XSS test, responsive test, ECharts failure test, or end-to-end browser test.
- No test reconciles documentation's GLOBAL-only page policy with actual mixed-scope admission.
- No test covers post-analysis empty state or accessible error messaging.

## 26. Code Quality and Technical Debt

### Inventory

- `templates/dashboard/dashboard.html` is a 447-line mixed-responsibility file containing markup, 74 lines of CSS, external dependencies, API orchestration, formatting, chart configuration, table generation, and export.
- Repeated request parameter construction exists in `loadSubcategories`, `loadمحصولs`, and Analyze.
- Repeated option HTML generation and unsafe `innerHTML` exist.
- Two unreferenced Dashboard templates duplicate KPI/chart concepts and expect obsolete context.
- Hard-coded categories, currency, endpoint strings, colors, heights, breakpoints, API response defaults, and CSV schema are spread across route/template.
- Mixed-language function identifiers and commented-out sensitivity production markup remain.
- No stale TODO marker was found, but comments explicitly call sensitivity a next-phase placeholder.
- No unused Python import was identified in `modules/dashboard/routes.py`; `modules/dashboard/__init__.py` is empty.
- `request` filters beyond factory are built but ignored by backend, and the filter endpoint is dead/missing integration.

### Prioritized technical debt

| Priority | Issue | Evidence / affected code | Consequence | Recommended future direction (not implemented) |
|---|---|---|---|---|
| P0 | Latent DOM XSS once live data is connected | `renderDetailTable`, `loadSubcategories`, `loadمحصولs` use unescaped `innerHTML` | User-controlled hierarchy values could execute script | Build nodes with `textContent`; validate response schema; add security tests |
| P0 | Intended filter endpoint absent | Active template fetches `/api/filter_options`; no route exists | Core dependent filters fail on every change | Decide canonical product-option service and authorize every factory-scoped query |
| P0 | Intended authorization policy ambiguous | Page admits factory-only user; docs state GLOBAL READ | Future changes may over-deny or overexpose shell/global action | Product/security owner must codify page-vs-action scopes and test them |
| P1 | Dashboard has no analytical data | `cost_analysis` returns fixed empty contract | Page cannot answer cost questions; zeros may be mistaken for real results | Define canonical source/freshness and distinguish “not calculated” from zero |
| P1 | Empty/error UX is misleading | Blank charts/table; no loading; generic alert; “none defined” conflates access | Users cannot diagnose missing data/access/integration | Add distinct authorized empty/configuration/error states after product decisions |
| P1 | CSV construction is unsafe/fragile for future live text | Direct concatenation without quote/formula handling/BOM | Corrupt CSV or spreadsheet formula execution | Reuse an escape/export helper and add Persian spreadsheet tests |
| P1 | Inline monolith and duplicate prototypes | Active 447-line template plus two obsolete alternates | Divergent behavior/localization and difficult review/testing | Confirm prototypes are unneeded, then separate assets/components without changing contracts |
| P1 | External chart dependency has weak resilience | Unpinned `@5`, no SRI/local fallback | Dashboard visualization unavailable/offline; supply-chain surface | Vendor/pin according to deployment policy and show fallback table/state |
| P2 | Race/redundant filter requests | Two async requests per factory/category event, no cancellation | Out-of-order options and needless load when API exists | Centralize dependent-filter refresh with sequencing/debounce |
| P2 | Page/API error contracts differ | Custom exception bodies vs global 403 JSON | Frontend cannot offer consistent safe messages | Standardize a non-disclosing machine contract while retaining correct statuses |
| P2 | ECharts and table lack accessibility semantics | Chart divs have no ARIA/text alternative; empty table only | Screen-reader users receive poor context | Add semantic summaries/accessible alternatives after chart requirements settle |
| P2 | Bootstrap tab attribute mismatch | `data-toggle` under Bootstrap 5 | Future restored sensitivity tab may not switch | Use the shared framework's supported attributes when feature is activated |
| P3 | Mixed identifier language/comment residue | `loadمحصولs`, `renderدسته...`, next-phase markup | Searchability/consistency cost | Normalize internal names only in a dedicated behavior-preserving cleanup |
| P3 | Fixed chart geometry/label strategy | 400px boxes, rotated/always-on labels | Mobile/long-Persian-label polish issues | Test target breakpoints and configure adaptive labels |

No recommendation above is an implementation roadmap or a decision to redesign.

## 27. Reusable Components/Services Elsewhere in the Repository

Potential later reuse (none adopted in this audit):

- `FactoryService`: canonical public factory selector values, active filtering, exact access enforcement, and `operational_key` resolution.
- `utils.profile_authorization`: `has_access`, `get_effective_level`, top-level role checks, and centralized hierarchy.
- `utils.module_registry`: exact IDs, labels, scopes, Desk minimum policy.
- `utils.localization`: `display_value`, Persian digits, Jalali formatting/parsing, message catalog.
- `window.JalaliDate` in `static/js/jalali-date.js`: future time filters/display.
- Shared `templates/base.html`, sidebar/header, `static/css/style.css`, and IRANSansX font variables.
- `app.py` content-aware 403 handler and `templates/errors/403.html`: safe page/API denial pattern.
- `modules/product/routes.py` `/api/product_options`: existing hierarchy/options capability requiring careful contract and Dashboard authorization review before reuse; it is not interchangeable by assumption with the missing endpoint.
- Product selection controls/templates: examples of factory/category/subcategory/product relationships and selectors.
- `modules/cost_calculation/routes.py` and `utils.cost_determiners`: authoritative current cost calculation entry points/business logic. Reuse should avoid duplicating formulas and must preserve per-factory checks.
- Cost calculation client-side CSV behavior: another export implementation to compare, not necessarily a safe shared abstraction.
- Factory-parameter “unconfigured factory” handling: a conceptual empty/configuration state supported by canonical registry integration.
- Profile frontend's DOM element helper and submission/error patterns: demonstrably avoids `innerHTML` in its access manager and may inform safe rendering.
- Test fixtures/patterns in authorization/factory/403 suites for constructing stores, users, grants, and Flask clients.

No general chart helper, reusable dashboard card macro, shared empty-state component, pagination component, or generic factory-select Jinja macro was found.

## 28. Current Dashboard Responsibilities

| Responsibility group | What Dashboard currently owns | Placement observation |
|---|---|---|
| Navigation/context | Blueprint endpoint; page title; entry links elsewhere | Normal feature responsibility |
| Filtering | Factory/category seeds and browser cascade orchestration | Cascade is incomplete; category constants may be misplaced relative to product domain |
| Data retrieval | Profile-store factory list; empty API contract | No analytical retrieval exists |
| Transformations | Public factories delegated to service; JS maps arrays to options/charts/rows | Presentation mapping is appropriate; unsafe DOM mechanism is debt |
| KPI calculations | Only fixed zeros/em dash | No core calculation duplicated |
| Chart preparation | Entirely browser-side ECharts option creation | Presentation responsibility, tightly coupled inline |
| Rendering | Jinja shell, DOM updates, ECharts, table, CSV | Broadly expected, but monolithic template |
| Access control | Route-local page condition; API factory/global checks; service validation | Correctly server-side, but intended page scope needs reconciliation |
| State | DOM selection, `currentData`, ECharts instances | Ephemeral, page-only |
| Formatting | Persian/Rial numeric functions, tooltip/labels, CSV headings | Appropriate presentation concern; duplicate/non-centralized |

The active Dashboard does **not** own or duplicate BOM costing, factory allocation, material prices, production prediction, transactional persistence, time aggregation, or historical analytics.

## 29. Potential Improvement Opportunities

These are candidates only, grouped by concern; they deliberately do not define phases.

| Group | Current issue | Potential benefit | Complexity | Dependencies | Risk |
|---|---|---|---|---|---|
| Information architecture | Page exposes nonfunctional cascade and hidden sensitivity pane | Align visible structure with actual supported business questions | M | Human KPI/report priorities | Removing/adding affordances before decisions could misstate scope |
| KPI design | Four placeholders have unresolved semantics | Trustworthy, decision-oriented metrics and explicit no-data semantics | L | Canonical transaction/cost result source, formula owners | High business correctness risk |
| Charts | Blank charts, no legend/empty annotation/RTL semantics | Understandable and accessible comparisons | M | Defined metrics/units/dimensions | Misleading aggregation/scale |
| Filtering | Missing endpoint; ignored filters; races | Functional, predictable product hierarchy exploration | M–L | Product data contract and per-factory authorization | Cross-factory leakage if joined incorrectly |
| Factory experience | “All” available to users lacking GLOBAL; no-access message conflation | Clear separation of global/factory reports and setup state | S–M | Policy decision on default/global aggregation | Incorrect default may expose or over-deny |
| Performance | Repeated failed requests/recreated charts/innerHTML loop | Lower request/render load once data grows | S–M | Working data contract and representative volumes | Premature optimization without dataset |
| Error/empty states | Generic alert and zeros mask unavailable data | Honest, actionable user feedback | M | Error taxonomy and freshness contract | Leaking sensitive factory detail |
| Responsive UX | Fixed charts/multi-select touch friction | Better phone/tablet operation | M | Target devices and browser matrix | Visual regressions without manual review |
| Accessibility | Chart-only visuals and weak semantics | Keyboard/screen-reader usability | M | Approved chart/table design | Incomplete ARIA could worsen experience |
| Maintainability | Inline 447-line file and stale alternates | Testable assets, reduced divergence | M | Decide disposition of prototypes | Accidental behavior/API changes during extraction |
| Testing | No direct route/API/frontend Dashboard suite | Prevent access, contract, and rendering regressions | M | Final policy/contracts | Tests may freeze placeholder behavior if written prematurely |
| Security | Unsafe HTML/CSV future sinks and inconsistent denial bodies | Safe live-data integration and reduced disclosure | M | Data provenance and common response pattern | Sanitization must not corrupt Persian values |

## 30. Product Decisions / Questions Requiring Human Input

Exactly **12 unresolved product questions** remain after code inspection:

1. What primary business decision should the Dashboard support (product cost monitoring, factory comparison, cost-driver analysis, or something else)?
2. What are the authoritative definitions/formulas for total cost, average cost per product, product count, and top cost driver, including aggregation, deduplication, ties, and units?
3. What canonical persisted or live dataset represents “calculated costing,” and when is a cost considered current/valid?
4. Should `/dashboard` itself require GLOBAL READ, allow any factory READ as current code does, or expose different shells for the two scopes?
5. Should “all factories” mean global aggregation, comparison without aggregation, or no filter—and which roles/grants may use it?
6. What should the default factory be for a multi-factory user, and should selection persist across page reloads/sessions?
7. Are the five category constants authoritative, or must categories/subcategories come dynamically from product/factory configuration?
8. Are products globally identified with factory-specific configurations, and what identity/key should Dashboard joins use when a product occurs in multiple factories?
9. What time horizon, grain, timezone, and Jalali period/date interaction are required, if any?
10. Which drill-downs, rankings, comparisons, and export fields are required, and should exported values be human-readable Jalali/Persian or canonical machine data?
11. What distinguishes “zero cost,” “not calculated,” “factory unconfigured,” “no matching products,” and “source unavailable” for users?
12. What freshness expectation applies—live calculation, stored snapshot, explicit refresh, scheduled generation, or eventual consistency—and who may trigger recalculation?

## 31. Recommended Areas for Further Investigation

These are evidence gaps to resolve before planning implementation, not implementation phases:

- Obtain product-owner/accounting definitions for the four KPI names and desired Dashboard decisions.
- Identify whether cost results have or need a canonical persisted snapshot; current cost APIs calculate on request and Dashboard does not consume them.
- Reconcile the route's mixed-scope admission with the GLOBAL-only page row in authorization documents and define “all factories.”
- Examine representative production data volume and completeness without copying sensitive `Data/` records into design artifacts.
- Define stable joins among canonical factory ID, operational key, product identity, category/subcategory, BOM, and cost output.
- Decide whether existing `/api/product_options` can safely serve Dashboard or whether a separately authorized read model is necessary; do not merely rename the current missing URL.
- Define time semantics, application timezone, aggregation calendar, Jalali user interaction, and historical retention.
- Establish an API error/empty-state taxonomy that preserves the existing non-disclosing 403 guarantee.
- Threat-model user-generated factory/product/category strings before any live DOM/CSV rendering.
- Validate responsive/RTL/ECharts behavior manually on agreed desktop, tablet, and mobile targets when a perceptible UI change is eventually authorized.
- Benchmark only after a representative analytical source and expected factory/product/history sizes are known.
- Resolve the intended retention or removal of the two unreferenced Dashboard prototypes and update historical documentation after behavior is deliberately chosen.

## 32. Appendix — Key File and Function Reference

| File | Symbol/area | Dashboard relevance |
|---|---|---|
| `modules/dashboard/routes.py` | `dashboard_bp` | Blueprint ID `dashboard` |
| same | `dashboard()` | Page authorization, accessible factories, static categories, Jinja render |
| same | `cost_analysis()` | Factory/global authorization and fixed empty JSON contract |
| `templates/dashboard/dashboard.html` | filter/card/chart/table markup | Entire active Dashboard UI |
| same | `populateInitialFilters()` | Initial factory/category DOM options and no-factory state |
| same | `loadSubcategories()` | Calls nonexistent `/api/filter_options` |
| same | `loadمحصولs()` | Calls nonexistent `/api/filter_options` |
| same | Analyze listener | Builds query, fetches cost API, renders or alerts |
| same | `renderDashboard()` | Coordinates KPIs/charts/table |
| same | `renderدستهBarChart()` | Category bar ECharts option |
| same | `renderزیردستهPieChart()` | Subcategory pie ECharts option |
| same | `renderDetailTable()` | Unsafe HTML row rendering |
| same | CSV listener | Client-only export |
| same | `formatNumber/Integer/Currency()` | `fa-IR`/Rial presentation |
| `templates/dashboard/dashboard_newer.html` | prototype | Unreferenced, expects `dashboard_data` |
| `templates/dashboard/dashboard copy.html` | prototype | Unreferenced, expects `dashboard_data` |
| `app.py` | blueprint registration | Registers routes without prefix |
| same | `inject_user()` | User/nav/Jalali/template shared context |
| same | `forbidden()` | Content-aware custom 403 UX |
| `utils/auth.py` | `get_profile_store()` | Configured canonical Profile store |
| same | `login_required()` | Session user load, active and forced-password gates |
| `utils/factory_service.py` | `get_accessible_factories()` | Active/access-filtered selector data |
| same | `require_access()` | Exact factory existence/active/grant enforcement |
| `utils/profile_authorization.py` | `get_effective_level`, `has_access` | Hierarchical GLOBAL/FACTORY permission policy |
| same | `is_top_level_admin` | Peer implicit-full-access roles |
| `utils/module_registry.py` | `MODULE_REGISTRY` | Exact `dashboard` ID and mixed scopes |
| `templates/base.html` | document/shared assets | Persian RTL shell, responsive viewport, global JS/CSS |
| `templates/components/sidebar.html` | navigation tuple | Conditional Dashboard link using canonical ID |
| `modules/desk/routes.py` / `templates/desk/workdesk.html` | Desk page/card | Navigation only; no Dashboard data reuse |
| `modules/product/routes.py` | `/api/product_options` | Existing but unused product hierarchy endpoint |
| `modules/cost_calculation/routes.py` / `utils/cost_determiners.py` | cost endpoints/formulas | Authoritative costing area, not currently called |
| `tests/test_friendly_forbidden.py` | Dashboard denial assertions | Page/JSON 403 integration |
| `tests/test_mandatory_desk_access.py` | Desk-only user assertions | No Dashboard inheritance/leakage |
| `tests/test_iransans_font_setup.py` | chart font assertion | Only direct active-template Dashboard presentation test |

### Final validation checklist

- Confirmed all seven relevant grantable modules are referenced only by their real IDs: `cost_calculation`, `dashboard`, `desk`, `factory_parameters`, `general_parameters`, `product`, `profile`.
- Confirmed the technical Dashboard ID is always documented as `dashboard`; title-case/uppercase occurrences are identified only as prose/display/comment/migration spelling.
- Confirmed no implementation or application data was modified.
- Confirmed no screenshot/image was created.
- Confirmed all meaningful Dashboard module files, all three Dashboard templates, both owned routes, supporting access/factory code, active data sources, tests, and related module boundaries were covered.
- Confirmed unresolved formulas, hierarchy, policy, time, source, and product expectations are explicitly marked rather than inferred.
