import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RtlSidebarLayoutTests(unittest.TestCase):
    def test_base_layout_places_sidebar_before_content_in_rtl_row(self):
        html = (ROOT / "templates/base.html").read_text(encoding="utf-8")
        self.assertIn('class="app-layout d-flex flex-column flex-lg-row min-vh-100"', html)
        self.assertNotIn("flex-lg-row-reverse", html)
        self.assertLess(html.index('<aside class="sidebar" id="mainSidebar">'), html.index('<div class="main-content flex-grow-1 d-flex flex-column">'))

    def test_sidebar_uses_right_side_logical_positioning(self):
        css = (ROOT / "static/css/style.css").read_text(encoding="utf-8")
        self.assertIn(".app-layout", css)
        self.assertIn("direction: rtl;", css)
        self.assertIn("position: sticky;", css)
        self.assertIn("inset-inline-start: 0;", css)
        self.assertIn("block-size: 100vh;", css)
        self.assertIn("transform: translateX(100%);", css)
        self.assertNotIn("inset-inline-end: 0;\n        block-size: 100%;\n        transform: translateX(100%);", css)

    def test_existing_sidebar_toggle_ids_are_preserved(self):
        html = (ROOT / "templates/base.html").read_text(encoding="utf-8")
        self.assertIn('id="sidebarToggle"', html)
        self.assertIn('id="mainSidebar"', html)
        self.assertIn('id="sidebarOverlay"', html)
        self.assertIn("sidebar.classList.toggle('show')", html)
        self.assertIn("document.body.classList.toggle('sidebar-open')", html)


if __name__ == "__main__":
    unittest.main()
