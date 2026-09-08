"""Stable domain values shared by core, storage, and UI layers."""


DATE_FORMAT = "%d.%m.%Y"
TIME_FORMAT = "%H:%M"

# Legacy CSV uses 00:00 for an absent clock, but the live UI must distinguish
# that historical encoding from a real midnight value.
ZERO_HHMM = "00:00"
UNSET_TIME = "--:--"
ZERO_DURATION = ZERO_HHMM

NORMAL_DAY = "Normal day"
WEEKEND_DAY = "Weekend"
NO_DATA_DAY = "No data"


def is_normal_day(value) -> bool:
    return str(value or "").strip().casefold() in ("", NORMAL_DAY.casefold())


END_OF_DAY = "23:59"
OPEN_END_MARKER = "..."
INTERRUPTION_SEPARATOR = ";"
PERIOD_SEPARATOR = "-"

CALENDAR_WEEK_PREFIX = "CW-"


class DayStatus:
    """Semantic status values calculated for a day row."""

    WEEKEND = "weekend"
    WEEKEND_TODAY = "weekend_today"
    SPECIAL_DAY = "special_day"
    SPECIAL_DAY_TODAY = "special_day_today"
    MISSING_TIMES = "missing_times"
    MISSING_TIMES_TODAY = "missing_times_today"
    VALID_DAY = "valid_day"
    VALID_DAY_TODAY = "valid_day_today"
