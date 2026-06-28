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
from datetime import date, datetime
import re

PERSIAN_MONTH_NAMES = (
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
)
_LATIN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

def normalize_digits(value):
    return str(value).translate(_LATIN_DIGITS)

def _div(a, b):
    return a // b

def _gregorian_to_jdn(gy, gm, gd):
    return (_div((gy + _div(gm - 8, 6) + 100100) * 1461, 4)
            + _div(153 * ((gm + 9) % 12) + 2, 5)
            + gd - 34840408
            - _div(_div(gy + 100100 + _div(gm - 8, 6), 100) * 3, 4)
            + 752)

def _jdn_to_gregorian(jdn):
    j = 4 * jdn + 139361631
    j = j + _div(_div(4 * jdn + 183187720, 146097) * 3, 4) * 4 - 3908
    i = _div((j % 1461), 4) * 5 + 308
    gd = _div((i % 153), 5) + 1
    gm = (_div(i, 153) % 12) + 1
    gy = _div(j, 1461) - 100100 + _div(8 - gm, 6)
    return gy, gm, gd

def _jalali_to_jdn(jy, jm, jd):
    r = _jalali_cal(jy)
    return (_gregorian_to_jdn(r["gy"], 3, r["march"])
            + (jm - 1) * 31 - _div(jm, 7) * (jm - 7) + jd - 1)

def _jalali_cal(jy):
    breaks = [-61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181, 1210,
              1635, 2060, 2097, 2192, 2262, 2324, 2394, 2456, 3178]
    gy = jy + 621
    leap_j = -14
    jp = breaks[0]
    if jy < jp or jy >= breaks[-1]:
        raise ValueError("سال جلالی خارج از محدوده پشتیبانی است.")
    jump = 0
    for jm_break in breaks[1:]:
        jump = jm_break - jp
        if jy < jm_break:
            break
        leap_j += _div(jump, 33) * 8 + _div(jump % 33, 4)
        jp = jm_break
    n = jy - jp
    leap_j += _div(n, 33) * 8 + _div((n % 33) + 3, 4)
    if jump % 33 == 4 and jump - n == 4:
        leap_j += 1
    leap_g = _div(gy, 4) - _div((_div(gy, 100) + 1) * 3, 4) - 150
    march = 20 + leap_j - leap_g
    if jump - n < 6:
        n = n - jump + _div(jump + 4, 33) * 33
    leap = ((n + 1) % 33 - 1) % 4
    if leap == -1:
        leap = 4
    return {"leap": leap, "gy": gy, "march": march}

def gregorian_to_jalali(gy, gm, gd):
    jy = gy - 621
    r = _jalali_cal(jy)
    jdn1f = _gregorian_to_jdn(gy, 3, r["march"])
    jdn = _gregorian_to_jdn(gy, gm, gd)
    k = jdn - jdn1f
    if k >= 0:
        if k <= 185:
            return jy, 1 + _div(k, 31), (k % 31) + 1
        k -= 186
    else:
        jy -= 1
        k += 179
        if _jalali_cal(jy)["leap"] == 0:
            k += 1
    return jy, 7 + _div(k, 30), (k % 30) + 1

def is_jalali_leap_year(jy):
    return _jalali_cal(jy)["leap"] == 0

def jalali_month_length(jy, jm):
    if 1 <= jm <= 6: return 31
    if 7 <= jm <= 11: return 30
    if jm == 12: return 30 if is_jalali_leap_year(jy) else 29
    return 0

def jalali_to_gregorian(jy, jm, jd):
    if not (1 <= jm <= 12 and 1 <= jd <= jalali_month_length(jy, jm)):
        raise ValueError("تاریخ جلالی نامعتبر است.")
    start = date(jy + 621, 3, 1).toordinal()
    end = date(jy + 622, 3, 31).toordinal()
    for ordinal in range(start, end + 1):
        candidate = date.fromordinal(ordinal)
        if gregorian_to_jalali(candidate.year, candidate.month, candidate.day) == (jy, jm, jd):
            return candidate.year, candidate.month, candidate.day
    raise ValueError("تاریخ جلالی نامعتبر است.")

def _parse_datetime(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime): return value
    if isinstance(value, date): return datetime(value.year, value.month, value.day)
    text = str(value).strip().replace("Z", "+00:00")
    try: return datetime.fromisoformat(text)
    except ValueError:
        try: return datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError: return None

def format_jalali_date(value, fallback=""):
    dt = _parse_datetime(value)
    if not dt: return fallback
    jy, jm, jd = gregorian_to_jalali(dt.year, dt.month, dt.day)
    return f"{jy:04d}/{jm:02d}/{jd:02d}".translate(PERSIAN_DIGITS)

def format_jalali_datetime(value, include_time=True, fallback=""):
    dt = _parse_datetime(value)
    if not dt: return fallback
    out = format_jalali_date(dt, fallback)
    if include_time:
        out += f" - {dt.hour:02d}:{dt.minute:02d}".translate(PERSIAN_DIGITS)
    return out

def parse_jalali_input(value, include_time=False):
    text = normalize_digits(value).strip()
    m = re.match(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})(?:\s*(?:-|T|\s)\s*(\d{1,2}):(\d{2}))?$", text)
    if not m: raise ValueError("تاریخ را در قالب ۱۴۰۵/۰۴/۰۷ وارد کنید.")
    jy, jm, jd = map(int, m.group(1,2,3)); gy, gm, gd = jalali_to_gregorian(jy,jm,jd)
    if include_time or m.group(4):
        hh = int(m.group(4) or 0); mm = int(m.group(5) or 0)
        if hh > 23 or mm > 59: raise ValueError("زمان نامعتبر است.")
        return f"{gy:04d}-{gm:02d}-{gd:02d}T{hh:02d}:{mm:02d}:00"
    return f"{gy:04d}-{gm:02d}-{gd:02d}"

def format_jalali_range(start, end, fallback=""):
    s = format_jalali_date(start, fallback); e = format_jalali_date(end, fallback)
    return f"{s} تا {e}" if s and e else s or e or fallback
