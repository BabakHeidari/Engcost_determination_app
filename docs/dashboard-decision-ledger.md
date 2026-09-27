# دفتر فشردهٔ تصمیم‌های داشبورد

منبع همهٔ ردیف‌ها: **owner review + later conversation clarification**. دامنه
V1 و وابستگی‌ها دقیقاً محدود به متن زیر است؛ «جزئیات باز» تصویب edge case نیست.

| ID | گزینه | قاعده مالک و دامنه مؤثر V1 | وضعیت | وابستگی/جزئیات باز |
|---|---|---|---|---|
| 001 | A | `Final_Production_Cost` کاندید unit cost محصول eligible | APPROVED_WITH_OPEN_DETAIL | اعتبار ورودی؛ G1–G4 |
| 002 | A | مجموع unit×prediction هم‌دوره؛ ناقص فقط «مجموع جزئی» + coverage/excluded | APPROVED_WITH_OPEN_DETAIL | G2، G3 |
| 003 | B | میانگین production-weighted با numerator/denominator/population/coverage | APPROVED_WITH_OPEN_DETAIL | 007، 023، G2/G3 |
| 004 | B | شمار configuration چهارگانه؛ configured/calculated/excluded جدا | APPROVED | 013 |
| 005 | A | بزرگ‌ترین contribution مطلق مصوب؛ value/share/tie؛ بدون label حدسی | APPROVED_WITH_OPEN_DETAIL | 009 و KPI population |
| 006 | A | inverse allocation فعلی با division حفظ شود | APPROVED_WITH_OPEN_DETAIL | تکرار pool تصویب نیست؛ G2 |
| 007 | A | prediction = واحد برنامه‌ریزی پیکربندی در planning period | APPROVED_WITH_OPEN_DETAIL | 023 و G3 |
| 008 | CUSTOM | missing/invalid prediction صفر نیست؛ state و partial coverage | APPROVED | 010 |
| 009 | A | شش ID ذخیره‌شده و common allocation فعلی؛ spelling دقیق حفظ شود | APPROVED_WITH_OPEN_DETAIL | currency/period/accounting metadata مفقود |
| 010 | CUSTOM | شش state صادقانه + aggregate PARTIAL؛ 401/403 access outcome | APPROVED | قرارداد محصول |
| 011 | A | یک factory الزامی؛ no global/all-factory V1 | APPROVED | filter/API scope |
| 012 | CUSTOM | ALL صریح و متمایز از NOT_SELECTED در هر سه سطح؛ raw empty دستور نیست | APPROVED | filter contract |
| 013 | B | identity = factory+category+subcategory+product | APPROVED | configuration ref |
| 014 | B | mixed page admission؛ action-level factory auth؛ only authorized actions | APPROVED | server enforcement |
| 015 | A | حساسیت عمومی: Dashboard READ + general_parameters READ | APPROVED | DASH-5 |
| 016 | A | حساسیت کارخانه: Dashboard READ + same-factory factory_parameters READ | APPROVED | DASH-5 |
| 017 | A | what-if non-persistent و بدون write به source | APPROVED | DASH-5 |
| 018 | A | live on request؛ timestamp/provenance فقط در صورت پشتیبانی | APPROVED_WITH_OPEN_DETAIL | G3؛ timestamp ساختگی ممنوع |
| 019 | A | precision کافی؛ rounding نمایشی؛ Decimal نیازمند compatibility test | APPROVED_WITH_OPEN_DETAIL | accounting boundaries تغییر نکند |
| 020 | B | server recomputation از current معتبر؛ stored BOM فقط historical reference | APPROVED_WITH_OPEN_DETAIL | G1، G4 |
| 021 | A+clarification | مقیاس درصد ۰..۱۰۰ و semantics مصوب؛ بدون stock/carryover/processing charge | APPROVED_WITH_OPEN_DETAIL | عبارت عددی gate است؛ G1 |
| 022 | CUSTOM | boundary validation؛ duplicate بی‌صدا overwrite/sum نشود | APPROVED_WITH_OPEN_DETAIL | row rule؛ G4 |
| 023 | A+clarification | start و end قابل انتخاب؛ pool/prediction هم‌دوره؛ no invented history | APPROVED_WITH_OPEN_DETAIL | G3 |
| 024 | A | breakdown/export با KPI population/scope/unit/coverage/permission reconcile | APPROVED_WITH_OPEN_DETAIL | پس از KPIهای معتبر |

## فرض‌های فنی NOT APPROVED

شکل فعلی فایل، labelها، ترتیب آرایه، رفتار exception، مقدار صفر placeholder و
عبارت browser هیچ‌کدام به‌تنهایی قاعده کسب‌وکار نیستند. encoding reference
مرکب و مرتب‌سازی casefold صرفاً جزئیات read-model این PR هستند.
