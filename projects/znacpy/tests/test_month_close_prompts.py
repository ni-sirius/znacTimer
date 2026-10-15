import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent

from znactime.storage.sqlite.repository import SQLiteRepository
from znactime.ui.qt import QApplication, QMessageBox, QPalette, QSettings, Qt
from znactime.ui.qt.app import TimeTrackerApp
from znactime.ui.table_schema import Column


class MonthClosePromptTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.repository = SQLiteRepository.create(root / "app.db")
        self.addCleanup(self.repository.close)
        palette = QPalette(self.app.palette())
        self.addCleanup(self.app.setPalette, palette)
        for name, result in (
            ("question", QMessageBox.StandardButton.No),
            ("information", None), ("warning", None),
        ):
            patched = patch(f"znactime.ui.qt.app.QMessageBox.{name}", return_value=result)
            setattr(self, name, patched.start())
            self.addCleanup(patched.stop)
        settings = QSettings(str(root / "settings.ini"), QSettings.Format.IniFormat)
        self.window = TimeTrackerApp(repository=self.repository, settings=settings)
        self.addCleanup(self.close_window)
        self.select_month(2024, 6)

    def close_window(self):
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def select_month(self, year, month):
        self.repository.get_or_create_month(year, month)
        self.window.header.set_period(year, month)
        self.window.load_month()
        self.app.processEvents()

    def edit(self, day, column, value):
        return self.window.table.model.setData(
            self.window.table.model.index(day - 1, column), value, Qt.ItemDataRole.EditRole,
        )

    def fill_other_planned_days(self, *, except_days=()):
        year, month = self.window.header.year(), self.window.header.month()
        record = self.repository.load_month(year, month)
        for day in record.days:
            if day.expected_work_minutes > 0 and day.work_date.day not in except_days:
                self.repository.update_day(
                    day.work_date, expected_revision=day.revision,
                    start_minute=480, end_minute=1020, break_duration_minutes=60,
                    fields=frozenset(("start_minute", "end_minute", "break_duration_minutes")),
                )
        self.window.load_month()

    def enter_last_calendar_end(self):
        self.assertTrue(self.edit(30, Column.START, "08:00"))
        self.assertTrue(self.edit(30, Column.END, "17:00"))

    def test_last_calendar_end_offers_close_despite_other_empty_days(self):
        for month, last_day in ((2, 29), (6, 30), (7, 31)):
            with self.subTest(month=month, last_day=last_day):
                self.select_month(2024, month)
                self.question.reset_mock()
                self.assertTrue(self.edit(last_day, Column.START, "08:00"))
                self.assertTrue(self.edit(last_day, Column.END, "17:00"))
                # The saved edit returns before any modal confirmation appears.
                self.question.assert_not_called()
                self.app.processEvents()

                self.assertEqual(self.question.call_count, 1)
                self.assertEqual(self.question.call_args.args[1], "Ready to close the month?")
                self.assertIn("last calendar day", self.question.call_args.args[2])
                self.assertIn("Would you like to review and close it now?", self.question.call_args.args[2])
                self.assertEqual(self.question.call_args.args[4], QMessageBox.StandardButton.No)
                self.assertEqual(self.repository.load_month(2024, month).status, "open")

    def test_completing_last_unfilled_workday_offers_close_before_calendar_end(self):
        self.fill_other_planned_days(except_days=(17,))
        self.assertTrue(self.edit(17, Column.START, "08:00"))
        self.app.processEvents()
        self.question.assert_not_called()

        self.assertTrue(self.edit(17, Column.END, "17:00"))
        self.app.processEvents()

        self.assertEqual(self.question.call_count, 1)
        self.assertIn("last unfinished workday", self.question.call_args.args[2])

    def test_programmatic_stop_update_also_offers_close(self):
        self.fill_other_planned_days(except_days=(17,))
        self.assertTrue(self.window.table.update_entry_for_date("17.06.2024", start="08:00"))
        self.assertTrue(self.window.table.update_entry_for_date("17.06.2024", end="17:00"))
        self.app.processEvents()

        self.assertEqual(self.question.call_count, 1)

    def test_both_milestones_in_one_edit_show_only_one_suggestion(self):
        self.fill_other_planned_days()
        self.enter_last_calendar_end()
        self.app.processEvents()

        self.assertEqual(self.question.call_count, 1)

    def test_accepting_closes_month_through_existing_flow(self):
        self.question.return_value = QMessageBox.StandardButton.Yes
        self.enter_last_calendar_end()
        self.app.processEvents()

        record = self.repository.load_month(2024, 6)
        self.assertEqual(self.question.call_count, 2)
        suggestion, confirmation = self.question.call_args_list
        self.assertEqual(suggestion.args[1], "Ready to close the month?")
        self.assertEqual(confirmation.args[1], "Close Month")
        self.assertIn("with planned work have no work times", confirmation.args[2])
        self.assertEqual(record.status, "closed")
        self.assertEqual(record.days[29].end_minute, 1020)
        self.assertEqual(record.days[2].special_day, "No data")
        self.assertTrue(self.window.month_closed)
        self.assertEqual(self.window.header.month_lock_icon.accessibleName(), "Month closed")

    def test_accepting_suggestion_then_declining_confirmation_keeps_month_open(self):
        self.question.side_effect = [QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No]
        self.enter_last_calendar_end()
        self.app.processEvents()

        self.assertEqual(self.question.call_count, 2)
        self.assertEqual(self.question.call_args.args[1], "Close Month")
        record = self.repository.load_month(2024, 6)
        self.assertEqual(record.status, "open")
        self.assertEqual(record.days[29].end_minute, 1020)
        self.assertNotEqual(record.days[2].special_day, "No data")
        self.assertFalse(self.window.month_closed)

    def test_partial_month_edits_and_failed_saves_do_not_prompt(self):
        self.assertFalse(self.edit(30, Column.END, "17:00"))
        self.assertTrue(self.edit(17, Column.START, "08:00"))
        self.assertFalse(self.edit(17, Column.END, "08:00"))
        self.assertTrue(self.edit(17, Column.END, "17:00"))
        self.app.processEvents()

        self.question.assert_not_called()

    def test_reloading_or_editing_already_complete_days_does_not_prompt(self):
        self.fill_other_planned_days()
        self.window.load_month()
        self.window.table.refresh_theme()
        self.assertTrue(self.edit(17, Column.END, "17:00"))
        self.assertTrue(self.edit(17, Column.END, "17:30"))
        self.app.processEvents()

        self.question.assert_not_called()

    def test_navigation_cancels_pending_close_offer(self):
        self.enter_last_calendar_end()
        self.select_month(2024, 7)
        self.app.processEvents()

        self.question.assert_not_called()

    def test_clearing_the_triggering_end_time_cancels_the_offer(self):
        self.enter_last_calendar_end()
        self.assertTrue(self.edit(30, Column.END, ""))
        self.app.processEvents()

        self.question.assert_not_called()

    def test_manual_close_consumes_pending_automatic_offer(self):
        self.enter_last_calendar_end()
        self.window.close_month()
        self.app.processEvents()

        self.assertEqual(self.question.call_count, 1)
        self.assertEqual(self.question.call_args.args[1], "Close Month")

    def test_closing_window_cancels_pending_offer(self):
        self.enter_last_calendar_end()
        self.window.close()
        self.app.processEvents()

        self.question.assert_not_called()

    def test_future_month_does_not_offer_an_unavailable_close(self):
        self.select_month(date.today().year + 1, 1)
        self.assertTrue(self.edit(31, Column.START, "08:00"))
        self.assertTrue(self.edit(31, Column.END, "17:00"))
        self.app.processEvents()

        self.question.assert_not_called()


if __name__ == "__main__":
    unittest.main()
