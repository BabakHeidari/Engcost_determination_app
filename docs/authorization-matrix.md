# ماتریس اعمال مجوز backend — Phase 8

این ماتریس routeهای ثبت‌شده برنامه را در برابر module پایدار، scope و کمینه سطح
لازم فهرست می‌کند. همه ردیف‌ها ابتدا احراز هویت می‌شوند. `FactoryService` هویت
کارخانه فعال و grant دقیق را پیش از خواندن داده عملیاتی کنترل می‌کند؛ هیچ selector
یا وضعیت DOM بخشی از تصمیم امنیتی نیست.

| Route / action | Module | Scope / factory context | Level / rule |
|---|---|---|---|
| `GET /workdesk` | `desk` | GLOBAL | READ |
| `GET /dashboard` | `dashboard` | GLOBAL؛ فهرست factory جداگانه فیلتر می‌شود | READ |
| `GET /api/cost_analysis` بدون factory | `dashboard` | GLOBAL | READ |
| `GET /api/cost_analysis?factory=<id>` | `dashboard` | FACTORY از query | READ |
| `GET /general_parameters/` | `general_parameters` | GLOBAL | READ |
| `POST /save_materials` | `general_parameters` | GLOBAL | MODIFY؛ جدول موجود را ویرایش می‌کند |
| `GET /factory_parameters/` | `factory_parameters` | FACTORY؛ فقط subset مجاز | READ حداقل در یک کارخانه |
| detail/subfield کارخانه | `factory_parameters` | FACTORY از path canonical | READ |
| چهار endpoint `save_*` پارامتر کارخانه | `factory_parameters` | FACTORY از session معتبر متصل به ID و operational key | MODIFY |
| production selection، configuration و product options | `product` | FACTORY؛ فقط subset مجاز | READ حداقل در یک کارخانه |
| `POST /product/<product>` | `product` | FACTORY از form | READ |
| افزودن product/category/subcategory | `product` | FACTORY از JSON body | WRITE (ایجاد رکورد) |
| `POST /save_bom` | `product` | FACTORY از session معتبر recipe | MODIFY (ویرایش BOM موجود) |
| صفحه محاسبه هزینه | `cost_calculation` | FACTORY؛ catalog فقط subset مجاز | READ حداقل در یک کارخانه |
| `POST /cost/get_cost` و `get_costs_bulk` | `cost_calculation` | FACTORY از هر payload item | READ؛ محاسبه/گزارش mutation نیست |
| `GET /profile/profile` | `profile` | GLOBAL | READ؛ USER فقط view model امن خودش را می‌بیند |
| create/edit/reset user | administrative | GLOBAL | فقط نقش سطح بالا؛ grant بی‌اثر است |
| create factory | administrative | GLOBAL | فقط نقش سطح بالا؛ grant بی‌اثر است |
| login/change-password/logout | authentication | GLOBAL | قواعد session/password؛ module grant ندارد |

## قواعد destructive و خطا

در routeهای فعال delete/archive وجود ندارد. افزودن آنها نیازمند mapping صریح
سیاست کسب‌وکار است و صرف نام `MODIFY` مجوز حذف ایجاد نمی‌کند. factory ناشناخته
`404`، factory معتبر ولی غیرفعال/غیرمجاز `403` و context session ناسازگار `400`
می‌دهد. نبود احراز هویت مطابق رفتار موجود به login هدایت می‌شود؛ مجوز ناکافی
هرگز به کارخانه دیگری redirect یا downgrade نمی‌شود.

## سازگاری و مرز فاز

schema و migration تغییر نکرده‌اند و هیچ منبع writable دوم ایجاد نشده است.
قفل، backup، validation و atomic replacement `ProfileDataStore` دست‌نخورده است؛
فرمول هزینه نیز تغییر نکرده است. UX مدیر بصری فاز 7.1 و انتشار پویای کارخانه فاز
6.8 حفظ شده‌اند. Phase 9 در این تغییر آغاز نشده است.
