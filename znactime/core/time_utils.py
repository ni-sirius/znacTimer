import re


TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def coerce_time_input(value):
    value = str(value).strip()

    if value.isdigit():
        if len(value) == 4:
            hours, minutes = value[:2], value[2:]
        elif len(value) == 3:
            hours, minutes = "0" + value[0], value[1:]
        elif len(value) == 2:
            hours, minutes = "00", value
        elif len(value) == 1:
            hours, minutes = "00", "0" + value
        else:
            return "00:00"

        try:
            hour_value = int(hours)
            minute_value = int(minutes)
        except ValueError:
            return "00:00"

        if 0 <= hour_value <= 23 and 0 <= minute_value <= 59:
            value = f"{hour_value:02d}:{minute_value:02d}"
        else:
            value = "00:00"

    if not TIME_RE.match(value):
        return None
    return value


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
