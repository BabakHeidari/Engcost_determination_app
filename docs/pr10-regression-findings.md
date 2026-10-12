# PR-10 backend regression findings

The exact predecessor baseline is `fc373ca92e97c91d3d3b4a1a181096cbdf733c37`.
Its complete non-browser suite reproduced **31 failed, 607 passed, 0 skipped**
across 638 tests in 33.00 seconds. This is an observed result, not an inherited
claim from PR-09A. Every failure below was investigated against the later merged
contracts. All 31 came from outdated fixtures or source-location assertions;
none required changing approved operational behavior or costing formulas.

## Isolation and reproducibility

Baseline source came from `git archive` of the exact SHA into
`work/pr10-base-run`. An empty canonical profile JSON was deliberately initialized
at `work/pr10-evidence/base-profile/app_data.json` before pytest collection or
application import. `APP_DATA_FILE` was set to that absolute path and
`APP_SECRET_KEY` to a fixture-only key for the process. Startup therefore had no
registered factory to migrate. Tests prepared their own temporary stores and
operational fixtures. Candidate tests ran from `work/pr10-current-run`, a separate
archive overlaid with current source, rather than importing the operational
checkout. No operational source-save route, migration, or repair was invoked.

A post-run blob-hash comparison against the exact Git tree found **zero changed
tracked baseline files**. Generated Python caches are outside the source tree
comparison. The operational checkout's `Data/` and `instance/` were not edited.

Validated runtime: Python 3.12.14, Flask 3.1.2, Werkzeug 3.1.9, pandas 2.2.3,
openpyxl 3.1.5, pytest 9.1.1. Node-backed models and exact-number tests were
included; the three existing Chromium suites were excluded from this particular
backend command and are reported separately. Complete dependency versions and
final release results are in [the evidence index](evidence/pr10/README.md).

```bash
git archive fc373ca92e97c91d3d3b4a1a181096cbdf733c37 | tar -x -C work/pr10-base-run
cd work/pr10-base-run
APP_DATA_FILE=/workspace/Engcost_determination_app/work/pr10-evidence/base-profile/app_data.json \
APP_SECRET_KEY=pr10-isolated-regression \
/workspace/Engcost_determination_app/work/pr10-venv/bin/python -m pytest tests \
  --ignore=tests/test_dashboard_frontend.py \
  --ignore=tests/test_dashboard_sensitivity_frontend.py \
  --ignore=tests/test_dashboard_visual_frontend.py -q \
  --junitxml=/workspace/Engcost_determination_app/work/pr10-evidence/base-backend.xml
```

The exact captured command above assumes the prepared isolated profile and shared
runtime; the release setup documents provide portable clean-checkout preparation.
[Baseline JUnit](evidence/pr10/base-backend.xml) records each failure.
[Candidate JUnit](evidence/pr10/candidate-backend.xml) records final integration
results. The focused repaired suites additionally produced 115 passed, 0 failed,
0 skipped before the configured-root filter fixture adjustment; the final focused
run includes that fixture and is captured as `current-regression-targeted.xml`.

## Approved contracts used for triage

- **V2:** [Factory Configuration V2](factory-configuration-v2.md) makes installed
  configuration the canonical source; valid detailed pools require subject and
  cost columns and win over a disagreeing old aggregate with a recorded warning.
- **Cost:** [Shared cost engine](pr05-shared-cost-engine.md) and
  [Cost Calculation workflow](pr05-5-cost-calculation-runbook.md) preserve the
  canonical four-part identity, live 98,000,000 IRR BOM golden, 100 IRR allocated
  Payroll, typed missing input, no invented zero, and initial-period lifecycle.
- **Access:** [Profile access model](profile-access-control-model.md),
  [authorization matrix](authorization-matrix.md), and
  [access-denied UX](access-denied-ux.md) require explicit Profile READ for USER,
  HTTP 403 for administrative denials, and mandatory Desk READ for active users.
- **Profile:** [User administration](profile-user-management.md),
  [frontend extraction](profile-frontend-phase-10.md), and
  [completed phase plan](profile-module-implementation-plan.md) authorize the
  current admin editor, revision metadata, lifecycle flags and external scripts.
  Passwords and hashes remain excluded from rendered/API data and audit.
- **Locale:** [Localization audit](localization-audit.md) and runtime defaults
  distinguish Persian language `fa` from locale `fa-IR`; the login shell and
  shared application layout legitimately use those respective language tags.

## Every reproduced failure

Each row is **P2: verification false negative**, resolved by correcting the
fixture or assertion location. An uninvestigated or failing check blocked
trustworthy release evidence until repaired; no row is waived because baseline
failed. Current behavior is exercised rather than bypassed. Parameterized failures
are listed separately to preserve the exact count of 31. No assertion was
discarded without retaining its underlying guarantee, and no skip or xfail was
added.

| # | Baseline test and affected behavior | Root cause / contract conflict | Resolution and retained guarantee |
|---|---|---|---|
| 1 | `test_cost_calculation_workflow::test_catalogue_maps_operational_key_to_canonical_id_and_hides_unauthorized` — Cost page factory label | Fixture searched unescaped Persian in Jinja JSON; JSON legitimately Unicode-escapes it. | Parse actual `tableJSON`; assert the entire authorized row, canonical ID and label, plus exclusion of operational/secret IDs. |
| 2 | `test_cost_calculation_workflow::test_single_route_golden_and_bulk_use_same_four_part_identity` — single/bulk costing | Old cost-only pool fixtures lack required V2 detailed `subject` column; rejection is correct. | Prepare valid detailed pools and deliberately install V2. Keep exact single/bulk 98,000,100 IRR, identity, and coverage assertions. |
| 3 | `test_cost_calculation_workflow::test_missing_source_response_exposes_diagnostic_without_zero_fallback` — missing source | Fixture deleted a legacy source and malformed remaining pools; installed V2 is authoritative. | Delete installed V2 Payroll file; keep 422, named missing source, expected canonical path, diagnostic reason and absence of a numeric fallback. |
| 4 | `test_cost_calculation_workflow::test_first_calculation_auto_initializes_period_and_continues` — first period | Invalid old detailed pool shape prevented costing after correct initialization. | Valid V2 preparation restores the original exact result while retaining INITIAL, ACTIVE, approved/active flags and SYSTEM_INITIALIZATION provenance. |
| 5 | `test_cost_calculation_workflow::test_frontend_distinguishes_failures_zero_and_stale_responses` — error handling | Non-JSON branch now distinguishes authentication redirects using a conditional rather than a literal object field. | Inspect current conditional; preserve all HTTP/network/invalid-JSON branches, stale sequence guard and no-zero assertions. |
| 6 | `test_factory_configuration_startup::test_startup_store_access_is_inside_application_context` — Flask initialization | `current_app` is a Flask `LocalProxy`; Python object identity with the proxied app is false. | Compare `_get_current_object()` to the exact app; retain context, configuration, instance path and every migration call. |
| 7 | `test_factory_navigation::test_factory_pages_use_bookmarkable_get_navigation` — factory breadcrumbs | V2 uses server-generated pool links; source assertion expected old JavaScript interpolation and exact incidental spacing. | Check current `pool_urls` link and whitespace-independent breadcrumb call; retain GET/POST compatibility, 303 and no-history-back navigation. |
| 8 | `test_factory_registry::test_add_user_template_uses_server_registry_and_has_truthful_empty_state` — grant options | Phase 10 moved option creation into safe external DOM code; old inline Jinja selector is gone. | Assert canonical JSON handoff, canonical `option.value`, active filtering, name/code label, disabled empty selector and truthful scoped empty message. |
| 9 | `test_friendly_forbidden::test_safe_fallback_uses_effective_access[grants1-/profile/profile-…]` — recovery destination | Old fixture expected Profile first despite mandatory Desk READ introduced in Phase 8.6. | Expect Desk and match the actual recovery button, then follow it and require 200. Other permission checks remain unchanged. |
| 10 | `test_legacy_costing_migration::test_loader_self_heals_recoverable_pool_and_calculates_normally` — summary migration | Fixture expected a new legacy sibling file; V2 now creates canonical `configuration/cost_pools/Payroll.json`. | Assert installed 100 pool, stable `LegacyMigratedTotal` ID, no sibling dual write, and exact calculated 16 IRR. |
| 11 | `test_legacy_costing_migration::test_loader_blocks_generated_incomplete_source_with_diagnostic` — absent prediction | V2 installs a NEEDS_INPUT prediction with null; numeric validation returns MISSING_NUMERIC_INPUT instead of legacy placeholder metadata. | Require MISSING_INPUT and exact code, installed NEEDS_INPUT/null value, and source diagnostic for the same active period. No prediction or zero is invented. |
| 12 | `test_legacy_costing_migration::test_loader_reports_conflict_when_healing_cannot_safely_reconcile` — detail/summary disagreement | Old loader expected a fatal aggregate conflict; V2 approved precedence retains valid detail and warns. | Renamed to `test_loader_preserves_detailed_pool_and_reports_v2_summary_mismatch`; assert 999 retained, 105.9 IRR exact result, explicit warning in manifest and unchanged legacy detail. |
| 13 | `test_module_persian_localization::ModulePersianLocalizationTests::test_factory_parameters_display_labels_preserve_contract_fields` — factory UI labels | V2 removed direct whole-structure save and receives weight schema from server JSON; old literals no longer belong to the template. | Check Persian derived-total explanation, weight save control, canonical JSON handoff and current endpoint; retain prediction-field assertion. |
| 14 | `test_product_catalog::test_production_selection_and_options_exclude_v2_configuration` — authorized Product selection | Safe Jinja JSON escapes Persian letters as well as apostrophe; exact raw-string assertion was invalid. | Parse shipped `rawData`, require the exact apostrophe product and escaped apostrophe, preserve XSS/hidden-product/V2 exclusion and empty-catalogue guarantees. Replace service stub with real USER factory authorization. |
| 15 | `test_profile_access_model::test_profile_template_uses_visual_selector_not_raw_json` — admin editor revision | Phase 10 moved behavior to `profile-page.js` and named the form `editForm`. | Verify revision assignment in the shipped external script; keep visual-manager loading and absence of raw grant JSON/editor fields. |
| 16 | `test_profile_add_user::test_authorization_and_validation_failures[usr_staff-changes0-400]` — account creation denial | User administration now authorizes before business validation; approved denial is 403. | Require 403 and byte-identical profile document. Legitimate malformed admin payloads remain 400. |
| 17 | `test_profile_add_user::test_authorization_and_validation_failures[usr_factory-changes5-400]` — account creation denial | Same obsolete expected 400; a factory USER has no administrative authority. | Require 403 and no profile/audit mutation; keep the full validation matrix. |
| 18 | `test_profile_add_user::test_modal_password_contract_and_passwords_are_not_prefilled` — password clearing | Event handlers moved to external page script. | Verify linked script, modal close cleanup and clearing in that script; preserve password input/autocomplete and no local/session storage checks across HTML and JS. |
| 19 | `test_profile_factory_creation::test_user_and_job_title_cannot_authorize_api_or_ui` — factory administration denial | Approved administrative denial is 403 rather than historical 400. | Require API 403, unchanged empty registry and Profile page 403 for USER lacking Profile READ; no create control appears. |
| 20 | `test_profile_factory_creation::test_factory_persists_across_store_and_application_reload` — new factory options | Selector now builds from canonical JSON in external DOM code, not pre-rendered `<option>`. | Parse exact canonical factory configuration after reload; assert ID/name/code/location/activity and the actual DOM option value/name formatter. |
| 21 | `test_profile_factory_creation::test_admin_ui_uses_server_id_and_updates_factory_grant_options` — registry refresh | Old inline `addFactoryOption`/`grantTemplate` paths were replaced by API creation followed by fresh page reload. | Verify current API request, reload and metadata-driven modules/options; retain real modal fields and no client-generated factory ID. |
| 22 | `test_profile_readonly::test_ordinary_user_sees_only_self_and_real_audit` — personal audit | Fixture granted Product READ but no Profile READ, so backend correctly returned 403. | Give explicit Profile READ, require 200 and retain self-only names, real event and cross-factory/user exclusion. |
| 23 | `test_profile_readonly::test_empty_history_is_truthful_and_page_is_read_only` — USER empty history | Same missing Profile READ. | Require authorized 200 with truthful empty history, read-only explanation and no administrative controls. |
| 24 | `test_profile_readonly::test_no_demo_fallback_and_persian_rtl_remain` — USER Profile rendering | Same missing Profile READ. | Require 200 Persian RTL profile and effective grants, retaining every fake/demo-marker exclusion. |
| 25 | `test_profile_readonly::test_safe_view_model_contains_no_secret_keys` — safe serialization | Test classified public optimistic-concurrency `revision` as a secret, contradicting merged admin editor contract. | Require exact revision and reject real secret keys; retain blanket absence of password content. |
| 26 | `test_profile_storage_architecture_docs::test_phase_plan_records_authentication_stop_boundary` — phase evidence | Assertion required Phase 7+ not started although phases 9–12 are merged and complete. | Keep historical phase 4–6 boundaries and assert current completed phases plus explicit absence of a later business capability. |
| 27 | `test_profile_user_management::test_peer_roles_equally_edit_ordinary_user_and_job_title_has_no_authority[usr_it]` — admin edit | Fixture submitted noncanonical out-of-order/duplicate permission array; current storage rejects it. | Submit canonical READ/WRITE for successful edit; retain exact persistence/job-title/no-Profile-authority checks. Add explicit malformed-array rejection/no-mutation checks. |
| 28 | `test_profile_user_management::test_peer_roles_equally_edit_ordinary_user_and_job_title_has_no_authority[usr_finance]` — peer admin edit | Same noncanonical array. | Same repaired positive and negative checks prove equal behavior of both privileged roles. |
| 29 | `test_profile_user_management::test_user_cannot_edit_and_unknown_or_inactive_grants_fail_closed` — USER edit denial | Approved access denial is 403, distinct from invalid-grant 400. | Require USER 403 and unchanged profile; retain unknown/inactive 400, add duplicate/out-of-order grant rejection. |
| 30 | `test_profile_user_management::test_password_reset_is_separate_safe_and_stale_edits_conflict` — password reset response | Blanket search for the word password rejected legitimate `must_change_password`, timestamp and scheme metadata. | Reject password/hash fields and plaintext, assert reset-required flag/revision; retain hash verification, safe audit and stale edit 409. |
| 31 | `test_rtl_foundation::RtlFoundationTests::test_shared_layout_loads_with_persian_rtl_context` — login/shared shell | Login is a standalone fa-IR shell and does not include shared `main.js`; test incorrectly treated it as the authenticated base layout. | Require login 200/fa-IR/RTL/styles, then render actual USER Desk 200/fa/RTL/shared script from an isolated profile. |

## Additional fixture hardening and release impact

Current filter initialization correctly uses the configured operational data root.
The two existing filter route tests used a zero-argument constructor stub; that
stub now accepts arguments while still returning its own isolated hierarchy. All
authorization, cascade and parent-validation assertions are preserved. Shared app
configuration in Cost Calculation and that filter fixture is restored through
pytest monkeypatch cleanup, preventing one fixture's temporary paths from leaking
into a later test. This adjustment is distinct from the original 31 failures.

The Product smoke now uses real `FactoryService`, a canonical ID different from
its operational directory, an ordinary USER's explicit Product READ grant, a
second forbidden factory, missing/malformed metadata, a hostile value, actual
Flask production-selection/options routes and a genuinely empty catalogue. Cost
Calculation retains independent authorized page and exact single/bulk goldens.

These repaired checks do not constitute owner UAT or production release approval.
Final technical status and any new hardening blockers belong to the release
readiness report. Owner sign-off remains **PENDING**.
