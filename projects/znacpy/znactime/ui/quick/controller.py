"""Application actions exposed to QML; storage remains authoritative."""

import calendar
import os
from collections.abc import Mapping
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import QItemSelection, QItemSelectionModel, QObject, Property, QTimer, QUrl, Qt, Signal, Slot
from PySide6.QtGui import QGuiApplication, QKeySequence

from znactime.config import APP_NAME, VERSION
from znactime.core.calendar_utils import build_calendar_week_text
from znactime.core.constants import DATE_FORMAT, PERIOD_SEPARATOR, UNSET_TIME, ZERO_DURATION
from znactime.core.day_evaluator import DayEvaluator
from znactime.core.models import MonthStats
from znactime.core.time_utils import hours_to_hhmm, open_interruption_start, parse_interruption_input
from znactime.storage.atomic_file import reject_protected_destination, sqlite_protected_paths
from znactime.storage.errors import StorageConflict, StorageError
from znactime.storage.legacy_csv_import import LegacyImportCancelled, preflight_legacy_data
from znactime.storage.sqlite.repository import SQLiteRepository
from znactime.ui.qt.first_launch import format_preflight_summary
from znactime.ui.qt.repository_mapper import parse_display_date
from znactime.ui.qt.settings import (
    FIT_STARTUP_HEIGHT_KEY, INITIAL_HEIGHT_KEY, INITIAL_WIDTH_KEY,
    SHOW_EXPECTED_END_KEY, load_startup_window_settings, load_work_schedule_settings,
)
from znactime.ui.qt.theme import ThemeController
from znactime.ui.quick.model import QuickMonthModel
from znactime.ui.quick.layout import month_layout
from znactime.ui.quick.tasks.runner import TaskRunner


def schedule_for_date(schedules, work_date):
    applicable = [item for item in schedules if item.effective_from <= work_date
                  and (item.effective_to is None or item.effective_to >= work_date)]
    return applicable[-1] if applicable else None


def _qml_colors(colors):
    return {key: _qml_colors(value) if isinstance(value, Mapping) else value
            for key, value in colors.items()}


class ApplicationController(QObject):
    changed = Signal()
    progressChanged = Signal()
    notification = Signal(str, str)
    confirmation = Signal(str, str, int)
    scrollToToday = Signal(int)
    monthLoaded = Signal()

    def __init__(self, repository, settings, parent=None, *, clock=None):
        super().__init__(parent)
        self.repository = repository
        self.settings = settings
        self._clock = clock or (lambda: datetime.now().astimezone())
        today = self._clock().date()
        self.year, self.month = today.year, today.month
        self._today = today
        self._record = None
        self._carry_discontinuity = False
        self._previous_unclosed = False
        self._confirm_id = 0
        self._pending = {}
        self._schedule_snapshot = None
        self._schedule_period = None
        self._shutting_down = False
        self._tasks = TaskRunner(self)
        self._tasks.progressChanged.connect(self.progressChanged)
        self._tasks.busyChanged.connect(self.changed)
        self._tasks.failed.connect(self._task_failed)
        self._day_hours, self._show_expected_end = load_work_schedule_settings(settings)
        self.theme = ThemeController(settings=settings)
        self._theme_colors = {name: _qml_colors(theme.colors) for name, theme in self.theme.themes.items()}
        self.theme.themeChanged.connect(self._theme_changed)
        self._model = QuickMonthModel(self, repository=repository, notify=self.notification.emit)
        self._model.entryCommitted.connect(self._edit_committed)
        self._model.entryEdited.connect(self._offer_close)
        self._model.monthReloaded.connect(self._record_reloaded)
        self._model.overtimeChanged.connect(lambda _: self.changed.emit())
        self.load_month()
        self._timer = QTimer(self)
        self._timer.setInterval(60_000)
        self._timer.timeout.connect(self.tick)
        self._timer.start()

    @Property(QObject, constant=True)
    def monthModel(self):
        return self._model

    @Property("QStringList", constant=True)
    def quitShortcuts(self):
        bindings = QKeySequence.keyBindings(QKeySequence.StandardKey.Quit)
        portable = QKeySequence("Ctrl+Q")
        if portable not in bindings:
            bindings.append(portable)
        return [binding.toString(QKeySequence.PortableText) for binding in bindings]

    @Property("QVariantMap", notify=progressChanged)
    def progress(self):
        """Publish task counters without invalidating month presentation."""
        return self._tasks.progress

    @Property("QVariantMap", notify=changed)
    def state(self):
        now = self._clock()
        record = self._record
        closed = record is not None and record.status == "closed"
        today_entry = self._today_entry(now)
        work_state, primary, message = "unavailable", "Start work", "Open the current, unlocked month to use workday controls"
        if today_entry is not None and not closed:
            if today_entry.start == UNSET_TIME:
                work_state, primary, message = "idle", "Start work", "Ready when you are"
            elif today_entry.end != UNSET_TIME:
                work_state, primary, message = "complete", "Day complete", f"{today_entry.start} – {today_entry.end}"
            elif open_interruption_start(today_entry.interruption):
                work_state, primary, message = "paused", "Resume work", f"Paused since {open_interruption_start(today_entry.interruption)}"
            else:
                work_state, primary, message = "working", "Pause", f"Working since {today_entry.start}"
            if today_entry.start != UNSET_TIME:
                end = today_entry.end if today_entry.end != UNSET_TIME else (open_interruption_start(today_entry.interruption) or now.strftime("%H:%M"))
                start_minute = int(today_entry.start[:2]) * 60 + int(today_entry.start[3:])
                end_minute = int(end[:2]) * 60 + int(end[3:])
                pauses = parse_interruption_input(today_entry.interruption)
                worked = max(0, end_minute - start_minute - (round(pauses.hours * 60) if pauses else 0))
                message += f" · {worked // 60:02d}:{worked % 60:02d} worked"
        fit, width, height = load_startup_window_settings(self.settings)
        status_text = message
        if work_state == "idle":
            status_text = "Ready to start today's workday"
        elif work_state == "working":
            status_text = f"Working since {today_entry.start} · {worked // 60:02d}:{worked % 60:02d}"
        elif work_state == "paused":
            pause_start = open_interruption_start(today_entry.interruption)
            minutes = max(0, now.hour * 60 + now.minute - int(pause_start[:2]) * 60 - int(pause_start[3:]))
            status_text = f"Paused since {pause_start} · {minutes // 60:02d}:{minutes % 60:02d}"
        elif work_state == "complete":
            status_text = f"Workday complete · {today_entry.start}–{today_entry.end}"
        return {
            "title": f"{APP_NAME} v{VERSION}", "version": VERSION,
            "year": self.year, "month": self.month,
            "currentMonth": (self.year, self.month) == (now.year, now.month),
            "monthName": calendar.month_name[self.month],
            "months": list(calendar.month_name)[1:],
            "calendarWeek": build_calendar_week_text(self.year, self.month, today=now.date()),
            "closed": closed, "carryDiscontinuity": self._carry_discontinuity,
            "previousUnclosed": self._previous_unclosed,
            "carry": hours_to_hhmm(record.opening_balance_minutes / 60) if record else "00:00",
            "balance": hours_to_hhmm(self._model.final_balance_hours()),
            "workState": work_state, "primaryText": primary, "workMessage": message,
            "workStatusText": status_text,
            "todayBadge": self._model.data(self._model.index(now.day - 1, 1), QuickMonthModel.BADGE) if today_entry is not None else {},
            "todayText": now.strftime("%A, %d %B"), "todayRow": now.day - 1,
            "dark": self.theme.is_dark(), "theme": self.theme.mode,
            "colors": self._theme_colors["dark" if self.theme.is_dark() else "light"],
            "showExpectedEnd": self._show_expected_end,
            "initialWidth": width, "initialHeight": height, "fitHeight": fit,
            "busy": self._tasks.busy, "progress": self.progress,
        }

    def _theme_changed(self, _mode):
        if hasattr(self, "_model"):
            self._model.refresh_theme()
        self.changed.emit()

    def _today_entry(self, now=None):
        now = now or self._clock()
        if (self.year, self.month) != (now.year, now.month):
            return None
        return self._model.entry_for_date(now.strftime(DATE_FORMAT))

    def load_month(self):
        try:
            record = self.repository.view_month(self.year, self.month)
            # Publish state once, when metadata and calculated rows agree.
            self._record_reloaded(record, notify=False)
            self._model.set_context(
                self.year, self.month, record.opening_balance_minutes / 60,
                self._day_hours, record.status == "closed", self._show_expected_end,
            )
            self._model.load_calculated_month(record, self._clock().date())
            self.changed.emit()
            self.monthLoaded.emit()
            return True
        except StorageError as error:
            self.notification.emit("Database error", str(error))
            return False

    def _record_reloaded(self, record, *, notify=True):
        if (record.year, record.month) != (self.year, self.month):
            return
        self._record = record
        try:
            self._carry_discontinuity = self.repository.month_has_carry_discontinuity(self.year, self.month)
            previous_year, previous_month = (self.year, self.month - 1) if self.month > 1 else (self.year - 1, 12)
            previous = self.repository.load_month(previous_year, previous_month)
            self._previous_unclosed = bool(previous and previous.status == "open" and any(
                day.start_minute is not None or day.end_minute is not None
                or day.break_duration_minutes or day.breaks for day in previous.days
            ))
        except StorageError as error:
            self._carry_discontinuity = self._previous_unclosed = False
            self.notification.emit("Balance status unavailable", str(error))
        if notify:
            self.changed.emit()

    def _edit_committed(self):
        try:
            self._record_reloaded(self.repository.view_month(self.year, self.month))
        except StorageError as error:
            self.notification.emit("Saved; reload failed", str(error))

    @Slot(int, int)
    def selectMonth(self, year, month):
        if self._tasks.busy or not 1 <= year <= 9999 or not 1 <= month <= 12:
            return
        previous = self.year, self.month
        self.year, self.month = year, month
        if not self.load_month():
            self.year, self.month = previous
            self.changed.emit()

    @Slot(int)
    def navigate(self, offset):
        total = self.year * 12 + self.month - 1 + offset
        year, month = divmod(total, 12)
        self.selectMonth(year, month + 1)

    @Slot()
    def showToday(self):
        today = self._clock().date()
        self.selectMonth(today.year, today.month)
        self.scrollToToday.emit(today.day - 1)

    @Slot()
    def tick(self):
        today = self._clock().date()
        if today != self._today:
            self._today = today
            self.selectMonth(today.year, today.month)
        else:
            self._model.recalculate(today=today, autosave=False)
            self.changed.emit()

    @Slot(int, int, str, result=bool)
    def editCell(self, row, column, value):
        if self._tasks.busy or not 0 <= row < self._model.rowCount() or not 0 <= column < self._model.columnCount():
            return False
        return self._model.setData(self._model.index(row, column), value)

    @Slot(int, int, result="QVariantMap")
    def beginCellEdit(self, row, column):
        if self._model.month_closed or not 0 <= row < self._model.rowCount() or column not in (1, 2, 3, 4):
            return {}
        entry = self._model.entries()[row]
        return {"row": row, "column": column, "date": entry.date, "revision": entry.revision}

    @Slot("QVariantMap", str, result=bool)
    def commitCellEdit(self, target, value):
        row, column = target.get("row", -1), target.get("column", -1)
        if not target or target != self.beginCellEdit(row, column):
            self.notification.emit("Edit expired", "The selected day changed while editing. Reopen the editor and try again.")
            return False
        return self.editCell(row, column, value)

    @Slot(int, int, result=str)
    def cellValue(self, row, column):
        if not 0 <= row < self._model.rowCount() or not 0 <= column < self._model.columnCount():
            return ""
        return self._model.data(self._model.index(row, column), Qt.ItemDataRole.EditRole) or ""

    @Slot(int, int, result=str)
    def initialCellValue(self, row, column):
        value = self.cellValue(row, column)
        return self._clock().strftime("%H:%M") if column in (2, 3) and value == UNSET_TIME else value

    @Slot(int, int, float, result="QVariantMap")
    def tableLayout(self, width, height, pixel_ratio):
        return month_layout(self._model, width, height, pixel_ratio)

    @Slot(int, int, int, int)
    def copyCells(self, first_row, first_column, last_row, last_column):
        rows = range(max(0, min(first_row, last_row)), min(self._model.rowCount(), max(first_row, last_row) + 1))
        columns = range(max(0, min(first_column, last_column)), min(self._model.columnCount(), max(first_column, last_column) + 1))
        text = "\n".join("\t".join(self.cellValue(row, col) for col in columns) for row in rows)
        QGuiApplication.clipboard().setText(text)

    @Slot(QObject, int, int, int, int, bool)
    def selectCells(self, selection, first_row, first_column, last_row, last_column, toggle):
        top = self._model.index(min(first_row, last_row), min(first_column, last_column))
        bottom = self._model.index(max(first_row, last_row), max(first_column, last_column))
        if selection.model() is self._model and top.isValid() and bottom.isValid():
            flag = QItemSelectionModel.Toggle if toggle else QItemSelectionModel.ClearAndSelect
            selection.select(QItemSelection(top, bottom), flag)

    @Slot(QObject)
    def copySelection(self, selection):
        indexes = selection.selectedIndexes()
        if not indexes:
            return
        rows = sorted({index.row() for index in indexes})
        columns = sorted({index.column() for index in indexes})
        values = {(index.row(), index.column()): index.data() for index in indexes}
        QGuiApplication.clipboard().setText("\n".join(
            "\t".join(str(values.get((row, column), "")) for column in columns) for row in rows
        ))

    @Slot(str)
    def copyText(self, text):
        QGuiApplication.clipboard().setText(text)

    @Slot(int, int, result=bool)
    def pasteCells(self, first_row, first_column):
        if self._tasks.busy or self._model.month_closed:
            return False
        lines = QGuiApplication.clipboard().text().splitlines()
        if not lines:
            return False
        cells = [(first_row + r, first_column + c, value)
                 for r, line in enumerate(lines) for c, value in enumerate(line.split("\t"))]
        # Check the destination before applying any cells.
        if any(not 0 <= r < self._model.rowCount() or not 1 <= c <= 4 for r, c, _ in cells):
            self.notification.emit("Cannot paste", "Paste into the Special day, Start, End, or Interruption columns within this month.")
            return False
        for row, column, value in cells:
            if not self.editCell(row, column, value):
                return False
        return True

    def _ask(self, title, text, action):
        self._confirm_id += 1
        self._pending = {self._confirm_id: action}
        self.confirmation.emit(title, text, self._confirm_id)

    @Slot(int, bool)
    def answerConfirmation(self, token, accepted):
        action = self._pending.pop(token, None)
        if accepted and action is not None:
            try:
                action()
            except (StorageError, OSError, ValueError) as error:
                self.notification.emit("Operation failed", str(error))
                self.load_month()

    def _work_action(self, action, *, replace_duration=False):
        now = self._clock()
        entry = self._today_entry(now)
        if self._tasks.busy or entry is None or self._model.month_closed:
            return
        try:
            minute = now.hour * 60 + now.minute
            if action == "pause":
                self.repository.start_pause(now.date(), minute, now, replace_duration=replace_duration)
            else:
                getattr(self.repository, action)(now.date(), minute, now)
            self.load_month()
        except StorageError as error:
            self.notification.emit("Workday update failed", str(error))

    @Slot()
    def primaryAction(self):
        entry = self._today_entry()
        if self._tasks.busy or entry is None or self._model.month_closed:
            return
        if entry.start == UNSET_TIME:
            if entry.end != UNSET_TIME:
                self._ask("Clear existing end time?", f"Starting the day will clear the existing end time ({entry.end}). Continue?",
                          lambda: self._work_action("start_workday"))
            else:
                self._work_action("start_workday")
        elif entry.end == UNSET_TIME:
            if open_interruption_start(entry.interruption):
                self._work_action("resume_workday")
            elif entry.interruption not in ("", ZERO_DURATION) and PERIOD_SEPARATOR not in entry.interruption:
                self._ask("Replace interruption duration?", "Today's interruption is stored as a duration. Replace it with the recorded pause period?",
                          lambda: self._work_action("pause", replace_duration=True))
            else:
                self._work_action("pause")

    @Slot()
    def stopWorkday(self):
        entry = self._today_entry()
        if entry is not None and entry.start != UNSET_TIME and entry.end == UNSET_TIME:
            self._work_action("stop_workday")

    @Slot()
    def closeMonth(self):
        if self._tasks.busy or self._model.month_closed:
            return
        year, month = self.year, self.month
        if date(year, month, 1) > self._clock().date().replace(day=1):
            self.notification.emit("Month close failed", "A future month cannot be closed.")
            return
        try:
            snapshot = self.repository.view_month(year, month)
            preview = self.repository.preview_month_close(year, month)
            revision = snapshot.revision
        except StorageError as error:
            self.notification.emit("Month close failed", str(error))
            return
        unresolved = bool(preview.unresolved_days)
        text = (f"{len(preview.unresolved_days)} day(s) with planned work have no work times.\n\n"
                "These days will be explicitly marked as No data. No data uses the configured special-day planned time; "
                "if that value is positive, closing will still require valid work times.\n\n") if unresolved else "All required days are complete.\n\n"
        text += (f"Opening balance: {hours_to_hhmm(preview.opening_balance_minutes / 60)}\n"
                 f"Calculated closing balance: {hours_to_hhmm(preview.closing_balance_minutes / 60)}\n\nClose this month?")

        def close():
            current = self.repository.view_month(year, month)
            if (current.revision != revision
                    or current.opening_balance_minutes != snapshot.opening_balance_minutes
                    or tuple(day.revision for day in current.days) != tuple(day.revision for day in snapshot.days)):
                raise StorageConflict("The month changed while confirmation was open. Review the reloaded month before closing it.")
            self.repository.close_month(year, month, expected_revision=revision, mark_unresolved_no_data=unresolved)
            self.load_month()
            self.notification.emit("Month closed", "Month successfully closed. PDF and CSV exports are separate actions.")
        self._ask("Close Month", text, close)

    @Slot()
    def reopenMonth(self):
        if self._tasks.busy or not self._model.month_closed:
            return
        year, month, revision = self.year, self.month, self._record.revision

        def reopen():
            self.repository.reopen_month(year, month, expected_revision=revision)
            self.load_month()
        self._ask("Reopen Month", "Reopen this month for corrections?\n\nLater closed months remain unchanged. A corrected balance may produce a carry-over discontinuity in a later closed month.", reopen)

    @staticmethod
    def _day_filled(entry, today):
        if entry.start in ("", UNSET_TIME) and entry.end in ("", UNSET_TIME) and entry.interruption in ("", ZERO_DURATION) and entry.expected_work_minutes == 0:
            return True
        return DayEvaluator.evaluate(entry, today=today).can_calculate

    def _offer_close(self, before, after):
        if self._model.month_closed or (self.year, self.month) > (self._clock().year, self._clock().month):
            return
        work_date = parse_display_date(after.date)
        last_day_end = work_date.day == calendar.monthrange(self.year, self.month)[1] and before.end in ("", UNSET_TIME) and after.end not in ("", UNSET_TIME)
        all_filled = not self._day_filled(before, self._clock().date()) and all(self._day_filled(e, self._clock().date()) for e in self._model.entries())
        if last_day_end or all_filled:
            period = self.year, self.month
            def offer():
                if not self._shutting_down and period == (self.year, self.month) and not self._pending:
                    self._ask("Ready to close the month?", "You've completed the last unfinished workday or entered the end time for the last calendar day. Review and close this month now?", self.closeMonth)
            QTimer.singleShot(0, self, offer)

    @Slot(str)
    def setTheme(self, mode):
        self.theme.set_mode(mode)

    @Slot(bool, int, int)
    def saveWindowSettings(self, fit_height, width, height):
        self.settings.setValue(FIT_STARTUP_HEIGHT_KEY, fit_height)
        self.settings.setValue(INITIAL_WIDTH_KEY, max(800, min(3840, width)))
        self.settings.setValue(INITIAL_HEIGHT_KEY, max(500, min(2160, height)))
        self.settings.sync()
        self.changed.emit()

    @Slot(result="QVariantMap")
    def scheduleSettings(self):
        try:
            selected = date(self.year, self.month, 1)
            self._schedule_snapshot = schedule_for_date(self.repository.list_work_schedules(), selected)
            self._schedule_period = self.year, self.month
            item = self._schedule_snapshot
            return {"days": list(item.weekday_minutes) if item else [480] * 5 + [0, 0],
                    "special": item.special_day_minutes if item else 0,
                    "showExpectedEnd": self._show_expected_end, "closed": self._model.month_closed}
        except StorageError as error:
            self.notification.emit("Schedule unavailable", str(error))
            return {}

    @Slot("QVariantList", int, bool, result=bool)
    def saveSchedule(self, days, special, show_expected):
        if self._tasks.busy or self._schedule_period != (self.year, self.month):
            return False
        try:
            days = tuple(int(value) for value in days)
            original = self._schedule_snapshot
            if original is None:
                raise ValueError("The active schedule could not be loaded. Reopen settings and try again.")
            if days != original.weekday_minutes or special != original.special_day_minutes:
                self.repository.replace_work_schedule(
                    effective_from=date(self.year, self.month, 1), effective_to=None,
                    weekday_minutes=days, special_day_minutes=special,
                    expected_public_id=original.public_id, expected_revision=original.revision,
                )
            self._show_expected_end = show_expected
            self.settings.setValue(SHOW_EXPECTED_END_KEY, show_expected)
            self.settings.sync()
            self.load_month()
            return True
        except (StorageError, ValueError) as error:
            self.notification.emit("Schedule update failed", str(error))
            if isinstance(error, StorageConflict):
                self.load_month()
            return False

    @Slot(str, result=str)
    def suggestedFile(self, kind):
        if kind == "backup":
            return self._clock().strftime("znactime-backup-%Y%m%d-%H%M%S.db")
        if kind == "pdf":
            return f"{self.year}_{calendar.month_name[self.month]}.pdf"
        return f"{self.year}_tmp_{self.month:02}.csv"

    @Slot(str, QUrl)
    def exportFile(self, kind, url):
        if self._tasks.busy or kind not in ("csv", "pdf", "backup"):
            return
        if not url.isLocalFile():
            self.notification.emit("Export failed", "Choose a local file.")
            return
        target = Path(url.toLocalFile())
        protected = sqlite_protected_paths(self.repository.path)
        try:
            reject_protected_destination(target, protected)
            month = self.repository.view_month(self.year, self.month)
        except StorageError as error:
            self.notification.emit("Unsafe destination", str(error))
            return
        stats = MonthStats(self.year, calendar.month_name[self.month], self._model.final_balance_hours())

        def write(overwrite):
            if kind == "backup":
                database = self.repository.path
                def backup(*, progress, cancelled):
                    repo = SQLiteRepository(database)
                    try:
                        return repo.backup_to(target, overwrite=overwrite, progress=progress, cancelled=cancelled)
                    finally:
                        repo.close()
                self._start_task("Backing up database", backup, lambda _: self.notification.emit("Backup complete", f"Database backed up to:\n{target}"))
                return
            try:
                if kind == "csv":
                    from znactime.storage.csv_export import export_month
                    export_month(month, target, overwrite=overwrite, protected_paths=protected)
                else:
                    from znactime.storage.pdf_export import export_pdf
                    export_pdf(stats, target, overwrite=overwrite, protected_paths=protected)
                self.notification.emit("Export complete", f"Saved to:\n{target}")
            except (OSError, StorageError) as error:
                self.notification.emit("Export failed", str(error))
        if os.path.lexists(target):
            self._ask("Replace export?", f"{target} already exists. Replace it?", lambda: write(True))
        else:
            write(False)

    @Slot(QUrl)
    def importFolder(self, url):
        if self._tasks.busy or not url.isLocalFile():
            return
        source = url.toLocalFile()
        self._start_task("Inspecting legacy data", lambda **kwargs: preflight_legacy_data(source, **kwargs), self._confirm_import)

    def _confirm_import(self, preflight):
        summary = format_preflight_summary(preflight)
        if preflight.blocking_errors:
            self.notification.emit("CSV import cannot continue", summary)
            return
        database = self.repository.path
        def merge():
            def task(*, progress, cancelled):
                repo = SQLiteRepository(database)
                try:
                    return repo.merge_legacy(preflight, progress=progress, cancelled=cancelled)
                finally:
                    repo.close()
            self._start_task("Importing legacy data", task, self._import_finished)
        self._ask("Confirm CSV import", f"Source: {preflight.source_root}\n\n{summary}\n\nExisting local day data, closed months, and per-day work limits will not be overwritten. Only untouched placeholders and missing months may receive CSV data. Source files will not be changed.\n\nContinue?", merge)

    def _import_finished(self, result):
        self.load_month()
        if result.already_imported:
            self.notification.emit("CSV data already imported", "This exact source snapshot was imported previously. No data changed.")
        else:
            self.notification.emit("CSV import complete", f"New months: {result.months_created}\nExisting months examined: {result.months_merged}\nDays imported: {result.days_imported}\nDays kept from SQLite: {result.days_kept_current}\nUnchanged/blank days: {result.days_unchanged}\nMonths imported as closed: {result.months_closed}\nClosures kept open: {result.closures_kept_open}\n\nCSV source preserved at:\n{result.source_root}")

    def _start_task(self, title, task, success):
        if self._shutting_down:
            return

        def completed(result):
            if self._shutting_down or not success:
                return
            try:
                success(result)
            except (StorageError, OSError, ValueError) as error:
                self.notification.emit("Operation failed", str(error))

        return self._tasks.start(title, task, completed)

    @Slot(object)
    def _task_failed(self, error):
        if not self._shutting_down and not isinstance(error, LegacyImportCancelled):
            self.notification.emit("Operation failed", str(error))

    @Slot()
    def cancelTask(self):
        self._tasks.cancel()

    def shutdown(self):
        self._shutting_down = True
        self._timer.stop()
        self._pending.clear()
        self._tasks.shutdown()
