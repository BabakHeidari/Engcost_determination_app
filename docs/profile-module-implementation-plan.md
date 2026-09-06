# Profile module implementation plan

## Phase status

This plan was created during Phase 2 because no existing profile implementation-plan document was present in the repository. It records architecture and phase boundaries only; it does not authorize or implement later-phase work.

| Phase | Status | Scope |
| --- | --- | --- |
| Phase 1 — current-state discovery | External/not present in this checkout | The requested `docs/profile-module-current-state.md` was not present. Phase 2 repeated the storage/authentication investigation needed for its decision. |
| Phase 2 — JSON storage architecture | Complete in documentation | Select the canonical store, define schemas, migration, password, locking, atomic-write, backup, Excel, and implementation decisions. |
| Phase 3 — JSON data-access layer | Complete | Centralized validation, locking, atomic writes, backups, and safe serializers. |
| Phase 4 — authentication migration | Complete | Canonical JSON login/current-user loading, legacy migration command, password reset flow, and authentication tests. Profile administration remains disabled. |
| Phase 5 — read-only Profile | Complete | Safe JSON-backed rendering, scoped visibility, effective permissions, and real audit history. |
| Phase 6 — add user with initial password | **Complete** | Authorization-aware user creation, initial password hashing, atomic audit, Persian modal, and focused tests. General editing remains disabled. |
| Phase 6.7 — factory creation | **Complete** | Equal top-level-admin creation, canonical locked/atomic persistence and audit, and dynamic Add User registry integration. |
| Phase 7 and later | **Not started** | General user editing and other Profile mutations remain separately scoped. |

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
- Operators initialize the canonical store once with `python -m scripts.migrate_auth_to_json`; missing storage produces a controlled Persian 503 response rather than a traceback or legacy fallback.
- The attended migration command strictly recognizes legacy SHA-256 hashes. Unknown values become `password_hash: null` and remain reset-required; no password is invented.
- Successful login stores only `user_id`, reloads active state from JSON on protected requests, and atomically records `last_login_at`.
- A reset-required account is restricted to the Persian RTL password-change and logout flow. New passwords are Werkzeug-generated salted hashes, limited to 12–256 Unicode characters without truncation.
- Password changes and their secret-free audit event share one locked atomic mutation. Profile rendering and administration were not connected.

## Stop point

Phase 4 ends after authentication cutover and its tests. Profile rendering still uses its existing demo-only page, and no Profile administration endpoint, permission editor, or later-phase feature was started.

## Phase 5 implementation decisions

- The protected Profile route reloads one validated snapshot from the canonical JSON store and builds a dedicated, allow-listed view model.
- Global-scope roles may see active users and factories globally. Factory-scoped users see active users and the active factory in their assignment; non-factory, non-global users see only themselves and no factory registry.
- Effective permissions combine the authenticated user's role permissions with explicit allow/deny overrides on the server. The page displays these values but cannot mutate them.
- Audit history is sourced only from canonical audit events visible to the current user; absent events produce an explicit empty state. Secret-bearing details and internal revisions are never included.
- All add/edit user, factory, and privilege controls and demo data were removed from production rendering. Server-provided feature flags remain false for every unfinished mutation.

## Phase 5 stop point

Phase 5 ends with read-only Profile rendering and focused automated tests. No add-user, edit-user, factory mutation, privilege mutation, or later-phase endpoint was implemented.

## Phase 6 implementation decisions

- `POST /api/profile/users` is the sole create-user API. It derives the actor from the authenticated session and rejects client-supplied IDs, creator fields, hashes, and permission fields.
- The existing central 12–256 Unicode-character password policy is reused and now explicitly rejects empty or whitespace-only values. Passwords are compared without normalization or truncation and hashed immediately with Werkzeug.
- This historical Phase 6 role rule was superseded by Phase 6.5: either top-level administrator may create any of the three canonical roles with identical authority; ordinary users receive only explicit grants to active factories/modules.
- ID allocation, duplicate-email enforcement, actor/role/factory authorization, insertion, and the secret-free `user.created` audit event share one locked atomic transaction in the canonical JSON store.
- New accounts are active and have `must_change_password: true`; the existing first-login password-change gate is therefore reused.

## Phase 6 stop point

Phase 6 ends after Add User and initial-password behavior. General user editing, activation changes, password resets by administrators, factory mutation, and permission mutation were not started.

## Phase 6.5 — canonical access-model migration (complete)

Phase 6.5 replaces the organizational role hierarchy with exactly `IT_ADMIN`,
`FINANCE_ECONOMIC_ADMIN`, and `USER`. The two administrator roles are parallel
and receive implicit full access from server policy; `USER` receives no implicit
access. Optional `job_title` is display metadata only. Ordinary access is stored
as canonical, de-duplicated scope/module grant objects on each user. The old
Official Admin, Factory Admin, Office Staff, Factory Staff, one-factory-admin
rule, role permissions and user overrides are obsolete authorization concepts.

The Add User endpoint and Persian modal now accept `system_role`, `job_title`,
and a visual list of granular grants. Only either top-level administrator may
create an account. Administrator editing, deactivation, promotion and reset UI
remain Phase 7 work and were not started.

`READ` and `WRITE` are independent capabilities. `DASHBOARD`, `DESK`, `PROFILE`
and `GENERAL_PARAMETERS` are global based on their current routes;
`FACTORY_PARAMETERS`, `PRODUCT`, and `COST_CALCULATION` operate on selected
factory data and are factory-scoped. This classification is centralized in
`utils.profile_authorization`; unknown values fail closed.

Existing schema-v1 Profile files are migrated automatically on the first
runtime read or mutation, including the first login attempt. The automatic path
uses the same inter-process lock, backup, validation, and atomic replacement as
the operator command, so Phase 6 credentials continue working after deployment.
Operators may also migrate proactively before starting the application:

```bash
python -m scripts.migrate_profile_access_model
```

The command uses the central lock/backup/validated atomic replacement path.
Clearly identified IT and Official administrators map to `IT_ADMIN` and
`FINANCE_ECONOMIC_ADMIN`. Ambiguous ordinary legacy accounts are retained with
no grants and their IDs are recorded in
`metadata.access_model_migration.review_user_ids` for manual review.

## Phase 6.5A — canonical factory registry (complete)

Five operational factory identities were discovered and imported one-way into
the canonical JSON registry. Existing operational keys are stable IDs/codes;
manual canonical records are never overwritten. `ProfileDataStore` performs the
locked, validated, backed-up atomic merge, exposes a safe active-only list, and
server-side grant validation continues to reject inactive or unknown IDs.

The Add User modal receives active factories only through the Profile view
model, supports repeated rows for different factory/module permissions, displays
name plus code, and shows a truthful Persian empty-registry message. No demo
fallback or second runtime source was added. Phase 7 remains not started. Full
source inventory and identity decisions are in
`docs/factory-registry-discovery.md`.

## Phase 6.7 — top-level factory creation (complete)

Both `IT_ADMIN` and `FINANCE_ECONOMIC_ADMIN`, and only those roles, may create
an active factory through the Persian Profile modal and
`POST /api/profile/factories`. The actor is derived from the authenticated
session and revalidated inside the store lock. Factory and `FACTORY_CREATED`
audit insertion share one canonical mutation; client authority/internal fields,
duplicate case-insensitive codes/IDs, and normalized duplicate display names
are rejected.

The response returns only safe factory fields. The page adds the returned
factory to its canonical registry display and the Add User grant selectors
without a restart or hard-coded browser registry. Top-level access remains
implicit through `system_role`; no grants are added to administrators or
ordinary users. No data migration was required. Factory edit/deactivate/delete
strategy is deferred: preserve stable IDs and historical references and prefer
deactivation over deletion. General user editing and all Phase 7 work were not
started.
