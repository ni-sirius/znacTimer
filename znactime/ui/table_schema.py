"""Table-column contract shared by the Qt model and view."""

from enum import IntEnum


class Column(IntEnum):
    CALENDAR_WEEK = 0
    DATE = 1
    SPECIAL_DAY = 2
    START = 3
    END = 4
    INTERRUPTION = 5
    DAILY_OVERTIME = 6
    MONTHLY_BALANCE = 7


COLUMNS = (
    "CW",
    "Date",
    "Special day",
    "Start",
    "End",
    "Interruption",
    "Daily OT",
    "Monthly",
)

ENTRY_FIELDS = (
    "cw",
    "date",
    "special",
    "start",
    "end",
    "interruption",
    "daily_ot",
    "monthly_balance",
)

EDITABLE_COLUMNS = frozenset(
    {
        Column.SPECIAL_DAY,
        Column.START,
        Column.END,
        Column.INTERRUPTION,
    }
)
TIME_COLUMNS = frozenset({Column.START, Column.END})
CENTERED_COLUMNS = frozenset(
    {
        Column.CALENDAR_WEEK,
        Column.DATE,
        Column.START,
        Column.END,
        Column.INTERRUPTION,
        Column.DAILY_OVERTIME,
        Column.MONTHLY_BALANCE,
    }
)
BADGE_COLUMNS = frozenset(
    {
        Column.SPECIAL_DAY,
        Column.START,
        Column.END,
        Column.INTERRUPTION,
    }
)
