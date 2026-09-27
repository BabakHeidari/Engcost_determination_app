# قرارداد محصول داشبورد — نسخه ۱

این سند مصوبات مالک محصول برای DASH-0.4 و برش مستقل فیلترهای DASH-1 را
ثبت می‌کند. شواهد وضع موجود در
[کشف ماژول](dashboard-module-discovery.md)،
[ممیزی هزینه](dash0-current-costing-audit.md) و
[خط‌مبناهای مشخصه‌ای](dash0-characterization-baselines.md) است. وضعیت مصوبات
در [دفتر تصمیم](dashboard-decision-ledger.md) و موانع عددی در
[دروازه‌های تأیید](dashboard-owner-approval-gates.md) آمده است.

## دامنه و هویت

هویت پیکربندی V1 چهارگانهٔ `factory_id + category + subcategory + product`
است؛ نام یکسان محصول در دو مسیر ادغام نمی‌شود. دقیقاً یک شناسه canonical و
فعال کارخانه الزامی است و گزینهٔ «همهٔ کارخانه‌ها» وجود ندارد. کارخانه ابتدا
در رجیستری Profile اعتبارسنجی و برای مجوز `dashboard:READ` بررسی می‌شود؛ تنها
پس از آن `operational_key` برای خواندن `Data/Factories` به‌کار می‌رود.

| کنش | مجوز لازم | نتیجهٔ نبود مجوز |
|---|---|---|
| ورود به صفحه با دسترسی کارخانه‌ای | `dashboard:READ` روی حداقل یک کارخانه | 403 |
| دریافت سلسله‌مراتب یک کارخانه | `dashboard:READ` روی همان کارخانه | 403؛ بدون lookup عملیاتی |
| مشاهده/اجرای حساسیت عمومی (آتی) | Dashboard READ و `general_parameters:READ` | کنش نمایش داده/اجرا نمی‌شود |
| مشاهده/اجرای حساسیت کارخانه (آتی) | Dashboard READ و `factory_parameters:READ` روی همان کارخانه | کنش نمایش داده/اجرا نمی‌شود |

مدیران سطح بالا طبق سیاست مرکزی به همهٔ کارخانه‌های فعال دسترسی دارند. مجوز
`product` هرگز پیش‌شرط endpoint داشبورد نیست و مجوز یک کارخانه دامنهٔ کارخانه
دیگر را باز نمی‌کند. HTTP 401/403 نتایج دسترسی‌اند، نه وضعیت دادهٔ کسب‌وکار.

## قرارداد دقیق فیلتر

`GET /api/dashboard/filter-options` پاسخ JSON نسخه `1` می‌دهد. پارامتر
`factory` الزامی است. `category`، `subcategory` و `product` هرکدام سه حالت
دارند: نبود پارامتر = `NOT_SELECTED`، مقدار `__ALL__` = عملگر صریح ALL، و یک
شناسهٔ عضو = انتخاب صریح. مقدار خالی به‌عنوان ALL تفسیر نمی‌شود. فرزند فقط در
دامنهٔ والد پاسخ داده می‌شود و عضو دستکاری‌شده یا ناسازگار `400
INVALID_SELECTION` می‌گیرد.

پاسخ شامل `version`، کارخانهٔ عمومی canonical، `state`، `operators.all`،
`selection` و `options.{categories,subcategories,products}` است. گزینه‌ها
قطعی و مرتب‌اند. شناسهٔ محصول یک reference مرکب پایدار از کل مسیر عملیاتی
است و label صرفاً نمایشی است. حالت‌ها عبارت‌اند از `OK`، `UNCONFIGURED`،
`NO_MATCH`، `NOT_SELECTED`، `INVALID_SELECTION`، `UNKNOWN_FACTORY`،
`FORBIDDEN` و `UNAVAILABLE`.

کلاینت کنترل‌های فرزند را هنگام بارگذاری غیرفعال می‌کند، پاسخ‌های منقضی را با
sequence و AbortController کنار می‌گذارد، فقط انتخاب هنوز معتبر را نگه
می‌دارد و رشته‌های داده را فقط با `textContent`/DOM API درج می‌کند.

## وضعیت‌های تحلیلی و سناریو

شش وضعیت دادهٔ مصوب برای اجرای عددی آتی باید بدون تبدیل ضمنی به صفر تعریف
شوند: `OK`، `MISSING_INPUT`، `INVALID_INPUT`، `AMBIGUOUS_INPUT`،
`NOT_APPLICABLE` و `CALCULATION_ERROR`. تجمیع ناقص وضعیت جداگانهٔ `PARTIAL`
دارد و پوشش و شمار excluded را همراه می‌کند. endpoint هزینه در این PR عمداً
`501 NOT_IMPLEMENTED` و `kpis: null` می‌دهد؛ صفر ساختگی گزارش نمی‌شود.

سناریوهای what-if آتی صرفاً در حافظهٔ درخواست‌اند: هیچ write به Profile، BOM،
پارامتر عمومی یا `Data/Factories` مجاز نیست. زمان محاسبه و provenance فقط اگر
منبع واقعاً پشتیبانی کند گزارش می‌شود؛ timestamp حدسی ممنوع است.

## موتور مشترک هزینهٔ PR-05

فرمول live و چهار gate عددی G1–G4 در تاریخ `2026-09-27` به تأیید مالک رسیدند.
Cost Calculation از loader فقط‌خواندنی و همان تابع pure که مصرف‌کنندگان تحلیلی
آتی استفاده خواهند کرد عبور می‌کند. period legacy باید در فایل binding
owner-controlled به یک کارخانه و یک بازهٔ صریح متصل باشد. baseline مالک از
actual timestamp و calculation timestamp جدا گزارش می‌شود. Dashboard KPI و UI
حساسیت همچنان خارج از دامنهٔ این PR هستند.

## فرض‌های فنیِ تأییدنشده

نام فایل JSON غیر `_meta` فعلاً نشانگر پیکربندی محصول در read-model است؛ این
یک قرارداد فنی با ساختار عملیاتی موجود است، نه تصویب معنای حسابداری فایل.
Base64URL فقط encoding شناسهٔ مرکب است و شناسهٔ تجاری جدید محسوب نمی‌شود.
