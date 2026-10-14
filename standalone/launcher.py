"""One-click, loopback-only launcher. No network/dependency/update preparation."""
import argparse
from contextlib import ExitStack
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import signal
import sys
import threading
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener
import webbrowser

from standalone.workspace import atomic_json, private_directory, user_locations
from utils.file_lock import FileLockTimeout, interprocess_file_lock


HTTP = build_opener(ProxyHandler({}))  # Local traffic must never use a proxy.


def verified(record):
    if not isinstance(record, dict) or record.get("application") != "Engcost":
        return False
    port = record.get("port")
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        return False
    token = record.get("token")
    if not isinstance(token, str) or len(token) < 40:
        return False
    try:
        req = Request(f"http://127.0.0.1:{port}/_local/health", headers={"X-Engcost-Capability": token})
        with HTTP.open(req, timeout=0.5) as response:
            result = json.load(response)
        return result.get("application") == "Engcost" and result.get("instance_id") == record.get("instance_id")
    except (OSError, ValueError, URLError):
        return False


def read_record(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def open_instance(record, *, no_browser=False):
    if not no_browser:
        webbrowser.open(f"http://127.0.0.1:{record['port']}/_local/#{record['token']}")


def request_stop(record):
    if not verified(record):
        return False
    origin = f"http://127.0.0.1:{record['port']}"
    # Use the same protected local authorization/CSRF mechanism as the UI.
    req = Request(origin + "/_local/authorize", data=json.dumps({"capability": record['token']}).encode(),
                  headers={"Content-Type": "application/json", "Origin": origin})
    with HTTP.open(req, timeout=2) as response:
        cookie = response.headers.get("Set-Cookie").split(";", 1)[0]
    from urllib.parse import urlencode
    req = Request(origin + "/_local/panel", headers={"Cookie": cookie})
    with HTTP.open(req, timeout=2) as response:
        page = response.read().decode()
    import re
    csrf = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
    req = Request(origin + "/_local/stop", data=urlencode({"csrf": csrf}).encode(),
                  headers={"Cookie": cookie, "Origin": origin})
    with HTTP.open(req, timeout=2) as response:
        response.read()
    return True


def stop_installed_processes():
    """Linux package scripts: verify executable ownership before SIGTERM.

    Run before replacing/removing code. No root-launched app or personal setup.
    Abort upgrade instead of forcing termination during an authorized write.
    """
    if sys.platform != "linux" or not getattr(sys, "frozen", False):
        raise RuntimeError("Native Linux installer operation only")
    own = Path(sys.executable).resolve()
    owned = []
    for process in Path("/proc").iterdir():
        if not process.name.isdigit() or int(process.name) == os.getpid():
            continue
        try:
            if (process / "exe").resolve(strict=True) == own:
                owned.append(process)
                os.kill(int(process.name), signal.SIGTERM)
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
    deadline = time.monotonic() + 60
    def live(process):
        try:
            return (process / 'exe').resolve(strict=True) == own
        except (OSError, RuntimeError):
            return False  # exited/zombie or a reused PID is no longer our worker

    while any(live(p) for p in owned):
        if time.monotonic() >= deadline:
            raise RuntimeError("Owned application is still draining; upgrade aborted")
        time.sleep(0.1)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", type=Path, help="Isolated native validation only")
    parser.add_argument("--workspace", type=Path, help="Preselected existing workspace for validation")
    parser.add_argument("--no-browser", action="store_true", help="Native validation only")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--installer-stop", action="store_true")
    args = parser.parse_args(argv)
    if args.installer_stop:
        stop_installed_processes()
        return 0
    config, default_workspace = user_locations()
    config = (args.config_root or config).expanduser().resolve()
    private_directory(config)
    record_path = config / "instance.json"
    if args.stop:
        record = read_record(record_path)
        if record and verified(record):
            request_stop(record)
            deadline = time.monotonic() + 60
            # Wait for the ownership lock, not just a disappearing HTTP port.
            while True:
                try:
                    with interprocess_file_lock(config / "launcher.lock", timeout=0):
                        return 0
                except FileLockTimeout:
                    if time.monotonic() >= deadline:
                        return 1
                    time.sleep(0.1)
        try:
            with interprocess_file_lock(config / "launcher.lock", timeout=0):
                return 0
        except FileLockTimeout:
            # A stale/unverifiable record with a live owner is not safe to replace.
            return 1

    if getattr(sys, 'frozen', False) and (Path(sys.executable).parent / '.engcost-upgrading').exists():
        raise RuntimeError('Installer is replacing application code')

    ownership = ExitStack()
    try:
        ownership.enter_context(interprocess_file_lock(config / "launcher.lock", timeout=0))
    except FileLockTimeout:
        # Another click may happen before the owner has bound its server.
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            record = read_record(record_path)
            if verified(record):
                open_instance(record, no_browser=args.no_browser)
                return 0
            time.sleep(0.05)
        raise RuntimeError("Existing instance did not become ready")

    handler = RotatingFileHandler(config / "launcher.log", maxBytes=512000, backupCount=2, encoding="utf-8")
    logger = logging.getLogger("engcost")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    controller = None
    server = None
    server_thread = None
    try:
        from standalone.controller import Controller
        from waitress.server import create_server
        controller = Controller(config, default_workspace, workspace=None)
        selection = read_record(config / "selection.json")
        selected = args.workspace or (selection or {}).get("workspace")
        if selected:
            controller.state = 'preparing'
        # Waitress binds once and retains its socket; no find/free/rebind race.
        try:
            server = create_server(controller, host="127.0.0.1", port=args.port, threads=4)
        except OSError:
            server = create_server(controller, host="127.0.0.1", port=0, threads=4)
        port = int(server.effective_port)
        controller.host = f"127.0.0.1:{port}"

        def record():
            return {"application": "Engcost", "instance_id": controller.instance_id,
                    "port": port, "token": controller.token}

        controller.record = record
        atomic_json(record_path, record())
        server_thread = threading.Thread(target=server.run, name="engcost-waitress")
        server_thread.start()
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: controller.stop.set())
        deadline = time.monotonic() + 30
        while not verified(record()):
            if time.monotonic() >= deadline:
                raise RuntimeError("Local server readiness failed")
            time.sleep(0.025)
        open_instance(record(), no_browser=args.no_browser)
        if selected:
            try:
                root = Path(selected).resolve()
                profile = read_record(root / "instance/app_data.json")
                resumable = (root / ".engcost-setup.json").is_file() and (
                    profile is None or not profile.get("users")
                )
                if getattr(sys, 'frozen', False) and (Path(sys.executable).parent / '.engcost-upgrading').exists():
                    raise RuntimeError('Installer is replacing application code')
                with controller.mutation:
                    controller.select(str(root), fresh=resumable)
            except Exception as exc:
                logger.warning("selection_rejected:%s", type(exc).__name__)
                controller.error = "فضای کاری ذخیره‌شده معتبر نیست؛ داده موجود حفظ شد. راهنمای بازیابی را بررسی کنید."
                controller.state = 'select'
        logger.info("local_server_ready")
        controller.stop.wait()
        controller.drain()
        server.task_dispatcher.shutdown(cancel_pending=False, timeout=60)
        server.close()
        # Close channels owned by this server only, after task draining.
        from waitress import wasyncore
        wasyncore.close_all(server._map)
        server_thread.join(timeout=5)
        return 0
    finally:
        if server is not None:
            server.close()
        if controller is not None:
            controller.close()
        record_path.unlink(missing_ok=True)
        ownership.close()
        logger.removeHandler(handler)
        handler.close()


def entrypoint():
    try:
        raise SystemExit(main())
    except Exception as exc:
        if '--installer-stop' in sys.argv or '--no-browser' in sys.argv:
            # Package scripts must never open a browser or prepare root's profile.
            if sys.stderr is not None:
                print('Engcost installer stop failed: ' + type(exc).__name__, file=sys.stderr)
            raise SystemExit(1)
        # Do not expose paths, accounts, tokens, input values, or exception text.
        message = "سامانه شروع نشد. دوباره تلاش کنید یا راهنمای بازیابی را بررسی کنید. (" + type(exc).__name__ + ")"
        if os.name == "nt":
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, "Engcost", 0x10 | 0x100000)
        else:
            config, _ = user_locations()
            private_directory(config)
            path = config / "startup-error.html"
            path.write_text('<meta charset="utf-8"><html lang="fa" dir="rtl"><p>' + message + '</p></html>', encoding="utf-8")
            webbrowser.open(path.as_uri())
        raise SystemExit(1)


if __name__ == "__main__":
    entrypoint()
