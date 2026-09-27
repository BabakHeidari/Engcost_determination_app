# دفتر فشردهٔ تصمیم‌های داشبورد

منبع همهٔ ردیف‌ها: **owner review + later conversation clarification**. دامنه
V1 و وابستگی‌ها دقیقاً محدود به متن زیر است؛ «جزئیات باز» تصویب edge case نیست.

| ID | گزینه | قاعده مالک و دامنه مؤثر V1 | وضعیت | وابستگی/جزئیات باز |
|---|---|---|---|---|
| 001 | A | `Final_Production_Cost` هزینهٔ واحد محصول eligible طبق فرمول V1 مصوب | APPROVED | اعتبار ورودی typed |
| 002 | A | مجموع unit×prediction هم‌دوره؛ ناقص فقط «مجموع جزئی» + coverage/excluded | APPROVED | G2/G3 در PR-05 تصویب شد |
| 003 | B | میانگین production-weighted با numerator/denominator/population/coverage | APPROVED | جمعیت کامل هم‌دسته و هم‌دوره |
| 004 | B | شمار configuration چهارگانه؛ configured/calculated/excluded جدا | APPROVED | 013 |
| 005 | A | بزرگ‌ترین contribution مطلق مصوب؛ value/share/tie؛ بدون label حدسی | APPROVED_WITH_OPEN_DETAIL | 009 و KPI population |
| 006 | A | inverse allocation با division؛ pool یک‌بار روی کل جمعیت برنامه‌ریزی‌شدهٔ دسته تخصیص می‌یابد | APPROVED | modeled با raw reconcile اجباری نمی‌شود |
| 007 | A | prediction = واحد برنامه‌ریزی پیکربندی در planning period صریح | APPROVED | binding مالک برای legacy الزامی است |
| 008 | CUSTOM | missing/invalid prediction صفر نیست؛ state و partial coverage | APPROVED | 010 |
| 009 | A | شش ID ذخیره‌شده، whole-factory scope و common allocation مصوب؛ spelling دقیق حفظ شود | APPROVED | raw و modeled جدا گزارش شوند |
| 010 | CUSTOM | شش state صادقانه + aggregate PARTIAL؛ 401/403 access outcome | APPROVED | قرارداد محصول |
| 011 | A | یک factory الزامی؛ no global/all-factory V1 | APPROVED | filter/API scope |
| 012 | CUSTOM | ALL صریح و متمایز از NOT_SELECTED در هر سه سطح؛ raw empty دستور نیست | APPROVED | filter contract |
| 013 | B | identity = factory+category+subcategory+product | APPROVED | configuration ref |
| 014 | B | mixed page admission؛ action-level factory auth؛ only authorized actions | APPROVED | server enforcement |
| 015 | A | حساسیت عمومی: Dashboard READ + general_parameters READ | APPROVED | DASH-5 |
| 016 | A | حساسیت کارخانه: Dashboard READ + same-factory factory_parameters READ | APPROVED | DASH-5 |
| 017 | A | what-if non-persistent و بدون write به source | APPROVED | DASH-5 |
| 018 | A | live on request؛ actual timestamp یا owner baseline `2026-09-27` با provenance متمایز | APPROVED | timestamp تاریخی ساختگی ممنوع |
| 019 | A | precision کافی؛ rounding نمایشی؛ Decimal نیازمند compatibility test | APPROVED_WITH_OPEN_DETAIL | accounting boundaries تغییر نکند |
| 020 | B | server recomputation از current معتبر؛ stored BOM فقط historical reference | APPROVED | فرمول live در G1 تصویب شد |
| 021 | A+clarification | `gross × (1-(Loss/100×Recyclability/100))`؛ بدون stock/carryover/processing charge | APPROVED | بدون گردکردن میانی |
| 022 | CUSTOM | هر BOM row هویت مستقل دارد؛ material تکراری مجاز و contribution ردیف‌ها جمع می‌شود | APPROVED | malformed row همچنان خطاست |
| 023 | A+clarification | start/end از binding مالک؛ baseline legacy برابر `2026-09-27` و متمایز از actual date | APPROVED | یک period برای هر binding |
| 024 | A | breakdown/export با KPI population/scope/unit/coverage/permission reconcile | APPROVED_WITH_OPEN_DETAIL | پس از KPIهای معتبر |

## فرض‌های فنی NOT APPROVED

شکل فعلی فایل، labelها، ترتیب آرایه، رفتار exception، مقدار صفر placeholder و
عبارت browser هیچ‌کدام به‌تنهایی قاعده کسب‌وکار نیستند. encoding reference
مرکب و مرتب‌سازی casefold صرفاً جزئیات read-model این PR هستند.
