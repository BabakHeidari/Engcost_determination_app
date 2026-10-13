# Owner-UAT Product creation evidence

Fix parent: latest `main`, merged PR-10 #46,
`bc9f3f10f7fdcfcd7ca4ccb0a13289d1a3af4cb7`. All runs use Python 3.12.14 and
isolated fixtures/disposable source copies; operational `Data/` and `instance/`
are not edited. No owner acceptance or native Windows execution is claimed.

| Final evidence | Result | Files |
|---|---|---|
| Full backend, Product/catalog, V2/startup, authorization, Cost Calculation, Dashboard/model/number regressions | 1,049 passed; 0 failures/errors/skips, including 72 new Product creation cases | [Log](backend.txt), [JUnit](backend.xml), [commands/versions/hashes](backend-summary.json) |
| Dashboard primary browser regressions, including 200-product desktop/mobile resource check | 41 distinct Dashboard cases passed | [Primary log](dashboard-browser.txt), [JUnit](dashboard-browser.xml), [snapshot](dashboard-browser-summary.json) |
| Final actual Jinja/Flask financial editor, desktop 1440px and mobile 390px | 2 passed; 0 failures/errors/skips | [Log](editor-browser.txt), [JUnit](editor-browser.xml), [snapshot](editor-browser-summary.json) |
| Python compilation and whitespace validation | Both exit 0 | [Checks](checks.txt) |
| Original operational inventory | Unchanged; 114 entries in each final isolated runner comparison | JSON summaries above |

**1,092 distinct passing cases**: 1,049 backend + 41 Dashboard browser + 2 Product
browser. The raw primary browser log has 43 passes: it also ran the two Product
editor cases before the final header localization. Those two are counted only
from their final targeted rerun. The only subsequent UI change translates the
financial editor's headings using existing Persian labels; Dashboard templates,
JS, routes and browser cases are unchanged. The final backend and editor snapshots
match the final source. No duplicate reruns inflate the total.

The original runner's `base_sha` remains PR-10's historical comparison anchor;
`checkout_sha` identifies this fix's actual parent above. `source_sha256` hashes
the exact disposable source executed before commit. Runtime/test/browser versions
are pinned in `requirements*.txt`; browser execution uses Playwright 1.62.0 and
installed Chromium 154.0.8037.57, with verified presentation assets cached under
`work/vendor`. Screenshots use synthetic data and were inspected:
[desktop](financial-editor-1440.png), [mobile](financial-editor-390.png).

## Actual commands

From the repository, using `/workspace/work/venv/bin/python` as `python`:

```bash
python -m pip install -r requirements-test.txt
python scripts/setup_dashboard_browser.py --chromium-path /usr/bin/chromium
python scripts/validate_dashboard_release.py --suite backend --name localized-final --evidence-dir work/owner-uat-evidence
PRODUCT_CREATION_EVIDENCE_DIR="$PWD/work/owner-uat-evidence/images" DASHBOARD_CHROMIUM_PATH=/usr/bin/chromium python scripts/validate_dashboard_release.py --suite browser --name owner-uat-final --evidence-dir work/owner-uat-evidence
PRODUCT_CREATION_EVIDENCE_DIR="$PWD/work/owner-uat-evidence/localized-images" DASHBOARD_CHROMIUM_PATH=/usr/bin/chromium python -c "import scripts.validate_dashboard_release as runner; runner.PRIMARY_BROWSER = ['tests/test_product_creation_frontend.py']; raise SystemExit(runner.main())" --suite browser --name editor-final --evidence-dir work/owner-uat-evidence
python -m compileall -q app.py modules utils
git diff --check
```

The first broad backend run passed 1,043 cases. Additional regression cases brought
both later full runs to 1,049. The first browser attempt produced 43 setup errors
because the execution sandbox denied Chromium socket operations (`setsockopt:
Operation not permitted`); [excerpt](browser-sandbox-excerpt.txt). Rerunning with
the required execution network/socket permission passed all 43. No source change,
skip or test waiver was used to resolve that environment failure.

## Reproduction and limits

[Before output](before.txt) comes from unchanged merged-PR-10 code using
[the retained script](reproduce-before.py). To repeat it, run that script in a
checkout of the parent SHA above with `PYTHONPATH=.`. The first journey is the
actual Ubuntu behavior; the second changes only legacy path helpers to emulate
their Windows filesystem result, then invokes the same Flask route. It proves
BOM/capacity survive the old legacy-weights 500, without touching operational data.
It is not a native Windows test.

Both OS lock adapters are covered in the backend suite, and creation/capacity
helpers use native joins and accept both relative-path separators. Native Windows
owner smoke remains pending. Ordinary failure compensation is tested at staging,
capacity publication, BOM publication, hierarchy replacement and refresh, plus
directory rollback and concurrent retries. It is not a power-loss/crash journal.
Existing partial attempts remain intact; use the
[inspection guide](../../product-creation-owner-uat.md) for a separately reviewed
operator repair, without deleting/resetting their files.
