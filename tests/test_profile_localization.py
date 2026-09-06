from pathlib import Path
import unittest


PROFILE_TEMPLATE = Path("templates/profile/profile.html")


class ProfileLocalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = PROFILE_TEMPLATE.read_text(encoding="utf-8")

    def test_profile_static_shell_is_persian_rtl(self):
        self.assertIn('class="profile-page" dir="rtl"', self.template)
        for text in [
            "بازگشت",
            "پروفایل کاربر",
            "اطلاعات کاربر",
            "دسترسی‌های مؤثر",
            "تاریخچه فعالیت",
        ]:
            self.assertIn(text, self.template)

    def test_profile_is_read_only(self):
        for mutation in ["addUserModal", "addFactoryModal", "update-privileges", "Math.random", "DEFAULT_USERS"]:
            self.assertNotIn(mutation, self.template)

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
