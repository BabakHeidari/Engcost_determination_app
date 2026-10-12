# PR-10 release evidence index

Predecessor: merged PR-09A / GitHub #45, main
`fc373ca92e97c91d3d3b4a1a181096cbdf733c37`.
Validated backend code commit:
`d9cd07120ba5238dbaf763d7788263ecb636dcd8`.
The final commit adds the exact-product browser scope guard and regression,
documentation and benchmark metadata, with no backend behavior change.

| Artifact | Result / scope |
|---|---|
| [Base backend JUnit](base-backend.xml) | 607 passed, 31 failed, 0 errors/skips; every failure triaged and resolved |
| [Candidate backend JUnit](candidate-backend.xml) | 977 passed, 0 failed/errors/skips in the final frozen-source isolated runner |
| [Combined actual browser JUnit](candidate-browser.xml) | 41 unique passing cases, 0 failed/errors/skips; current functional + retained runs and earlier timing case below |
| [Current functional release browser](candidate-browser-functional.xml) | 24 cases after the exact-product guard; 0 failures/errors/skips; timing case deselected |
| [Earlier timing case](candidate-browser-timing.xml) | 1 all-products case, including 60 timing samples, extracted unchanged from the original full run |
| [Retained PR-09A actual browser](candidate-browser-retained.xml) | 16 passing current-source real-client cases, without legacy caller adapters |
| [Original full browser capture](candidate-browser-release.xml) | 23 passing cases before the exact-product guard; supplemental, not counted twice |
| [Original Lab lifecycle](candidate-browser-lifecycle.xml) | 1 earlier passing lifecycle case, included in the current functional rerun; not counted twice |
| [Exact-path failing reproduction](exact-reference-before.xml) / [fixed result](exact-reference-after.xml) | 1 deliberately reproduced failure before the fix / 1 pass after; supplemental, not candidate failures |
| [Exact-path scope](exact-reference-scope.json) / [final browser source](browser-final-source.json) | Current source digests, run boundaries, reproduction commands and original timing-source distinction |
| [Legacy compatibility JUnit](candidate-compatibility.xml) | 96 passed, 0 failed/errors/skips; explicitly adapted old callers, separate from primary evidence |
| [Candidate environment/commands/source hashes](candidate-summary.json) | Python/packages, exact command, disposable source hashes and unchanged operational inventory |
| [Compatibility summary/command](compatibility-summary.json) | Outcome and reproduction command; run predates final browser guard |
| [Untouched baseline source](base-source-integrity.json) | No changed tracked files after baseline regression |
| [Raw base benchmark](benchmark-base-final.json) | 360 timed requests; first and warm 30 per six workloads; full counters, source/harness hashes, profiles |
| [Raw candidate benchmark](benchmark-candidate.json) | 360 paired timed requests; every slow sample retained |
| [Benchmark source freeze](benchmark-source-freeze.json) | 53 backend source files per version and one identical harness |
| [Raw browser timing](browser-performance.json) | 30 desktop + 30 mobile measurements; explicit observation boundaries/concurrency |
| [Raw Cost lifecycle](browser-lifecycle.json) | Four Cost report cycles; Lab cycles are also retained in the compact browser JSON |
| [SHA-256 manifest](manifest.json) | Artifact integrity and distinct JUnit counts |

There are **1,114 distinct passing candidate cases**: 977 backend, 41 actual
browser and 96 compatibility. No skips, blanket xfails or test omissions are used.
Node-backed model/number checks are included in the backend count; 720 backend
timing requests and 60 browser timing observations are measurements, not extra
passing test cases. Repeated or supplemental checks are not double-counted.

Python 3.12.14, Flask 3.1.2, Werkzeug 3.1.9, pandas 2.2.3, openpyxl 3.1.5,
pytest 9.1.1, Playwright 1.62.0, Node 24.19.0, Chromium 154.0.8037.57 and
vendored ECharts 5.6.0 were used. Full installed dependency versions are retained
in the candidate summary and benchmark environments; reproducible pins are in
the root requirements files. See [operations](../../dashboard-release-operations.md)
for portable clean setup and isolated validation commands.

The combined browser XML combines the current functional and retained JUnit
suites with one timing testcase extracted from the original full run, without
altering any testcase outcome or time. Every input XML is retained separately.
The 60 timing observations precede the final exact-product path guard. Product
ALL still short-circuits that guard and new option attributes are populated
before timing starts. Original timings and source hashes are preserved; this is
not a final-source timing rerun. The compatibility run also predates that guard.
Current-source functional and retained runs pass all 40 executed cases.
Absolute workspace/temp paths in captured commands describe this execution;
portable setup does not require those locations or hidden caches.

All screenshots, browser fixtures and performance datasets use generated data.
No operational profile, password hash or credential is evidence. Original
`Data/`/`instance/` retain 90 files and 24 directories by the runner's exact
inventory/hash/mtime comparison. Analytical request immutability and deliberate
startup initialization are verified separately.

The warmed Cost Analysis p95 increased to 3.906 s in this shared-host dataset;
the mechanism remains unidentified and samples are retained. Read
[performance limitations](../../pr10-performance.md) before interpreting medians
as a uniform latency improvement. Technical evidence does not constitute owner
UAT, a deployment SLA or production release approval. Owner sign-off is PENDING.
