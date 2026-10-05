import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from znactime.core.models import MonthClosePreview
from znactime.storage.csv_export import month_rows
from znactime.storage.sqlite.repository import SQLiteRepository
from znactime.ui.qt import QApplication, QMessageBox, QPalette, QSettings
from znactime.ui.qt.app import TimeTrackerApp


class MonthLifecycleUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _window(repository, *, closed=False):
        return SimpleNamespace(
            repository=repository,
            month_closed=closed,
            header=SimpleNamespace(year=lambda: 2024, month=lambda: 6),
            _month_record=SimpleNamespace(revision=7),
            load_month=Mock(),
        )

    @patch("znactime.ui.qt.app.QMessageBox.information")
    @patch("znactime.ui.qt.app.QMessageBox.question")
    def test_close_confirmation_marks_unresolved_days_no_data_atomically(
        self, question, _information
    ):
        repository = Mock()
        repository.preview_month_close.return_value = MonthClosePreview(
            2024,
            6,
            60,
            120,
            (date(2024, 6, 3), date(2024, 6, 4)),
        )
        question.return_value = QMessageBox.StandardButton.Yes
        window = self._window(repository)

        TimeTrackerApp.close_month(window)

        self.assertIn("2 day(s) with planned work", question.call_args.args[2])
        self.assertIn("No data", question.call_args.args[2])
        repository.close_month.assert_called_once_with(
            2024,
            6,
            expected_revision=7,
            mark_unresolved_no_data=True,
        )
        window.load_month.assert_called_once_with()

    @patch("znactime.ui.qt.app.QMessageBox.information")
    @patch("znactime.ui.qt.app.QMessageBox.question")
    def test_reopen_warning_preserves_later_closed_months(self, question, _information):
        repository = Mock()
        question.return_value = QMessageBox.StandardButton.Yes
        window = self._window(repository, closed=True)

        TimeTrackerApp.reopen_month(window)

        self.assertIn("Later closed months will remain unchanged", question.call_args.args[2])
        repository.reopen_month.assert_called_once_with(
            2024,
            6,
            expected_revision=7,
        )
        window.load_month.assert_called_once_with()

    def test_month_navigation_displays_and_exports_carry_only_after_previous_closes(self):
        palette = QPalette(self.app.palette())
        with tempfile.TemporaryDirectory() as directory:
            repository = SQLiteRepository.create(Path(directory) / "app.db")
            window = None
            try:
                june = repository.get_or_create_month(2024, 6)
                day = june.days[2]
                repository.update_day(
                    day.work_date, expected_revision=day.revision,
                    start_minute=480, end_minute=1020, break_duration_minutes=30,
                    fields=frozenset(("start_minute", "end_minute", "break_duration_minutes")),
                )
                settings = QSettings(str(Path(directory) / "settings.ini"), QSettings.Format.IniFormat)
                window = TimeTrackerApp(repository=repository, settings=settings)
                window.header.set_period(2024, 7)
                window.load_month()
                self.assertEqual(window.header.carry_over_label.text(), "Carry over: 00:00")
                self.assertEqual(window.table.model.carry_over, 0)
                self.assertEqual(list(month_rows(window._month_record))[1][-1], "00:00")
                self.assertIsNone(repository.load_month(2024, 7))

                closed = repository.close_month(
                    2024, 6, expected_revision=june.revision, mark_unresolved_no_data=True,
                )
                window.load_month()
                self.assertEqual(window.header.carry_over_label.text(), "Carry over: 00:30")
                self.assertEqual(window.table.model.carry_over, 0.5)
                self.assertEqual(list(month_rows(window._month_record))[1][-1], "00:30")
                self.assertIsNone(repository.load_month(2024, 7))

                repository.reopen_month(2024, 6, expected_revision=closed.revision)
                window.load_month()
                self.assertEqual(window.header.carry_over_label.text(), "Carry over: 00:00")
                self.assertEqual(window.table.model.carry_over, 0)
            finally:
                if window is not None:
                    window.close()
                repository.close()
                self.app.setPalette(palette)


if __name__ == "__main__":
    unittest.main()
