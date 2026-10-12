# PR-09A — current-data visual analytics and shared-baseline lab

PR-09A is now merged as GitHub #45, main
`fc373ca92e97c91d3d3b4a1a181096cbdf733c37`. The implementation-time results
below are retained as historical PR evidence. Current hardening, regression,
dependency and release status is in [PR-10](pr10-dashboard-release-readiness.md).

Base: merged PR-09 / GitHub #44, `fb610755d04561649a6a35ebc3dbd287070bad17`.
The merged Persian Sensitivity UI was verified before implementation. No PR-10
work, historical cost-series endpoint, historical snapshots, persistence, source
editing, scenario sharing, forecasting, optimization or Monte Carlo is included.
Installed period bindings describe the current operational inputs and planning
population; neither fingerprints nor period dates assert historical observations.

## Read-only Cost Analysis wrapper

`GET /api/dashboard/cost-analysis/visuals` accepts the exact query contract of
`GET /api/cost_analysis`: one authorized canonical factory, explicit category,
subcategory and product (including explicit `__ALL__`), optional installed period
and matching canonical start/end. Existing callers and `/api/cost_analysis` remain
compatible. HTTP outcomes and authorization are shared with the canonical route.
No additional general/factory source-module grants are required for this already
authorized derived Cost Analysis result.

The response is `{version:"1", analysis:<canonical PR-06 report>, visuals:{...}}`.
The canonical report is calculated once. `cost_visuals` only reads that accepted
report: no loader, sources, second calculation or write. All analytical monetary
arithmetic uses the existing Python Decimal context; wire values are exact fixed
Decimal strings. `DashboardVisuals.adaptCost` explicitly validates and unwraps the
response, preserving `DashboardReport` validation, immutable acceptance, scope
checks and the original full-report CSV. Local chart focus never edits the accepted
selection, allocation denominator, KPI, coverage or export population.

`visuals` includes:

- `factor_ids`: BOM and the six exact existing pool IDs, with shared UI colors.
- `composition`: four largest absolute contributions and OTHER; original amounts
  and shares remain in `analysis.breakdowns.drivers`. OTHER carries member IDs.
  Donut is available only with nonnegative contributions and positive total.
- `products`: exact four-part identities, prediction, unit/projected costs, seven
  unit components, seven projected components and per-product reconciliation.
- `hierarchy`: category → subcategory → exact configuration. Rectangle areas and
  monetary grouping use **IRR/period**, not summed per-unit costs. Signed or
  zero-total populations retain exact tables rather than invalid rectangles.
- `materials`: projected BOM contribution by material, every contributing original
  row identity, unit/period amounts, exact share and cumulative share. The
  denominator is the **selected calculated projected BOM total**. Signed/zero
  data uses bars, without interpreting cumulative shares as a Pareto distribution.
  `material_reconciliation` exposes authoritative BOM minus grouped leaf total.
- `coverage`, `period`, calculated-population label and excluded rows with reasons.

Factory drilling stops at supported allocated pool contributions; depth-3 V2
items are not allocated to products. Raw whole-factory pool totals stay separate
in the canonical report. Duplicate BOM material rows remain independently
inspectable. Heatmap cells are IRR/product; scatter x is product/period, y is
IRR/product and bubble area is projected IRR/period. Signed costs use a fixed point
and explicit table. Unavailable/excluded configurations are never plotted as zero.

## Shared-baseline POST

`POST /api/dashboard/sensitivity/visual-analysis` has the strict request schema in
[dashboard-visual-analysis-request.schema.json](dashboard-visual-analysis-request.schema.json).
Existing PR-08 GET/POST routes are unchanged. JSON duplicate keys, non-finite
constants, extra keys and request query parameters are rejected. Required fields
are the PR-08 explicit `factory`, `category`, `subcategory`, exact product
reference and installed `period`, plus exactly two `scenarios` with IDs A and B:

```json
{
  "factory": "factory-canonical",
  "category": "category",
  "subcategory": "sub",
  "product": "reference-from-authorized-filter-options",
  "period": "P",
  "scenarios": [
    {"id": "A", "overrides": []},
    {"id": "B", "overrides": []}
  ],
  "experiment": null
}
```

Each override uses the PR-08 grammar `{parameter_id,mode,value}` with an exact
canonical Decimal **string**, mode `absolute` or `percent_change`. Absolute means
the final hypothetical value; percent change is relative to the captured source
baseline. No client baseline, mapping, snapshot token or persistent scenario ID
is accepted. Empty input is not zero. Domain validation does not clip values.
Schema date format also requires runtime canonical ISO dates and exact binding
matches; selection whitespace/control characters are rejected at runtime.

Optional experiment shapes:

```json
{"type":"tornado","ranges":[
  {"parameter_id":"pool:Payroll","mode":"absolute","low":"0","high":"2000"}
]}
```

```json
{"type":"one_factor","axes":[
  {"parameter_id":"pool:Payroll","mode":"percent_change","values":["-10","0","10"]}
]}
```

```json
{"type":"two_factor","axes":[
  {"parameter_id":"pool:Payroll","mode":"absolute","values":["0","1000"]},
  {"parameter_id":"pool:Overhead","mode":"absolute","values":["0","500"]}
]}
```

All parameter IDs must come from the fresh authorized registry. Aliases are
resolved only with the existing server-owned source coordinates. Aliased axes
and duplicate Tornado drivers fail safely; they are not independent drivers.
Low must not exceed high. Tornado measures each chosen low/high with all other
inputs fixed at baseline, ranks the measured absolute **unit-cost high-minus-low
impact**, and does not claim global importance or probability. Curves use actual
supplied point values, without a JavaScript business formula or fitted model.
Two-factor points are Cartesian combinations. MATHEMATICAL_ZERO controls remain
available; their combined effects can become nonzero.

Authorization and grammar/work checks precede operational capture where possible.
One existing read-only loader captures inputs once and calculates baseline once.
A, B and all valid experiment points call the existing pure `calculate_cost`
engine with normalized `CostOverrides` against **the same immutable inputs**.
Every POST uses fresh sources; a preceding registry GET supplies no baseline.
The UI submits both current drafts for advanced experiments and accepts all charts
only from that one response; a changed returned baseline is explained in Persian.

The response preserves the PR-08 version/context/registry/redaction whitelist and
adds `visual_version:"1"`, `scenarios:[{id,result,effective_overrides}]`,
`comparisons`, `experiment`, `evaluation_budget` and `baseline_context`.
Comparison keys are `A_minus_baseline`, `B_minus_baseline` and `B_minus_A`.
Each metric declares direction, reference, target, unit and exact percentage
denominator (the reference value). Reference zero gives null percentage with
`NOT_APPLICABLE`. Projected deltas subtract actual projected results; they are
never estimated by multiplying a unit delta by one side's prediction.

Waterfalls retain reference/target unit costs and all seven output-component
differences. These are **output differences, not independent causal input
attribution**. `reconciliation` and `technical_reconciliation` expose a finite
Decimal residue rather than changing leaf contributions. Backend-computed start,
end, offset and size support plotting without browser monetary arithmetic.

Compact experiment points contain permitted input IDs, modes, exact supplied
values/source units, backend-normalized final values, effective inputs, exact output metrics, baseline deltas and
typed state. No full BOM or registry is repeated per point. Domain-invalid samples
have null metrics, a safe typed issue and explicit valid/invalid counts. Charts
omit unavailable cells; tables explain them and never color them as zero.

## Permissions, limits and lifecycle

Dashboard READ authorizes the selected derived baseline/output costs. General
controls additionally need global general_parameters READ; factory controls need
factory_parameters READ on this exact factory. Group checks repeat in POST.
Dashboard-only users can compare empty A/B drafts. Prediction, raw pools, source
prices and FX remain omitted according to PR-08. The UI/export never reconstructs
omitted inputs from costs, fetches them elsewhere or adds source grants for charts.

- Request body: 64 KiB, including chunked/cached reads; Decimal length: 128 chars.
- Overrides: at most 64 per scenario.
- Tornado: at most 10 ranges (20 low/high evaluations).
- One factor: at most 41 supplied points.
- Two factors: at most 11 values per axis (121 combinations).
- Hard evaluation budget: 200. **Reserved work = 1 baseline + 1 A + 1 B + every
  requested sample**, including domain-invalid sample reservations. Executed
  counts include only actual engine calls; domain-invalid normalization is not a
  fabricated calculation. Current shape limits allow at most 124 engine calls.

HTTP 400 handles malformed specifications/overrides and aliases; 403 permission;
404 unknown factory; 413 size; 422 unavailable baseline/binding; 503 hierarchy;
500 safe calculation failure. Existing login redirect behavior remains intact.

A/B edits, selection, experiment ranges, refresh and Reset immediately invalidate
comparison, chart instances, exact popovers and CSV. Abort plus generation/scope/
draft-revision guards discard late responses. Reset clears both drafts/settings
and retains the latest authorized baseline for the same context, with no request
or save. Observed permission/session failures clear protected context and drafts.
Advanced charts mount on opening and dispose on closing; tab changes dispose
hidden charts. Exact-value tables remain usable when ECharts fails. Tooltips use
richText, labels use textContent, and exports use original strings, UTF-8 BOM,
CRLF, quoting and formula-injection protection preserving legitimate negatives.

## Verification

Tests use the existing isolated Flask/Chromium harness and V2 fixtures, without
importing operational startup. Source inventories, SHA-256 and file/directory
mtimes are checked for successful, invalid and unauthorized requests.

Commands used (from the repository root; `$PY` was
`/workspace/.engcost-venv/bin/python`):

```bash
$PY -m pytest tests/test_dashboard_visual_analysis.py tests/test_dashboard_visual_model.py tests/test_dashboard_sensitivity_model.py tests/test_dashboard_numbers.py -q --tb=short
PYTHONPATH=/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/site-packages DASHBOARD_UI_EVIDENCE_DIR=work/pr09a-screenshots $PY -m pytest tests/test_dashboard_visual_frontend.py -q --tb=short
PYTHONPATH=/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/site-packages $PY -m pytest tests/test_dashboard_frontend.py tests/test_dashboard_sensitivity_frontend.py -q --tb=short
APP_DATA_FILE=$PWD/work/pr09a-validation/profiles-branch.json APP_SECRET_KEY=pr09a-isolated-test $PY -m pytest tests --ignore=tests/test_dashboard_frontend.py --ignore=tests/test_dashboard_sensitivity_frontend.py --ignore=tests/test_dashboard_visual_frontend.py -q --tb=short --junitxml=work/pr09a-validation/backend-branch.xml
$PY -m compileall -q app.py modules utils
node --check static/js/dashboard-visuals.js
node --check static/js/dashboard-lab.js
git diff --check
```

- Focused backend/model/number checks: **44 passed**.
- Shipped-client Chromium checks: **16 passed**; real ECharts, failure fallback,
  keyboard hierarchy/product focus, A/B goldens, Tornado/response/two-factor,
  invalid points, malicious source labels/CSV, mobile, draft/range/selection races,
  Reset, both source-group revocations and session failure.
- Existing Cost Analysis/Sensitivity browser compatibility: **96 passed**.
  The old suites intentionally exercise old endpoint and legacy renderer callers
  through test-only asset adapters in their shared fixture. They do not assert
  the new A/B workspace; the separate shipped-client suite does, without adapters.
  Initial runs against changed request/UI assumptions failed; adapting those old
  callers restored the complete compatibility suite without dropping assertions.
- Broad backend: **607 passed, 31 failed**. The identical command on untouched
  merged main (a detached worktree, separate initialized profile fixture, excluding
  its two browser suites) gave **577 passed, the same 31 failed**. JUnit failure
  identities match exactly. Existing failures concern profile/startup/catalog
  fixtures and localization/RTL assertions; no unrelated assertions were changed.
- Compilation, Dashboard JavaScript syntax and whitespace checks passed.
- Operational `Data/` and `instance/`: **90 files / 24 directories** retain their
  inventories, hashes and file/directory mtimes across validation. Every new
  browser fixture also checks exact inventories/hashes/mtimes and allows no POST
  except the read-only lab endpoint. No operational/profile/scenario cache writes.

Representative large fixture (the bounded-work test above): 200 configurations,
500 selected independent BOM rows, 121 two-factor samples; **124 engine calls**,
**0.647857 s**, **211 unique source reads**, **265448 response bytes**, including
**151234 experiment bytes**. Baseline, A/B and all samples use one captured input
object; each source is read once. Timings describe this isolated fixture, not an
operational performance guarantee. Domain-invalid reservations are also tested.

Actual desktop (1440×1100) and mobile (390×844) Chromium screenshots were captured,
inspected and refined for readable axes, permanent notice, lazy charts, keyboard
navigation and narrow layouts. All use isolated fixture data:

| View | Desktop | Mobile |
| --- | --- | --- |
| Cost Analysis / PARTIAL | [image](images/pr09a/cost-desktop.png) | [image](images/pr09a/cost-mobile.png) |
| Hierarchy exploration | [image](images/pr09a/cost-exploration-desktop.png) | [image](images/pr09a/cost-exploration-mobile.png) |
| Shared-baseline A/B | [image](images/pr09a/ab-desktop.png) | [image](images/pr09a/ab-mobile.png) |
| Tornado | [image](images/pr09a/tornado-desktop.png) | [image](images/pr09a/tornado-mobile.png) |
| Actual response curve | [image](images/pr09a/one_factor-desktop.png) | [image](images/pr09a/one_factor-mobile.png) |
| Two-factor matrix | [image](images/pr09a/two_factor-desktop.png) | [image](images/pr09a/two_factor-mobile.png) |
