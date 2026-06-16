import calendar
from datetime import date, datetime


def _parse_date(date_str):
    return datetime.strptime(date_str, "%d.%m.%Y").date()


def is_weekend(date_str):
    return _parse_date(date_str).weekday() >= 5


def calendar_week_tag(date_str):
    parsed_date = _parse_date(date_str)
    return f"CW-{parsed_date.isocalendar().week}"


def build_calendar_week_text(year, month, today=None):
    if today is None:
        today = date.today()

    current_week = today.isocalendar().week
    days_in_month = calendar.monthrange(year, month)[1]
    month_weeks = [
        date(year, month, day).isocalendar().week
        for day in range(1, days_in_month + 1)
    ]
    month_week_start = month_weeks[0]
    month_week_end = month_weeks[-1]
    weeks_in_year = date(year, 12, 28).isocalendar().week

    return (
        f"Calendar week {current_week}, "
        f"This month {month_week_start}-{month_week_end}, "
        f"This year {weeks_in_year}"
    )
