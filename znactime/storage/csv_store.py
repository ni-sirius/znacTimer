import calendar
import csv
import os
from datetime import date

from znactime.core.calendar_utils import calendar_week_tag
from znactime.core.models import DayEntry, MonthStats
from znactime.core.time_utils import hhmm_to_hours
from znactime.storage import paths


def _normalized_csv_row(row):
    row_data = list(row)
    if row_data and row_data[0].startswith("CW-"):
        row_data = row_data[1:]
    normalized = list(row_data[:7])
    while len(normalized) < 7:
        normalized.append("")
    return normalized


def _default_entries(year, month):
    days = calendar.monthrange(year, month)[1]
    entries = []

    for day in range(1, days + 1):
        current_date = date(year, month, day)
        date_str = current_date.strftime("%d.%m.%Y")
        entries.append(
            DayEntry(
                cw=calendar_week_tag(date_str),
                date=date_str,
                special="Normal day",
                start="00:00",
                end="00:00",
                interruption="00:00",
            )
        )

    return entries


def _entry_from_csv_row(row):
    csv_row = _normalized_csv_row(row)
    return DayEntry(
        cw=calendar_week_tag(csv_row[0]),
        date=csv_row[0],
        special=csv_row[1],
        start=csv_row[2],
        end=csv_row[3],
        interruption=csv_row[4],
        daily_ot=csv_row[5],
        monthly_balance=csv_row[6],
    )


def _entry_to_csv_row(entry):
    return [
        entry.date,
        entry.special,
        entry.start,
        entry.end,
        entry.interruption,
        entry.daily_ot,
        entry.monthly_balance,
    ]


def load_month(year, month, data_dir=None) -> list[DayEntry]:
    month_file = paths.tmp_month_file(year, month, data_dir=data_dir)
    if not os.path.exists(month_file):
        return _default_entries(year, month)

    with open(month_file, newline="") as f:
        return [_entry_from_csv_row(row) for row in csv.reader(f)]


def save_month(year, month, entries: list[DayEntry], data_dir=None):
    paths.year_dir(year, create=True, data_dir=data_dir)
    with open(paths.tmp_month_file(year, month, data_dir=data_dir), "w", newline="") as f:
        writer = csv.writer(f)
        for entry in entries:
            writer.writerow(_entry_to_csv_row(entry))


def is_month_closed(year, month, data_dir=None):
    return os.path.exists(paths.closed_flag_file(year, month, data_dir=data_dir))


def mark_month_closed(year, month, data_dir=None):
    paths.year_dir(year, create=True, data_dir=data_dir)
    with open(paths.closed_flag_file(year, month, data_dir=data_dir), "w"):
        pass


def get_carry_over(year, month, data_dir=None) -> float:
    prev_year, prev_month = year, month - 1
    if prev_month == 0:
        prev_year, prev_month = year - 1, 12

    if not is_month_closed(prev_year, prev_month, data_dir=data_dir):
        return 0.0

    prev_file = paths.tmp_month_file(prev_year, prev_month, data_dir=data_dir)
    if not os.path.exists(prev_file):
        return 0.0

    try:
        with open(prev_file, newline="") as f:
            rows = list(csv.reader(f))
    except OSError:
        return 0.0

    if not rows:
        return 0.0

    normalized = _normalized_csv_row(rows[-1])
    return hhmm_to_hours(normalized[6])


def append_year_summary(stats: MonthStats, data_dir=None):
    paths.year_dir(stats.year, create=True, data_dir=data_dir)
    summary_file = paths.year_summary_file(stats.year, data_dir=data_dir)
    file_exists = os.path.exists(summary_file)

    with open(summary_file, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Year", "Month", "Overtime"])
        writer.writerow([stats.year, stats.month, f"{stats.overtime:.2f}"])
