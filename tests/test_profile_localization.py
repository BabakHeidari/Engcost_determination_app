from pathlib import Path
import unittest


PROFILE_TEMPLATE = Path("templates/profile/profile.html")


class ProfileLocalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = PROFILE_TEMPLATE.read_text(encoding="utf-8")

    def test_profile_static_shell_is_persian_rtl(self):
        self.assertIn('class="dashboard" dir="rtl"', self.template)
        for text in [
            "بازگشت",
            "پروفایل کاربر",
            "کنترل‌های مدیریتی",
            "افزودن کاربر جدید",
            "افزودن کارخانه جدید",
            "دسترسی اولیه ماژول‌ها",
        ]:
            self.assertIn(text, self.template)

    def test_profile_display_mapping_helpers_keep_internal_values(self):
        for internal_value in ["IT Admin", "Official Admin", "Factory Admin", "General Parameters", "User Profile", "Read", "Write", "Modify"]:
            self.assertIn(internal_value, self.template)
        for display_value in ["مدیر فناوری اطلاعات", "مدیر سازمانی", "مدیر کارخانه", "پارامترهای عمومی", "خواندن", "نوشتن", "ویرایش"]:
            self.assertIn(display_value, self.template)

    def test_profile_critical_identifiers_are_not_renamed(self):
        for identifier in [
            'id="newUserEmail"',
            'id="newUserRole"',
            'id="newUserFactory"',
            'id="newFactoryLocation"',
            "currentUser",
            "target_user_id",
            "new_privileges",
            "/api/profile/update-privileges",
        ]:
            self.assertIn(identifier, self.template)

    def test_profile_visible_english_replacements(self):
        visible_english = [
            ">Back<",
            ">Loading...<",
            ">Admin Controls<",
            ">Add New User<",
            ">Add Factory<",
            "No users to display",
            "Network error.",
            "Email already exists.",
        ]
        for text in visible_english:
            self.assertNotIn(text, self.template)


if __name__ == "__main__":
    unittest.main()
