# PR-10 Dashboard performance evidence

The benchmark uses generated, installed V2 inputs and the real Dashboard
blueprint in a standalone Flask application. It does not import `app.py`, run
startup migrations, start an operational server, or touch operational `Data/`
or `instance/`. Fixture contents, directory population, SHA-256 hashes and file
and directory modification times must remain identical after every workload.

## Reproduce

From the repository root, with the release validation environment installed:

```bash
mkdir -p work/pr10-base-run
git archive fc373ca92e97c91d3d3b4a1a181096cbdf733c37 | tar -x -C work/pr10-base-run
PYTHONDONTWRITEBYTECODE=1 work/pr10-venv/bin/python scripts/benchmark_dashboard.py \
  --repository work/pr10-base-run \
  --archive-revision fc373ca92e97c91d3d3b4a1a181096cbdf733c37 \
  --first-samples 30 --warm-samples 30 --profile \
  --output work/pr10-evidence/benchmark-base-final.json
PYTHONDONTWRITEBYTECODE=1 work/pr10-venv/bin/python scripts/benchmark_dashboard.py \
  --first-samples 30 --warm-samples 30 --profile \
  --output work/pr10-evidence/benchmark-candidate.json
```

Run these commands sequentially with other release suites and browser timing
finished. The exact release run reused the untouched baseline archive prepared
for regression testing. Do not overlay an old archive with unrelated sources.

`--repository /path/to/pr09a-checkout` runs the same harness and fixture against
an unchanged PR-09A source checkout. For an archive without its own Git checkout,
`--archive-revision` checks the complete backend Python file population and each
file's digest against the selected Git tree. It prevents parent-checkout Git
metadata from incorrectly labelling a baseline archive as a dirty candidate.
The selected repository supplies the
application imports; the harness does not change that checkout. Raw JSON
includes every sample, summaries, observed work counters, environment/package
versions, Decimal context, source/harness SHA-256 values and separate cProfile
observations. All 53 backend Python source files are captured before timing;
a run fails if those sources change while it is measured.
The release's compact results are in `pr10-performance-results.json`.

Each workload has 30 first-request observations and 30 warmed observations.
A first request is the first request to a fresh Flask application and
authenticated client. A warmed request follows one excluded warm-up on the
same application/client. Python imports, fixture installation and Flask
registration are outside the timed interval. The OS page cache is not flushed.
The timer spans the in-process test-client request through completed response
serialization; source/engine counters are enabled inside that interval.
Network transfer and browser rendering are measured separately.

Percentiles use the nearest-rank definition: sort the measured values, then
choose `ceil(n × p)`. p50 and p95 use observed samples, without extrapolation.
These are measurements of the recorded shared Linux environment; they establish
no operational latency SLA. Re-run on the deployment host to assess its limits.

## Representative inputs and work

All 200 configurations are valid and have predictions in one category and
subcategory. The selected configuration has 500 independent BOM row identities
across four Rial materials. Every other configuration has three independent
rows; the all-selected report therefore calculates 1,097 BOM rows across all
200 products. Six separate factory pools, a 50% category share and an installed
approved planning period make every displayed allocation valid.

The two all-selected workloads exercise canonical Cost Analysis and its visual
wrapper. The four sensitivity workloads submit distinct A/B overrides and
respectively no experiment, 41 one-factor points, 10 Tornado ranges (20 points),
and an 11 × 11 matrix (121 points). The matrix retains the PR-09A reference
dimensions: 200 configured products, 500 selected BOM rows and 121 samples.

Each request reads 212 unique operational/metadata sources: 200 BOM documents,
materials, weights, predictions, six pools, the binding, the V2 manifest and
hierarchy metadata. The loader captures the 211 engine-bound sources once;
hierarchy validation reads the remaining metadata document once. Repeated
physical reads of these operational/metadata sources must be zero. Profile-store
reads are counted separately, including their own unique and repeated counts.
Every request creates one loader; the next HTTP request reads fresh inputs.

Expected observed engine calls are 200 for each all-selected report, 3 for A/B,
44 for one factor, 23 for Tornado and 124 for the matrix. Sensitivity always has
one baseline engine call and one shared captured `CostInputs` object across
baseline, A/B and every sample. The all-selected visual wrapper calculates
each selected configuration once, then derives visual data from that report.
No full BOM or registry is repeated per experiment point.

## Profiled bottlenecks and bounded fixes

The original many-product path rebuilt the same category predictions for every
selected product. For 200 products, it matched 200 prediction rows for each of
200 category identities in each of 200 loads, about eight million comparisons.
The read-only loader now builds one validated prediction-row index and one
complete typed prediction tuple per category and captured document. These
records belong to that loader only. Full allocation population, missing and
duplicate prediction diagnostics, source-name validation and safe path checks
remain in place. Failure records are not replaced with empty predictions.

The matrix executes 124 genuine engine calls against 500 rows; profiling showed
462,499 `_decimal` calls. Already typed Decimal values now keep their exact
representation while still passing finite and domain checks. Source strings,
booleans, absent values and other public input types retain the existing parser.
The costing formula, rounding policy and execution count remain unchanged.

The work regression tests require one prediction parse for an 80-product
allocation population, preserve unselected-product validation, and prove that
edits remain invisible within an existing capture but become visible to the
next loader. They also check extreme exact Decimal representations and typed
rejections for booleans, non-finite values and negatives. Timing is recorded
without a flaky elapsed-time assertion.

Duplicate explicit BOM row IDs now fail with typed `AMBIGUOUS_INPUT` and
`BOM_ROW_ID_NOT_UNIQUE` in both the loader and pure engine, preserving the
independent generated row IDs used for repeated material names. This prevents
override maps from ambiguously controlling multiple rows.

## Measured results

The paired run measured exact predecessor
`fc373ca92e97c91d3d3b4a1a181096cbdf733c37` followed by candidate backend commit
`d9cd07120ba5238dbaf763d7788263ecb636dcd8`. Both runs used identical harness
SHA-256 values and fixture dimensions. All 53 backend Python files matched their
respective Git trees and the source freeze; none changed during either run.
The repository-wide `tracked_changes` flag includes release-document/harness
edits; the candidate's `backend_sources_match_revision` is true and
`changed_backend_sources` is empty.

Recorded environment: CPython 3.12.14, Linux 6.18.44 x86_64 with glibc 2.41,
three logical CPUs; Flask 3.1.2, Werkzeug 3.1.9, pandas 2.2.3 and openpyxl 3.1.5.
Decimal context used precision 28 and ROUND_HALF_EVEN. Other release suites had
stopped before the sequential backend runs. This was still a shared environment
without a reserved CPU or an operational latency SLA.

Each version has 360 timed requests: 30 first and 30 warmed observations per
six workloads. Excluded warmups and one separate cProfile observation per
workload are not included in these percentiles. Entries show observed p50 / p95.

| Workload | First base p50 / p95 (ms) | First candidate p50 / p95 (ms) | Warm base p50 / p95 (ms) | Warm candidate p50 / p95 (ms) | First / warm n per version |
|---|---:|---:|---:|---:|---:|
| Cost Analysis, all 200 | 548.823 / 617.499 | 169.782 / 245.823 | 537.460 / 668.702 | 156.942 / 3906.351 | 30 / 30 |
| Cost Analysis visuals, all 200 | 589.568 / 627.236 | 160.288 / 176.629 | 584.660 / 1237.620 | 161.467 / 173.407 | 30 / 30 |
| Baseline + A/B | 59.315 / 74.810 | 51.923 / 65.861 | 58.822 / 70.202 | 50.922 / 64.850 | 30 / 30 |
| One factor, 41 points | 252.735 / 275.420 | 151.616 / 232.496 | 250.648 / 272.997 | 144.059 / 157.622 | 30 / 30 |
| Tornado, 10 ranges / 20 points | 152.533 / 171.669 | 94.139 / 116.588 | 150.523 / 166.881 | 94.755 / 110.169 | 30 / 30 |
| Two factor, 11 × 11 / 121 points | 630.366 / 675.214 | 332.404 / 397.737 | 672.180 / 890.227 | 336.626 / 344.483 | 30 / 30 |

Observed counters and response sizes below are constant across all first and warmed samples in both versions.

| Workload | Response bytes, base / candidate | Engine calls per request | Unique / repeated operational or metadata reads | Profile reads (unique / repeated) |
|---|---:|---:|---:|---:|
| Cost Analysis, all 200 | 1,088,007 / 1,088,007 | 200 | 212 / 0 | 4 (1 / 3) |
| Cost Analysis visuals, all 200 | 1,439,667 / 1,439,667 | 200 | 212 / 0 | 4 (1 / 3) |
| Baseline + A/B | 147,073 / 147,073 | 3 | 212 / 0 | 4 (1 / 3) |
| One factor, 41 points | 187,215 / 187,215 | 44 | 212 / 0 | 4 (1 / 3) |
| Tornado, 10 ranges / 20 points | 167,812 / 167,812 | 23 | 212 / 0 | 4 (1 / 3) |
| Two factor, 11 × 11 / 121 points | 299,030 / 299,030 | 124 | 212 / 0 | 4 (1 / 3) |

The candidate first and warmed p50 values are lower for all six workloads in
this dataset. The all-selected Cost
Analysis warmed p95 is higher: 3,906.351 ms versus 668.702 ms, with retained
candidate observations up to 4,180.991 ms. We did not remove slower samples.
The measurements do not establish a cause for that tail or uniform latency
improvement; deployment-host measurements remain necessary for operational
limits.

The five observations above 1,000 ms are consecutive warmed requests 4–8:
2,869.620, 1,521.721, 3,906.351, 4,180.991 and 3,107.347 ms. Every response-size
and observed work counter matches the other warmed requests, including 200
engine calls, one loader, 2,612 loader read attempts and 2,401 request-local
source reuses. Neighboring requests 3 and 9 took 379.634 and 421.680 ms.
The separate profile ran after all 30 warmed observations and took 0.535718 s;
it did not profile those slow requests. The evidence does not identify extra
work or an underlying CPU, scheduling, garbage-collection or lock mechanism.
That tail remains an unexplained operational measurement limitation. The
compact JSON records this inspection and retains the original percentiles.

The source counts refer to operational and hierarchy/metadata documents.
Authentication reads one separate profile document four times per request,
including three repeated profile reads. Including that document gives 216
physical reads from 213 unique files, with three repeats. Every request uses one
loader; each sensitivity request has one baseline evaluation and one shared
captured input object across A/B and experiment points. The full 200-product
Cost reports and response sizes are preserved.

Separate profiled observations record 200 loader calls for all-selected Cost:
base cumulative loader time 0.625156 s, candidate 0.113623 s. The matrix records
462,499 `_decimal` calls in both versions: cumulative time 1.094335 s for base
and 0.296820 s for candidate. These instrumented single profiles are work
observations, not additional percentile samples or causal latency guarantees.

[Compact paired results](pr10-performance-results.json) retain environments,
source/harness digests, all summaries, response sizes, counters and separate
profiles. [Raw base samples](evidence/pr10/benchmark-base-final.json) and
[raw candidate samples](evidence/pr10/benchmark-candidate.json) preserve every
observation. [The source freeze](evidence/pr10/benchmark-source-freeze.json)
pins both backend trees and the common harness before the paired sequence.

## Browser rendering and lifecycle

The shipped-browser measurements use the same 200-product / 1,097-BOM-row
all-selected visual report, including the 500-row selected product. Each viewport
has 30 observations after one excluded warmup.

| Viewport | n | Local HTTP request to ready p50 / p95 (ms) | ResponseEnd to ready p50 / p95 (ms) | Advanced toggle to chart p50 / p95 (ms) |
|---|---:|---:|---:|---:|
| Desktop 1440 × 1100 | 30 | 1712.846 / 2733.199 | 829.700 / 1938.500 | 509.500 / 1089.300 |
| Mobile 390 × 844 | 30 | 767.104 / 1169.077 | 430.700 / 893.200 | 276.700 / 980.500 |

These intervals include Playwright action/observation overhead. Early samples
in this shared container overlapped historical compatibility browser tests;
no backend benchmark overlapped. Slower observations are retained. The browser
results are separate from the in-process backend comparison and establish no
production latency SLA.

Every timing cycle replaces a report, opens/closes an advanced chart and changes
tabs. All 60 observations retain five resize listeners, one report observer and
two base charts; hidden-tab charts are disposed. Separate four-cycle Cost and
Lab checks confirm each retired chart is disposed, resource counts stabilize
after the shared exact-value listener is installed, and Reset/clear returns to
the documented baseline. No accumulating listener, observer or chart count was
observed across those cycles.

[Browser findings](pr10-browser-findings.md) document actual shipped-script/API
boundaries, interval definitions, lifecycle counts and screenshot inspection.
[Browser results](pr10-browser-performance-results.json) retain all 60 raw
observations, summaries, lifecycle cycles and source/screenshot digests.
