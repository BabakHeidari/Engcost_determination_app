import os
import unittest
from pathlib import Path

from utils.demo_data import DEMO_LOCALE_ENV, demo_path_for, persian_demo_enabled
from utils.localization import DISPLAY_MAPPINGS, display_value, format_persian_digits
from utils.paths import parent_path, product_path


class PersianDataLayerTests(unittest.TestCase):
    def setUp(self):
        self.previous_demo_locale = os.environ.get(DEMO_LOCALE_ENV)

    def tearDown(self):
        if self.previous_demo_locale is None:
            os.environ.pop(DEMO_LOCALE_ENV, None)
        else:
            os.environ[DEMO_LOCALE_ENV] = self.previous_demo_locale

    def test_display_mappings_preserve_unknown_fallbacks(self):
        self.assertEqual(display_value("Product_Name", "columns"), "نام محصول")
        self.assertEqual(display_value("success", "statuses"), "موفق")
        self.assertEqual(display_value("AdministrativeandResearch", "departments"), "اداری و پژوهش")
        self.assertEqual(display_value("unmapped-production-value"), "unmapped-production-value")

    def test_persian_digits_are_display_only_strings(self):
        self.assertEqual(format_persian_digits("Cost 12345.67"), "Cost ۱۲۳۴۵.۶۷")

    def test_persian_demo_data_is_opt_in(self):
        os.environ.pop(DEMO_LOCALE_ENV, None)
        self.assertFalse(persian_demo_enabled())
        canonical = Path(product_path + ".json")
        self.assertEqual(demo_path_for(canonical), canonical)

        os.environ[DEMO_LOCALE_ENV] = "fa"
        self.assertTrue(persian_demo_enabled())
        self.assertEqual(
            demo_path_for(canonical),
            Path(parent_path) / "Demo" / "fa" / "ProductsLater.json",
        )

    def test_mapping_domains_cover_core_reference_groups(self):
        for domain in ["statuses", "columns", "units", "currencies", "departments", "categories", "reports"]:
            self.assertIn(domain, DISPLAY_MAPPINGS)
            self.assertTrue(DISPLAY_MAPPINGS[domain])


if __name__ == "__main__":
    unittest.main()
