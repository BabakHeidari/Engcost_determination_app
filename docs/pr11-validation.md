# PR-11 validation and installer delivery

**Superseded package notice:** 0.11.0 has a real-browser setup-form 403 defect.
Its results below did not exercise setup form clicks. Version 0.11.1 fixes the
referrer policy and adds installed browser submission coverage; replacement native
builds are being validated. See [cause, correction and recovery](pr11-setup-form-fix.md).

Version **0.11.0**, x64, unsigned. [Draft PR #48](https://github.com/BabakHeidari/Engcost_determination_app/pull/48) remains unmerged.
Implementation started from verified main `c18dec9c673d33f1afa6ced1efc292cdb721d412`, including merged #46 and #47.
Validated code head: `5815f1fded5b0074283354d39f1d542700e36919`.
Native CI built PR merge ref `ea1f954dbdaed7b8b7e9576371df2a5218e0adf6`.
The final handover commit changes documentation/evidence only.

## Delivered installers

[Successful native run 38446908358](https://github.com/BabakHeidari/Engcost_determination_app/actions/runs/38446908358) contains these downloadable archives. Extract the archive for the actual installer, `SHA256SUMS`, `build-info.json`, screenshots and validation reports. GitHub authentication may be required; Actions artifacts have limited retention.

| Installer | Download | Installer SHA-256 |
|---|---|---|
| `Engcost-0.11.0-Setup.exe` | [Windows x64 archive](https://github.com/BabakHeidari/Engcost_determination_app/actions/runs/38446908358/artifacts/11838598703) | `0f742fe50960f89a95358c72c7512ddce66aa2e14b96987752e2e2a42f547599` |
| `engcost_0.11.0_amd64.deb` | [Ubuntu 22.04 x64 archive](https://github.com/BabakHeidari/Engcost_determination_app/actions/runs/38446908358/artifacts/11838209153) | `fe86117ff119ee9ae323ea971f95421a69e69544864519fef5a1afc78f364d2d` |

Both shipping runtimes are CPython **3.12.14**, Waitress **3.0.2**, PyInstaller **6.16.0** onedir; runtime/build dependencies are pinned. Windows CPython is built natively from verified source `2abcf904b8dac8c999d2b3aac76681abb333798a`; 3.12.10 is only its build bootstrap. Metadata records dependency, source and resource hashes and unsigned status. Both native builds report `dirty: true`; these are not clean-checkout or bit-identical reproducibility proof. Per-file fingerprints are retained. The Windows contract report matches all reported application/module/utility/template/JavaScript hashes at the validated code head; test-file differences are checkout line endings.

## Tested platform matrix

| Platform | Actual execution | Result and limit |
|---|---|---|
| Ubuntu x64 | Hosted Ubuntu 22.04, glibc 2.35, Python 3.12.14 | Real dpkg installation; installed frozen smoke, running reinstall/uninstall retention and 1,062 backend tests passed. Bundled ELF passes the GLIBC 2.35 gate; package minimum is 2.35. Stock Ubuntu Desktop GUI/icon acceptance remains pending. |
| Windows x64 | Hosted Windows Server 2022, Python 3.12.14 | Real NSIS per-user installation; installed frozen smoke, running reinstall/uninstall retention and 1,062 backend tests passed. Stock Windows 10/11 ordinary-user Desktop acceptance remains pending; those OS versions are targets, not validated minimums. |
| Local Linux reference | Debian 13, glibc 2.41, Python 3.12.14 | Actual deb frozen payload tested read-only; local 1,062 backend and 43 existing browser cases passed. This separate local binary requires GLIBC 2.38 and is not the delivered Ubuntu package. |

All reported suites have zero failures, errors and skips. Native Windows bootstrap-contract diagnostics also pass independently; shipping acceptance uses compiled 3.12.14. Raw summaries: [Windows](evidence/pr11/native-windows-summary.json), [Ubuntu](evidence/pr11/native-ubuntu-summary.json).

## Installed offline and preservation checks

The actual installed executable runs from an unrelated CWD with Persian/spaces in workspace/config paths, isolated PATH and no PYTHONPATH, system Python packages, Git, Node or source checkout dependency. Ubuntu installation is system-owned/read-only; Windows tests also exercise read-only application resources. Linux injects a test-only external connect/DNS blocker, excluded from production. Windows blocks non-loopback outbound application traffic through its firewall. Browser external requests are independently aborted and counted. Hosted runners contain development tools; isolating the application is distinct from a clean end-user Desktop test.

Both native smokes pass fresh administrator creation/login; existing authentication and workspace selection; setup disabled after users exist; secret continuity/uniqueness; corrupt/incomplete recovery; repeated simultaneous clicks; occupied port; stale records; verified graceful stop and five restarts. Actual installers stop the verified owned service during same-package reinstall, retain Data/instance and secrets, and retain them after uninstall.

Installed integration checks cover V2-only factory/category/subcategory/product creation and destructive retry protection, material/BOM/financial saves, costing, Profile Excel, Cost Analysis, A/B and matrix requests. The synthetic fixture has 200 products and 500 BOM rows. Desktop 1440 px and mobile 390 px pages (setup/login, Desk, Profile, Product, factory/general parameters, Cost, Dashboard) have zero external/failed requests and JavaScript errors; local fonts, ECharts 5.6.0, CSV and exact-table chart fallback are checked. Native archives include screenshots. No stock installer-dialog/Desktop-icon capture is claimed.

Analytical request source hashes remain unchanged; setup/edit writes use isolated fixture data. Local operational Data/instance inventory: all 114 entries, bytes and mtimes unchanged. Native regression jobs also verify their checkout inventories unchanged. Operational stores, credentials, capabilities and private diagnostic logs are excluded from evidence.

## Native measurements

Seconds, all samples retained in raw summaries. Readiness starts at executable process launch, excluding desktop icon handling and browser process startup. Five restarts use warm filesystem caches; these are not power-on cold boot SLAs. Business readiness includes asynchronous application import after controller readiness. Request samples are ten actual requests per route with the representative fixture.

| Platform / measurement | Median | Min–max | p95 (nearest rank) |
|---|---:|---:|---:|
| Windows controller readiness (5) | 0.614 | 0.592–0.616 | 0.616 |
| Windows business readiness (5) | 1.311 | 1.286–1.314 | 1.314 |
| Windows Cost Analysis (10) | 0.187 | 0.184–0.210 | 0.210 |
| Windows A/B (10) | 0.187 | 0.180–0.212 | 0.212 |
| Windows matrix (10) | 0.205 | 0.199–0.224 | 0.224 |
| Ubuntu controller readiness (5) | 0.287 | 0.279–0.289 | 0.289 |
| Ubuntu business readiness (5) | 0.678 | 0.647–0.687 | 0.687 |
| Ubuntu Cost Analysis (10) | 0.083 | 0.082–0.108 | 0.108 |
| Ubuntu A/B (10) | 0.086 | 0.085–0.110 | 0.110 |
| Ubuntu matrix (10) | 0.100 | 0.098–0.128 | 0.128 |

First setup-controller readiness: Windows 0.757 s, Ubuntu 0.280 s. Administrator submission to business readiness: 0.537 s / 0.385 s, excluding human input. First usable navigation to an already-ready server: Windows 0.810 s desktop / 0.737 s mobile; Ubuntu 0.826 s / 0.901 s. Native reference hosts are GitHub-hosted Windows Server 2022 and Ubuntu 22.04 VMs identified in raw reports; CPU/quota details were not captured, so timings should not be generalized.

Local reference: AMD EPYC 9V74, three visible logical CPUs, two-CPU cgroup quota, 8 GiB memory, Debian 13 container on Linux 6.18.44. Earlier [local frozen measurements](evidence/pr11/linux-frozen-summary.json) identify their own executable/source revision. No financial cache or calculation precision change was introduced.

## Remaining acceptance gates

Stock Ubuntu Desktop and Windows 10/11 GUI installation, branded icon/default-browser launch and ordinary-user UAT; signing (no certificate supplied); owner verification of proprietary IRANSansX and Handsontable redistribution entitlement; and independent previous-compatible-version downgrade. This first package proves same-package running reinstall and uninstall preservation, not two-version rollback. Schema-v1 or damaged existing workspaces require approved recovery rather than automatic reset/migration. Public release, deployment and merge remain outside scope.

## Runtime/path audit

Active loaders use centralized RuntimePaths selected before application import. Flask resources/instance, APP_DATA_FILE, costing Data and period bindings are explicitly connected. Factory registry and folder-tracer entry no longer derive writable roots independently. Development/HTTPS defaults and supported configuration injection remain available. Legacy unused helpers in load_data.py retain development behavior; active routes do not call their XLSX/fallback/category-invention paths. Production templates/assets use reviewed local resources; obsolete Desk stylesheet copies are excluded. Customer startup performs no dependency preparation, downloads, update checks or telemetry.
