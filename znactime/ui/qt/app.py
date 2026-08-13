import os
from datetime import datetime
from pathlib import Path

from PySide6 import __version__ as PYSIDE_VERSION

from znactime.config import APP_NAME, VERSION
from znactime.core.calendar_utils import build_calendar_week_text
from znactime.core.constants import (
    DATE_FORMAT,
    END_OF_DAY,
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
from znactime.storage.errors import StorageError
from znactime.storage.legacy_csv_import import preflight_legacy_data
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
from znactime.ui.qt.repository_mapper import minute_text, parse_display_date
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
            applicable = [
                item for item in self.repository.list_work_schedules()
                if item.effective_from <= today
                and (item.effective_to is None or item.effective_to >= today)
            ]
            if applicable:
                self.day_hours = applicable[-1].weekday_minutes[today.weekday()] / 60
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

        self._finalize_stale_session(now)
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
        initial_minutes = None
        if self.repository is not None and self._month_record is not None:
            today = datetime.today().date()
            current = next(
                (item for item in self._month_record.days if item.work_date == today),
                self._month_record.days[0] if self._month_record.days else None,
            )
            initial_minutes = current.expected_work_minutes if current else None
        dialog = WorkScheduleDialog(
            self,
            self.theme_controller.settings,
            initial_workday_minutes=initial_minutes,
            persist_workday=self.repository is None,
        )
        dialog.exec()
        self._apply_work_schedule_settings(
            day_hours=dialog.schedule_widget.day_minutes() / 60,
            show_expected_end=dialog.schedule_widget.show_expected_end(),
        )

    def show_about(self):
        create_about_dialog(self).exec()

    def _apply_work_schedule_settings(self, day_hours=None, show_expected_end=None):
        if day_hours is None or show_expected_end is None:
            day_hours, show_expected_end = load_work_schedule_settings(
                self.theme_controller.settings
            )
        if (
            day_hours == self.day_hours
            and show_expected_end == self.show_expected_end
        ):
            return
        day_hours_changed = day_hours != self.day_hours
        if getattr(self, "repository", None) is not None and day_hours_changed:
            try:
                self.repository.replace_work_schedule(
                    effective_from=datetime.today().date(),
                    effective_to=None,
                    weekday_minutes=(round(day_hours * 60),) * 7,
                )
            except StorageError as error:
                QMessageBox.warning(self, "Schedule update failed", str(error))
                return
            self.day_hours = day_hours
            self.show_expected_end = show_expected_end
            self.load_month()
            return
        self.day_hours = day_hours
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
        )

    def _check_today_rollover(self, now=None):
        if now is None:
            now = datetime.now()

        today = now.date()
        if today == self._current_date:
            return

        self._finalize_stale_session(now)
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
            record = self.repository.get_or_create_month(year, month)
        except StorageError as error:
            QMessageBox.critical(self, "Database error", str(error))
            return
        self._month_record = record
        self.month_closed = record.status == "closed"
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

    def _today_entry(self, now=None):
        if now is None:
            now = datetime.now()
        if self.header.year() != now.year or self.header.month() != now.month:
            return None
        return self.table.entry_for_date(now.strftime(DATE_FORMAT))

    def _active_pause(self, now=None):
        if getattr(self, "repository", None) is not None:
            active = self.repository.load_active_workday()
            if active is None:
                return None
            record = self.repository.load_month(active.work_date.year, active.work_date.month)
            day = next(item for item in record.days if item.work_date == active.work_date)
            pause = next((item for item in day.breaks if item.end_minute is None), None)
            return minute_text(pause.start_minute) if pause else None
        return None

    def _set_active_pause(self, date_text, start_text):
        return None

    def _clear_active_pause(self):
        return None

    def _active_session(self, now=None):
        if getattr(self, "repository", None) is not None:
            active = self.repository.load_active_workday()
            if active is None:
                return None
            record = self.repository.load_month(active.work_date.year, active.work_date.month)
            day = next(item for item in record.days if item.work_date == active.work_date)
            return minute_text(day.start_minute)
        return None

    def _set_active_session(self, date_text, start_text):
        return None

    def _clear_active_session(self):
        return None

    def _finalize_stale_session(self, now=None):
        if now is None:
            now = datetime.now()
        if getattr(self, "repository", None) is not None:
            try:
                updated = self.repository.finalize_stale_workday(now.date(), now)
            except StorageError as error:
                QMessageBox.warning(self, "Workday recovery failed", str(error))
                return False
            if updated is not None:
                self.load_month()
                return True
            return False
        return False

    def _stale_session_changes(
        self,
        entry,
        session_start,
        pause_date,
        pause_start,
    ):
        if entry.end != UNSET_TIME:
            return {}

        changes = {
            "start": entry.start if entry.start != UNSET_TIME else session_start,
            "end": END_OF_DAY,
        }
        if pause_date != entry.date or not pause_start or pause_start >= END_OF_DAY:
            return changes

        interruption = entry.interruption
        if (
            interruption not in ("", ZERO_DURATION)
            and PERIOD_SEPARATOR not in interruption
        ):
            return changes
        try:
            changes["interruption"] = finish_interruption_period(
                interruption,
                pause_start,
                END_OF_DAY,
            )
        except ValueError:
            pass
        return changes

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
        session_start = self._active_session(now)
        if entry.start == UNSET_TIME:
            self._clear_active_session()
            self.workday_bar.set_state(WorkdayState.IDLE)
        elif entry.end != UNSET_TIME:
            self._clear_active_session()
            self.workday_bar.set_state(
                WorkdayState.COMPLETE,
                start=entry.start,
                end=entry.end,
            )
        else:
            if session_start != entry.start:
                self._clear_active_session()
                self._set_active_session(entry.date, entry.start)
                pause_start = None

            if pause_start:
                open_pause_start = open_interruption_start(entry.interruption)

                if open_pause_start is None:
                    self._clear_active_pause()
                    pause_start = None
                elif open_pause_start != pause_start:
                    self._set_active_pause(entry.date, open_pause_start)
                    pause_start = open_pause_start

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
        now = datetime.now()
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
                    self.repository.start_pause(work_date, minute, now)
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
            self._clear_active_session()
            self._set_active_session(date_text, time_text)
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
        if updated:
            self._set_active_pause(date_text, start_text)
        return updated

    def _finish_active_pause(self, entry, end_text):
        pause_start = self._active_pause()
        if pause_start is None:
            return True
        if entry is None:
            self._clear_active_pause()
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
        if updated:
            self._clear_active_pause()
        return updated

    def stop_workday(self):
        now = datetime.now()
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
        if end_text < entry.start:
            return

        if self._active_pause(now):
            if not self._finish_active_pause(entry, end_text):
                return
            entry = self._today_entry(now)

        self.table.update_entry_for_date(entry.date, end=end_text)
        self._clear_active_session()
        self.refresh_workday_bar(now)

    def close_month(self):
        if self.month_closed:
            QMessageBox.information(self, "Month closed", "This month is already closed.")
            return

        close_text = (
            "Close this month? CSV and PDF export remain separate actions."
            if getattr(self, "repository", None) is not None
            else "Close this month and generate PDF report?"
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

        if getattr(self, "repository", None) is not None:
            try:
                self.repository.close_month(
                    self.header.year(),
                    self.header.month(),
                    expected_revision=self._month_record.revision,
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
            return

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
        if os.path.exists(path):
            answer = QMessageBox.question(
                self,
                "Replace export?",
                f"{path} already exists. Replace it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return None
        return path

    def export_month_csv(self):
        if self.repository is None or self._month_record is None:
            return
        suggested = f"{self.header.year()}_tmp_{self.header.month():02}.csv"
        target = self._confirmed_export_path(
            "Export month CSV", suggested, "CSV files (*.csv)"
        )
        if target is None:
            return
        try:
            from znactime.storage.csv_export import export_month

            export_month(self._month_record, target, overwrite=True)
        except OSError as error:
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
            preflight = preflight_legacy_data(source)
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
            "per-day work limits, and active timer state will not be overwritten. "
            "Only untouched calendar-day placeholders and missing months may receive "
            "CSV data. Source files will not be changed.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            result = self.repository.merge_legacy(preflight)
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
        target = self._confirmed_export_path(
            "Export month PDF", suggested, "PDF files (*.pdf)"
        )
        if target is None:
            return
        try:
            from znactime.storage import pdf_export

            pdf_export.export_pdf(stats, target)
        except OSError as error:
            QMessageBox.warning(self, "Export failed", str(error))

    def backup_database(self):
        if self.repository is None:
            return
        suggested = datetime.now().strftime("znactime-backup-%Y%m%d-%H%M%S.db")
        target = self._confirmed_export_path(
            "Back up database", suggested, "SQLite databases (*.db)"
        )
        if target is None:
            return
        try:
            self.repository.backup_to(target, overwrite=True)
        except (OSError, StorageError) as error:
            QMessageBox.warning(self, "Backup failed", str(error))
            return
        QMessageBox.information(self, "Backup complete", f"Database backed up to:\n{target}")
