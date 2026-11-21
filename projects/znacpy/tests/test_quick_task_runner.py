"""Task-runner contracts independent of the month controller and QML engine."""

import os
import threading
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QCoreApplication, QEvent, QObject
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from znactime.ui.quick.tasks.runner import TaskRunner


class QuickTaskRunnerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.parent = QObject()
        self.runner = TaskRunner(self.parent)
        self.release_events = []

    def tearDown(self):
        for event in self.release_events:
            event.set()
        self.runner.shutdown()
        self.app.processEvents()
        self.parent.deleteLater()
        QCoreApplication.sendPostedEvents(self.parent, QEvent.Type.DeferredDelete)

    def event(self):
        event = threading.Event()
        self.release_events.append(event)
        return event

    def wait_until(self, condition):
        deadline = time.monotonic() + 3
        while not condition() and time.monotonic() < deadline:
            QTest.qWait(5)
        self.assertTrue(condition(), "Runner did not reach the expected state")

    def test_success_delivers_final_snapshot_on_gui_thread_after_busy_clears(self):
        worker_threads, delivery_threads, states, results = [], [], [], []
        main_thread = threading.get_ident()
        self.runner.busyChanged.connect(lambda: states.append(self.runner.busy))
        self.runner.progressChanged.connect(lambda: delivery_threads.append(threading.get_ident()))

        def task(*, progress, cancelled):
            worker_threads.append(threading.get_ident())
            progress("Final phase", 4, 7)
            return "result"

        def completed(result):
            results.append((result, self.runner.busy, self.runner.progress, threading.get_ident()))

        self.assertTrue(self.runner.start("Standalone task", task, completed))
        self.wait_until(lambda: bool(results))
        self.assertEqual(states, [True, False])
        self.assertNotEqual(worker_threads[0], main_thread)
        self.assertEqual(set(delivery_threads), {main_thread})
        self.assertEqual(results[0], (
            "result", False,
            {"title": "Standalone task", "phase": "Final phase", "completed": 4, "total": 7},
            main_thread,
        ))
        self.assertFalse(self.runner._progress_timer.isActive())
        results[0][2]["phase"] = "Changed by caller"
        self.assertEqual(self.runner.progress["phase"], "Final phase")

    def test_overlapping_and_post_shutdown_tasks_are_rejected(self):
        finish = self.event()
        completed, unexpected = [], []

        def task(*, progress, cancelled):
            progress("Waiting", 1, 2)
            finish.wait()
            return "first"

        def rejected(**_):
            unexpected.append(True)

        self.assertTrue(self.runner.start("First", task, completed.append))
        self.wait_until(lambda: self.runner.progress["completed"] == 1)
        before = self.runner.progress
        self.assertFalse(self.runner.start("Overlapping", rejected, completed.append))
        self.assertEqual(self.runner.progress, before)
        finish.set()
        self.wait_until(lambda: completed == ["first"])
        self.runner.shutdown()
        self.assertFalse(self.runner.start("After shutdown", rejected, completed.append))
        self.app.processEvents()
        self.assertEqual(unexpected, [])

    def test_failure_delivers_original_error_and_allows_another_task(self):
        error = RuntimeError("Expected standalone failure")
        failures, results = [], []
        self.runner.failed.connect(lambda failure: failures.append(
            (failure, self.runner.busy, self.runner.progress, threading.get_ident())
        ))

        def task(*, progress, cancelled):
            progress("Last failure phase", 2, 5)
            raise error

        self.assertTrue(self.runner.start("Failure", task, results.append))
        self.wait_until(lambda: bool(failures))
        self.assertIs(failures[0][0], error)
        self.assertFalse(failures[0][1])
        self.assertEqual(failures[0][2]["phase"], "Last failure phase")
        self.assertEqual(failures[0][2]["completed"], 2)
        self.assertEqual(failures[0][3], threading.get_ident())
        self.assertEqual(results, [])
        self.assertFalse(self.runner._progress_timer.isActive())
        self.assertTrue(self.runner.start("Recovery", lambda **_: "recovered", results.append))
        self.wait_until(lambda: results == ["recovered"])

    def test_starting_next_task_from_busy_observer_preserves_both_callbacks(self):
        finish_second = self.event()
        results, started_second = [], []

        def second(*, progress, cancelled):
            progress("Second phase", 1, 4)
            finish_second.wait()
            return "second"

        def busy_changed():
            if not self.runner.busy and not started_second:
                started_second.append(self.runner.start("Second", second, results.append))

        self.runner.busyChanged.connect(busy_changed)
        self.assertTrue(self.runner.start("First", lambda **_: "first", results.append))
        self.wait_until(lambda: results == ["first"])
        self.assertEqual(started_second, [True])
        self.assertTrue(self.runner.busy)
        self.assertEqual(self.runner.progress["title"], "Second")
        finish_second.set()
        self.wait_until(lambda: results == ["first", "second"])

    def test_shutdown_from_start_notification_cannot_restart_the_thread(self):
        executed, completed, failures = [], [], []
        self.runner.failed.connect(failures.append)

        def task(*, progress, cancelled):
            executed.append(True)
            return "must not run after shutdown"

        self.runner.busyChanged.connect(lambda: self.runner.shutdown() if self.runner.busy else None)
        self.assertFalse(self.runner.start("Close during start", task, completed.append))
        self.assertIsNone(self.runner._thread)
        self.assertFalse(self.runner.busy)
        self.app.processEvents()
        self.assertFalse(self.runner._progress_timer.isActive())
        self.assertEqual(executed, [])
        self.assertEqual(completed, [])
        self.assertEqual(failures, [])

    def test_shutdown_joins_active_worker_without_processing_gui_events(self):
        started = self.event()
        reporters, completed, failures = [], [], []
        self.runner.failed.connect(failures.append)

        def task(*, progress, cancelled):
            reporters.append(progress)
            progress("Pending at shutdown", 1, 2)
            started.set()
            while not cancelled():
                threading.Event().wait(0.001)
            progress("After cancellation", 2, 2)
            return "must not deliver"

        self.assertTrue(self.runner.start("Active shutdown", task, completed.append))
        self.assertTrue(started.wait(1))
        self.runner.shutdown()
        self.runner.shutdown()
        self.assertFalse(self.runner._thread.isRunning())
        self.assertFalse(self.runner._progress_timer.isActive())
        before = self.runner.progress
        reporters[0]("Retired callback", 999, 1000)
        self.app.processEvents()
        self.assertEqual(self.runner.progress, before)
        self.assertEqual(completed, [])
        self.assertEqual(failures, [])
