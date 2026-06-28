import pytest

from utils.localization import (
    format_jalali_date,
    format_jalali_datetime,
    format_jalali_range,
    gregorian_to_jalali,
    is_jalali_leap_year,
    jalali_month_length,
    jalali_to_gregorian,
    parse_jalali_input,
)


def test_gregorian_to_jalali_display_date_and_datetime():
    assert format_jalali_date("2026-06-28") == "۱۴۰۵/۰۴/۰۷"
    assert format_jalali_datetime("2026-06-28T14:30:00") == "۱۴۰۵/۰۴/۰۷ - ۱۴:۳۰"


def test_jalali_to_gregorian_input_persian_and_latin_digits():
    assert parse_jalali_input("۱۴۰۵/۰۴/۰۷") == "2026-06-28"
    assert parse_jalali_input("1405/04/07 14:30") == "2026-06-28T14:30:00"


def test_leap_year_and_month_length_validation():
    assert is_jalali_leap_year(1403)
    assert jalali_month_length(1403, 12) == 30
    assert jalali_month_length(1404, 12) == 29
    assert jalali_to_gregorian(1403, 12, 30) == (2025, 3, 20)
    with pytest.raises(ValueError):
        jalali_to_gregorian(1404, 12, 30)


def test_null_invalid_and_range_fallbacks():
    assert format_jalali_date(None) == ""
    assert format_jalali_datetime("not-a-date", fallback="—") == "—"
    assert format_jalali_range("2026-06-28", "2026-06-29") == "۱۴۰۵/۰۴/۰۷ تا ۱۴۰۵/۰۴/۰۸"
    with pytest.raises(ValueError):
        parse_jalali_input("۱۴۰۵/۱۳/۰۱")


def test_no_timezone_day_shift_for_naive_iso_values():
    assert gregorian_to_jalali(2026, 3, 20) == (1404, 12, 29)
    assert gregorian_to_jalali(2026, 3, 21) == (1405, 1, 1)
