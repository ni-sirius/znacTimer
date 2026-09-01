import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from znactime.storage.errors import StorageLocked
from znactime.storage.sqlite.bootstrap import startup_lock


class SQLiteBootstrapLockTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary.name) / "znactime.db"

    def tearDown(self):
        self.temporary.cleanup()

    def test_lock_contention_does_not_probe_or_signal_a_process(self):
        with patch("os.kill", side_effect=AssertionError("os.kill must not be called")):
            with startup_lock(self.database):
                with self.assertRaises(StorageLocked):
                    with startup_lock(self.database):
                        self.fail("A contending setup acquired the same lock.")

    def test_stale_metadata_does_not_block_a_released_advisory_lock(self):
        lock_path = self.database.with_name(self.database.name + ".lock")
        lock_path.write_text(f"{os.getpid()}\n", encoding="ascii")

        with patch("os.kill", side_effect=AssertionError("os.kill must not be called")):
            with startup_lock(self.database):
                self.assertTrue(lock_path.exists())

        # The stable lock inode remains available for the next process. Crash
        # recovery depends on the OS releasing the handle, not on deleting a PID file.
        with startup_lock(self.database):
            self.assertTrue(lock_path.exists())


if __name__ == "__main__":
    unittest.main()
