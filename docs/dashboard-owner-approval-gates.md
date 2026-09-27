# دروازه‌های تأیید مالک برای اجرای عددی داشبورد

این چهار checkpoint در تأیید مالک مورخ `2026-09-27` بسته شدند. قواعد زیر
جایگزین وضعیت‌های pending پیشین هستند و مبنای فرمول `cost-v1-owner-approved-2026-09-27` محسوب می‌شوند.

## G1 — عبارت بازمحاسبه BOM

- **وضعیت:** OWNER APPROVED.
- **قاعده:** `gross = Usage × current price × FX` و
  `live = gross × (1 - (Loss/100 × Recyclability/100))`. درصدها باید در
  بازهٔ بستهٔ ۰ تا ۱۰۰ باشند و clamp نمی‌شوند؛ stored Rial تاریخی است.
- **مثال:** Usage=100، Loss=10 و Recyclability=20. تقسیم یا عدم تقسیم درصدها
  بر 100 می‌تواند خروجی‌هایی با چند مرتبه اختلاف بسازد؛ هیچ‌کدام از روی نام
  فیلد انتخاب نمی‌شود.
- **PR متاثر:** PR-05 / نخستین اجرای عددی BOM.
- **golden:** Usage=100، Loss=10، Recyclability=20، price=2 و FX=500,000:
  gross=100,000,000، factor=0.98 و live=98,000,000 ریال؛ stored=777,777 بی‌اثر است.

## G2 — reconciliation pool مشترک چندمحصولی

- **وضعیت:** OWNER APPROVED.
- **قاعده:** هر یک از شش pool کل کارخانه ابتدا inverse-share می‌شود و سپس فقط
  یک‌بار بر مجموع prediction کل جمعیت eligible دسته تقسیم می‌شود؛ filter نمایشی
  مخرج را تغییر نمی‌دهد و raw/modeled/difference جدا هستند.
- **مثال:** pool=1,000، share=50% و دو محصول هرکدام prediction=10؛ legacy به
  هر محصول 200 ریال/واحد می‌دهد و projected sum برابر 4,000 می‌شود، یعنی pool
  توسعه‌یافتهٔ 2,000 برای هر محصول دوباره شمرده می‌شود.
- **PR متاثر:** PR-05 / projected total و aggregation.
- **golden:** pool=1,000، share=50%، predictionهای 10+10: adjusted=2,000،
  unit=100 برای هر محصول، aggregate=2,000 و modeled-minus-raw=+1,000 ریال.

## G3 — اتصال بازه به منابع legacy و FX

- **وضعیت:** OWNER APPROVED.
- **قاعده:** legacy بدون تاریخ فقط از طریق binding صریح به یک period با start/end
  پذیرفته می‌شود. baseline مالک `2026-09-27` است و actual timestamp نیست؛
  content fingerprint فقط trace فنی است.
- **مثال:** کاربر ۱۴۰۵/۰۱/۰۱ تا ۱۴۰۵/۰۳/۳۱ را انتخاب می‌کند، اما prediction=100
  و pool=1,000 هیچ تاریخ ندارند؛ نسبت‌دادن آنها به فصل انتخابی ساختگی است.
- **PR متاثر:** PR-05 و هر trend/period comparison بعدی.
- **golden:** منبع bindشده به P فقط در P قابل استفاده است؛ درخواست Q بدون
  binding وضعیت missing/incomplete می‌گیرد و P ضمنی reuse نمی‌شود.

## G4 — ردیف تکراری ماده در BOM

- **وضعیت:** OWNER APPROVED.
- **قاعده:** material name شناسهٔ ردیف نیست؛ هر ردیف هویت و contribution مستقل
  دارد و ردیف‌های معتبر تکراری حفظ و جمع می‌شوند.
- **مثال:** ردیف‌های «سرب» با مبلغ 100 و 40 به‌جای قاعده‌ای روشن ممکن است 100
  باقی بمانند؛ 140، 40 یا خطا هرکدام نیازمند تصمیم مالک‌اند.
- **PR متاثر:** PR-05 / server-side BOM recomputation.
- **golden:** دو ردیف lead با 100 و 40 جدا بازگردانده و به BOM=140 ریال جمع می‌شوند.
