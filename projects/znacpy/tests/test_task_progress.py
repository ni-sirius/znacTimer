import threading
import unittest

from znactime.ui.quick.tasks.progress import TaskProgressBuffer


class TaskProgressBufferTest(unittest.TestCase):
    def test_only_latest_snapshot_is_pending(self):
        progress = TaskProgressBuffer()
        for completed in range(1000):
            progress.report("Reading", completed, 1000)
        self.assertEqual(progress.take(), ("Reading", 999, 1000))
        self.assertIsNone(progress.take())

    def test_finish_freezes_final_value_for_one_last_delivery(self):
        progress = TaskProgressBuffer()
        progress.report("Final phase", 4, 5)
        progress.finish()
        progress.report("Too late", 999, 1000)
        self.assertEqual(progress.close(), ("Final phase", 4, 5))
        self.assertIsNone(progress.take())
        self.assertIsNone(progress.close())

    def test_close_retires_saved_callback_and_discards_pending_data(self):
        progress = TaskProgressBuffer()
        report = progress.report
        report("Pending", 1, 2)
        self.assertEqual(progress.close(), ("Pending", 1, 2))
        report("Retired", 2, 2)
        self.assertIsNone(progress.take())

    def test_worker_reporting_after_finish_cannot_change_final_value(self):
        progress = TaskProgressBuffer()
        reported, finish = threading.Event(), threading.Event()

        def worker():
            progress.report("Before finish", 1, 2)
            reported.set()
            finish.wait()
            progress.report("After finish", 2, 2)

        thread = threading.Thread(target=worker)
        self.addCleanup(thread.join, 1)
        self.addCleanup(finish.set)
        thread.start()
        self.assertTrue(reported.wait(1))
        progress.finish()
        finish.set()
        thread.join(1)
        self.assertFalse(thread.is_alive())
        self.assertEqual(progress.take(), ("Before finish", 1, 2))
