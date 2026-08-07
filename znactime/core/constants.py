"""Stable domain values shared by core, storage, and UI layers."""


DATE_FORMAT = "%d.%m.%Y"
TIME_FORMAT = "%H:%M"

# The persisted HH:MM format historically uses the same encoded value for an
# unset clock time and a duration of zero. Semantic aliases keep call sites
# readable while preserving that data contract.
ZERO_HHMM = "00:00"
UNSET_TIME = ZERO_HHMM
ZERO_DURATION = ZERO_HHMM

NORMAL_DAY = "Normal day"
WEEKEND_DAY = "Weekend"

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

