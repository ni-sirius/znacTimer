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

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QSettings
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

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
        # Dispose this fixture's remaining QObjects; production ownership is
        # deliberately unchanged by the task-notification change.
        self.controller.theme.deleteLater()
        self.controller.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
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
        self.assertFalse(self.dialog.property("visible"))
        notification = self.owner.window.findChild(QObject, "notificationDialog")
        self.assertTrue(notification.property("visible"))
        self.assertEqual(notification.property("message"), "Expected task failure")
