# Phase 12 — سخت‌سازی امنیت، بازیابی و تأیید نهایی

## نتیجه بازبینی امنیتی

- `instance/app_data.json` تنها منبع زنده کاربران، کارخانه‌ها، grantها و audit است؛
  Excel فقط خروجی snapshot و فایل‌های قدیمی فقط ورودی مهاجرت‌اند.
- مسیر پیش‌فرض canonical و backup زیر `instance/` و خارج از `static/` و
  `templates/` است. در production باید `APP_DATA_FILE` به مسیر محافظت‌شده بیرون
  checkout اشاره کند و مجوز پوشه/فایل به حساب سرویس محدود باشد.
- `password_hash` فقط در store وجود دارد. serializer عمومی، Profile، audit و
  Excel آن را حذف می‌کنند. هیچ گذرواژه پیش‌فرض یا credential تولیدی در runtime
  وجود ندارد. artifactهای legacy `auth_data.json` و `auth_data.xlsx` از tracking
  Git حذف و ignore شده‌اند؛ migration input را operator خارج از repository تأمین
  می‌کند.
- همه mutationهای وب actor را از `g.current_user`، یعنی user ID نشست امضاشده،
  می‌گیرند و store دوباره actor و نقش او را زیر قفل کنترل می‌کند. فیلد actor
  ارسالی client پذیرفته نمی‌شود.
- کلید ثابت Flask حذف شده است. production باید `APP_SECRET_KEY` تصادفی، پایدار
  و محرمانه تنظیم کند. نبود آن فقط یک کلید موقت همراه هشدار می‌سازد؛ بنابراین
  نشست‌ها پس از restart معتبر نمی‌مانند. `SESSION_COOKIE_HTTPONLY` و
  `SameSite=Lax` همیشه فعال‌اند و در HTTPS باید `APP_COOKIE_SECURE=true` باشد.
- debug فقط با `FLASK_DEBUG=true` صریح فعال می‌شود. demo فقط با مقدار صریح
  `ENG_COST_DEMO_LOCALE=fa` فعال است و fallback خاموش یا خودکار ندارد.
- پروژه dependency مدیریت CSRF جداگانه ندارد. SameSite=Lax خط مبنای فعلی برای
  درخواست‌های cookie-based است؛ reverse proxy باید Origin/Host نامعتبر را رد
  کند. پیش از exposure اینترنت عمومی، token ضد-CSRF سراسری برای فرم و fetch و
  rate limiting ورود باید افزوده شود. این محدودیت استقرار است، نه ادعای حفاظت
  هم‌سطح سامانه‌های بزرگ identity.

## قرارداد canonical نهایی

سند نسخه ۲ شامل `metadata` و آرایه‌های `users`، `factories` و `audit_events`
است؛ containerهای سازگاری `role_permissions` و `user_permission_overrides` باید
خالی بمانند. user دارای ID پایدار، username/email یکتا و normalized،
`password_hash`، یکی از سه `system_role`، `job_title` توصیفی، active/reset state،
revision/timestamps و `access_grants[]` است. factory دارای ID/code/name یکتا،
display/location/status و operational key اختیاری است. event دارای ID، actor،
target، action و UTC timestamp و فقط metadata امن اختیاری module/factory/change
است. همه timestampهای ذخیره/API canonical هستند و UI آنها را جلالی نمایش می‌دهد.

رجیستری grantable دقیقاً این هفت ID است:

`cost_calculation`, `dashboard`, `desk`, `factory_parameters`,
`general_parameters`, `product`, `profile`.

`auth` داخلی است و در editor، grant، audit module ID یا Excel قرار نمی‌گیرد.
سطوح `NONE < READ < WRITE < MODIFY` به‌ترتیب به `[]`، `[READ]`،
`[READ, WRITE]` و `[READ, WRITE, MODIFY]` serialize می‌شوند. مقدار ناشناخته در
module/scope/factory/level fail closed است. دو نقش `IT_ADMIN` و
`FINANCE_ECONOMIC_ADMIN` peer و دارای full access ضمنی هستند. `USER` برای همه
ماژول‌ها deny است، به‌جز USER فعال که Desk GLOBAL حداقل READ مؤثر دارد. این
baseline row مصنوعی یا audit event نمی‌سازد و widgetهای Desk همچنان باید مجوز
ماژول منبع را جداگانه بررسی کنند.

## بازیابی خرابی

خواندن JSON خراب با خطای روشن متوقف می‌شود و داده خالی/demo جایگزین نمی‌گردد.
برای بازیابی برنامه را از سرویس خارج کنید، از فایل و پوشه backup یک کپی مستقل
بگیرید، سپس اجرا کنید:

```bash
python -m scripts.recover_profile_store /secure/application-data/app_data.json
```

اگر path حذف شود، command از `APP_DATA_FILE` و سپس default توسعه استفاده می‌کند.
command زیر همان قفل بین‌پردازه‌ای backupها را از جدید به قدیم می‌خواند، هر
candidate را کامل validate می‌کند، جدیدترین نمونه معتبر را انتخاب می‌کند، bytes
خراب فعلی را با mode محدود در پوشه `corrupt/` نگه می‌دارد و restore را با temp،
fsync و atomic replace انجام می‌دهد. `metadata.last_recovery` منبع و زمان را ثبت
می‌کند؛ business audit جعلی بدون actor ساخته نمی‌شود. پس از restore، login، شمار
کاربران/کارخانه‌ها، revision و آخرین mutationهای مورد انتظار را بررسی کنید.

## هم‌زمانی، backup و محدودیت استقرار

هر read/write canonical قفل فایل بین‌پردازه‌ای می‌گیرد؛ mutation کامل، uniqueness،
optimistic revision، audit و validation زیر قفل‌اند. فایل temporary پیش از replace
fsync و validate می‌شود، backup معتبر قبل از replace ساخته می‌شود و failure پیش
از replace فایل قبلی را سالم باقی می‌گذارد. timeout با
`APP_DATA_LOCK_TIMEOUT`، تعداد backup با `APP_DATA_BACKUP_LIMIT` و پنجره audit با
`APP_AUDIT_EVENT_LIMIT` تنظیم می‌شود.

این مدل برای تعداد کاربر کم، write کم/متوسط و یک server یا workerهای دقیقاً
هماهنگ روی filesystem محلی مناسب است. برای instanceهای متعدد، write سنگین،
network filesystem با semantics قفل/rename نامطمئن، disaster recovery چندمنطقه‌ای
یا تاریخچه نامحدود مناسب نیست و تضمین transaction/concurrency پایگاه‌داده رابطه‌ای
را ندارد. backupهای bounded جایگزین backup خارج‌سایتی، monitoring، retention
سازمانی و آزمون دوره‌ای restore نیستند.

## اجرای regression نهایی

```bash
APP_SECRET_KEY=test-only-secret python -m pytest -q
python -m compileall app.py modules utils scripts
APP_SECRET_KEY=test-only-secret python - <<'PY'
import app
print(app.app.url_map)
PY
git grep -n -I -E 'WILL BE CHANGED|password == "admin"|app.run\(debug=True\)'
```

suite مجوز، registry دقیق، Desk، 403 HTML/JSON، Visual Access Manager، factory
propagation، audit، Excel، locking/atomicity/recovery، RTL/Jalali و عدم افشای hash
را پوشش می‌دهد. costing formula یا داده عملیاتی در Phase 12 تغییر نکرده است.
