import unittest
from pathlib import Path

from utils.localization import display_value


ROOT = Path(__file__).resolve().parents[1]


class ModulePersianLocalizationTests(unittest.TestCase):
    def read_template(self, relative_path):
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_general_parameters_display_labels_preserve_internal_values(self):
        html = self.read_template("templates/general_parameters/general_parameters.html")
        self.assertIn("هزینه هر واحد به ارز", html)
        self.assertIn("انتخاب ارز", html)
        self.assertIn("IRR - ریال ایران", html)
        self.assertIn('value: "IRR - Iranian Rial"', html)
        self.assertIn("function displayHeader", html)
        self.assertIn("cost_per_unit_in_currency", html)
        self.assertIn("addRowBtn", html)

    def test_factory_parameters_display_labels_preserve_contract_fields(self):
        factories = self.read_template("templates/factory_parameters/factories.html")
        details = self.read_template("templates/factory_parameters/factory_details.html")
        self.assertIn("نام کارخانه", factories)
        self.assertIn("کارخانه دین‌محمدپور", factories)
        self.assertIn('name="factory name"', factories)
        self.assertIn("function displayDataValue", factories)
        self.assertIn("ساختار هزینه با موفقیت ذخیره شد", details)
        self.assertIn("selling_share_of_category", details)
        self.assertIn("preditcionOfProductionPerCapitaData", details)

    def test_product_configuration_display_labels_preserve_payload_keys(self):
        selection = self.read_template("templates/product/production_selection.html")
        product_page = self.read_template("templates/product/product_page.html")
        config = self.read_template("templates/product/configuration.html")
        self.assertIn("جدول محصولات", selection)
        self.assertIn("کارخانه دین‌محمدپور", selection)
        self.assertIn("product_name: productName", selection)
        self.assertIn('fetch("/add_product"', selection)
        self.assertIn("هزینه ماده به ریال", product_page)
        self.assertIn("/save_bom", product_page)
        self.assertIn("پیکربندی محصول", config)
        self.assertIn('id="product_code"', config)

    def test_shared_display_mapping_has_factory_and_product_reference_values(self):
        self.assertEqual(display_value("DinMohamadpour", "categories"), "کارخانه دین‌محمدپور")
        self.assertEqual(display_value("Bahman Khodro", "categories"), "بهمن خودرو")
        self.assertEqual(display_value("Lead-Acid", "categories"), "سرب-اسید")
        self.assertEqual(display_value("unmapped-value", "categories"), "unmapped-value")


if __name__ == "__main__":
    unittest.main()
