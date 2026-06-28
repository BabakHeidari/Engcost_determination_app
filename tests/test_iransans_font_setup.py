import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class IranSansFontSetupTests(unittest.TestCase):
    def test_global_stylesheet_declares_expected_iransansx_faces(self):
        css = (ROOT / "static/css/style.css").read_text(encoding="utf-8")
        expected = {
            "../fonts/IRANSansX-Regular.woff2": "font-weight: 400;",
            "../fonts/IRANSansX-Medium.woff2": "font-weight: 500;",
            "../fonts/IRANSansX-Bold.woff2": "font-weight: 700;",
        }
        self.assertEqual(css.count('font-family: "IRANSansX";'), 3)
        self.assertEqual(css.count("font-display: swap;"), 3)
        for path, weight in expected.items():
            self.assertIn(f'url("{path}") format("woff2")', css)
            self.assertIn(weight, css)

    def test_shared_font_stack_and_monospace_boundaries(self):
        css = (ROOT / "static/css/style.css").read_text(encoding="utf-8")
        self.assertIn('--app-font-family: "IRANSansX", "Vazirmatn", "Noto Naskh Arabic", Tahoma, "Segoe UI", Arial, sans-serif;', css)
        self.assertIn('code,\npre,\nkbd,\nsamp,\n.code-like,\n.formula,\n.sku', css)
        self.assertIn('"SF Mono", "Cascadia Code", "Consolas", "Liberation Mono", monospace', css)

    def test_dashboard_charts_use_shared_font_variable(self):
        dashboard = (ROOT / "templates/dashboard/dashboard.html").read_text(encoding="utf-8")
        self.assertIn("APP_FONT_FAMILY", dashboard)
        self.assertIn("textStyle: { fontFamily: APP_FONT_FAMILY }", dashboard)
        self.assertIn("fontFamily: APP_FONT_FAMILY", dashboard)

    def test_documentation_lists_expected_font_files(self):
        doc = (ROOT / "docs/persian-data-localization.md").read_text(encoding="utf-8")
        self.assertIn("static/fonts/IRANSansX-Regular.woff2", doc)
        self.assertIn("static/fonts/IRANSansX-Medium.woff2", doc)
        self.assertIn("static/fonts/IRANSansX-Bold.woff2", doc)
        self.assertIn("font-display: swap", doc)


if __name__ == "__main__":
    unittest.main()
