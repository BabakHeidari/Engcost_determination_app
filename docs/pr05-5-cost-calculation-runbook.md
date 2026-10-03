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

## راه‌اندازی خودکار نخستین دوره برای کارخانه جدید

فقط وقتی هیچ رکورد دوره‌ای برای canonical factory وجود ندارد، نخستین درخواست
محاسبه می‌تواند discovery را اجرا کند و یک رکورد `INITIAL` با
`status=ACTIVE`, `active=true` و `approved=true` بسازد. این approval انسانی نیست:
`approved_by` و `approval_type` هر دو `SYSTEM_INITIALIZATION` هستند و زمان واقعی
initialization در `approved_at`/`created_at` ثبت می‌شود. اگر هر دوره‌ای از قبل
وجود داشته باشد، رکورد دیگری ساخته یا فعال نمی‌شود؛ دوره‌های آینده همان lifecycle
کنترل‌شده عادی را دارند.

کشف، تاریخ‌های درج‌شده در material prices، BOMها، پارامترهای کارخانه، prediction
و شش pool را می‌خواند. زودترین تاریخ معتبر start است و evidence شامل نوع منبع،
نام فایل، شناسه فیلد، raw value و confidence می‌ماند. `date_origin=SOURCE_DATE`
یعنی start از منبع آمده است. اگر داده هزینه‌ای معتبر وجود دارد ولی هیچ تاریخ
authoritative ندارد، start روز initialization و
`date_origin=SYSTEM_INITIALIZATION_DATE` است؛ این تاریخ هرگز timestamp تاریخی
منبع معرفی نمی‌شود. end مرز شفاف initialization است
(`end_date_origin=SYSTEM_INITIALIZATION_BOUNDARY`) و برای تاریخ منبع آینده، با
start یکسان می‌شود تا بازه معکوس ساخته نشود. نبود هرگونه داده معتبر، خطای typed
می‌دهد و period خالی نمی‌سازد.

برای dry-run/بازبینی کنسول مورد اعتماد:

```bash
python scripts/initialize_planning_period.py \
  --profile-file instance/app_data.json \
  --binding-file instance/costing_period_bindings.json \
  discover --factory-id CANONICAL_ID --data-root Data
```

`--write` فقط برای ایجاد اولین رکورد استفاده می‌شود. درخواست عادی
`POST /cost/get_cost` همین initialization را در نبود کامل تاریخچه به‌صورت امن
انجام می‌دهد و سپس با loader تازه محاسبه را ادامه می‌دهد. endpoint محافظت‌شده
`POST /cost/planning-period/initial/discover` نیز همین قرارداد را دارد. هیچ user
ID جعلی یا manager approval ثبت نمی‌شود.

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
و active یکتا لازم دارد. اگر رکورد legacy `DRAFT` باشد، تاریخچه از قبل وجود دارد و قانون first-period آن را خودکار فعال نمی‌کند؛ draft جدید نسازید و lifecycle کنترل‌شده موجود را طی کنید.
اگر فقط `start_date`/`end_date` وجود داشته باشد، schema با loader سازگار نیست؛
فیلدهای canonical runtime در قرارداد فعلی `start` و `end` هستند.

### تشخیص تفصیلی منابع

برای مقایسه فهرست `sources` دوره فعال با مسیرهایی که `CostInputLoader` واقعاً
حل می‌کند، فرمان فقط‌خواندنی زیر را اجرا کنید:

```bash
python scripts/diagnose_costing_sources.py --factory-id CANONICAL_ID \
  --category CATEGORY --subcategory SUBCATEGORY --product PRODUCT
```

گزینه‌های هویت محصول برای تشخیص مسیر دقیق BOM هستند؛ بدون آن‌ها، فرمان همه
BOMهای موجود کارخانه را در برابر الگوی مورد انتظار گزارش می‌کند. خروجی شامل
دوره فعال، منابع ثبت‌شده، نام منابع شناخته‌شده loader، منابع resolved و missing
است. برای هر منبع، `expected_location`، وضعیت `AVAILABLE`/`MISSING`، فایل پیدا
شده و علت ثبت می‌شود. این فرمان هیچ منبعی نمی‌سازد، مقدار جایگزین نمی‌گذارد و
binding را تغییر نمی‌دهد. پاسخ `SOURCE_UNAVAILABLE` API نیز همین تشخیص را به
همراه نام منبع گمشده، مسیر مورد انتظار و منابع در دسترس برمی‌گرداند.

### نرمال‌سازی امن منابع legacy

اگر مسیر canonical گم شده باشد، loader فقط یک بار در همان درخواست سرویس مرکزی
`legacy_costing_migration` را اجرا و سپس diagnostic را دوباره محاسبه می‌کند.
تنها نگاشت عددی تأییدشده، ردیف یکتای `Subfield`/`Cost` در
`Factory_Data.json` به فایل همان pool است؛ `Cost` بدون اعمال
`PercentageOfAll` عیناً منتقل می‌شود و صفر صریح نیز یک مقدار معتبر است. فایل
canonical موجود هرگز بازنویسی نمی‌شود. تعارض مقدار canonical و aggregate قدیمی
فقط با وضعیت `CONFLICT` گزارش می‌شود.

برای prediction، سهم دسته یا BOM فاقد مقدار authoritative، سرویس فقط در صورت
شناخته‌شدن هویت محصول/دسته یک ساختار قابل‌ویرایش با مقدار `null` یا ردیف‌های
خالی و `_migration.status=NEEDS_INPUT` می‌سازد. loader این فایل را
calculation-ready نمی‌داند و با `LEGACY_SOURCE_NEEDS_INPUT` متوقف می‌شود؛ Capacity،
`PercentageOfAll` و metadata محصول هرگز به prediction، سهم فروش یا BOM تبدیل
نمی‌شوند. برای material price/FX نیز هیچ نگاشت speculative یا placeholder عددی
وجود ندارد.

ابزار batch به‌طور پیش‌فرض dry run است:

```bash
python scripts/migrate_legacy_costing_sources.py --factory-id CANONICAL_ID
python scripts/migrate_legacy_costing_sources.py --all-factories
```

تنها افزودن `--write` فایل‌ها را ایجاد می‌کند. وضعیت‌های `AVAILABLE`،
`WOULD_CREATE_READY`، `WOULD_CREATE_NEEDS_INPUT`، `CREATED_READY`،
`CREATED_NEEDS_INPUT`، `CONFLICT` و `UNRECOVERABLE` بدون چاپ payload خام گزارش
می‌شوند. همه فایل‌های تولیدشده fingerprint منبع (هرجا منبع واقعی وجود دارد)،
نسخه migration، زمان ایجاد و `business_value_invented=false` دارند. اجرای مجدد
فایل موجود یا `generated_at` آن را تغییر نمی‌دهد و هیچ فایل XLSX یا
`ProductsLater.json` دست‌کاری نمی‌شود.

## قبل و بعد

- **قبل:** انتخاب ردیف دارای operational key به 404 می‌رسید؛ 422 و network هر
  دو پیام Backend می‌گرفتند؛ ورودی غایب ممکن بود صفر نمایش داده شود.
- **بعد:** صفحه فقط محصول مجاز را با canonical ID و label امن می‌سازد، API قبل
  از read مجوز را بررسی می‌کند، و UI status+JSON را نگه می‌دارد. تنها 200/OK با
  عدد finite نتیجه نمایش می‌دهد و پاسخ دیرهنگام انتخاب قبلی نادیده گرفته می‌شود.

تست‌ها تعامل JavaScript را با browser engine واقعی اجرا نمی‌کنند؛ قرارداد HTML/
JS و Flask integration به‌صورت executable بررسی شده، ولی smoke test دستی در
مرورگر deployment پس از ارائه تنظیمات واقعی همچنان لازم است.
