# Jalali date localization

## Approach and libraries

The application uses a single local conversion layer and does not call external date APIs or remote services.

- Backend helpers live in `utils.localization`.
- Frontend helpers live in `static/js/jalali-date.js` and are loaded by `templates/base.html` before page scripts.
- The implementation uses the standard Julian-day conversion algorithm for Gregorian ⇄ Jalali conversion, keeping the project dependency-free and UTF-8 text-only.

## Canonical/internal policy

Internal storage, JSON keys, API payloads, sorting, calculations, filenames, IDs, form field names, and database-facing values remain in the existing canonical Gregorian/ISO format. The Jalali layer is presentation-boundary only.

Stored timestamps such as `last_modification_date` continue to be created with `Date.toISOString()` or existing Python datetime behavior. Historical records are not rewritten or migrated.

## Converted user-facing areas

- Shared header last-login date display.
- Workdesk last-login date-time display.
- General-parameters last-modification display and save confirmation alert.
- Profile demo work-history timestamps.
- Shared JavaScript date-time clock now uses Persian digits.
- Reusable backend Jinja filters: `jalali_date` and `jalali_datetime`.
- Reusable frontend object: `window.JalaliDate`.

The active dashboard and cost CSV exports currently do not include human-readable date values in rows or headings. Their generated filenames intentionally keep machine-safe Gregorian timestamp components.

## Input conversion flow

When a user-facing Jalali date input is added, it must keep the existing submitted field name and convert the visible Jalali value back to the current canonical Gregorian/ISO value before submitting to routes, fetch payloads, filters, or calculations.

Supported helper examples:

- `parse_jalali_input("۱۴۰۵/۰۴/۰۷")` → `2026-06-28`
- `parse_jalali_input("1405/04/07 14:30")` → `2026-06-28T14:30:00`
- `window.JalaliDate.parseJalaliInput("۱۴۰۵/۰۴/۰۷")` → `2026-06-28`

Invalid Jalali dates raise a Persian validation message, for example month 13 or day 30 in a non-leap Esfand.

## Output examples

- Date only: `2026-06-28` → `۱۴۰۵/۰۴/۰۷`
- Date and time: `2026-06-28T14:30:00` → `۱۴۰۵/۰۴/۰۷ - ۱۴:۳۰`
- Range: `2026-06-28` to `2026-06-29` → `۱۴۰۵/۰۴/۰۷ تا ۱۴۰۵/۰۴/۰۸`

## Timezone policy

No application-wide timezone setting was found. Existing browser-generated ISO timestamps and server-side datetime values are preserved. The Jalali display helpers parse and format the supplied value without imposing a new timezone policy, avoiding broad timestamp shifts or historical rewrites.

Future timezone work should define an explicit application timezone before changing storage or display semantics.

## Reports, charts, and exports

Visible chart labels and tooltips should use the shared Jalali helpers when date data is introduced. Chronological ordering must continue to use canonical Gregorian/ISO values.

Human-readable reports and exports should display Jalali date columns. Machine-readable exports should keep canonical raw date values or add separate display columns rather than replacing raw integration fields.

## Intentionally unchanged technical/raw dates

- Canonical JSON/API fields such as `last_modification_date` stay ISO/Gregorian.
- CSV filenames stay ASCII/Gregorian for filesystem and automation compatibility.
- No database values, historical timestamps, formulas, routes, or API contracts were changed.

## Maintenance rules

1. Use `utils.localization` and `window.JalaliDate`; do not add competing conversion implementations.
2. Display readonly dates with Persian digits in `YYYY/MM/DD` format.
3. Display date-times as `YYYY/MM/DD - HH:mm` with Persian digits.
4. Keep hidden, submitted, and machine-readable values canonical.
5. Accept Persian and Latin digits for Jalali input where manual date entry is supported.
6. Add focused tests for leap years, invalid dates, date-only values, date-times, and timezone non-shift behavior whenever date behavior changes.
