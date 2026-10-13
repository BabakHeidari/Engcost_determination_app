# PR-11 evidence

The local frozen package was built from clean source commit
`222602a1c1417e766742a457525c070dd94bd277`, with CPython 3.12.14 on Debian 13 x64.
Its exact executable hash and all raw distributions are in
[linux-frozen-summary.json](linux-frozen-summary.json). It was extracted from the
real deb into a Persian/spaces installation path, made read-only, then exercised
with external TCP/DNS blocked and browser external requests aborted/counted.
These results do not establish stock Ubuntu Desktop or Windows acceptance.

* [Backend: 1,059 passed, zero skipped](backend.txt), [JUnit](backend.xml).
* [Existing primary browser: 43 passed, zero skipped](browser.txt), [JUnit](browser.xml).
* [Actual private first-admin screen](setup-admin.png).
* [Actual frozen Dashboard desktop](dashboard-1440.png) and [mobile](dashboard-390.png),
  synthetic 200-product fixture with exact-table fallback exercised.

Operational checkout Data/instance: all 114 inventory entries, bytes, directory
and file mtimes unchanged. Setup/edit/login writes are intentional isolated
operations; analytical source hashes are checked separately. Test credentials,
private capabilities and operational stores are not distributed as evidence.

Native CI is linked from [PR #48](https://github.com/BabakHeidari/Engcost_determination_app/pull/48).
The first Ubuntu jobs built/installed the actual deb and passed frozen/offline
smoke, then exposed a harness import-path error in retention validation. The
Windows setup action has no 3.12.14 binary; corrected automation builds pinned
CPython source commit `2abcf904b8dac8c999d2b3aac76681abb333798a` natively, using
3.12.10 solely as a build bootstrap. Job results and artifact links remain the
authority for native-platform status. See [status/measurements](../../pr11-validation.md).
