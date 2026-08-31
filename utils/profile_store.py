"""Validated, locked and atomic access to the profile JSON document.

This module deliberately has no Flask dependency.  Routes must consume the
domain methods here rather than opening the canonical file themselves.
"""

from __future__ import annotations

import copy
import errno
import fcntl
import json
import os
import tempfile
import time
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


SUPPORTED_SCHEMA_VERSION = 1
REQUIRED_COLLECTIONS = (
    "users",
    "factories",
    "role_permissions",
    "user_permission_overrides",
    "audit_events",
)
ROOT_FIELDS = {"schema_version", "metadata", *REQUIRED_COLLECTIONS}
PLAINTEXT_PASSWORD_FIELDS = {"password", "plain_password", "plaintext_password"}


class ProfileStoreError(Exception):
    """Base application-level storage error."""


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
    return unicodedata.normalize("NFKC", value).strip().casefold()


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
    """Validate a complete schema-v1 document, raising a clear domain error."""
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

    roles = set(data["role_permissions"])
    for role, definition in data["role_permissions"].items():
        if not isinstance(role, str) or not role or not isinstance(definition, dict):
            raise ProfileDataValidationError("Role permission entries must be named objects")

    factory_ids, factory_codes = set(), set()
    for factory in data["factories"]:
        if not isinstance(factory, dict):
            raise ProfileDataValidationError("Factory records must be objects")
        factory_id = _required_string(factory, "id", "Factory")
        code = _required_string(factory, "code", "Factory").strip().casefold()
        if factory_id in factory_ids:
            raise ProfileDataValidationError(f"Duplicate factory id: {factory_id}")
        if code in factory_codes:
            raise ProfileDataValidationError(f"Duplicate normalized factory code: {factory.get('code')}")
        factory_ids.add(factory_id)
        factory_codes.add(code)

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
        if user.get("role") not in roles:
            raise ProfileDataValidationError(f"User {user_id} has an unrecognized role")
        factory_id = user.get("factory_id")
        if factory_id is not None and factory_id not in factory_ids:
            raise ProfileDataValidationError(f"User {user_id} references an unknown factory")
        password_hash = user.get("password_hash")
        if password_hash is not None and not isinstance(password_hash, str):
            raise ProfileDataValidationError(f"User {user_id} password_hash must be a string")
        user_ids.add(user_id)
        user_emails.add(email)
        usernames.add(username)

    override_ids = set()
    for override in data["user_permission_overrides"]:
        if not isinstance(override, dict):
            raise ProfileDataValidationError("Permission overrides must be objects")
        override_id = _required_string(override, "id", "Permission override")
        if override_id in override_ids:
            raise ProfileDataValidationError(f"Duplicate permission override id: {override_id}")
        if override.get("user_id") not in user_ids:
            raise ProfileDataValidationError(f"Override {override_id} references an unknown user")
        if override.get("factory_id") is not None and override["factory_id"] not in factory_ids:
            raise ProfileDataValidationError(f"Override {override_id} references an unknown factory")
        override_ids.add(override_id)

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
        operation = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        deadline = time.monotonic() + self.lock_timeout
        while True:
            try:
                fcntl.flock(descriptor, operation | fcntl.LOCK_NB)
                return descriptor
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN):
                    os.close(descriptor)
                    raise ProfileStoreLockError("Unable to acquire profile data lock") from exc
                if time.monotonic() >= deadline:
                    os.close(descriptor)
                    raise ProfileStoreLockError("Timed out acquiring profile data lock") from exc
                time.sleep(0.02)

    @staticmethod
    def _unlock(descriptor):
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)

    def _load_unlocked(self):
        try:
            with self.path.open("r", encoding="utf-8") as stream:
                data = json.load(stream)
        except FileNotFoundError as exc:
            raise ProfileStoreError(
                f"Profile data is not initialized: {self.path}. Run the explicit bootstrap process."
            ) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise ProfileStoreError(f"Unable to read valid profile data from {self.path}") from exc
        return validate_data(data)

    def load_data(self):
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
                "role_permissions": copy.deepcopy(role_permissions or {}),
                "user_permission_overrides": [],
                "audit_events": [],
            }
            validate_data(data)
            self._atomic_write(data, create_backup=False)
            return copy.deepcopy(data)
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
            directory_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

    def _mutate(self, callback: Callable[[dict], object]):
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

    def authenticate_user(self, identifier, password, verifier):
        """Verify a credential and record last login in one locked mutation."""
        normalized = normalize_email(identifier)

        def change(data):
            user = next((u for u in data["users"] if normalize_email(u["email"]) == normalized), None)
            if user is None or not user.get("is_active", False) or not verifier(user, password):
                return None, False
            user["last_login_at"] = _utc_now()
            user["revision"] = user.get("revision", 1) + 1
            return public_user(user), True

        return self._mutate_conditionally(change)

    def _mutate_conditionally(self, callback):
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
            candidate.setdefault("revision", 1)
            candidate.setdefault("factory_id", None)
            if any(u["id"] == candidate["id"] for u in data["users"]):
                raise ProfileDataConflictError("User id already exists")
            if any(normalize_email(u["email"]) == candidate["email"] for u in data["users"]):
                raise ProfileDataConflictError("User email already exists")
            data["users"].append(candidate)
            return public_user(candidate)
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

    def list_factories(self):
        return copy.deepcopy(self.load_data()["factories"])

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
