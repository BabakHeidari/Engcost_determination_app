# Profile JSON storage architecture

## Status and scope

This is the Phase 2 architecture decision record. It documents the current system and the intended storage design; it does **not** change routes, authentication, persistence, authorization, UI behavior, or costing data. The requested earlier documents `docs/profile-module-current-state.md` and `docs/profile-module-implementation-plan.md` were not present when this investigation began. A Phase 2 implementation-plan update is added separately.

## 1. Existing storage mechanism

The application is file based. There is no active relational persistence layer:

- The **real credential source used at login** is `Data/Overall/auth_data.xlsx`. `utils.auth.authenticate()` reads it with pandas on every authentication attempt.
- `Data/Overall/auth_data.json` is a generated/parallel representation, but no authentication or profile route reads it. It must not be treated as a second writable source of truth. It has the column-oriented shape described below.
- `Data_Better_Structure/auth_data.json` is empty and inactive.
- `Data/Overall/saba.db` exists and `utils/dbmanager.py` contains inactive/commented SQLite experiments. Neither participates in the active request flow and neither should be revived for profile work.
- Operational factory data is distributed between `Data/Overall/factories.json` and per-factory files below `Data/Factories/`. These files feed existing factory and costing behavior and remain outside this profile/authentication migration.
- The profile page has no runtime persistence. Its user, factory, role, permission, and history records are JavaScript demo constants in `templates/profile/profile.html`; the backend injection variables are currently absent because the route passes no data.

Existing writers use direct `open(..., "w")`, `json.dump()`, pandas Excel writers, or the `utils.xlsxTojson.to_json()` wrapper. No reusable file lock, atomic replacement, transaction, revision check, or application-data repository abstraction exists.

## 2. Existing authentication flow

The complete active flow is:

```text
GET /login
  -> modules.auth.routes.login
  -> templates/auth/login.html

POST /login (username, password form fields)
  -> modules.auth.routes.login
  -> utils.auth.authenticate(username, password)
  -> pandas.read_excel(Data/Overall/auth_data.xlsx)
  -> lowercase the lookup username
  -> SHA-256 hash the submitted UTF-8 password
  -> compare that digest to the row's password_hash
  -> return the string "OK" or "NotOK"
  -> on success set Flask session["user"] to the submitted username
  -> redirect to /workdesk
  -> @login_required checks only that session["user"] exists
  -> render the protected page
```

`GET /logout` calls `session.clear()` and redirects to login. Flask's default signed client-side session cookie is used. No stable user ID, role, active status, session revision, last-login value, or server-side current-user object is stored or reloaded. The `app.inject_user` context processor derives a display name directly from `session["user"]`; it does not look up a user record. Consequently, changes such as deactivation cannot currently invalidate an already issued session, and possession of the session key is the only protected-route check.

The profile route is `GET /profile/profile`, guarded by the same `login_required` decorator. It renders the template without `current_user`, `all_users`, or `factories`. All profile API examples in `modules/profile/routes.py` are commented placeholders and therefore expose no active endpoints.

## 3. Existing user-file format

`Data/Overall/auth_data.xlsx` has three logical columns:

| Field | Current meaning |
| --- | --- |
| `username` | Login identifier; lookup lowercases submitted input but does not otherwise normalize stored values. |
| `password_hash` | Unsalted hexadecimal SHA-256 digest. It is not plaintext, but it is not an appropriate adaptive password hash. |
| `access_level` | Coarse role/access value; it is not loaded into the session or enforced by routes. |

The inactive `Data/Overall/auth_data.json` mirrors those columns in the project's column-oriented table convention:

```json
{
  "_order": ["username", "password_hash", "access_level"],
  "data": {
    "username": ["..."],
    "password_hash": ["..."],
    "access_level": ["..."]
  }
}
```

The store has no stable ID, full name, email, factory assignment, active/first-login state, timestamps, provenance, revision, overrides, or audit events. The only password creation helper, `utils.auth.accounter()`, interactively creates the same raw SHA-256 digest and rewrites the Excel file; it is not a web route.

## 4. Canonical file decision

### Decision

Introduce one new canonical profile/authentication file, referred to as `app_data.json`, with its path provided by `APP_DATA_FILE`. Use a safe development default below Flask's non-public `instance/` directory, for example `instance/app_data.json`; production must set an external path such as:

```text
APP_DATA_FILE=/secure/application-data/app_data.json
```

Expanding `Data/Overall/auth_data.json` was rejected because it is a generated, column-oriented shadow of an Excel credential file, its name implies credentials rather than the complete identity/access domain, and adopting it risks continued Excel/JSON dual writes. A new schema makes the one-time cutover explicit and permits clean validation and versioning.

After migration, `app_data.json` is the **only writable and authoritative runtime source for users, the profile factory registry, role permissions, user overrides, and audit events**. The old XLSX and JSON credential files become read-only migration inputs and must not be consulted during normal requests. They should be archived outside the runtime path after verified cutover.

This decision does not consolidate or alter BOM, material, production, or factory-cost files. Those existing operational stores and calculations are unrelated to this phase. The `factories` collection below is the canonical identity/access registry used for user assignment; later implementation must map it deliberately to existing factory identifiers without rewriting costing inputs.

## 5. Proposed JSON schema

All timestamps are canonical UTC RFC 3339 strings (for example `2026-08-01T12:30:00Z`). Jalali conversion remains a presentation-only concern.

```json
{
  "schema_version": 1,
  "metadata": {
    "created_at": "2026-08-01T12:30:00Z",
    "updated_at": "2026-08-01T12:30:00Z",
    "revision": 1,
    "migration": {
      "source": "Data/Overall/auth_data.xlsx",
      "completed_at": "2026-08-01T12:30:00Z"
    }
  },
  "users": [],
  "factories": [],
  "role_permissions": {},
  "user_permission_overrides": [],
  "audit_events": []
}
```

Unknown top-level keys should be rejected for schema version 1. Reads must validate the full document before returning domain data. Writes must validate the proposed complete document before replacement. Array order has no authorization meaning.

## 6. User schema

```json
{
  "id": "usr_01J4A...",
  "username": "admin",
  "full_name": "نام و نام خانوادگی",
  "email": "user@example.com",
  "password_hash": "scrypt:...",
  "role": "IT Admin",
  "factory_id": null,
  "is_active": true,
  "must_change_password": true,
  "created_at": "2026-08-01T12:30:00Z",
  "updated_at": "2026-08-01T12:30:00Z",
  "created_by_user_id": null,
  "updated_by_user_id": null,
  "last_login_at": null,
  "password_changed_at": null,
  "revision": 1
}
```

Rules:

- `id` is an opaque, generated, immutable stable identifier (UUID or ULID string); array position and email are never identifiers.
- `username` remains during compatibility migration because the current login form is username based. It is trimmed and case-normalized for lookup and unique under that normalization.
- `email` is trimmed, Unicode-normalized as appropriate, lowercased for comparison, syntactically validated, and unique. The stored value is the normalized value.
- `full_name` is required display text and must be length bounded and escaped normally by Jinja/DOM APIs.
- `password_hash` is required only for an account allowed to use password login. It is accepted from no profile API and returned by no serializer. A missing/invalid hash makes login fail closed.
- `role` must be one of the server-defined keys in `role_permissions`; clients cannot invent roles.
- `factory_id` is required only for factory-scoped roles and must reference an active factory; global/office roles use `null`.
- `is_active` is server enforced at login and on every current-user load.
- `must_change_password` forces an authenticated user into the future password-change flow before other protected functions. The enforcement design belongs to the authentication implementation phase, not this phase.
- Creator/updater IDs reference users. `null` is permitted only for bootstrap/migration system actions and must be explained by the associated audit event.
- `revision` is a positive integer incremented for each user mutation and supports optimistic conflict detection.

Password hashes must never appear in templates, API responses, JavaScript, logs, exceptions, audit event details, exports, or backups intended for administrative inspection.

## 7. Factory schema

```json
{
  "id": "fac_dinmohamadpour",
  "code": "DIN",
  "name": "DinMohamadpour",
  "display_name": "کارخانه دین‌محمدپور",
  "location": null,
  "is_active": true,
  "operational_key": "DinMohamadpour",
  "created_at": "2026-08-01T12:30:00Z",
  "updated_at": "2026-08-01T12:30:00Z",
  "created_by_user_id": null,
  "updated_by_user_id": null,
  "revision": 1
}
```

`id` and normalized `code` are unique and immutable. `operational_key` is an explicit, unique mapping to the existing factory directory/value when one exists; it avoids treating a display label or filesystem path as an identity. This registry must not embed factory costs, paths, BOMs, or calculation fields. Deactivation is preferred to deletion when referenced by users or audit events.

## 8. Permission schema

Role definitions are persisted once, but every authorization decision is made by server code against known module/action identifiers.

```json
{
  "role_permissions": {
    "IT Admin": {
      "scope": "global",
      "permissions": {
        "user_profile": ["read", "create_user", "update_user", "manage_permissions"],
        "factories": ["read", "create"]
      }
    }
  },
  "user_permission_overrides": [
    {
      "id": "upo_01J4A...",
      "user_id": "usr_01J4A...",
      "effect": "allow",
      "module": "dashboard",
      "actions": ["read"],
      "factory_id": null,
      "created_at": "2026-08-01T12:30:00Z",
      "created_by_user_id": "usr_01J4A...",
      "revision": 1
    }
  ]
}
```

The current JavaScript names (`IT Admin`, `Official Admin`, `Factory Admin`, `Office Staff`, `Factory Staff`; module privilege levels `Read`, `Write`, `Modify`) are only a UI prototype, not enforced definitions. Before implementation, product owners must approve the role matrix and the meaning of generic `write` versus `modify`. The backend must compute effective permissions from the authenticated user, role, scope, and overrides. It must ignore actor IDs, roles, or privileges supplied by the browser. Overrides may only narrow or grant within the acting administrator's own delegated authority, following a documented server-side hierarchy.

## 9. Audit schema

```json
{
  "id": "aud_01J4A...",
  "occurred_at": "2026-08-01T12:30:00Z",
  "actor_user_id": "usr_01J4A...",
  "action": "user.permissions_updated",
  "target_type": "user",
  "target_id": "usr_01J4A...",
  "factory_id": null,
  "request_id": "req_01J4A...",
  "outcome": "success",
  "details": {
    "changed_fields": ["role", "factory_id"]
  }
}
```

Audit events are append-only in normal operation. Events contain stable IDs and minimal non-secret metadata, never passwords, password hashes, session cookies, raw request bodies, or full before/after user documents. Failed login auditing, if approved, should use a normalized/redacted identifier and rate-aware retention rather than disclosing whether an account exists. The random history generated by `generateHistoryForUser()` in the template is demo-only and is not an audit source.

Because audit growth can make a single JSON document expensive, retention and archival limits must be decided before implementation. Archival is a controlled backup/reporting operation; live authorization and current profile history still read only the canonical file.

## 10. Password-hashing strategy

The present unsalted single-round SHA-256 comparison must be supported only for one-time migration compatibility. It is fast and therefore unsuitable for password storage.

The target uses Werkzeug's maintained helpers already supplied through Flask:

- Hash new/reset passwords with `werkzeug.security.generate_password_hash(password)` using the dependency's supported default algorithm (currently an adaptive salted scheme); do not hand-build cryptography or persist an algorithm separately from the encoded hash.
- Verify target hashes with `werkzeug.security.check_password_hash(stored_hash, submitted_password)`.
- Apply server-side password length/quality rules and rate limiting in the implementation phase. Never trim or normalize password characters silently.

Migration behavior:

1. Identify legacy hashes strictly as 64-character hexadecimal SHA-256 values during a controlled migration, not by trying multiple algorithms indefinitely.
2. Import the digest into `password_hash` with migration metadata that records `legacy_sha256` status without recording the digest in an audit event.
3. On the first successful legacy verification, immediately generate a Werkzeug hash, set `must_change_password` according to the approved policy, update `password_changed_at` only when the user actually chooses a new password, increment revisions, and atomically persist the document.
4. Prefer issuing a one-time administrative reset and setting `must_change_password=true` for all imported users. Accounts whose source value is absent, malformed, duplicated ambiguously, or otherwise unverifiable are imported inactive (or blocked from password login) and require an administrator-controlled reset. There is no plaintext recovery.
5. Once all accounts have been reset/upgraded or the migration deadline passes, remove the legacy verifier. Never create new SHA-256-only hashes.

First-login enforcement must be server side. A flagged user may access only logout and the password-change form/API until a valid new password is stored. Successful change rotates/clears other session state as supported, writes a sanitized audit event, sets `must_change_password=false`, and updates the relevant timestamps/revisions.

## 11. Existing-user migration strategy

Migration is a separate, explicitly invoked, idempotent command—not an implicit action during application import or every startup.

1. Back up and checksum the legacy XLSX; restrict access to the migration operator.
2. Read `Data/Overall/auth_data.xlsx` once and validate required columns, normalized username uniqueness, hash shape, and recognized `access_level` values. Never log rows or hashes.
3. Create stable user IDs. Map `access_level` through an explicitly approved role mapping; do not guess unknown values.
4. Populate required missing full names/emails through an approved input or use a documented incomplete-account state that remains inactive. Do not fabricate routable email addresses.
5. Build factories from the existing factory directory/list using stable IDs and `operational_key` mappings, without changing operational files.
6. Write a complete version-1 candidate to a new file, validate it, fsync it, and atomically install it. Refuse to overwrite an initialized destination unless an explicit, safe recovery procedure is used.
7. Run migration verification: counts, unique constraints, references, permissions, login/reset cases, and absence of hashes in output surfaces/logs.
8. Configure the application to use only `APP_DATA_FILE`. Make legacy stores read-only and then archive them securely. Do not dual-write or fall back silently to Excel.

Rollback restores the pre-cutover configuration and protected legacy backup only before new canonical writes are accepted. After live mutations, rollback requires an intentional reverse/forward recovery plan; copying stale Excel over the canonical file is prohibited.

## 12. File placement and permissions

- Keep the live file outside `static/` and `templates/` and do not add a Flask download route.
- Resolve `APP_DATA_FILE` at startup. A relative development value is resolved against Flask's instance path, not the process working directory. Production should use a mounted external directory.
- The containing directory should be owned by the service account with mode `0700`; the data file, lock file, backups, and temporary files should use mode `0600` (or the platform-equivalent least privilege). Reject symlinks/unexpected file types where practical.
- Fail startup clearly when production configuration is absent, unreadable, invalid, or insecure; do not fall back to a credential file committed to Git.
- Commit only a hash-free example such as `instance/app_data.example.json` in the later implementation phase. Ignore `instance/app_data.json`, temporary files, locks, and backups. Production credentials and hashes must never be committed.

## 13. Locking strategy

Use one repository/service layer for every read-modify-write operation. Use a separate sibling lock file (for example `app_data.json.lock`) because locking the data inode itself is unsafe across atomic replacement.

- Take a shared lock for reads where the platform/library supports reliable shared locks; take an exclusive lock for the entire read-validate-authorize-modify-validate-write sequence.
- Use an established cross-process locking library, or a small platform adapter around operating-system advisory locks; do not use an in-process `threading.Lock` alone.
- Apply a bounded timeout and return a controlled service-unavailable/conflict response instead of waiting forever.
- Under the exclusive lock, re-read the latest document and check document/user revisions to prevent lost updates from stale forms.
- All application processes and maintenance/migration commands must use the same lock protocol. This design supports a single host/shared filesystem with lock semantics; network filesystems require explicit verification. It is not intended as a horizontally distributed database substitute.

## 14. Atomic-write strategy

While holding the exclusive lock:

1. Load and fully validate the current document and expected revision.
2. Apply the authorized mutation in memory, append the sanitized audit event, and increment entity/document revisions and `metadata.updated_at`.
3. Serialize deterministically as UTF-8 JSON to a uniquely named temporary file in the **same directory** as the target. Set restrictive permissions at creation.
4. Flush and `fsync()` the temporary file.
5. Parse and validate the temporary file again.
6. Use `os.replace(temp_path, target_path)` for same-filesystem atomic replacement.
7. `fsync()` the containing directory on platforms that support it.
8. Clean up the temporary file on failure while retaining the lock until state is known.

Never truncate the live file in place. The application must treat malformed JSON, unsupported schema versions, broken references, and failed durability operations as errors; it must not silently reset to an empty store.

## 15. Backup and recovery strategy

- Before each successful replacement, retain a validated copy of the prior revision using a rotation policy; backup creation must not expose a partially written file.
- Store backups outside web roots with the same or stricter permissions. Encrypt production backups at rest using deployment-managed facilities and restrict/record restore access.
- Name backups with canonical UTC timestamps and document revision/checksum; user-facing restore tools may display the timestamp in Jalali without changing the filename/metadata.
- Define retention by count and age, plus secure deletion requirements. Audit retention is a product/compliance decision.
- Recovery is operator initiated: stop or quiesce writers, lock, verify checksum/JSON/schema/references, copy the selected backup to a same-directory temporary file, atomically replace, fsync, restart, and run health/auth checks.
- Test restores regularly. A backup is not considered valid until a restore drill succeeds.

## 16. Excel alternative analysis

| Concern | JSON canonical storage | Excel canonical storage |
| --- | --- | --- |
| Runtime reads/writes | Native typed serialization and straightforward full-document validation | Workbook parsing is slower and type coercion is less predictable |
| Safe replacement | Simple same-directory temporary file plus atomic replace | Workbook writes are more complex and vulnerable to corruption/manual locks |
| Concurrency | One clear document lock/revision protocol | Concurrent/manual edits are fragile and difficult to reconcile |
| Review/testing | Deterministic fixtures, diffs, schema validation, version field | Human-readable grid, but weak schema and noisy binary diffs |
| Authentication data | Can be permission-restricted and never exposed to spreadsheet tooling | Easy to copy, email, or accidentally reveal/modify credential cells |

JSON is therefore the canonical runtime format. Excel may later be implemented only as a sanitized export, validated administrative import, inspection artifact, or backup/reporting format. Password hashes must be excluded from ordinary exports. Excel import must never become a concurrent writable source of truth and must pass through the same validation, authorization, locking, audit, and atomic-write service.

## 17. File-by-file implementation plan

No item below is implemented in Phase 2.

| Future file | Intended change |
| --- | --- |
| `app.py` | Load validated `APP_DATA_FILE` configuration and secure deployment configuration; replace display-only session derivation with a sanitized current-user context. |
| `utils/paths.py` or a dedicated config module | Resolve the configurable instance/external application-data path without a production absolute hard-code. |
| New `utils/app_data_store.py` | Own schema validation, locking, atomic replacement, revisions, backups, and sanitized repository methods. No route may read/write the JSON directly. |
| `utils/auth.py` | Replace pandas runtime lookup with repository lookup, Werkzeug verification/rehash, active/first-login checks, and stable current-user loading. Remove/retire `accounter()`. |
| `modules/auth/routes.py` | Store only stable user/session metadata after verified login, record `last_login_at`, enforce password-change state, and keep messages Persian/RTL. |
| `modules/profile/routes.py` | Supply sanitized profile data and add server-authenticated, server-authorized, validated APIs in the appropriate later phase. Ignore client actor fields. |
| `templates/profile/profile.html` | Remove demo authority and consume sanitized server payloads; preserve Persian RTL and canonical internal identifiers. Never receive `password_hash`. |
| New migration command/script | Perform explicit validated one-time XLSX-to-JSON migration with dry-run/reporting that contains no secrets. |
| New schema/example files | Provide a safe empty/example version-1 document with no production users or hashes. |
| `.gitignore` | Exclude live instance data, lock, temp, and backup files. |
| `tests/` | Add isolated temporary-file tests for migration, validation, hashing upgrades, auth/session/current-user behavior, authorization, locking/conflicts, atomic failure recovery, backups, and secret non-disclosure. |
| `docs/profile-module-implementation-plan.md` | Track phase boundaries, approved decisions, tests, rollout, and rollback. |

Existing costing modules, `utils.cost_determiners.py`, BOM/material files, and factory cost files are explicitly outside this plan.

## 18. Open product decisions

1. Is login retained as username-based, changed to normalized email, or allowed by either unique identifier?
2. What are the approved stable role keys, hierarchy, module/action matrix, and meanings of `Write` versus `Modify`?
3. Which roles require a factory, and can a user belong to more than one factory? The proposed version-1 schema assumes at most one.
4. Which existing `access_level` values map to which roles? Unknown values must not be guessed.
5. Who supplies missing full names and unique email addresses for migrated users?
6. Must every legacy user reset at first login, or may a successful legacy check transparently upgrade the hash before a time-bounded mandatory reset?
7. What password policy, reset-delivery mechanism, rate limits, session lifetime, and forced-session-revocation rules are required?
8. Is one factory administrator per factory a real invariant or only demo-template behavior?
9. Are permission overrides allow-only, deny-only, or both, and which roles may delegate them?
10. Which actions and failed outcomes require audit events, who may view them, and what are retention/redaction requirements?
11. What backup retention, encryption, recovery-point objective, and recovery-time objective are required?
12. Is deployment guaranteed to be a single host/filesystem with reliable advisory locks? If not, this single-file architecture needs operational constraints rather than pretending to provide distributed transactions.
13. Should the checked-in legacy credential artifacts be removed from version control after secure migration and history review?

## Phase 2 conclusion and risks

The real login store and flow are now identified, and `APP_DATA_FILE` pointing to one `app_data.json` is selected for the future identity/profile domain. Major remaining risks are the weak legacy hashes, committed credential artifacts, a hard-coded Flask secret key, lack of CSRF/rate limiting, session checks that do not reload active users, client-only demo authorization, no current locking/atomic writes, unresolved role semantics, and the operational limits of one-file concurrency. These are findings and future work only. Phase 3 or any later implementation phase has not been started.
