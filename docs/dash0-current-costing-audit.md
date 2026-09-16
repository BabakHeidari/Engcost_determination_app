# DASH-0.1 Current Costing Audit

## 1. Executive Summary

> **Scope boundary:** This is a read-only characterization of the implementation at the time of the audit. It neither endorses nor changes a business rule. No production Python, route, template, JSON, spreadsheet, database, or application data was modified.

**FACT:** The live costing engine is `cost_aggregator(product, fac, cat, subc)` in `utils/cost_determiners.py`. The authenticated single- and bulk-product APIs in `modules/cost_calculation/routes.py` validate factory access, translate the canonical registry record to its operational directory key, and call that function. The engine then reads three kinds of factory-scoped JSON: the BOM at the exact hierarchy path, the factory summary and named subfield files, and the category-weight and production-prediction tables.

**CURRENT IMPLEMENTED FORMULA — BUSINESS VALIDITY NOT YET APPROVED:** For each factory-summary `Subfield` entry `s`, the engine computes

\[
C_s = \frac{\sum_i subfield[s].cost_i}{W_c/100}\div P_p
\]

where `W_c` is the first `selling_share_of_category` whose parallel `category` value equals the requested category and `P_p` is the first `Predicted Production` whose parallel `Product Name` equals the requested product. It computes the BOM term from the BOM's already-stored `cost_of_material_in_rial` values, then returns

\[
Final\_Production\_Cost = Total\_BOM\_Cost + \sum_s C_s.
\]

The category share is therefore in a denominator, followed by production in a second denominator. **REQUIRES HUMAN BUSINESS APPROVAL.**

**FACT:** The engine does **not** read current general material prices, exchange rates, usage, waste, recyclability, the factory summary's `Cost`, its `PercentageOfAll`, product `Capacity`, or product metadata while calculating. Those values can affect costing only if another workflow first materializes new `cost_of_material_in_rial` values into a BOM. The product editor performs that derivation in browser JavaScript; saving general material prices does not invoke BOM recalculation because `product_cost_recalculation()` is an unimplemented stub and its route call is commented out.

**TECHNICAL RISK:** Most input failures propagate as unhandled exceptions and therefore normally become Flask 500 responses. In contrast, `__subfield_coster()` catches every exception while opening, parsing, indexing, or summing a subfield and silently substitutes zero. The output cannot distinguish a genuine zero from a missing/corrupt/malformed subfield.

**FACT:** Calculation itself is read-only with respect to application files and Flask session. Some preparation/display routes are not read-only: product selection rebuilds the global catalog, factory loaders convert Excel to JSON (and can copy a template), editors write JSON/Excel, and product/factory routes store path context in session. These are separate from `cost_aggregator()`.

## 2. Files and Documentation Inspected

### Repository instructions

- `AGENTS.md` — the only `AGENTS.md` found from the repository parent downward. No nested instruction file applies.

### Documentation read

The following were inspected for Dashboard discovery/roadmap context, architecture, registry and authorization, JSON ownership/storage, localization, factory integration, and operational constraints:

- `docs/dashboard-module-discovery.md` (the current Dashboard discovery report and its modernization gaps; no separate Dashboard roadmap Markdown file exists in `docs/`)
- `docs/project-architecture.md`
- `docs/factory-integration-inventory.md`
- `docs/factory-registry-discovery.md`
- `docs/module-registry.md`
- `docs/authorization-matrix.md`
- `docs/authentication-json-migration.md`
- `docs/profile-json-storage-architecture.md`
- `docs/profile-json-data-access-layer.md`
- `docs/phase-12-hardening-and-operations.md`
- `docs/jalali-date-localization.md`
- `docs/localization-audit.md`
- `docs/persian-data-localization.md`

Existing documentation was treated as context rather than executable truth. In particular, `docs/dashboard-module-discovery.md` already records that the current Dashboard report is deliberately empty and disconnected from costing; the code trace below independently confirms the current implementation.

### Executable source and UI inspected

- Registration/paths: `app.py`; `utils/paths.py`; `utils/demo_data.py`.
- Costing: `utils/cost_determiners.py`; `modules/cost_calculation/routes.py`; `templates/cost/calculation.html`.
- Load/conversion helpers: `utils/load_data.py`; `utils/load_bom.py`; `utils/xlsxTojson.py`; `utils/updaters.py`; `utils/product_sheet_updater.py`.
- Input-owner modules: `modules/general_parameters/routes.py`; `templates/general_parameters/general_parameters.html`; `modules/factory_parameters/routes.py`; relevant factory templates; `modules/product/routes.py`; `templates/product/product_page.html`; `utils/factory_service.py`.
- Dashboard: `modules/dashboard/routes.py`; `templates/dashboard/dashboard.html`.

### Data shapes inspected (read-only)

- Overall catalogs/templates: `Data/Overall/ProductsLater.json`, `material_costs.json`, `material_costs_current.json`, `material_costs_history.json`, `category_table_sample.json`, and `sample_product.json`.
- Factory summary, category weight, and prediction files under each current directory in `Data/Factories/`.
- Factory subfield JSON schemas (`Factory_Data_<Subfield>.json`) and product/BOM JSON schemas at `Data/Factories/<factory>/<category>/<subcategory>/<product>.json`.
- `Data/Factories/__metadata.json` and product `_meta.json` files for hierarchy/capacity distinction.

Binary XLSX contents were not treated as the runtime costing source: the cost engine opens JSON directly. No application-data file was changed.

## 3. Current Costing Entry Points

### HTTP and page entry points

| Entry | Evidence | Input | Behavior |
|---|---|---|---|
| `GET /cost/cost_calculation` | `app.py` registers `cost_calculation_bp` at `/cost`; `modules/cost_calculation/routes.py::cost_cal()` | Authenticated user | Gets accessible factories through `FactoryService`, opens `Data/Overall/ProductsLater.json` directly, filters its rows by operational key, and renders `templates/cost/calculation.html`. No costs are calculated. |
| `POST /cost/get_cost` | `modules/cost_calculation/routes.py::get_cost()` | JSON keys `Product_Name`, `Factory`, `Category`, `Subcategory` | Rejects an empty/falsy payload with 400; validates factory registry/access; passes empty strings for absent hierarchy keys; calls `cost_aggregator`; JSON-serializes its return. Costing exceptions are not caught. |
| `POST /cost/get_costs_bulk` | `modules/cost_calculation/routes.py::get_costs_bulk()` | JSON list of product objects | Requires a list, validates every entry and every factory before calculating any item, then calls `cost_aggregator` sequentially. Result keys are product names, so duplicate names overwrite earlier results. Any calculation exception aborts the response; there is no partial result contract. |
| Direct Python | `utils/cost_determiners.py::cost_aggregator()` | Four strings in practice | Has no validation or authorization of its own; callers must supply the exact operational path components. |

**FACT:** Authentication and factory authorization occur in the route layer, not in the costing helper. `FactoryService.operational_key()` supplies the directory component. Category, subcategory, and product are accepted from the request without being cross-checked against the global catalog before path/parallel-array lookups.

**TECHNICAL RISK:** `utils/cost_determiners.py` imports `pandas` although it never uses it. Thus importing the costing engine fails with `ModuleNotFoundError` when pandas is absent, before any cost input is read.

## 4. End-to-End Calculation Flow

The conceptual hierarchy is implemented as path selection plus two name-only table lookups, not as a joined relational model:

1. **Factory identity and access.** `get_cost()`/`get_costs_bulk()` pass the request's `Factory` value to `FactoryService.require_access(..., "cost_calculation")`. The returned registry record's operational key becomes `fac`. Unknown factory produces route-level 404; inactive/unauthorized factory produces 403.
2. **Category/subcategory/product selection.** The route forwards request strings as `cat`, `subc`, and `product`. The category participates both in the BOM path and a category-weight lookup. The subcategory participates only in the BOM path. Product participates in the BOM filename and a prediction lookup.
3. **BOM read.** `cost_aggregator()` calls `__BOM_coster()`, which calls `utils.load_data.load_bom()`. The exact path is `Data/Factories/<fac>/<cat>/<subc>/<product>.json`; `load_json()` may apply demo redirection, but `utils.demo_data` maps only named `Data/Overall` demo files, so factory BOM paths are unchanged.
4. **BOM aggregation.** `__BOM_coster()` replaces the root with `bom_data['data']`. For every value in `data['materials']`, it uses `materials.index(material)` and takes the corresponding value from `data['cost_of_material_in_rial']`. It stores that value in a dictionary keyed by material, then sums the dictionary values as `Total_BOM_Cost`.
5. **Factory summary read/subfield discovery.** `__all_subfields_coster()` directly reads `Data/Factories/<fac>/Factory_Data.json` and uses exactly `['data']['Subfield']`. It does not consume summary `Cost` or `PercentageOfAll`.
6. **Category allocation read.** It directly reads `Data/Factories/<fac>/category_weights.json`, obtains `['data']`, finds the first index of `cat` in `category`, and reads the parallel `selling_share_of_category` value.
7. **Production allocation read.** It directly reads `Data/Factories/<fac>/ProductionPrediction.json`, obtains `['data']`, finds the first index of `product` in `Product Name`, and reads the parallel `Predicted Production` value.
8. **Subfield reads.** In summary-list order, `__subfield_coster()` builds `Data/Factories/<fac>/Factory_Data_<subfield>.json`, loads it, and sums exactly `['data']['cost']`. Any exception in this entire operation yields numeric zero.
9. **Allocation.** Each result is `subfield_total / (category_weight / 100) / ProductionPrediction`. No rounding, normalization, percentage-sum check, unit conversion, or filtering occurs.
10. **Final assembly.** `all_costs` initially contains subfield-name keys. `cost_aggregator()` then assigns `BOM`, assigns nested `BOM_Details`, and calculates `Final_Production_Cost` by summing all current top-level values except `BOM_Details`. At the instant of summation, `Final_Production_Cost` itself has not yet been inserted.

**FACT:** The returned JSON shape is dynamic because subfield names become top-level output keys:

```text
{
  <Subfield>: <allocated numeric cost>, ...,
  "BOM": <stored-BOM total>,
  "BOM_Details": {<material>: <stored rial value>, ..., "Total_BOM_Cost": <total>},
  "Final_Production_Cost": <sum>
}
```

**TECHNICAL RISK:** A summary subfield literally named `BOM` or `BOM_Details` is overwritten by final assembly. A subfield named `Final_Production_Cost` would be included in the sum and then overwritten by the computed final value. Duplicate subfield names overwrite earlier dictionary entries, so the final sum includes only the last occurrence of a duplicate name.

## 5. Current Formula Map

### Mathematical characterization

Let:

- `M` be the ordered BOM `materials` list;
- `R[j]` be the parallel stored `cost_of_material_in_rial[j]`;
- `S` be the ordered factory summary `Subfield` list;
- `K_s` be the list `data.cost` in `Factory_Data_<s>.json`, or zero after any caught exception;
- `W_c` be the first parallel category share selected by `category.index(cat)`;
- `P_p` be the first parallel prediction selected by `Product Name.index(product)`.

**CURRENT IMPLEMENTED FORMULA — BUSINESS VALIDITY NOT YET APPROVED:**

\[
BOMDetails[m] = R[firstIndex(M,m)] \quad \text{for each iteration over }m\in M
\]

Because `BOMDetails` is a dictionary, repeated material names collapse to one key; because `.index()` always returns the first occurrence, later repeated-material costs are never selected.

\[
Total\_BOM\_Cost = \sum_{m\in unique(M)} BOMDetails[m]
\]

\[
RawSubfield_s = \begin{cases}
\sum_i K_{s,i} & \text{if load, shape, and Python sum all succeed}\\
0 & \text{if any exception occurs}
\end{cases}
\]

\[
AllocatedSubfield_s = \frac{RawSubfield_s}{W_c/100}\div P_p
= \frac{100\times RawSubfield_s}{W_c\times P_p}
\]

The second algebraic form is equivalent only when both denominators permit evaluation; the implementation evaluates left-to-right exactly as the first form.

\[
Final\_Production\_Cost = Total\_BOM\_Cost + \sum_{s\in unique(S)} AllocatedSubfield_s
\]

### Actual dependency map and hidden reads

```text
HTTP Factory identifier
  -> Profile JSON canonical factory registry (authorization only)
  -> FactoryService.operational_key
      -> Data/Factories/<fac>/Factory_Data.json
           -> data.Subfield[]
               -> Data/Factories/<fac>/Factory_Data_<Subfield>.json
                    -> data.cost[] -> sum -> RawSubfield
      -> Data/Factories/<fac>/category_weights.json
           -> data.category[].index(cat)
           -> parallel data.selling_share_of_category[index] -> W_c
      -> Data/Factories/<fac>/ProductionPrediction.json
           -> data["Product Name"].index(product)
           -> parallel data["Predicted Production"][index] -> P_p
      -> Data/Factories/<fac>/<cat>/<subc>/<product>.json
           -> data.materials[]
           -> parallel data.cost_of_material_in_rial[] -> Total_BOM_Cost

AllocatedSubfield = RawSubfield / (W_c / 100) / P_p
Final_Production_Cost = Total_BOM_Cost + sum(AllocatedSubfield)
```

Not dependencies of the calculation invocation: `ProductsLater.json` (selection only), product `_meta.json`/`Capacity`, `material_costs.json`, XLSX files, `Factory_Data.json.data.Cost`, `PercentageOfAll`, `_order`, modification metadata, and all other BOM columns.

## 6. BOM Cost Lineage

### Runtime-consumed fields

| BOM field | Evidence/source meaning | Runtime use by `cost_aggregator` | Source vs derived |
|---|---|---|---|
| `materials` | BOM row identity displayed/edited by `templates/product/product_page.html`; stored by `/save_bom` | Iteration, dictionary key, and `.index()` lookup | User-selected/reference-linked input |
| `cost_of_material_in_rial` | Product editor labels it “cost of material in Rial” and derives it before save | The **only** monetary BOM column read by `__BOM_coster()` | Precomputed/materialized derived value in BOM |

### Fields present but not recomputed by costing

| Field | Current preparation behavior | Consumed directly by engine? | Unit/evidence |
|---|---|---|---|
| `unit` | Copied in browser from `material_costs.json` for selected material | No | Enumerated material unit; exact physical dimension depends on row (`UNRESOLVED` generically) |
| `currency` | Copied from selected material | No | Currency label/code |
| `cost_per_unit_in_currency` | Copied from selected material's current general price | No | Currency units per material unit |
| `cost_currency` | Browser `getCostCurrency()`: `1` for exact `IRR - Iranian Rial`; otherwise it looks up a **material whose name equals the currency string** and uses that material's `cost_per_unit_in_currency`; missing lookup becomes empty | No | Intended/displayed as exchange rate to Rial; exact semantic source is `UNRESOLVED` |
| `usage` | BOM-editable numeric value | No | Material quantity in the row's `unit` |
| `lost_percentage` | BOM-editable and UI-clamped below 100 | No | Label says percentage, but computation uses the raw numeric value without `/100` |
| `recycability_percentage` | BOM-editable; UI keeps it below loss when loss is positive | No | Label says percentage, but computation uses the raw numeric value without `/100` |
| `cost_of_material_in_its_currency` | Browser calculates `costPerUnit * usage * max(0, 1 - lost * rec)` and serializes to four decimals before save | No | Currency amount |
| `cost_of_material_in_rial` | Browser calculates `costPerUnit * usage * costCurrency * max(0, 1 - lost * rec)` and serializes to four decimals, then save normalizes numeric strings to numbers rounded to three decimals | Yes, without recomputation | Rial per BOM material row, per UI label |
| `_order` | Controls display/save column order | No | N/A |

Some legacy BOMs contain `cost_per_unit` in `data` while `_order` asks for `cost_per_unit_in_currency`. The engine ignores both spellings, but malformed/stale `cost_of_material_in_rial` values still directly determine the BOM term.

### General-price change propagation

**FACT:** Changing `Data/Overall/material_costs.json` through `POST /save_materials` does **not** automatically change `cost_aggregator()` output. The engine never opens that file. The product page reads the current material table, executes `updateAllDerivedFields()` in the browser on page initialization for rows having a material, and only `POST /save_bom` persists the recalculated derived columns. Therefore the dependency is manual and materialized:

```text
material_costs.json change
  -X-> cost_aggregator (no direct edge)
  -> later authorized product-page load
  -> browser material lookup and derivation
  -> explicit BOM save
  -> BOM cost_of_material_in_rial
  -> subsequent cost_aggregator call
```

**TECHNICAL RISK:** Merely opening the product page changes the in-memory derived values, but the costing endpoint continues to see old stored values until save. The browser efficiency expression treats values labeled as percentages as raw multipliers. This report records that behavior without judging its intended business meaning.

## 7. General Parameter Lineage

The current owner is `modules/general_parameters/routes.py`: `GET /general_parameters/` reads `Data/Overall/material_costs.json`; `POST /save_materials` passes added/edited/deleted rows to `utils.updaters.material_data_updater()`.

| Technical field | JSON type observed | Unit | Direct engine consumption | Copy/materialization and dependency chain |
|---|---|---|---|---|
| `material` | string | Material identifier/name | No | Product editor maps it to BOM `materials`; the saved name is later used only to key BOM details. |
| `unit` | string | Row-specific unit (`UNRESOLVED` as a universal unit) | No | Copied to BOM `unit`; not used in costing. |
| `currency` | string | Currency label/code | No | Copied to BOM `currency`; also passed to the product editor's `getCostCurrency()` behavior. |
| `cost_per_unit_in_currency` | number in current general table | Currency/material-unit | No | Copied to BOM; browser uses it to derive both cost columns; only saved BOM `cost_of_material_in_rial` later reaches costing. |
| `last_modification_date` | string when saved | Canonical date-time string | No | Metadata only. |

`material_costs_history.json` is appended by the updater, but does not feed product editing or costing. `material_costs_current.json` exists but the active paths point to `material_costs.json`. `product_cost_recalculation()` is `pass`, and the route's apparent call is commented out.

**TECHNICAL RISK:** `__material_history_updater()` currently processes `added_materials` twice rather than processing `modified_materials` on its second call. This is outside the cost formula but weakens price-history lineage. No fix is made here.

## 8. Factory Parameter Lineage

| Technical input | Exact source | Calculation use | Unit | Required/fallback |
|---|---|---|---|---|
| Operational factory key `fac` | `FactoryService.operational_key()` after route access validation | Directory component for every factory read | Identifier | Required; invalid/inactive/inaccessible requests are rejected before calculation. Direct Python calls have no guard. |
| `data.Subfield[]` | `Data/Factories/<fac>/Factory_Data.json` | Discovers names and output terms; order governs evaluation/insertion | Name/identifier | Required. Missing/corrupt/root/key failures propagate. Empty list is allowed and produces BOM-only final cost. |
| `data.Cost[]` | Same summary | Not used | Likely monetary summary, but `UNRESOLVED` for engine | Ignored. |
| `data.PercentageOfAll[]` | Same summary | Not used | Percentage by label | Ignored. |
| `data.cost[]` | `Factory_Data_<Subfield>.json` | Python `sum()` gives raw subfield total | Monetary amount; currency is not stated in file schema (`UNRESOLVED`) | Any exception becomes zero. Empty list sums to zero. Booleans/numbers follow Python sum semantics; strings/mixed invalid elements cause caught `TypeError` and zero. |
| `data.category[]` | `category_weights.json` | First-match index for request `cat` | Name/identifier | Required; missing file/schema/category propagates. |
| `data.selling_share_of_category[]` | Same file, parallel index | Denominator `weight/100` | Percentage points by field name and UI | Required numeric nonzero for successful division; no validation/default. |
| `data["Product Name"][]` | `ProductionPrediction.json` | First-match index for request `product` | Name/identifier | Required; missing file/schema/product propagates. |
| `data["Predicted Production"][]` | Same file, parallel index | Second denominator | Production count (`UNRESOLVED` time horizon) | Required numeric nonzero for successful division; no validation/default. |

The owner UI is `modules/factory_parameters/routes.py`. It can load/display all four tables and has separate save endpoints. `load_factory_summery()` always attempts to regenerate summary JSON from the `Summery` Excel sheet before returning it; `load_factory_subfield()` regenerates a subfield JSON from an Excel sheet. In contrast, the costing engine directly reads existing JSON and never performs those conversions.

### Subfield-specific behavior

**FACT:** Names come only from `Factory_Data.json.data.Subfield`, not from directory enumeration and not from the summary `Cost` rows. For every list element, a filename is formed verbatim as `Factory_Data_<name>.json`.

**FACT:** `__subfield_coster()` uses a bare `except:` around `load_json(...)` and `sum(subfield_data['data']['cost'])`. Consequently all of the following are masked as zero: absent/unreadable file; JSON decoding failure; demo-path helper failure; wrong root type; missing `data`; missing `cost`; non-iterable `cost`; a string or other non-addable element; and process-level exceptions inheriting directly from `BaseException` (because this is broader than `except Exception`). Errors forming the path occur before the `try` only in the `Path`/format expression and are not normally expected with route strings.

**FACT:** Missing subfield files are independently zeroed; calculation proceeds to later subfields. The current factory summary may list subfields with no corresponding JSON, which therefore appear in successful output as `0.0` or `0` after allocation.

## 9. Category-Weight Behavior

> **CURRENT IMPLEMENTED BEHAVIOR — BUSINESS VALIDITY NOT YET APPROVED. REQUIRES HUMAN BUSINESS APPROVAL.**

- **Source:** `Data/Factories/<fac>/category_weights.json`, root `data`, parallel keys `category` and `selling_share_of_category`.
- **Representation:** Current files use numeric percentage points such as `60`, `30`, `10`, `100.0`, and repeating `33.333...`. The loader's fallback creator (used by the factory-parameter page, not costing) assigns `100 / category_count` to every category.
- **Lookup:** `category_weights["category"].index(cat)` uses exact Python equality and returns the first match. Case, whitespace, localization, and aliases are not normalized.
- **Formula placement:** `__subfield_coster(...) / (category_cost_weight / 100)`, so a smaller positive share creates a larger allocated subfield result; it is not multiplication by the share.
- **Missing category:** `list.index()` raises `ValueError`; no costing catch exists, so the HTTP calculation normally returns 500.
- **Missing file/invalid JSON/missing key:** the underlying exception propagates, normally 500.
- **Zero numeric share:** `category_cost_weight / 100` is zero, then division raises `ZeroDivisionError`, normally 500. A nonnumeric value can raise `TypeError` before division.
- **Duplicate category:** the first occurrence and its parallel weight win; later duplicates are ignored.
- **Unequal parallel-list lengths:** a found category whose index has no weight raises `IndexError`, normally 500. Extra weights are ignored.
- **Negative numeric share:** technically accepted; it produces negative allocated subfield costs (unless later prediction behavior changes the sign again).
- **Values above 100:** technically accepted with no clamp or sum validation.

No code verifies that all category shares total 100 or that every hierarchy category has exactly one row.

## 10. ProductionPrediction Behavior

> **CURRENT IMPLEMENTED BEHAVIOR — desired semantics are UNRESOLVED and require human approval.**

Source is exactly `Data/Factories/<fac>/ProductionPrediction.json`, with parallel keys `Product Name` and `Predicted Production` under `data`. Lookup is `Product Name.index(product)` and therefore exact, name-only, and first-match.

| Case | Actual behavior |
|---|---|
| Valid positive numeric value | Each already category-adjusted subfield total is divided by it. BOM is not divided by production. |
| Numeric zero (`0` or `0.0`) | First subfield allocation attempts division by zero and raises `ZeroDivisionError`. If the factory summary has no subfields, prediction is still looked up but never divided, and BOM-only output succeeds. |
| Missing product | `.index()` raises `ValueError`; normally HTTP 500. |
| Missing prediction file | `load_json()` re-raises `FileNotFoundError`; normally HTTP 500. |
| Invalid JSON | `JSONDecodeError` propagates; normally HTTP 500. |
| Missing root/data/column | `KeyError` (or type/index error) propagates; normally HTTP 500. |
| Nonnumeric value | Division raises `TypeError`; numeric strings are not coerced and also fail. |
| Duplicate product | First matching row wins; later entries are ignored. |
| Negative numeric value | Accepted; every otherwise-positive allocated subfield term becomes negative. No validation occurs. |
| Unequal parallel-list lengths | A found name without a corresponding prediction raises `IndexError`; extra prediction values are ignored. |

The factory detail helper `product_lister()` has a different display-time fallback: on **any** exception it derives that factory's product names from the global catalog and returns zeros. That fallback is not used by `cost_aggregator()`, so it does not make a missing prediction file calculable.

## 11. Product Identity and Hierarchy

**FACT:** Runtime recipe identity is path-dependent and factory-specific:

```text
(operational factory key, category, subcategory, product name)
  -> Data/Factories/<factory>/<category>/<subcategory>/<product>.json
```

The global `Data/Overall/ProductsLater.json` catalog stores rows with `Product_Name`, `Factory`, `Category`, `Subcategory`, and `Capacity`. `utils.updaters.create_product_metadata()` can regenerate it by walking depth-three factory directories; it is a selector/catalog, not an input read by `cost_aggregator()`.

**FACT:** Identity is inconsistent across individual sub-operations:

- BOM lookup uses the full four-part path.
- Category weight lookup uses category name only within factory.
- ProductionPrediction lookup uses product name only within factory; category/subcategory are not part of that lookup.
- Bulk API response identity uses product name only (`result[name]`), so same-named products in distinct hierarchy paths/factories collide and the later result overwrites the earlier one.
- `BOM_Details` identity uses material name only and collapses duplicate material rows.
- Factory authorization uses canonical factory registry identity, but storage uses its `operational_key` directory value.

Therefore the implementation does not establish a single global product-ID strategy. The recipe itself is composite/path-scoped, while prediction and response mapping are name-only at narrower/different scopes.

## 12. Units Inventory

| Value | Current unit supported by evidence | Notes |
|---|---|---|
| General/BOM `unit` | Row-specific material unit | Values are labels; no unit conversion occurs. Generic dimension is `UNRESOLVED`. |
| General/BOM `currency` | Named currency | Reference label only in engine. |
| `cost_per_unit_in_currency` | Currency unit per material unit | Evidenced by technical key and Persian display label. |
| `cost_currency` | Intended exchange-rate-like multiplier to Rial | UI makes IRR equal 1 and multiplies it into Rial cost; exact base/quote convention is `UNRESOLVED`. |
| `usage` | Quantity in the BOM row's material unit | No dimensional enforcement. |
| `lost_percentage`, `recycability_percentage` | Percentage points by name/UI | Browser formula consumes raw entered number, not divided by 100. |
| `cost_of_material_in_its_currency` | Currency amount per product BOM | Precomputed browser value. |
| `cost_of_material_in_rial` | Rial per product BOM row | Explicit UI label; sole BOM monetary input to engine. |
| `Total_BOM_Cost`, returned `BOM` | Rial per product, if all stored row values honor their label | Arithmetic itself does not enforce currency. |
| Subfield `data.cost` / raw total | `UNRESOLVED` monetary unit | Files and engine do not encode/convert currency. Consistency with Rial is assumed implicitly by final addition. |
| `selling_share_of_category` | Percentage points | Divided by 100 before being used as denominator. |
| `Predicted Production` | Production count | Period/time horizon and whether count is category- or product-specific are `UNRESOLVED`; lookup is product name within factory. |
| Allocated subfield term | Raw subfield monetary unit divided by share fraction and production count | Interpreted by final addition as compatible with BOM Rial/product, but this dimensional compatibility is not validated. |
| `Final_Production_Cost` | Operationally presented as product cost; exact guaranteed unit is `UNRESOLVED` | It adds labeled Rial BOM values to subfield values whose currency/time basis is not encoded. |
| Product `Capacity` | `UNRESOLVED` | Stored in `_meta.json`/catalog and unused by costing. |
| Summary `PercentageOfAll` | Percentage points | Unused by costing. |

## 13. Error and Fallback Behavior

### Error matrix

| Stage | Failure | Current result |
|---|---|---|
| Route payload | Single payload absent/falsy | JSON 400 `No JSON payload`. |
| Route payload | Single payload is a truthy non-dict (e.g. list) | `.get` raises `AttributeError`; normally 500. |
| Route payload | Bulk root is not list / item not dict | JSON 400. |
| Authorization | Unknown / inaccessible or inactive factory | JSON 404 / 403 from explicit route catches. |
| BOM path/load | Missing file, malformed JSON, permissions | `load_json()` logs at level 5 and re-raises; normally 500. |
| BOM shape | Missing `data`, `materials`, or Rial column; short parallel column | `KeyError`/`IndexError`; normally 500. |
| BOM arithmetic | Stored numeric strings or mixed invalid values | Python `sum()` raises `TypeError`; normally 500. No coercion. |
| BOM duplicate material | Repeated row | Silent first-occurrence selection plus dictionary collapse; not an exception. |
| Summary/category/prediction load/shape | Missing/malformed/missing lookup | Exception propagates; normally 500. |
| Subfield load/shape/sum | Any exception at all | Silently becomes zero for that named subfield. |
| Category share/prediction | Zero denominator | `ZeroDivisionError`; normally 500. |
| Final sum | A nonnumeric allocated/BOM value reaches sum | `TypeError`; normally 500. |
| Bulk calculation | Duplicate product name | Silent overwrite in response object. |
| JSON serialization | NaN/infinity produced by unusual numeric input | Flask/Python serialization behavior applies; engine has no finite-number check. |

**TECHNICAL RISK:** Errors are asymmetric: a broken subfield looks like valid zero cost, while a broken BOM, category row, prediction row, or top-level factory file fails the entire request. Neither cost route maps calculation failures to a documented JSON error contract.

**TECHNICAL RISK:** `load_json()` may redirect reads only when `ENG_COST_DEMO_LOCALE=fa`, but its mapping applies to known Overall file stems. Current factory costing reads are therefore canonical. The cost page itself opens the Overall product catalog with built-in `open()` rather than `load_json()`, so even catalog demo selection is not used there.

## 14. Side Effects

### Cost calculation itself

**FACT:** `cost_aggregator()`, `__BOM_coster()`, `__all_subfields_coster()`, `__subfield_coster()`, `load_bom()`, and `load_json()` perform reads and construct in-memory dictionaries only. They do not write JSON/XLSX, update metadata, change the Flask session, or maintain a cache. `load_json()` logs failures, which is an operational logging side effect but not an application-data mutation.

The single and bulk cost routes likewise do not modify session or files; they only authenticate, authorize, calculate, and serialize. Bulk validation intentionally completes before protected calculation reads, but calculations then run sequentially.

### Separate preparation/editing behavior

- `GET /product/production_selection` calls `create_product_metadata()` and rewrites `Data/Overall/ProductsLater.json` by walking product directories.
- Product page selection stores `recipe_path` and `recipe_factory_id` in session. `POST /save_bom` writes the browser-provided BOM JSON.
- Factory detail/subfield loaders can convert XLSX sheets to JSON; a missing/broken factory summary can cause a template XLSX copy. Factory routes store factory/subfield paths in session.
- Factory save endpoints write summary/category/prediction JSON; subfield save also updates XLSX and regenerates summary data.
- General-parameter save writes the current material JSON and history JSON.

These workflows prepare inputs, but none is invoked by the cost engine or cost API routes.

## 15. Dashboard Integration Gap

**FACT:** `GET /api/cost_analysis` in `modules/dashboard/routes.py` validates an optional factory context, then always returns four zero/placeholder KPIs and three empty breakdown arrays. It does not import/call `cost_aggregator`, read `ProductsLater.json`, traverse product hierarchy, or read any BOM/factory/material input.

**FACT:** The Dashboard filter shell obtains accessible canonical factories and supplies hard-coded display categories. Its API ignores category, subcategory, and product parameters. Meanwhile the real costing API expects a concrete factory/category/subcategory/product tuple and returns a per-product dynamic dictionary, not the Dashboard KPI/breakdown contract.

The current gap is therefore an absent, approved integration/aggregation contract between (a) authorized hierarchy enumeration, (b) per-product costing with its documented failures and name collisions, and (c) Dashboard KPI/breakdown response shapes. There is also no defined handling for partial failures, duplicate identities, currency/unit compatibility, or cross-product aggregation. This audit does not propose that contract or redesign the Dashboard.

## 16. Candidate Baseline Fixtures

These are **characterization candidates for current technical behavior, not expected business-correct results**. Tests should use temporary copied/minimized fixtures rather than mutate production data or encode unrelated sensitive values.

### Existing representative success scenarios

1. **`DinMohamadpour / IKCO / LithiumIon / B3N47`** — six BOM rows, non-empty multi-material stored Rial data, a valid category share and positive prediction, six discovered factory subfields, four present subfield files and two missing ones, and a non-trivial successful final cost. It characterizes missing-subfield-to-zero and the full formula.
2. **`DinMohamadpour / Bahman Khodro / Fidelity / 20mAH-F`** — three-material BOM, category share other than 100, positive prediction, multiple nonzero subfields, and successful non-trivial output. It is useful for denominator ordering.
3. **`DinMohamadpour / Bahman Khodro / Fidelity / 30mAH-F`** — two-material BOM and very large stored BOM value; useful for numeric scale and floating allocation characterization.
4. **`Nasooz / nasooz_cat1 / nasooz_sub_cat1 / nasooz_prod_1`** — two-material BOM, category share 100, positive prediction, three present and three absent listed subfield files; useful for simple category denominator and fractional allocated costs.
5. **`Nasooz / nasooz_cat1 / nasooz_sub_cat1 / nasooz_prod_2`** — single-material counterpart under the same factory/category/subcategory with a different prediction, useful for checking per-product production allocation.

To avoid freezing sensitive or volatile application amounts in this audit, exact totals should be captured by the future characterization test from a reviewed sanitized fixture at fixture-creation time.

### Existing failure candidates

- Current legacy products whose `cost_of_material_in_rial` contains numeric strings characterize the uncaught `TypeError` from Python `sum()`.
- A HajAmini product with a numerically valid BOM characterizes missing `ProductionPrediction.json`; note that some HajAmini products fail earlier at BOM summation, proving stage ordering.
- A summary-listed subfield with no matching JSON characterizes silent zero.

### Minimal synthetic edge candidates for a future test suite

- Empty BOM materials/Rial arrays (BOM total zero).
- Duplicate material name with different parallel Rial values (first-index and dictionary-collapse behavior).
- Empty summary subfield list (BOM-only output, even with zero prediction after successful lookup).
- Duplicate subfield name and reserved names `BOM`, `BOM_Details`, `Final_Production_Cost`.
- Missing/corrupt subfield and missing `data.cost` (each silently zero).
- Missing category; duplicate category; zero, negative, nonnumeric, and over-100 category weight; unequal category/weight lengths.
- Missing prediction file/product; duplicate product; zero, negative, numeric-string, nonnumeric prediction; unequal prediction lists.
- Missing/short/mixed-type BOM columns and a malformed JSON BOM.
- Same product name in two hierarchy paths in a bulk request (response overwrite).
- Empty/falsy single request, truthy non-object request, invalid bulk entry, and fully authorized bulk where a later calculation fails.

## 17. Business Semantics Requiring Human Approval

The following **12 unresolved business semantics** are intentionally questions, not decisions:

1. **UNRESOLVED BUSINESS SEMANTIC — category allocation:** Should `selling_share_of_category` be a divisor exactly as implemented, a multiplier, or part of another allocation method? What does it represent?
2. **UNRESOLVED BUSINESS SEMANTIC — production allocation:** What period and scope does `Predicted Production` represent, and which cost pools should be divided by it? Should BOM remain outside that division?
3. **UNRESOLVED BUSINESS SEMANTIC — cost drivers:** Are all factory subfields allocated by the same category share and prediction, or do individual subfields require distinct drivers?
4. **UNRESOLVED BUSINESS SEMANTIC — subfield currency/time basis:** Are all `data.cost` values Rial and for the same period as prediction, making their addition to BOM Rial/product dimensionally valid?
5. **UNRESOLVED BUSINESS SEMANTIC — BOM freshness:** When should general price/exchange-rate changes materialize into stored BOM costs, and which version/date should costing use?
6. **UNRESOLVED BUSINESS SEMANTIC — percentages:** Are loss and recyclability stored as fractions or percentage points, and is `1 - lost * recycability` the intended business relationship?
7. **UNRESOLVED BUSINESS SEMANTIC — exchange rate:** Is looking up a material named exactly like a currency the intended source and convention for `cost_currency`?
8. **UNRESOLVED BUSINESS SEMANTIC — product identity:** Should a product be globally identified, factory-scoped by name, or identified by the full factory/category/subcategory/name composite (or a stable ID)?
9. **UNRESOLVED BUSINESS SEMANTIC — duplicates:** What should duplicate material, category, prediction, subfield, or bulk product identities mean?
10. **UNRESOLVED BUSINESS SEMANTIC — zero/missing/invalid values:** Should these fail, be excluded, use zero, use a fallback, or mark a result incomplete? Current behavior is inconsistent and is not endorsed.
11. **UNRESOLVED BUSINESS SEMANTIC — Dashboard KPIs:** What entities, time period, units, weighting, failure policy, and aggregation define total cost, average cost/product, product count, top cost driver, and category/subcategory breakdowns?
12. **UNRESOLVED BUSINESS SEMANTIC — negative values:** Are negative category shares, predictions, subfield costs, or final allocated terms valid adjustments, or invalid data?

No answer to these questions is implied by documenting current code.

## 18. Appendix — File / Function / Field Reference

| File | Function/route/field | Current role |
|---|---|---|
| `app.py` | `register_blueprint(..., url_prefix="/cost")` | Establishes actual cost route prefix. |
| `modules/cost_calculation/routes.py` | `cost_cal()` | Authorized catalog page; direct Overall catalog read/filter. |
| same | `get_cost()` | Single calculation route and factory authorization. |
| same | `get_costs_bulk()` | Validate-whole-batch then name-keyed calculations. |
| `utils/cost_determiners.py` | `__BOM_coster()` | Stored Rial BOM dictionary/total. |
| same | `__subfield_coster()` | Direct subfield JSON sum with bare-except zero. |
| same | `__all_subfields_coster()` | Summary discovery, category/prediction lookup, allocation. |
| same | `cost_aggregator()` | Output assembly and final sum. |
| `utils/load_data.py` | `load_json()` | Demo-aware JSON read, logging, re-raise. |
| same | `load_bom()` | Exact four-part hierarchy path. |
| same | `load_factory_summery()` | UI loader that converts/copies Excel; not cost path. |
| same | `load_factory_subfield()` | UI loader that converts Excel; not cost path. |
| same | `load_category_weights_of_costs()` | UI fallback creator; not used by cost path. |
| `utils/paths.py` | `parent_path`, `product_path`, `material_path` | `Data` root and legacy Overall paths. |
| `utils/demo_data.py` | `demo_path_for()` | Optional known Overall read redirection; factory inputs unaffected. |
| `modules/general_parameters/routes.py` | `/general_parameters/`, `/save_materials` | General material-price owner. |
| `utils/updaters.py` | `material_data_updater()` | Writes material current/history data. |
| same | `product_cost_recalculation()` | Empty stub; no propagation. |
| same | `create_product_metadata()` | Walks product paths and writes global catalog. |
| `modules/product/routes.py` | `product_page()` | Loads BOM and general materials for editor; sets session context. |
| same | `save_bom()` | Persists browser-precomputed BOM. |
| `templates/product/product_page.html` | `getCostCurrency()`, `calculateEfficiencyFactor()`, `updateDerivedFields()` | Current client-side BOM derivation formulas. |
| `modules/factory_parameters/routes.py` | `factory_details()`, `product_lister()` | Factory input UI and display-only prediction fallback. |
| same | `save_factories`, `save_category_table`, `save_factory_subfields`, `save_prediction_production_per_capita` | Input preparation/mutations separate from calculation. |
| `utils/xlsxTojson.py` | `xlsx_to_json_convertor()`, `to_json()` | JSON/XLSX preparation and writes. |
| `modules/dashboard/routes.py` | `/dashboard`, `/api/cost_analysis` | Authorized shell and deliberately empty analytics response. |
| `Data/Overall/ProductsLater.json` | `Product_Name`, `Factory`, `Category`, `Subcategory`, `Capacity` | Selector/catalog, not engine dependency. |
| `Data/Overall/material_costs.json` | `material`, `unit`, `currency`, `cost_per_unit_in_currency` | General inputs copied/derived into BOM by browser workflow. |
| `Data/Factories/<fac>/Factory_Data.json` | `Subfield`, `Cost`, `PercentageOfAll` | Only `Subfield` is consumed by engine. |
| `Data/Factories/<fac>/Factory_Data_<s>.json` | `data.cost` | Raw subfield cost list. |
| `Data/Factories/<fac>/category_weights.json` | `category`, `selling_share_of_category` | Category denominator lookup. |
| `Data/Factories/<fac>/ProductionPrediction.json` | `Product Name`, `Predicted Production` | Production denominator lookup. |
| `Data/Factories/<fac>/<cat>/<subc>/<product>.json` | `materials`, `cost_of_material_in_rial` | Direct BOM calculation fields; other columns are stored lineage only. |

### Audit completion statement

- **Report path:** `docs/dash0-current-costing-audit.md`.
- **Formulas discovered:** stored-Rial BOM aggregation; raw subfield sum; inverse category-share allocation; inverse predicted-production allocation; final BOM-plus-allocated-subfields sum; and the upstream browser-only BOM derivation formula.
- **Major hidden dependencies:** direct summary-driven subfield filenames, category and prediction parallel arrays, precomputed BOM Rial values, operational factory directory keys, and pandas at import time.
- **Candidate baseline fixtures:** five existing successful scenarios, existing malformed/missing-data failures, and the synthetic edge inventory in Section 16.
- **Unresolved business semantics count:** 12, isolated in Section 17.
- **Highest technical risks:** silent broad-exception zeroing; stale/precomputed BOM prices; uncaught input/schema/division errors; inconsistent name/path identity and duplicate collapse; unvalidated units; and no Dashboard integration/aggregation contract.
- **Confirmation:** No business definition was changed or approved.
- **Confirmation:** No production code or production application data was changed.
