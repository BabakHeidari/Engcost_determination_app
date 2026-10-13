# PR-10 / DASH-7 numerical and read-only findings

The release checks preserve the approved `cost-v1-owner-approved-2026-09-27`
formula and decisions 001–024 in the [decision ledger](dashboard-decision-ledger.md).
There is no new accounting rule, data period, source history or persistence path.

## Cross-surface numerical proofs

`tests/test_dashboard_release_numerics.py` exercises the real Cost Calculation,
canonical Cost Analysis, visual wrapper, single-scenario and A/B routes, plus
`calculate_cost`. The common-capture test first runs each route's actual loader,
checks all resolved business inputs against an isolated frozen capture, then
supplies the same `CostInputs` object to each calculation. Only the loader's
display lineage role and capture timestamp are omitted from the input comparison.
Canonical factory identity, full category population, source prices/FX, independent
BOM rows, six pools and the installed planning period must agree.

All typed monetary and quantity fields are tested as fixed Decimal strings.
The Cost Calculation compatibility fields remain available, including independent
duplicate-material entries in `BOM_Details`.

| Approved vector | Observed result and protected behavior |
| --- | --- |
| G1: usage 100, price 2, FX 500,000, loss 10%, recyclability 20% | Live BOM **98,000,000 IRR/product**; stored historical 777,777 does not affect live cost. With G2 payroll, selected unit cost is 98,000,100 and projected cost is 980,001,000 for quantity 10. All five HTTP surfaces and the pure engine agree. |
| G4: independent lead rows 100 + 40 | Baseline **140**, price +10% **154**, price +20% **168 IRR/product**. Original row IDs and contributions remain separate in canonical, compatibility and scenario breakdowns. |
| G2: raw payroll 1,000, category share 50%, predictions 10 + 10 | Baseline **100 IRR/product / 1,000 IRR/period** for selected A; adjusted category pool is 2,000, full-category denominator 20 and modeled-minus-raw +1,000. |
| G2 A: selected prediction 30, other prediction 10 | **50 IRR/product / 1,500 IRR/period**. The denominator becomes 40. |
| G2 B: category share 25%, predictions unchanged | **200 IRR/product / 2,000 IRR/period**. Inverse allocation remains division. |
| B minus A | Actual unit difference **150** and actual projected difference **500**. Percentages use A's corresponding result as the reference; projected difference is calculated from each side's actual quantity and cost. |

Additional proofs check:

- Display filtering and excluding a malformed BOM leave the full valid category
  prediction denominator unchanged. A partial report exposes its partial total,
  coverage and excluded null rows; charts contain only calculated configurations.
- The weighted average uses the sum of projected costs over the same sum of
  production quantities. Unequal quantities produce 4,400 / 40 = 110 in the
  tie fixture. BOM and Payroll both contribute 2,200; deterministic tied IDs are
  `["BOM", "Payroll"]`, with each share 50%.
- Raw pools remain whole-factory amounts and retain their distinct modeled
  category/selected values and differences. Cost units remain IRR/product,
  quantity product/period and projected amounts IRR/period.
- Same-named A configurations in separate subcategories retain distinct
  four-part identities. Three calculated configurations reconcile to a projected
  hierarchy total of 2,950. Pareto groups 2,400 lead and 550 copper using all
  independent original rows and the selected calculated projected BOM denominator.
  Ambiguous legacy name-only prediction controls remain unsupported.
- Missing, negative and duplicate prediction mappings give typed unavailable
  outcomes with null numerical fields across analysis, wrapper and scenarios.
- A genuine zero cost remains a calculated result. Shares with a zero total are
  null; reference-zero comparison percentages are `NOT_APPLICABLE`. A selected
  prediction of zero with a positive full-category denominator preserves a valid
  unit cost and zero projected cost; its weighted average is unavailable.
- FX connected to a zero material price is `MATHEMATICAL_ZERO` with dependencies.
  Combined price/FX changes produce the actual two-factor results 0, 0, 50, 60.
  A mathematical zero effect is not a missing mapping.
- Same-factory pool aliases retain distinct logical lineage roles while sharing
  the same fingerprint. A single override updates both dependencies; conflicting
  overrides and aliased experiment axes fail safely.
- Every single-scenario and A/B POST captures once, calculates the baseline once,
  and sends the same input object to all evaluations. A registry GET baseline of
  140 followed by a source price change produces the fresh POST baseline 280 and
  A/B results 308/336. Engine inputs and normalized override mappings remain
  unchanged after every calculation.
- Finite Decimal residues remain explicit. The fractional-share fixture retains
  a projected row-minus-driver difference of **-0.00000000000000000000001 IRR/period**
  through the visual wrapper, with original component leaves intact. The waterfall
  unit-difference residue is also reported as technical reconciliation.

## Confirmed defect and minimal fix

Duplicate material names are valid independent BOM rows. Duplicate resolved row
IDs cannot identify independent overrides or lossless compatibility entries.

Before PR-10, two explicit `row_id="duplicate"` rows returned HTTP 200/OK from
Cost Calculation, canonical Cost Analysis and its visual wrapper, while both
sensitivity surfaces returned 422/`AMBIGUOUS_INPUT`. Cost Calculation's dictionary
compatibility view could overwrite one contribution, and a pure row-ID override
could target multiple rows ambiguously.

The shared loader now detects a repeated resolved row ID and raises
`AMBIGUOUS_INPUT` / `BOM_ROW_ID_NOT_UNIQUE`. The pure engine applies the same check
before resolving any override map. Existing auto-generated `row-N` IDs preserve
their source indices, and duplicate material rows with distinct IDs retain
100 + 40 = 140. Tests cover both equal-material and different-material duplicate
IDs across all five HTTP surfaces and directly supplied pure engine inputs.
No formula, valid-input result, six-pool identifier or authorization requirement
changes.

## Exact read-only inventories

`tests/test_dashboard_release_readonly.py` prepares V2, binding and Profile fixtures
before taking the baseline. It inventories the complete isolated fixture tree,
including each path's kind, file SHA-256 or symlink target, size, mode and
nanosecond modification time. Directory mtimes are included, so a transient
artifact that is created and removed also changes the inventory.

These 63 cases cover the real filter, canonical analysis, visual wrapper,
parameter registry, single-scenario and A/B APIs. Inventories remain identical
after successful requests, partial reports, invalid experiment points, malformed
or oversize requests, client-supplied baselines, invalid sources, absent V2/binding,
unknown/inactive/unauthorized factories, missing authentication, forbidden source
group overrides, source aliases and safe unexpected failures. Migration helpers
are replaced with failures on missing/invalid input paths. Denied factory cases
also fail if any operational key or costing population is resolved.

The existing Profile lock is part of the prepared inventory. These API tests
register isolated real blueprints and do not import `app.py`; startup installation
and the real Dashboard page belong to the separate isolated release startup smoke.
Operational repository `Data/`, owner bindings and real Profile data are never
used as fixtures or edited by these tests.

## Reproduction

Run from the repository root after installing `requirements-test.txt`:

```bash
python -m pytest -q tests/test_dashboard_release_numerics.py tests/test_dashboard_release_readonly.py
```

The numerical file contains 21 cases and the exact inventory file 63 cases.
Full-suite and browser evidence is recorded by the release validation workflow in
[release operations](dashboard-release-operations.md).
