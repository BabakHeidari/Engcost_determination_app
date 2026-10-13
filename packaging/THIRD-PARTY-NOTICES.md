# Bundled third-party software

This is an unsigned review build, not a public release or a statement of license
entitlement. Exact asset bytes, versions, archive hashes and provenance are in
`vendor-manifest.json`; the full asset allowlist is in `resources.json`.

* Bootstrap 5.3.2: MIT; bundled LICENSE.
* Font Awesome Free 6.5.1: icons CC BY 4.0, fonts SIL OFL 1.1, code MIT;
  bundled LICENSE.txt. CSS and every referenced woff2/ttf are local.
* ECharts 5.6.0: Apache-2.0; bundled LICENSE and NOTICE.
* SheetJS Community Edition 0.18.5: Apache-2.0; bundled LICENSE. The previous
  unused mojibake-damaged copy failed JavaScript syntax validation. This bundle
  uses verified upstream bytes. Core Excel exchange uses the existing backend.
* Handsontable JavaScript 17.0.1: commercial or restricted personal/evaluation
  terms, not MIT. The unreferenced existing compatibility CSS is retained with
  its repository hash. LICENSE.txt is bundled. No commercial license key or
  redistribution entitlement is supplied or asserted. Current core templates
  do not load Handsontable. Owner licensing review is required before any use
  or redistribution under its commercial terms.
* IRANSansX: existing local Regular/Medium/Bold files are bundled unchanged.
  Proprietary font software; no license/redistribution certificate is recorded
  in this repository. The owner must establish applicable rights before
  customer/public redistribution. No rights or license key are invented.
* CPython 3.12: PSF license and included third-party notices. Build automation
  copies the installed interpreter license; missing license fails the build.
* Flask, Werkzeug, Jinja2, MarkupSafe, itsdangerous, blinker, click, pandas,
  NumPy, python-dateutil, pytz, tzdata, six, openpyxl, et_xmlfile, Waitress:
  exact pinned versions are recorded in build-info.json. Installed distribution
  license files are collected into `licenses/` alongside their metadata.
* PyInstaller 6.16.0: GPL with its bootloader distribution exception; build
  collects its installed license files. Bundling does not make proprietary
  application licenses or asset licenses disappear.

Application branding is reused from this repository, with no new rights claim.
No signing certificate, online update service, analytics, or telemetry is used.
