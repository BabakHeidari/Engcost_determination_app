# PR-10 legacy browser compatibility validation

The 96 checks in `tests/test_dashboard_frontend.py` and
`tests/test_dashboard_sensitivity_frontend.py` retain the pre-PR09A caller and
renderer contracts. They are explicitly labelled compatibility evidence. The
primary release suite in `tests/test_dashboard_release_frontend.py` serves the
shipped JavaScript and pinned local ECharts unchanged and is the evidence for
the shipped Dashboard.

The compatibility harness starts an authenticated standalone Flask application
with temporary, explicitly installed V2 source fixtures. It does not import
`app.py` or read operational stores. Sensitivity browser checks preserve source
inventory, SHA-256 and nanosecond modification-time snapshots and reject
source-save requests.

## Explicit compatibility adapters

For these two modules only, the harness serves test-only adaptations of the
cost and sensitivity callers:

- Cost analysis calls the retained `/api/cost_analysis` contract and supplies
  its report directly to the legacy report renderer.
- Sensitivity calls the retained `/api/dashboard/sensitivity/scenario`
  contract, mounts the legacy sensitivity renderer, and exports the accepted
  legacy snapshot with `DashboardSensitivityModel.csv`.
- Local ECharts is deliberately unavailable for fallback tests. Cases that
  exercise charts explicitly remove that route and load the same pinned local
  5.6.0 library as the shipped page.

All selection guards, cancellation, response validation, exact Decimal display,
authorization, actual Flask endpoints, source immutability and CSV safeguards
remain live. These adaptations are not production changes and are not used by
the primary release suite.

## Obsolete fixture repairs

PR-10 validates nested identities, counts and repeated metadata. Some synthetic
legacy reports previously changed only the visible row or card and retained
references to configurations outside that synthetic selection. Fixtures now
carry consistent public envelopes:

- Expanded reports clone public product lineage onto each selected composite
  identity and enumerate only their reported pool categories.
- Hostile-label cases update the matching lineage and pool-category identities,
  so the original HTML/text and spreadsheet formula-injection assertions reach
  rendering and CSV export.
- Synthetic totals agree with the weighted numerator and reconciliation's
  repeated projected total. The modified top-driver value/share agree with its
  corresponding driver entry.
- An excluded synthetic row carries null amounts, empty component arrays and
  its typed issue. Nested coverage matches the PARTIAL report's 26 calculated
  and one excluded configuration.

The tests still consume all supplied financial values as backend authority;
fixture repair does not introduce browser costing or rounding calculations.
No tests, assertions, skips or expected failures were added or removed to make
the suite pass. No production JavaScript was changed for compatibility.

## Reproduction and evidence

```bash
DASHBOARD_CHROMIUM_PATH=/usr/bin/chromium \
  work/pr10-venv/bin/python -m pytest \
  tests/test_dashboard_frontend.py \
  tests/test_dashboard_sensitivity_frontend.py \
  -q --tb=short \
  --junitxml=work/pr10-evidence/compatibility-final.xml
```

Playwright and Chromium are required. The sandboxed runner needs local network
socket access for the isolated Flask/browser connection. Collection evidence is
`work/pr10-evidence/compatibility-collection.txt` (96 tests).

The final execution passed **96 of 96 tests in 326.67 seconds**, with exit code
zero. Parsed JUnit records **zero failures, zero errors and zero skipped cases**;
the final count matches collection, with no omissions. Evidence is
`work/pr10-evidence/compatibility-final.xml`, `compatibility-final.txt` and
`compatibility-summary.json`.

The initial run recorded 89 passed and seven failed in 450.34 seconds
(`compatibility-initial.xml` and `.txt`). All seven failures were synthetic cost
reports rejected before rendering; all sensitivity compatibility cases passed.
The repaired full, expanded, partial and hostile-label fixtures were also
checked directly against the unchanged report validator before the final
browser rerun.

This compatibility run precedes the final exact-product path guard. Current-source
functional and retained real-client suites were rerun after that fix; the
compatibility result remains historical caller coverage, separately labelled
and not a claim of a second current-source release execution.
