"""Explicit, resumable preparation. Importing this module never imports app.py."""
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile

from utils.profile_store import ProfileDataStore, validate_data
from utils.runtime_paths import RuntimePaths


def private_directory(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "nt":
        system32 = Path(os.environ["SystemRoot"]) / "System32"
        output = subprocess.check_output(
            [str(system32 / "whoami.exe"), "/user", "/fo", "csv", "/nh"],
            text=True, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        sid = next(csv.reader([output.strip()]))[1]
        if not sid.startswith("S-1-"):
            raise ValueError("Cannot establish workspace owner")
        subprocess.run([str(system32 / "icacls.exe"), str(path), "/reset"], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=subprocess.CREATE_NO_WINDOW)
        subprocess.run([str(system32 / "icacls.exe"), str(path), "/inheritance:r",
                        "/grant:r", f"*{sid}:(OI)(CI)F"], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        path.chmod(0o700)


def atomic_json(path, value):
    path = Path(path)
    descriptor, temporary = tempfile.mkstemp(prefix=".engcost-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        Path(temporary).unlink(missing_ok=True)


def user_locations():
    if os.name == "nt":
        base = Path(os.environ["LOCALAPPDATA"]) / "Engcost"
        return base / "config", base / "workspace"
    home = Path.home()
    config = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / "engcost"
    data = Path(os.environ.get("XDG_DATA_HOME", home / ".local/share")) / "engcost/workspace"
    return config, data


def checked_root(value):
    root = Path(value).expanduser()
    if not root.is_absolute():
        raise ValueError("مسیر پوشه باید کامل باشد.")
    # Resolve aliases so two launchers use the same workspace lock.
    root = root.resolve()
    resources = RuntimePaths.from_environment({}).resources
    installation = Path(os.path.dirname(os.path.abspath(os.sys.executable)))
    if root == resources or resources in root.parents or (
        getattr(os.sys, "frozen", False) and (root == installation or installation in root.parents)
    ):
        raise ValueError("پوشه داده باید بیرون از محل نصب باشد.")
    for part in (root / "Data", root / "instance", root / "runtime"):
        if part.is_symlink():
            raise ValueError("پیوند پوشه برای فضای کاری پشتیبانی نمی‌شود.")
    return root


def validate_existing(root):
    """Read-only preflight; no locks, migrations, or repairs during selection."""
    root = checked_root(root)
    profile = root / "instance/app_data.json"
    if profile.is_symlink() or not (root / "Data/Overall").is_dir() or not (root / "Data/Factories").is_dir():
        raise ValueError("فضای کاری باید پوشه‌های Data و instance معتبر داشته باشد.")
    data = validate_data(json.loads(profile.read_text(encoding="utf-8")))
    if not data["users"]:
        raise ValueError("فضای کاری موجود کاربر ندارد؛ بازیابی را طبق راهنما انجام دهید.")
    for factory in data["factories"]:
        key = factory.get("operational_key") or factory["id"]
        if not isinstance(key, str) or not key or key in {".", ".."} or any(c in key for c in '/\\<>:"|?*'):
            raise ValueError("کلید عملیاتی کارخانه معتبر نیست.")
        if not (root / "Data/Factories" / key).is_dir():
            raise ValueError("پوشه عملیاتی یکی از کارخانه‌ها وجود ندارد.")
    # Reject symlink escapes before activating any existing data.
    for tree in (root / "Data", root / "instance"):
        if any(path.is_symlink() for path in tree.rglob("*")):
            raise ValueError("فضای کاری دارای پیوند فایل است؛ انتخاب متوقف شد.")
    return data


def prepare(root, *, fresh=False):
    root = checked_root(root)
    settings_path = root / "instance/standalone.json"
    marker = root / ".engcost-setup.json"
    if fresh:
        if root.exists() and any(root.iterdir()) and not marker.is_file():
            raise ValueError("پوشه خالی نیست؛ هیچ داده‌ای بازنویسی نشد.")
        if marker.exists() and json.loads(marker.read_text()) != {"schema": 1, "mode": "fresh"}:
            raise ValueError("نشان راه‌اندازی نامعتبر است.")
        private_directory(root)
        if not marker.exists():
            atomic_json(marker, {"schema": 1, "mode": "fresh"})
        for relative in ("Data/Overall", "Data/Factories", "instance", "runtime", "logs"):
            private_directory(root / relative)
        resources = RuntimePaths.from_environment({}).resources
        for source in sorted((resources / "packaging/blank/Overall").glob("*.json")):
            target = root / "Data/Overall" / source.name
            blank = json.loads(source.read_text(encoding="utf-8"))
            if target.exists():
                # Resume an interrupted setup; never replace edited/corrupt bytes.
                if json.loads(target.read_text(encoding="utf-8")) != blank:
                    raise ValueError("قالب راه‌اندازی تغییر کرده است؛ بازیابی دستی لازم است.")
            else:
                atomic_json(target, blank)
        profile = ProfileDataStore(root / "instance/app_data.json")
        if not profile.path.exists():
            profile.initialize()
        else:
            profile.load_data()  # Corruption fails closed.
    else:
        validate_existing(root)
        private_directory(root / "instance")
        for relative in ("runtime", "logs"):
            private_directory(root / relative)
    if settings_path.exists():
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        if settings.get("schema") != 1 or not isinstance(settings.get("secret"), str) or len(settings["secret"]) < 64:
            raise ValueError("تنظیمات یا کلید نشست خراب است؛ داده موجود حفظ شد.")
    else:
        settings = {"schema": 1, "secret": secrets.token_hex(32)}
        atomic_json(settings_path, settings)
    return root, settings


def activate(root, settings):
    """Connect launcher state to import-bound helpers and Flask configuration."""
    os.environ.update(ENGCOST_STANDALONE="1", ENGCOST_WORKSPACE=str(root),
                      APP_DATA_FILE=str(root / "instance/app_data.json"),
                      APP_SECRET_KEY=settings["secret"], APP_COOKIE_SECURE="0", FLASK_DEBUG="0")
    os.environ.pop("ENG_COST_DEMO_LOCALE", None)


def first_admin(root, values):
    from utils.auth import set_password
    username = values.get("username", "").strip()
    name = values.get("full_name", "").strip()
    email = values.get("email", "").strip()
    if not username or len(username) > 160 or any(c.isspace() for c in username):
        raise ValueError("نام کاربری نباید خالی یا دارای فاصله باشد.")
    if not name or len(name) > 160 or len(email) > 254 or "@" not in email or any(c.isspace() for c in email):
        raise ValueError("نام و ایمیل معتبر وارد کنید.")
    if values.get("password") != values.get("confirmation"):
        raise ValueError("تکرار گذرواژه یکسان نیست.")
    now = datetime.now(timezone.utc).isoformat()
    candidate = {"username": username, "email": email, "full_name": name,
                 "system_role": "IT_ADMIN", "is_active": True,
                 "must_change_password": False, "created_at": now, "updated_at": now}
    set_password(candidate, values.get("password"))
    return ProfileDataStore(root / "instance/app_data.json").create_initial_admin(candidate)
