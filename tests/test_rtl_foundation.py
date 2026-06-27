from pathlib import Path
import unittest

from utils.localization import DEFAULT_DIRECTION, DEFAULT_LANGUAGE, DEFAULT_LOCALE, t


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
        self.assertIn('<html lang="fa" dir="rtl">', html)
        self.assertIn('static/css/style.css', html)
        self.assertIn('static/js/main.js', html)

    def test_localization_defaults_and_message_catalog(self):
        self.assertEqual(DEFAULT_LANGUAGE, "fa")
        self.assertEqual(DEFAULT_LOCALE, "fa-IR")
        self.assertEqual(DEFAULT_DIRECTION, "rtl")
        self.assertEqual(t("auth.invalid_credentials"), "نام کاربری یا گذرواژه نادرست است.")


if __name__ == "__main__":
    unittest.main()
