# PR-11 validation status

Base verified through current GitHub main: `c18dec9c673d33f1afa6ced1efc292cdb721d412`.
Merged #46 and #47 are present. Artifact source SHA, exact dependency versions,
resource hashes, source hashes and unsigned status are recorded in build-info.json.

| Platform | Target / minimum baseline | Current validation |
|---|---|---|
| Linux x64 executor | Debian 13, glibc 2.41, CPython 3.12.14 | Actual .deb built; frozen payload extracted and exercised from a read-only installation path with Persian/spaces. This local binary requires GLIBC 2.38. OS-level installation/reinstall/uninstall is delegated to native CI. This is not Ubuntu Desktop acceptance. |
| Ubuntu x64 | Ubuntu Desktop 22.04 LTS or later, standard browser/OS libraries | Native ubuntu-22.04 build/install/smoke/retention CI supplied; pending actual job results. No minimum Ubuntu version is claimed validated before those jobs run; stock Desktop UAT remains pending. |
| Windows x64 | Windows 10/11 desktop; Windows Server 2022 CI | NSIS build/install/frozen/offline/retention CI supplied; native execution pending actual jobs. Desktop minimum OS/UAT remains pending. Linux success does not establish Windows success. |

The Linux smoke launches the **frozen executable extracted from the real deb**,
from an unrelated directory containing spaces and Persian names. Its PATH points
to `/nonexistent`; no PYTHONPATH, system Python packages, Git, Node or source
checkout is available to it. Waitress binds loopback only. Linux validation injects
a test-only connect/DNS blocker; browser routes abort and count all external
requests. This test library is not included in production packages. CI runs the
same smoke against an OS-installed, system-owned, read-only Linux application.
Windows validation uses a native outbound firewall rule plus browser interception.
The Ubuntu 22.04 job rejects any bundled ELF requiring GLIBC newer than 2.35.
Every Linux build audits its actual symbols and writes the real minimum into
the package dependency and build-info.json; the Debian candidate is not falsely
advertised as an Ubuntu 22.04 binary.

Current local results: 1,059 backend cases passed with zero failures/errors/skips,
including ten bootstrap/path/control/drain tests. A native smoke run passed fresh
admin/login, V2-only new factory/category/subcategory/product and destructive retry
protection, simultaneous clicks, occupied port, stale instance record, unrelated
CWD, Persian paths, existing workspace/auth preservation, persistent/unique
secrets, setup disabled after users exist, graceful restart, actual Cost Analysis,
A/B and matrix requests, and analytical source hash checks. Desktop 1440 and
mobile 390 pages (login, Desk, Profile, Product, Factory/General Parameters, Cost,
Dashboard) made zero external/failed requests and zero JavaScript errors, with
local fonts and ECharts 5.6.0 verified. Final expanded results and raw timing
distributions are retained in the evidence artifact, including corrupt/incomplete
recovery and a 200-product/500-row representative fixture.

Reference executor: AMD EPYC 9V74 virtual CPU, 3 visible logical CPUs, cgroup
quota 2 CPUs, 8 GiB memory limit, Debian 13 container on Linux 6.18.44. Timings are
process restarts with warm filesystem caches, not power-on cold boot or a desktop
icon/browser end-to-end SLA. Setup-server readiness precedes business import;
business-ready time is separately measured. All samples are kept; distributions
must be assessed from native-summary.json, not interpreted as universal promises.
No persistent financial cache or changed calculation precision was added.

Remaining gates: native Windows jobs, Ubuntu jobs and stock Desktop checks;
actual installer dialogs/desktop icon evidence on those systems; previous-version
rollback (this is the first package); signing; proprietary font/Handsontable
entitlement; owner UAT. Existing schema-v1 or damaged workspaces require approved
recovery instead of being silently migrated/reset by the setup selector. The
development/HTTPS deployment defaults and supported Flask configuration injection
remain available. Build/test artifact delivery is authorized; no public release,
deployment, merging, telemetry, updater, history capture or persisted scenarios.

## Runtime/path audit

All active feature loaders bind `utils.paths`, now selected by RuntimePaths before
app import. Flask instance/resources, APP_DATA_FILE, costing Data and period
bindings are explicitly connected. Factory registry and the folder-tracer entry
point no longer derive writable roots independently. Legacy unused loader helpers
in load_data.py retain their development behavior; active routes do not invoke
their XLSX/fallback/category-invention paths. Old template/desk CSS copies are
excluded from the production template allowlist; shared Font Awesome supplies
icons. All current template script/style references use local URLs and reviewed
font paths. No customer dependency/cache preparation is performed.
