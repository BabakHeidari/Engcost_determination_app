# PR-10 shipped-browser findings

The PR-10 release cases pass against the actual Jinja Dashboard, unchanged shipped
business scripts, real authorized Flask APIs and vendored ECharts 5.6.0. There are
25 distinct release cases with zero failures, errors or skips. After the final
exact-product guard, 24 functional cases pass on current source. The earlier
timing case is retained with its original source hashes and scope caveat below.

| Committed evidence | Executed cases | Failures | Errors | Skips |
|---|---:|---:|---:|---:|
| [Current functional release](evidence/pr10/candidate-browser-functional.xml) | 24 | 0 | 0 | 0 |
| [Earlier all-products timing case](evidence/pr10/candidate-browser-timing.xml) | 1 | 0 | 0 | 0 |

The [retained PR-09A actual browser](evidence/pr10/candidate-browser-retained.xml)
has 16 passing cases on current source, giving 41 primary shipped-client cases. The
[combined JUnit](evidence/pr10/candidate-browser.xml) retains all three executions.
Historical compatibility has 96 separate passing cases. Compatibility endpoint
adapters or synthetic legacy wire shapes do not satisfy this gate.

## Actual boundary and isolation

`tests/test_dashboard_release_frontend.py` uses isolated installed V2 fixtures,
a standalone Flask application, authenticated synthetic sessions and an ephemeral
localhost server. It renders `templates/dashboard/dashboard.html` and serves every
required `static/js/dashboard-*.js` business asset through Flask. Every served
business script must match its on-disk SHA-256 byte for byte. Only pinned,
integrity-checked Bootstrap and Font Awesome presentation bytes are fulfilled
from the setup cache; ECharts is the shipped local vendor. No business asset is
rewritten, and no legacy API endpoint adapter is installed.

The fixture never imports operational `app.py`, accesses operational stores or
runs operational startup migration. Every browser case compares fixture content,
population and file/directory modification times after the prepared checkpoint.
Observed HTTP methods must be GET/HEAD except the nonpersistent Lab analysis
POST. Unhandled page errors fail the gate. Transport race tests delay genuine
authorized Flask documents and deliberately ignore AbortSignal to test the
client's independent generation/scope/revision guards.

## Covered journeys and fix

- Default Cost selection requires explicit cascade choices, including ALL. Exact
  installed boundaries display Jalali and submit canonical Gregorian dates;
  mismatched localized date edits block submission. PARTIAL coverage is one
  calculated and one excluded configuration. Table filtering, search, sorting and
  pagination preserve the accepted KPI and full two-configuration CSV.
- Chart click, keyboard hierarchy drill, material Pareto, product/factor heatmap
  and production/cost scatter preserve scope and exact accepted KPI/CSV. Repeated
  material names remain distinct BOM rows in local exploration.
- Independent A/B drafts produce all three comparison directions and exact
  backend unit/projected deltas. Three waterfall charts preserve exact targets.
  Tornado, one-factor and two-factor charts use actual backend sample results and
  exact exports. Editing a range invalidates results and export.
- Keyboard and touch exact-value inspection/copy, Escape, tab arrows/Home,
  chart initialization failure and an absent chart library retain the documented
  exact-table/CSV fallback and focus behavior.
- Late Lab results cannot restore data after A/B edits, range edits, Reset,
  selection changes or baseline refresh. Duplicate Cost/Lab submissions issue
  one request. A stale Cost result cannot cross a changed product scope. Source
  edits become visible on the next real request with a new lineage notice.
- Malformed received Cost identities/duplicate factors and Lab budgets/unknown
  waterfall factors never mount accepted results or enable CSV.
- Baseline refresh was disabled while a scenario request was pending. Refresh
  now remains available and invokes the existing cancellation/invalidation path
  before loading the fresh registry. The stale-response test verifies the actual
  button is enabled and a late scenario cannot restore results or export.

## Repeated resources and timing

Cost and Sensitivity each repeat four accepted-report/run cycles, opening and
closing an advanced chart, switching tabs and replacing/resetting results.
Every retired chart reports `isDisposed()`. Cost begins with three platform
resize listeners and no report observer/chart. After the first exact-value render
one shared document listener is installed: accepted Cost reports stay at five
listeners, one observer and two charts; clearing returns to four listeners and
zero report observers/charts. The shared exact-value listener intentionally serves
both tabs until pagehide and its registrations use weak references.

Sensitivity's authorized baseline stays at four listeners, one observer and zero
charts (the baseline view is exact values and tables). Every accepted Lab run
stays at five listeners, one observer and three
charts. Closing the waterfall restores that accepted count, leaving the tab
disposes all charts, and Reset restores the baseline count. Clearing its selection
leaves four listeners and zero report observers/charts. Counts do not grow across
the four cycles. Raw counts and each cycle are retained in the JSON evidence.

The final timing case runs the representative 200-product, 1,097-BOM-row
all-selected visual report, including the 500-row selected product. At each
viewport it excludes one warmup and records 30 observations: desktop 1440×1100
and mobile 390×844. Every cycle replaces the report, opens/closes the product ×
factor heatmap and switches away/back. All 60 observations retain five resize
listeners, one report observer and two base charts; chart disposal and hidden-tab
zero-chart checks must pass every cycle. This is a shared-container timing
dataset: the historical compatibility browser suite overlapped early samples,
then stopped before the remaining samples completed. No backend benchmark
overlapped this run. The raw observations are retained without removing slower
samples or claiming uncontended measurements.

Chromium `154.0.8037.57`, Playwright `1.62.0`, ECharts 5.6.0,
headless Linux and Asia/Tehran browser time are recorded with source/screenshot
hashes in [the machine-readable evidence](pr10-browser-performance-results.json).
Percentiles use nearest rank, `ceil(n × p)`, on actual observations.

| Viewport | Measured interval | n | p50 ms | p95 ms | max ms |
|---|---|---:|---:|---:|---:|
| desktop | Local HTTP request and report ready | 30 | 1712.846 | 2733.199 | 3935.663 |
| desktop | Browser responseEnd to ready observation | 30 | 829.700 | 1938.500 | 2324.500 |
| desktop | Advanced toggle to mounted-chart observation | 30 | 509.500 | 1089.300 | 1181.500 |
| mobile | Local HTTP request and report ready | 30 | 767.104 | 1169.077 | 2357.481 |
| mobile | Browser responseEnd to ready observation | 30 | 430.700 | 893.200 | 1335.900 |
| mobile | Advanced toggle to mounted-chart observation | 30 | 276.700 | 980.500 | 1646.300 |

The first interval spans the Playwright keyboard action through the real local
HTTP response and report-ready observation. The second starts at browser resource
`responseEnd` and ends after observing accepted state; the third starts at the
actual details toggle and ends after observing the mounted ECharts instance.
These are observed bounds including automation/polling overhead, not an isolated
renderer profiler. Backend-only timings are reported in
[the performance audit](pr10-performance.md). This shared Linux host establishes
no production latency SLA; representative deployment measurements remain owner
UAT work.

## Screenshot inspection

Synthetic screenshots were captured and visually inspected at desktop, tablet
820×1180 and mobile widths as applicable. PARTIAL status and coverage, currency
and period units, RTL layout and narrow-screen stacked KPIs remain readable.
Advanced charts retain their units, context and nonpersistent notice. Horizontal
document overflow is checked automatically at every captured viewport; large
tables remain inside their own scroll containers.

| Journey | Desktop | Tablet | Mobile |
|---|---|---|---|
| Cost PARTIAL | [desktop](images/pr10/partial-desktop.png) | — | [mobile](images/pr10/partial-mobile.png) |
| A/B comparison | [desktop](images/pr10/ab-desktop.png) | — | [mobile](images/pr10/ab-mobile.png) |
| Tornado | [desktop](images/pr10/tornado-desktop.png) | [tablet](images/pr10/tornado-tablet.png) | [mobile](images/pr10/tornado-mobile.png) |
| One factor | [desktop](images/pr10/one_factor-desktop.png) | [tablet](images/pr10/one_factor-tablet.png) | [mobile](images/pr10/one_factor-mobile.png) |
| Two factors | [desktop](images/pr10/two_factor-desktop.png) | [tablet](images/pr10/two_factor-tablet.png) | [mobile](images/pr10/two_factor-mobile.png) |

## Reproduce

Install the pinned requirements and presentation cache with
`scripts/setup_dashboard_browser.py`; `--chromium-path /usr/bin/chromium` validates
an installed browser instead of downloading one. From the repository root:

```bash
DASHBOARD_CHROMIUM_PATH=/usr/bin/chromium DASHBOARD_REQUIRE_BROWSER=1 \
  DASHBOARD_UI_EVIDENCE_DIR=docs/images/pr10 \
  DASHBOARD_BROWSER_LIFECYCLE_FILE=work/pr10-evidence/browser-lifecycle.json \
  DASHBOARD_BROWSER_METRICS_FILE=work/pr10-evidence/browser-performance.json \
  work/pr10-venv/bin/python -m pytest -q tests/test_dashboard_release_frontend.py \
  --junitxml=work/pr10-evidence/release-browser.xml
```

For timing alone, add `-k many_product` and run without other heavy tests or
benchmarks. `scripts/validate_dashboard_release.py --suite browser` provides the
broader isolated release-runner workflow and rejects missing/skipped browser
cases. Owner acceptance and production release approval remain PENDING in
[the manual UAT checklist](dashboard-release-uat.md).

## Exact-product path regression after timing capture

The exact-product controller previously checked only the product label after
matching the response's selected opaque reference. With category and subcategory
both ALL, a coherent report for a different authorized path with the same label
could therefore be accepted if transport forged only that selected reference.
Canonical report/visual validation correctly accepted the report's internally
consistent identities; the missing check was the binding to the selected option.

The controller now retains the authorized option's category and subcategory
alongside its label and compares all three with every exact-product detail row.
Existing canonical validation binds the factory, and the request scope guards
still reject changed selections. References remain opaque, and no financial
arithmetic or backend contract changed.

One additional primary browser case obtains both references from actual hierarchy
options and first accepts/exports the legitimate selected path. Its transport
intercept fetches a genuine Flask report for a second category/subcategory with
the same label and valid installed V2 inputs, then changes only
`analysis.scope.selection.product`. All nested identities and monetary values
remain the genuine other-path backend result. Before the fix this yielded OK,
a visible report, enabled CSV and two live charts. After the fix it yields
UNAVAILABLE, a hidden report, disabled CSV and zero live charts. The existing
asset-byte, page-error and fixture content/inventory/mtime guards apply.

The deliberate before-fix reproduction is retained in
[before-fix JUnit](evidence/pr10/exact-reference-before.xml) (one deliberate
failing reproduction); the targeted [after-fix run](evidence/pr10/exact-reference-after.xml)
has one pass. The current [functional primary suite](evidence/pr10/candidate-browser-functional.xml)
has 24 passes, zero failures,
errors or skips, with only the costly timing case deselected. The primary suite
now contains 25 distinct release cases.

The 16 retained real-client cases were rerun after this guard and passed in
58.85 seconds. [Final browser provenance](evidence/pr10/browser-final-source.json)
records hashes and reproduction commands; earlier full/lifecycle runs remain
available as supplemental evidence and are not counted twice.

The 60 timing observations above precede this guard. Their recorded
`dashboard-analysis.js` SHA-256 remains
`37175573c377fb4274440fc723edbaceecfd2d65e46d2a8907de425a632ff9d3`; the guarded
controller is
`d5fd4c01a7a887601c9b24024316e7401bb04b7e91c125ccc4f4457463a9f9e9`.
The timed report explicitly selects product ALL, which still short-circuits this
exact-product comparison; added option attributes are populated before timing
begins. Timing observations and their original source hashes are preserved,
and no new measurements or final-source timing claim are made by this functional
rerun. Backend benchmark inputs and code are unchanged by this fix.
