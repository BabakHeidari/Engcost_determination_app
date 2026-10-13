"""Private loopback setup/control UI and a draining business WSGI dispatcher."""
from contextlib import ExitStack
import hmac
import json
import logging
from pathlib import Path
import secrets
import threading

from flask import Flask, abort, jsonify, make_response, redirect, render_template, request

from standalone.workspace import activate, atomic_json, checked_root, first_admin, prepare, private_directory
from utils.file_lock import interprocess_file_lock
from utils.profile_store import ProfileDataStore, ProfileStoreError
from utils.runtime_paths import RuntimePaths


class Controller:
    def __init__(self, config, default_workspace, *, workspace=None, record=None):
        resources = RuntimePaths.from_environment({}).resources
        self.config = Path(config)
        self.default_workspace = Path(default_workspace)
        self.workspace = workspace
        self.record = record
        self.token = secrets.token_urlsafe(32)
        self.instance_id = secrets.token_hex(16)
        self.csrf = secrets.token_urlsafe(32)
        self.stop = threading.Event()
        self.condition = threading.Condition()
        self.active = 0
        self.stopping = False
        self.business = None
        self.state = "select"
        self.error = None
        self.ownership = ExitStack()
        self.mutation = threading.Lock()
        self.local = Flask("engcost_local", template_folder=str(resources / "templates"),
                           static_folder=str(resources / "static"), static_url_path="/_local/static")
        self.local.config["MAX_CONTENT_LENGTH"] = 16384
        self._routes()

    def _authorized(self):
        return hmac.compare_digest(request.cookies.get("engcost_local", ""), self.token)

    def _routes(self):
        app = self.local

        @app.before_request
        def boundary():
            if request.remote_addr != "127.0.0.1" or request.host != self.host:
                abort(403)
            if request.method == "POST" and request.headers.get("Origin") != "http://" + self.host:
                abort(403)
            if request.path in {"/_local/", "/_local/authorize", "/_local/health"} or request.path.startswith("/_local/static/"):
                return
            if not self._authorized():
                abort(403)
            if request.method == "POST" and not hmac.compare_digest(request.form.get("csrf", ""), self.csrf):
                abort(403)

        @app.after_request
        def protect(response):
            response.headers["Cache-Control"] = "no-store"
            # no-referrer makes browser form POSTs send Origin: null. Retain
            # the same-origin value required by boundary(), while still keeping
            # local URLs out of cross-origin referrers. Capabilities are removed
            # from the fragment by standalone-entry.js before navigation.
            response.headers["Referrer-Policy"] = "same-origin"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'none'"
            return response

        @app.get("/_local/health")
        def health():
            if not hmac.compare_digest(request.headers.get("X-Engcost-Capability", ""), self.token):
                abort(403)
            return jsonify(application="Engcost", instance_id=self.instance_id, state=self.state)

        @app.post("/_local/authorize")
        def authorize():
            value = (request.get_json(silent=True) or {}).get("capability", "")
            if not isinstance(value, str) or not hmac.compare_digest(value, self.token):
                abort(403)
            response = make_response(jsonify(ok=True))
            response.set_cookie("engcost_local", self.token, httponly=True, samesite="Strict", path="/_local")
            return response

        @app.get("/_local/")
        def entry():
            return render_template("standalone/entry.html")

        @app.get("/_local/status")
        def status():
            return jsonify(state=self.state)

        @app.get("/_local/panel")
        def panel():
            return render_template("standalone/panel.html", state=self.state, csrf=self.csrf,
                                   default_workspace=str(self.default_workspace), error=self.error)

        @app.post("/_local/workspace")
        def select():
            if not self.mutation.acquire(blocking=False):
                abort(409)
            try:
                if self.stopping or self.state != "select":
                    abort(409)
                self.select(request.form.get("workspace", ""), fresh=request.form.get("mode") == "fresh")
                self.error = None
            except (ValueError, OSError, ProfileStoreError) as exc:
                logging.getLogger("engcost").warning("workspace_rejected:%s", type(exc).__name__)
                self.error = "فضای کاری معتبر نیست یا اجازه دسترسی ندارید. داده موجود حفظ شد؛ راهنمای بازیابی را بررسی کنید."
            finally:
                self.mutation.release()
            return redirect("/_local/panel")

        @app.post("/_local/admin")
        def admin():
            with self.mutation:
                if self.stopping or self.state != "admin":
                    abort(409)
                try:
                    first_admin(self.workspace, request.form)
                    self.error = None
                    self.start_business()
                except (ValueError, OSError, ProfileStoreError) as exc:
                    logging.getLogger("engcost").warning("admin_rejected:%s", type(exc).__name__)
                    self.error = "حساب ساخته نشد. نام، ایمیل و گذرواژه (حداقل ۱۲ نویسه) و تکرار آن را بررسی کنید."
            return redirect("/_local/panel")

        @app.post("/_local/stop")
        def stop():
            with self.condition:
                self.stopping = True
                self.state = "stopping"
            self.stop.set()
            return render_template("standalone/stopped.html")

    def select(self, value, *, fresh=False):
        root = checked_root(value)
        # Never add a lock or runtime directory to an unvalidated existing root.
        if not fresh:
            from standalone.workspace import validate_existing
            validate_existing(root)
        elif root.exists() and any(root.iterdir()) and not (root / ".engcost-setup.json").is_file():
            raise ValueError("Fresh workspace must be empty")
        private_directory(root)
        lock = self.ownership.enter_context(interprocess_file_lock(root / ".engcost-instance.lock", timeout=0))
        try:
            # The owned lock is the only extra file allowed before fresh preparation.
            if fresh and not (root / ".engcost-setup.json").exists():
                atomic_json(root / ".engcost-setup.json", {"schema": 1, "mode": "fresh"})
            root, settings = prepare(root, fresh=fresh)
            activate(root, settings)
            self.workspace = root
            atomic_json(self.config / "selection.json", {"schema": 1, "workspace": str(root)})
            atomic_json(root / "runtime/instance.json", self.record())
            if ProfileDataStore(root / "instance/app_data.json").load_data()["users"]:
                self.start_business()
            elif fresh:
                self.state = "admin"
            else:
                raise ValueError("Existing workspace has no users")
        except BaseException:
            self.ownership.close()
            raise

    def start_business(self):
        self.state = "preparing"

        def initialize():
            try:
                # Preparation and path/secret configuration strictly precede import.
                from app import app
                app.config.update(DEBUG=False, TESTING=False, SESSION_COOKIE_SECURE=False)
                self.business = app
                self.state = "ready"
            except Exception as exc:
                logging.getLogger("engcost").error("startup_failed:%s", type(exc).__name__)
                self.error = "آماده‌سازی انجام نشد. برنامه را متوقف کنید و راهنمای بازیابی را بررسی کنید."
                self.state = "error"

        self.initializer = threading.Thread(target=initialize, name="engcost-initialize")
        self.initializer.start()

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        if path.startswith("/_local/"):
            return self.local(environ, start_response)
        # Also reject DNS rebinding for the existing business app.
        if environ.get("REMOTE_ADDR") != "127.0.0.1" or environ.get("HTTP_HOST") != self.host:
            start_response("403 Forbidden", [("Content-Type", "text/plain")])
            return [b"Forbidden"]
        with self.condition:
            if self.stopping or self.business is None:
                start_response("503 Service Unavailable", [("Content-Type", "text/plain; charset=utf-8")])
                return ["سامانه در حال آماده‌سازی یا توقف است.".encode()]
            self.active += 1

        def finish():
            try:
                iterable = self.business(environ, start_response)
                try:
                    yield from iterable
                finally:
                    if hasattr(iterable, "close"):
                        iterable.close()
            finally:
                with self.condition:
                    self.active -= 1
                    self.condition.notify_all()
        return finish()

    def drain(self):
        with self.condition:
            self.stopping = True
            while self.active:
                self.condition.wait(timeout=0.2)
        # Setup writes use this same mutex. Wait for the complete transaction
        # and any initializer it starts before releasing workspace ownership.
        with self.mutation:
            initializer = getattr(self, 'initializer', None)
        if initializer is not None:
            initializer.join()

    def close(self):
        if self.workspace:
            (self.workspace / "runtime/instance.json").unlink(missing_ok=True)
        self.ownership.close()
