# PR-05 — موتور مشترک هزینه

## قرارداد اجرایی

`utils.costing_engine.CostInputLoader` پس از resolve شناسهٔ canonical با
`FactoryService`، operational key را فقط برای مسیرهای `Data/Factories` مصرف
می‌کند. فایل‌ها در آغاز request خوانده و cache می‌شوند؛ محاسبه هیچ read/write
مخفی ندارد. binding مالک در `instance/costing_period_bindings.json` قرار می‌گیرد؛
فایل example عمداً تاریخ واقعی اختراع نمی‌کند.
برای سازگاری endpoint قدیمی که period نمی‌فرستد، دقیقاً یک binding با
`active: true` به‌صورت owner-controlled انتخاب می‌شود؛ صفر یا چند active خطاست.

`calculate_cost(inputs, overrides=None)` تابع pure و نسخهٔ فرمول آن
`cost-v1-owner-approved-2026-09-27` است. خروجی typed شامل state، واحد، هویت
چهارگانه، period، BOM rows، شش driver، provenance و خطاها است. override فقط
در حافظه اعمال می‌شود.

## تفاوت مصوب legacy → V1

| موضوع | Legacy characterization | V1 مصوب |
|---|---|---|
| BOM | stored `cost_of_material_in_rial` | قیمت جاری و FX جاری با G1؛ stored فقط reference |
| درصد | browser raw multiplication/clamp | تقسیم هر درصد بر ۱۰۰ و reject خارج بازه |
| duplicate | first-index/dict overwrite | row identity مستقل و جمع contributionها |
| pool failure | silent zero | typed missing/invalid state |
| تخصیص pool | pool کامل برای هر محصول | یک‌بار روی prediction کل جمعیت دسته |
| زمان | بدون period | owner binding صریح؛ baseline legacy متمایز از actual |

Product/BOM editor نیز همان G1 را برای preview اجرا می‌کند: هر دو درصد مستقل
در بازهٔ بستهٔ ۰ تا ۱۰۰ اعتبارسنجی و پیش از ضرب بر ۱۰۰ تقسیم می‌شوند. server
در `/save_bom` ورودی‌ها و mapping قیمت/ارز را دوباره اعتبارسنجی و فیلدهای مشتق
تاریخی را refresh می‌کند؛ بنابراین ورودی ناقص به مبلغ ظاهراً معتبر صفر تبدیل
نمی‌شود و `Recyclability > Loss` مجاز است.

آزمون‌های `tests/test_costing_characterization.py` به‌عنوان شاهد توصیفی legacy
حفظ شده‌اند. goldenهای business-approved مستقل در `tests/test_costing_engine.py`
قرار دارند. هیچ دادهٔ production/demo برای این تغییر ویرایش نشده است.

## ریسک‌های باقی‌مانده

- تا زمانی که مالک فایل binding واقعی با start/end را تأمین نکند، endpoint
  برای آن period صادقانه `MISSING_INPUT` می‌دهد.
- منابع legacy ممکن است ردیف ناقص یا mapping ارز مبهم داشته باشند؛ V1 به‌جای
  حدس یا صفر آنها را رد می‌کند.
- BOMهایی که پیش از این اصلاح با درصدهای غیرصفر ذخیره شده‌اند ممکن است در
  `cost_of_material_in_rial` مبلغ صفر نادرست داشته باشند. این فیلد در live V1
  authoritative نیست؛ در نخستین ذخیرهٔ معتبر بعدی refresh می‌شود. مهاجرت یا
  backfill داده‌های production خارج از دامنهٔ PR-05 است.
- UI Dashboard و Sensitivity و KPIهای آنها عمداً در PR-05 پیاده نشده‌اند.
