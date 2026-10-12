# PR-10 Dashboard security findings

The review covers the Dashboard page, filter options, retained Cost Analysis
and Sensitivity endpoints, and the current visual wrapper and A/B lab. The base
is the merged PR-09A commit
`fc373ca92e97c91d3d3b4a1a181096cbdf733c37`. No authorization policy, session
middleware, source-save route, costing formula or operational data was changed.

## Verified boundary fixes

- Filter options reject unknown or repeated query fields, explicit ALL factories,
  empty/whitespace/control-character selections and overlong values before
  operational lookup. The configured isolated costing root is used consistently
  with the analysis routes. Expected hierarchy failures retain 400/503 distinctions;
  unexpected failures return a typed 500 without exposing exception text or paths.
- Cost Analysis rejects the DEL control character as well as other malformed
  selections. A typed or report-level `CALCULATION_ERROR` produces HTTP 500 in
  both the canonical and visual envelopes; input failures retain HTTP 422.
- Both analytical POST routes retain cached middleware body reads and preserve
  the stricter of the existing application/per-request limit and 64 KiB. A
  terminated WSGI stream is checked with one bounded extra byte when its prefix
  reaches that limit. Valid JSON followed by oversized whitespace therefore
  cannot be accepted through a truncated prefix. Missing-length streams without
  a termination indication fail closed; terminated streams work within the bound,
  including when a misleading zero length hint is present.
- A non-string experiment type is a typed 400 before source capture. Duplicate
  JSON keys, non-finite JSON constants, unknown request fields and forged
  comparison/source payloads remain rejected. Existing override, range, point,
  alias and reserved-evaluation limits are preserved.
- Duplicate explicit BOM row IDs are typed `AMBIGUOUS_INPUT` in the loader and
  pure engine, so an override cannot ambiguously control multiple independent
  rows. Repeated material names with distinct row IDs remain supported.

## Authorization and disclosure evidence

`tests/test_dashboard_release_security.py` exercises all seven page/action
boundaries with Dashboard-only, each individual source group, both groups,
wrong-factory grants, no access and both privileged administrator roles.
General-only or factory-only in these fixtures includes the required Dashboard
grant; separate users with only a source grant are denied. Mixed page admission
and exact factory action checks remain distinct. Unknown factories are 404;
known inactive or unauthorized factories are 403 before hierarchy/source lookup.
An unrelated global Dashboard grant does not grant a factory action.

Every request rechecks current session/user/grant state. Logout, missing/expired
users, inactive users, mandatory password changes and revoked Dashboard access
are covered. A parameter ID copied from a previous listing cannot survive source
group revocation. READ is sufficient for permitted hypothetical controls;
MODIFY is not required. Authorized Cost Analysis derived outputs retain their
existing Dashboard-only admission.

The three Sensitivity envelopes are recursively inspected for forbidden nested
prices, FX, historical BOM values and source paths. Without factory-parameter
READ, prediction and raw allocation inputs are omitted; without the relevant
source grant, restricted provenance is omitted. Existing POST protection is
tested on both POST routes without any exemption. Denied, invalid and successful
requests also preserve prepared fixture file/directory hashes and mtimes.

The shipped client adapter, DOM, tooltip and CSV evidence is documented in
[client findings](pr10-client-findings.md) and the final release browser results.
Browser checks use actual shipped scripts; API fixture checks alone do not prove
DOM disclosure behavior or deployment-server chunked transport behavior.

## Results and reproduction

The final frozen-source backend JUnit contains **231 passing security cases**,
0 failures/errors/skips, within the **977 passing** backend checks. The earlier
220-case run preceded the final streaming-body cases and is not final release
evidence. The [candidate JUnit and command/environment record](evidence/pr10/README.md)
are authoritative for final counts.

```bash
python -m pytest tests/test_dashboard_release_security.py -q \
  --junitxml=work/pr10-evidence/release-security.xml
```

The suite registers real Dashboard routes on a standalone Flask fixture using
temporary V2 operational inputs, bindings and profile storage. It does not import
`app.py`, initialize the operational runtime, run migrations or invoke source-save
routes. Deliberate fixture preparation happens before no-write inventories.
Actual application initialization is checked separately in the isolated startup
suite, as documented in the release evidence.

The independent production-code review found no unresolved P0/P1 in the reviewed
authorization, bounded POST parsing, source redaction or request-local prediction
reuse. This is a scoped review finding, not production approval. Final technical
checks and owner UAT retain separate statuses; owner sign-off remains **PENDING**.
