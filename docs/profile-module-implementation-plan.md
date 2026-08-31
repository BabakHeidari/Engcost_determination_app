# Profile module implementation plan

## Phase status

This plan was created during Phase 2 because no existing profile implementation-plan document was present in the repository. It records architecture and phase boundaries only; it does not authorize or implement later-phase work.

| Phase | Status | Scope |
| --- | --- | --- |
| Phase 1 — current-state discovery | External/not present in this checkout | The requested `docs/profile-module-current-state.md` was not present. Phase 2 repeated the storage/authentication investigation needed for its decision. |
| Phase 2 — JSON storage architecture | Complete in documentation | Select the canonical store, define schemas, migration, password, locking, atomic-write, backup, Excel, and implementation decisions. |
| Phase 3 — JSON data-access layer | Complete | Centralized validation, locking, atomic writes, backups, and safe serializers. |
| Phase 4 — authentication migration | Complete | Canonical JSON login/current-user loading, legacy migration command, password reset flow, and authentication tests. Profile administration remains disabled. |
| Phase 5 and later | **Not started** | Profile rendering/APIs, administration, authorization management, and later rollout work remain separately scoped. |

## Phase 2 decision update

- Add a new versioned `app_data.json`, configured by `APP_DATA_FILE`, rather than promoting the inactive generated `Data/Overall/auth_data.json`.
- Use the Flask instance directory only as a safe development default; production supplies a protected external path.
- Make this file the sole writable source for users, profile factory assignments, role permissions, user overrides, and audit events after a one-time cutover.
- Treat `Data/Overall/auth_data.xlsx` as the current source and later as a read-only migration input. Do not dual-write or silently fall back to it.
- Keep costing/BOM/material/factory operational persistence unchanged.
- Replace legacy SHA-256 verification through a controlled reset/upgrade path with Werkzeug password helpers; never expose hashes.
- Centralize validation, authorization-aware mutations, cross-process locking, revisions, atomic replacement, and backups in one future repository service.

The complete decision, schemas, file-by-file plan, open decisions, and risks are in `docs/profile-json-storage-architecture.md`.

## Gates before any implementation phase

1. Approve role keys, hierarchy, permission semantics, factory-assignment rules, and legacy `access_level` mapping.
2. Approve username/email login policy and the source of missing user profile fields.
3. Approve mandatory-reset behavior, password policy, rate limiting, session revocation, and recovery workflow.
4. Confirm single-host/filesystem locking assumptions and deployment ownership/permission controls.
5. Approve audit scope/retention and backup/recovery objectives.
6. Define tests and rollback criteria before changing runtime authentication.

## Required future test groups

These runtime tests are planned, not added in Phase 2 because no runtime behavior was introduced. Phase 2 adds only a documentation-contract test for this decision record and stop boundary:

- schema acceptance/rejection and referential integrity;
- migration dry run, malformed/duplicate legacy rows, and idempotency;
- Werkzeug hashes, legacy upgrade/reset, invalid/absent hash fail-closed behavior, and non-disclosure;
- login, logout, active-user reload, password-change gating, and session invalidation;
- role/factory authorization and hostile client actor/permission fields;
- concurrent revisions, lock timeout, atomic replacement failures, and cleanup;
- backup creation and validated restore;
- Persian RTL/Jalali presentation boundaries after UI integration;
- regression checks proving costing modules and data contracts are unchanged.

## Phase 4 implementation decisions

- Runtime authentication consults only `APP_DATA_FILE` (default `instance/app_data.json`); it never falls back to either legacy credential artifact.
- The attended migration command strictly recognizes legacy SHA-256 hashes. Unknown values become `password_hash: null` and remain reset-required; no password is invented.
- Successful login stores only `user_id`, reloads active state from JSON on protected requests, and atomically records `last_login_at`.
- A reset-required account is restricted to the Persian RTL password-change and logout flow. New passwords are Werkzeug-generated salted hashes, limited to 12–256 Unicode characters without truncation.
- Password changes and their secret-free audit event share one locked atomic mutation. Profile rendering and administration were not connected.

## Stop point

Phase 4 ends after authentication cutover and its tests. Profile rendering still uses its existing demo-only page, and no Profile administration endpoint, permission editor, or later-phase feature was started.
