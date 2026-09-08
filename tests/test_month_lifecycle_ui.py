import os
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from znactime.core.models import MonthClosePreview
from znactime.ui.qt import QApplication, QMessageBox
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


if __name__ == "__main__":
    unittest.main()
