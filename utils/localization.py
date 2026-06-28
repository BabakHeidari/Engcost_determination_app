"""Small shared localization helpers for the current Persian RTL UI foundation."""

DEFAULT_LOCALE = "fa-IR"
DEFAULT_LANGUAGE = "fa"
DEFAULT_DIRECTION = "rtl"

MESSAGES = {
    "auth.invalid_credentials": "نام کاربری یا گذرواژه نادرست است.",
}


def t(message_key, default=None):
    """Return a localized message for a stable message key."""
    return MESSAGES.get(message_key, default if default is not None else message_key)


PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

DISPLAY_MAPPINGS = {
    "statuses": {
        "success": "موفق", "ok": "تأیید شده", "error": "خطا", "failed": "ناموفق",
        "pending": "در انتظار", "active": "فعال", "inactive": "غیرفعال", "draft": "پیش‌نویس",
        "approved": "تأیید شده", "rejected": "رد شده", "completed": "تکمیل شده",
    },
    "columns": {
        "Product_Name": "نام محصول", "Factory": "کارخانه", "Category": "دسته", "Subcategory": "زیردسته",
        "Capacity": "ظرفیت", "factory name": "نام کارخانه", "manager": "مدیر", "city": "شهر",
        "address": "نشانی", "view": "مشاهده", "category": "دسته",
        "selling_share_of_category": "سهم فروش دسته", "Product Name": "نام محصول",
        "Predicted Production": "تولید پیش‌بینی‌شده", "subfield": "زیرحوزه", "cost": "هزینه",
        "percentageofall": "درصد از کل", "subject": "موضوع", "materials": "مواد", "material": "ماده",
        "unit": "واحد", "usage": "مصرف", "currency": "ارز", "cost_currency": "ارز هزینه",
        "cost_per_unit_in_currency": "هزینه هر واحد به ارز", "cost_per_unit": "هزینه هر واحد",
        "lost_percentage": "درصد ضایعات", "recycability_percentage": "درصد بازیافت‌پذیری",
        "cost_of_material_in_its_currency": "هزینه ماده به ارز اصلی",
        "cost_of_material_in_rial": "هزینه ماده به ریال", "actions": "عملیات",
    },
    "units": {
        "kg": "کیلوگرم", "Kilogram (kg)": "کیلوگرم (kg)", "t": "تن", "Metric Ton (t)": "تن (t)",
        "pc": "عدد", "Piece (pc)": "عدد (pc)", "hr": "ساعت", "Hour (hr)": "ساعت (hr)",
        "day": "روز", "Day (day)": "روز (day)", "No Unit: Currency": "بدون واحد: ارز",
    },
    "currencies": {
        "IRR": "ریال ایران", "USD": "دلار آمریکا", "EUR": "یورو",
        "IRR - Iranian Rial": "IRR - ریال ایران", "USD - US Dollar": "USD - دلار آمریکا",
    },
    "departments": {
        "AdministrativeandResearch": "اداری و پژوهش", "FinancialCosts": "هزینه‌های مالی",
        "Overhead": "سربار", "Payroll": "حقوق و دستمزد", "Depriciation": "استهلاک",
        "NonOperationalCostsandIncomes": "هزینه‌ها و درآمدهای غیرعملیاتی",
    },
    "categories": {
        "Cathode": "کاتد", "Anode": "آند", "Electrolyte": "الکترولیت", "Separator": "جداکننده",
        "Packaging": "بسته‌بندی", "Plant Alpha": "کارخانه آلفا", "Plant Beta": "کارخانه بتا",
        "Plant Gamma": "کارخانه گاما", "Factory A": "کارخانه الف", "Factory B": "کارخانه ب", "Factory C": "کارخانه ج",
        "DinMohamadpour": "کارخانه دین‌محمدپور", "HajAmini": "کارخانه حاج‌امینی", "Arefi": "کارخانه عارفی",
        "Nasooz": "کارخانه نسوز", "TajdidPazir": "کارخانه تجدیدپذیر", "Bahman Khodro": "بهمن خودرو",
        "IKCO": "ایران‌خودرو", "Saipa": "سایپا", "Lead-Acid": "سرب-اسید", "LithiumIon": "لیتیوم-یون",
        "Fidelity": "فیدلیتی", "Sild": "سیلد", "BigVehielcle": "خودروی سنگین", "SmallVehiecle": "خودروی سبک",
        "Tehran": "تهران", "Qom": "قم", "Semnan": "سمنان", "Zanjan": "زنجان",
    },
    "reports": {
        "total_cost": "کل هزینه", "avg_cost_per_product": "میانگین هزینه هر محصول",
        "product_count": "تعداد محصولات", "top_cost_driver": "مهم‌ترین عامل هزینه",
        "breakdown_by_category": "تفکیک بر اساس دسته", "breakdown_by_subcategory": "تفکیک بر اساس زیردسته",
        "detail_breakdown": "ریز تفکیک هزینه",
    },
}


def display_value(value, domain=None, default=None):
    """Return a Persian presentation value without mutating the stored/internal value."""
    if value is None:
        return default if default is not None else ""
    text = str(value)
    domains = [domain] if domain else []
    domains.extend(["columns", "statuses", "departments", "units", "currencies", "categories", "reports"])
    for name in domains:
        mapping = DISPLAY_MAPPINGS.get(name, {})
        if text in mapping:
            return mapping[text]
    return default if default is not None else text


def format_persian_digits(value):
    """Format display-only numbers with Persian digits; does not parse or alter raw values."""
    return str(value).translate(PERSIAN_DIGITS)
