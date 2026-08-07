import os
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from PySide6 import __version__ as PYSIDE_VERSION

from znactime.config import DEFAULT_DAY_HOURS, VERSION
from znactime.core.calendar_utils import build_calendar_week_text
from znactime.core.calculator import recalculate as recalculate_entries
from znactime.core.models import MonthStats
from znactime.core.time_utils import (
    append_interruption_period,
    finish_interruption_period,
    hours_to_hhmm,
    parse_interruption_input,
)
from znactime.storage import csv_store, paths
from znactime.ui.qt import (
    QApplication,
    QIcon,
    QMainWindow,
    QMessageBox,
    QPalette,
    QPixmap,
    QTimer,
    QVBoxLayout,
    QWidget,
    Qt,
)
from znactime.ui.qt.header import HeaderWidget
from znactime.ui.qt.menu import MenuBar
from znactime.ui.qt.player import (
    PAUSE_DATE_KEY,
    PAUSE_START_KEY,
    SESSION_DATE_KEY,
    SESSION_START_KEY,
    WorkdayBar,
)
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
    dialog.setWindowTitle("About znacTime")
    dialog.setWindowIcon(QIcon(str(APP_ICON_PATH)))
    dialog.setTextFormat(Qt.TextFormat.RichText)
    dialog.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
    dialog.setText(
        "<h2>znacTime</h2>"
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
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"znacTime v{VERSION}")
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
        self.resize(initial_width, initial_height)

        self.menu = MenuBar(
            self,
            close_month_command=self.close_month,
            appearance_command=self.open_appearance_settings,
            work_schedule_command=self.open_work_schedule_settings,
            about_command=self.show_about,
        )
        self.setMenuBar(self.menu)

        self.header = HeaderWidget(self)
        now = datetime.now()
        self._current_date = now.date()
        self.header.set_year(now.year)
        self.header.set_month(now.month)
        self.header.selectionChanged.connect(self.load_month)

        self.table = TableWidget(self)
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
        dialog = WorkScheduleDialog(
            self,
            self.theme_controller.settings,
        )
        dialog.exec()
        self._apply_work_schedule_settings()

    def show_about(self):
        create_about_dialog(self).exec()

    def _apply_work_schedule_settings(self):
        day_hours, show_expected_end = load_work_schedule_settings(
            self.theme_controller.settings
        )
        if (
            day_hours == self.day_hours
            and show_expected_end == self.show_expected_end
        ):
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
        dark = (
            QApplication.palette().color(QPalette.ColorRole.Window).lightness()
            < 128
        )
        background = "#19171f" if dark else "#f1edf8"
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
        self.month_closed = csv_store.is_month_closed(year, month)
        self.carry_over = csv_store.get_carry_over(year, month)

        self.header.set_carry_over_text(f"Carry over: {hours_to_hhmm(self.carry_over)}")
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
        self.table.set_entries(csv_store.load_month(year, month))
        self.table.recalculate(today=datetime.today().date(), autosave=False)
        self.table.set_month_closed(self.month_closed)
        self.menu.set_month_closed(self.month_closed)
        self.refresh_workday_bar()

    def _today_entry(self, now=None):
        if now is None:
            now = datetime.now()
        if self.header.year() != now.year or self.header.month() != now.month:
            return None
        return self.table.entry_for_date(now.strftime("%d.%m.%Y"))

    def _active_pause(self, now=None):
        if now is None:
            now = datetime.now()
        settings = self.theme_controller.settings
        pause_date = settings.value(PAUSE_DATE_KEY, "", type=str)
        pause_start = settings.value(PAUSE_START_KEY, "", type=str)
        today_text = now.strftime("%d.%m.%Y")
        if pause_date and pause_date != today_text:
            self._clear_active_pause()
            return None
        return pause_start or None

    def _set_active_pause(self, date_text, start_text):
        settings = self.theme_controller.settings
        settings.setValue(PAUSE_DATE_KEY, date_text)
        settings.setValue(PAUSE_START_KEY, start_text)
        settings.sync()

    def _clear_active_pause(self):
        settings = self.theme_controller.settings
        settings.remove(PAUSE_DATE_KEY)
        settings.remove(PAUSE_START_KEY)
        settings.sync()

    def _active_session(self, now=None):
        if now is None:
            now = datetime.now()
        settings = self.theme_controller.settings
        session_date = settings.value(SESSION_DATE_KEY, "", type=str)
        session_start = settings.value(SESSION_START_KEY, "", type=str)
        today_text = now.strftime("%d.%m.%Y")
        if session_date and session_date != today_text:
            self._clear_active_session()
            return None
        return session_start or None

    def _set_active_session(self, date_text, start_text):
        settings = self.theme_controller.settings
        settings.setValue(SESSION_DATE_KEY, date_text)
        settings.setValue(SESSION_START_KEY, start_text)
        settings.sync()

    def _clear_active_session(self):
        settings = self.theme_controller.settings
        settings.remove(SESSION_DATE_KEY)
        settings.remove(SESSION_START_KEY)
        settings.sync()
        self._clear_active_pause()

    def _finalize_stale_session(self, now=None):
        if now is None:
            now = datetime.now()

        settings = self.theme_controller.settings
        session_date_text = settings.value(SESSION_DATE_KEY, "", type=str)
        session_start = settings.value(SESSION_START_KEY, "", type=str)
        if not session_date_text or not session_start:
            return False

        try:
            session_date = datetime.strptime(
                session_date_text,
                "%d.%m.%Y",
            ).date()
        except ValueError:
            self._clear_active_session()
            return False

        if session_date >= now.date():
            return False

        pause_date = settings.value(PAUSE_DATE_KEY, "", type=str)
        pause_start = settings.value(PAUSE_START_KEY, "", type=str)
        displayed_entry = self.table.entry_for_date(session_date_text)
        displayed_period_matches = (
            self.header.year() == session_date.year
            and self.header.month() == session_date.month
        )

        updated = False
        if displayed_period_matches and displayed_entry is not None:
            changes = self._stale_session_changes(
                displayed_entry,
                session_start,
                pause_date,
                pause_start,
            )
            if changes:
                updated = self.table.update_entry_for_date(
                    session_date_text,
                    **changes,
                )
        elif not csv_store.is_month_closed(session_date.year, session_date.month):
            entries = csv_store.load_month(session_date.year, session_date.month)
            for position, entry in enumerate(entries):
                if entry.date != session_date_text:
                    continue
                changes = self._stale_session_changes(
                    entry,
                    session_start,
                    pause_date,
                    pause_start,
                )
                if not changes:
                    break
                entries[position] = replace(entry, **changes)
                entries = recalculate_entries(
                    entries,
                    carry_over=csv_store.get_carry_over(
                        session_date.year,
                        session_date.month,
                    ),
                    day_hours=getattr(
                        self,
                        "day_hours",
                        DEFAULT_DAY_HOURS,
                    ),
                    today=now.date(),
                    month_closed=False,
                )
                csv_store.save_month(session_date.year, session_date.month, entries)
                updated = True
                break

        self._clear_active_session()
        return updated

    def _stale_session_changes(
        self,
        entry,
        session_start,
        pause_date,
        pause_start,
    ):
        if entry.end != "00:00":
            return {}

        changes = {
            "start": entry.start if entry.start != "00:00" else session_start,
            "end": "23:59",
        }
        if pause_date != entry.date or not pause_start or pause_start >= "23:59":
            return changes

        interruption = entry.interruption
        if interruption not in ("", "00:00") and "-" not in interruption:
            return changes
        try:
            changes["interruption"] = finish_interruption_period(
                interruption,
                pause_start,
                "23:59",
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
                "unavailable",
                message="Open the current, unlocked month to use workday controls",
            )
            return

        pause_start = self._active_pause(now)
        session_start = self._active_session(now)
        if entry.start == "00:00":
            self._clear_active_session()
            self.workday_bar.set_state("idle")
        elif entry.end != "00:00":
            self._clear_active_session()
            self.workday_bar.set_state(
                "complete",
                start=entry.start,
                end=entry.end,
            )
        else:
            if session_start != entry.start:
                self._clear_active_session()
                self._set_active_session(entry.date, entry.start)
                pause_start = None

            if pause_start:
                interruption = parse_interruption_input(entry.interruption)
                open_pause_start = None
                if interruption is not None and interruption.has_incomplete:
                    open_period = next(
                        period
                        for period in interruption.normalized.split(";")
                        if period.endswith("-...")
                    )
                    open_pause_start = open_period.removesuffix("-...")

                if open_pause_start is None:
                    self._clear_active_pause()
                    pause_start = None
                elif open_pause_start != pause_start:
                    self._set_active_pause(entry.date, open_pause_start)
                    pause_start = open_pause_start

            if pause_start:
                self.workday_bar.set_state(
                    "paused",
                    start=entry.start,
                    pause_start=pause_start,
                )
                return
            self.workday_bar.set_state(
                "working",
                start=entry.start,
            )

    def on_workday_primary(self):
        now = datetime.now()
        entry = self._today_entry(now)
        if self.month_closed or entry is None:
            return

        date_text = now.strftime("%d.%m.%Y")
        time_text = now.strftime("%H:%M")
        pause_start = self._active_pause(now)

        if entry.start == "00:00":
            if entry.end != "00:00":
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
                end="00:00",
            )
        elif pause_start:
            if not self._finish_active_pause(entry, time_text):
                return
        elif entry.end == "00:00":
            if not self._start_active_pause(entry, date_text, time_text):
                return

        self.refresh_workday_bar(now)

    def _start_active_pause(self, entry, date_text, start_text):
        interruption = entry.interruption
        if interruption not in ("", "00:00") and "-" not in interruption:
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
            interruption = "00:00"

        try:
            interruption = append_interruption_period(
                interruption,
                start_text,
                "...",
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
        if interruption not in ("", "00:00") and "-" not in interruption:
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
            interruption = "00:00"

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
        if self.month_closed or entry is None or entry.start == "00:00":
            return

        end_text = now.strftime("%H:%M")
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

        answer = QMessageBox.question(
            self,
            "Close Month",
            "Close this month and generate PDF report?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        stats = self.collect_statistics()
        csv_store.append_year_summary(stats)
        self.export_pdf(stats)
        csv_store.mark_month_closed(self.header.year(), self.header.month())

        self.month_closed = True
        self.table.set_context(
            year=self.header.year(),
            month=self.header.month(),
            carry_over=self.carry_over,
            day_hours=self.day_hours,
            month_closed=True,
            show_expected_end=self.show_expected_end,
        )
        self.table.recalculate(today=datetime.today().date(), autosave=False)
        self.table.set_month_closed(True)
        self.menu.set_month_closed(True)
        self.refresh_workday_bar()

        QMessageBox.information(self, "Month closed", "Month successfully closed.")

    def collect_statistics(self):
        return MonthStats(
            year=self.header.year(),
            month=self.header.month_name(),
            overtime=self.table.final_balance_hours(),
        )

    def export_pdf(self, stats):
        from znactime.storage import pdf_export

        pdf_name = os.path.join(
            paths.year_dir(stats.year, create=True),
            f"{stats.year}_{stats.month}.pdf",
        )
        pdf_export.export_pdf(stats, pdf_name)
