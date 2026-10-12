from pathlib import Path
import unittest
import tempfile

from utils.localization import DEFAULT_DIRECTION, DEFAULT_LANGUAGE, DEFAULT_LOCALE, t
from utils.profile_store import ProfileDataStore


class RtlFoundationTests(unittest.TestCase):
    def test_base_template_sets_persian_rtl_root(self):
        base = Path("templates/base.html").read_text(encoding="utf-8")
        self.assertIn('<html lang="fa" dir="rtl">', base)

    def test_shared_layout_loads_with_persian_rtl_context(self):
        try:
            import app as app_module
        except ModuleNotFoundError as exc:
            if exc.name == "flask":
                self.skipTest("Flask is not installed in this execution environment")
            raise

        flask_app = app_module.app
        flask_app.config.update(TESTING=True)
        with flask_app.test_client() as client:
            response = client.get("/login")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('<html lang="fa-IR" dir="rtl">', html)
        self.assertIn('static/css/style.css', html)
        # Login has its own shell. Render a real authenticated shared-layout
        # page before checking its shared script and Persian/RTL root.
        with tempfile.TemporaryDirectory() as directory:
            store = ProfileDataStore(Path(directory) / "profiles.json")
            store.initialize({})
            store.create_user({"id": "rtl-reader", "username": "rtl-reader", "email": "rtl@example.test",
                               "full_name": "کاربر", "system_role": "USER", "job_title": "",
                               "access_grants": [], "is_active": True, "must_change_password": False,
                               "password_hash": "unused", "revision": 1})
            previous = flask_app.config.get("APP_DATA_FILE")
            flask_app.config["APP_DATA_FILE"] = str(store.path)
            try:
                with flask_app.test_client() as client:
                    with client.session_transaction() as session:
                        session["user_id"] = "rtl-reader"
                    shared = client.get("/workdesk")
                self.assertEqual(shared.status_code, 200)
                html = shared.get_data(as_text=True)
                self.assertIn('<html lang="fa" dir="rtl">', html)
                self.assertIn('static/js/main.js', html)
            finally:
                if previous is None:
                    flask_app.config.pop("APP_DATA_FILE", None)
                else:
                    flask_app.config["APP_DATA_FILE"] = previous

    def test_localization_defaults_and_message_catalog(self):
        self.assertEqual(DEFAULT_LANGUAGE, "fa")
        self.assertEqual(DEFAULT_LOCALE, "fa-IR")
        self.assertEqual(DEFAULT_DIRECTION, "rtl")
        self.assertEqual(t("auth.invalid_credentials"), "نام کاربری یا گذرواژه نادرست است.")


if __name__ == "__main__":
    unittest.main()
