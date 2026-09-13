# لایه تبادل اختیاری اکسل — Phase 11

## مرز معماری

مسیر `GET /api/profile/export.xlsx` فقط برای دو نقش هم‌سطح `IT_ADMIN` و
`FINANCE_ECONOMIC_ADMIN` فعال است. خروجی از یک snapshot معتبر که با read lock سرویس
مرکزی `ProfileDataStore` خوانده شده ساخته می‌شود. فایل اکسل هیچ‌گاه منبع runtime،
registry کارخانه یا مقصد dual-write نیست و تولید آن JSON canonical را تغییر نمی‌دهد.

Import در این فاز **فعال نشده است**. در نتیجه workbook، endpoint آپلود یا مسیر mutation
از اکسل وجود ندارد. هر import آینده باید جداگانه و صریح فعال شود و dry-run اجباری، کنترل
مدیر سطح بالا، validation canonical، قفل، backup، atomic write و audit امن را رعایت کند.

## قرارداد workbook

نسخه `profile-exchange-v1` پنج sheet ثابت دارد:

- `Users`: شناسه پایدار، نام، ایمیل، نقش canonical، عنوان شغلی، وضعیت فعال، timestampهای
  امن، وضعیت کلی گذرواژه و نوع دسترسی. هش/متن گذرواژه و credential صادر نمی‌شود.
- `Factories`: همه کارخانه‌های registry canonical در snapshot، شامل کارخانه‌های ساخته‌شده
  در runtime، با ID/code/name/location/status و timestampهای موجود.
- `AccessGrants`: grantهای صریح USER با `ExplicitAccessLevel` و سطح مؤثر. آرایه خام مجوز
  صادر نمی‌شود. مدیران سطح بالا به‌صورت `IMPLICIT_FULL_ACCESS` در Users مشخص‌اند و دسترسی
  آنها به ردیف‌های تکراری تبدیل نمی‌شود.
- `AuditEvents`: فقط شناسه‌ها، زمان canonical، actor/target/action، factory/module و خلاصه
  allow-listed تغییر صادر می‌شود. label فارسی ماژول در کنار `ModuleId` دقیق قرار دارد.
- `Metadata`: نسخه schema، revision snapshot، زمان UTC تولید، غیرفعال‌بودن import، سیاست
  Desk و هر هفت شناسه واقعی registry را ثبت می‌کند.

شناسه‌های module فقط `cost_calculation`، `dashboard`، `desk`،
`factory_parameters`، `general_parameters`، `product` و `profile` هستند. `auth` داخلی است
و در registry قابل grant یا export قرار نمی‌گیرد.

## Desk و سطح سلسله‌مراتبی

سطح‌ها تنها `NONE`، `READ`، `WRITE` و `MODIFY` هستند. برای USER فعال که Desk صریح ندارد،
یک ردیف توضیحی با `ExplicitAccessLevel=NONE`، `EffectiveAccessLevel=READ` و
`PolicySource=MANDATORY_DESK_MINIMUM` صادر می‌شود. این ردیف policy-derived است و هنگام
export در JSON ذخیره نمی‌شود. grant صریح بالاتر با `PolicySource=EXPLICIT_GRANT` نمایش
داده می‌شود. بنابراین workbook هرگز Desk مؤثر NONE را برای کاربر فعال القا نمی‌کند.

Phase 12 و هیچ رفتار import در این تغییر آغاز نشده است.
