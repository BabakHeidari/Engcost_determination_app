# DASH-0.3 Human Business-Decision Dossier

> **HUMAN GATE — NO BUSINESS RULE IS APPROVED HERE**
>
> This dossier packages current facts, viable choices, consequences, and
> non-binding technical advice for the product/business owner. Every card is
> unresolved. It does not authorize implementation, change a formula, or turn
> a recommendation into a contract. DASH-0.4 and analytical implementation
> must wait for explicit human approval of the relevant Decision IDs.

## Decision summary

| ID | Decision | Risk if unresolved | Blocks Phase | Status |
|---|---|---|---|---|
| DASH0-BIZ-001 | Unit Cost KPI | A familiar label could report the wrong economic quantity | DASH-1, DASH-2 | PENDING HUMAN APPROVAL |
| DASH0-BIZ-002 | Projected Total Cost KPI | Multiplication may mix incompatible horizons or incomplete products | DASH-1, DASH-2 | PENDING HUMAN APPROVAL |
| DASH0-BIZ-003 | Weighted Average Unit Cost KPI | Wrong weights/denominator can reverse comparisons | DASH-1, DASH-2 | PENDING HUMAN APPROVAL |
| DASH0-BIZ-004 | Product Count KPI | Counts may mix catalog entries, configurations, or calculated products | DASH-1, DASH-2 | PENDING HUMAN APPROVAL |
| DASH0-BIZ-005 | Top Cost Driver KPI | Dynamic keys have unapproved meanings and ties | DASH-1, DASH-2, DASH-3 | PENDING HUMAN APPROVAL |
| DASH0-BIZ-006 | Category-share allocation | Current inverse allocation may materially distort unit cost | DASH-1, DASH-2, DASH-5 | PENDING HUMAN APPROVAL |
| DASH0-BIZ-007 | Predicted Production meaning and horizon | Allocation is dimensionally unverifiable | DASH-1, DASH-2, DASH-5 | PENDING HUMAN APPROVAL |
| DASH0-BIZ-008 | Prediction edge cases and partial coverage | One bad row can fail or silently bias an aggregate | DASH-1, DASH-2, DASH-3, DASH-5 | PENDING HUMAN APPROVAL |
| DASH0-BIZ-009 | Factory cost-driver meanings and allocation | Labels do not establish accounting meaning, currency, or driver | DASH-1, DASH-2, DASH-3, DASH-5 | PENDING HUMAN APPROVAL |
| DASH0-BIZ-010 | Analytical data-state taxonomy | Zero can be confused with absent or failed data | DASH-1, DASH-2, DASH-3 | PENDING HUMAN APPROVAL |
| DASH0-BIZ-011 | Analysis factory scope | Aggregation, comparison, and authorization contracts differ | DASH-1, DASH-2, DASH-3, DASH-5 | PENDING HUMAN APPROVAL |
| DASH0-BIZ-012 | Hierarchy filters and empty selections | Results may unintentionally broaden beyond user intent | DASH-1, DASH-2, DASH-3 | PENDING HUMAN APPROVAL |
| DASH0-BIZ-013 | Product identity and duplicate resolution | Name-only joins can overwrite or cross-wire configurations | DASH-1, DASH-2, DASH-3, DASH-5 | PENDING HUMAN APPROVAL |
| DASH0-BIZ-014 | Dashboard permissions and “all factories” | UI/policy mismatch can overexpose or overdeny analysis | DASH-1, DASH-2, DASH-3, DASH-5 | PENDING HUMAN APPROVAL |
| DASH0-BIZ-015 | General-parameter sensitivity visibility | Simulation could reveal prices/exchange inputs without source permission | DASH-5 | PENDING HUMAN APPROVAL |
| DASH0-BIZ-016 | Factory-parameter sensitivity visibility | Simulation could reveal factory costs without source permission | DASH-5 | PENDING HUMAN APPROVAL |
| DASH0-BIZ-017 | Source edits versus sensitivity overrides | What-if actions could be mistaken for persistent source changes | DASH-5 | PENDING HUMAN APPROVAL |
| DASH0-BIZ-018 | Cost freshness model | “Current” and “last updated” have no defined meaning | DASH-1, DASH-2, DASH-3, DASH-5 | PENDING HUMAN APPROVAL |
| DASH0-BIZ-019 | Business rounding, precision, comparisons, and ties | Displayed totals may not reconcile; rankings may be unstable | DASH-1, DASH-2, DASH-3, DASH-5 | PENDING HUMAN APPROVAL |
| DASH0-BIZ-020 | BOM cost provenance and freshness | Dashboard can report stale materialized Rial values | DASH-1, DASH-2, DASH-5 | PENDING HUMAN APPROVAL |
| DASH0-BIZ-021 | Loss, recyclability, and exchange-rate semantics | Upstream BOM amounts may have an unapproved dimensional formula | DASH-1, DASH-2, DASH-5 | PENDING HUMAN APPROVAL |
| DASH0-BIZ-022 | Invalid, negative, and duplicate costing inputs | Current outcomes range from negative costs to overwrite or failure | DASH-1, DASH-2, DASH-3, DASH-5 | PENDING HUMAN APPROVAL |
| DASH0-BIZ-023 | Time, calendar, and period semantics | Cross-period totals and trends would be misleading | DASH-1, DASH-2, DASH-3, DASH-5 | PENDING HUMAN APPROVAL |
| DASH0-BIZ-024 | Breakdown, export, and drill-down meaning | Detail may not reconcile to KPIs or may disclose excess data | DASH-2, DASH-3 | PENDING HUMAN APPROVAL |

### Phase dependency key

- **DASH-1:** analytical contracts/read model and honest state/error boundaries.
- **DASH-2:** Cost Analysis implementation and its KPI calculations.
- **DASH-3:** breakdown/comparison/reporting presentation and export behavior.
- **DASH-5:** sensitivity analysis and access policy.

These phase labels reflect the supplied roadmap terminology and discovery
dependencies; they do not approve a phase design. No separate Dashboard
roadmap Markdown file currently exists in `docs/`.

## Evidence baseline and fact/choice boundary

The evidence set is `docs/dashboard-module-discovery.md`,
`docs/dash0-current-costing-audit.md`,
`docs/dash0-characterization-baselines.md`, the current Dashboard and costing
code, `tests/test_costing_characterization.py`, and the existing architecture,
factory, localization, and authorization documentation. Facts below describe
only current behavior. Options are candidates, not commitments.

---

## DASH0-BIZ-001

**Decision ID:** DASH0-BIZ-001  
**Title:** Meaning of Unit Cost

**Why this decision is required:**  
“Unit” could mean one configured product, one produced item in a stated period,
or another commercial unit. Without an approved definition, a currency value
cannot be aggregated or compared safely.

**Current implemented behavior:**  
The active Dashboard has no `unit_cost` field. Its closest placeholder is
`avg_cost_per_product = 0`. The costing engine returns
`Final_Production_Cost = stored BOM Rial/product + allocated subfields`; whether
that output is an approved unit cost is unresolved.

**Evidence:**
- `modules/dashboard/routes.py::cost_analysis`; `utils/cost_determiners.py::cost_aggregator`
- CB-01 returns `Final_Production_Cost = 2240.0`; CB-06 returns a genuine numeric zero

**Options:**

**Option A:** Treat each successful `Final_Production_Cost` as unit cost.  
**Implications:** Numerator is BOM plus allocated subfields; denominator is one
product unit implicit in current allocation; unit is intended Rial/product but
depends on unapproved category, production, and source-unit assumptions.

**Option B:** Define unit cost from an approved cost-pool numerator divided by
an approved produced/projected quantity.  
**Implications:** Requires explicit included/excluded pools, period, quantity,
and handling of products without valid denominators; may differ from the live
engine.

**Option C:** Do not expose Unit Cost until a separate accounting result is
approved and available.  
**Implications:** Honest but blocks the KPI and dependent comparisons.

**Technical recommendation, if applicable:**  
(non-binding) Store value, currency, physical unit, period, coverage, state,
and formula/version lineage together rather than returning a bare number.

**Required human answer:**  
Decision required: approve the numerator, denominator, currency/unit, period,
aggregation level, and incomplete-coverage behavior for Unit Cost.

**Affected roadmap phases:** DASH-1, DASH-2  
**Status:** PENDING HUMAN APPROVAL

---

## DASH0-BIZ-002

**Decision ID:** DASH0-BIZ-002  
**Title:** Meaning of Projected Total Cost

**Why this decision is required:**  
A projected total normally combines a per-unit value and quantity, but neither
the time horizon nor the eligible cost/result population is approved.

**Current implemented behavior:**  
The Dashboard placeholder `total_cost` is always zero and has no formula or
period. The engine produces one product result; it does not calculate a
Dashboard total.

**Evidence:**
- `modules/dashboard/routes.py::cost_analysis`; Dashboard discovery KPI inventory
- CB-04 shows prediction changes allocated subfields but not BOM, rather than calculating a projected total

**Options:**

**Option A:** Sum `unit cost × Predicted Production` for eligible products.  
**Implications:** Numerator becomes projected currency cost; quantity is the
weight and implied denominator is none. It requires common currency/horizon and
a policy for partial prediction/cost coverage.

**Option B:** Sum approved period cost pools directly.  
**Implications:** Avoids reconstructing totals from rounded unit values but
requires authoritative period pools and reconciliation rules.

**Option C:** Report only selected-product unit costs, with no projected total.  
**Implications:** Avoids a false aggregate but removes the current “کل هزینه”
concept.

**Technical recommendation, if applicable:**  
(non-binding) Return coverage counts/amounts beside any aggregate and never
convert excluded products into zero implicitly.

**Required human answer:**  
Decision required: define projected total numerator, horizon, currency,
eligible population, and incomplete-coverage policy.

**Affected roadmap phases:** DASH-1, DASH-2  
**Status:** PENDING HUMAN APPROVAL

---

## DASH0-BIZ-003

**Decision ID:** DASH0-BIZ-003  
**Title:** Meaning of Weighted Average Unit Cost

**Why this decision is required:**  
An arithmetic mean, production-weighted mean, and cost/quantity ratio answer
different questions and react differently to missing products.

**Current implemented behavior:**  
`avg_cost_per_product` is always zero. No weighting or denominator exists.

**Evidence:**
- `modules/dashboard/routes.py::cost_analysis`; `templates/dashboard/dashboard.html::renderDashboard`
- CB-01/CB-04 demonstrate product cost itself changes when prediction changes

**Options:**

**Option A:** Arithmetic mean: `sum(valid unit costs) / count(valid product configurations)`.  
**Implications:** Each configuration has equal weight; missing results change
both numerator and denominator and can bias comparisons.

**Option B:** Production-weighted mean: `sum(unit cost × approved quantity) /
sum(approved quantity)`.  
**Implications:** Unit is Rial/product; requires a common horizon and a decision
on zero/missing/negative quantities. Using prediction both inside current unit
cost and again as a weight needs explicit accounting approval.

**Option C:** Ratio of approved aggregate costs to approved aggregate output.  
**Implications:** Can reconcile to totals if sources share scope/horizon, but is
not necessarily the average of displayed unit-cost rows.

**Technical recommendation, if applicable:**  
(non-binding) Expose numerator, denominator, included/excluded counts, and
weight source in the analytical response.

**Required human answer:**  
Decision required: select the numerator, denominator/weight, entity counted,
horizon, and incomplete-coverage behavior.

**Affected roadmap phases:** DASH-1, DASH-2  
**Status:** PENDING HUMAN APPROVAL

---

## DASH0-BIZ-004

**Decision ID:** DASH0-BIZ-004  
**Title:** Meaning of Product Count

**Why this decision is required:**  
Catalog products, factory configurations, hierarchy paths, predicted products,
and successfully calculated results are not the same population.

**Current implemented behavior:**  
The KPI is constant zero. The repository has a global catalog plus
factory/category/subcategory BOM paths, while bulk cost results are keyed only
by product name and can overwrite duplicates.

**Evidence:**
- `modules/dashboard/routes.py::cost_analysis`; `modules/cost_calculation/routes.py::get_costs_bulk`
- Costing audit identity and duplicate-result findings

**Options:**

**Option A:** Count distinct business products.  
**Implications:** Requires an approved stable business product ID across factories.

**Option B:** Count distinct factory/category/subcategory/product configurations.  
**Implications:** The same named product can count more than once; aligns with BOM path identity.

**Option C:** Count only configurations with an `OK` calculation in the selected scope.  
**Implications:** Count becomes a data-coverage metric and must be paired with excluded/configured totals.

**Technical recommendation, if applicable:**  
(non-binding) Label counts precisely and provide configured, matched, calculated,
and excluded counts rather than overloading one number.

**Required human answer:**  
Decision required: identify the counted entity, deduplication key, filter scope,
and treatment of missing/failed/inactive configurations.

**Affected roadmap phases:** DASH-1, DASH-2  
**Status:** PENDING HUMAN APPROVAL

---

## DASH0-BIZ-005

**Decision ID:** DASH0-BIZ-005  
**Title:** Meaning of Top Cost Driver

**Why this decision is required:**  
“Top” may mean largest absolute contribution, largest share, largest change, or
most frequent driver; current driver keys lack approved accounting semantics.

**Current implemented behavior:**  
The placeholder is `—`. Cost output contains dynamic subfield keys plus `BOM`;
no ranking, aggregation, tie policy, or coverage rule exists.

**Evidence:**
- `modules/dashboard/routes.py::cost_analysis`; Dashboard discovery KPI inventory
- `utils/cost_determiners.py::cost_aggregator`; CB-01 dynamic `Labor`, `Energy`, and `BOM` contributions

**Options:**

**Option A:** Largest absolute approved contribution after summing by driver.  
**Implications:** Unit is Rial for the selected scope; requires additive/common
period values and a decision whether BOM is one driver.

**Option B:** Largest percentage of approved total cost.  
**Implications:** Denominator must be positive/complete; percentages can mislead
when records are excluded or negative adjustments exist.

**Option C:** Largest change versus a baseline/scenario.  
**Implications:** Requires two reproducible snapshots and belongs to comparative
or sensitivity analysis rather than a simple current-state KPI.

**Technical recommendation, if applicable:**  
(non-binding) Return driver ID, approved label, value, share, scope, tie flag,
and coverage instead of label text alone.

**Required human answer:**  
Decision required: define eligible drivers, ranking measure, aggregation,
denominator, tie/negative/incomplete behavior, and displayed unit.

**Affected roadmap phases:** DASH-1, DASH-2, DASH-3  
**Status:** PENDING HUMAN APPROVAL

---

## DASH0-BIZ-006

**Decision ID:** DASH0-BIZ-006  
**Title:** Business treatment of `selling_share_of_category`

**Why this decision is required:**  
The field has a material inverse effect on every factory contribution, but its
name alone does not prove that it is an allocation denominator.

**Current implemented behavior:**  
The first exact category match supplies `W`. For each subfield, current code
computes `raw_subfield / (W / 100) / PredictedProduction`. Thus a smaller
positive share increases allocated unit cost. The field comes from
`Data/Factories/<factory>/category_weights.json` at
`data.selling_share_of_category`.

**Evidence:**
- `utils/cost_determiners.py::__all_subfields_coster`
- CB-01: `W=50`, raw Labor `1000`, prediction `10` gives `200`; CB-03: `W=25` gives `400`

**Options:**

**Option A:** Retain division by share fraction.  
**Implications:** A 25% share expands a pool fourfold before production division;
zero fails, negatives invert sign, and shares above 100 reduce the pool.

**Option B:** Multiply raw pool by share fraction, then divide by production.  
**Implications:** A smaller share assigns less of the pool; this changes every
factory contribution and final unit product cost.

**Option C:** Use another allocation basis (normalized category shares, direct
cost assignment, or driver-specific allocation).  
**Implications:** Requires pool scope, category universe, normalization, and
driver rules; may prevent a single share from applying to every subfield.

**Technical recommendation, if applicable:**  
(non-binding) Preserve the characterization tests as “current behavior” and
version any approved replacement separately with dimensional examples.

**Required human answer:**  
Decision required: explicitly approve or reject current division, define the
field's business meaning/scale, explain its interaction with production
prediction, and approve the resulting effect on unit product cost.

**Affected roadmap phases:** DASH-1, DASH-2, DASH-5  
**Status:** PENDING HUMAN APPROVAL

---

## DASH0-BIZ-007

**Decision ID:** DASH0-BIZ-007  
**Title:** Business meaning, unit, and horizon of Predicted Production

**Why this decision is required:**  
The prediction is a denominator for all factory subfields, yet its physical
unit, factory/product scope, version, and time horizon are not established.

**Current implemented behavior:**  
The first exact product-name match in `ProductionPrediction.json` supplies a
raw numeric denominator. The engine divides every allocated subfield by it;
BOM remains outside the division.

**Evidence:**
- `utils/cost_determiners.py::__all_subfields_coster`
- CB-01 prediction `10` gives Labor `200`; CB-04 prediction `20` gives `100`, while BOM stays `2000`

**Options:**

**Option A:** Interpret as units of this product expected in an approved period.  
**Implications:** Factory pools and category share must refer to that same
factory/period; unit result is per predicted product unit.

**Option B:** Interpret as capacity or another planning quantity.  
**Implications:** The current denominator may not represent expected production
and KPI labels/horizons must say which quantity is used.

**Option C:** Use actual production, a selected scenario quantity, or separate
drivers by cost pool.  
**Implications:** Requires new sources/versioning; fixed and variable pools may
behave differently.

**Technical recommendation, if applicable:**  
(non-binding) Attach unit, start/end period, factory/configuration identity,
scenario/version, and provenance to every quantity.

**Required human answer:**  
Decision required: define Predicted Production's business meaning, physical
unit, horizon, scope, version, applicable pools, and whether BOM belongs inside
or outside any quantity allocation.

**Affected roadmap phases:** DASH-1, DASH-2, DASH-5  
**Status:** PENDING HUMAN APPROVAL

---

## DASH0-BIZ-008

**Decision ID:** DASH0-BIZ-008  
**Title:** Prediction zero, missing, invalid, negative, unmatched, and partial coverage

**Why this decision is required:**  
Multi-product analytics need a deterministic coverage policy; treating a bad
quantity as zero, exclusion, fallback, or total failure produces different KPIs.

**Current implemented behavior:**  
Zero raises `ZeroDivisionError`; a missing product raises `ValueError`; a
nonnumeric value raises `TypeError`; a missing file raises `FileNotFoundError`.
Negative numeric values calculate negative contributions. A failing item aborts
the current bulk response, so there is no partial analytical result contract.

**Evidence:**
- `utils/cost_determiners.py::__all_subfields_coster`; `modules/cost_calculation/routes.py::get_costs_bulk`
- CB prediction failure tests and missing-prediction-file test

**Options:**

**Option A:** Fail the entire selected analysis.  
**Implications:** Strong comparability but one product prevents all KPIs.

**Option B:** Exclude invalid/uncovered products and report explicit partial coverage.  
**Implications:** Results remain usable but denominators/counts must exclude the
same entities and users must see exclusions.

**Option C:** Apply an approved fallback/default for specified cases.  
**Implications:** Improves continuity but creates modeled rather than sourced
results and requires provenance; zero and negative still need distinct rulings.

**Technical recommendation, if applicable:**  
(non-binding) Represent per-configuration state and reason; never silently
coerce missing/invalid prediction to numeric zero.

**Required human answer:**  
Decision required: approve separate behavior for zero, missing field/file,
invalid, negative, product absent from table, duplicate match, and partial
coverage in multi-product analytics.

**Affected roadmap phases:** DASH-1, DASH-2, DASH-3, DASH-5  
**Status:** PENDING HUMAN APPROVAL

---

## DASH0-BIZ-009

**Decision ID:** DASH0-BIZ-009  
**Title:** Factory cost-driver identities, labels, meanings, units, and allocation

**Why this decision is required:**  
Technical names and display translations do not establish accounting scope,
fixed/variable behavior, currency, time basis, or the correct allocation driver.

**Current implemented behavior:**  
All four inspected factory summaries list the following six identifiers. The
engine discovers them from `Factory_Data.json.data.Subfield`, sums each matching
`Factory_Data_<identifier>.json.data.cost`, and applies the identical category
share and prediction division. Summary `Cost` and `PercentageOfAll` are ignored.

| Technical identifier | Current display label | Raw source | Current costing contribution | Meaning confidence |
|---|---|---|---|---|
| `AdministrativeandResearch` | `اداری و پژوهش` | `Factory_Data_AdministrativeandResearch.json` `data.cost[]` | Sum, then common share/prediction division | Label mapped; accounting contents/driver unconfirmed |
| `Payroll` | `حقوق و دستمزد` | `Factory_Data_Payroll.json` `data.cost[]` | Same | Label mapped; direct/indirect and period unconfirmed |
| `Overhead` | `سربار` | `Factory_Data_Overhead.json` `data.cost[]` | Same | Label mapped; included cost classes unconfirmed |
| `FinancialCosts` | `هزینه‌های مالی` | `Factory_Data_FinancialCosts.json` `data.cost[]` | Same | Label mapped; accounting treatment unconfirmed |
| `Depriciation` | `استهلاک` | misspelled persisted identifier in `Factory_Data_Depriciation.json` | Same | Display label mapped; asset basis/period unconfirmed |
| `NonOperationalCostsandIncomes` | `هزینه‌ها و درآمدهای غیرعملیاتی` | `Factory_Data_NonOperationalCostsandIncomes.json` | Same | Sign, inclusion, and “income” treatment unconfirmed |

Synthetic CB fixtures additionally use `Labor` and `Energy`; these are test
identifiers, not evidence that production factories define those drivers.

**Evidence:**
- Current `Data/Factories/*/Factory_Data.json`; `utils/localization.py::DISPLAY_MAPPINGS["departments"]`
- `utils/cost_determiners.py::__subfield_coster/__all_subfields_coster`; CB-01 and CB-05

**Options:**

**Option A:** Approve these six as common business drivers with the current common allocation.  
**Implications:** Requires confirmation that every raw `cost` is same currency
and period and that one allocation basis fits all six.

**Option B:** Approve the identifiers but define driver-specific meanings and allocation bases.  
**Implications:** More faithful accounting is possible, but requires metadata,
formula ownership, and potentially new source fields.

**Option C:** Treat subfields as configurable factory-local pools rather than a global taxonomy.  
**Implications:** Dashboard comparison needs mapping/grouping rules and cannot
infer semantic equivalence from raw names.

**Technical recommendation, if applicable:**  
(non-binding) Preserve persisted identifiers; add separately approved labels,
definitions, sign, currency, period, pool type, and driver metadata. Do not
infer a new Persian/business name from code.

**Required human answer:**  
Decision required: approve, rename, group, or reject each meaning; define raw
currency/time basis, signs, BOM eligibility, and whether each uses category
share, production, another driver, or no allocation.

**Affected roadmap phases:** DASH-1, DASH-2, DASH-3, DASH-5  
**Status:** PENDING HUMAN APPROVAL

---

## DASH0-BIZ-010

**Decision ID:** DASH0-BIZ-010  
**Title:** Analytical data-state taxonomy

**Why this decision is required:**  
Current Dashboard zeros and costing exceptions do not distinguish a valid zero
from no match, no calculation, missing configuration, incomplete data, or a
source failure.

**Current implemented behavior:**  
Dashboard always returns zero/empty values after authorization. Costing silently
turns any subfield read/parse/schema/sum exception into zero, while many BOM,
category, and prediction failures propagate.

**Evidence:**
- `modules/dashboard/routes.py::cost_analysis`; `utils/cost_determiners.py::__subfield_coster`
- CB-05 swallowed failures and CB-06 genuine zero

**Options:**

| Candidate (not final) | Possible trigger | User-facing implication | Possible API implication |
|---|---|---|---|
| `OK` | Approved calculation completed with required coverage | Show value and freshness | Value plus coverage/lineage |
| `NO_MATCH` | Valid filters resolve to no eligible configuration | “No matching products,” not zero | Successful response with empty result/state |
| `NOT_CALCULATED` | Eligible configuration exists but no accepted result exists | Invite permitted calculation/refresh | No numeric value; reason/action metadata |
| `FACTORY_UNCONFIGURED` | Registry factory lacks required operational mapping/files | Setup message without leaking unauthorized details | Scoped state, not a fabricated zero |
| `INCOMPLETE_INPUT` | Required rows/fields are absent or invalid | Identify safe remediation/partial coverage | Per-item issues and aggregate coverage |
| `SOURCE_ERROR` | Source cannot be read/parsed or service fails | Error/retry message; preserve genuine-zero distinction | Stable error code; appropriate HTTP/status contract |

**Option A:** Approve all six as distinct states.  
**Implications:** Most expressive; increases API/UI/testing work and requires
precise precedence when several triggers apply.

**Option B:** Merge selected states.  
**Implications:** Simpler contract but can hide whether users should change
filters, configure data, calculate, or retry.

**Option C:** Split states further (for example unauthorized, stale, partial,
invalid prediction, or unavailable source).  
**Implications:** Better actionability/auditability at greater complexity;
authorization should generally remain an HTTP access outcome, not business data.

**Technical recommendation, if applicable:**  
(non-binding) Separate authorization/transport errors, overall analysis state,
and per-configuration calculation state; never encode absence as numeric zero.

**Required human answer:**  
Decision required: approve, rename, merge, split, or reject each candidate;
define precedence, user wording, partial-aggregate rules, and API/HTTP semantics.

**Affected roadmap phases:** DASH-1, DASH-2, DASH-3  
**Status:** PENDING HUMAN APPROVAL

---

## DASH0-BIZ-011

**Decision ID:** DASH0-BIZ-011  
**Title:** Dashboard analysis factory scope

**Why this decision is required:**  
Single-factory analysis, global aggregation, and multi-factory comparison have
different identity, unit, permission, and KPI contracts.

**Current implemented behavior:**  
The UI offers “all factories.” A factory query validates FACTORY Dashboard READ;
no factory query requires GLOBAL Dashboard READ. Both return identical empty data.

**Evidence:**
- `modules/dashboard/routes.py::dashboard/cost_analysis`
- Dashboard discovery factory-context and authorization sections

**Options:**

**Option A:** One factory per analysis.  
**Implications:** Simplest model and permission boundary; filters use one
operational hierarchy, KPIs avoid cross-factory identity/currency/period joins,
but comparison requires separate later work.

**Option B:** Global/all-factory aggregated analysis.  
**Implications:** Requires GLOBAL permission, compatible periods/units, composite
product identity, coverage reconciliation, and UX that explains an aggregate.

**Option C:** Multi-factory comparison without collapsing factories.  
**Implications:** Requires access to every selected factory, factory dimension
in every row/series, comparable KPI definitions, multi-select UX, and higher
query/presentation complexity.

**Technical recommendation, if applicable:**  
(non-binding) Keep factory scope explicit in request and response and validate
every included factory server-side. The roadmap's proposed V1 choice, if any,
must not be treated as approval.

**Required human answer:**  
Decision required: explicitly approve V1 scope, meaning of “all factories,”
permitted combinations, default selection, and whether aggregation and/or
comparison are in scope.

**Affected roadmap phases:** DASH-1, DASH-2, DASH-3, DASH-5  
**Status:** PENDING HUMAN APPROVAL

---

## DASH0-BIZ-012

**Decision ID:** DASH0-BIZ-012  
**Title:** Product hierarchy filters and empty-filter semantics

**Why this decision is required:**  
Factory → Category → Subcategory → Product is both a navigation hierarchy and
a potential analytical scope. Empty children could mean all descendants,
unselected/incomplete input, or no match.

**Current implemented behavior:**  
Factory options are access-filtered registry records; categories are five
hard-coded values. Subcategory/product loaders call nonexistent
`/api/filter_options`. The analysis API ignores category, subcategory, and
product query values.

**Evidence:**
- `modules/dashboard/routes.py::dashboard/cost_analysis`
- `templates/dashboard/dashboard.html::loadSubcategories/loadProducts`; Dashboard discovery filter inventory

**Options:**

**Option A:** Empty at each level means all authorized descendants.  
**Implications:** Convenient aggregation but can broaden queries unexpectedly;
each KPI must state the resulting population.

**Option B:** Require a complete leaf selection for cost analysis.  
**Implications:** Unambiguous configuration and simpler joins; prevents category
and portfolio analytics.

**Option C:** Give each level explicit “all” versus “not selected” states.  
**Implications:** Clearest intent but needs richer UX/API validation and defined
behavior when parent selections change.

**Technical recommendation, if applicable:**  
(non-binding) Source hierarchy dynamically from an authorized read model and
send explicit scope operators rather than relying on empty strings.

**Required human answer:**  
Decision required: approve hierarchy source/order, cascading behavior, and the
meaning of empty category, subcategory, and product filters at every level.

**Affected roadmap phases:** DASH-1, DASH-2, DASH-3  
**Status:** PENDING HUMAN APPROVAL

---

## DASH0-BIZ-013

**Decision ID:** DASH0-BIZ-013  
**Title:** Product identity and same-name resolution

**Why this decision is required:**  
Current paths imply composite identity, but prediction lookup and bulk output
use product name, permitting collisions across factories/hierarchies.

**Current implemented behavior:**  
BOM location is factory/category/subcategory/product. Prediction lookup is
product-name-only within a factory file. Bulk response keys are product names,
so later same-name results overwrite earlier ones.

**Evidence:**
- `utils/load_data.py::load_bom`; `utils/cost_determiners.py::__all_subfields_coster`
- `modules/cost_calculation/routes.py::get_costs_bulk`; costing audit duplicate inventory

**Options:**

**Option A:** Product name is globally unique identity.  
**Implications:** Requires enforced uniqueness and a rule for existing same-name configurations.

**Option B:** Identity is factory + category + subcategory + product name.  
**Implications:** Matches BOM paths; same business product may have multiple
configurations and needs a separate grouping key for portfolio analytics.

**Option C:** Introduce/use a stable product ID plus factory configuration ID.  
**Implications:** Most robust joins but requires mapping/migration and careful
backward compatibility; this dossier does not authorize it.

**Technical recommendation, if applicable:**  
(non-binding) Never use display name alone as an API result key; retain all
identity dimensions and report ambiguous matches.

**Required human answer:**  
Decision required: approve business product and configuration identities,
same-name behavior across factories/paths, prediction joins, duplicate handling,
and Dashboard resolution/display.

**Affected roadmap phases:** DASH-1, DASH-2, DASH-3, DASH-5  
**Status:** PENDING HUMAN APPROVAL

---

## DASH0-BIZ-014

**Decision ID:** DASH0-BIZ-014  
**Title:** Dashboard page, factory, GLOBAL, and “all factories” permissions

**Why this decision is required:**  
Current page admission differs from documentation, and the UI advertises a
global action that factory-only users cannot execute.

**Current implemented behavior:**  
`/dashboard` admits a user with at least one accessible factory or GLOBAL READ.
Factory analysis requires FACTORY `dashboard=READ`; no-factory analysis requires
GLOBAL READ. The authorization matrix describes the page itself as GLOBAL READ.
The selector always initially offers “all factories.” Top-level roles have
implicit full access.

**Evidence:**
- `modules/dashboard/routes.py::dashboard/cost_analysis`
- `docs/authorization-matrix.md`; Dashboard discovery authorization section

**Options:**

**Option A:** Page requires GLOBAL READ; factory-only users cannot enter.  
**Implications:** Matches older documentation but makes FACTORY Dashboard grants
insufficient for the page that would use them.

**Option B:** Keep mixed-scope page admission and show only authorized actions.  
**Implications:** Factory-only users can analyze allowed factories; “all” must
be hidden/disabled unless separately authorized.

**Option C:** Separate global and factory Dashboard entry points/views.  
**Implications:** Clearest policy/UX but more routes/navigation/contracts.

**Technical recommendation, if applicable:**  
(non-binding) Enforce authorization server-side for every request and derive
visible scope choices from effective permissions; UI hiding is not enforcement.

**Required human answer:**  
Decision required: approve page access, GLOBAL versus FACTORY READ meanings,
“all factories” authorization, factory-specific analysis, and expected UX for
users holding only one scope.

**Affected roadmap phases:** DASH-1, DASH-2, DASH-3, DASH-5  
**Status:** PENDING HUMAN APPROVAL

---

## DASH0-BIZ-015

**Decision ID:** DASH0-BIZ-015  
**Title:** Sensitivity visibility for general parameters

**Why this decision is required:**  
Dashboard READ does not necessarily grant access to material prices, currencies,
or other general parameters; a simulator could reveal their values indirectly.

**Current implemented behavior:**  
Sensitivity is inaccessible placeholder markup. `general_parameters` is a
separate GLOBAL permission. No sensitivity API or policy exists.

**Evidence:**
- `templates/dashboard/dashboard.html` sensitivity placeholder
- `docs/authorization-matrix.md`; `modules/general_parameters/routes.py`

**Options:**

**Option A:** Require both Dashboard READ and General Parameters READ to view or simulate actual values.  
**Implications:** Least privilege; some Dashboard users lose sensitivity access.

**Option B:** Allow simulation with abstract deltas but conceal actual source values.  
**Implications:** Reduces direct disclosure but outputs may still permit inference.

**Option C:** Dashboard READ alone permits values and simulation.  
**Implications:** Simpler role experience but broadens sensitive business-data visibility.

**Technical recommendation, if applicable:**  
(non-binding) Authorize both parameter retrieval and scenario execution on the
server; assess inference through outputs, exports, and error messages.

**Required human answer:**  
Decision required: may `dashboard=READ` without `general_parameters=READ` see
actual general values, enter overrides, run simulations, and view/export results?

**Affected roadmap phases:** DASH-5  
**Status:** PENDING HUMAN APPROVAL

---

## DASH0-BIZ-016

**Decision ID:** DASH0-BIZ-016  
**Title:** Sensitivity visibility for factory parameters

**Why this decision is required:**  
Factory cost pools and production inputs may be more sensitive than derived
Dashboard results and have a separate FACTORY permission.

**Current implemented behavior:**  
No sensitivity implementation exists. `factory_parameters` and `dashboard` are
separate factory-scoped modules; Dashboard access does not confer parameter access.

**Evidence:**
- `templates/dashboard/dashboard.html` sensitivity placeholder
- `docs/authorization-matrix.md`; `modules/factory_parameters/routes.py`

**Options:**

**Option A:** Require Dashboard READ and matching-factory Factory Parameters READ.  
**Implications:** Preserves source permission boundaries; reduces simulator availability.

**Option B:** Permit abstract changes without revealing source values.  
**Implications:** Useful for some users but derived output can leak baselines.

**Option C:** Dashboard READ alone permits factory parameter visibility/simulation.  
**Implications:** Broadens access to potentially sensitive cost and production data.

**Technical recommendation, if applicable:**  
(non-binding) Check every selected factory independently and avoid cross-factory
scenario output unless the user holds all required grants.

**Required human answer:**  
Decision required: may a user without matching `factory_parameters=READ` see,
override, simulate, infer, or export factory-level parameter values/results?

**Affected roadmap phases:** DASH-5  
**Status:** PENDING HUMAN APPROVAL

---

## DASH0-BIZ-017

**Decision ID:** DASH0-BIZ-017  
**Title:** Real source edits versus what-if override mutability

**Why this decision is required:**  
Users must know whether a scenario changes authoritative material/BOM/factory
files or is an ephemeral analytical input.

**Current implemented behavior:**  
Existing parameter/product modules persist edits through their own endpoints.
Dashboard has no mutation endpoint; its sensitivity pane is a placeholder.

**Evidence:**
- General/factory/product save routes documented in `docs/project-architecture.md`
- `modules/dashboard/routes.py` has GET-only routes

**Options:**

**Option A:** Sensitivity overrides are non-persistent and never edit sources.  
**Implications:** Clear what-if boundary; reproducibility requires exportable
scenario inputs or separately saved scenario records.

**Option B:** Persist named scenarios separately from authoritative parameters.  
**Implications:** Supports collaboration/audit but needs ownership, retention,
permissions, and explicit promotion rules.

**Option C:** Permit authorized application of scenarios to real sources.  
**Implications:** High-risk mutation requiring source-module MODIFY permissions,
validation, confirmation, audit, rollback, and recalculation policy.

**Technical recommendation, if applicable:**  
(non-binding) Default architecture should keep override input separate from
source mutation; do not reuse source-save endpoints implicitly.

**Required human answer:**  
Decision required: explicitly approve whether scenarios are non-persistent,
session-only, saved separately, shareable, or promotable to real parameters,
and who may perform each action.

**Affected roadmap phases:** DASH-5  
**Status:** PENDING HUMAN APPROVAL

---

## DASH0-BIZ-018

**Decision ID:** DASH0-BIZ-018  
**Title:** Cost freshness, storage, caching, and “last updated”

**Why this decision is required:**  
Accuracy, latency, reproducibility, and sensitivity depend on whether results
are live or versioned snapshots.

**Current implemented behavior:**  
Cost APIs calculate on request from stored BOM/factory JSON. Dashboard does not
call them and returns constants. No canonical cost snapshot, cache, schedule,
refresh action, or Dashboard timestamp exists.

**Evidence:**
- `modules/cost_calculation/routes.py`; `utils/cost_determiners.py::cost_aggregator`
- Dashboard discovery freshness section; CB-01 verifies a calculation does not write inputs

**Options:**

**Option A:** Live calculation on each request.  
**Implications:** Reflects current files but can be slow/non-reproducible and can
partially change during multi-product reads; “last updated” could mean request time.

**Option B:** Persisted calculation snapshot triggered explicitly.  
**Implications:** Reproducible/versionable and fast to read; may be stale and
needs trigger permission and lineage timestamps.

**Option C:** Scheduled snapshots.  
**Implications:** Predictable portfolio reports; freshness bounded by schedule
and failures need status/monitoring.

**Option D:** Cached live results.  
**Implications:** Balances latency but needs cache keys/invalidation for every
source/version and clear calculation versus cache timestamps.

**Technical recommendation, if applicable:**  
(non-binding) Define separate source-as-of, calculated-at, cached-at, and
scenario timestamps; retain formula/source versions for reproducibility.

**Required human answer:**  
Decision required: choose or combine freshness models, define staleness limits,
refresh authority, invalidation, reproducibility, and the user-facing meaning
of “last updated.”

**Affected roadmap phases:** DASH-1, DASH-2, DASH-3, DASH-5  
**Status:** PENDING HUMAN APPROVAL

---

## DASH0-BIZ-019

**Decision ID:** DASH0-BIZ-019  
**Title:** Business rounding, precision, tolerance, comparisons, and ties

**Why this decision is required:**  
Accounting rounding affects reconciliation and ranking; it is distinct from a
test tolerance used only for binary floating-point comparisons.

**Current implemented behavior:**  
The engine rounds nothing. Product save normalizes some derived BOM values to
three decimals. Dashboard displays currency with two decimals, count with zero,
and chart percentage rounded by presentation. CB fixtures use exact binary
values specifically to avoid introducing a tolerance.

**Evidence:**
- `utils/cost_determiners.py`; product save/browser derivation in costing audit
- `templates/dashboard/dashboard.html::formatCurrency`; characterization baseline scope

**Options:**

**Option A:** Round only for display; aggregate full stored precision.  
**Implications:** Best computational precision but displayed rows may not sum
to displayed totals.

**Option B:** Round at approved accounting boundaries.  
**Implications:** Reconciliation improves if boundaries/mode are explicit, but
results differ depending on per-line/per-product/per-total order.

**Option C:** Store minor currency units/decimal values and define comparison tolerance separately.  
**Implications:** More deterministic money handling; requires migration/interface decisions.

**Technical recommendation, if applicable:**  
(non-binding) Specify currency precision and rounding mode/boundary; keep
technical floating-point tolerance confined to implementation/tests and never
present it as a business materiality tolerance.

**Required human answer:**  
Decision required: approve display decimals, stored/calculation precision,
rounding mode and stage, allocation remainder handling, ranking equality/tie
behavior, and any accounting/materiality tolerance.

**Affected roadmap phases:** DASH-1, DASH-2, DASH-3, DASH-5  
**Status:** PENDING HUMAN APPROVAL

---

## DASH0-BIZ-020

**Decision ID:** DASH0-BIZ-020  
**Title:** BOM cost provenance and material-price freshness

**Why this decision is required:**  
The engine uses materialized Rial amounts, not current general parameters, so a
Dashboard “current cost” may reflect an older BOM save.

**Current implemented behavior:**  
Only BOM `cost_of_material_in_rial` is summed. General price changes do not
recalculate BOMs; the product page derives values in the browser and an
explicit save is required. No accepted as-of/version field joins the result.

**Evidence:**
- `utils/cost_determiners.py::__BOM_coster`; `utils/updaters.py::product_cost_recalculation` stub
- CB-02 proves unrelated price/usage values are ignored

**Options:**

**Option A:** Dashboard uses stored BOM costs and exposes their accepted save/as-of lineage.  
**Implications:** Reproducible but potentially stale; needs a staleness policy.

**Option B:** Recompute BOM from current approved general parameters on analysis.  
**Implications:** Fresher but changes current behavior, requires an authoritative
server formula, and complicates historical reproduction/sensitivity.

**Option C:** Use versioned calculated snapshots linking BOM and price versions.  
**Implications:** Strong lineage; requires snapshot/version infrastructure.

**Technical recommendation, if applicable:**  
(non-binding) Do not label a stored BOM amount “current” without source-version
and as-of metadata.

**Required human answer:**  
Decision required: approve the BOM source used by analytics, acceptable age,
recalculation trigger/owner, version/date semantics, and stale-data behavior.

**Affected roadmap phases:** DASH-1, DASH-2, DASH-5  
**Status:** PENDING HUMAN APPROVAL

---

## DASH0-BIZ-021

**Decision ID:** DASH0-BIZ-021  
**Title:** Loss, recyclability, and exchange-rate semantics in upstream BOM cost

**Why this decision is required:**  
Dashboard trust depends on upstream BOM values whose current browser formula
contains unapproved percentage and exchange-rate conventions.

**Current implemented behavior:**  
The product browser computes `costPerUnit × usage × costCurrency ×
max(0, 1 - lost × recyclability)` without dividing percentage-labeled inputs by
100. For non-IRR currency it looks for a material whose name equals the
currency. Costing later trusts the saved Rial value without recomputation.

**Evidence:**
- `templates/product/product_page.html` derivation functions; costing audit BOM lineage
- CB-02 confirms only the saved result reaches the engine

**Options:**

**Option A:** Approve current stored values as authoritative despite derivation provenance.  
**Implications:** Dashboard can proceed technically but may institutionalize an
unapproved upstream convention.

**Option B:** Approve corrected/explicit fraction, percentage, recovery, and exchange-rate semantics.  
**Implications:** Requires formula/version decisions outside this dossier and
potential recomputation; no formula change is authorized here.

**Option C:** Exclude or flag products without an approved BOM calculation version.  
**Implications:** Improves trust but reduces coverage.

**Technical recommendation, if applicable:**  
(non-binding) Version BOM derivation and expose provenance/validation state to
analytics before aggregating.

**Required human answer:**  
Decision required: define loss/recyclability scales and relationship, exchange
rate source/direction/as-of, clamp behavior, and eligibility of legacy BOMs.

**Affected roadmap phases:** DASH-1, DASH-2, DASH-5  
**Status:** PENDING HUMAN APPROVAL

---

## DASH0-BIZ-022

**Decision ID:** DASH0-BIZ-022  
**Title:** Invalid, negative, over-range, and duplicate costing inputs

**Why this decision is required:**  
Current engine behavior is inconsistent: some failures raise, subfield failures
become zero, negative denominators produce signed results, and duplicate names
collapse or select the first match.

**Current implemented behavior:**  
Duplicate BOM materials and subfields collapse in dictionaries; category and
prediction `.index()` choose first matches; bulk same-name products overwrite.
Zero denominators raise; numeric negatives and shares above 100 are not rejected;
nonnumeric values generally fail unless caught inside subfield loading.

**Evidence:**
- `utils/cost_determiners.py` dictionary and `.index()` behavior
- Costing audit candidate edge inventory; characterization category/prediction/subfield failure tests

**Options:**

**Option A:** Reject invalid/range/duplicate data and fail affected analysis.  
**Implications:** Strong integrity but lower availability and requires validation ownership.

**Option B:** Exclude affected configurations with explicit incomplete coverage.  
**Implications:** Partial analytics remain possible; all KPI denominators need consistent exclusion.

**Option C:** Define approved meanings for selected negatives/duplicates and reject the rest.  
**Implications:** Supports adjustments or repeated lines only with explicit sign,
aggregation, uniqueness, and precedence contracts.

**Technical recommendation, if applicable:**  
(non-binding) Validate at ingestion and calculation boundaries and preserve all
duplicates until an approved aggregation rule handles them.

**Required human answer:**  
Decision required: approve valid ranges/signs and exact policies for duplicate
materials, categories, predictions, subfields, and product identities, plus
failure/exclusion/fallback behavior.

**Affected roadmap phases:** DASH-1, DASH-2, DASH-3, DASH-5  
**Status:** PENDING HUMAN APPROVAL

---

## DASH0-BIZ-023

**Decision ID:** DASH0-BIZ-023  
**Title:** Analytical time horizon, calendar, and period alignment

**Why this decision is required:**  
Costs, shares, and prediction cannot be aggregated dimensionally without a
shared period; future trends need date semantics even though UI dates must be Jalali.

**Current implemented behavior:**  
Dashboard has no date/period filter or payload field. Factory pools and
Predicted Production have no enforced shared period. Application localization
requires Jalali display/input while canonical storage remains machine-readable.

**Evidence:**
- Dashboard discovery date/time inventory
- `docs/jalali-date-localization.md`; costing audit unresolved subfield/prediction time basis

**Options:**

**Option A:** One explicit current planning period selected by source version.  
**Implications:** Simpler V1 but needs approved period and as-of labeling.

**Option B:** User-selectable monthly/yearly/horizon periods.  
**Implications:** Requires historical/versioned sources, aggregation grain,
timezone boundaries, and Jalali UI/canonical API conversion.

**Option C:** No temporal claim; show only configuration-level calculation.  
**Implications:** Avoids false time aggregation but limits projected/trend KPIs.

**Technical recommendation, if applicable:**  
(non-binding) Keep canonical timestamps/period keys in APIs and use Jalali only
for end-user display/input, with an explicit application timezone.

**Required human answer:**  
Decision required: define horizon/grain, alignment of every input, timezone,
Jalali interaction, historical retention, and behavior for mixed periods.

**Affected roadmap phases:** DASH-1, DASH-2, DASH-3, DASH-5  
**Status:** PENDING HUMAN APPROVAL

---

## DASH0-BIZ-024

**Decision ID:** DASH0-BIZ-024  
**Title:** Breakdown, drill-down, ranking, and export semantics

**Why this decision is required:**  
Charts/table/CSV exist as empty shells, but dimensions, reconciliation,
coverage, units, and disclosure policy are unapproved.

**Current implemented behavior:**  
Category bar, subcategory pie, detail table, and client CSV consume empty arrays.
The table expects factory/category/subcategory/product/cost; CSV exports those
fields after any successful empty response.

**Evidence:**
- `templates/dashboard/dashboard.html` chart/table/export functions
- `modules/dashboard/routes.py::cost_analysis`; Dashboard discovery chart/table inventory

**Options:**

**Option A:** Breakdowns reconcile exactly to an approved KPI population.  
**Implications:** Requires consistent identity, exclusion, rounding, driver,
period, and “other/unallocated” rules.

**Option B:** Treat charts as independent analytical views.  
**Implications:** More flexible, but each needs its own numerator/denominator and
users may incorrectly expect reconciliation.

**Option C:** Defer detail/export until access and semantic contracts are approved.  
**Implications:** Reduces disclosure/misinterpretation risk but limits DASH-3.

**Technical recommendation, if applicable:**  
(non-binding) Include applied scope, freshness, state, coverage, units, and
stable IDs in downloadable output; protect against spreadsheet injection and
enforce the same server-side permissions as the visible analysis.

**Required human answer:**  
Decision required: approve required dimensions, reconciliation target,
ranking/ties, drill-down depth, export fields/format, Jalali versus canonical
dates, and permissions for each detail level.

**Affected roadmap phases:** DASH-2, DASH-3  
**Status:** PENDING HUMAN APPROVAL

---

## Human approval worksheet

For each Decision ID, the owner should record: approved option or bespoke rule;
precise definitions and examples; owner/date; affected scope; exceptions;
effective version; and whether follow-up accounting, product, security, or data
governance review is required. Silence, a technical recommendation, or current
behavior is **not** approval.

## Completion report and mandatory stop

1. **Dossier path:** `docs/dash0-business-decision-dossier.md`.
2. **Total decision items:** 24, all `PENDING HUMAN APPROVAL`.
3. **Critical decisions blocking DASH-2:** DASH0-BIZ-001 through 014 and
   DASH0-BIZ-018 through 024, as detailed in the summary table.
4. **Decisions blocking Cost Analysis:** KPI definitions (001–005), allocation
   and prediction (006–008), drivers/states/scope/hierarchy/identity/access
   (009–014), and freshness/rounding/provenance/input/time/detail contracts
   (018–024).
5. **Decisions blocking Sensitivity:** DASH0-BIZ-006 through 009,
   DASH0-BIZ-011, DASH0-BIZ-013 through 023 where marked DASH-5, especially
   visibility and persistence decisions 015–017.
6. **Technical recommendations included:** Yes; each is explicitly non-binding.
7. **No decision finalized:** Confirmed.
8. **No business logic changed:** Confirmed; this is documentation only.
9. **Human gate:** DASH-0.4 must wait for explicit human approval. Review this
   dossier together with `docs/dash0-current-costing-audit.md` and
   `docs/dash0-characterization-baselines.md`. Do not start DASH-0.4 automatically.
