import re


TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def hhmm_to_hours(hhmm_str):
    if not hhmm_str or ":" not in hhmm_str:
        return 0.0
    try:
        is_negative = hhmm_str.strip().startswith("-")
        clean_str = hhmm_str.replace("-", "")
        hours_str, minutes_str = clean_str.split(":", 1)
        decimal_hours = int(hours_str) + int(minutes_str) / 60
        return -decimal_hours if is_negative else decimal_hours
    except (ValueError, AttributeError):
        return 0.0


def hours_to_hhmm(decimal_hours):
    is_negative = decimal_hours < 0
    abs_hours = abs(decimal_hours)

    hours = int(abs_hours)
    minutes = round((abs_hours - hours) * 60)

    if minutes == 60:
        hours += 1
        minutes = 0

    formatted_time = f"{hours:02d}:{minutes:02d}"
    return f"-{formatted_time}" if is_negative else formatted_time
