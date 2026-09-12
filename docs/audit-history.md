# تاریخچه ممیزی واقعی JSON — Phase 9

## منبع، شکل رویداد و اتمیک‌بودن

`audit_events[]` در همان `instance/app_data.json` منبع یگانه و زنده تاریخچه کسب‌وکار است؛
هیچ پایگاه داده یا فایل writable موازی وجود ندارد. رویدادهای موفق مدیریت کاربر و ایجاد کارخانه
در همان callback تغییر، زیر قفل بین‌پردازه‌ای و پیش از validation، backup و atomic replace افزوده
می‌شوند. در نتیجه شکست validation یا نوشتن، نه تغییر و نه success event را در فایل canonical باقی
نمی‌گذارد. زمان canonical رویداد UTC/ISO است و فقط در UI به جلالی نمایش داده می‌شود.

فیلدهای پایه `id`، `actor_user_id`، `target_type`، `target_id`، `action` و `occurred_at`
هستند. نام‌های شناخته‌شده رویدادهای فازهای قبل هنگام نخستین load زیر همان قفل به نام‌های canonical تبدیل می‌شوند و `details` قدیمی به `changes` انتقال می‌یابد. `factory_id`، `module_id` و `changes` فقط در صورت نیاز اضافه می‌شوند. metadata باید حداقلی
و امن باشد؛ گذرواژه یا هش آن، credential، secret، reset token، session identifier، header
احراز هویت، cookie و request body ذخیره نمی‌شود.

## رویدادها و شناسه‌های ماژول

رویدادهای canonical عبارت‌اند از `USER_CREATED`، `USER_UPDATED`،
`SYSTEM_ROLE_CHANGED`، `JOB_TITLE_CHANGED`، `ACCESS_GRANTS_CHANGED`،
`USER_ACTIVATED`، `USER_DEACTIVATED`، `PASSWORD_CHANGED`،
`PASSWORD_RESET_BY_ADMIN` و producer موجود و یگانه `FACTORY_CREATED`. ورود موفق عمداً audit
نمی‌شود؛ `last_login_at` همچنان داده حساب است. mutationهای عملیاتی دیگری که پیش از این producer
کسب‌وکار نداشتند در این فاز صاحب producer تازه نشده‌اند.

`module_id` فقط یکی از شناسه‌های دقیق `cost_calculation`، `dashboard`، `desk`،
`factory_parameters`، `general_parameters`، `product` و `profile` است. `auth` داخلی است.
برچسب فارسی مستقیماً از رجیستری canonical ماژول خوانده می‌شود.

تغییر grant به‌صورت قطعی بر اساس `(scope_type, factory_id, module_id)` مرتب و با سطح‌های
`NONE`، `READ`، `WRITE` و `MODIFY` خلاصه می‌شود. فقط تفاوت persisted صریح ثبت می‌شود؛ READ
ضمنی Desk نه row می‌سازد و نه تاریخچه مصنوعی. تغییر صریح Desk بالاتر از READ مانند هر grant
دیگر ثبت می‌شود.

## مشاهده، denial و رشد فایل

دو مدیر سطح بالا همه رویدادهای live را می‌بینند. USER فقط رویداد شخصی امن خود را می‌بیند و اگر
رویداد module/factory داشته باشد، server پیش از ساخت view model دسترسی مؤثر همان scope را کنترل
می‌کند. Desk baseline به تنهایی تاریخچه ماژول دیگر را باز نمی‌کند. metadata خام به template داده
نمی‌شود؛ UI تنها label عامل/هدف، action، خلاصه امن و زمان جلالی را می‌گیرد و حداکثر ۱۰۰ رویداد
جدید را نمایش می‌دهد.

render صفحه 403 و denialهای JSON business audit تولید نمی‌کنند. در صورت نیاز، ثبت تلاش امنیتی
باید در server/security logging جداگانه انجام شود و وارد `audit_events` نشود.

پنجره زنده پیش‌فرض ۱۰۰۰ رویداد است و با `APP_AUDIT_EVENT_LIMIT` قابل تنظیم است. پس از mutation،
قدیمی‌ترین رویدادهای مازاد زیر همان قفل حذف و شمارش تجمعی، زمان pruning و limit در
`metadata.audit_retention` ثبت می‌شود؛ بنابراین حذف خاموش نیست. این برنامه archive runtime
نمی‌خواند یا نمی‌نویسد. نگهداری archive، در صورت الزام سازمانی، مسئولیت فرایند محافظت‌شده
خارج از runtime و فقط برای سوابق audit است و هرگز منبع user/factory/access نمی‌شود.

Phase 10 در این تغییر آغاز نشده است.
