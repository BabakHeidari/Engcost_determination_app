# fa-IR Persian and RTL Localization Audit

## Audit scope

This audit covers the current Flask application surfaces visible to end users and administrators, including Jinja templates, page-local JavaScript strings, shared static JavaScript, CSS/layout assumptions, Flask JSON/flash messages, dashboard chart/CSV strings, and existing documentation notes about print/PDF/export behavior. This is an audit and planning artifact only; no application code, templates, styles, JavaScript behavior, routes, APIs, data files, schemas, or business logic were changed.

Primary inspected areas:

- Shared shell: `templates/base.html`, `templates/components/header.html`, `templates/components/sidebar.html`, `static/css/style.css`, `static/js/main.js`.
- Auth/workdesk/profile: `templates/auth/login.html`, `templates/desk/workdesk.html`, `templates/profile/profile.html`, `modules/auth/routes.py`, `modules/profile/routes.py`.
- Material/factory/product/cost/dashboard templates and route messages under `templates/**` and `modules/**/routes.py`.
- Legacy/alternate templates still present in the repository, because they may be reused or linked later: `templates/dashboard/dashboard copy.html`, `templates/dashboard/dashboard_newer.html`, `templates/desk/workdest_old.html`, `templates/product/prod_sel_new.html`, `templates/cost/calculation old.html`, `templates/cost/working old.html`.
- Static layout risks in `static/css/style.css` and page-local `<style>` blocks.
- Active exports found in source: client-side CSV downloads in cost calculation and dashboard. No active email, PDF generation, server-side report export, `window.print`, or `jsPDF` route was found in active source during this audit.

## Localization policy recommended for this application

### Recommended decisions

1. **Labels and prose:** use Persian (`fa-IR`) labels and messages by default, with RTL layout. Keep short unavoidable technical acronyms in Latin script where they are the industry norm.
2. **Numerals:** use **Latin numerals for editable technical/cost inputs and tabular cost values** in phase 1, because current parsing depends on `parseFloat`, `Number`, HTML `input[type="number"]`, CSV output, JSON contracts, and Excel-like data. Use Persian numerals only for decorative/display-only counts after a later formatting layer is introduced.
3. **Dates:** display dates as **Jalali/Shamsi for users** while preserving stored/transport dates as ISO/Gregorian. The UI should explicitly format date/time with a single helper so `last_login`, `last_modification_date`, dashboard timestamps, and history entries do not diverge.
4. **Currency:** display Iranian Rial consistently as `ریال`/`IRR`, but do not convert stored currency codes or API keys. Existing hard-coded USD currency formatting in factory/cost/dashboard areas should be reviewed before translation because it may be semantically wrong for Iranian-cost use.

### Technical terms needing product-owner terminology decisions

Do not assume final Persian accounting/manufacturing terminology without stakeholder confirmation. Suggested alternatives:

| English term | Candidate Persian labels |
|---|---|
| Cost Determination System | سامانه تعیین بهای تمام‌شده / سامانه محاسبه هزینه |
| Cost Calculation | محاسبه هزینه / محاسبه بهای تمام‌شده |
| General Parameters | پارامترهای عمومی / تنظیمات عمومی |
| Factory Parameters | پارامترهای کارخانه / تنظیمات کارخانه |
| Product Configuration | پیکربندی محصول / تنظیمات محصول |
| BOM | فهرست مواد (BOM) / صورت مواد و قطعات (BOM) |
| Recipe | دستور ساخت / فرمول ساخت |
| Cost Driver | عامل هزینه / محرک هزینه |
| Subfield | زیرحوزه / بخش فرعی |
| Category | دسته / گروه |
| Subcategory | زیردسته / زیرگروه |
| Capacity | ظرفیت / ظرفیت تولید |
| Production Prediction | پیش‌بینی تولید / برآورد تولید |
| Recyclability | بازیافت‌پذیری / قابلیت بازیافت |
| Lost percentage | درصد ضایعات / درصد اتلاف |
| Material | ماده / متریال |
| Factory Admin | مدیر کارخانه / سرپرست کارخانه |
| Official Admin | مدیر رسمی / مدیر سازمانی |

## Translation boundaries

### Text that must be translated

Translate all visible labels, headings, navigation items, button labels, placeholders, pagination text, alert/confirm messages, validation errors, empty states, chart titles/legends/axis labels/tooltips, CSV headings intended for users, modal titles/actions, table display headers, and Flask flash/JSON messages surfaced to the UI.

### Technical terms that may remain English

The following may remain English or bilingual based on product-owner preference:

- Acronyms and standards: `BOM`, `CSV`, `JSON`, `API`, `KPI`, `PDF`, `Excel`, `IRR`, `USD`, `EUR`, currency codes, SI unit abbreviations (`kg`, `m`, `L`, `m²`, `m³`).
- Role names while backend roles are unchanged: `IT Admin`, `Official Admin`, `Factory Admin`, `Factory Staff`, but UI labels can show Persian beside stable backend values.
- Product/factory/category names loaded from data files if they are business data rather than UI copy.
- Browser/developer-only console messages can remain English unless shown to users.

### Items that must never be translated/renamed

Do not translate or rename identifiers, field names, routes, JSON keys, database/data values, form names, session keys, API payload keys, function names, Python identifiers, CSS/JS selectors, or integration contracts. Examples observed in source include:

- Routes/endpoints: `/login`, `/logout`, `/workdesk`, `/general_parameters/`, `/save_materials`, `/factory_parameters/`, `/save_factories`, `/save_factory_subfields`, `/product/production_selection`, `/api/product_options`, `/add_product`, `/add_category`, `/add_subcategory`, `/save_bom`, `/cost/cost_calculation`, `/cost/get_cost`, `/cost/get_costs_bulk`, `/dashboard`, `/api/cost_analysis`.
- JSON/API keys and table schema keys: `Product_Name`, `Factory`, `Category`, `Subcategory`, `_order`, `data`, `material`, `unit`, `currency`, `cost_per_unit_in_currency`, `cost_currency`, `lost_percentage`, `recycability_percentage`, `cost_of_material_in_its_currency`, `cost_of_material_in_rial`, `factory name`, `subfield`, `cost`, `percentageofall`, `subject`, `status`, `message`, `error`, `success`.
- Auth/session/internal names: `username`, `password`, `session["user"]`, `last_login`, `user`, `currentUser`, `privileges`, `scope`, `factoryId`, role constants and module keys used by profile JavaScript.
- Data file names and generated file paths under `Data/`, Excel sheet names, and existing application data values unless a separate data-migration task is approved.

## File-by-file inventory of English user-facing strings

### `README.md`

- Contains only the project title `cost_determination_system`. Not an in-app user surface, but if README is localized later, title can be Persian or bilingual.

### `templates/base.html`

- HTML language is `en`; should become `fa-IR` in implementation.
- Default page title: `Cost Determination System`.
- Sidebar toggle accessibility text: `Toggle sidebar`.
- Footer text: `© 2026 Copy Right By B. Heydari`.
- Comments are English but not user-facing. Duplicate script tags and duplicated script content should be addressed separately from localization.

### `templates/components/header.html`

- Header strings: `Welcome,`, `Last login:`, `Time:`, `Logout`.
- Date/time display currently hard-codes `2026-04-21` and uses browser default `toLocaleTimeString()` from `static/js/main.js`, not `fa-IR`.

### `templates/components/sidebar.html`

- Brand/nav labels: `Cost System`, `Work Desk`, `General Parameters`, `Factory Parameters`, `Product Configuration`, `Cost Calculation`, `Dashboard`, `User Profile`.
- Commented legacy nav labels are English; translate if restored.

### `templates/auth/login.html`

- HTML language is `en`.
- Title: `Login | Cost Determination System`.
- Login card likely includes `Cost System Login`, `Username`, `Password`, and sign-in button text.
- Displays Flask flash messages, currently English from `modules/auth/routes.py`.

### `modules/auth/routes.py`

- Flash message: `Invalid username or password`.
- This is server-generated user-facing text and should be translated or returned through a message catalog.

### `templates/desk/workdesk.html`

- Title block: `Work Desk`.
- Welcome panel: `Work Desk`, `Welcome back, ...`, `Last login:`, `Logout`.
- Cards: `General Parameters`, `Set system-wide parameters`, `Factory Parameters`, `Manage factory settings`, `Product Configuration`, `Configure your products and BOM`, `Cost Calculation`, `Calculate product costs`, `Dashboard`, `View analytics and reports`, `User Profile`, `Manage your account`, repeated `Open` buttons.
- Directional arrow icon `fa-arrow-right` should be mirrored or replaced for RTL.

### `templates/desk/workdest_old.html`

- Legacy/old workdesk surface. Audit before deletion or reuse; expected to contain the same workdesk/navigation English labels and should be translated if it remains reachable.

### `templates/general_parameters/general_parameters.html`

- Page/actions: `Back`, `Editable Table`, `Add Row`, `Add Column`, `Save Changes`.
- Search/pagination/status: `Search by first column`, `Showing ... of ... rows`, `Page 1`, `Last modified:`.
- Modals: `Add New Row`, `Edit Row`, `Cancel`, `Add Row`, `Save Changes`.
- JavaScript option labels: currency names such as `IRR - Iranian Rial`, `USD - US Dollar`; unit names such as `Kilogram (kg)`, `No Unit: Currency`, `Metric Ton (t)`, `Piece (pc)`, `Hour (hr)`, `Day (day)`.
- JavaScript-generated UI/alerts to translate: filter labels, editable column labels, delete/edit actions, modal field labels from headers, save success/error alerts, validation messages, confirmation prompts, last-modified formatting, and pagination strings.
- Data column keys must not be renamed; only display labels should be mapped.

### `templates/general_parameters/style_gp.css`

- CSS contains LTR layout assumptions: margins/paddings, `left`/`right`, text alignment, modal action alignment, pagination control direction, and icons. Needs RTL logical-property pass if this stylesheet is active.

### `modules/general_parameters/routes.py`

- JSON status `ok` is contract-like and should not be translated unless a separate display message is added. No user prose beyond status observed.

### `templates/factory_parameters/factories.html`

- Factory directory page likely includes headings/stat cards in English plus JavaScript-rendered table headers.
- JavaScript display strings: column labels based on `factory name`, `manager`, `city`, `address`, `view`; generated header `View`; button `View Details`.
- Stats labels likely include total factories/managers/cities depending on markup.
- Icons/emojis precede English labels; placement must be checked in RTL.
- Do not rename form field `factory name`.

### `templates/factory_parameters/factory_details.html`

- JavaScript-generated labels: `Subfield`, `Cost`, `Percentageofall`, `Actions`, `Details`.
- Currency display uses `Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })`; this is a localization and possibly business-risk item.
- Percentage display appends `%` with Latin numerals and LTR ordering.
- Additional tables for category weights/production prediction likely generate button/status text and headings; all visible table titles, save buttons, and errors should be mapped through labels.

### `templates/factory_parameters/factory_subfield.html`

- Page/table JavaScript strings: `Subject`, `Cost`, `Actions`, `Delete column`.
- Currency display uses `en-US` and `USD`.
- Header editing strips non-Latin letters with `/[^a-zA-Z\s]/g`, which would break Persian editable column names. This is a high-risk RTL/localization bug if translated headers become editable data keys.
- Delete/add/save/filter/pagination/modal strings in the rest of the template should be translated. Preserve schema keys `subject` and `cost`.

### `modules/factory_parameters/routes.py`

- JSON statuses: `success`. Treat as API contract values, not localized display copy, unless UI maps them to localized messages.
- Commented historical error messages are English but inactive; translate if code is restored.

### `templates/product/production_selection.html`

- Main product page: `Product Management`, likely `Products`, `Add Category`, `Add Subcategory`, `Add Product`, search placeholder `Search by product name...`.
- Filters/buttons: `Factory`, `Category`, `Subcategory`, `No products found`, `Previous`, `Next`, `View`, filter counters, active filter chips, product count text `product/products`, pagination showing text.
- Add product modal: `Add New Product`, `Product Name *`, `Enter product name`, `Factory *`, `Category *`, `Select Factory First`, `Subcategory *`, `Select Category First`, `Capacity *`, `Enter capacity`, `Cancel`, `Save Product`.
- Add category modal: `Add New Category`, `Select Factory`, `Category Name *`, `Enter category name`, `Save Category`.
- Add subcategory modal: `Add New Subcategory`, `Select Category`, `Subcategory Name *`, `Enter subcategory name`, `Save Subcategory`.
- JavaScript messages: `Select`, `No categories available`, `No subcategories available`, `Select Subcategory`, `Error:`, `Unknown error`, dynamic success text from server, empty/filter/reset messages, notification text.
- Directional pagination arrows `← Previous` and `Next →` need RTL review.
- Do not translate payload keys `product_name`, `factory`, `category`, `subcategory`, `capacity` or backend JSON keys.

### `templates/product/prod_sel_new.html`

- Alternate product selection page: `Back`, `Product Table`, `Search Product_Name...`, dropdown labels `Factory`, `Category`, `Subcategory`, `Previous`, `Next`, `View`, dynamic `Page X of Y`.
- Uses raw field name `Product_Name` in placeholder; display can be Persian, key must remain unchanged.

### `templates/product/product_page.html`

- BOM editor strings: `BOM / Recipe for:`, `Search materials...`, `Add Column`, `Add Row`, `Save`/`Save Changes`.
- JavaScript prompts/alerts/confirms: `Column name?`, `A column with this name already exists!`, `Cannot remove core column ...`, `Delete column ...?`, `Delete this row?`, `Row N: lost_percentage must be less than 100%`, `Row N: recycability_percentage (...) must be less than lost_percentage (...)`, `Save changes?`, `BOM saved successfully ✅`, `Error saving BOM`.
- Core column names are shown directly from data (`materials`, `unit`, `currency`, `cost_per_unit_in_currency`, `usage`, etc.). Implement display-label mapping rather than renaming keys.
- Material names/options are data values; do not translate unless data localization is explicitly in scope.

### `templates/product/configuration.html`

- Product configuration page should be treated as user-facing if reachable. Translate headings, labels, forms, buttons, placeholders, and any JavaScript messages. Preserve routes and API payload names.

### `templates/product/archived.js`

- Archived JavaScript may contain old UI strings. Do not prioritize unless included by a template or restored, but translate if reactivated.

### `templates/product/style.css`

- Contains product-page layout assumptions including left/right margins, text alignment, hover translate direction, dropdown positioning, notification placement, modal action alignment, and pagination. Needs RTL pass if used by product templates.

### `modules/product/routes.py` and `modules/product/new routes.py`

- User-facing JSON messages: `All fields are required.`, `Factory and category name are required.`, `Category '...' added successfully.`, `Factory, category, and subcategory name are required.`, `Subcategory '...' added successfully.`
- Exceptions from updater functions are passed through as `message`; those underlying English messages should be audited before exposing in Persian UI.
- API keys/status values should remain stable; UI should translate messages or use message codes.

### `templates/cost/calculation.html`

- Cost calculation UI includes `Back`, product search, dropdown filters, export button, table headings, calculate buttons, loading/status messages, cost result labels, and pagination/filter stats.
- CSS uses `text-align: left`, `left: 0` dropdown positioning, `margin-left`, LTR flex ordering, and hover effects. Needs RTL logical-property pass.
- CSV export likely emits English headings and Latin number/currency formatting; export headers must be deliberately localized or kept English for machine interoperability.
- API data keys `Product_Name`, `Factory`, `Category`, `Subcategory` must not be renamed.

### `templates/cost/calculation old.html` and `templates/cost/working old.html`

- Legacy cost pages. Translate if retained/reachable; otherwise mark as candidates for cleanup. Likely duplicate old search/filter/table/export strings.

### `modules/cost_calculation/routes.py`

- User/API errors: `No JSON payload`, `Expected a list of products`.
- These are API errors. If surfaced in UI, show localized messages client-side while preserving API error keys.

### `templates/dashboard/dashboard.html`

- Page strings: `← Back`, `Battery Manufacturing Cost Dashboard`, `Cost Analysis`, `Filter Data`, `Factory`, `All Factories`, `Category`, `Subcategory`, `Product`, `Analyze Cost`, `Download CSV`, KPI labels `Total Cost`, `Avg. Cost / Product`, `No. of Products`, `Top Cost Driver`, table title `Detailed Cost Breakdown`, table headers `Factory`, `Category`, `Subcategory`, `Product`, `Cost ($)`, empty state `Select filters and click "Analyze Cost" to view breakdown`, `Sensitivity Analysis`, `This section will be implemented next. You'll be able to run what-if scenarios on cost drivers.`
- Chart strings in JavaScript should be translated: category bar chart title/axis names/series name/tooltips, subcategory pie chart title/legend/tooltips, loading/error messages, CSV filename/header labels.
- Chart library ECharts needs explicit RTL tooltip styling and Persian number/date formatting; default canvas/SVG text will not inherit all document direction behavior.

### `templates/dashboard/dashboard_newer.html` and `templates/dashboard/dashboard copy.html`

- Alternate dashboard templates likely contain English KPIs, chart labels, filters, export/download labels, and placeholder text. Translate if reachable or remove in a cleanup task to avoid divergent localization.

### `modules/dashboard/routes.py`

- Sample data uses English category names, KPI/detail labels, filter option names, and cost-analysis structures. Treat sample display labels as translatable seed/demo content; preserve JSON keys.

### `templates/profile/profile.html`

- Page/admin strings: `Back`, `User Profile`, `Loading...`, `Admin Controls`, `Add New User`, `Full Name`, `Enter user's full name`, `Email`, `Assign Role`, `-- Select Role --`, `Assign Factory`, `-- Select Factory --`, `Add New Factory`, `Initial Module Access`, `Select a role to see default privileges`, `Cancel`, `Add User`, `Factory Code`, `e.g., F4`, `Factory Name`, `e.g., Factory Delta`, `Location`, `e.g., Building 4, North Campus`.
- JavaScript constants/user labels: roles `IT Admin`, `Official Admin`, `Factory Admin`, `Factory Staff`; modules `General Parameters`, `Factory Parameters`, `Product Management`, `Cost Calculation`, `Dashboard`, `User Management`; access levels `read`, `write`, `modify`; badges `Live`, `Demo`; labels `Scope`, `Default access levels`, `No default privileges`, `Admin assigned`, `Add User`, `Edit User`, `Save Changes`, `Add New User`, `Add New Factory`, `Save`, `Close`, history labels, warnings.
- Validation/errors: `Enter factory code.`, `Enter factory name.`, `Code exists.`, `Name exists.`, `Failed.`, `Network error.`, `Enter name.`, `Valid email required.`, `Select role.`, `Email already exists.`, `This factory already has an admin. Each factory can have only one admin.`, `Select factory.`, `Factory Admins can only modify Factory Staff module access.`, `Some access levels are restricted based on your privileges.`, `No modules available.`
- Inline styles contain many LTR assumptions (`left:0`, `right:20px`, `border-left`, `padding-right`, `grid-template-columns:1fr 380px`, `justify-content:space-between`, `text-transform:uppercase`, `letter-spacing`). Requires careful RTL visual review.

### `modules/profile/routes.py`

- Most profile API code is commented placeholder. Commented messages include `Cannot create this role` and `Unauthorized`; translate if endpoints are restored.

### `static/js/main.js`

- Time display uses `now.toLocaleTimeString()` without locale; should use `fa-IR` or a central formatter.
- Dynamic BOM-like row placeholder: `Component name`.
- Numeric totals use `.toFixed(2)` and Latin decimal separator. Keep Latin in inputs/technical tables for phase 1; localize display-only values later.

### `static/css/style.css`

- Global RTL risks: mobile sidebar is fixed to `left: 0` and hidden with `translateX(-100%)`; hover moves nav links with `translateX(5px)`; footer and main content assume LTR flow; mobile toggle is inline-styled at bottom-right in `base.html`; padding uses physical `left/right` values.
- Needs a global RTL strategy using `html[dir="rtl"]`, Bootstrap RTL or logical properties, and mirrored sidebar behavior.

### `app.py`

- No major visible copy except app/session context behavior. If error handlers are added later, localize them.

### `utils/**`

- Mostly internal. Avoid translating function names, keys, file names, cost formulas, and data contracts.
- Any exception messages from updater/load/cost helpers that are surfaced directly through JSON should be mapped to localized UI messages rather than translating identifiers inside low-level utilities.

### `Data_Better_Structure/**`

- Contains sample/auth/material/product/factory JSON. Treat as data, not UI copy. Do not translate without an explicit data-localization migration.

## RTL risks

### Sidebar direction

- Current sidebar lives on the left on mobile and slides from the left. For RTL, it should usually live on the right and slide from the right.
- `base.html` uses `flex-lg-row`; for RTL this may keep sidebar before content but visual order needs confirmation.
- Sidebar toggle button is bottom-right; in RTL it may conflict with right-side sidebar. Consider bottom-left or context-aware placement.
- Sidebar nav hover moves links right (`translateX(5px)`), which is visually backward in RTL.

### Bootstrap/flex/grid alignment

- Many templates use Bootstrap classes whose physical direction matters: `text-start/text-end` if introduced, `float-*`, `ms/me` vs `ml/mr`, `justify-content-between`, `d-flex gap-*`, row order, and card icon/text order.
- Inline styles in profile and page-local styles use physical `left`, `right`, `padding-left`, `padding-right`, `margin-left`, `border-left`, and `text-align:left`.
- Use Bootstrap RTL build or a dedicated `dir="rtl"` override layer; avoid one-off fixes.

### Icons/arrows

- Back buttons use `← Back` or `fa-arrow-left`; open buttons use `fa-arrow-right`; pagination uses `← Previous` and `Next →`; chevrons in general parameters point left/right.
- In RTL, previous/next semantics and back/open arrows must be consciously mirrored. Some icons such as logout and chart icons do not need mirroring.

### Table columns

- Many tables render headers directly from JSON keys and assume the first column is the search/display anchor. RTL should not rename keys; instead use display-label maps.
- Numeric/currency columns should stay visually aligned for scanning. Recommended: Persian labels with numeric cells `dir="ltr"` and `text-align: end` or a numeric utility class.
- Sticky/action columns, if added, should appear at the RTL-appropriate edge.
- Editable headers in factory subfield currently reject Persian letters; this must be fixed before translating editable table headers.

### Numeric inputs

- HTML number inputs and JavaScript parsing (`parseFloat`, `Number`, `.toFixed`) expect Latin digits and dot decimals.
- Persian numerals in editable inputs would break calculations without a normalization layer.
- Recommendation: Latin digits in inputs and CSV/Excel; optional Persian digits in display-only summaries later.

### Charts and tooltips

- ECharts labels, legends, axis names, series names, and tooltips are configured in JavaScript and will not be localized by `dir="rtl"` alone.
- Tooltips need RTL text alignment, `fa-IR` number formatting, and bidi isolation for mixed Persian/Latin product codes/currency.
- Bar/category ordering may need review so reading flow feels natural in RTL.

### Pagination

- Text such as `Showing 1-10 of 50 rows`, `Page 1`, `Page X of Y`, `Previous`, `Next` appears in several templates.
- Button order and chevrons should be reversed for RTL, while page numbers can remain ascending left-to-right or use a locale decision; manual review is required.

### Modal alignment

- Modal headers use `justify-content: space-between` and close buttons placed in LTR order. RTL modals should place close icons where expected and align field labels right.
- Modal action rows currently use `justify-content:flex-end`; in RTL the primary/secondary button order should be reviewed.
- Inline profile modals and product custom modals are high risk because styles are embedded and physical-direction based.

### Print/PDF/export layout

- Active source includes CSV export, but no active PDF/print generation was found.
- CSV headings and filenames must be decided: Persian for human users, English for machine workflows, or bilingual.
- Excel/CSV opened in spreadsheet apps may not preserve RTL unless BOM/encoding, sheet direction, and column order are handled explicitly.
- Existing root-level PDF/DOCX/PPTX artifacts are not active generated surfaces but should be manually reviewed if they are distributed to users.

## Recommended implementation order

1. **Create localization infrastructure first**
   - Set `lang="fa-IR"` and `dir="rtl"` centrally.
   - Add a display-label dictionary for schema keys instead of renaming data keys.
   - Add central JavaScript helpers for `t()`, number formatting, date formatting, bidi isolation, and numeric input normalization.
2. **Shared shell and authentication**
   - Localize base title/footer/accessibility text, header, sidebar, login page, flash messages.
   - Add global RTL CSS/Bootstrap RTL strategy.
3. **Low-risk static pages/cards**
   - Workdesk cards and static labels.
   - Profile static modal labels only after deciding role/module display-name strategy.
4. **Editable data tables**
   - General parameters, factory directory/details/subfield, product selection, BOM editor.
   - Implement display labels without mutating `_order`/data keys.
   - Fix Persian header editing restrictions before allowing Persian user-created column labels.
5. **Cost calculation and dashboard**
   - Localize filter UI, KPI labels, result labels, CSV headings, chart titles/legends/tooltips.
   - Confirm currency semantics (`USD` vs `IRR`) before changing formatting.
6. **Server messages and validation**
   - Replace raw English messages with message codes plus localized UI messages or centralized server-side message catalog.
   - Avoid localizing API status values.
7. **Exports/print/report artifacts**
   - Decide bilingual vs Persian CSV/Excel headings.
   - Add manual checks in Excel/LibreOffice for UTF-8, RTL direction, and numeric behavior.
8. **Legacy template cleanup**
   - Remove unreachable old/copy templates or localize them to prevent regressions if reintroduced.

## Testing scenarios

### Desktop

- Login failure and success with Persian messages and correct RTL card alignment.
- Sidebar open/current-page navigation, hover animation direction, and logout button alignment.
- Workdesk card grid at wide widths; verify icon/text/button order and no clipped Persian labels.
- General parameters: search, filters, add/edit/delete row, add/delete column, save, last-modified date, pagination, modal layout.
- Factory pages: factory directory, details, subfield table edit/save/delete/filter; verify currency/percentage alignment.
- Product selection: search, dropdown filters, active chips, product/category/subcategory creation modals, validation errors, pagination arrows.
- BOM editor: material selection, numeric calculations, invalid lost/recyclability validation, save confirm/success/error, display-label mapping for core columns.
- Cost calculation: search/filter, single/bulk cost retrieval, loading/error states, CSV export, numeric/currency display.
- Dashboard: filters, analyze flow, KPI cards, ECharts labels/tooltips/legends, CSV download, empty state.
- Profile: admin/user modals, validation errors, notifications, privilege editor, history panel, role/module display labels.

### Mobile/tablet

- Sidebar slides from correct RTL edge and overlay closes it.
- Floating sidebar toggle does not cover important actions.
- Header wraps without reversing semantic order incorrectly.
- Cards stack and buttons remain tappable with Persian text.
- Tables scroll horizontally without clipping first/action columns; numeric columns remain readable.
- Dropdown filter menus open within viewport from the correct edge.
- Modals fit narrow screens, close buttons and action buttons remain accessible.
- Notifications appear on the expected side and do not cover navigation/actions.
- Chart labels/tooltips remain legible on narrow screens.

### Export/manual artifact checks

- CSV opens as UTF-8 in Excel/LibreOffice with Persian headings intact.
- Numeric columns remain numeric, not Persian-text strings, unless intentionally display-only.
- Any future PDF/print report renders Persian shaping, RTL order, table column order, and mixed Latin/Persian codes correctly.

## Highest-risk files

1. `templates/profile/profile.html` — dense inline CSS/JS, many admin strings, roles/modules/access levels, notifications, modals, validation, physical LTR styling.
2. `templates/product/production_selection.html` — large custom UI, filters, modals, notifications, pagination, dynamic strings, API interactions.
3. `templates/product/product_page.html` — BOM schema keys shown as labels, numeric calculations, validation alerts, editable columns.
4. `templates/factory_parameters/factory_subfield.html` — editable headers currently strip non-Latin characters; currency formatting hard-coded to `en-US`/`USD`.
5. `templates/cost/calculation.html` — cost results/export behavior, numeric formatting, dropdown/table LTR layout.
6. `templates/dashboard/dashboard.html` — ECharts labels/tooltips/legends, KPI labels, CSV export, mixed sample/API data.
7. `static/css/style.css` and page-local styles — global sidebar and repeated physical-direction assumptions.
8. `modules/product/routes.py`, `modules/auth/routes.py`, `modules/cost_calculation/routes.py` — English server messages that may surface to users.

## Manual visual review essential

Manual visual review is essential for:

- Mobile sidebar edge, overlay, and floating toggle placement.
- Back/open/pagination arrow direction and button order.
- Dense editable tables with Persian labels and Latin numeric cells.
- Product creation modals and profile/admin modals on mobile.
- ECharts dashboard legends, tooltips, long Persian labels, and chart responsiveness.
- CSV/Excel exports opened outside the browser.
- Any future PDF/print output, because Persian shaping and RTL table order cannot be validated by compile checks alone.
