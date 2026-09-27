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
نبود period/version/as-of در منبع، مجوز ساخت metadata نیست.

هدف تحلیلی recomputation سمت سرور از ورودی‌های جاری معتبر عمومی/مواد/FX/BOM
است؛ مبلغ ریالی ذخیره‌شدهٔ BOM فقط مرجع تاریخی/مقایسه‌ای است. Usage ناخالص و
شامل loss و recycled material است؛ Loss بر Usage ناخالص اعمال می‌شود؛ Loss و
Recyclability هر دو درصد ۰..۱۰۰ هستند. stock re-entry، مصرف فرضی کل بازیافتی،
carryover ledger و هزینهٔ پردازش بازیافت در BOM وجود ندارد. با این حال عبارت
عددی دقیق تا حل دروازهٔ فرمول تصویب نشده است.

## تخصیص، دقت و اعتبارسنجی

تقسیم فعلی pool بر `selling_share_of_category / 100` برای یک محصول حفظ می‌شود
و به ضرب تبدیل نمی‌شود. این تصویب، تکرار pool مشترک در جمع چند محصول را تصویب
نمی‌کند. شناسه‌های شش subfield ذخیره‌شده یعنی `AdministrativeandResearch`،
`Payroll`، `Overhead`، `FinancialCosts`، `Depriciation` (با همین املای ذخیره‌شده)
و `NonOperationalCostsandIncomes` بدون تغییر حفظ می‌شوند؛ label منبع
currency/period/accounting semantics نیست.

محاسبه باید با دقت کافی و گردکردن فقط در presentation انجام شود؛ Decimal بدون
آزمون سازگاری اجازهٔ تغییر مرز حسابداری ندارد. ورودی‌ها در ingestion/calculation
اعتبارسنجی می‌شوند. duplicate هرگز بی‌صدا overwrite، discard یا sum نمی‌شود و
تا تصویب قاعده، `AMBIGUOUS_INPUT`/پوشش ناقص تولید می‌کند.

جزئیات باز در [دروازه‌های مالک](dashboard-owner-approval-gates.md) ثبت شده‌اند؛
DASH-0 از نظر عددی کامل اعلام نمی‌شود.
