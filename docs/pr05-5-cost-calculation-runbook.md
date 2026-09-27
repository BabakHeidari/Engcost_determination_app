# PR-05.5 — بازیابی گردش کامل محاسبه هزینه

## تشخیص baseline

### A. نقص‌های تأییدشده در کد مخزن

1. کاتالوگ، مقدار operational key را در `Factory` مرورگر می‌گذاشت، در حالی که
   API همان فیلد را canonical ID می‌دانست. این تفاوت فقط در رجیستری‌هایی رخ
   می‌دهد که دو مقدار متفاوت دارند؛ fixture کنترل‌شده `factory-canonical` در
   برابر `legacy-folder` آن را بازتولید کرد.
2. مرورگر تمام پاسخ‌های non-2xx (از جمله 422 typed) و خطای واقعی شبکه را به
   `null` تبدیل و یک پیام Backend نمایش می‌داد. مقدارهای غایب نیز با `?? 0`
   هزینه معتبر صفر نشان داده می‌شدند.
3. خروجی bulk با کلید چهارگانه درست بود، اما کاتالوگ همان شناسه را نمی‌فرستاد؛
   export خطاهای هر محصول را abort می‌کرد و روی مقدارهای ناسازگار `.toFixed()`
   صدا می‌زد.
4. نبود فایل runtime binding ابتدا به خطای عمومی source/file تبدیل می‌شد، نه
   وضعیت عملیاتی روشن «دوره تأیید نشده است».

### B. بازتولید کنترل‌شده

تست Flask با رجیستری، کاتالوگ و همه منابع موقت ثابت می‌کند که operational key
متفاوت اکنون در مرز صفحه به canonical ID نگاشت می‌شود. پاسخ موفق route برابر
`HTTP 200`, `state=OK`, `Final_Production_Cost=98000100` است (BOM برابر
98,000,000 و Payroll برابر 100 ریال/واحد). حذف binding پاسخ `HTTP 422` با
`state=MISSING_INPUT`, `code=PERIOD_NOT_BOUND` و پیام فارسی قابل اقدام می‌دهد.

### C. یافته‌های deployment

به محیط واقعی گزارش‌دهنده دسترسی نبود؛ بنابراین هیچ ادعایی درباره فایل‌ها،
مجوزها یا علت قطعی رخداد در deployment واقعی نداریم.

### D. فرضیه‌های تأییدنشده برای deployment

ممکن است runtime binding نصب نشده باشد، operational key با canonical ID تفاوت
داشته باشد، یا یکی از منابع قیمت/FX/BOM/سهم/prediction/شش pool ناقص باشد. پس از
استقرار، کد typed دقیق مورد واقعی را بدون ساختن عدد صفر مشخص می‌کند.

## تنظیم یک‌باره و قابل ممیزی دوره

فایل واقعی (نه example) به‌طور پیش‌فرض
`instance/costing_period_bindings.json` است. مسیر profile registry واقعی و مسیر
binding را صریح بدهید. شناسه canonical کارخانه همان `id` رکورد کارخانه در
`instance/app_data.json` (یا مسیر `APP_DATA_FILE`) است؛ display name، code و نام
پوشه جایگزین آن نیستند.

ابتدا dry-run اجرا کنید و هر منبع را **صریحاً** تأیید کنید:

```bash
python scripts/manage_costing_bindings.py \
  --profile-file instance/app_data.json \
  --binding-file instance/costing_period_bindings.json \
  --actor-id AUTHORIZED_TOP_LEVEL_USER_ID \
  --factory-id OWNER_CANONICAL_ID --period-id OWNER_PERIOD_ID \
  --start OWNER_START_ISO --end OWNER_END_ISO --active \
  --source materials --source bom --source weights --source predictions \
  --source pool:AdministrativeandResearch --source pool:Payroll \
  --source pool:Overhead --source pool:FinancialCosts \
  --source pool:Depriciation --source pool:NonOperationalCostsandIncomes
```

پس از بازبینی خروجی، همان فرمان را با `--write` اجرا کنید. نوشتن atomic است؛ CLI
وجود canonical factory، تاریخ‌ها، نام منابع و یکتایی active binding را بررسی
می‌کند. برای تغییر active period ابتدا binding قبلی را با ورودی صریح مناسب
غیرفعال کنید؛ ابزار period را از امروز، mtime یا محصول حدس نمی‌زند. فایل runtime
و اطلاعات واقعی مالک نباید commit شوند.

تاریخ `2026-09-27` فقط **owner-assigned legacy baseline** است؛ timestamp واقعی
منبع و start/end دوره نیست. start/end بالا باید مستقیماً توسط مالک ارائه شوند.
در deployment واقعی هنوز این ورودی‌ها لازم‌اند: canonical factory ID، period
ID، start، end، active و فهرست منابعی که مالک برای همان period تأیید کرده است.

## راه‌اندازی نخستین دوره برای کارخانه جدید

اگر کارخانه هنوز هیچ دوره ACTIVE و approved ندارد، ابتدا کشف را به‌صورت dry-run
انجام دهید:

```bash
python scripts/initialize_planning_period.py \
  --profile-file instance/app_data.json \
  --binding-file instance/costing_period_bindings.json \
  discover --factory-id CANONICAL_ID --data-root Data
```

کشف، تاریخ‌های کسب‌وکاری درج‌شده در material prices، BOMهای کارخانه، پارامترهای
کارخانه، prediction و شش pool را بررسی و زودترین تاریخ معتبر را همراه نوع منبع،
نام فایل، شناسه فیلد، زمان کشف و confidence ثبت می‌کند. mtime فایل استفاده
نمی‌شود. تاریخ جلالی ورودی برای storage به ISO canonical تبدیل می‌شود. برای ثبت
پیش‌نویس، پس از بازبینی همان فرمان را با `--write` اجرا کنید.

اگر هیچ تاریخ authoritative در محتوای منابع وجود نداشته باشد، تاریخ جاری فقط با
`baseline_type=SYSTEM_INITIALIZATION_DATE` و
`creation_reason=SYSTEM_INITIALIZATION_DATE` ثبت می‌شود. `source_evidence` خالی
می‌ماند؛ این مقدار timestamp تاریخی، تاریخ ایجاد منبع یا تراکنش کسب‌وکار نیست.

خروجی کشف همیشه `status=DRAFT`, `approved=false`, `active=false` و `end=null`
است و موتور هزینه آن را نمی‌پذیرد. مدیر فعال با نقش موجود `IT_ADMIN` یا
`FINANCE_ECONOMIC_ADMIN` باید end و تمام منابع را صریحاً تأیید کند؛ job title یا
مجوز جدیدی ساخته نشده است:

```bash
python scripts/initialize_planning_period.py \
  --profile-file instance/app_data.json \
  --binding-file instance/costing_period_bindings.json \
  approve --factory-id CANONICAL_ID --actor-id TOP_LEVEL_USER_ID \
  --end OWNER_APPROVED_END_ISO \
  --source materials --source bom --source weights --source predictions \
  --source pool:AdministrativeandResearch --source pool:Payroll \
  --source pool:Overhead --source pool:FinancialCosts \
  --source pool:Depriciation --source pool:NonOperationalCostsandIncomes
```

ابتدا dry-run و سپس با `--write` ثبت کنید. approval رکورد را به
`status=ACTIVE`, `approved=true`, `active=true` تبدیل و actor/time را ثبت می‌کند.
تا پیش از آن `PERIOD_NOT_BOUND` رفتار صحیح است. وجود draft، به‌تنهایی period
پیش‌فرض یا fallback ایجاد نمی‌کند.

در استقرار وب، مسیر ترجیحی و احراز هویت‌شده برای همین عملیات‌ها
`POST /cost/planning-period/initial/discover` با بدنه `{"factory_id":"..."}` و
`POST /cost/planning-period/initial/approve` با بدنه شامل `factory_id`، `end` و
`sources` است. هر دو route نشست معتبر و نقش موجود top-level را الزام می‌کنند؛
actor approval از نشست خوانده می‌شود، نه از بدنه درخواست. CLI فقط برای کنسول
محلیِ مورد اعتماد اپراتور است و همچنان رکورد actor باید نقش فعال IT یا
مالی/اقتصادی داشته باشد.

## راستی‌آزمایی و عیب‌یابی

پس از استقرار فایل، workerهای برنامه را restart کنید (یا مطابق روش deployment
reload کنید) و با نشست مجاز درخواست زیر را بفرستید:

```json
{"Factory":"CANONICAL_ID","Category":"...","Subcategory":"...","Product_Name":"...","Period":"OWNER_PERIOD_ID"}
```

به `POST /cost/get_cost` پاسخ موفق باید 200/OK و identity، period، breakdown،
provenance و `Final_Production_Cost` داشته باشد. نبود `Period` فقط وقتی مجاز است
که دقیقاً یک binding معتبر `active:true` برای کارخانه باشد. `PERIOD_NOT_BOUND`
یعنی دوره نصب/تأیید نشده یا active یکتا نیست؛ `UNBOUND_LEGACY_SOURCE` یعنی نام
منبع در binding تأیید نشده؛ `SOURCE_UNAVAILABLE`/`SOURCE_PARSE_ERROR` یعنی منبع
نصب‌شده غایب/خراب است؛ خطاهای price/FX/prediction/share علت همان ورودی را نشان
می‌دهند. 401/session، 403، 404، 5xx و network در UI وضعیت‌های جدا هستند.

Bulk اکنون `{state, coverage, results}` برمی‌گرداند. در حالت mixed، state برابر
`PARTIAL` است و CSV ردیف‌های موفق را با عدد معتبر و ردیف‌های ناموفق را با عدد
خالی و state/code/message صادر می‌کند؛ این خروجی «جمع کامل کارخانه» نیست.

### تشخیص فقط‌خواندنی binding واقعی

پیش از ساخت یا تغییر دوره، وضعیت runtime را با همان canonical ID ارسال‌شده از
ردیف محصول بررسی کنید:

```bash
python scripts/diagnose_costing_period.py \
  --profile-file "$APP_DATA_FILE" \
  --binding-file instance/costing_period_bindings.json \
  --factory-id CANONICAL_ID_FROM_BROWSER_PAYLOAD
```

فرمان هیچ فایلی را تغییر نمی‌دهد و factory input، canonical resolution، مسیر و
وجود فایل runtime، factory ID ذخیره‌شده در binding، period ID، start/end، status،
active، approved، approval owner و نتیجه هر شرط موتور را گزارش می‌کند. موتور هر
سه شرط `active=true`، `approved=true` و `status=ACTIVE` را همراه start/end معتبر
و active یکتا لازم دارد. اگر رکورد `DRAFT` باشد، discovery فقط پیشنهاد ساخته و
مسیر approval احراز هویت‌شده هنوز باید توسط مدیر مجاز طی شود؛ draft جدید نسازید.
اگر فقط `start_date`/`end_date` وجود داشته باشد، schema با loader سازگار نیست؛
فیلدهای canonical runtime در قرارداد فعلی `start` و `end` هستند.

## قبل و بعد

- **قبل:** انتخاب ردیف دارای operational key به 404 می‌رسید؛ 422 و network هر
  دو پیام Backend می‌گرفتند؛ ورودی غایب ممکن بود صفر نمایش داده شود.
- **بعد:** صفحه فقط محصول مجاز را با canonical ID و label امن می‌سازد، API قبل
  از read مجوز را بررسی می‌کند، و UI status+JSON را نگه می‌دارد. تنها 200/OK با
  عدد finite نتیجه نمایش می‌دهد و پاسخ دیرهنگام انتخاب قبلی نادیده گرفته می‌شود.

تست‌ها تعامل JavaScript را با browser engine واقعی اجرا نمی‌کنند؛ قرارداد HTML/
JS و Flask integration به‌صورت executable بررسی شده، ولی smoke test دستی در
مرورگر deployment پس از ارائه تنظیمات واقعی همچنان لازم است.
