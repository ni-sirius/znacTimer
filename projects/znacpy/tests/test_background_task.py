import os
import threading
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from znactime.storage.legacy_csv_import import LegacyImportCancelled
from znactime.ui.qt import QApplication, QTimer
from znactime.ui.qt.background import run_background_task


class BackgroundTaskTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def test_task_runs_off_the_ui_thread(self):
        ui_thread = threading.get_ident()

        result = run_background_task(
            None,
            "Test task",
            lambda *, progress, cancelled: (
                progress("Working", 1, 1),
                threading.get_ident(),
            )[1],
        )

        self.assertNotEqual(result, ui_thread)

    def test_cancel_waits_for_worker_cleanup_and_propagates(self):
        cleaned_up = threading.Event()

        def task(*, progress, cancelled):
            try:
                while not cancelled():
                    cleaned_up.wait(0.01)
                raise LegacyImportCancelled("cancelled")
            finally:
                cleaned_up.set()

        def cancel_active_dialog():
            dialog = QApplication.activeModalWidget()
            if dialog is None:
                QTimer.singleShot(0, cancel_active_dialog)
                return
            dialog.cancel_button.click()

        QTimer.singleShot(0, cancel_active_dialog)
        with self.assertRaises(LegacyImportCancelled):
            run_background_task(None, "Test cancellation", task)

        self.assertTrue(cleaned_up.is_set())


if __name__ == "__main__":
    unittest.main()
