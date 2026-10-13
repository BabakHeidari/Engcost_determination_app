# PR-10 / DASH-7 release candidate

Base: merged PR-09A / GitHub #45, latest main
`fc373ca92e97c91d3d3b4a1a181096cbdf733c37`. Its visual workspace and A/B lab
were verified before implementation. Validated backend code is
`d9cd07120ba5238dbaf763d7788263ecb636dcd8`; the final commit adds an exact-product
browser scope guard, its regression, documentation and benchmark provenance,
with no backend behavior change.

| Gate | Result |
|---|---|
| Backend, model, exact-number and actual startup | **PASS: 977**, 0 failures/errors/skips |
| Actual Jinja/Flask/shipped browser | **PASS: 41** (25 new release + 16 retained actual-client), 0 failures/errors/skips; timing-source distinction below |
| Explicit legacy compatibility | **PASS: 96**, 0 failures/errors/skips; separate from primary evidence |
| Performance measurements | **COMPLETE: 720 backend requests + 60 browser samples**; observed tail limitation below |
| Owner UAT | **PENDING**; fixture checks are not owner acceptance |
| Production approval / deployment | **NOT APPROVED / NOT PERFORMED** |

[JUnit, commands, versions, source hashes and raw measurements](evidence/pr10/README.md)
record **1,114 distinct passing candidate cases**. No blanket skip, xfail or
critical-failure waiver is used. No unresolved P0/P1 was identified by these
checks; any P0/P1 affecting security, costing, authorization, persistence or the
default journey blocks release. Owner sign-off remains required.

## Concrete changes

- Analytical POST limits preserve the stricter application bound and 64 KiB,
  including cached middleware bodies, terminated lengthless/chunked streams and
  a misleading zero-length hint. Oversized valid JSON prefixes now return 413.
- Filters use the configured operational root and reject repeated/unknown/malformed
  query fields before lookup. Errors redact exception details. Non-string
  experiment types return 400 and genuine calculation failures retain 500.
- Duplicate explicit BOM row IDs consistently return typed ambiguity across
  Cost Calculation, analysis, visuals, Sensitivity and A/B. Repeated materials
  with independent generated IDs remain valid.
- Shipped adapters validate nested identities, factors/scenarios, units,
  scope/period/state/null combinations, comparison directions, waterfall positions,
  experiment indices/counts and budgets. Protected extensions fail before DOM/CSV.
  Exact product responses bind the full authorized category/subcategory/product
  path even when both parent filters are ALL. Refresh now invalidates a pending
  scenario; charts and listeners retire correctly.
- Request-local prediction indexing and a validated Decimal fast path address
  profiled bottlenecks. No source/result cache crosses requests. ECharts 5.6.0 is
  vendored with license/notice, verified hashes and SRI; exact-table fallback remains.

The untouched base reproduced **607 passed / 31 failed**. Every failure was
investigated and resolved as an obsolete fixture/source-location assertion against
later approved contracts, without changing approved production behavior. The
[31-row disposition](pr10-regression-findings.md) records behavior, cause,
contract conflict, P2 verification impact and retained assertions. An ordinary
USER's authorized real production-selection route now has a meaningful smoke.

See [security findings](pr10-security-findings.md),
[client validation](pr10-client-findings.md),
[numerical/no-write proofs](pr10-numerical-findings.md), and
[actual browser coverage](pr10-browser-findings.md).

## Preserved contracts and scope

G1–G4, V2, formula `cost-v1-owner-approved-2026-09-27`, Decimal precision,
canonical four-part identities, grants and period rules remain intact.
Cross-surface goldens retain G1 **98,000,000 IRR**, duplicate BOM **140 → 154 → 168**,
and G2 baseline **100 / 1000**, A **50 / 1500**, B **200 / 2000**, B−A **150 / 500**
(unit IRR/product / projected IRR/period).

Full-category denominators remain independent of display filters/BOM exclusions;
raw factory pools and modeled selected contributions have distinct scopes.
Weighted numerators/denominators, counts/ties, Pareto grouping/shares, hierarchy
units, zero/unavailable values, aliases and finite Decimal residues are checked.
Authoritative totals and original contributions stay unchanged; reconciliation is
visible. Waterfalls explain output differences; Tornado independently varies one
input against baseline; curves/matrices are actual engine evaluations. Baseline,
A, B and every point share one capture; each POST is fresh. Zero references have
null/NOT_APPLICABLE percentages and B−A uses A as its percentage reference.

This is current-data/hypothetical analysis. Periods, fingerprints and the owner
legacy baseline do not establish cost history. No persisted scenarios, historical
capture, sharing, forecasting or new business optimization is added. PR-11 is
not started. Browser cancellation invalidates UI acceptance; server cancellation
is not claimed.

## No-write, screenshots and operational limits

Isolated fixtures compare file/directory inventory, hashes, mtimes, modes and
symlinks after successful, invalid and forbidden requests; pure inputs remain
unchanged. Original operational **90 files / 24 directories** remain unchanged.
Actual app import/registration is separately exercised after temporary configuration
is set: deliberate startup initializes fixture V2; subsequent analytics and
repeated startup are unchanged. No operational migration/repair/source-save is
run during validation and no analysis/history storage is added.

Thirteen fixture screenshots were captured and inspected. Key views:

| View | Desktop | Mobile |
|---|---|---|
| PARTIAL Cost | [Image](images/pr10/partial-desktop.png) | [Image](images/pr10/partial-mobile.png) |
| A/B | [Image](images/pr10/ab-desktop.png) | [Image](images/pr10/ab-mobile.png) |
| Tornado | [Image](images/pr10/tornado-desktop.png) | [Image](images/pr10/tornado-mobile.png) |
| One factor | [Image](images/pr10/one_factor-desktop.png) | [Image](images/pr10/one_factor-mobile.png) |
| Two factors | [Image](images/pr10/two_factor-desktop.png) | [Image](images/pr10/two_factor-mobile.png) |

[Paired performance results](pr10-performance.md) use 30 first + 30 warm requests
per workload/version. The reference is 200 configurations, 500 selected BOM rows,
121 matrix points; all-selected visuals calculate 200 products/1,097 rows.
Warm matrix p50/p95 improved **672/890 → 337/344 ms**. Visual-wrapper warm p50/p95
was **585/1238 → 161/173 ms**. Counts/bytes remain identical: one loader,
212 unique/0 repeated operational or metadata reads; profile reads are separately
4 from one file (3 repeats). Matrix work remains 124 actual engine evaluations.

**Unexplained limitation:** Cost Analysis warm p95 increased **669 → 3906 ms**,
although p50 improved **537 → 157 ms**. Five consecutive slow samples are retained,
with identical bytes/work counters and no identified cause. The evidence does
not establish uniform latency improvement or a deployment SLA. Browser timings
also retain early overlap with compatibility work and automation-observation
costs. The 60 browser samples precede the final exact-product guard: their
all-products branch is unchanged, and original source hashes are retained.
Current-source functional and retained suites pass 24 + 16 cases; the earlier
timing case contributes one additional unique case, without a final-source timing
claim. Compatibility's 96-case run also precedes that guard and is separately
labelled. Deployment-host latency verification remains pending.

Managed Chromium download was network-policy blocked; explicitly installed
Chromium 154.0.8037.57 was validated with Playwright 1.62.0 instead. Setup documents
provide that reproducible override. Flask/WSGI body tests do not substitute for
real deployment-proxy integration or owner UAT on operational inputs.

Use the [manual owner checklist](dashboard-release-uat.md) and
[runtime/upgrade/rollback guide](dashboard-release-operations.md). Rollback selects
prior code/dependencies while preserving operational profile, V2 data and bindings.
Two prototype templates were removed only after proving no runtime references.
Leave this candidate unmerged for review; production approval is PENDING.

## Owner-UAT finding: Product creation after V2 activation

The owner reported `[Errno 2] ... Data/Factories/f2/category_weights.json` after
creating a category and subcategory, then a product. Product creation still ran a
legacy zero-share update after writing BOM/capacity, and its creation helpers used
literal Windows separators. This is a release finding outside the earlier
Dashboard analytical checks. #46 had already merged when the fix started, so the
focused follow-up branches from merged PR-10 on latest main.

The fix removes financial writes from creation, validates authorized native paths,
stages/locks related writes and compensates ordinary failures, and preserves
existing BOM/capacity files on retries. The authorized financial editor presents
new same-factory identities with blank values without saving them on read. Only
Factory Parameters MODIFY can save financial inputs; typed unavailable costing
and V2 authority are preserved. See the
[resolution and safe inspection guide](product-creation-owner-uat.md) and
[actual follow-up evidence](evidence/product-creation-owner-uat/README.md).

**Technical resolution: implemented and regression-tested in the follow-up. Owner
retest, native Windows smoke and production acceptance: PENDING.** Earlier PR-10
results remain historical evidence; this finding does not mark the original UAT
checklist accepted. No operational Data or instance changes are part of the fix.
