# First-run panel form correction (0.11.1)

Version 0.11.0's private controller returned `Referrer-Policy: no-referrer`.
A real Chromium form POST from `/_local/panel` sent `Origin: null`, so the
controller's exact same-origin check correctly rejected workspace selection,
first-administrator submission and stop with HTTP 403. The workspace path did
not cause this error. The original installed smoke supplied Origin explicitly
through its HTTP helper and only photographed setup; it missed real form clicks.

Version 0.11.1 uses `Referrer-Policy: same-origin`. Normal browser form submissions
retain the loopback origin, and cross-origin referrers remain suppressed. The
loopback address/Host check, exact Origin check, private capability cookie and
CSRF token stay enforced. Missing, null and foreign origins are rejected by
regression tests even when cookie and CSRF are valid.

Native installed acceptance now clicks the shipped workspace, administrator and
stop forms through Playwright, without overriding Origin. It covers both fresh
setup/login and existing workspace/login/stop with external requests blocked;
the native summary records each form's actual origin/status. Version metadata
and installer filenames are advanced to 0.11.1.

## اقدام کاربر

بسته ۰٫۱۱٫۱ را روی نصب قبلی نصب کنید و سپس نشان Engcost را باز کنید.
نصب‌کننده همان نمونه معتبر را متوقف می‌کند و داده، کاربران و کلید نشست را
نگه می‌دارد. اگر به توقف دستی نیاز بود، میان‌بر «توقف» در Start Menu را باز
کنید؛ این میان‌بر به فرم خراب نسخه قبلی وابسته نیست. پوشه workspace یا فایل‌های
Data و instance را برای رفع این خطا حذف نکنید. دوباره مرحله انتخاب فضای کاری
را ادامه دهید؛ برای داده موجود همان پوشه قبلی را انتخاب کنید.

Download links and native validation are recorded in
[installer delivery](pr11-validation.md) and the [Persian guide](offline-installers.md).
