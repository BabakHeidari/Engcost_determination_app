import subprocess
from pathlib import Path


def test_no_committed_runtime_secret_or_demo_credentials():
    source = Path("app.py").read_text(encoding="utf-8")
    assert "WILL BE CHANGED" not in source
    assert 'password == "admin"' not in source
    assert "app.run(debug=True)" not in source
    tracked = subprocess.run(
        ["git", "ls-files"], check=True, capture_output=True, text=True
    ).stdout.splitlines()
    assert "Data/Overall/auth_data.json" not in tracked
    assert "Data/Overall/auth_data.xlsx" not in tracked


def test_secret_key_can_be_supplied_by_environment():
    source = Path("app.py").read_text(encoding="utf-8")
    assert 'os.environ.get("APP_SECRET_KEY")' in source
    assert "secrets.token_hex(32)" in source


def test_session_cookie_security_defaults():
    source = Path("app.py").read_text(encoding="utf-8")
    assert "SESSION_COOKIE_HTTPONLY=True" in source
    assert 'SESSION_COOKIE_SAMESITE="Lax"' in source
