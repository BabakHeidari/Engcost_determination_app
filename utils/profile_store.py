"""Validated, locked and atomic access to the profile JSON document.

This module deliberately has no Flask dependency.  Routes must consume the
domain methods here rather than opening the canonical file themselves.
"""

from __future__ import annotations

import copy
import errno
import json
import os
import re
import tempfile
import time
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from utils.profile_authorization import (
    SYSTEM_ROLES,
    TOP_LEVEL_ROLES,
    USER,
    canonicalize_access_grants,
    is_top_level_admin,
    would_leave_active_admin,
)


if os.name == "nt":
    import msvcrt
else:
    import fcntl


SUPPORTED_SCHEMA_VERSION = 2
REQUIRED_COLLECTIONS = (
    "users",
    "factories",
    "role_permissions",
    "user_permission_overrides",
    "audit_events",
)
ROOT_FIELDS = {"schema_version", "metadata", *REQUIRED_COLLECTIONS}
PLAINTEXT_PASSWORD_FIELDS = {"password", "plain_password", "plaintext_password"}


def _prepare_lock_file(descriptor: int) -> None:
    """Ensure Windows has a byte range available for ``msvcrt.locking``."""
    if os.name == "nt" and os.fstat(descriptor).st_size == 0:
        os.write(descriptor, b"\0")
        os.fsync(descriptor)


def _acquire_file_lock(descriptor: int, exclusive: bool) -> None:
    if os.name == "nt":
        # msvcrt has no shared lock, so Windows serializes readers and writers.
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
    else:
        operation = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        fcntl.flock(descriptor, operation | fcntl.LOCK_NB)


def _release_file_lock(descriptor: int) -> None:
    if os.name == "nt":
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(descriptor, fcntl.LOCK_UN)


def _sync_parent_directory(path: Path) -> None:
    """Persist directory metadata where opening directories is supported."""
    if os.name == "nt":
        # Windows rejects os.open() on directories. The candidate file itself
        # has already been flushed and os.replace() is atomic on local NTFS.
        return
    directory_fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


class ProfileStoreError(Exception):
    """Base application-level storage error."""


class ProfileStoreNotInitializedError(ProfileStoreError):
    """The configured canonical store has not been created yet."""


class ProfileDataValidationError(ProfileStoreError):
    """The canonical document is unsafe or incompatible."""


class ProfileDataConflictError(ProfileStoreError):
    """A unique key or expected revision conflicts with current data."""


class ProfileStoreLockError(ProfileStoreError):
    """The inter-process lock could not be acquired in time."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def normalize_email(value: str) -> str:
    if not isinstance(value, str):
        raise ProfileDataValidationError("User email must be a string")
    return unicodedata.normalize("NFKC", value).strip().casefold()


def normalize_username(value: str) -> str:
    if not isinstance(value, str):
        raise ProfileDataValidationError("Username must be a string")
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    # Usernames are token identifiers in this application, not display names.
    # Ignore accidental whitespace so a legacy value such as "Mohsen 1224"
    # remains reachable with the intended login identifier "Mohsen1224".
    return "".join(normalized.split())


def normalize_factory_name(value: str) -> str:
    if not isinstance(value, str):
        raise ProfileDataValidationError("Factory name must be a string")
    return " ".join(unicodedata.normalize("NFKC", value).strip().casefold().split())


def _required_string(record: dict, field: str, label: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ProfileDataValidationError(f"{label} {field} must be a non-empty string")
    return value


def _reject_plaintext_passwords(value, path="root") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.casefold() in PLAINTEXT_PASSWORD_FIELDS:
                raise ProfileDataValidationError(f"Plaintext password field is forbidden at {path}.{key}")
            _reject_plaintext_passwords(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_plaintext_passwords(child, f"{path}[{index}]")


def validate_data(data: dict) -> dict:
    """Validate a complete schema-v2 document, raising a clear domain error."""
    if not isinstance(data, dict):
        raise ProfileDataValidationError("Profile data root must be an object")
    if data.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        raise ProfileDataValidationError("Unsupported profile data schema_version")
    unknown_fields = set(data) - ROOT_FIELDS
    if unknown_fields:
        raise ProfileDataValidationError(f"Unknown profile data fields: {sorted(unknown_fields)}")
    if not isinstance(data.get("metadata"), dict):
        raise ProfileDataValidationError("Profile data metadata must be an object")
    revision = data["metadata"].get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise ProfileDataValidationError("metadata.revision must be a positive integer")
    for name in REQUIRED_COLLECTIONS:
        expected = dict if name == "role_permissions" else list
        if name not in data or not isinstance(data[name], expected):
            raise ProfileDataValidationError(f"Required collection {name} has an invalid type")
    _reject_plaintext_passwords(data)

    if data["role_permissions"] or data["user_permission_overrides"]:
        raise ProfileDataValidationError("Legacy role permissions and overrides must be empty")

    factory_ids, factory_codes, factory_names = set(), set(), set()
    for factory in data["factories"]:
        if not isinstance(factory, dict):
            raise ProfileDataValidationError("Factory records must be objects")
        factory_id = _required_string(factory, "id", "Factory")
        code = _required_string(factory, "code", "Factory").strip().casefold()
        _required_string(factory, "name", "Factory")
        display_name = factory.get("display_name") or factory["name"]
        name = normalize_factory_name(display_name)
        if factory_id in factory_ids:
            raise ProfileDataValidationError(f"Duplicate factory id: {factory_id}")
        if code in factory_codes:
            raise ProfileDataValidationError(f"Duplicate normalized factory code: {factory.get('code')}")
        if name in factory_names:
            raise ProfileDataValidationError(f"Duplicate normalized factory name: {factory.get('name')}")
        factory_ids.add(factory_id)
        factory_codes.add(code)
        factory_names.add(name)

    user_ids, user_emails, usernames = set(), set(), set()
    for user in data["users"]:
        if not isinstance(user, dict):
            raise ProfileDataValidationError("User records must be objects")
        user_id = _required_string(user, "id", "User")
        email = normalize_email(user.get("email"))
        username = normalize_username(user.get("username", user.get("email")))
        if not email:
            raise ProfileDataValidationError(f"User {user_id} email must not be empty")
        if user_id in user_ids:
            raise ProfileDataValidationError(f"Duplicate user id: {user_id}")
        if email in user_emails:
            raise ProfileDataValidationError(f"Duplicate normalized user email: {email}")
        if not username or username in usernames:
            raise ProfileDataValidationError(f"Duplicate or empty normalized username: {username}")
        if user.get("system_role") not in SYSTEM_ROLES:
            raise ProfileDataValidationError(f"User {user_id} has an unrecognized system_role")
        if user.get("email_normalized") != email:
            raise ProfileDataValidationError(f"User {user_id} has an invalid email_normalized")
        job_title = user.get("job_title", "")
        if not isinstance(job_title, str) or len(job_title) > 160:
            raise ProfileDataValidationError(f"User {user_id} has an invalid job_title")
        try:
            canonical_grants = canonicalize_access_grants(user.get("access_grants", []), factory_ids)
        except ValueError as exc:
            raise ProfileDataValidationError(f"User {user_id}: {exc}") from None
        if is_top_level_admin(user) and canonical_grants:
            raise ProfileDataValidationError(f"Top-level user {user_id} must not store grants")
        if canonical_grants != user.get("access_grants"):
            raise ProfileDataValidationError(f"User {user_id} access_grants are not canonical")
        password_hash = user.get("password_hash")
        if password_hash is not None and not isinstance(password_hash, str):
            raise ProfileDataValidationError(f"User {user_id} password_hash must be a string")
        user_ids.add(user_id)
        user_emails.add(email)
        usernames.add(username)

    audit_ids = set()
    for event in data["audit_events"]:
        if not isinstance(event, dict):
            raise ProfileDataValidationError("Audit events must be objects")
        event_id = _required_string(event, "id", "Audit event")
        if event_id in audit_ids:
            raise ProfileDataValidationError(f"Duplicate audit event id: {event_id}")
        if event.get("factory_id") is not None and event["factory_id"] not in factory_ids:
            raise ProfileDataValidationError(f"Audit event {event_id} references an unknown factory")
        if "password_hash" in json.dumps(event, ensure_ascii=False).casefold():
            raise ProfileDataValidationError(f"Audit event {event_id} contains forbidden secret material")
        audit_ids.add(event_id)
    return data


def public_user(user: dict) -> dict:
    """Return a detached user representation that can safely cross a UI/API boundary."""
    def redact(value):
        if isinstance(value, dict):
            return {
                key: redact(child)
                for key, child in value.items()
                if key.casefold() not in PLAINTEXT_PASSWORD_FIELDS | {"password_hash"}
            }
        if isinstance(value, list):
            return [redact(child) for child in value]
        return copy.deepcopy(value)
    return redact(user)


class ProfileDataStore:
    def __init__(self, path, backup_limit=5, lock_timeout=10.0):
        self.path = Path(path).expanduser().resolve()
        self.lock_path = self.path.with_name(self.path.name + ".lock")
        self.backup_dir = self.path.parent / "backups"
        self.backup_limit = max(0, int(backup_limit))
        self.lock_timeout = float(lock_timeout)

    @classmethod
    def from_environment(cls, instance_path, environ=None):
        environ = os.environ if environ is None else environ
        configured = environ.get("APP_DATA_FILE")
        path = Path(configured) if configured else Path(instance_path) / "app_data.json"
        if configured and not path.is_absolute():
            path = Path(instance_path) / path
        return cls(
            path,
            backup_limit=int(environ.get("APP_DATA_BACKUP_LIMIT", "5")),
            lock_timeout=float(environ.get("APP_DATA_LOCK_TIMEOUT", "10")),
        )

    def _lock(self, exclusive):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        _prepare_lock_file(descriptor)
        deadline = time.monotonic() + self.lock_timeout
        while True:
            try:
                _acquire_file_lock(descriptor, exclusive)
                return descriptor
            except OSError as exc:
                is_contention = exc.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK)
                is_contention = is_contention or getattr(exc, "winerror", None) in (33, 36)
                if not is_contention:
                    os.close(descriptor)
                    raise ProfileStoreLockError("Unable to acquire profile data lock") from exc
                if time.monotonic() >= deadline:
                    os.close(descriptor)
                    raise ProfileStoreLockError("Timed out acquiring profile data lock") from exc
                time.sleep(0.02)

    @staticmethod
    def _unlock(descriptor):
        try:
            _release_file_lock(descriptor)
        finally:
            os.close(descriptor)

    def _load_raw_unlocked(self):
        try:
            with self.path.open("r", encoding="utf-8") as stream:
                return json.load(stream)
        except FileNotFoundError as exc:
            raise ProfileStoreNotInitializedError(
                f"Profile data is not initialized: {self.path}. Run the explicit bootstrap process."
            ) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise ProfileStoreError(f"Unable to read valid profile data from {self.path}") from exc

    def _load_unlocked(self):
        return validate_data(self._load_raw_unlocked())

    def ensure_current_schema(self):
        """Upgrade the prior canonical schema before any runtime operation.

        Phase 6 installations already have a schema-v1 file. Requiring an
        operator to migrate it before the first request makes valid credentials
        appear broken, so the same locked, backed-up migration is performed
        automatically. Unknown versions still fail closed.
        """
        descriptor = self._lock(False)
        try:
            data = self._load_raw_unlocked()
            version = data.get("schema_version") if isinstance(data, dict) else None
            if version == SUPPORTED_SCHEMA_VERSION:
                validate_data(data)
                return {"migrated": False, "review_user_ids": []}
            if version != 1:
                validate_data(data)
        finally:
            self._unlock(descriptor)
        # migrate_access_model obtains an exclusive lock and checks the version
        # again, making concurrent first requests safe and idempotent.
        return self.migrate_access_model()

    def load_data(self):
        self.ensure_current_schema()
        descriptor = self._lock(False)
        try:
            return copy.deepcopy(self._load_unlocked())
        finally:
            self._unlock(descriptor)

    def initialize(self, role_permissions=None):
        """Explicitly create an empty store.  No default user or password is created."""
        descriptor = self._lock(True)
        try:
            if self.path.exists():
                raise ProfileDataConflictError("Profile data is already initialized")
            now = _utc_now()
            data = {
                "schema_version": SUPPORTED_SCHEMA_VERSION,
                "metadata": {"created_at": now, "updated_at": now, "revision": 1},
                "users": [],
                "factories": [],
                # Retained as empty compatibility containers in schema v2. They
                # are never consulted as authorization authorities.
                "role_permissions": {},
                "user_permission_overrides": [],
                "audit_events": [],
            }
            validate_data(data)
            self._atomic_write(data, create_backup=False)
            return copy.deepcopy(data)
        finally:
            self._unlock(descriptor)

    def migrate_access_model(self):
        """Migrate a schema-v1 role document to v2 under the normal write lock.

        Ambiguous ordinary-role permissions are intentionally not translated;
        affected IDs are recorded for administrator review rather than over-granted.
        """
        descriptor = self._lock(True)
        try:
            data = self._load_raw_unlocked()
            if data.get("schema_version") == SUPPORTED_SCHEMA_VERSION:
                validate_data(data)
                return {"migrated": False, "review_user_ids": []}
            if data.get("schema_version") != 1 or not isinstance(data.get("users"), list):
                raise ProfileDataValidationError("Only a valid schema-v1 document can be migrated")
            review_ids = []
            role_mapping = {
                "IT Admin": "IT_ADMIN", "IT_ADMIN": "IT_ADMIN",
                "Official Admin": "FINANCE_ECONOMIC_ADMIN",
                "FINANCE_ECONOMIC_ADMIN": "FINANCE_ECONOMIC_ADMIN",
            }
            for user in data["users"]:
                legacy_role = user.pop("role", user.get("system_role"))
                system_role = role_mapping.get(legacy_role, USER)
                if system_role == USER and legacy_role not in ("USER", "user"):
                    review_ids.append(user.get("id"))
                user["system_role"] = system_role
                user["email"] = normalize_email(user.get("email"))
                user["email_normalized"] = user["email"]
                user.setdefault("job_title", "")
                # Old role scope/override intent cannot safely express the new
                # per-factory/per-module grant pairs, so ordinary users fail closed.
                user["access_grants"] = []
                user.pop("factory_id", None)
                user.setdefault("updated_by_id", user.get("created_by_id"))
            data["schema_version"] = SUPPORTED_SCHEMA_VERSION
            data["role_permissions"] = {}
            data["user_permission_overrides"] = []
            data.setdefault("metadata", {})["access_model_migration"] = {
                "completed_at": _utc_now(),
                "review_user_ids": [value for value in review_ids if isinstance(value, str)],
            }
            data["metadata"]["revision"] = max(1, data["metadata"].get("revision", 1)) + 1
            data["metadata"]["updated_at"] = _utc_now()
            validate_data(data)
            # _atomic_write creates and fsyncs a backup before replacement.
            self._atomic_write(data, create_backup=True)
            return {"migrated": True, "review_user_ids": review_ids}
        finally:
            self._unlock(descriptor)

    def _backup_current(self, revision):
        if not self.backup_limit or not self.path.exists():
            return
        self.backup_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        backup = self.backup_dir / f"{self.path.stem}.{stamp}.r{revision}.json"
        with self.path.open("rb") as source, backup.open("xb") as destination:
            os.chmod(backup, 0o600)
            while chunk := source.read(1024 * 1024):
                destination.write(chunk)
            destination.flush()
            os.fsync(destination.fileno())
        backups = sorted(self.backup_dir.glob(f"{self.path.stem}.*.json"))
        for expired in backups[:-self.backup_limit]:
            expired.unlink()

    def _atomic_write(self, data, create_backup=True):
        validate_data(data)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        try:
            os.chmod(temporary_name, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            with open(temporary_name, "r", encoding="utf-8") as stream:
                validate_data(json.load(stream))
            if create_backup:
                self._backup_current(data["metadata"]["revision"] - 1)
            os.replace(temporary_name, self.path)
            _sync_parent_directory(self.path.parent)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

    def _mutate(self, callback: Callable[[dict], object]):
        self.ensure_current_schema()
        descriptor = self._lock(True)
        try:
            data = self._load_unlocked()
            result = callback(data)
            data["metadata"]["revision"] += 1
            data["metadata"]["updated_at"] = _utc_now()
            validate_data(data)
            self._atomic_write(data)
            return copy.deepcopy(result)
        finally:
            self._unlock(descriptor)

    def get_user_by_id(self, user_id, include_secret=False):
        user = next((item for item in self.load_data()["users"] if item["id"] == user_id), None)
        return copy.deepcopy(user) if include_secret or user is None else public_user(user)

    def get_user_by_email(self, email, include_secret=False):
        normalized = normalize_email(email)
        user = next((u for u in self.load_data()["users"] if normalize_email(u["email"]) == normalized), None)
        return copy.deepcopy(user) if include_secret or user is None else public_user(user)

    def get_user_by_identifier(self, identifier, include_secret=False):
        normalized = normalize_username(identifier)
        user = next(
            (
                item
                for item in self.load_data()["users"]
                if normalize_username(item.get("username", item["email"])) == normalized
                or normalize_email(item["email"]) == normalized
            ),
            None,
        )
        return copy.deepcopy(user) if include_secret or user is None else public_user(user)

    def authenticate_user(self, identifier, password, verifier):
        """Verify a credential and record last login in one locked mutation."""
        normalized = normalize_username(identifier)

        def change(data):
            user = next(
                (
                    item
                    for item in data["users"]
                    if normalize_username(item.get("username", item["email"])) == normalized
                    or normalize_email(item["email"]) == normalized
                ),
                None,
            )
            if user is None or not user.get("is_active", False) or not verifier(user, password):
                return None, False
            user["last_login_at"] = _utc_now()
            user["revision"] = user.get("revision", 1) + 1
            return public_user(user), True

        return self._mutate_conditionally(change)

    def _mutate_conditionally(self, callback):
        self.ensure_current_schema()
        descriptor = self._lock(True)
        try:
            data = self._load_unlocked()
            result, changed = callback(data)
            if changed:
                data["metadata"]["revision"] += 1
                data["metadata"]["updated_at"] = _utc_now()
                validate_data(data)
                self._atomic_write(data)
            return copy.deepcopy(result)
        finally:
            self._unlock(descriptor)

    def change_password(self, user_id, new_hash):
        if not isinstance(new_hash, str) or not new_hash:
            raise ProfileDataValidationError("A generated password hash is required")
        def change(data):
            user = next((u for u in data["users"] if u["id"] == user_id), None)
            if user is None or not user.get("is_active", False):
                raise ProfileStoreError("User not found")
            now = _utc_now()
            user.update({
                "password_hash": new_hash,
                "password_scheme": "werkzeug",
                "must_change_password": False,
                "password_changed_at": now,
                "updated_at": now,
                "revision": user.get("revision", 1) + 1,
            })
            data["audit_events"].append({
                "id": f"aud_{uuid.uuid4().hex}",
                "occurred_at": now,
                "actor_user_id": user_id,
                "action": "user.password_changed",
                "target_type": "user",
                "target_id": user_id,
            })
            return public_user(user), True
        return self._mutate_conditionally(change)

    def list_users(self):
        return [public_user(user) for user in self.load_data()["users"]]

    def create_user(self, values):
        candidate = copy.deepcopy(values)
        def change(data):
            candidate.setdefault("id", f"usr_{uuid.uuid4().hex}")
            candidate["email"] = normalize_email(candidate.get("email"))
            candidate["email_normalized"] = candidate["email"]
            candidate.setdefault("revision", 1)
            candidate.setdefault("system_role", USER)
            candidate.setdefault("job_title", "")
            candidate["access_grants"] = canonicalize_access_grants(
                candidate.get("access_grants", []), {f["id"] for f in data["factories"]}
            )
            if is_top_level_admin(candidate):
                candidate["access_grants"] = []
            if any(u["id"] == candidate["id"] for u in data["users"]):
                raise ProfileDataConflictError("User id already exists")
            if any(normalize_email(u["email"]) == candidate["email"] for u in data["users"]):
                raise ProfileDataConflictError("User email already exists")
            data["users"].append(candidate)
            return public_user(candidate)
        return self._mutate(change)

    def create_user_as_actor(self, actor_user_id, values):
        """Create a user and audit it in one authorization-aware transaction."""
        candidate = copy.deepcopy(values)

        def change(data):
            actor = next((u for u in data["users"] if u["id"] == actor_user_id), None)
            if actor is None or not actor.get("is_active", False):
                raise ProfileDataValidationError("کاربر ایجادکننده معتبر نیست.")
            if not is_top_level_admin(actor):
                raise ProfileDataValidationError("فقط مدیر سطح بالا مجاز به ایجاد کاربر است.")
            target_role = candidate.get("system_role")
            if target_role not in SYSTEM_ROLES:
                raise ProfileDataValidationError("نقش سامانه نامعتبر است.")
            active_factory_ids = {f["id"] for f in data["factories"] if f.get("is_active", True)}
            try:
                grants = canonicalize_access_grants(candidate.get("access_grants", []), active_factory_ids)
            except ValueError as exc:
                raise ProfileDataValidationError(str(exc)) from None
            if target_role in TOP_LEVEL_ROLES:
                grants = []
            email = normalize_email(candidate.get("email"))
            if any(normalize_email(u["email"]) == email for u in data["users"]):
                raise ProfileDataConflictError("ایمیل قبلاً ثبت شده است.")
            now = _utc_now()
            new_user = {
                "id": f"usr_{uuid.uuid4().hex}", "username": email, "email": email,
                "email_normalized": email, "full_name": candidate["full_name"],
                "system_role": target_role, "job_title": candidate.get("job_title", ""),
                "access_grants": grants,
                "is_active": True, "must_change_password": True,
                "password_hash": candidate["password_hash"], "password_scheme": "werkzeug",
                "created_at": now, "updated_at": now, "created_by_id": actor_user_id,
                "updated_by_id": actor_user_id,
                "last_login_at": None, "password_changed_at": None, "revision": 1,
            }
            data["users"].append(new_user)
            data["audit_events"].append({
                "id": f"aud_{uuid.uuid4().hex}", "occurred_at": now,
                "actor_user_id": actor_user_id, "action": "user.created",
                "target_type": "user", "target_id": new_user["id"],
                "details": {"system_role": target_role},
            })
            return public_user(new_user)

        return self._mutate(change)

    def update_user(self, user_id, changes, expected_revision=None):
        updates = copy.deepcopy(changes)
        for immutable in ("id",):
            updates.pop(immutable, None)
        if any(key.casefold() in PLAINTEXT_PASSWORD_FIELDS for key in updates):
            raise ProfileDataValidationError("Plaintext passwords are forbidden")
        def change(data):
            user = next((u for u in data["users"] if u["id"] == user_id), None)
            if user is None:
                raise ProfileStoreError("User not found")
            if expected_revision is not None and user.get("revision", 1) != expected_revision:
                raise ProfileDataConflictError("User revision conflict")
            if "email" in updates:
                updates["email"] = normalize_email(updates["email"])
                if any(u["id"] != user_id and normalize_email(u["email"]) == updates["email"] for u in data["users"]):
                    raise ProfileDataConflictError("User email already exists")
            user.update(updates)
            user["revision"] = user.get("revision", 1) + 1
            user["updated_at"] = _utc_now()
            return public_user(user)
        return self._mutate(change)

    def update_user_as_actor(self, actor_user_id, user_id, changes, expected_revision):
        """Authorize, validate, edit and audit an account in one transaction."""
        updates = copy.deepcopy(changes)

        def change(data):
            actor = next((u for u in data["users"] if u["id"] == actor_user_id), None)
            target = next((u for u in data["users"] if u["id"] == user_id), None)
            if actor is None or not actor.get("is_active") or not is_top_level_admin(actor):
                raise ProfileDataValidationError("فقط مدیر سطح بالا مجاز به ویرایش کاربران است.")
            if target is None:
                raise ProfileStoreError("User not found")
            if target.get("revision", 1) != expected_revision:
                raise ProfileDataConflictError("اطلاعات کاربر تغییر کرده است؛ صفحه را تازه‌سازی کنید.")
            sensitive = {"system_role", "is_active", "email"} & set(updates)
            if actor_user_id == user_id and sensitive:
                raise ProfileDataValidationError("تغییر حساس حساب مدیر باید توسط مدیر سطح بالای دیگری انجام شود.")
            if is_top_level_admin(target) and sensitive and actor_user_id == user_id:
                raise ProfileDataValidationError("مدیر نمی‌تواند تغییر حساس را روی حساب خود انجام دهد.")
            new_role = updates.get("system_role", target["system_role"])
            new_active = updates.get("is_active", target.get("is_active", False))
            if would_leave_active_admin(data, user_id, new_role, new_active):
                raise ProfileDataValidationError("سامانه باید حداقل یک مدیر سطح بالای فعال داشته باشد.")
            email = normalize_email(updates.get("email", target["email"]))
            if any(u["id"] != user_id and normalize_email(u["email"]) == email for u in data["users"]):
                raise ProfileDataConflictError("ایمیل قبلاً ثبت شده است.")
            active_factory_ids = {f["id"] for f in data["factories"] if f.get("is_active", True)}
            all_factory_ids = {f["id"] for f in data["factories"]}
            raw_grants = updates.get("access_grants", target.get("access_grants", []))
            # Existing inactive-factory grants remain valid historical records;
            # a submitted replacement may only assign currently active factories.
            permitted_factory_ids = active_factory_ids if "access_grants" in updates else all_factory_ids
            try:
                grants = canonicalize_access_grants(raw_grants, permitted_factory_ids)
            except ValueError as exc:
                raise ProfileDataValidationError(str(exc)) from None
            if new_role in TOP_LEVEL_ROLES:
                grants = []
            now = _utc_now()
            before = {"system_role": target["system_role"], "is_active": target.get("is_active", False)}
            target.update(updates)
            target.update({"email": email, "email_normalized": email,
                           "system_role": new_role, "access_grants": grants,
                           "updated_at": now, "updated_by_id": actor_user_id,
                           "revision": target.get("revision", 1) + 1})
            if "email" in updates:
                target["username"] = email
            changed_fields = sorted(key for key in updates if key != "access_grants")
            if grants != raw_grants or "access_grants" in updates:
                changed_fields.append("access_grants")
            details = {"changed_fields": sorted(set(changed_fields))}
            if "system_role" in updates:
                details["system_role"] = {"before": before["system_role"], "after": new_role}
            if "is_active" in updates:
                details["is_active"] = {"before": before["is_active"], "after": new_active}
            data["audit_events"].append({"id": f"aud_{uuid.uuid4().hex}", "occurred_at": now,
                "actor_user_id": actor_user_id, "action": "user.updated", "target_type": "user",
                "target_id": user_id, "details": details})
            return public_user(target)
        return self._mutate(change)

    def reset_password_as_actor(self, actor_user_id, user_id, password_hash, expected_revision):
        """Reset a target password without exposing or auditing secret material."""
        if not isinstance(password_hash, str) or not password_hash:
            raise ProfileDataValidationError("هش گذرواژه معتبر نیست.")
        def change(data):
            actor = next((u for u in data["users"] if u["id"] == actor_user_id), None)
            target = next((u for u in data["users"] if u["id"] == user_id), None)
            if actor is None or not actor.get("is_active") or not is_top_level_admin(actor):
                raise ProfileDataValidationError("فقط مدیر سطح بالا مجاز به بازنشانی گذرواژه است.")
            if target is None:
                raise ProfileStoreError("User not found")
            if target.get("revision", 1) != expected_revision:
                raise ProfileDataConflictError("اطلاعات کاربر تغییر کرده است؛ صفحه را تازه‌سازی کنید.")
            if is_top_level_admin(target) and actor_user_id == user_id:
                raise ProfileDataValidationError("گذرواژه مدیر سطح بالا باید توسط مدیر سطح بالای دیگری بازنشانی شود.")
            now = _utc_now()
            target.update({"password_hash": password_hash, "password_scheme": "werkzeug",
                "must_change_password": True, "password_changed_at": now, "updated_at": now,
                "updated_by_id": actor_user_id, "revision": target.get("revision", 1) + 1})
            data["audit_events"].append({"id": f"aud_{uuid.uuid4().hex}", "occurred_at": now,
                "actor_user_id": actor_user_id, "action": "user.password_reset",
                "target_type": "user", "target_id": user_id,
                "details": {"must_change_password": True}})
            return public_user(target)
        return self._mutate(change)

    def list_factories(self):
        return copy.deepcopy(self.load_data()["factories"])

    def list_active_factories(self):
        """Return only public fields for factories assignable to new grants."""
        return [
            {key: copy.deepcopy(factory.get(key)) for key in ("id", "code", "name", "display_name", "location")}
            for factory in self.load_data()["factories"] if factory.get("is_active", True)
        ]

    def merge_factories(self, candidates):
        """Add new discovered factories without overwriting canonical records."""
        if not isinstance(candidates, list):
            raise ProfileDataValidationError("Factory candidates must be a list")
        proposed = copy.deepcopy(candidates)

        def change(data):
            existing_ids = {factory["id"] for factory in data["factories"]}
            existing_codes = {factory["code"].strip().casefold() for factory in data["factories"]}
            created = []
            for candidate in proposed:
                if not isinstance(candidate, dict):
                    raise ProfileDataValidationError("Factory candidate must be an object")
                factory_id = _required_string(candidate, "id", "Factory")
                code = _required_string(candidate, "code", "Factory").strip()
                _required_string(candidate, "name", "Factory")
                if factory_id in existing_ids or code.casefold() in existing_codes:
                    continue
                candidate["code"] = code
                candidate.setdefault("is_active", True)
                candidate.setdefault("location", None)
                candidate.setdefault("revision", 1)
                data["factories"].append(candidate)
                existing_ids.add(factory_id)
                existing_codes.add(code.casefold())
                created.append(copy.deepcopy(candidate))
            return {"created": created, "created_count": len(created)}, bool(created)

        return self._mutate_conditionally(change)

    def create_factory(self, values):
        candidate = copy.deepcopy(values)
        def change(data):
            candidate.setdefault("id", f"fac_{uuid.uuid4().hex}")
            candidate["code"] = _required_string(candidate, "code", "Factory").strip().upper()
            candidate.setdefault("revision", 1)
            if any(f["id"] == candidate["id"] for f in data["factories"]):
                raise ProfileDataConflictError("Factory id already exists")
            if any(f["code"].strip().casefold() == candidate["code"].casefold() for f in data["factories"]):
                raise ProfileDataConflictError("Factory code already exists")
            data["factories"].append(candidate)
            return copy.deepcopy(candidate)
        return self._mutate(change)

    def create_factory_as_actor(self, actor_user_id, values):
        """Create and audit a factory under one authorized atomic mutation."""
        candidate = copy.deepcopy(values)

        def change(data):
            actor = next((u for u in data["users"] if u["id"] == actor_user_id), None)
            if actor is None or not actor.get("is_active", False):
                raise ProfileDataValidationError("کاربر ایجادکننده معتبر نیست.")
            if not is_top_level_admin(actor):
                raise ProfileDataValidationError("فقط مدیر سطح بالا مجاز به ایجاد کارخانه است.")

            code_value = candidate.get("code")
            if not isinstance(code_value, str) or not code_value.strip():
                raise ProfileDataValidationError("کد کارخانه الزامی است.")
            code = code_value.strip()
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", code):
                raise ProfileDataValidationError("کد کارخانه باید ۱ تا ۶۴ نویسه لاتین، عدد، خط تیره، زیرخط یا نقطه باشد.")
            name_value = candidate.get("name")
            if not isinstance(name_value, str) or not name_value.strip():
                raise ProfileDataValidationError("نام کارخانه الزامی است.")
            name = " ".join(name_value.split())
            if len(name) > 160:
                raise ProfileDataValidationError("نام کارخانه نباید بیش از ۱۶۰ نویسه باشد.")
            normalized_name = normalize_factory_name(name)
            normalized_code = code.casefold()
            if any(f["id"].casefold() == normalized_code for f in data["factories"]):
                raise ProfileDataConflictError("شناسه کارخانه قبلاً ثبت شده است.")
            if any(f["code"].strip().casefold() == normalized_code for f in data["factories"]):
                raise ProfileDataConflictError("کد کارخانه قبلاً ثبت شده است.")
            if any(normalize_factory_name(f.get("display_name") or f["name"]) == normalized_name for f in data["factories"]):
                raise ProfileDataConflictError("نام کارخانه قبلاً ثبت شده است.")

            location = candidate.get("location")
            if location is not None:
                if not isinstance(location, str):
                    raise ProfileDataValidationError("موقعیت کارخانه نامعتبر است.")
                location = " ".join(location.split()) or None
                if location and len(location) > 240:
                    raise ProfileDataValidationError("موقعیت کارخانه نباید بیش از ۲۴۰ نویسه باشد.")
            now = _utc_now()
            factory = {
                "id": code, "code": code, "name": name, "display_name": name,
                "location": location, "is_active": True,
                "created_at": now, "updated_at": now,
                "created_by_id": actor_user_id, "updated_by_id": actor_user_id,
                "revision": 1,
            }
            data["factories"].append(factory)
            data["audit_events"].append({
                "id": f"aud_{uuid.uuid4().hex}", "occurred_at": now,
                "actor_user_id": actor_user_id, "action": "FACTORY_CREATED",
                "target_type": "factory", "target_id": factory["id"],
                "factory_id": factory["id"],
                "details": {"code": code, "name": name},
            })
            return {key: copy.deepcopy(factory.get(key)) for key in ("id", "code", "name", "location", "is_active")}

        return self._mutate(change)

    def get_role_permissions(self, role):
        return copy.deepcopy(self.load_data()["role_permissions"].get(role))

    def get_user_permission_overrides(self, user_id):
        return [copy.deepcopy(item) for item in self.load_data()["user_permission_overrides"] if item["user_id"] == user_id]

    def append_audit_event(self, values):
        event = copy.deepcopy(values)
        def change(data):
            event.setdefault("id", f"aud_{uuid.uuid4().hex}")
            event.setdefault("occurred_at", _utc_now())
            _reject_plaintext_passwords(event, "audit_event")
            if "password_hash" in json.dumps(event, ensure_ascii=False).casefold():
                raise ProfileDataValidationError("Audit events must not contain password hashes")
            if any(item["id"] == event["id"] for item in data["audit_events"]):
                raise ProfileDataConflictError("Audit event id already exists")
            data["audit_events"].append(event)
            return copy.deepcopy(event)
        return self._mutate(change)
