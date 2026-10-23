"""Deterministic date generation; no database, timezone or locale dependencies."""

from calendar import monthrange
from datetime import date, timedelta

FREQUENCIES = [
    "once",
    "daily",
    "weekly",
    "fortnightly",
    "monthly",
    "bimonthly",
    "quarterly",
    "semiannual",
    "yearly",
    "custom",
]
CALENDAR_CHOICES = [("national", "Nacional"), ("institution", "Nacional e institucional")]
MONTHS = {"monthly": 1, "bimonthly": 2, "quarterly": 3, "semiannual": 6, "yearly": 12}


def business_day(day, holidays):
    return day.weekday() < 5 and day.isoformat() not in holidays


def adjust(day, mode, holidays):
    if mode == "none":
        return day
    step = 1 if mode == "next" else -1
    for _ in range(370):
        if business_day(day, holidays):
            return day
        day += timedelta(days=step)
    raise ValueError("Calendário sem dia útil próximo.")


def month_date(year, month, anchor, rule, holidays):
    last = monthrange(year, month)[1]
    mode = rule["month_mode"]
    if mode == "day":
        return date(year, month, min(rule.get("month_day") or anchor.day, last))
    if mode == "first_day":
        return date(year, month, 1)
    if mode == "last_day":
        return date(year, month, last)
    days = [date(year, month, n) for n in range(1, last + 1)]
    if mode in ["business_day", "last_business_day"]:
        days = [d for d in days if business_day(d, holidays)]
    else:
        days = [d for d in days if d.weekday() == rule["weekday"]]
    index = -1 if mode in ["last_business_day", "last_weekday"] else rule["ordinal"] - 1
    return days[index] if -len(days) <= index < len(days) else None


def scheduled_dates(rule, through, holidays=()):
    """Yield (nominal, adjusted); count includes excluded nominal dates.

    Clamp month days independently (Jan 31 -> Feb 28 -> Mar 31).
    Missing nth weekday/business day skips that period, never spills months.
    """
    start = date.fromisoformat(rule["start"])
    end = min(through, date.fromisoformat(rule["end"]))
    holidays = frozenset(holidays)
    frequency = rule["frequency"]
    current, index, count = start, 0, 0
    if frequency in ["weekly", "fortnightly"]:
        current += timedelta(days=(rule["weekday"] - start.weekday()) % 7)
    while current <= end:
        if frequency in MONTHS:
            absolute = start.year * 12 + start.month - 1 + index * MONTHS[frequency]
            year, month = divmod(absolute, 12)
            if date(year, month + 1, 1) > end:
                break
            current = month_date(year, month + 1, start, rule, holidays)
        if current is not None and start <= current <= end:
            count += 1
            if count > rule["count"]:
                break
            if current.isoformat() not in rule["exceptions"]:
                yield current, adjust(current, rule["adjustment"], holidays)
        if frequency == "once":
            break
        index += 1
        if frequency in MONTHS:
            current = date(year, month + 1, 1)
            continue
        step = {"daily": 1, "weekly": 7, "fortnightly": 14}.get(frequency, rule["interval"])
        if frequency == "custom" and rule["interval_unit"] == "business_days":
            for _ in range(step):
                current += timedelta(days=1)
                current = adjust(current, "next", holidays)
        else:
            current += timedelta(days=step)
