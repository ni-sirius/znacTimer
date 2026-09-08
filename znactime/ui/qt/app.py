import os
from datetime import date, datetime
from pathlib import Path

from PySide6 import __version__ as PYSIDE_VERSION

from znactime.config import APP_NAME, VERSION
from znactime.core.calendar_utils import build_calendar_week_text
from znactime.core.constants import (
    DATE_FORMAT,
    OPEN_END_MARKER,
    PERIOD_SEPARATOR,
    TIME_FORMAT,
    UNSET_TIME,
    ZERO_DURATION,
)
from znactime.core.models import MonthStats
from znactime.core.time_utils import (
    append_interruption_period,
    finish_interruption_period,
    hours_to_hhmm,
    open_interruption_start,
)
from znactime.storage.atomic_file import (
    reject_protected_destination,
    sqlite_protected_paths,
)
from znactime.storage.errors import StorageConflict, StorageError
from znactime.storage.legacy_csv_import import (
    LegacyImportCancelled,
    preflight_legacy_data,
)
from znactime.storage.sqlite.repository import SQLiteRepository
from znactime.ui.qt import (
    QApplication,
    QFileDialog,
    QIcon,
    QMainWindow,
    QMessageBox,
    QPixmap,
    QTimer,
    QVBoxLayout,
    QWidget,
    Qt,
)
from znactime.ui.qt.header import HeaderWidget
from znactime.ui.qt.first_launch import format_preflight_summary
from znactime.ui.qt.menu import MenuBar
from znactime.ui.qt.player import (
    WorkdayBar,
    WorkdayState,
)
from znactime.ui.qt.color_scheme import is_dark_theme, theme_color
from znactime.ui.qt.background import run_background_task
from znactime.ui.qt.repository_mapper import parse_display_date
from znactime.ui.qt.settings import (
    AppearanceDialog,
    WorkScheduleDialog,
    load_startup_window_settings,
    load_work_schedule_settings,
)
from znactime.ui.qt.table import TableWidget
from znactime.ui.qt.theme import ThemeController


APP_ICON_PATH = Path(__file__).with_name("assets") / "app_icon.png"
ABOUT_LICENSE = "MIT"
ABOUT_WEBSITE = "https://znac.org"
ABOUT_CONTACT = "znacompany@gmail.com"
ABOUT_USE = "Track workdays, interruptions, and overtime."


def _schedule_for_date(schedules, work_date):
    applicable = [
        item
        for item in schedules
        if item.effective_from <= work_date
        and (item.effective_to is None or item.effective_to >= work_date)
    ]
    return applicable[-1] if applicable else None


def create_about_dialog(parent=None):
    dialog = QMessageBox(parent)
    dialog.setWindowTitle(f"About {APP_NAME}")
    dialog.setWindowIcon(QIcon(str(APP_ICON_PATH)))
    dialog.setTextFormat(Qt.TextFormat.RichText)
    dialog.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
    dialog.setText(
        f"<h2>{APP_NAME}</h2>"
        f"<p><b>Version:</b> {VERSION}<br>"
        f"<b>License:</b> {ABOUT_LICENSE}<br>"
        f"<b>Built with:</b> PySide6 {PYSIDE_VERSION} — LGPL v3</p>"
        f"<p>{ABOUT_USE}</p>"
        f'<p><b>Author:</b> <a href="{ABOUT_WEBSITE}">znac.org</a><br>'
        f'<b>Contact:</b> <a href="mailto:{ABOUT_CONTACT}">'
        f"{ABOUT_CONTACT}</a></p>"
    )
    icon = QPixmap(str(APP_ICON_PATH))
    if not icon.isNull():
        dialog.setIconPixmap(
            icon.scaled(
                96,
                96,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
    dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
    return dialog


class TimeTrackerApp(QMainWindow):
    def __init__(self, repository=None):
        super().__init__()
        self.repository = repository
        self._month_record = None
        self.setWindowTitle(f"{APP_NAME} v{VERSION}")
        self.setWindowIcon(QIcon(str(APP_ICON_PATH)))

        self.month_closed = False
        self.month_carry_discontinuity = False
        self.carry_over = 0.0
        self.current_overtime = 0.0
        self._initial_size_fitted = False
        self.theme_controller = ThemeController()
        self.theme_controller.themeChanged.connect(self.on_theme_changed)
        (
            self.fit_startup_height,
            initial_width,
            initial_height,
        ) = load_startup_window_settings(
            self.theme_controller.settings
        )
        (
            self.day_hours,
            self.show_expected_end,
        ) = load_work_schedule_settings(self.theme_controller.settings)
        if self.repository is not None:
            today = datetime.today().date()
            active_schedule = _schedule_for_date(
                self.repository.list_work_schedules(), today
            )
            if active_schedule is not None:
                self.day_hours = (
                    active_schedule.weekday_minutes[today.weekday()] / 60
                )
        self.resize(initial_width, initial_height)

        self.menu = MenuBar(
            self,
            close_month_command=self.close_month,
            appearance_command=self.open_appearance_settings,
            work_schedule_command=self.open_work_schedule_settings,
            about_command=self.show_about,
            export_month_command=self.export_month_csv,
            export_pdf_command=self.export_current_pdf,
            backup_command=self.backup_database,
            import_csv_command=self.import_csv_data,
            reopen_month_command=self.reopen_month,
        )
        self.setMenuBar(self.menu)

        self.header = HeaderWidget(self)
        now = datetime.now()
        self._current_date = now.date()
        self.header.set_year(now.year)
        self.header.set_month(now.month)
        self.header.selectionChanged.connect(self.load_month)

        self.table = TableWidget(self, repository=repository)
        self.table.overtimeChanged.connect(self.set_current_overtime)
        self.table.monthReloaded.connect(self._apply_reloaded_month)
        self.table.contentHeightChanged.connect(self.fit_initial_window_height)

        self.workday_bar = WorkdayBar(self)
        self.workday_bar.primaryClicked.connect(self.on_workday_primary)
        self.workday_bar.stopClicked.connect(self.stop_workday)
        self.table.entriesChanged.connect(self.refresh_workday_bar)

        central_widget = QWidget(self)
        central_widget.setObjectName("appBackground")
        central_widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(self.header)
        layout.addWidget(self.table, stretch=1)
        layout.addWidget(self.workday_bar)
        self.setCentralWidget(central_widget)
        central_widget.setFocus(Qt.FocusReason.OtherFocusReason)
        self.apply_shell_theme()

        self.load_month()
        self._today_rollover_timer = QTimer(self)
        self._today_rollover_timer.setInterval(60 * 1000)
        self._today_rollover_timer.timeout.connect(self._check_today_rollover)
        self._today_rollover_timer.start()

    def fit_initial_window_height(self, table_content_height):
        if self._initial_size_fitted or not self.fit_startup_height:
            return

        screen = self.screen()
        if screen is None:
            return

        frame_height = max(
            0,
            self.frameGeometry().height() - self.geometry().height(),
        )
        layout = self.centralWidget().layout()
        margins = layout.contentsMargins()
        content_height = (
            self.menuBar().sizeHint().height()
            + self.header.sizeHint().height()
            + table_content_height
            + self.workday_bar.sizeHint().height()
            + margins.top()
            + margins.bottom()
            + layout.spacing() * 2
            + frame_height
        )
        target_height = min(
            content_height,
            screen.availableGeometry().height(),
        )

        self._initial_size_fitted = True
        self.resize(self.width(), target_height)

    def open_appearance_settings(self):
        dialog = AppearanceDialog(self, self.theme_controller)
        dialog.exec()

    def open_work_schedule_settings(self):
        initial_weekday_minutes = None
        initial_special_day_minutes = 0
        active_schedule = None
        if self.repository is not None:
            selected_month = date(self.header.year(), self.header.month(), 1)
            active_schedule = _schedule_for_date(
                self.repository.list_work_schedules(), selected_month
            )
            if active_schedule is not None:
                initial_weekday_minutes = active_schedule.weekday_minutes
                initial_special_day_minutes = active_schedule.special_day_minutes
        dialog = WorkScheduleDialog(
            self,
            self.theme_controller.settings,
            initial_weekday_minutes=initial_weekday_minutes,
            initial_special_day_minutes=initial_special_day_minutes,
            persist_workday=self.repository is None,
        )
        dialog.exec()
        self._apply_work_schedule_settings(
            weekday_minutes=dialog.schedule_widget.weekday_minutes(),
            special_day_minutes=dialog.schedule_widget.special_day_minutes(),
            show_expected_end=dialog.schedule_widget.show_expected_end(),
            expected_schedule=active_schedule,
        )

    def show_about(self):
        create_about_dialog(self).exec()

    def _apply_work_schedule_settings(
        self,
        day_hours=None,
        show_expected_end=None,
        *,
        weekday_minutes=None,
        special_day_minutes=None,
        expected_schedule=None,
    ):
        if (
            (day_hours is None and weekday_minutes is None)
            or show_expected_end is None
        ):
            loaded_day_hours, show_expected_end = load_work_schedule_settings(
                self.theme_controller.settings
            )
            if day_hours is None:
                day_hours = loaded_day_hours
        if weekday_minutes is None:
            weekday_minutes = (round(day_hours * 60),) * 5 + (0, 0)
        if special_day_minutes is None:
            special_day_minutes = getattr(expected_schedule, "special_day_minutes", 0)
        today = datetime.today().date()
        selected_day_hours = weekday_minutes[today.weekday()] / 60
        schedule_changed = (
            expected_schedule is None
            or weekday_minutes != expected_schedule.weekday_minutes
            or special_day_minutes != getattr(expected_schedule, "special_day_minutes", 0)
        )
        if (
            not schedule_changed
            and selected_day_hours == self.day_hours
            and show_expected_end == self.show_expected_end
        ):
            return
        if getattr(self, "repository", None) is not None and schedule_changed:
            if expected_schedule is None:
                QMessageBox.warning(
                    self,
                    "Schedule update failed",
                    "The active work schedule could not be loaded. Reopen the settings and try again.",
                )
                return
            selected_month = (
                date(self.header.year(), self.header.month(), 1)
                if getattr(self, "header", None) is not None
                else datetime.today().date().replace(day=1)
            )
            if getattr(self, "month_closed", False):
                QMessageBox.warning(
                    self,
                    "Schedule update unavailable",
                    "The selected month is closed. Reopen it before changing the work schedule.",
                )
                return
            try:
                self.repository.replace_work_schedule(
                    effective_from=selected_month,
                    effective_to=None,
                    weekday_minutes=weekday_minutes,
                    special_day_minutes=special_day_minutes,
                    expected_public_id=expected_schedule.public_id,
                    expected_revision=expected_schedule.revision,
                )
            except StorageConflict:
                current = _schedule_for_date(
                    self.repository.list_work_schedules(), selected_month
                )
                if current is not None:
                    self.day_hours = current.weekday_minutes[selected_month.weekday()] / 60
                self.load_month()
                QMessageBox.warning(
                    self,
                    "Work schedule changed",
                    "Another writer changed the work schedule while the settings were open. "
                    "Your change was not applied; the current schedule has been reloaded.",
                )
                return
            except StorageError as error:
                QMessageBox.warning(self, "Schedule update failed", str(error))
                return
            self.day_hours = selected_day_hours
            self.show_expected_end = show_expected_end
            self.load_month()
            return
        self.day_hours = selected_day_hours
        self.show_expected_end = show_expected_end
        self.table.set_context(
            year=self.header.year(),
            month=self.header.month(),
            carry_over=self.carry_over,
            day_hours=self.day_hours,
            month_closed=self.month_closed,
            show_expected_end=self.show_expected_end,
        )
        self.table.recalculate(today=datetime.today().date(), autosave=False)

    def on_theme_changed(self, _mode):
        self.apply_shell_theme()
        self.menu.apply_theme()
        self.header.apply_theme()
        self.table.refresh_theme()
        self.workday_bar.apply_theme()

    def apply_shell_theme(self):
        background = theme_color("shell.background", is_dark_theme())
        self.setStyleSheet(
            "QWidget#appBackground {"
            f"background-color: {background};"
            "}"
        )

    def set_current_overtime(self, overtime):
        self.current_overtime = overtime
        self.header.set_overtime_text(
            f"Overtime: {hours_to_hhmm(overtime)}",
            closed=self.month_closed,
            carry_discontinuity=getattr(self, "month_carry_discontinuity", False),
        )

    def _check_today_rollover(self, now=None):
        if now is None:
            now = datetime.now()

        today = now.date()
        if today == self._current_date:
            return

        self._current_date = today

        if self.header.year() != now.year or self.header.month() != now.month:
            self.header.set_period(now.year, now.month)
            self.load_month()
            return

        self.header.set_calendar_week_text(
            build_calendar_week_text(now.year, now.month, today=today)
        )
        self.table.recalculate(today=today, autosave=False)
        self.refresh_workday_bar(now)

    def load_month(self):
        year = self.header.year()
        month = self.header.month()
        if self.repository is None:
            return
        try:
            record = self.repository.view_month(year, month)
            carry_discontinuity = self.repository.month_has_carry_discontinuity(
                year, month
            )
        except StorageError as error:
            QMessageBox.critical(self, "Database error", str(error))
            return
        self._month_record = record
        self.month_closed = record.status == "closed"
        self.month_carry_discontinuity = carry_discontinuity
        self.carry_over = record.opening_balance_minutes / 60
        self.header.set_carry_over_text(
            f"Carry over: {hours_to_hhmm(self.carry_over)}"
        )
        self.header.set_calendar_week_text(
            build_calendar_week_text(year, month, today=datetime.today().date())
        )
        self.table.set_context(
            year=year,
            month=month,
            carry_over=self.carry_over,
            day_hours=self.day_hours,
            month_closed=self.month_closed,
            show_expected_end=self.show_expected_end,
        )
        self.table.set_month_record(record)
        self.table.recalculate(today=datetime.today().date(), autosave=False)
        self.table.set_month_closed(self.month_closed)
        self.menu.set_month_closed(self.month_closed)
        self.refresh_workday_bar()

    def _apply_reloaded_month(self, record):
        if record.year != self.header.year() or record.month != self.header.month():
            return
        self._month_record = record
        self.month_closed = record.status == "closed"
        try:
            self.month_carry_discontinuity = (
                self.repository.month_has_carry_discontinuity(
                    record.year, record.month
                )
                if self.repository is not None
                else False
            )
        except StorageError:
            self.month_carry_discontinuity = False
        self.carry_over = record.opening_balance_minutes / 60
        self.header.set_carry_over_text(
            f"Carry over: {hours_to_hhmm(self.carry_over)}"
        )
        self.menu.set_month_closed(self.month_closed)
        self.refresh_workday_bar()

    def _today_entry(self, now=None):
        if now is None:
            now = datetime.now()
        if self.header.year() != now.year or self.header.month() != now.month:
            return None
        return self.table.entry_for_date(now.strftime(DATE_FORMAT))

    def _active_pause(self, now=None):
        entry = self._today_entry(now)
        if entry is None or entry.start == UNSET_TIME or entry.end != UNSET_TIME:
            return None
        return open_interruption_start(entry.interruption)

    def refresh_workday_bar(self, now=None):
        if now is None:
            now = datetime.now()
        entry = self._today_entry(now)
        if self.month_closed or entry is None:
            self.workday_bar.set_state(
                WorkdayState.UNAVAILABLE,
                message="Open the current, unlocked month to use workday controls",
            )
            return

        pause_start = self._active_pause(now)
        if entry.start == UNSET_TIME:
            self.workday_bar.set_state(WorkdayState.IDLE)
        elif entry.end != UNSET_TIME:
            self.workday_bar.set_state(
                WorkdayState.COMPLETE,
                start=entry.start,
                end=entry.end,
            )
        else:
            if pause_start:
                self.workday_bar.set_state(
                    WorkdayState.PAUSED,
                    start=entry.start,
                    pause_start=pause_start,
                )
                return
            self.workday_bar.set_state(
                WorkdayState.WORKING,
                start=entry.start,
            )

    def on_workday_primary(self):
        now = datetime.now().astimezone()
        entry = self._today_entry(now)
        if self.month_closed or entry is None:
            return

        if getattr(self, "repository", None) is not None:
            work_date = parse_display_date(entry.date)
            minute = now.hour * 60 + now.minute
            if entry.start == UNSET_TIME and entry.end != UNSET_TIME:
                answer = QMessageBox.question(
                    self,
                    "Clear existing end time?",
                    f"Starting the day will clear the existing end time "
                    f"({entry.end}). Continue?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return
            try:
                if entry.start == UNSET_TIME:
                    self.repository.start_workday(work_date, minute, now)
                elif self._active_pause(now):
                    self.repository.resume_workday(work_date, minute, now)
                elif entry.end == UNSET_TIME:
                    replace_duration = False
                    if (
                        entry.interruption not in ("", ZERO_DURATION)
                        and PERIOD_SEPARATOR not in entry.interruption
                    ):
                        answer = QMessageBox.question(
                            self,
                            "Replace interruption duration?",
                            "Today's interruption is stored as a duration. "
                            "Replace it with the recorded pause period?",
                            QMessageBox.StandardButton.Yes
                            | QMessageBox.StandardButton.No,
                            QMessageBox.StandardButton.No,
                        )
                        if answer != QMessageBox.StandardButton.Yes:
                            return
                        replace_duration = True
                    self.repository.start_pause(
                        work_date,
                        minute,
                        now,
                        replace_duration=replace_duration,
                    )
            except StorageError as error:
                QMessageBox.warning(self, "Workday update failed", str(error))
                return
            self.load_month()
            return

        date_text = now.strftime(DATE_FORMAT)
        time_text = now.strftime(TIME_FORMAT)
        pause_start = self._active_pause(now)

        if entry.start == UNSET_TIME:
            if entry.end != UNSET_TIME:
                answer = QMessageBox.question(
                    self,
                    "Clear existing end time?",
                    f"Starting the day will clear the existing end time "
                    f"({entry.end}). Continue?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return
            self.table.update_entry_for_date(
                date_text,
                start=time_text,
                end=UNSET_TIME,
            )
        elif pause_start:
            if not self._finish_active_pause(entry, time_text):
                return
        elif entry.end == UNSET_TIME:
            if not self._start_active_pause(entry, date_text, time_text):
                return

        self.refresh_workday_bar(now)

    def _start_active_pause(self, entry, date_text, start_text):
        interruption = entry.interruption
        if (
            interruption not in ("", ZERO_DURATION)
            and PERIOD_SEPARATOR not in interruption
        ):
            answer = QMessageBox.question(
                self,
                "Replace interruption duration?",
                "Today's interruption is stored as a duration. Replace it "
                "with the recorded pause period?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False
            interruption = ZERO_DURATION

        try:
            interruption = append_interruption_period(
                interruption,
                start_text,
                OPEN_END_MARKER,
            )
        except ValueError as error:
            QMessageBox.warning(self, "Invalid pause", str(error))
            return False

        updated = self.table.update_entry_for_date(
            entry.date,
            interruption=interruption,
        )
        return updated

    def _finish_active_pause(self, entry, end_text):
        pause_start = self._active_pause()
        if pause_start is None:
            return True
        if entry is None:
            return True

        interruption = entry.interruption
        if (
            interruption not in ("", ZERO_DURATION)
            and PERIOD_SEPARATOR not in interruption
        ):
            answer = QMessageBox.question(
                self,
                "Replace interruption duration?",
                "Today's interruption is stored as a duration. Replace it "
                "with the recorded pause period?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False
            interruption = ZERO_DURATION

        try:
            interruption = finish_interruption_period(
                interruption,
                pause_start,
                end_text,
            )
        except ValueError as error:
            QMessageBox.warning(self, "Invalid pause", str(error))
            return False

        updated = self.table.update_entry_for_date(
            entry.date,
            interruption=interruption,
        )
        return updated

    def stop_workday(self):
        now = datetime.now().astimezone()
        entry = self._today_entry(now)
        if self.month_closed or entry is None or entry.start == UNSET_TIME:
            return

        if getattr(self, "repository", None) is not None:
            try:
                self.repository.stop_workday(
                    parse_display_date(entry.date),
                    now.hour * 60 + now.minute,
                    now,
                )
            except StorageError as error:
                QMessageBox.warning(self, "Workday update failed", str(error))
                return
            self.load_month()
            return

        end_text = now.strftime(TIME_FORMAT)
        if end_text <= entry.start:
            QMessageBox.warning(
                self,
                "Invalid time range",
                "End time must be later than start time; overnight work is not supported.",
            )
            return

        if self._active_pause(now):
            if not self._finish_active_pause(entry, end_text):
                return
            entry = self._today_entry(now)

        self.table.update_entry_for_date(entry.date, end=end_text)
        self.refresh_workday_bar(now)

    def close_month(self):
        if self.month_closed:
            QMessageBox.information(self, "Month closed", "This month is already closed.")
            return

        if getattr(self, "repository", None) is None:
            return
        year = self.header.year()
        month = self.header.month()
        today = datetime.today().date()
        if date(year, month, 1) > date(today.year, today.month, 1):
            QMessageBox.warning(
                self,
                "Month close failed",
                "A future month cannot be closed.",
            )
            return
        try:
            preview = self.repository.preview_month_close(year, month)
        except StorageError as error:
            QMessageBox.warning(self, "Month close failed", str(error))
            return
        unresolved_count = len(preview.unresolved_days)
        closing = hours_to_hhmm(preview.closing_balance_minutes / 60)
        opening = hours_to_hhmm(preview.opening_balance_minutes / 60)
        if unresolved_count:
            close_text = (
                f"{unresolved_count} day(s) with planned work have no work times.\n\n"
                "If you continue, each of those days will be explicitly marked "
                "as No data. No data uses the configured special-day planned time; "
                "if that value is positive, closing will still require valid work times."
                f"\n\nOpening balance: {opening}\n"
                f"Calculated closing balance: {closing}\n\n"
                "Mark these days as No data and close the month?"
            )
        else:
            close_text = (
                f"All required days are complete.\n\nOpening balance: {opening}\n"
                f"Calculated closing balance: {closing}\n\nClose this month?"
            )
        answer = QMessageBox.question(
            self,
            "Close Month",
            close_text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self.repository.close_month(
                year,
                month,
                expected_revision=self._month_record.revision,
                mark_unresolved_no_data=bool(unresolved_count),
            )
        except StorageError as error:
            QMessageBox.warning(self, "Month close failed", str(error))
            return
        self.load_month()
        QMessageBox.information(
            self,
            "Month closed",
            "Month successfully closed. PDF and CSV exports are separate actions.",
        )

    def reopen_month(self):
        if not self.month_closed or self.repository is None:
            QMessageBox.information(self, "Month open", "This month is already open.")
            return
        answer = QMessageBox.question(
            self,
            "Reopen Month",
            "Reopen this month for corrections?\n\n"
            "Later closed months will remain unchanged. If the corrected balance no "
            "longer matches the next closed month, that month will show a carry-over "
            "discontinuity.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.repository.reopen_month(
                self.header.year(),
                self.header.month(),
                expected_revision=self._month_record.revision,
            )
        except StorageError as error:
            QMessageBox.warning(self, "Month reopen failed", str(error))
            return
        self.load_month()
        QMessageBox.information(
            self,
            "Month reopened",
            "The month is editable again. Later closed months were not changed.",
        )

        return

    def collect_statistics(self):
        return MonthStats(
            year=self.header.year(),
            month=self.header.month_name(),
            overtime=self.table.final_balance_hours(),
        )

    def _confirmed_export_path(self, caption, suggested, file_filter):
        path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            caption,
            suggested,
            file_filter,
        )
        if not path:
            return None
        protected_paths = (
            sqlite_protected_paths(self.repository.path)
            if self.repository is not None
            else ()
        )
        try:
            reject_protected_destination(path, protected_paths)
        except StorageError as error:
            QMessageBox.warning(self, "Unsafe destination", str(error))
            return None
        overwrite = os.path.lexists(path)
        if overwrite:
            answer = QMessageBox.question(
                self,
                "Replace export?",
                f"{path} already exists. Replace it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return None
        return path, overwrite

    def export_month_csv(self):
        if self.repository is None or self._month_record is None:
            return
        suggested = f"{self.header.year()}_tmp_{self.header.month():02}.csv"
        destination = self._confirmed_export_path(
            "Export month CSV", suggested, "CSV files (*.csv)"
        )
        if destination is None:
            return
        target, overwrite = destination
        try:
            from znactime.storage.csv_export import export_month

            month = self.repository.load_month(
                self.header.year(),
                self.header.month(),
            )
            if month is None:
                raise StorageError("The selected month no longer exists.")
            export_month(
                month,
                target,
                overwrite=overwrite,
                protected_paths=sqlite_protected_paths(self.repository.path),
            )
        except (OSError, StorageError) as error:
            QMessageBox.warning(self, "Export failed", str(error))

    def import_csv_data(self):
        if self.repository is None:
            return
        detected = Path.cwd() / "data"
        source = QFileDialog.getExistingDirectory(
            self,
            "Select legacy CSV data folder",
            str(detected if detected.is_dir() else Path.home()),
        )
        if not source:
            return
        try:
            preflight = run_background_task(
                self,
                "Inspecting legacy data",
                lambda *, progress, cancelled: preflight_legacy_data(
                    source,
                    progress=progress,
                    cancelled=cancelled,
                ),
            )
        except LegacyImportCancelled:
            return
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "CSV import cannot continue", str(error))
            return
        summary = format_preflight_summary(preflight)
        if preflight.blocking_errors:
            QMessageBox.critical(self, "CSV import cannot continue", summary)
            return
        answer = QMessageBox.question(
            self,
            "Confirm CSV import",
            f"Source: {preflight.source_root}\n\n{summary}\n\n"
            "SQLite remains authoritative. Existing local day data, closed months, "
            "per-day work limits, and current table data will not be overwritten. "
            "Only untouched calendar-day placeholders and missing months may receive "
            "CSV data. Source files will not be changed.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            database_path = self.repository.path

            def merge(*, progress, cancelled):
                worker_repository = SQLiteRepository(database_path)
                try:
                    return worker_repository.merge_legacy(
                        preflight,
                        progress=progress,
                        cancelled=cancelled,
                    )
                finally:
                    worker_repository.close()

            result = run_background_task(
                self,
                "Importing legacy data",
                merge,
            )
        except LegacyImportCancelled:
            return
        except (OSError, StorageError, ValueError) as error:
            QMessageBox.critical(self, "CSV import failed", str(error))
            return
        if result.already_imported:
            QMessageBox.information(
                self,
                "CSV data already imported",
                "This exact source snapshot was imported previously. No data changed.",
            )
            return
        self.load_month()
        closure_note = (
            f"\nClosed CSV months kept open because of local conflicts: "
            f"{result.closures_kept_open}."
            if result.closures_kept_open
            else ""
        )
        QMessageBox.information(
            self,
            "CSV import complete",
            f"New months: {result.months_created}\n"
            f"Existing months examined: {result.months_merged}\n"
            f"Days imported into SQLite: {result.days_imported}\n"
            f"Days kept from current SQLite data: {result.days_kept_current}\n"
            f"Unchanged/blank days: {result.days_unchanged}\n"
            f"Months imported as closed: {result.months_closed}"
            f"{closure_note}\n\n"
            f"CSV source preserved at:\n{result.source_root}",
        )

    def export_current_pdf(self):
        if self.repository is None:
            return
        stats = self.collect_statistics()
        suggested = f"{stats.year}_{stats.month}.pdf"
        destination = self._confirmed_export_path(
            "Export month PDF", suggested, "PDF files (*.pdf)"
        )
        if destination is None:
            return
        target, overwrite = destination
        try:
            from znactime.storage import pdf_export

            pdf_export.export_pdf(
                stats,
                target,
                overwrite=overwrite,
                protected_paths=sqlite_protected_paths(self.repository.path),
            )
        except (OSError, StorageError) as error:
            QMessageBox.warning(self, "Export failed", str(error))

    def backup_database(self):
        if self.repository is None:
            return
        suggested = datetime.now().strftime("znactime-backup-%Y%m%d-%H%M%S.db")
        destination = self._confirmed_export_path(
            "Back up database", suggested, "SQLite databases (*.db)"
        )
        if destination is None:
            return
        target, overwrite = destination
        try:
            database_path = self.repository.path

            def backup(*, progress, cancelled):
                worker_repository = SQLiteRepository(database_path)
                try:
                    worker_repository.backup_to(
                        target,
                        overwrite=overwrite,
                        progress=progress,
                        cancelled=cancelled,
                    )
                finally:
                    worker_repository.close()

            run_background_task(self, "Backing up database", backup)
        except LegacyImportCancelled:
            return
        except (OSError, StorageError) as error:
            QMessageBox.warning(self, "Backup failed", str(error))
            return
        QMessageBox.information(self, "Backup complete", f"Database backed up to:\n{target}")
