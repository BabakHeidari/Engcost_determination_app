# PR-06 / DASH-3 — قرارداد API تحلیل هزینه

سخت‌سازی سازگار [PR-10](pr10-dashboard-release-readiness.md) validation پاسخ
و گزینه‌های فیلتر را تکمیل می‌کند؛ خطای `CALCULATION_ERROR` واقعی طبق قرارداد
500 است و ورودی/دوره unavailable همچنان 422 باقی می‌ماند. واحد، جمعیت،
precision و API نسخه ۱ تغییر نمی‌کنند.

`GET /api/cost_analysis` از ورودی‌های واقعی نصب‌شده و همان
`CostInputLoader` و `calculate_cost` مصرف‌شده در Cost Calculation استفاده
می‌کند. این برش شامل سرویس backend، قرارداد پاسخ و آزمون‌های API است؛ تکمیل
صفحه داشبورد، نمودارها و CSV در [PR-07](pr07-dashboard-cost-analysis-ui.md) و
registry/API حساسیت تک‌پیکربندی در [PR-08](pr08-dashboard-sensitivity-api.md)
قرار دارند. قرارداد GET این سند مستقل و بدون تغییر باقی می‌ماند.
فرمول `cost-v1-owner-approved-2026-09-27` و مصوبات G1–G4 تغییر نمی‌کنند.

## درخواست و مجوز

فقط پارامترهای `factory`، `category`، `subcategory`، `product`، `period`،
`start` و `end` پذیرفته می‌شوند. پارامتر تکراری، ناشناخته، خالی، دارای فاصله
در ابتدا/انتها یا کاراکتر کنترلی و مقدار بیش از ۲۰۴۸ کاراکتر رد می‌شود.

`factory` باید یک شناسه canonical و فعال رجیستری باشد. مجوز
`dashboard:READ` دقیقاً روی همان کارخانه پیش از lookup عملیاتی بررسی می‌شود؛
مجوز `product` یا `cost_calculation` لازم نیست. مدیران سطح بالا مطابق سیاست
مرکزی به کارخانه‌های فعال دسترسی دارند. شناسه canonical در تمام identityهای
پاسخ باقی می‌ماند، حتی اگر `operational_key` متفاوت باشد.

هر سه سطح سلسله‌مراتب باید صریح انتخاب شوند: نبود هر سطح `NOT_SELECTED`
است؛ `__ALL__` انتخاب صریح همه اعضای دامنه والد است؛ مقدار عضو فقط در همان
دامنه پذیرفته می‌شود. مقدار `product` یک reference مرکب برگرفته از
`/api/dashboard/filter-options` است، نه نام نمایشی محصول. نام یکسان در دو
مسیر دو پیکربندی مستقل باقی می‌ماند. فایل‌های configuration نسخه دوم و
namespaceهای رزروشده عضو جمعیت محصول نیستند.

نمونه انتخاب همه پیکربندی‌های یک کارخانه در دوره ثبت‌شده:

```http
GET /api/cost_analysis?factory=factory-1&category=__ALL__&subcategory=__ALL__&product=__ALL__&period=P
```

`period` اختیاری است. با حذف آن فقط binding یکتای موجود با
`active: true`، `approved: true` و `status: ACTIVE` پذیرفته می‌شود. شناسه
صریح نیز باید به binding معتبر همین کارخانه برسد. رکورد معتبر
`SYSTEM_INITIALIZATION` پذیرفته می‌شود؛ درخواست تحلیلی چنین رکوردی ایجاد
نمی‌کند. `start` و `end` باید با هم، به شکل ISO Gregorian و دقیقاً برابر
مرزهای binding منتخب باشند. تاریخ دلخواه binding ضمنی نمی‌سازد و منبع دوره
دیگر به‌صورت خودکار reuse نمی‌شود.

## پاسخ نسخه ۱

| فیلد | قرارداد |
|---|---|
| `version` | رشته `"1"` |
| `formula_version` | نسخه فرمول مشترک مصوب |
| `state` | وضعیت تجمیع، انتخاب یا دسترسی |
| `scope` | کارخانه عمومی canonical، انتخاب سه‌سطحی، جمعیت نمایشی و جمعیت تخصیص |
| `period` | `{id,start,end}` از binding معتبر؛ در صورت نبود binding برابر `null` |
| `calculated_at` | زمان اجرای درخواست UTC؛ تاریخ تاریخی منبع نیست |
| `source_lineage` | شناسه منطقی منبع، fingerprint، `actual_as_of`، `owner_assigned_baseline` و `business_version` |
| `coverage` | `configured`، `calculated`، `excluded` و `percentage` برای پیکربندی‌های منتخب |
| `kpis` | شمار تطبیق، مجموع کامل/جزئی، میانگین موزون و وضعیت عامل غالب |
| `breakdowns` | `products`، `drivers` و `factory_pools` با دامنه صریح |
| `arithmetic_reconciliation` | اختلاف فنی ناشی از ترتیب جمع Decimal بین مجموع KPI و contributionهای driver، با واحد `IRR/period` |
| `detail_rows` | یک ردیف مستقل برای هر پیکربندی منتخب، از جمله موارد excluded |
| `issues` | code، state و پیام امن فارسی؛ identity مورد مربوط در صورت وجود |

مبالغ، quantityها، سهم‌ها و درصد پوشش به‌صورت رشته Decimal با context
۲۸ رقم معنادار برمی‌گردند؛ گردکردن پولی میانی یا quantize انجام نمی‌شود.
countها integer و مقدار unavailable برابر `null` است.
شناسه چهارگانه هر ردیف شامل `factory_id`، `category`، `subcategory` و
`product` است. ردیف `OK` شامل `unit_cost` با واحد `IRR/product`،
`prediction`، `projected_cost`، `bom_total`، `bom_components` و
`driver_components` است. ردیف excluded همین identity و state/issue را
نگه می‌دارد و مقدارهای محاسبه‌نشده را `null` می‌دهد.

`source_lineage` مسیر فایل یا متن exception ندارد. زمان واقعی منبع فقط اگر
خود منبع آن را داشته باشد گزارش می‌شود؛ baseline مالک `2026-09-27` از زمان
واقعی و زمان اجرای درخواست جدا است. fingerprint اثبات زمان تاریخی نیست.

## KPI و پوشش

- `matched_configuration_count` تعداد کلیدهای چهارگانه منتخب است و برابر
  `coverage.configured` می‌ماند. calculated و excluded جدا گزارش می‌شوند.
- در پوشش کامل، `projected_total` مجموع `unit_cost × prediction` تمام
  پیکربندی‌های منتخب معتبر و `partial_total` برابر `null` است.
- در پوشش مختلط، state برابر `PARTIAL`، `projected_total` برابر `null` و
  `partial_total` مجموع همان ردیف‌های معتبر با
  `partial_total_label: "مجموع جزئی"` است. دلیل exclusion در ردیف و issues
  موجود است.
- `weighted_average` شامل `value`، `numerator`، `denominator`، واحد،
  population و coverage است. صورت مجموع projected ردیف‌های معتبر و مخرج
  مجموع prediction همان ردیف‌ها است. مخرج صفر مقدار میانگین را unavailable
  و وضعیت آن را `NOT_APPLICABLE` می‌کند.
- با نبود ردیف معتبر، هیچ مجموع یا میانگین عددی ساخته نمی‌شود؛ count واقعی
  حفظ می‌شود. داده معتبر با هزینه صفر همچنان `OK` و مبلغ `"0"` است.
- گروه‌بندی top driver طبق تأیید مالک در `2026-10-10` شامل BOM به‌عنوان
  یک driver و شش pool دقیق ذخیره‌شده است. contributionهای projected هر
  گروه روی همان پیکربندی‌های منتخب معتبر جمع و با بزرگ‌ترین قدر مطلق
  رتبه‌بندی می‌شوند. `value` contribution گروه برنده و `share` درصد آن
  از همان projected total یا partial total است؛ total صفر share را `null`
  می‌کند. `tie` تساوی بیش از یک گروه در قدر مطلق بیشینه و `tied_ids` تمام
  شناسه‌های هم‌رتبه به ترتیب صعودی شناسه را گزارش می‌کند؛ `id` نخستین
  شناسه همین فهرست است. پوشش جزئی همچنان `PARTIAL` و محدود به جمعیت معتبر
  است. مثال BOM=۱۵۰ و بزرگ‌ترین pool=۱۰۰، BOM را برنده می‌کند. این تأیید
  جزئیات ledger 005 را می‌بندد و G1–G4 را تغییر نمی‌دهد.

## breakdown و تخصیص

`breakdowns.products` همان ردیف‌های محاسبه‌شده جمعیت منتخب است.
`breakdowns.drivers` contribution پیش‌بینی‌شده BOM و شش pool را بر همین
جمعیت جمع می‌کند؛ همه breakdownها با همان population، دوره و دامنه KPI
محاسبه می‌شوند. `share` درصد projected total یا partial total و هنگام مجموع
صفر برابر `null` است. به‌علت precision محدود Decimal و تفاوت ترتیب جمع،
برابری آخرین رقم رشته‌های مبلغ تضمین نمی‌شود؛ `arithmetic_reconciliation`
شامل `projected_rows_total`، `driver_components_total`، `difference`
(اولی منهای دومی) و `unit` است و اختلاف فنی KPI total با مجموع driverها را
صریح نگه می‌دارد. برای مثال
`97014.30303030303030303030302` و
`97014.30303030303030303030303` اختلاف `-0.00000000000000000000001`
ریال دارند. هیچ contribution برای حذف این اختلاف تغییر داده نمی‌شود و
این trace فنی tolerance بیزینسی یا تغییر مرز حسابداری نیست.

شناسه‌های pool دقیقاً عبارت‌اند از `AdministrativeandResearch`، `Payroll`،
`Overhead`، `FinancialCosts`، `Depriciation` و
`NonOperationalCostsandIncomes`. هر pool یک مقدار whole-factory دارد و فقط
یک‌بار در `breakdowns.factory_pools` گزارش می‌شود:

| فیلد | دامنه/معنا |
|---|---|
| `raw_total`, `raw_scope` | pool خام کل کارخانه؛ `whole_factory` |
| `modeled_selected_total`, `modeled_selected_scope` | مجموع contributionهای projected منتخب معتبر؛ `selected_calculated_configurations` |
| `selected_minus_raw` | modeled منتخب منهای raw؛ مقایسه دو دامنه صریح |
| `modeled_category_total`, `modeled_category_scope` | مجموع adjusted pool هر دسته گزارش‌شده یک‌بار؛ `full_prediction_population_of_reported_categories` |
| `category_minus_raw` | modeled کامل دسته‌های گزارش‌شده منهای raw |
| `categories` | category، `adjusted_pool` و `prediction_denominator` هر دسته |
| `unit`, `coverage` | `IRR/period` و پوشش جمعیت منتخب |

مخرج هر تخصیص مجموع prediction معتبر کل جمعیت دسته و دوره است و با فیلتر
نمایشی یا exclusion یک BOM تغییر نمی‌کند. prediction ناقص یک عضو دسته
مخرج را نامعلوم می‌کند؛ محاسبه با حذف پنهانی آن عضو ادامه نمی‌یابد. modeled
به raw وادار به reconcile نمی‌شود. raw در تمام ردیف‌ها دوباره جمع نمی‌شود.

golden G2: pool=۱۰۰۰، share=۵۰٪ و predictionهای ۱۰+۱۰، adjusted=۲۰۰۰ و
contribution واحد=۱۰۰. با انتخاب هر دو محصول، modeled منتخب=۲۰۰۰ و اختلاف
با raw=+۱۰۰۰؛ با انتخاب تنها یکی، مخرج همچنان ۲۰، modeled منتخب=۱۰۰۰ و
modeled کامل دسته همچنان ۲۰۰۰ است. G1 مبلغ BOM=۹۸٬۰۰۰٬۰۰۰ ریال و G4
دو contribution مستقل ۱۰۰+۴۰=۱۴۰ ریال را حفظ می‌کنند.

## رفتار فقط‌خواندنی و HTTP

Dashboard یک loader با `read_only=True` و `module="dashboard"` برای هر
درخواست دارد. رجیستری، جمعیت کامل کارخانه، binding، manifest و اسناد ورودی
در snapshot درخواست نگه‌داری می‌شوند؛ read موفق و ناموفق طی همان درخواست
دوباره از فایل متغیر resolve نمی‌شود. فقط configuration canonical نصب‌شده
V2 و منابع bindشده مصرف می‌شوند. manifest باید کامل و متعلق به کارخانه
مجاز باشد. sourceهای `NEEDS_INPUT` یا `INVALID_LEGACY_SOURCE` صفر واقعی
تلقی نمی‌شوند.

تحلیل هیچ configuration، metadata، placeholder، planning period، source یا
cache دائمی ایجاد/ذخیره نمی‌کند. مسیر startup و مهاجرت پیش‌فرض Cost
Calculation موجود حفظ می‌شود؛ اجرای تحلیل آن مسیرها را فراخوانی نمی‌کند.
نبود یا نامعتبر بودن منبع وضعیت typed می‌دهد.

| HTTP | نتیجه |
|---|---|
| 200 | `OK`، `PARTIAL` یا `NO_MATCH` برای دامنه منتخب معتبر |
| 400 | `NOT_SELECTED`، `INVALID_SELECTION` یا `INVALID_REQUEST` |
| 302 | درخواست بدون ورود معتبر؛ redirect ورود طبق `login_required` موجود |
| 403 | کارخانه غیرفعال یا دسترسی نامجاز |
| 404 | کارخانه canonical ناشناخته |
| 422 | ورودی/binding unavailable یا نامعتبر، یا نبود ردیف قابل محاسبه |
| 503 | سلسله‌مراتب در دسترس یا معتبر نیست |
| 500 | `CALCULATION_ERROR` با issue عمومی امن |

`NO_MATCH` یعنی انتخاب کامل و معتبر به پیکربندی نرسیده است؛
`NOT_SELECTED` یعنی انتخاب صریح هنوز کامل نیست. redirect ورود و HTTP 403
وضعیت داده بیزینسی محسوب نمی‌شوند. بررسی نبود write در آزمون‌ها شامل مسیر موفق، منبع
مفقود و خرابی ورودی است؛ startup پیش از import اپلیکیشن به fixture مستقل
هدایت می‌شود.

## PR-09A compatible visual extension

See [current-data visualization and shared-baseline experiment API](pr09a-dashboard-visual-analytics.md) and the [strict JSON request schema](dashboard-visual-analysis-request.schema.json). The existing endpoint contract remains supported. The extensions add no historical series, stored scenarios or source writes.
