"""Tests for pure business logic in app.py — no tkinter, no I/O."""
from datetime import date

import pytest

import gui.app as app_module


# ── _nth_weekday_of_month ─────────────────────────────────────────────────────

def test_first_monday_of_january_2026():
    # 2026-01-05 is the first Monday
    result = app_module._nth_weekday_of_month(2026, 1, 0, 1)
    assert result == date(2026, 1, 5)


def test_last_friday_of_january_2026():
    # 2026-01-30 is the last Friday
    result = app_module._nth_weekday_of_month(2026, 1, 4, -1)
    assert result == date(2026, 1, 30)


def test_fifth_occurrence_returns_none_when_not_enough():
    # Most months don't have 5 Mondays
    result = app_module._nth_weekday_of_month(2026, 2, 0, 5)
    assert result is None


def test_second_wednesday():
    # 2026-01-14 is the second Wednesday
    result = app_module._nth_weekday_of_month(2026, 1, 2, 2)
    assert result == date(2026, 1, 14)


# ── _expand_recurrence ────────────────────────────────────────────────────────

def _entry(date_str: str, **rec_kwargs) -> dict:
    rec = {"freq": "daily", "interval": 1, "end_mode": "never"}
    rec.update(rec_kwargs)
    return {"id": "test", "date": date_str, "recurrence": rec}


def test_expand_daily_covers_whole_month():
    entry = _entry("01.01.2026")
    result = app_module._expand_recurrence(entry, 2026, 1)
    assert len(result) == 31


def test_expand_daily_with_interval():
    entry = _entry("01.01.2026", interval=7)
    result = app_module._expand_recurrence(entry, 2026, 1)
    # 01, 08, 15, 22, 29 → 5 occurrences
    assert len(result) == 5


def test_expand_daily_count_limit():
    entry = _entry("01.01.2026", end_mode="count", count=3)
    result = app_module._expand_recurrence(entry, 2026, 1)
    assert len(result) == 3


def test_expand_daily_until_date():
    entry = _entry("01.01.2026", end_mode="until", until="05.01.2026")
    result = app_module._expand_recurrence(entry, 2026, 1)
    assert len(result) == 5


def test_expand_no_recurrence_returns_empty():
    entry = {"id": "x", "date": "01.01.2026"}
    assert app_module._expand_recurrence(entry, 2026, 1) == []


def test_expand_freq_none_returns_empty():
    entry = _entry("01.01.2026", freq="none")
    assert app_module._expand_recurrence(entry, 2026, 1) == []


def test_expand_base_after_month_returns_empty():
    entry = _entry("01.03.2026")
    assert app_module._expand_recurrence(entry, 2026, 1) == []


def test_expand_weekly():
    # Weekly requires explicit weekdays list; "MO" = Monday
    entry = _entry("05.01.2026", freq="weekly", interval=1, weekdays=["MO"])
    result = app_module._expand_recurrence(entry, 2026, 1)
    # Mondays in Jan 2026: 5, 12, 19, 26
    assert len(result) == 4
    assert result[0] == date(2026, 1, 5)


def test_expand_weekly_no_weekdays_returns_empty():
    entry = _entry("05.01.2026", freq="weekly", interval=1)
    assert app_module._expand_recurrence(entry, 2026, 1) == []


def test_expand_monthly():
    entry = _entry("15.01.2026", freq="monthly", interval=1)
    result = app_module._expand_recurrence(entry, 2026, 1)
    assert result == [date(2026, 1, 15)]


def test_expand_monthly_not_in_other_month():
    entry = _entry("15.01.2026", freq="monthly", interval=1)
    result = app_module._expand_recurrence(entry, 2026, 2)
    assert result == [date(2026, 2, 15)]


def test_expand_yearly_matches():
    entry = _entry("10.01.2025", freq="yearly", interval=1)
    result = app_module._expand_recurrence(entry, 2026, 1)
    assert result == [date(2026, 1, 10)]


def test_expand_yearly_no_match_wrong_month():
    entry = _entry("10.03.2025", freq="yearly", interval=1)
    result = app_module._expand_recurrence(entry, 2026, 1)
    assert result == []
