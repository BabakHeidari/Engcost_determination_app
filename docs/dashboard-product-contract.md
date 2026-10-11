# قرارداد محصول داشبورد — نسخه ۱

این سند مصوبات مالک محصول برای DASH-0.4، برش مستقل فیلترهای DASH-1 و
اجرای backend تحلیل DASH-3 را ثبت می‌کند. قرارداد API اجرایی در
[PR-06](pr06-dashboard-cost-analysis-api.md)، رابط تحلیل در
[PR-07](pr07-dashboard-cost-analysis-ui.md) و API حساسیت در
[PR-08](pr08-dashboard-sensitivity-api.md) و رابط حساسیت در
[PR-09](pr09-dashboard-sensitivity-ui.md) ثبت شده‌اند. شواهد وضع موجود در
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
| تحلیل هزینه یک کارخانه | `dashboard:READ` روی همان کارخانه | 403؛ بدون lookup عملیاتی |
| فهرست/اجرای پارامتر عمومی حساسیت | Dashboard READ و `general_parameters:READ` سراسری | پارامتر از فهرست حذف و override نامجاز رد می‌شود |
| فهرست/اجرای پارامتر کارخانه‌ای حساسیت | Dashboard READ و `factory_parameters:READ` روی همان کارخانه | پارامتر از فهرست حذف و override نامجاز رد می‌شود |

مدیران سطح بالا طبق سیاست مرکزی به همهٔ کارخانه‌های فعال دسترسی دارند. مجوز
`product` یا `cost_calculation` پیش‌شرط endpoint داشبورد نیست و مجوز یک
کارخانه دامنهٔ کارخانه دیگر را باز نمی‌کند. HTTP 401/403 نتایج دسترسی‌اند،
نه وضعیت دادهٔ کسب‌وکار.

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

شش وضعیت دادهٔ مصوب اجرای عددی بدون تبدیل ضمنی به صفر تعریف می‌شوند:
`OK`، `MISSING_INPUT`، `INVALID_INPUT`، `AMBIGUOUS_INPUT`،
`NOT_APPLICABLE` و `CALCULATION_ERROR`. تجمیع ناقص وضعیت جداگانهٔ `PARTIAL`
دارد و پوشش و شمار excluded را همراه می‌کند. `GET /api/cost_analysis`
نسخه `1` با موتور مشترک هزینه اجرا می‌شود: پوشش کامل `projected_total`،
پوشش مختلط فقط `partial_total` با برچسب «مجموع جزئی» و نبود ردیف معتبر
مقدارهای عددی `null` می‌دهد. انتخاب صریح هر سه سطح الزامی است؛
`NO_MATCH` از `NOT_SELECTED` جدا می‌ماند. جزئیات دامنه، breakdown، دوره،
lineage و وضعیت فعلی top driver در [قرارداد PR-06](pr06-dashboard-cost-analysis-api.md)
ثبت شده است؛ صفر ساختگی گزارش نمی‌شود.

API حساسیت PR-08 دقیقاً یک پیکربندی، دسته و زیردسته صریح و یک شناسه دوره موجود
را می‌پذیرد؛ `ALL` و انتخاب چندمحصولی مجاز نیستند. registry سرور فقط ورودی‌های
مصوب با mapping معتبر را به کاربر مجاز عرضه می‌کند. سناریوهای what-if صرفاً
در حافظهٔ همان درخواست‌اند: هیچ write به Profile، BOM، پارامتر عمومی یا
`Data/Factories` مجاز نیست. خط‌مبنا و سناریو با snapshot مشترک و موتور یکسان
محاسبه می‌شوند؛ مجوز گروه‌ها در POST دوباره بررسی می‌شود. ورودی‌های گروه
نامجاز حتی در breakdown، خطا و metadata پاسخ افشا نمی‌شوند. زمان محاسبه و
provenance فقط اگر منبع واقعاً پشتیبانی کند گزارش می‌شود؛ timestamp حدسی ممنوع
است. رابط حساسیت در PR-09 فعال شده است؛ کنترل‌ها تنها از registry مجاز ساخته
می‌شوند و هر مقایسه فقط baseline و scenario همان پاسخ POST را استفاده می‌کند.
تغییر انتخاب/پیش‌نویس و بازنشانی نتیجه و CSV قبلی را باطل می‌کنند؛ بازنشانی
خط‌مبنای مجاز همان دامنه را بدون درخواست تازه حفظ می‌کند.

## موتور مشترک هزینهٔ PR-05

فرمول live و چهار gate عددی G1–G4 در تاریخ `2026-09-27` به تأیید مالک رسیدند.
Cost Calculation و Dashboard از همان تابع pure عبور می‌کنند. loader پیش‌فرض
Cost Calculation رفتار مهاجرت موجود را حفظ می‌کند؛ Dashboard صریحاً از
`read_only=True` و `module="dashboard"` با snapshot درخواست استفاده می‌کند
و configuration، metadata یا دوره اولیه نمی‌سازد. period legacy باید در
binding معتبر موجود به یک کارخانه و بازه صریح متصل باشد؛ رکورد معتبر
`SYSTEM_INITIALIZATION` نیز پذیرفته می‌شود. baseline مالک از actual timestamp
و calculation timestamp جدا گزارش می‌شود. KPIهای backend در PR-06 اجرا
می‌شوند؛ UI تحلیل و CSV در PR-07 و registry/API حساسیت در PR-08 اجرا می‌شوند.
رابط حساسیت در PR-09 ارائه می‌شود؛ ذخیره/اعمال سناریو همچنان خارج از دامنه است.

## فرض‌های فنیِ تأییدنشده

نام فایل JSON غیر `_meta` فعلاً نشانگر پیکربندی محصول در read-model است؛ این
یک قرارداد فنی با ساختار عملیاتی موجود است، نه تصویب معنای حسابداری فایل.
Base64URL فقط encoding شناسهٔ مرکب است و شناسهٔ تجاری جدید محسوب نمی‌شود.
