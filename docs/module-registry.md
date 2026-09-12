# رجیستری canonical ماژول‌ها — Phase 8.3

## سیاست صریح grantability

رجیستری production در `utils/module_registry.py` صریح است و از پوشه‌های `modules/`
auto-discover نمی‌شود. مجموعه دقیق **Grantable** عبارت است از:

```text
cost_calculation
dashboard
desk
factory_parameters
general_parameters
product
profile
```

ماژول **Internal / not grantable**:

```text
auth
```

`auth` در grant، مدیر دسترسی، کارت کارخانه، export دسترسی یا navigation به‌عنوان
ماژول کاربردی عرضه نمی‌شود. ورود، خروج، تغییر اجباری گذرواژه و ابطال نشست تابع
قواعد مستقل امنیتی هستند.

## metadata، برچسب و scope واقعی

| ID فنی | برچسب موجود فارسی | Scope | سیاست واقعی |
|---|---|---|---|
| `cost_calculation` | محاسبه هزینه | FACTORY | catalog و APIهای محاسبه با کارخانه canonical محدود می‌شوند. |
| `dashboard` | داشبورد | MIXED (GLOBAL + FACTORY) | shell/report کلی grant سراسری دارد؛ هر factory filter grant مستقل همان کارخانه می‌خواهد. |
| `desk` | میز کار | GLOBAL | landing/hub مستقل است و مجوز ماژول دیگر را ایجاد نمی‌کند. |
| `factory_parameters` | پارامترهای کارخانه | FACTORY | فهرست، detail، subfield و mutation با `FactoryService` کنترل می‌شوند. |
| `general_parameters` | پارامترهای عمومی | GLOBAL | جدول مواد مشترک است و factory context ندارد. |
| `product` | پیکربندی محصول | FACTORY | hierarchy، انتساب محصول و BOM در context کارخانه کنترل می‌شوند. |
| `profile` | پروفایل کاربر | GLOBAL | صفحه اختیاری پروفایل grant می‌خواهد؛ API مدیریت حساب همچنان فقط top-level admin است. |

هر ردیف UI دقیقاً یک selector با `NONE`، `READ`، `WRITE` و `MODIFY` دارد و به‌ترتیب
`[]`، `["READ"]`، `["READ", "WRITE"]` و
`["READ", "WRITE", "MODIFY"]` serialize می‌شود. grant غایب برای USER برابر
`NONE` است؛ دو نقش `IT_ADMIN` و `FINANCE_ECONOMIC_ADMIN` بدون grant ذخیره‌شده
`MODIFY` ضمنی دارند.

فایل‌های schema v2 ساخته‌شده در Phase 8 ممکن است همین نام پوشه‌ها را با حروف
بزرگ ذخیره کرده باشند. `ProfileDataStore` این spelling قدیمی را هنگام نخستین
خواندن، زیر قفل انحصاری و همراه backup اتمیک، به ID lowercase همین رجیستری تبدیل
می‌کند و سطح مؤثر و scope را حفظ می‌کند. این مسیر فقط تغییر حالت حروف یکی از هفت
ID واقعی را می‌پذیرد؛ alias و ماژول ناشناخته همچنان رد می‌شوند. در نتیجه حساب‌های
موجود پس از استقرار Phase 8.3 قادر به login می‌مانند و privilege جدیدی نمی‌گیرند.

## route-to-module inventory

| Blueprint / route یا action | ID | Scope | حداقل سطح |
|---|---|---|---|
| `GET /workdesk` | `desk` | GLOBAL | READ |
| `GET /dashboard`، گزارش کلی `GET /api/cost_analysis` | `dashboard` | GLOBAL | READ |
| `GET /api/cost_analysis?factory=<id>` | `dashboard` | FACTORY | READ |
| `GET /general_parameters/` | `general_parameters` | GLOBAL | READ |
| `POST /save_materials` | `general_parameters` | GLOBAL | MODIFY |
| directory/detail/subfield کارخانه | `factory_parameters` | FACTORY | READ |
| endpointهای `save_*` کارخانه | `factory_parameters` | FACTORY | MODIFY |
| selection/configuration/options و صفحه محصول | `product` | FACTORY | READ |
| افزودن product/category/subcategory | `product` | FACTORY | WRITE |
| `POST /save_bom` | `product` | FACTORY | MODIFY |
| صفحه و APIهای تکی/گروهی هزینه | `cost_calculation` | FACTORY | READ |
| `GET /profile/profile` | `profile` | GLOBAL | READ |

APIهای create/edit/reset user و create factory ماژول grantable جداگانه نیستند و با
نقش top-level کنترل می‌شوند. `logout` و تغییر اجباری گذرواژه حتی با
`profile = NONE` در دسترس می‌مانند.

از Phase 8.6، login و پایان تغییر اجباری گذرواژه برای هر کاربر فعال به Desk
redirect می‌شوند، زیرا Desk حداقل READ ضمنی دارد. این سیاست grant ماژول دیگری
نمی‌سازد و احراز هویت یا فعال‌بودن حساب را دور نمی‌زند.

## وابستگی فازهای بعد

Phase 9 باید label رویدادهای access را از همین metadata بگیرد. Phase 10 باید هفت
ID، حذف `auth`، کارت‌ها و selector یگانه را حفظ کند. Phase 11 import/export را با
همین IDها انجام می‌دهد و `auth` را صادر نمی‌کند. Phase 12 exact-set، hierarchy،
factory isolation و direct-route denial را دوباره سخت‌گیرانه بررسی می‌کند.
Phase 9 در Phase 8.3 آغاز نشده است.

## سیاست ویژه `desk` — Phase 8.6

metadata canonical ماژول `desk` دارای `mandatory_access: true` و
`minimum_level: READ` است. برای هر USER فعال و احراز هویت‌شده، نبود grant یا
حالت قدیمی NONE/خالی در سطح مؤثر به READ ارتقا می‌یابد؛ این سطح ضمنی است و در
رکورد کاربران تکثیر نمی‌شود. مدیران سطح بالا مانند قبل MODIFY ضمنی دارند.

Desk فعلی فقط صفحه فرود و مجموعه میان‌بر است و mutation یا عملیات معنادار
WRITE/MODIFY ندارد. مدیر بصری آن را به‌صورت اطلاع‌رسان و غیرقابل حذف نمایش می‌دهد،
Add User نیازی به انتخاب آن ندارد، و sidebar همواره آن را نشان می‌دهد. میان‌برهای
ماژول‌های دیگر در Desk با دسترسی مؤثر همان ماژول فیلتر می‌شوند و Desk READ مجوز
خواندن Dashboard، هزینه، محصول یا داده کارخانه ایجاد نمی‌کند. همه ماژول‌های دیگر
همچنان با grant غایب به NONE می‌رسند. fallback قدیمی Desk=NONE دیگر برای USER
فعال کاربرد ندارد و مقصد ورود معتبر Desk است.

Phaseهای 9 تا 12 و import/export آینده باید تفاوت policy ضمنی با تغییر صریح مدیر
را حفظ کنند، Desk=NONE را حالت مؤثر معتبر ندانند و برای READ پایه رویداد audit
مصنوعی نسازند. Phase 9 در این تغییر آغاز نشده است.
