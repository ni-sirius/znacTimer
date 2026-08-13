from dataclasses import dataclass
from datetime import date


@dataclass
class DayEntry:
    cw: str
    date: str
    special: str
    start: str
    end: str
    interruption: str
    daily_ot: str = ""
    monthly_balance: str = ""
    row_color: str = ""  # semantic row color key, mapped by the UI
    expected_work_minutes: int | None = None
    revision: int | None = None


@dataclass
class MonthStats:
    year: int
    month: str
    overtime: float


@dataclass(frozen=True)
class BreakRecord:
    public_id: str
    position: int
    start_minute: int
    end_minute: int | None
    revision: int = 1


@dataclass(frozen=True)
class DayRecord:
    work_date: date
    special_day: str
    start_minute: int | None
    end_minute: int | None
    break_duration_minutes: int | None
    breaks: tuple[BreakRecord, ...]
    expected_work_minutes: int
    expected_minutes_overridden: bool
    revision: int
    daily_overtime_minutes: int | None = None
    running_balance_minutes: int | None = None


@dataclass(frozen=True)
class MonthRecord:
    year: int
    month: int
    status: str
    opening_balance_minutes: int
    closing_balance_minutes: int | None
    revision: int
    days: tuple[DayRecord, ...]


@dataclass(frozen=True)
class WorkSchedulePeriod:
    public_id: str
    effective_from: date
    effective_to: date | None
    weekday_minutes: tuple[int, int, int, int, int, int, int]
    revision: int


@dataclass(frozen=True)
class ActiveWorkdayRecord:
    work_date: date
    started_at_utc: str
    revision: int
