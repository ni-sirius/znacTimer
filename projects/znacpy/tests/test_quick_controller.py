import os
import tempfile
import threading
import time
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, QUrl
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from znactime.core.models import DayEntry
from znactime.storage import csv_store
from znactime.storage.sqlite.repository import SQLiteRepository
from znactime.storage.legacy_csv_import import LegacyImportCancelled
from znactime.ui.quick.controller import ApplicationController
from znactime.ui.quick.model import QuickMonthModel


class QuickControllerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.path = self.root / "test.db"
        self.repository = SQLiteRepository.create(self.path)
        self.settings = QSettings(str(self.root / "settings.ini"), QSettings.IniFormat)
        self.now = datetime(2024, 6, 17, 8, 0, tzinfo=timezone.utc)
        self.controller = ApplicationController(self.repository, self.settings, clock=lambda: self.now)
        self.notices = []
        self.confirmations = []
        self.controller.notification.connect(lambda *args: self.notices.append(args))
        self.controller.confirmation.connect(lambda *args: self.confirmations.append(args))

    def tearDown(self):
        self.controller.shutdown()
        self.repository.close()
        self.temporary.cleanup()

    def answer(self, accepted=True):
        self.controller.answerConfirmation(self.confirmations[-1][2], accepted)

    def wait_task(self):
        deadline = time.monotonic() + 10
        while self.controller.state["busy"] and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertFalse(self.controller.state["busy"], "Background task did not finish")

    def test_navigation_is_read_only_and_crosses_years(self):
        self.assertIsNone(self.repository.load_month(2024, 6))
        self.controller.selectMonth(2024, 1)
        self.controller.navigate(-1)
        self.assertEqual((self.controller.state["year"], self.controller.state["month"]), (2023, 12))
        self.assertIsNone(self.repository.load_month(2023, 12))
        self.controller.showToday()
        self.assertEqual(self.controller.state["month"], 6)

    def test_navigation_publishes_one_fully_calculated_month(self):
        states = []
        resets = []
        data_changes = []
        model = self.controller.monthModel
        self.controller.changed.connect(lambda: states.append(self.controller.state))
        model.modelReset.connect(lambda: resets.append(model.entries()))
        model.dataChanged.connect(lambda *args: data_changes.append(args))
        self.controller.selectMonth(2024, 5)
        self.assertEqual(len(states), 1)
        self.assertEqual(len(resets), 1)
        self.assertEqual(data_changes, [], "Navigation recalculated rows after publishing them")
        self.assertEqual((states[0]["year"], states[0]["month"]), (2024, 5))
        self.assertEqual(len(resets[0]), 31)
        self.assertTrue(all(entry.cw and entry.row_color for entry in resets[0]))
        self.assertEqual(states[0]["balance"], resets[0][-1].monthly_balance)

    def test_edit_snapshot_rejects_reloaded_revision_and_allows_unchanged_day(self):
        self.controller.editCell(16, 2, "08:00")
        target = self.controller.beginCellEdit(16, 3)
        self.controller.tick()
        self.assertTrue(self.controller.commitCellEdit(target, "17:00"))
        target = self.controller.beginCellEdit(16, 3)
        self.controller.editCell(16, 2, "09:00")
        self.controller.load_month()
        self.assertFalse(self.controller.commitCellEdit(target, "18:00"))
        self.assertEqual(self.controller.cellValue(16, 3), "17:00")
        self.assertEqual(self.notices[-1][0], "Edit expired")

    def test_edits_persist_and_expected_end_is_never_saved(self):
        self.assertTrue(self.controller.editCell(16, 2, "08:00"))
        index = self.controller.monthModel.index(16, 3)
        badge = self.controller.monthModel.data(index, QuickMonthModel.BADGE)
        self.assertEqual(badge["state"], "expected")
        self.assertEqual(badge["texts"], ["16:00"])
        self.assertTrue(self.controller.monthModel.data(index, QuickMonthModel.TODAY))
        reopened = SQLiteRepository(self.path)
        try:
            day = reopened.load_month(2024, 6).days[16]
            self.assertEqual(day.start_minute, 480)
            self.assertIsNone(day.end_minute)
        finally:
            reopened.close()

    @patch("znactime.ui.qt.model.QMessageBox.warning", side_effect=AssertionError("Widgets dialog used"))
    def test_validation_errors_use_qml_signal_and_leave_data_intact(self, _warning):
        self.assertFalse(self.controller.editCell(16, 2, "25:00"))
        self.assertFalse(self.controller.editCell(16, 4, "nonsense"))
        self.assertEqual(len(self.notices), 2)
        self.assertIsNone(self.repository.load_month(2024, 6))

    def test_stale_revision_reloads_current_value_without_overwriting(self):
        self.controller.editCell(16, 2, "08:00")
        other = SQLiteRepository(self.path)
        try:
            day = other.load_month(2024, 6).days[16]
            other.update_day(day.work_date, expected_revision=day.revision,
                             fields=frozenset({"start_minute"}), start_minute=540)
            self.assertFalse(self.controller.editCell(16, 2, "10:00"))
            self.assertEqual(self.controller.cellValue(16, 2), "09:00")
            self.assertEqual(self.notices[-1][0], "Save conflict")
        finally:
            other.close()

    def test_start_pause_resume_stop_and_elapsed_time(self):
        self.controller.primaryAction()
        self.assertEqual(self.controller.state["workState"], "working")
        self.now = self.now.replace(hour=12)
        self.controller.primaryAction()
        self.assertEqual(self.controller.state["workState"], "paused")
        self.now = self.now.replace(hour=12, minute=30)
        self.assertIn("04:00 worked", self.controller.state["workMessage"])
        self.controller.primaryAction()
        self.assertEqual(self.controller.cellValue(16, 4), "12:00-12:30")
        self.now = self.now.replace(hour=17, minute=0)
        self.controller.stopWorkday()
        self.assertEqual(self.controller.state["workState"], "complete")
        self.assertIn("08:30 worked", self.controller.state["workMessage"])
        self.assertEqual(self.repository.load_month(2024, 6).days[16].end_minute, 1020)

    def test_duration_replacement_requires_confirmation(self):
        self.controller.editCell(16, 2, "08:00")
        self.controller.editCell(16, 4, "00:30")
        self.now = self.now.replace(hour=12)
        self.controller.primaryAction()
        self.assertEqual(self.confirmations[-1][0], "Replace interruption duration?")
        self.answer(False)
        self.assertEqual(self.controller.cellValue(16, 4), "00:30")
        self.controller.primaryAction()
        self.answer()
        self.assertEqual(self.controller.cellValue(16, 4), "12:00-...")

    def test_multiple_interruption_periods_preserve_identities(self):
        self.controller.editCell(16, 2, "08:00")
        self.assertTrue(self.controller.editCell(16, 4, "12:00-12:30;14:00-14:15"))
        before = self.repository.load_month(2024, 6).days[16].breaks
        self.assertTrue(self.controller.editCell(16, 4, "12:00-12:45;14:00-14:15"))
        after = self.repository.load_month(2024, 6).days[16].breaks
        self.assertEqual([p.public_id for p in before], [p.public_id for p in after])

    def test_close_cancel_close_reopen_and_read_only_roles(self):
        self.controller.closeMonth()
        self.assertIn("No data", self.confirmations[-1][1])
        self.answer(False)
        self.assertFalse(self.controller.state["closed"])
        self.controller.closeMonth()
        self.answer()
        self.assertTrue(self.controller.state["closed"])
        self.assertFalse(self.controller.editCell(16, 2, "08:00"))
        index = self.controller.monthModel.index(16, 2)
        self.assertFalse(self.controller.monthModel.data(index, QuickMonthModel.EDITABLE))
        self.controller.reopenMonth()
        self.answer()
        self.assertFalse(self.controller.state["closed"])
        self.assertTrue(self.controller.editCell(16, 2, "08:00"))

    def test_future_month_close_and_workday_actions_are_disabled(self):
        self.controller.navigate(1)
        self.controller.closeMonth()
        self.assertEqual(self.notices[-1][0], "Month close failed")
        self.assertEqual(self.confirmations, [])
        self.controller.primaryAction()
        self.assertEqual(self.controller.state["workState"], "unavailable")
        self.assertIsNone(self.repository.load_month(2024, 7))

    def test_close_confirmation_does_not_accept_stale_month_revision(self):
        self.controller.editCell(16, 2, "08:00")
        self.controller.editCell(16, 3, "16:00")
        self.controller.closeMonth()
        other = SQLiteRepository(self.path)
        try:
            day = other.load_month(2024, 6).days[16]
            other.update_day(day.work_date, expected_revision=day.revision,
                             fields=frozenset({"end_minute"}), end_minute=1020)
            self.answer()
            self.assertFalse(self.controller.state["closed"])
            self.assertEqual(self.controller.cellValue(16, 3), "17:00")
            self.assertEqual(self.notices[-1][0], "Operation failed")
        finally:
            other.close()

    def test_month_completion_offers_review_after_editor_finishes(self):
        self.controller.editCell(29, 2, "08:00")
        self.controller.editCell(29, 3, "16:00")
        self.assertEqual(self.confirmations, [])
        self.app.processEvents()
        self.assertEqual(self.confirmations[-1][0], "Ready to close the month?")
        self.answer()
        self.assertEqual(self.confirmations[-1][0], "Close Month")

    def test_midnight_rollover_changes_month_and_work_controls(self):
        self.now = datetime(2024, 7, 1, 0, 1, tzinfo=timezone.utc)
        self.controller.tick()
        self.assertEqual(self.controller.state["month"], 7)
        self.assertEqual(self.controller.state["workState"], "idle")

    def test_schedule_changes_update_expected_time_and_persist_setting(self):
        self.controller.scheduleSettings()
        self.assertTrue(self.controller.saveSchedule([420] * 5 + [0, 0], 60, False))
        self.controller.editCell(16, 2, "08:00")
        day = self.repository.load_month(2024, 6).days[16]
        self.assertEqual(day.expected_work_minutes, 420)
        self.assertFalse(self.controller.state["showExpectedEnd"])
        self.assertFalse(self.settings.value("work_schedule/show_expected_end", type=bool))

    def test_schedule_snapshot_rejects_concurrent_change(self):
        original = self.controller.scheduleSettings()
        item = self.repository.list_work_schedules()[-1]
        self.repository.replace_work_schedule(
            effective_from=date(2024, 6, 1), effective_to=None,
            weekday_minutes=(390,) * 5 + (0, 0), special_day_minutes=0,
            expected_public_id=item.public_id, expected_revision=item.revision,
        )
        self.assertFalse(self.controller.saveSchedule([420] * 5 + [0, 0], original["special"], True))
        self.assertEqual(self.notices[-1][0], "Schedule update failed")

    def test_clipboard_range_and_destination_checks(self):
        self.controller.editCell(16, 2, "08:00")
        self.controller.editCell(16, 3, "17:00")
        self.controller.copyCells(16, 2, 16, 3)
        self.assertEqual(self.app.clipboard().text(), "08:00\t17:00")
        self.assertTrue(self.controller.pasteCells(17, 2))
        self.assertEqual(self.controller.cellValue(17, 3), "17:00")
        self.assertFalse(self.controller.pasteCells(29, 4))
        self.assertEqual(self.controller.cellValue(29, 4), "00:00")

    def test_exports_csv_pdf_and_overwrite_cancellation(self):
        self.controller.editCell(16, 2, "08:00")
        for kind in ("csv", "pdf"):
            target = self.root / f"report.{kind}"
            self.controller.exportFile(kind, QUrl.fromLocalFile(str(target)))
            self.assertTrue(target.is_file())
            if kind == "pdf":
                self.assertTrue(target.read_bytes().startswith(b"%PDF"))
            target.write_bytes(b"keep me")
            self.controller.exportFile(kind, QUrl.fromLocalFile(str(target)))
            self.answer(False)
            self.assertEqual(target.read_bytes(), b"keep me")

    def test_export_cannot_overwrite_database_or_its_sidecars(self):
        before = self.path.read_bytes()
        for path in (self.path, Path(str(self.path) + "-wal"), Path(str(self.path) + "-shm")):
            self.controller.exportFile("csv", QUrl.fromLocalFile(str(path)))
            self.assertEqual(self.notices[-1][0], "Unsafe destination")
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.confirmations, [])

    def test_backup_uses_worker_connection_and_can_be_reopened(self):
        self.controller.editCell(16, 2, "08:00")
        target = self.root / "backup.db"
        self.controller.exportFile("backup", QUrl.fromLocalFile(str(target)))
        self.wait_task()
        backup = SQLiteRepository(target)
        try:
            self.assertEqual(backup.load_month(2024, 6).days[16].start_minute, 480)
        finally:
            backup.close()
        self.assertEqual(self.notices[-1][0], "Backup complete")

    def test_import_preflight_confirmation_and_merge_run_in_workers(self):
        source = self.root / "legacy"
        csv_store.save_month(2024, 6, [DayEntry("CW-25", "17.06.2024", "Normal day", "08:00", "16:00", "00:00")], data_dir=str(source))
        self.controller.importFolder(QUrl.fromLocalFile(str(source)))
        self.wait_task()
        self.assertEqual(self.confirmations[-1][0], "Confirm CSV import")
        self.assertIsNone(self.repository.load_month(2024, 6))
        self.answer()
        self.wait_task()
        self.assertEqual(self.repository.load_month(2024, 6).days[16].start_minute, 480)
        self.assertEqual(self.notices[-1][0], "CSV import complete")

    def test_theme_and_startup_settings_keep_existing_keys(self):
        self.controller.setTheme("dark")
        self.assertTrue(self.controller.state["dark"])
        self.controller.saveWindowSettings(False, 1100, 750)
        self.assertEqual(self.settings.value("appearance/color_scheme"), "dark")
        self.assertEqual(self.controller.state["initialWidth"], 1100)
        self.assertFalse(self.controller.state["fitHeight"])

    def test_cancelling_worker_finishes_without_error_notification(self):
        started = threading.Event()
        def task(*, progress, cancelled):
            started.set()
            while not cancelled():
                threading.Event().wait(0.001)
            raise LegacyImportCancelled()
        self.controller._start_task("Cancelable task", task, lambda _: self.fail("Cancelled task succeeded"))
        self.controller.cancelTask()
        self.wait_task()
        self.assertTrue(started.is_set())
        self.assertEqual(self.notices, [])


if __name__ == "__main__":
    unittest.main()
