"""Interactively create the first IT administrator without persisting plaintext."""

import getpass
import os
from pathlib import Path

from utils.auth import set_password
from utils.profile_store import ProfileDataStore, ProfileStoreNotInitializedError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROLES = {
    "IT Admin": {"scope": "global", "permissions": {}},
    "Office Staff": {"scope": "global", "permissions": {}},
}


def store_path() -> Path:
    configured = os.environ.get("APP_DATA_FILE")
    if not configured:
        return PROJECT_ROOT / "instance" / "app_data.json"
    path = Path(configured)
    return path if path.is_absolute() else PROJECT_ROOT / "instance" / path


def main() -> None:
    store = ProfileDataStore(store_path())
    try:
        store.load_data()
    except ProfileStoreNotInitializedError:
        store.initialize(ROLES)

    username = input("Username [Mohsen1224]: ").strip() or "Mohsen1224"
    existing = store.get_user_by_identifier(username)
    if existing is not None:
        print(f"IT administrator already exists: {existing['username']}")
        return
    email = input("Email: ").strip()
    full_name = input("Full name: ").strip() or username
    password = getpass.getpass("Password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match; no user was created.")

    candidate = {}
    set_password(candidate, password)
    created = store.create_user({
        "username": username,
        "email": email,
        "full_name": full_name,
        "role": "IT Admin",
        "factory_id": None,
        "is_active": True,
        "must_change_password": False,
        "revision": 1,
        **candidate,
    })
    print(f"IT administrator created: {created['username']}")


if __name__ == "__main__":
    main()
