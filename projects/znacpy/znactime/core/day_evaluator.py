"""Shared workday validation for calculations and row explanations."""

from dataclasses import dataclass
from datetime import date, datetime

from znactime.core.constants import (
    DATE_FORMAT, OPEN_END_MARKER, PERIOD_SEPARATOR, INTERRUPTION_SEPARATOR,
    UNSET_TIME, ZERO_DURATION,
)
from znactime.core.models import DayEntry
from znactime.core.time_utils import coerce_time_input, parse_interruption_input


class DayEvaluationState:
    EMPTY = ""
    IN_PROGRESS = "in_progress"
    VALID = "valid"
    INVALID = "invalid"


@dataclass(frozen=True)
class DayEvaluation:
    state: str
    can_calculate: bool
    reasons: tuple[str, ...] = ()

    @property
    def explanation(self) -> str:
        if self.state != DayEvaluationState.INVALID:
            return ""
        return "Daily overtime cannot be calculated.\n\n" + "\n".join(self.reasons)


class DayEvaluator:
    """Evaluate recorded work times without changing or calculating balances."""

    @staticmethod
    def evaluate(entry: DayEntry, *, today: date, month_closed: bool = False) -> DayEvaluation:
        issues = []
        pending = []
        try:
            work_date = datetime.strptime(entry.date, DATE_FORMAT).date()
        except (TypeError, ValueError):
            work_date = None
            issues.append("The date is invalid. Enter a valid day, month, and year.")
        running_day = work_date == today and not month_closed
        start_text = str(entry.start or "").strip()
        end_text = str(entry.end or "").strip()
        pause_text = str(entry.interruption or "").strip()
        has_times = (
            start_text not in ("", UNSET_TIME)
            or end_text not in ("", UNSET_TIME)
            or pause_text not in ("", ZERO_DURATION)
        )
        start = coerce_time_input(start_text)
        end = coerce_time_input(end_text)
        if start is None and start_text not in ("", UNSET_TIME):
            issues.append(f"Start time '{start_text}' is invalid. Use HH:MM.")
        if end is None and end_text not in ("", UNSET_TIME):
            issues.append(f"End time '{end_text}' is invalid. Use HH:MM.")
        pause = parse_interruption_input(pause_text)
        if pause is None:
            issues.append("The pause is invalid. Enter a duration or start/end times.")

        if start is None:
            if has_times:
                pending.append("The workday start time is missing.")
                if end is not None or (pause is not None and pause_text not in ("", ZERO_DURATION)):
                    issues.append("Enter a workday start time before recording an end or a pause.")
        elif end is None:
            pending.append("The workday end time is missing.")
        elif end <= start:
            issues.append(f"Workday end {end} must be after start {start}.")

        if pause is not None:
            if PERIOD_SEPARATOR in pause.normalized:
                previous_end = None
                for period in pause.normalized.split(INTERRUPTION_SEPARATOR):
                    pause_start, pause_end = period.split(PERIOD_SEPARATOR, 1)
                    label = f"Pause {period}"
                    if start is not None and pause_start < start:
                        issues.append(f"{label} starts before the workday starts at {start}.")
                    if pause_end == OPEN_END_MARKER:
                        if end is not None:
                            issues.append(f"{label} has no end time, but the workday has ended.")
                        else:
                            pending.append(f"{label} is still in progress.")
                    elif pause_end <= pause_start:
                        issues.append(f"{label} must end after it starts.")
                    elif end is not None and pause_end > end:
                        issues.append(f"{label} ends after the workday ends at {end}.")
                    if end is not None and pause_start >= end:
                        issues.append(f"{label} starts at or after the workday ends at {end}.")
                    if previous_end is not None and pause_start < previous_end:
                        issues.append(f"{label} overlaps another pause.")
                    previous_end = "24:00" if pause_end == OPEN_END_MARKER else pause_end
            if start is not None and end is not None and end > start:
                start_minutes = int(start[:2]) * 60 + int(start[3:])
                end_minutes = int(end[:2]) * 60 + int(end[3:])
                if round(pause.hours * 60) > end_minutes - start_minutes:
                    issues.append("The total pause duration exceeds the workday duration.")

        reasons = tuple(dict.fromkeys(issues + pending))
        if issues or (pending and has_times and not running_day):
            return DayEvaluation(DayEvaluationState.INVALID, False, reasons)
        if not has_times:
            return DayEvaluation(DayEvaluationState.IN_PROGRESS if running_day else DayEvaluationState.EMPTY, False)
        if start is not None and end is not None and not pending:
            return DayEvaluation(DayEvaluationState.VALID, True)
        return DayEvaluation(DayEvaluationState.IN_PROGRESS, False, reasons)
