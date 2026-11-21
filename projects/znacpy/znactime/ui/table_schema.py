"""Table-column contract shared by the Qt model and view."""

from enum import IntEnum

from znactime.core.time_utils import hours_to_hhmm, parse_interruption_input


def interruption_tooltip(item, total):
    """Shared period/total explanation for interruption chips in either UI."""
    if not item.get("complete", True) or (item.get("target") or {}).get("action") == "add":
        return None
    period = parse_interruption_input(item.get("text", ""))
    return f"{hours_to_hhmm(period.hours)}/{total}" if period is not None and total else None


class Column(IntEnum):
    DATE = 0
    SPECIAL_DAY = 1
    START = 2
    END = 3
    INTERRUPTION = 4
    DAILY_OVERTIME = 5
    MONTHLY_BALANCE = 6


COLUMNS = (
    "Date",
    "Special day",
    "Start",
    "End",
    "Interruption",
    "Daily",
    "Monthly",
)

ENTRY_FIELDS = (
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
