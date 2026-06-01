"""Tests for tools/get_current_date.py — format and date accuracy."""

from datetime import datetime
from unittest.mock import patch

from tools.get_current_date import get_current_date

_DAYS = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}


def test_returns_string():
    assert isinstance(get_current_date(), str)


def test_format_day_comma_date():
    result = get_current_date()
    parts = result.split(", ")
    assert len(parts) == 2, f"Expected 'Weekday, YYYY-MM-DD', got: {result!r}"
    day, date = parts
    assert day in _DAYS, f"Unknown day name: {day!r}"
    assert len(date) == 10 and date[4] == "-" and date[7] == "-", \
        f"Date not in YYYY-MM-DD format: {date!r}"


def test_date_matches_today():
    now = datetime(2026, 5, 20, 12, 0, 0)  # Wednesday
    with patch("tools.get_current_date.datetime") as mock_dt:
        mock_dt.now.return_value = now
        result = get_current_date()
    assert "2026-05-20" in result
    assert "Wednesday" in result


def test_weekday_matches_date():
    result = get_current_date()
    day_name, date_str = result.split(", ")
    parsed = datetime.strptime(date_str, "%Y-%m-%d")
    expected_day = parsed.strftime("%A")
    assert day_name == expected_day
