# Profile JSON data-access layer (Phase 3)

## Scope and status

Phase 3 adds the centralized `utils.profile_store.ProfileDataStore` repository. It does not connect authentication, the Profile route, the Profile template, or its JavaScript demo data to the new store. The existing Excel authentication flow is intentionally unchanged until the later migration phase.

The canonical runtime document is selected by `APP_DATA_FILE`; a relative configured path is resolved below Flask's instance directory. The development default is `instance/app_data.json`. The live file, sibling lock, temporary files, and bounded `instance/backups/` directory are ignored by Git and are outside Flask's `static/` directory. `instance/app_data.example.json` is a hash-free schema example, not a runtime credential store.

## Repository boundary

Runtime code must use the repository methods rather than opening `app_data.json`:

- `load_data`, `get_user_by_id`, `get_user_by_email`, and `list_users`;
- `create_user` and `update_user`;
- `list_factories` and `create_factory`;
- `get_role_permissions` and `get_user_permission_overrides`;
- `append_audit_event`.

User lookup/list methods return public copies with password and password-hash fields recursively removed. Only a future authentication service may deliberately request the secret-bearing record with `include_secret=True`; such a value must never cross a template, API, log, audit, or JavaScript boundary.

## Validation and failure behavior

Every read and both sides of every mutation validate schema version 1. Validation rejects non-object roots, unknown root keys, absent/wrongly typed collections, unsupported versions, invalid metadata revisions, duplicate user IDs, duplicate normalized emails, duplicate factory IDs/codes, missing factory references, unknown user roles, non-string password hashes, plaintext password fields at any depth, invalid overrides, duplicate audit IDs, and secret material in audit events.

Malformed or absent storage raises a `ProfileStoreError`/`ProfileDataValidationError`; it is never replaced with empty data automatically. Expected-revision and uniqueness failures use `ProfileDataConflictError`.

## Lock, write, backup, and recovery behavior

On Linux/macOS, reads take a shared advisory `fcntl` lock and mutations take an exclusive lock. On Windows, `msvcrt` byte-range locking safely serializes readers and writers because it has no shared-lock operation. Both adapters lock the stable sibling `.lock` file. The exclusive lock covers reload, validation, ID allocation, duplicate checks, mutation, revision increment, candidate validation, backup, and replacement. A bounded timeout prevents indefinite waiting.

Writes serialize to a uniquely named mode-`0600` temporary file in the target directory, flush and `fsync` it, parse and validate it again, then install it with `os.replace`. The containing directory is also synced where supported. A failed replacement removes the temporary candidate and leaves the prior canonical JSON intact.

Before a normal replacement, the valid prior revision is copied to the non-web `backups/` directory and synced. `APP_DATA_BACKUP_LIMIT` controls rotation (default `5`, `0` disables backups); oldest matching backups are deleted so growth is bounded. Restore is an explicit operator action: stop writers, validate the chosen backup with `validate_data`, preserve the damaged file for investigation, and atomically place the selected revision while holding the same lock protocol.

Local Linux/macOS deployments use `fcntl`; Windows deployments use `msvcrt`. Network filesystems still require deployment-specific verification of their locking and atomic-replacement semantics.

## Explicit initialization and secure administrator bootstrap

Initialization is never implicit and never creates a known administrator. An operator first chooses an approved role matrix and calls `initialize()` once. Production must set `APP_DATA_FILE` to a protected location owned by the service account. Example initialization (the shown role matrix is illustrative and must be replaced with the approved matrix):

```bash
APP_DATA_FILE=/secure/application-data/app_data.json python - <<'PY'
import os
from utils.profile_store import ProfileDataStore

store = ProfileDataStore(os.environ["APP_DATA_FILE"])
store.initialize({"IT Admin": {"scope": "global", "permissions": {}}})
print("Empty profile store initialized; no user or password was created.")
PY
```

Creating the first administrator is a separate attended bootstrap operation. Do not put the password in shell history, source, environment variables, command arguments, or logs. Read it with `getpass`, hash it with Werkzeug, and pass only the encoded hash to the store:

```bash
APP_DATA_FILE=/secure/application-data/app_data.json python - <<'PY'
import getpass
import os
from werkzeug.security import generate_password_hash
from utils.profile_store import ProfileDataStore

password = getpass.getpass("Initial administrator password: ")
confirmation = getpass.getpass("Confirm password: ")
if password != confirmation or len(password) < 12:
    raise SystemExit("Passwords must match and contain at least 12 characters")
store = ProfileDataStore(os.environ["APP_DATA_FILE"])
created = store.create_user({
    "email": input("Administrator email: ").strip(),
    "username": input("Administrator username: ").strip(),
    "full_name": input("Administrator full name: ").strip(),
    "role": "IT Admin",
    "factory_id": None,
    "is_active": True,
    "must_change_password": True,
    "password_hash": generate_password_hash(password),
})
print(f"Created administrator {created['id']}; no hash was returned.")
PY
```

Restrict the directory to `0700` and the file/lock/backups to `0600`. A later phase must add approved authorization, password policy, audit context, and authentication integration before using this bootstrap account through the web application.

## Phase boundary

No Profile UI, route, login, logout, session, current-user loading, authorization decorator, costing formula, or operational factory data was changed. User migration and runtime cutover have not started.
