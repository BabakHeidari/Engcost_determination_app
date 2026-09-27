# معناشناسی مصوب هزینهٔ داشبورد V1

این سند قرارداد نتیجه را ثبت می‌کند و هیچ فرمولی را اجرا یا تغییر نمی‌دهد.
رفتار legacy در [ممیزی](dash0-current-costing-audit.md) و
[آزمون‌های مشخصه‌ای](dash0-characterization-baselines.md) باقی مانده است.

## KPIها و پوشش

| KPI | صورت | مخرج | واحد | جمعیت و پوشش |
|---|---|---|---|---|
| هزینهٔ واحد کاندید | `Final_Production_Cost` معتبر | یک واحد پیکربندی محصول | ریال/محصول (مشروط به اعتبار ورودی‌ها) | فقط پیکربندی eligible و محاسبه‌شده |
| هزینهٔ کل پیش‌بینی‌شده | مجموع `unit cost × approved prediction` هم‌دوره | ندارد | ریال/دوره | ناقص فقط با برچسب «مجموع جزئی»، درصد پوشش و excluded count |
| میانگین موزون واحد | مجموع `unit cost × approved quantity` | مجموع همان quantity معتبر | ریال/محصول | numerator، denominator، population و coverage برگردانده شود |
| تعداد محصول | تعداد کلیدهای متمایز چهارگانه | ندارد | پیکربندی | configured/calculated/excluded جداگانه |
| عامل غالب هزینه | بزرگ‌ترین contribution مطلق تجمیع‌شدهٔ مصوب | total مصوب برای share | ریال و درصد | value، share، tie flag و پوشش؛ label حدسی ممنوع |

هر aggregate ناقص `PARTIAL` است. prediction مفقود/نامعتبر صفر نیست. breakdown
و export باید دقیقاً با جمعیت، دامنه، واحد، دوره، پوشش و مجوز KPI مربوطه
reconcile شوند.

## ورودی و زمان

Prediction تعداد برنامه‌ریزی‌شدهٔ همان پیکربندی در بازهٔ دارای شروع و پایان
صریح است. pool و prediction باید هم‌دوره باشند. نرخ FX ریال برای یک واحد ارز
خارجی و تازه‌ترین نرخ **معتبر** در زمان محاسبه با source time/version است.
نبود period/version/as-of در منبع، مجوز ساخت metadata نیست. legacy تنها با
binding صریح مالک به یک planning period پذیرفته می‌شود؛ تاریخ `2026-09-27`
در این حالت owner-assigned baseline است، نه actual source timestamp.

هدف تحلیلی recomputation سمت سرور از ورودی‌های جاری معتبر عمومی/مواد/FX/BOM
است؛ مبلغ ریالی ذخیره‌شدهٔ BOM فقط مرجع تاریخی/مقایسه‌ای است. Usage ناخالص و
شامل loss و recycled material است؛ Loss بر Usage ناخالص اعمال می‌شود؛ Loss و
Recyclability هر دو درصد ۰..۱۰۰ هستند. stock re-entry، مصرف فرضی کل بازیافتی،
carryover ledger و هزینهٔ پردازش بازیافت در BOM وجود ندارد. فرمول مصوب هر ردیف
`Usage × current price × FX × (1-(Loss/100 × Recyclability/100))` است. FX برای
قیمت ریالی ۱ است، stored Rial در live دخالت ندارد و گردکردن پولی میانی انجام نمی‌شود.

## تخصیص، دقت و اعتبارسنجی

تقسیم pool بر `selling_share_of_category / 100` حفظ می‌شود و به ضرب تبدیل
نمی‌شود. adjusted pool یک‌بار بر مجموع prediction همهٔ محصولات eligible همان
دسته و period تقسیم می‌شود؛ display filter این جمعیت را محدود نمی‌کند. raw pool،
modeled allocation و اختلاف آنها جدا هستند. شناسه‌های شش subfield ذخیره‌شده یعنی `AdministrativeandResearch`،
`Payroll`، `Overhead`، `FinancialCosts`، `Depriciation` (با همین املای ذخیره‌شده)
و `NonOperationalCostsandIncomes` بدون تغییر حفظ می‌شوند؛ label منبع
currency/period/accounting semantics نیست.

محاسبه باید با دقت کافی و گردکردن فقط در presentation انجام شود؛ Decimal بدون
آزمون سازگاری اجازهٔ تغییر مرز حسابداری ندارد. ورودی‌ها در ingestion/calculation
اعتبارسنجی می‌شوند. هر ردیف BOM هویت مستقل دارد؛ نام ماده می‌تواند تکرار شود و
contribution ردیف‌های معتبر بدون overwrite جمع می‌شود. malformed row خطای typed است.

golden vectorهای بسته‌شده در [دروازه‌های مالک](dashboard-owner-approval-gates.md)
و پیاده‌سازی PR-05 ثبت شده‌اند.
