# PR-11 evidence

[Native run 38446908358](https://github.com/BabakHeidari/Engcost_determination_app/actions/runs/38446908358) passed Windows Server 2022 and Ubuntu 22.04 builds, actual installer execution, offline frozen/browser checks, running reinstall/uninstall preservation and all 1,062 backend cases on each platform (zero failures/errors/skips).
Validated code head `5815f1fded5b0074283354d39f1d542700e36919`; packages record PR merge SHA `ea1f954dbdaed7b8b7e9576371df2a5218e0adf6` and `dirty: true`. Per-source/resource hashes are in each archive's build-info.json.

* [Windows installer and native reports](https://github.com/BabakHeidari/Engcost_determination_app/actions/runs/38446908358/artifacts/11838598703).
* [Ubuntu installer and native reports](https://github.com/BabakHeidari/Engcost_determination_app/actions/runs/38446908358/artifacts/11838209153).
* [Native Windows raw summary](native-windows-summary.json) and [Ubuntu raw summary](native-ubuntu-summary.json), including installer/executable checksums and every timing sample.
* [Local backend: 1,062 passed, zero skipped](backend.txt), [JUnit](backend.xml).
* [Existing primary browser: 43 passed, zero skipped](browser.txt), [JUnit](browser.xml).
* [Local private first-admin screen](setup-admin.png).
* [Local frozen Dashboard desktop](dashboard-1440.png) and [mobile](dashboard-390.png), synthetic 200-product fixture with exact-table fallback exercised.

Earlier local Debian frozen evidence came from clean source `222602a1c1417e766742a457525c070dd94bd277`, CPython 3.12.14, exercised in a read-only Persian/spaces installation path with external TCP/DNS blocked. [Its raw measurements](linux-frozen-summary.json) identify that executable; they do not replace final native evidence. Its GLIBC 2.38 package is not the delivered Ubuntu GLIBC 2.35 artifact.

Operational local checkout Data/instance: all 114 entries, bytes and mtimes unchanged. Native jobs separately check their checkout inventories. Setup/edit/login writes are isolated intentional operations; analytical source hashes are checked separately. Credentials, private capabilities and operational stores are excluded from evidence.

Archives include synthetic setup/browser captures; stock Desktop installer-dialog, icon/default-browser evidence and owner acceptance remain pending. See [checksums, platform matrix, timings and limitations](../../pr11-validation.md).
