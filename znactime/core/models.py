from dataclasses import dataclass


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
    row_color: str = ""


@dataclass
class MonthStats:
    year: int
    month: str
    overtime: float
