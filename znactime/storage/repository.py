from __future__ import annotations

from datetime import date, datetime
from typing import Callable, Protocol

from znactime.core.models import (
    BreakRecord,
    DayRecord,
    MonthClosePreview,
    MonthRecord,
    WorkSchedulePeriod,
)
from znactime.storage.legacy_csv_import import LegacyMergeResult, LegacyPreflight


class Repository(Protocol):
    def get_or_create_month(self, year: int, month: int) -> MonthRecord: ...

    def load_month(self, year: int, month: int) -> MonthRecord | None: ...

    def list_months(self, year: int | None = None) -> tuple[MonthRecord, ...]: ...

    def update_day(
        self,
        work_date: date,
        *,
        expected_revision: int,
        special_day: str | None = None,
        start_minute: int | None = None,
        end_minute: int | None = None,
        break_duration_minutes: int | None = None,
        breaks: tuple[BreakRecord, ...] | None = None,
        expected_work_minutes: int | None = None,
        expected_minutes_overridden: bool | None = None,
        fields: frozenset[str] = frozenset(),
    ) -> DayRecord: ...

    def is_month_closed(self, year: int, month: int) -> bool: ...

    def get_carry_over(self, year: int, month: int) -> int: ...

    def close_month(
        self,
        year: int,
        month: int,
        *,
        expected_revision: int,
        mark_unresolved_no_data: bool = False,
    ) -> MonthRecord: ...

    def preview_month_close(self, year: int, month: int) -> MonthClosePreview: ...

    def reopen_month(
        self, year: int, month: int, *, expected_revision: int
    ) -> MonthRecord: ...

    def month_has_carry_discontinuity(self, year: int, month: int) -> bool: ...

    def list_work_schedules(self) -> tuple[WorkSchedulePeriod, ...]: ...

    def replace_work_schedule(
        self,
        *,
        effective_from: date,
        effective_to: date | None,
        weekday_minutes: tuple[int, int, int, int, int, int, int],
        expected_public_id: str,
        expected_revision: int,
    ) -> WorkSchedulePeriod: ...

    def set_day_work_limit(
        self, work_date: date, minutes: int, *, expected_revision: int
    ) -> DayRecord: ...

    def start_workday(self, work_date: date, minute: int, now: datetime) -> DayRecord: ...

    def start_pause(
        self,
        work_date: date,
        minute: int,
        now: datetime,
        *,
        replace_duration: bool = False,
    ) -> DayRecord: ...

    def resume_workday(self, work_date: date, minute: int, now: datetime) -> DayRecord: ...

    def stop_workday(self, work_date: date, minute: int, now: datetime) -> DayRecord: ...

    def backup_to(
        self,
        destination: str,
        *,
        overwrite: bool = False,
        progress: Callable[[str, int, int], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> None: ...

    def merge_legacy(
        self,
        preflight: LegacyPreflight,
        *,
        progress: Callable[[str, int, int], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> LegacyMergeResult: ...

    def close(self) -> None: ...
