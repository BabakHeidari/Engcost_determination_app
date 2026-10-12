# PR-08 / DASH-5 — API حساسیت مجاز و غیرماندگار

در نسخه فعلی رابط PR-09 و آزمایش PR-09A فعال‌اند. سخت‌سازی سازگار
[PR-10](pr10-dashboard-release-readiness.md) سقف body فاقد طول/chunked و
محدودیت سخت‌گیرانه‌تر برنامه، envelope nested و خطای typed را بررسی می‌کند.
حدود ۶۴ KiB/۶۴ override/۱۲۸ نویسه و مجوز READ/رداکشن باقی می‌مانند.

این برش پس از ادغام PR-07 / GitHub PR شمارهٔ ۴۲ روی `main` اجرا می‌شود و تنها
registry پارامتر، سرویس سناریو و دو endpoint زیر را اضافه می‌کند:

```text
GET  /api/dashboard/sensitivity/parameters
POST /api/dashboard/sensitivity/scenario
```

فرمول مشترک `cost-v1-owner-approved-2026-09-27`، gateهای G1–G4 و مصوبات
تصمیم‌های `015`، `016` و `017` در
[دفتر تصمیم](dashboard-decision-ledger.md) و
[دروازه‌های مالک](dashboard-owner-approval-gates.md) مبنا هستند. رابط حساسیت
در صفحهٔ داشبورد غیرفعال می‌ماند؛ PR-09 رابط آن را جداگانه اجرا خواهد کرد.
هیچ save/apply، سابقه، اشتراک‌گذاری، سناریوی چندمحصولی/چندکارخانه‌ای، بهینه‌سازی
یا شبیه‌سازی تصادفی در این PR وجود ندارد.

## انتخاب دقیق و قرارداد درخواست نسخهٔ ۱

هر دو endpoint دقیقاً یک کارخانهٔ canonical فعال، یک دسته، یک زیردسته، یک
reference مرکب معتبر محصول و یک **شناسهٔ صریح دورهٔ موجود** می‌پذیرند. مقادیر
`factory`، `category`، `subcategory`، `product` و `period` الزامی‌اند.
`__ALL__`، نبود انتخاب، نام نمایشی محصول به‌جای reference، والد ناسازگار،
reference جعل‌شده و batch رد می‌شوند. reference از API موجود
`/api/dashboard/filter-options` به‌دست می‌آید؛ encoding شناسه مجوز نیست.

`start` و `end` اختیاری‌اند؛ اگر یکی وجود دارد، هر دو باید ISO Gregorian
canonical باشند و دقیقاً با مرز binding همین کارخانه و دوره برابر بمانند.
binding معتبر موجود با وضعیت `SYSTEM_INITIALIZATION` طبق سیاست loader
پذیرفته می‌شود. API دوره، metadata یا binding ایجاد نمی‌کند و تاریخ دلخواه را
به دوره تبدیل نمی‌کند. حذف `period` نیز انتخاب ضمنی دورهٔ فعال ایجاد نمی‌کند.
PR-09 تاریخ را برای کاربر جلالی نمایش/دریافت خواهد کرد؛ API همان تاریخ canonical
را نگه می‌دارد.

GET تنها هفت کلید انتخاب بالا را در query می‌پذیرد. POST همان کلیدها و کلید
الزامی `overrides` را در یک JSON object می‌پذیرد؛ query یا body چندمحصولی و
کلیدهای اضافی، از جمله خط‌مبنای ارسالی کلاینت و mapping دلخواه، مجاز نیستند.
هر عضو overrides دقیقاً چنین شکلی دارد:

```json
{
  "parameter_id": "pool:Payroll",
  "mode": "absolute",
  "value": "30"
}
```

نمونهٔ GET برای fixture نمونه؛ reference باید از گزینه‌های مجاز کارخانهٔ
خود کاربر دریافت شود:

```http
GET /api/dashboard/sensitivity/parameters?factory=factory-canonical&category=category&subcategory=sub&product=WyJsZWdhY3ktZm9sZGVyIiwiY2F0ZWdvcnkiLCJzdWIiLCJBIl0&period=P
```

نمونهٔ POST برای افزایش نسبی قیمت مادهٔ `lead` و تغییر absolute سهم دستهٔ
همان دامنه، با فرض داشتن هر دو grant لازم:

```http
POST /api/dashboard/sensitivity/scenario
Content-Type: application/json
```

```json
{
  "factory": "factory-canonical",
  "category": "category",
  "subcategory": "sub",
  "product": "WyJsZWdhY3ktZm9sZGVyIiwiY2F0ZWdvcnkiLCJzdWIiLCJBIl0",
  "period": "P",
  "overrides": [
    {
      "parameter_id": "material:e3456bc1f4d270f4a9793375",
      "mode": "percent_change",
      "value": "10"
    },
    {
      "parameter_id": "category_share:edb2cd3b74c999af70f0b705",
      "mode": "absolute",
      "value": "25"
    }
  ]
}
```

این شناسه‌ها برای ورودی‌های همین مثال‌اند؛ برنامهٔ کلاینت باید ID پاسخ GET
را استفاده کند و source mapping را از رشتهٔ ID استخراج نکند. سناریوی بدون
override همان بدنه با `"overrides": []` است.

`mode` فقط `absolute` یا `percent_change` است. `value` رشتهٔ Decimal ASCII
canonical است و با grammar زیر تطبیق دارد:

```text
-?(0|[1-9][0-9]*)(\.[0-9]+)?
```

عدد JSON، `null`، boolean، فاصله، رقم فارسی، علامت `+`، اعشار بدون بخش صحیح،
leading zero، exponent، `NaN` و infinity پذیرفته نمی‌شوند. query تکراری، کلید
تکراری JSON، override تکراری و دو شناسهٔ متفاوت با source target مشترک رد
می‌شوند؛ ترتیب overrides تعیین‌کنندهٔ نتیجه نیست.

حدود فنی: body حداکثر ۶۴ KiB، حداکثر ۶۴ override و حداکثر ۱۲۸ نویسه برای هر
رشتهٔ Decimal. این حدود برای پردازش درخواست‌اند و سقف مالی اختراع نمی‌کنند.
مقدارهای انتخاب حداکثر ۲۰۴۸ نویسه و ID پارامتر حداکثر ۲۵۶ نویسه‌اند؛ مانند
قرارداد تحلیل هزینه، فضای ابتدا/انتها و کاراکتر کنترلی در انتخاب پذیرفته
نمی‌شود.

POST قرارداد موجود JSON و session پروژه را حفظ می‌کند. پروژه در این نقطه
framework یا token سراسری CSRF ندارد؛ session موجود `SameSite=Lax` است.
این endpoint middleware یا حفاظت نصب‌شده‌ای را معاف یا غیرفعال نمی‌کند.

## schema پاسخ نسخهٔ ۱

GET و POST envelope مشترک زیر را دارند. همهٔ مبالغ، quantityها، درصدها و
مرزهای عددی domain رشتهٔ Decimal هستند؛ count/boolean/شناسه به نوع خود باقی
می‌مانند. رشته‌ها از `Decimal` با formatting ثابت `f` تولید می‌شوند؛ float
compatibility یا exponent وارد JSON نمی‌شود.

| فیلد | نوع و قرارداد |
|---|---|
| `version` | رشتهٔ `"1"` |
| `formula_version` | رشتهٔ نسخهٔ موتور مشترک |
| `state` | وضعیت صریح درخواست/داده |
| `identity` | `{factory_id, category, subcategory, product}`؛ کارخانه canonical، نه operational key؛ تا resolve معتبر برابر `null` |
| `period` | `{id,start,end}` از binding دقیق؛ تا resolve معتبر برابر `null` |
| `calculated_at` | ISO datetime UTC capture همین درخواست؛ failure پیش از capture برابر `null` |
| `source_lineage` | آرایهٔ provenance مجاز؛ شکل هر عضو در ادامه آمده است |
| `non_persistent` | همیشه `true` |
| `permissions` | `{general_parameters: boolean, factory_parameters: boolean}` پس از capture مجاز؛ parser/access failure برابر `{}` |
| `parameters` | آرایهٔ entryهای registry فقط برای گروه مجاز |
| `unsupported_parameters` | `{parameter_type,reason,message}` و `group` برای exclusion مخصوص گروه؛ توضیح historical غیرحساس مشترک و بقیه فقط برای گروه مجاز |
| `baseline` | result معتبر خط‌مبنا یا result typed با مبالغ `null` در baseline failure؛ failure پیش از capture برابر `null` |
| `scenario` | result معتبر سناریو در POST یا result typed با مبالغ `null` در failure پس از capture؛ GET و failure پیش از baseline معتبر برابر `null` |
| `delta` | `{amount,percentage,percentage_state,unit,direction}` در POST؛ GET/failure برابر `null` |
| `effective_overrides` | آرایهٔ overrideهای normalized مجاز؛ GET/failure برابر `[]` |
| `issues` | آرایهٔ `{state,code,message}` امن فارسی و `identity` در صورت resolve معتبر؛ موفق برابر `[]` |

هر entry در `parameters` این کلیدها را دارد:

| فیلد | قرارداد |
|---|---|
| `parameter_id` | ID پایدار سرور؛ شکل‌ها در جدول پایین |
| `group` | `general_parameters` یا `factory_parameters` |
| `label` | برچسب فارسی؛ نام ورودی کاربر صرفاً متن است |
| `unit` | واحد source معتبر، مانند `USD/kg`، `IRR/USD`، `IRR/period`، `percent`، `product/period` |
| `numeric_type` | رشتهٔ `"decimal"` |
| `baseline_value` | مقدار دقیق snapshot سرور |
| `supported_modes` | `["absolute", "percent_change"]` |
| `domain` | `{minimum,minimum_exclusive,maximum,maximum_exclusive}`؛ مرزهای عددی رشته و maximum بدون سقف برابر `null` |
| `constraints` | `FINITE_DECIMAL`، `VALID_BASELINE_REQUIRED`؛ prediction همچنین `POSITIVE_FULL_CATEGORY_PREDICTION_DENOMINATOR` |
| `applicable`, `editable`, `reason` | برای entry قابل اجرا `true`، `true`، `null`؛ mapping غیرقابل اجرا به‌جای کنترل در `unsupported_parameters` قرار می‌گیرد |
| `effect_state` | `CONNECTED` یا `MATHEMATICAL_ZERO` برای اثر صفر ریاضی اثبات‌شده |
| `effect_context` | `"baseline_inputs_other_parameters_fixed"`؛ اثر فقط با ثابت‌بودن دیگر ورودی‌های خط‌مبنا توصیف می‌شود |
| `scope` | `selected_configuration`، `whole_factory_simulated` یا `selected_category` |
| `period` | همان `{id,start,end}` پذیرفته‌شده |
| `source_reference` | `{source: logical_source_role, record_id: parameter_id}`؛ بدون path/filename/JSON pointer |
| `provenance` | metadata واقعی منبع مطابق شکل زیر |
| `dependencies` | آرایهٔ dependencyهای whitelist سرور مطابق شکل پایین |

IDهای hashشده از SHA-256 UTF-8 و ۲۴ نویسهٔ نخست hex ساخته می‌شوند؛ canonical
source mapping فقط در registry خصوصی سرور قرار دارد:

| نوع | شکل ID |
|---|---|
| ماده | `material:<hash(canonical material)>` |
| ارز | `fx:<hash(canonical currency)>` |
| pool | `pool:<exact pool ID>` |
| سهم | `category_share:<hash(category)>` |
| prediction | `prediction:<hash(full canonical identity JSON)>` |

JSON هویت prediction با ترتیب کلیدهای صعودی، بدون فضای separator و UTF-8
ساخته می‌شود. ID به‌تنهایی تضمین applicability، authorization یا source
freshness نیست و صرفاً باید از registry همین selection دریافت شود.

شکل dependencyها دقیقاً یکی یا چند مورد زیر است؛ row IDs هویت مستقل BOMاند
و به کلاینت اجازهٔ انتخاب coordinate جدید نمی‌دهند:

```text
{kind: "material_unit_prices", row_ids: [row_id, ...]}
{kind: "fx_rates", currency: currency_id, row_ids: [row_id, ...]}
{kind: "factory_pool_amounts", pool_ids: [exact_pool_id, ...]}
{kind: "category_share", category: category_id}
{kind: "product_predictions", identity: identity,
 allocation_population: "full_category_predictions"}
```

`provenance` و هر عضو مجاز `source_lineage` شکل یکسان دارند:

```text
{source: logical_source_role, fingerprint: original_content_fingerprint,
 actual_as_of: ISO_datetime | null,
 owner_assigned_baseline: ISO_date | null,
 business_version: string | null}
```

هیچ کدام از این فیلدها برای override فرضی ساخته یا تغییر داده نمی‌شوند.

`baseline` و `scenario` resultهای صریح زیرند:

| فیلد | قرارداد |
|---|---|
| `state` | `"OK"` برای result معتبر، typed baseline state یا `INVALID_INPUT` / `CALCULATION_ERROR` برای scenario unavailable |
| `unit_cost`, `unit` | Decimal string یا `null` و `"IRR/product"` |
| `projected_cost`, `projected_cost_unit` | Decimal string یا `null` و `"IRR/period"` |
| `projected_cost_scope`, `projected_cost_label` | `"single_configuration"` و برچسب فارسی صریح همین پیکربندی |
| `bom_total`, `driver_total` | جمع‌های مشتق‌شدهٔ دقیق مجاز داشبورد یا `null` در result unavailable |
| `prediction`, `prediction_unit` | فقط با grant کارخانه‌ای: Decimal string یا `null` و `"product/period"`؛ برای دیگران کلیدها حذف می‌شوند |
| `breakdown.bom_components` | آرایهٔ `{row_id,material,live_cost_in_rial}`؛ بدون stored historical amount یا raw price/FX |
| `breakdown.driver_components` | آرایهٔ `{pool_id,per_unit_contribution,product_period_contribution}`؛ با grant کارخانه‌ای همچنین `raw_factory_pool`، `adjusted_category_pool`، `category_prediction_total` و `modeled_minus_raw` |
| `issues` | `[]` برای result معتبر؛ issueهای امن typed برای result unavailable |

`effective_overrides` شامل `{parameter_id,mode,value,baseline_value,final_value,
unit,provenance_state}` است؛ `provenance_state` همیشه
`"HYPOTHETICAL_OVERRIDE"` می‌ماند. `value` Decimal normalized درخواست است؛
حفظ spelling اصلی مقدار ارسالی، مثلاً trailing zeroها، قرارداد این فیلد نیست.
این فهرست با ترتیب canonical ID برمی‌گردد تا ترتیب body نتیجه یا presentation
مقایسه را عوض نکند.

failure مفقود/نامعتبر منبع، هویت و دورهٔ **قبلاً resolveشده**، مجوز فعلی و
lineage واقعی و مجاز captureشده را حفظ می‌کند. مبالغ baseline در این حالت
`null`، breakdownها خالی و scenario/delta برابر `null` می‌مانند؛ این envelope
با خطای parser/access پیش از resolve متفاوت است و baseline معتبر جعل نمی‌کند.

اگر baseline معتبر capture شده ولی normalization/domain/alias بررسی یا محاسبهٔ
سناریو شکست بخورد، baseline معتبر و context/registry مجاز حفظ می‌شوند؛ scenario
با `INVALID_INPUT` یا `CALCULATION_ERROR`، مبالغ `null` و breakdown خالی معرفی
می‌شود. `delta` برابر `null` و `effective_overrides` خالی می‌مانند؛ مقدار یا ID
نامعتبر ارسالی در issue بازتاب نمی‌یابد. top state برای خطای درخواست
`INVALID_REQUEST` و HTTP 400، و برای خطای محاسبه `CALCULATION_ERROR` و HTTP 500
است.

نمونهٔ بخش delta برای golden prediction پایین:

```json
{
  "amount": "-50",
  "percentage": "-50.0",
  "percentage_state": "OK",
  "unit": "IRR/product",
  "direction": "scenario_minus_baseline"
}
```

با baseline صفر، همان schema مقدار `percentage: null` و
`percentage_state: "NOT_APPLICABLE"` دارد. trailing zero در Decimal معتبر
معنای جدید مالی ایجاد نمی‌کند؛ کلاینت نباید برای مقایسه رشته‌ها را به float
تبدیل کند.

## پارامترهای مصوب و دامنهٔ مقدار نهایی

registry متعلق به سرور است؛ parameter ID نه token دسترسی است و نه نام فایل
یا JSON pointer. وابستگی‌ها از ورودی canonical و معتبر همان snapshot ساخته
می‌شوند؛ کلاینت نمی‌تواند field mapping یا source path انتخاب کند.

| گروه | ورودی مصوب V1 | واحد | دامنهٔ مقدار نهایی | dependency |
|---|---|---|---|---|
| `general_parameters` | قیمت مادهٔ applicable در BOM منتخب | ارز قیمت / واحد ثبت‌شدهٔ ماده | `>= 0`؛ اگر همان source نیز FX باشد `> 0` | تمام row IDهای همان ورودی canonical ماده |
| `general_parameters` | FX خارجی applicable | ریال / یک واحد ارز خارجی | `> 0` | تمام ردیف‌های applicable آن ارز |
| `factory_parameters` | هر یک از شش pool خام کل کارخانه | `IRR/period` | `>= 0` | ورودی whole-factory pool در همان دوره |
| `factory_parameters` | سهم دستهٔ منتخب | درصد | `> 0` و `<= 100` | inverse-share همین دسته |
| `factory_parameters` | prediction پیکربندی منتخب | `product/period` | `>= 0`؛ مخرج کامل دسته نیز `> 0` | quantity همین هویت چهارگانه در جمعیت کامل دسته |

هر پارامتر modes `absolute` و `percent_change` را دارد. محدودهٔ بالا روی مقدار
**نهایی normalized** اعمال می‌شود؛ درصد نسبی به‌تنهایی سقف مالی ندارد.

```text
absolute:       final_value = value
percent_change: final_value = baseline_value × (1 + value / 100)
```

همهٔ overrideها مستقلاً نسبت به خط‌مبنای اصلی محاسبه می‌شوند. سهم ۵۰ با
`percent_change = "10"` برابر ۵۵ می‌شود، نه ۶۰؛ percentage point mode نداریم.
کاهش قیمت یا pool مثبت به میزان ۱۰۰٪ می‌تواند صفر معتبر بسازد؛ FX صفر مجاز
نیست. برای قیمت یا pool با خط‌مبنای صفر، تغییر نسبی اثر صفر واقعی دارد؛ این
یک اثر ریاضی معتبر است و به‌معنای dependency شکسته نیست.

`MATHEMATICAL_ZERO` به حالت captureشده با دیگر پارامترها ثابت اشاره دارد؛
override ترکیبی می‌تواند اثر را فعال کند. مثلاً FX برای ماده‌ای با قیمت صفر
به‌تنهایی اثر صفر دارد، ولی همراه با افزایش قیمت ماده می‌تواند contribution
را تغییر دهد. `effect_context` این مرز را صریح نگه می‌دارد.

نام‌های canonical شش pool بدون تصحیح املا عبارت‌اند از:

```text
AdministrativeandResearch
Payroll
Overhead
FinancialCosts
Depriciation
NonOperationalCostsandIncomes
```

این پارامترها **ورودی شبیه‌سازی‌شدهٔ pool کل کارخانه در دوره** هستند؛ مجموع
projected نتیجه فقط مربوط به پیکربندی منتخب است. تغییر pool برای محدودکردن
مخرج به محصول منتخب مجوز نمی‌دهد و raw با modeled به‌اجبار برابر نمی‌شود.

قیمت canonical ماده به همهٔ occurrenceهای آن ماده fan-out می‌شود؛ contribution
و row identity هر ردیف BOM مستقل باقی می‌مانند. FX یک ارز نیز تمام ردیف‌های
applicable آن ارز را پوشش می‌دهد. conversion ریال دقیقاً ۱ و غیرقابل ویرایش
است. قیمت/ارز unused در این BOM به‌عنوان کنترل قابل اجرا عرضه نمی‌شود؛ mapping
مبهم رد می‌شود و هویت source اختصاصی محصول از روی حدس ساخته نمی‌شود.

اگر دو پیکربندی هم‌نام در جمعیت کامل کارخانه، حتی در دو دسته، به یک ردیف
legacy `Product Name` مشترک
prediction وصل شوند، تغییر quantity «فقط منتخب» mapping مستقلی ندارد. مثلاً
دو مسیر `sub-A/P` و `sub-B/P` با یک prediction ذخیره‌شدهٔ `P=10` را نمی‌توان
با همان ردیف source به `30` و `10` تبدیل کرد. چنین prediction control قابل
اجرا نیست و فقط برای کاربر کارخانه‌ای مجاز با دلیل امن
`AMBIGUOUS_PREDICTION_MAPPING` توضیح داده می‌شود؛ اصل تحلیل baseline مطابق
loader موجود باقی می‌ماند.

دو parameter ID که به یک ورودی source مشترک برسند alias هستند. یک override
مجاز به همهٔ dependencyهای همان source fan-out می‌شود؛ درخواست هم‌زمان هر دو
alias با `CONFLICTING_SOURCE_OVERRIDES` رد می‌شود و آخرین مقدار برنده نیست.

پارامترهای unsupported عبارت‌اند از stored historical Rial BOM، مقدارهای
محاسبه‌شدهٔ حسابداری، Usage/Loss/Recyclability، fieldهای arbitrary، پارامتر
FX ریالی، prediction سایر پیکربندی‌ها و item-level V2. سطح item نیازمند mapping
و معناشناسی مصوب است؛ pool-level این PR چنین mapping تازه‌ای اختراع نمی‌کند.
پاسخ `unsupported_parameters` همیشه توضیح غیرحساس
`historical_bom_cost / NOT_A_LIVE_INPUT` دارد؛ با grant عمومی همچنین
`irr_fx / FIXED_IRR_CONVERSION` و با grant کارخانه‌ای
`v2_item_level_parameters / UNAPPROVED_MAPPING` عرضه می‌شوند. exclusion
prediction مبهم نیز فقط برای گروه کارخانه‌ای مجاز است. این توضیح‌ها کنترل
قابل اجرا یا مقادیر source نیستند.

## مجوز و redaction

رجیستری Profile، فعال‌بودن کارخانه و `dashboard:READ` روی همان کارخانه پیش
از lookup عملیاتی بررسی می‌شوند. `login_required` کاربر فعلی را در **هر**
درخواست دوباره بارگذاری می‌کند. علاوه بر آن، resolve/افشای پارامترهای هر گروه
و اجرای override آن گروه با سیاست مرکزی کنترل می‌شود:

| دسترسی کاربر روی کارخانهٔ منتخب | registry | override قابل اجرا | پاسخ عمومی |
|---|---|---|---|
| Dashboard READ فقط | بدون پارامتر قابل ویرایش گروه‌ها | فقط فهرست خالی overrides | نتیجهٔ مشتق‌شدهٔ مجاز داشبورد؛ ورودی محافظت‌شده حذف می‌شود |
| Dashboard READ + general_parameters GLOBAL READ | پارامترهای `general_parameters` | فقط `general_parameters` | input/detail عمومی مجاز؛ input/detail کارخانه‌ای حذف می‌شود |
| Dashboard READ + factory_parameters READ همان کارخانه | پارامترهای `factory_parameters` | فقط `factory_parameters` | input/detail کارخانه‌ای مجاز؛ input/detail عمومی حذف می‌شود |
| Dashboard READ + هر دو گروه | هر دو گروه | هر دو گروه | فیلدهای مجاز هر دو گروه |
| مجوز Dashboard کارخانهٔ دیگر یا کارخانهٔ غیرفعال | 403 پیش از lookup عملیاتی | هیچ | بدون مقادیر عملیاتی |
| `IT_ADMIN` / `FINANCE_ECONOMIC_ADMIN` | implicit privilege سیاست مرکزی | هر دو گروه برای کارخانهٔ فعال | همان whitelist مجاز |

`MODIFY` لازم نیست؛ سناریو write ندارد. داشتن grant عمومی، grant کارخانه‌ای را
الزامی نمی‌کند و بالعکس. داشتن grant کارخانه‌ای برای کارخانهٔ دیگر نیز کافی
نیست. POST registry را با grantهای فعلی دوباره می‌سازد؛ لغو دسترسی پس از GET
با parameter ID قدیمی دور زده نمی‌شود. ID جعل‌شده یا گروه نامجاز در سرور رد
می‌شود.

فقط خروجی‌های مشتق‌شدهٔ قبلاً مجاز داشبورد در فیلدهای مشترک قرار می‌گیرند.
مقادیر ورودی، baseline/final override، provenance و جزئیات dependency/breakdown
گروه‌ها فقط با مجوز همان گروه عرضه می‌شوند. serializer whitelist صریح Decimal
دارد؛ `CostResult.to_dict()` و floatهای compatibility آن در این قرارداد
مصرف نمی‌شوند. هیچ مسیر، filename، exception خام، JSON pointer یا ورودی پنهان
در errors، metadata یا nested/export-capable payload قرار نمی‌گیرد.

## snapshot، محاسبه و freshness

هر درخواست یک `CostInputLoader(read_only=True)` با `module="dashboard"` دارد
و `COSTING_DATA_ROOT` و `COSTING_PERIOD_BINDINGS_FILE` فعلی را رعایت می‌کند.
رجیستری مجاز، binding، population کامل دسته، manifest نصب‌شدهٔ V2 و منابع
لازم در همان درخواست capture می‌شوند. read موفق و ناموفق cache درخواست
دارد؛ baseline و scenario از فایل دوباره resolve نمی‌شوند.

baseline یک‌بار با `calculate_cost` محاسبه می‌شود. overrideهای normalized به
mappingهای مستقل `CostOverrides` تبدیل و scenario با **همان** تابع pure
محاسبه می‌شود. ورودی baseline و mappingهای اصلی mutate نمی‌شوند. prediction
منتخب فقط quantity همان هویت در population کامل دسته را عوض می‌کند؛ prediction
دیگران باقی می‌ماند و مخرج تخصیص و projected همین محصول دوباره محاسبه می‌شوند.

Decimal، context و مرز حسابداری موتور حفظ می‌شوند؛ quantize یا rounding نمایشی
در API نداریم. منبع baseline مفقود/نامعتبر با override تعمیر نمی‌شود و نتیجهٔ
نامعتبر به صفر تبدیل نمی‌شود. snapshot مشترک request مانع mixed baseline
و scenario می‌شود؛ این snapshot تراکنش سراسری فایل‌ها یا تاریخچهٔ منبع نیست.

هیچ source، Profile، BOM، binding، manifest، metadata، مهاجرت، backup، lock یا
cache پایدار نوشته نمی‌شود. سناریو cache میان کاربرها ندارد. تغییر واقعی منبع
پس از capture نباید baseline و scenario همان درخواست را تغییر دهد؛ درخواست
بعدی منابع فعلی را دوباره می‌خواند.

`calculated_at` زمان اجرای واقعی درخواست است؛ `actual_as_of` فقط از منبع،
`owner_assigned_baseline` جدا و fingerprint صرفاً اثرانگشت محتوای اصلی است.
override فرضی timestamp یا fingerprint تازهٔ منبع نمی‌سازد. GET registry تضمین
ثبات منابع تا POST بعدی نیست؛ POST همیشه registry، مقادیر baseline، binding
و مجوزها را تازه resolve می‌کند. PR-09 باید baseline و context **پاسخ POST**
را معتبر بداند و مقدار نمایش‌داده‌شده در GET را snapshot تاریخی یا concurrency
token معرفی نکند.

## مقایسهٔ تک‌پیکربندی

مبلغ delta همواره `scenario - baseline` است؛ درصد unit-cost delta از همان
baseline محاسبه می‌شود. baseline صفر درصد را `null` با وضعیت
`NOT_APPLICABLE` می‌کند؛ signed amount delta همچنان معتبر است. شکست ورودی یا
محاسبه عدد ظاهری صفر نمی‌سازد.

projected cost فقط `unit_cost × corresponding_prediction` همین هویت و همین
دوره است: prediction خط‌مبنا برای baseline و prediction نهایی برای scenario.
این مبلغ total کارخانه، سازمان یا سایر پیکربندی‌ها نیست. فهرست خالی overrides
باید مقادیر baseline/scenario، breakdown و source context یکسان بسازد.

## نتایج HTTP و وضعیت امن

| HTTP | نتیجه |
|---|---|
| 200 | registry یا مقایسهٔ معتبر `OK`؛ صفر واقعی نیز معتبر است |
| 400 | missing/ALL/forged selection، body نامعتبر، ID ناشناخته، duplicate/conflict، mode/Decimal/domain نامعتبر |
| 302 | session نامعتبر؛ redirect ورود یا تغییر گذرواژه مطابق `login_required` موجود |
| 403 | کارخانهٔ غیرفعال، Dashboard نامجاز یا override گروه نامجاز |
| 404 | کارخانهٔ canonical ناشناخته |
| 413 | body بزرگ‌تر از حد فنی |
| 422 | binding یا منبع unavailable/missing/invalid/ambiguous؛ baseline معتبر ساخته نشده است |
| 503 | hierarchy unavailable/invalid |
| 500 | خطای unexpected با issue عمومی فارسی |

Issueها `code`، `state` و پیام امن فارسی دارند؛ متن exception، source path و
جزئیات گروه نامجاز در آنها نیست. خطای دسترسی وضعیت دادهٔ کسب‌وکار محسوب نمی‌شود.

## شاهدهای عددی و نبود write

آزمون‌ها از fixture ایزولهٔ نصب‌شدهٔ V2 و Flask واقعی استفاده می‌کنند؛ startup
یا migration دادهٔ operational واقعی برای تست فعال نمی‌شود. مثال‌های مصوب:

| حالت | baseline | scenario |
|---|---|---|
| دو BOM row همان ماده | contributionهای `100 + 40 = 140` | قیمت `+10%` → `110 + 44 = 154`، دو row ID مستقل |
| prediction با G2؛ BOM صفر، pool `1000`، share `50`، quantityها `10+10` | denominator `20`، unit `100`، projected منتخب `1000` | quantity منتخب `30` و دیگری `10` → denominator `40`، unit `50`، projected منتخب `1500` |
| share روی همان fixture | share `50`، adjusted pool `2000`، unit `100` | share `25` → adjusted pool `4000`، unit `200` |

baseline Decimal با Cost Analysis و مسیر مشترک Cost Calculation برای همان
هویت و دوره مقایسه می‌شود. تست‌ها no-overrides، price/FX/pool/share/prediction،
ترتیب overrideها، alias conflicts، صفرها، domain failures، malformed/forged
requests، missing/ambiguous sources، period mismatch، تمام permission groups و
top roles، لغو مجوز میان GET/POST، redaction nested، concurrency مستقل و تغییر
بیرونی منبع پس از capture را بررسی می‌کنند.

inventory و SHA-256 همهٔ فایل‌های fixture شامل عمومی، BOM، V2/manifest،
prediction، binding و Profile پیش/پس درخواست موفق، ردشده و exception مقایسه
می‌شود؛ فایل اضافه/حذف/تغییر یا artifact مهاجرت/lock/cache مجاز نیست. ورودی‌ها و
mappingهای baseline نیز باید یکسان باقی بمانند.

فرمان‌های اجرا با Python محیط مجازی دارای dependencyهای پروژه:

```bash
python -m pytest tests/test_dashboard_sensitivity.py -q
python -m pytest tests/test_dashboard_cost_analysis.py tests/test_dashboard_readonly_loader.py tests/test_dashboard_period_metadata.py tests/test_costing_engine.py -q
python -m compileall app.py modules utils
git diff --check
```

برای collection مجموعهٔ کامل، Profile startup ابتدا به یک store خالی و ایزوله
هدایت می‌شود تا import `app.py` کارخانهٔ فعال نداشته باشد و migration منبع
واقعی را اجرا نکند. مسیر scratch زیر جزو deliverable یا دادهٔ operational نیست:

```bash
python - <<'PY'
from pathlib import Path
from utils.profile_store import ProfileDataStore
ProfileDataStore(Path.cwd() / "work/pr08-validation/profiles.json").initialize({})
PY
APP_DATA_FILE="$PWD/work/pr08-validation/profiles.json" APP_SECRET_KEY=pr08-isolated-test python -m pytest tests --ignore=tests/test_dashboard_frontend.py -q --junitxml=work/pr08-validation/tests.xml
```

کلید session این فرمان مقدار آزمایشی ثابت است؛ برای اجرای برنامهٔ واقعی
استفاده نمی‌شود. همین فرمان با store ایزوله در checkout بدون تغییر
`main` نیز برای مقایسهٔ failureها اجرا شد.

نتایج اجرای نهایی:

- مجموعهٔ تازهٔ `tests/test_dashboard_sensitivity.py`: **۱۴۹ موفق**، شامل
  goldens عددی، API واقعی، مجوز/redaction، خطاهای contextual، سناریوهای هم‌زمان،
  snapshot و hash/inventory نبود write.
- regressionهای مرتبط موتور هزینه، Dashboard، loader فقط‌خواندنی و دوره:
  **۱۴۷ موفق**.
- مجموعهٔ کامل backend: **۵۶۹ موفق و ۳۱ ناموفق**. همان فرمان و محیط روی
  `main` بدون تغییر با commit `7883971` برابر **۴۲۰ موفق و ۳۱ ناموفق** بود؛
  مقایسهٔ شناسه‌های failure در JUnit دو اجرا دقیقاً یک مجموعهٔ یکسان نشان داد.
  هیچ failure تازه یا حذف‌شده‌ای وجود ندارد و assertion نامرتبط ضعیف نشده است.
- هر **۸۷ فایل و ۲۲ directory** عملیاتی `Data/` پس از مجموعهٔ کامل همان
  inventory و SHA-256 پیش از اجرا را داشتند؛ fixtureها نیز نبود فایل
  اضافه/حذف/تغییر و artifact مهاجرت/lock/cache را بررسی می‌کنند.
- نمونهٔ GET و POST مستند بالا با fixture واقعی و ایزولهٔ Flask هر دو HTTP
  **۲۰۰** دادند؛ hashهای ID، کلیدهای envelope/parameter/result، parse همهٔ
  نمونه‌های JSON و پیوندهای نسبی مستندات بررسی شدند.
- compilation پایتون و `git diff --check` موفق بودند. محیط آزمون شامل
  Flask 3.1.3، pandas 3.0.6، openpyxl 3.1.5 و pytest 9.1.1 بود؛ محدودیت حجم
  مستقل هر درخواست از API `Request.max_content_length` در Flask 3.1 استفاده می‌کند.

تست مرورگر UI در این برش اجرا نشده است؛ رابط حساسیت غیرفعال است و template
و asset رابط موجود تغییر نکرده‌اند. نتایج browser مربوط به PR-07 در
[سند رابط تحلیل](pr07-dashboard-cost-analysis-ui.md) باقی می‌مانند.

## PR-09A compatible visual extension

See [current-data visualization and shared-baseline experiment API](pr09a-dashboard-visual-analytics.md) and the [strict JSON request schema](dashboard-visual-analysis-request.schema.json). The existing endpoint contract remains supported. The extensions add no historical series, stored scenarios or source writes.
