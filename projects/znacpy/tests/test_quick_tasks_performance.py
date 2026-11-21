"""Regression checks for task progress without main-window presentation refreshes."""

import os
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QObject, QSettings
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

from znactime.storage.legacy_csv_import import LegacyImportCancelled
from znactime.storage.sqlite.repository import SQLiteRepository
from znactime.ui.quick.app import TimeTrackerApp
from znactime.ui.quick.layout import month_layout


class QuickTaskProgressTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        if not QFontDatabase.families():
            for filename in (
                "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/System/Library/Fonts/SFNS.ttf",
            ):
                if Path(filename).is_file():
                    identifier = QFontDatabase.addApplicationFont(filename)
                    families = QFontDatabase.applicationFontFamilies(identifier)
                    if families:
                        cls.app.setFont(QFont(families[0], 10))

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.repository = SQLiteRepository.create(root / "test.db")
        settings = QSettings(str(root / "settings.ini"), QSettings.IniFormat)
        settings.setValue("window/fit_height_to_rows", False)
        self.owner = TimeTrackerApp(
            self.repository, settings,
            clock=lambda: datetime(2024, 6, 17, 12, tzinfo=timezone.utc),
        )
        self.controller = self.owner.controller
        self.controller._timer.stop()  # Clock refreshes are outside this fixture.
        self.release_events = []
        self.dialog_hosts = []  # Retain borrowed QWindow wrappers until teardown.
        self.owner.show()
        QTest.qWait(60)
        self.dialog = self.owner.window.findChild(QObject, "taskProgressDialog")
        # Retain the QML content wrapper while inspecting its child controls.
        self.content = self.dialog.property("contentItem")
        content = self.content
        self.phase = next(item for item in content.findChildren(QObject)
                          if item.inherits("QQuickLabel"))
        self.bar = next(item for item in content.findChildren(QObject)
                        if item.inherits("QQuickProgressBar"))
        self.cancel_button = next(item for item in content.findChildren(QObject)
                                  if item.inherits("QQuickAbstractButton")
                                  and item.property("text") == "Cancel")

    def tearDown(self):
        for event in self.release_events:
            event.set()
        self.owner.shutdown()
        self.app.processEvents()
        self.repository.close()
        self.temporary.cleanup()
        self.assertEqual(self.owner.errors, [], "QML emitted runtime warnings")

    def event(self):
        event = threading.Event()
        self.release_events.append(event)
        return event

    def wait_until(self, condition):
        deadline = time.monotonic() + 5
        while not condition() and time.monotonic() < deadline:
            QTest.qWait(5)
        self.assertTrue(condition(), "Task/UI did not reach its expected state")

    def settle(self):
        self.app.processEvents()
        QTest.qWait(20)

    def test_worker_progress_updates_dialog_without_refreshing_month(self):
        self.assertFalse(self.controller._tasks._progress_timer.isActive())
        send_progress, finish = self.event(), self.event()
        worker_threads, delivery_threads = [], []
        successes, changed, data_changes, resets = [], [], [], []
        main_thread = threading.get_ident()

        def task(*, progress, cancelled):
            worker_threads.append(threading.get_ident())
            send_progress.wait()
            for completed in range(1, 26):
                progress("Reading records", completed, 25)
            finish.wait()
            return "finished"

        self.controller._start_task("Progress check", task, successes.append)
        self.wait_until(lambda: bool(worker_threads))
        self.settle()
        self.assertTrue(self.controller.state["busy"])
        self.assertTrue(self.dialog.property("visible"))
        year = self.owner.window.findChild(QObject, "yearSelector")
        self.assertFalse(year.property("enabled"))
        self.controller.changed.connect(lambda: changed.append(True))
        self.controller.monthModel.dataChanged.connect(lambda *_: data_changes.append(True))
        self.controller.monthModel.modelReset.connect(lambda: resets.append(True))
        # Observe the legacy path too, so the unmodified app reaches the actual
        # presentation-refresh assertion rather than failing on a missing API.
        progress_notify = getattr(self.controller, "progressChanged", self.controller.changed)
        progress_notify.connect(lambda: delivery_threads.append(threading.get_ident()))

        with patch("znactime.ui.quick.controller.month_layout", wraps=month_layout) as layout:
            send_progress.set()
            self.wait_until(lambda: self.bar.property("value") == 25)
            self.settle()
            layout.assert_not_called()
        self.assertEqual(changed, [], "Progress refreshed the main UI state")
        self.assertEqual(data_changes, [])
        self.assertEqual(resets, [])
        self.assertEqual(self.dialog.property("title"), "Progress check")
        self.assertEqual(self.phase.property("text"), "Reading records")
        self.assertEqual(self.bar.property("to"), 25)
        self.assertFalse(self.bar.property("indeterminate"))
        self.assertTrue(self.cancel_button.property("enabled"))
        self.assertNotEqual(worker_threads[0], main_thread)
        self.assertTrue(delivery_threads)
        self.assertEqual(set(delivery_threads), {main_thread})
        self.assertEqual(self.controller.progress, self.controller.state["progress"])

        finish.set()
        self.wait_until(lambda: not self.controller.state["busy"])
        self.assertEqual(successes, ["finished"])
        self.assertFalse(self.controller._tasks._progress_timer.isActive())
        self.assertFalse(self.dialog.property("visible"))
        self.assertTrue(year.property("enabled"))
        self.assertEqual(changed, [True], "Task completion must still notify busy-state changes")

    def test_next_task_resets_visible_title_phase_and_counts(self):
        finish_first, finish_second = self.event(), self.event()
        successes = []

        def first(*, progress, cancelled):
            progress("First phase", 3, 7)
            finish_first.wait()
            return "first"

        self.controller._start_task("First task", first, successes.append)
        self.wait_until(lambda: self.bar.property("value") == 3)
        finish_first.set()
        self.wait_until(lambda: not self.controller.state["busy"])

        def second(*, progress, cancelled):
            finish_second.wait()
            return "second"

        self.controller._start_task("Second task", second, successes.append)
        self.settle()
        self.assertTrue(self.dialog.property("visible"))
        self.assertEqual(self.dialog.property("title"), "Second task")
        self.assertEqual(self.phase.property("text"), "Starting…")
        self.assertEqual(self.bar.property("value"), 0)
        self.assertTrue(self.bar.property("indeterminate"))
        finish_second.set()
        self.wait_until(lambda: not self.controller.state["busy"])
        self.assertEqual(successes, ["first", "second"])

    def test_native_close_updates_cancelling_without_main_refresh(self):
        finish = self.event()
        changed, notices, successes = [], [], []

        def task(*, progress, cancelled):
            progress("Waiting", 1, 10)
            finish.wait()
            if cancelled():
                raise LegacyImportCancelled()
            return "unexpected success"

        self.controller._start_task("Cancel check", task, successes.append)
        self.wait_until(lambda: self.bar.property("value") == 1)
        self.settle()
        self.controller.changed.connect(lambda: changed.append(True))
        self.controller.notification.connect(lambda *values: notices.append(values))
        host = self.dialog.property("dialogWindow")
        self.dialog_hosts.append(host)
        with patch("znactime.ui.quick.controller.month_layout", wraps=month_layout) as layout:
            host.close()
            self.settle()
            self.assertEqual(self.phase.property("text"), "Cancelling…")
            self.assertFalse(self.cancel_button.property("enabled"))
            self.assertTrue(self.controller.state["busy"])
            self.assertEqual(changed, [])
            layout.assert_not_called()
        finish.set()
        self.wait_until(lambda: not self.controller.state["busy"])
        self.assertEqual(changed, [True])
        self.assertEqual(notices, [])
        self.assertEqual(successes, [])
        self.assertFalse(self.dialog.property("visible"))

    def test_worker_failure_still_restores_busy_state_and_reports_error(self):
        finish = self.event()
        notices, successes, changed = [], [], []

        def task(*, progress, cancelled):
            progress("Checking records", 2, 5)
            finish.wait()
            raise RuntimeError("Expected task failure")

        self.controller.notification.connect(lambda *values: notices.append(values))
        self.controller.changed.connect(lambda: changed.append(self.controller.state["busy"]))
        self.controller._start_task("Failure check", task, successes.append)
        self.wait_until(lambda: self.bar.property("value") == 2)
        finish.set()
        self.wait_until(lambda: not self.controller.state["busy"])
        self.assertEqual(changed, [True, False])
        self.assertEqual(successes, [])
        self.assertEqual(notices, [("Operation failed", "Expected task failure")])
        self.assertFalse(self.controller._tasks._progress_timer.isActive())
        self.assertFalse(self.dialog.property("visible"))
        notification = self.owner.window.findChild(QObject, "notificationDialog")
        self.assertTrue(notification.property("visible"))
        self.assertEqual(notification.property("message"), "Expected task failure")

    def test_progress_burst_delivers_only_the_latest_pending_value(self):
        send, produced, finish = self.event(), self.event(), self.event()
        updates = []

        def task(*, progress, cancelled):
            send.wait()
            for completed in range(1, 1001):
                progress("Reading burst", completed, 1000)
            produced.set()
            finish.wait()

        self.controller._start_task("Burst check", task, lambda _: None)
        self.settle()
        self.controller.progressChanged.connect(lambda: updates.append(dict(self.controller.progress)))
        send.set()
        # Hold GUI processing until the worker has produced the entire burst.
        self.assertTrue(produced.wait(2))
        self.wait_until(lambda: self.bar.property("value") == 1000)
        self.settle()
        self.assertEqual([update["completed"] for update in updates], [1000])
        self.assertEqual(self.phase.property("text"), "Reading burst")
        finish.set()
        self.wait_until(lambda: not self.controller.state["busy"])

    def test_pending_progress_cannot_overwrite_cancelling(self):
        send_late, produced, finish = self.event(), self.event(), self.event()

        def task(*, progress, cancelled):
            progress("Waiting", 1, 10)
            send_late.wait()
            progress("Late queued update", 9, 10)
            produced.set()
            finish.wait()
            if cancelled():
                raise LegacyImportCancelled()

        self.controller._start_task("Cancel queued progress", task, lambda _: None)
        self.wait_until(lambda: self.bar.property("value") == 1)
        send_late.set()
        self.assertTrue(produced.wait(1))
        self.controller.cancelTask()
        self.assertFalse(self.controller._tasks._progress_timer.isActive())
        expected = dict(self.controller.progress)
        QTest.qWait(150)
        self.assertEqual(self.controller.progress, expected)
        self.assertEqual(self.phase.property("text"), "Cancelling…")
        self.assertFalse(self.cancel_button.property("enabled"))
        self.assertEqual(self.bar.property("value"), 1)
        finish.set()
        self.wait_until(lambda: not self.controller.state["busy"])

    def test_retired_callback_cannot_update_completed_or_next_task(self):
        reporters, completed = [], []
        finish_second = self.event()

        def first(*, progress, cancelled):
            reporters.append(progress)
            progress("First final value", 3, 7)
            return "first"

        def capture(result):
            completed.append((result, dict(self.controller.progress)))

        self.controller._start_task("First task", first, capture)
        self.wait_until(lambda: not self.controller.state["busy"])
        self.assertEqual(completed[0][1]["completed"], 3)
        first_progress = dict(self.controller.progress)
        reporters[0]("After completion", 99, 100)
        self.settle()
        self.assertEqual(self.controller.progress, first_progress)

        def second(*, progress, cancelled):
            progress("Second phase", 1, 4)
            finish_second.wait()
            return "second"

        self.controller._start_task("Second task", second, capture)
        self.wait_until(lambda: self.phase.property("text") == "Second phase")
        second_progress = dict(self.controller.progress)
        reporters[0]("Retired first task", 100, 100)
        QTest.qWait(150)
        self.assertEqual(self.controller.progress, second_progress)
        self.assertEqual(self.dialog.property("title"), "Second task")
        finish_second.set()
        self.wait_until(lambda: not self.controller.state["busy"])
        self.assertEqual([result for result, _ in completed], ["first", "second"])

    def test_fast_failure_flushes_final_progress_before_notification(self):
        seen = []

        def task(*, progress, cancelled):
            progress("Last failure phase", 2, 5)
            raise RuntimeError("Expected fast failure")

        self.controller.notification.connect(
            lambda title, text: seen.append((title, text, dict(self.controller.progress)))
        )
        self.controller._start_task("Fast failure", task, lambda _: self.fail("Failure succeeded"))
        self.wait_until(lambda: not self.controller.state["busy"])
        self.assertEqual(seen[0][:2], ("Operation failed", "Expected fast failure"))
        self.assertEqual(seen[0][2]["phase"], "Last failure phase")
        self.assertEqual(seen[0][2]["completed"], 2)
        self.assertEqual(seen[0][2]["total"], 5)

    def test_success_callback_error_restores_controls_and_reports_notification(self):
        notices = []

        def task(*, progress, cancelled):
            progress("Final phase", 4, 4)
            return "completed"

        def completed(result):
            self.assertEqual(result, "completed")
            self.assertFalse(self.controller.state["busy"])
            raise ValueError("Expected result handling failure")

        self.controller.notification.connect(lambda *values: notices.append(values))
        self.controller._start_task("Result policy check", task, completed)
        self.wait_until(lambda: not self.controller.state["busy"])
        self.assertEqual(notices, [("Operation failed", "Expected result handling failure")])
        self.assertEqual(self.controller.progress["completed"], 4)
        self.assertFalse(self.dialog.property("visible"))
        self.assertTrue(self.owner.window.findChild(QObject, "yearSelector").property("enabled"))

    def test_progress_phases_and_totals_stay_coherent_while_running(self):
        next_phase, finish = self.event(), self.event()

        def task(*, progress, cancelled):
            progress("Hashing", 1, 5)
            next_phase.wait()
            progress("Parsing", 2, 3)
            finish.wait()

        self.controller._start_task("Phase check", task, lambda _: None)
        self.wait_until(lambda: self.phase.property("text") == "Hashing")
        self.assertEqual(self.bar.property("to"), 5)
        self.assertEqual(self.bar.property("value"), 1)
        next_phase.set()
        self.wait_until(lambda: self.phase.property("text") == "Parsing")
        self.assertEqual(self.bar.property("to"), 3)
        self.assertEqual(self.bar.property("value"), 2)
        finish.set()
        self.wait_until(lambda: not self.controller.state["busy"])

    def test_shutdown_discards_progress_and_disposes_running_task(self):
        reporters, successes = [], []

        def task(*, progress, cancelled):
            reporters.append(progress)
            progress("Working", 1, 10)
            while not cancelled():
                threading.Event().wait(0.001)
            raise LegacyImportCancelled()

        self.controller._start_task("Shutdown check", task, successes.append)
        self.wait_until(lambda: self.bar.property("value") == 1)
        runner = self.controller._tasks
        timer, thread = runner._progress_timer, runner._thread
        self.owner.shutdown()
        reporters[0]("After shutdown", 999, 1000)
        self.app.processEvents()
        self.assertFalse(isValid(runner))
        self.assertFalse(isValid(timer))
        self.assertFalse(isValid(thread))
        self.assertEqual(successes, [])
