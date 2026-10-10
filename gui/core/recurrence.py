"""Expansion of recurring calendar entries into concrete dates."""

import calendar as _cal_mod
from datetime import date as _date
from datetime import datetime
from datetime import timedelta as _timedelta

# Weekday codes: index matches Python's date.weekday() (0=Mon … 6=Sun)
_WD_CODES = ["MO", "DI", "MI", "DO", "FR", "SA", "SO"]


def nth_weekday_of_month(year: int, month: int, weekday: int, pos: int):
    """Return the pos-th occurrence (1-based; -1 = last) of weekday in month."""
    _, last_day = _cal_mod.monthrange(year, month)
    days = [_date(year, month, d) for d in range(1, last_day + 1)
            if _date(year, month, d).weekday() == weekday]
    if not days:
        return None
    if pos == -1:
        return days[-1]
    idx = pos - 1
    return days[idx] if 0 <= idx < len(days) else None


def expand_recurrence(data: dict, year: int, month: int) -> list:
    """Return sorted list of date objects for recurring entry within (year, month)."""
    rec = data.get("recurrence")
    if not rec:
        return []
    freq = rec.get("freq", "none")
    if freq == "none":
        return []

    try:
        base = datetime.strptime(data["date"], "%d.%m.%Y").date()
    except (KeyError, ValueError):
        return []

    interval = max(1, int(rec.get("interval", 1)))
    end_mode = rec.get("end_mode", "never")
    max_count = int(rec["count"]) if end_mode == "count" and "count" in rec else None
    end_date = None
    if end_mode == "until" and "until" in rec:
        try:
            end_date = datetime.strptime(rec["until"], "%d.%m.%Y").date()
        except ValueError:
            pass

    _, last_day = _cal_mod.monthrange(year, month)
    month_start = _date(year, month, 1)
    month_end   = _date(year, month, last_day)

    upper = month_end
    if end_date and end_date < upper:
        upper = end_date

    if base > upper:
        return []

    occurrences = []

    if freq == "daily":
        gap = max(0, (month_start - base).days)
        steps_before = gap // interval
        d = base + _timedelta(days=steps_before * interval)
        count = steps_before
        while d <= upper:
            if max_count is not None and count >= max_count:
                break
            if d >= month_start:
                occurrences.append(d)
            count += 1
            d += _timedelta(days=interval)

    elif freq == "weekly":
        weekdays = rec.get("weekdays", [])
        wd_indices = sorted({_WD_CODES.index(wd) for wd in weekdays if wd in _WD_CODES})
        if not wd_indices:
            return []
        week_start = base - _timedelta(days=base.weekday())
        count = 0
        done = False
        while not done and week_start <= upper + _timedelta(days=6):
            for wd_idx in wd_indices:
                d = week_start + _timedelta(days=wd_idx)
                if d < base:
                    continue
                if max_count is not None and count >= max_count:
                    done = True
                    break
                if d > upper:
                    done = True
                    break
                count += 1
                if d >= month_start:
                    occurrences.append(d)
            if not done:
                week_start += _timedelta(weeks=interval)

    elif freq == "monthly":
        mode = rec.get("month_mode", "monthday")
        cur_year, cur_month = base.year, base.month
        count = 0
        while _date(cur_year, cur_month, 1) <= upper:
            if mode == "monthday":
                day = int(rec.get("month_day", base.day))
                _, lday = _cal_mod.monthrange(cur_year, cur_month)
                try:
                    d = _date(cur_year, cur_month, min(day, lday))
                except ValueError:
                    d = None
            else:
                pos     = int(rec.get("month_pos", "1"))
                wd_code = rec.get("month_weekday", _WD_CODES[0])
                wd_idx  = _WD_CODES.index(wd_code) if wd_code in _WD_CODES else 0
                d = nth_weekday_of_month(cur_year, cur_month, wd_idx, pos)

            if d and d >= base:
                if max_count is not None and count >= max_count:
                    break
                count += 1
                if d <= upper and d >= month_start:
                    occurrences.append(d)

            m = cur_month + interval
            cur_year  += (m - 1) // 12
            cur_month  = ((m - 1) % 12) + 1

    elif freq == "yearly":
        cur_year = base.year
        count = 0
        while True:
            try:
                d = base.replace(year=cur_year)
            except ValueError:
                d = base.replace(year=cur_year, day=28)
            if d > upper:
                break
            if d >= base:
                if max_count is not None and count >= max_count:
                    break
                count += 1
                if d >= month_start:
                    occurrences.append(d)
            cur_year += interval

    return sorted(occurrences)

