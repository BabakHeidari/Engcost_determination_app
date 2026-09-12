# موجودی یکپارچه‌سازی رجیستری کارخانه — Phase 6.8

این سند نتیجه جست‌وجوی route، service، template، JavaScript، loader، گزارش و
فایل‌های عملیاتی است. هویت کارخانه فقط از `factories[]` در JSON canonical و از
طریق `FactoryService` خوانده می‌شود. فایل‌های قدیمی زیر `Data/Factories` صرفاً
پیکربندی عملیاتی وابسته به `operational_key` هستند و رجیستری هویت نیستند.

| ماژول | فایل/Route | منبع پیشین | هدف | طبقه | مسیر مجوز موجود | نیاز به تغییر | منبع هدف | راه‌اندازی کارخانه جدید | یادداشت |
|---|---|---|---|---|---|---|---|---|---|
| Profile/Admin | `modules/profile/routes.py`، `/profile/profile` | رجیستری به‌همراه اجرای discovery در هر بار | نمایش کاربر/grant و افزودن کارخانه/کاربر | MIXED | مدیران کامل؛ USER با grant | بله | `FactoryService`/store | A | discovery زمان اجرا حذف شد؛ Add User از همان گزینه‌های فعال استفاده می‌کند. |
| Factory Parameters | `modules/factory_parameters/routes.py` | `Overall/factories.json` و نام URL/session | فهرست، پارامتر، زیرحوزه، پیش‌بینی | FACTORY_SCOPED | `factory_parameters` READ/WRITE | بله | `FactoryService` | C | کارخانه بدون فایل عملیاتی نمایش داده می‌شود و حالت «پیکربندی نشده» دارد؛ مقدار کارخانه دیگر قرض گرفته نمی‌شود. |
| Product selection/configuration | `modules/product/routes.py` | metadata پوشه برای کارخانه | فیلتر و ایجاد دسته/زیردسته/محصول | MIXED | `product` READ/WRITE | بله | رجیستری برای هویت؛ metadata فقط روابط موجود | C | هویت محصول در catalog سراسری است ولی انتساب/recipe/capacity کارخانه‌ای و چندکارخانه‌ای است. |
| BOM | `/product/<product_name>`، `/save_bom` | factory ارسالی و path نشست | recipe محصول در کارخانه | FACTORY_SCOPED | `product` READ/WRITE | بله | `FactoryService` | C | factory ID دوباره در read و mutation کنترل می‌شود. |
| Cost Calculation | `modules/cost_calculation/routes.py` | ستون Factory در catalog/payload | انتخاب محصول و محاسبه | FACTORY_SCOPED | `cost_calculation` READ | بله | `FactoryService` | C | کارخانه معتبر ولی بدون input نتیجه کارخانه دیگری نمی‌گیرد؛ فرمول تغییر نکرد. |
| Dashboard/report | `modules/dashboard/routes.py` | سه کارخانه demo ثابت | فیلتر و breakdown | MIXED | shell سراسری؛ فیلتر `dashboard` کارخانه‌ای | بله | `FactoryService` | A | گزینه‌ها canonical هستند؛ نبود داده نتیجه صفر/خالی است. داده نمایشی قدیمی هنوز فقط بدنه نمونه API است و منبع گزینه/هویت نیست. |
| General Parameters | `modules/general_parameters/routes.py` | بدون کارخانه | هزینه مواد مشترک | GLOBAL | `general_parameters` | خیر | ندارد | A | افزودن `factory_id` مدل کسب‌وکار را تحریف می‌کند. |
| Desk/Auth | `modules/desk`، `modules/auth` | بدون کارخانه | پوسته/احراز هویت | GLOBAL | نشست و نقش canonical | خیر | ندارد | A | `job_title` ورودی مجوز نیست. |
| Operational loaders | `utils/load_bom.py`، `load_data.py`، `cost_determiners.py` | مسیر `Data/Factories/<key>` | خواندن input موجود | FACTORY_SCOPED | caller اکنون پیش از فراخوانی کنترل می‌کند | بله در caller | ID canonical سپس `operational_key` | C | این helperها فهرست کارخانه تولید نمی‌کنند. |
| Discovery/import | `utils/factory_registry.py`، script population | اسکن JSON/XLSX/folder | import یک‌باره Phase 6.5A | GLOBAL/OPERATOR | اجرای صریح operator | خیر | merge به store | B فقط import اولیه | workflow runtime نیست و Phase 6.8 آن را بازسازی نمی‌کند. |

## قرارداد و رفتار

- view model انتخاب‌گر فقط `id`، `code` و `name` (و در context لازم location یا
  active) را می‌دهد؛ `operational_key` فقط در backend resolve می‌شود.
- مدیران `IT_ADMIN` و `FINANCE_ECONOMIC_ADMIN` هم‌رتبه‌اند و همه کارخانه‌های
  فعال فعلی و آینده را می‌بینند. USER فقط grant دقیق factory/module/permission را
  می‌بیند. factory ناشناخته، غیرفعال یا غیرمجاز بدون fallback رد می‌شود.
- رجیستری خالی معتبر است و UI پیام «هیچ کارخانه‌ای تعریف نشده است.» می‌دهد.
  انتخاب ضمنی F1، عضو صفر یا نخستین کارخانه وجود ندارد.
- A یعنی بدون initialization؛ B یعنی import ساختاری صریح؛ C یعنی setup صریح
  مدیر پیش از استفاده. هیچ عدد، محصول، عامل هزینه یا تنظیمی برای کارخانه جدید
  اختراع یا از کارخانه دیگری کپی نمی‌شود.

## منابع ثابت باقی‌مانده و ابهام

نام کارخانه‌های تاریخی در نگاشت ترجمه و fixture/demo باقی مانده‌اند؛ اینها منبع
production selector یا authority نیستند. گزارش واقعی تراکنشی برای داشبورد در
repository یافت نشد؛ بنابراین endpoint فعال به‌جای داده ساختگی یا داده کارخانه
دیگر، خروجی صادقانه صفر/خالی می‌دهد. Category/Subcategory نام سراسری قطعی ندارند: ساختار
پوشه نشان می‌دهد رابطه آنها با کارخانه است، درحالی‌که نام‌ها ممکن است تکرار شوند؛
Phase 6.8 این رابطه را به `factory_id` واحد و مصنوعی تبدیل نکرد.

## هم‌ترازی Phase 8.3

شناسه‌های factory-aware رجیستری ماژول عبارت‌اند از `cost_calculation`،
`dashboard` (بخش FACTORY)، `factory_parameters` و `product`. همه از همان
`FactoryService` و رجیستری کارخانه canonical استفاده می‌کنند؛ بنابراین کارخانه
جدید بدون آرایه محلی وارد گزینه‌های مدیر دسترسی می‌شود و هر زوج factory/module
مستقل می‌ماند. شناسه‌های global عبارت‌اند از `desk`، `general_parameters`،
`profile` و بخش GLOBAL ماژول `dashboard`. فهرست کامل در
`docs/module-registry.md` ثبت شده و `auth` grantable نیست.
