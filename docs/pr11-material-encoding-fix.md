# Persian material identity correction (0.11.2)

General Parameters read `material_costs.json` with `open(..., "r")`, using the
host's default encoding. The updater writes UTF-8 and BOM already reads UTF-8.
On a Windows CP1252 default, UTF-8 bytes for `اسید` become `Ø§Ø³ÛŒØ¯`.
The initial save can therefore be correct on disk while a reload displays bad
text; editing that loaded row can persist the garbled name back into the catalog.
BOM uses exact material names as references, so altered strings stop matching.

The fix uses the shared explicit UTF-8 JSON reader, serializes page data through
Jinja `tojson` instead of a raw Python dictionary, and sets edit-input values
through the DOM so quotes/HTML characters cannot truncate names. Stored names,
units, currency codes, prices, IDs and calculation rules are not normalized or
translated. There is no automatic rewrite of existing financial sources.

Regression coverage exercises UTF-8 add/read/edit/BOM-save under a simulated
Windows default decoder, including Persian yeh, ZWNJ, quotes and script delimiters.
All four new cases failed against 0.11.1 and pass after correction. Native installed
acceptance additionally adds a Persian material through the real General Parameters
modal, saves/reloads it, edits its price, reloads again, selects it in BOM, saves
and reopens that BOM. It verifies the exact stored identity and a 150 IRR price / 300
IRR line cost with two units and zero loss/recycling, with external traffic blocked.

## به‌روزرسانی و بررسی داده موجود

۱. بسته ۰٫۱۱٫۲ را روی نصب قبلی نصب کنید و Engcost را دوباره باز کنید. نصب، داده‌ها
و کاربران را حفظ می‌کند. سپس صفحه پارامترهای عمومی را دوباره بارگذاری کنید؛ اگر
نام‌ها درست شدند، فایل اصلی سالم بوده و اصلاح داده لازم نیست.

۲. اگر نامی هنوز مانند `Ø§Ø³ÛŒØ¯` دیده می‌شود، متن خراب قبلاً داخل فایل ذخیره شده
است. ابتدا سامانه را متوقف کنید و از کل `Data` و `instance` پشتیبان بگیرید.
پس از اجرا، همان ردیف ماده را در پارامترهای عمومی **ویرایش** کنید و نام صحیح را
طبق منبع معتبر خود وارد کنید؛ قیمت، واحد و ارز را بررسی و تغییرات را ذخیره کنید.
برای این کار ردیف ماده را حذف و دوباره ایجاد نکنید.

۳. در BOMهای استفاده‌کننده، همان ماده صحیح را از فهرست انتخاب و BOM را ذخیره
کنید. مصرف، ضایعات و بازیافت‌پذیری را حفظ کنید و قیمت/هزینه نمایش‌داده‌شده را
بررسی کنید. نام ماده مرجع تطبیق دقیق است؛ اگر نام خراب در BOM هم ذخیره شده باشد،
صرف اصلاح نام در جدول مواد آن مرجع قدیمی را تغییر نمی‌دهد.

تبدیل حدسی و خودکار روی نام‌ها انجام نمی‌شود؛ این کار ممکن است نام‌های واقعی یا
ارجاع‌های مالی را تغییر دهد. نسخه پشتیبان و بررسی مالک، مرجع اصلاح موارد قبلی است.

Installers, checksums and native results: [delivery report](pr11-validation.md).
